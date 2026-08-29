"""
Runtime do chat agentico: roda um AIAgent conversacional com streaming.

O `run_conversation` do AIAgent e sincrono e emite progresso via callbacks que
disparam na thread worker. Aqui fazemos a ponte para um async generator: os
callbacks empurram eventos numa asyncio.Queue (thread-safe via
loop.call_soon_threadsafe) e `stream_chat` os consome e entrega ao endpoint SSE.

Eventos emitidos (dict):
  {"type": "token", "text": str}        delta de texto da resposta
  {"type": "tool_start", "tool_call_id": str, "name": str,
   "arguments": dict}                  inicio de uma tool (ex.: analyze_page)
  {"type": "tool_result", "tool_call_id": str, "name": str,
   "ok": bool, "error": str | None,
   "result_summary": {...} | None}      fim de uma tool -- ver _extract_result_summary
                                        (contagem real + fontes, quando aplicavel)
  {"type": "done", "final": str,
   "usage": {"input_tokens": int,
             "output_tokens": int,
             "total_tokens": int}}      resposta final + tokens do turno
                                        ('usage' ausente se o provider não contou)
  {"type": "error", "error": str}       erro
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any

# Import com side-effect: registra o toolset 'a11y_chat' no registry local.
import backend.src.services.chat_tools  # noqa: F401
from backend.src.agents.squad import build_squad_plan
from backend.src.config.settings import get_settings
from backend.src.services import a11y_knowledge, chat_history_store, chat_progress, last_analysis_store, session_context
from backend.src.services.chat_tools import A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET
from backend.src.services.telemetry import agent_span
from backend.src.shared.error_formatter import format_human_friendly_error
from run_agent import AIAgent

logger = logging.getLogger(__name__)

_CHAT_MAX_ITERATIONS = 12
_PROVIDER_STATE_TTL_SECONDS = 60 * 60
_PROVIDER_STATE: dict[tuple[str, str, str], tuple[str, float]] = {}


def _provider_state_get(conversation_id: str | None, provider: str, model: str) -> str | None:
    if not conversation_id:
        return None
    key = (conversation_id, provider, model)
    current = _PROVIDER_STATE.get(key)
    if current is None:
        return None
    response_id, expires_at = current
    if expires_at <= time.monotonic():
        _PROVIDER_STATE.pop(key, None)
        return None
    return response_id


def _provider_state_put(
    conversation_id: str | None, provider: str, model: str, response_id: str | None
) -> None:
    if conversation_id and response_id:
        _PROVIDER_STATE[(conversation_id, provider, model)] = (
            response_id,
            time.monotonic() + _PROVIDER_STATE_TTL_SECONDS,
        )

# Constantes de intent do clarifier: fonte unica de verdade.
# Se o clarifier mudar os valores, basta atualizar aqui.
_INTENT_OUT_OF_SCOPE = "out_of_scope"
_INTENT_NEEDS_CLARIFICATION = "needs_clarification"
# Usada quando o clarifier classifica como ambíguo mas não devolve a pergunta.
_DEFAULT_CLARIFY_QUESTION = (
    "Consegue detalhar um pouco mais? Me diz qual URL, arquivo ou trecho de código "
    "você quer que eu audite, que eu já começo."
)

RESEARCH_PROTOCOL = """

### PROTOCOLO DE PESQUISA ITERATIVA (Agentic RAG — ReAct 2026)
Quando precisares de pesquisar informação normativa (WCAG, APG, ACT rules, EN 301 549, Section 508, PDF/UA, WAI-ARIA), segue obrigatoriamente este ciclo:
1. PENSAR: Formula a query mais específica possível para o que precisas encontrar.
2. AGIR: Usa tavily_search ou exa_search com essa query.
3. AVALIAR: Após receber o resultado, chama evaluate_research ou avalia internamente:
   - A informação é suficiente para responder com precisão normativa?
   - Há lacunas ou ambiguidades que exigem pesquisa adicional?
4. Se INSUFICIENTE: Refina a query (mais específica, diferente ângulo) e pesquisa novamente. Não repitas a mesma query.
5. Se SUFICIENTE ou após 3 iterações: Sintetiza a resposta citando as fontes. Se chegaste ao limite sem informação completa, avisa o utilizador das limitações.
Limite: máximo 3 pesquisas por pergunta para evitar loops.
"""


SYSTEM_PROMPT = (
    "You are the QA Accessibility assistant. You help developers, QAs, and "
    "stakeholders audit web and document accessibility against WCAG 2.2, WAI-ARIA, "
    "Section 508, the European Accessibility Act (EAA), and EN 301 549. You are strictly specialized in digital accessibility, including auditing web pages, code, and documents (DOCX, PDF, PPTX, EPUB, XLSX) to make them accessible.\n\n"
    "CRITICAL ROLE CONSTRAINT:\n"
    "- Your only focus and purpose is accessibility auditing, identifying accessibility violations, and remediating files (HTML, CSS, JS, TSX, DOCX, PDF, PPTX, EPUB, XLSX) to make them accessible.\n"
    "- You MUST reject any requests for general development help, general project structure, or legal/content analysis that do not concern accessibility. Politely refuse and state that you only specialize in accessibility.\n"
    "- If a user uploads a document like a PDF, Word, PowerPoint, EPUB, or Excel file, they want you to audit its accessibility structure (not its legal or general content). For PDF and XLSX specifically, call `analyze_document` (dedicated PDF/UA and Excel-accessibility specialist agents, real veraPDF validation for PDF when available) instead of jumping straight to a blind fix -- it gives you a real, structured list of issues to work from, and its output feeds the same export/checklist/VPAT tools as analyze_page. For DOCX/PPTX/EPUB, use the extracted text directly with your accessibility knowledge, then remediate as usual.\n"
    "- If you use search, use only the specialized tools `tavily_search` and `exa_search`. Do not try to extract the same URL again after `analyze_page` or `analyze_site` has already completed; use the analysis result and the local last-analysis cache instead.\n"
    "- You have access to two specialized search tools: `tavily_search` (good for accessibility guidelines, tutorials, target-page discovery, and articles) and `exa_search` (good for technical WCAG specifications, ACT rules, and precise accessibility references). Use either, or both, only when search is necessary for the user's accessibility task.\n\n"
    "Your communication rules:\n"
    "1. Speak in a natural, simple, human, and relaxed tone (conversa simples de um humano descontraído).\n"
    "2. Speak the user's language (Portuguese if they write in Portuguese).\n"
    "3. NEVER use any emojis in your responses (Zero emojis na sua resposta).\n"
    "4. Keep private reasoning internal. Communicate only concise, observable progress and final conclusions.\n"
    "5. ACTION DIRECTIVE FOR ATTACHED FILES: When the user attaches files (HTML, CSS, JS, DOCX, etc.) for accessibility analysis, DO NOT merely say you will analyze them later. Perform the complete, thorough accessibility audit of all attached files immediately in this turn, detailing WCAG 2.2 criterion violations, contrast issues, keyboard/focus gaps, missing accessible names/labels, and concrete remediation fixes.\n"
    "6. DO NOT use any markdown characters or formatting markers like `---`, `**`, `***`, `*`, or headers in your conversational responses. Write only clean, plain text. NEVER use empty lines or blank lines between paragraphs. If you want to start a new paragraph, use a single newline character (\\n) so that there are no blank/empty lines in the output.\n"
    "7. CRITICAL ACCENTUATION RULE: You MUST write in correct Portuguese with EVERY accent mark present. "
    "Use á, é, í, ó, ú, â, ê, ô, ã, õ, ç rigorously on EVERY word that requires them. "
    "WRONG examples you must NEVER produce: 'você', 'página', 'análise', 'não', 'começar', 'código', 'formulário', 'título', 'conteúdo', 'dinâmico', 'único', 'semântica'. "
    "CORRECT versions you MUST always use: 'você', 'página', 'análise', 'não', 'começar', 'código', 'formulário', 'título', 'conteúdo', 'dinâmico', 'único', 'semântica'. "
    "This is an accessibility tool: missing accents cause screen readers (NVDA, JAWS, VoiceOver) to mispronounce words, which is an accessibility violation itself. Zero tolerance for missing accents.\n"
    "8. Use conversational connectives and a collaborative, natural rhythm (e.g., 'Olha', 'Entendi', 'Vamos lá', 'Pelo que notei aqui...'). Avoid corporate template greetings, boilerplate disclaimers, or robotic AI introductory warnings. Speak directly like a competent colleague working with the user.\n"
    "9. If a task is complex or has ambiguity, lay out your planned action steps clearly and verify the user's intent. Offer distinct, human-friendly options when multiple paths are possible.\n"
    "10. SCOPE DISCIPLINE: Do ONLY what the user explicitly asked for. If the user asks you to check only the forms, check ONLY the forms. If the user asks you to analyze only the contrast, analyze ONLY the contrast. Do NOT expand the scope on your own. Do NOT run a full audit when a specific, focused analysis was requested. If you are unsure about the scope, ask the user before proceeding. When you finish, answer ONLY about what was asked, do not add unrequested extra information or analysis.\n"
    "11. FABLE METHOD SKILL (THINK / ACT / PROVE): Operate using disciplined agentic reasoning. Internally follow a Think -> Act -> Prove loop. Validate all accessibility assumptions against W3C/WCAG specs before presenting conclusions. Evaluate human impact through Personas (e.g. NVDA/Screen Reader user, Motor/Keyboard user).\n"
    "12. PLANNING & APPROVAL RULE: When proposing an audit plan or analyzing external targets, if you ask for approval or confirm scope, you MUST call the `clarify` tool with `question` and `choices` (e.g. ['Aprovar Plano', 'Alterar Foco', 'Cancelar']). NEVER write a plan and then immediately answer yourself in the same turn. NEVER simulate the user's reply. Once you propose a question or plan, you MUST call `clarify` and wait for the user to respond interactively.\n"
    "13. REMEDIATION CHECKPOINT RULE: AFTER running analysis and BEFORE calling `fix_and_zip_files` or modifying any code, you MUST summarize the issues to be fixed and present the proposed fixes to the user using the `clarify` tool with options like ['Aplicar Correções', 'Não Corrigir', 'Revisar Detalhes']. Wait for approval before modifying code.\n"
    "13b. PLAN FORMAT RULE: whenever the `question` you pass to `clarify` contains a plan or a "
    "checklist (rules 12 and 13), write one short line per step, each line starting with a number "
    "(`1.`) or a dash (`-`), followed by a status box, then the step text. The status box is "
    "`[ ]` for a step still to be done, `[~]` for the step in progress, and `[x]` for a step "
    "already completed.\n"
    "13c. NO SIMULATED DIALOGUE OR TEXT OPTIONS: A plan or question with options MUST NEVER be printed as plain prose followed by self-dialogue. You must call the `clarify` tool directly. Writing questions and fake answers in one turn is strictly prohibited. When calling tools, the interface automatically presents the accessible tool status cards (e.g., 'Auditando acessibilidade da página...', 'Editando arquivos...') to the user.\n"
    "14. UNIVERSAL HUMANIZED CONVERSATION & EMPATHY DIRECTIVE (2026): Respond with warm, fluid, empathetic, and human language. Listen actively, acknowledge user intent warmly, and eliminate any robotic AI disclaimers (e.g. 'As an AI model...'). Speak naturally as an intelligent, thoughtful accessibility partner.\n"
    "15. ADDITIONAL DELIVERABLE TOOLS: after an `analyze_page`/`analyze_site` has run, you have `generate_vpat` (WCAG 2.2 Voluntary Product Accessibility Template, for enterprise/government/Section 508 procurement) and `generate_test_suite` (Playwright + axe-core tests ready for the audited team's CI), both built from the most recent analysis. Offer/use these when the user asks for a VPAT, conformance report, procurement documentation, or automated/CI accessibility tests. You also have `create_github_issue` (file a GitHub issue for a finding, when the user gives or has a repo configured), `nvda_speak` (read text aloud via NVDA on the user's machine, when asked to demonstrate what a screen reader announces), and `run_remote_test` (run a Selenium/Postman/Cypress check against a live target, when the user asks for that kind of automated check). For `run_remote_test` with runner='cypress' or runner='selenium': ALWAYS ask the user first (via `clarify`) whether to run locally (the real Cypress/Selenium binary on this machine -- may already be installed, the tool checks for real) or in the cloud (real axe-core, no install needed) -- this is the user's decision, never pick one yourself or silently fall back from one to the other. Local execution runs real commands on the machine, so also ask whether to approve it once or always for this conversation (pass `remember_choice: true` if they say always, so you don't have to ask again this chat for the same runner). If local is chosen but not actually installed, the tool offers a real install (`location='install_local'`) -- ask explicitly before doing that too, it can take a few minutes. All of these, like every other tool, need rule 5's spoken explanation before you call them.\n"
    "16. LIVE PREVIEW: after `fix_and_zip_files` has fixed at least one HTML page, you have `open_live_preview`, which opens a side-by-side before/after view of the fixed page(s) for the user. Call it when the user asks to see, visualize, or compare the fixed page. The tool returns JSON with `session_id` and `total_pages` -- when it succeeds, you MUST include the literal marker `[LIVE_PREVIEW:<session_id>:<total_pages>]` somewhere in your visible response text (substituting the real values), exactly in that bracket format, so the interface can open the preview panel. Do not describe or explain this marker to the user -- it is invisible UI wiring, not part of your spoken message. Symmetrically, if the user asks you to close the preview, include the literal marker `[CLOSE_PREVIEW]` in your response.\n"
    "16b. REMOTE TEST RESULTS FEED THE SAME DELIVERABLES: a successful `run_remote_test` (cypress/selenium, any location) automatically caches its real findings and the tested page's HTML in the same place `analyze_page` does -- so right after it, `generate_checklist`, `export_xlsx`, `generate_vpat`, `generate_accessibility_statement`, `generate_test_suite`, and `fix_and_zip_files` (+ `open_live_preview` afterwards) all work directly from that real Cypress/Selenium/axe-core run, no need to `analyze_page` again first. After a remote test finds violations, proactively offer these next steps (spreadsheet, checklist, PDF, VPAT, fixing the code and showing the before/after preview) instead of waiting to be asked. Postman/Newman results are API contract checks, not page HTML issues -- they don't feed these deliverables the same way.\n"
    "16c. REMOTE TEST RESULTS IN YOUR OWN WORDS, NAMING THE REAL TOOL: when reporting a `run_remote_test` result, always name which real engine actually produced it (Cypress local, Cypress cloud, Selenium local/cloud, Newman/Postman) and state its real engine/version if present in the result (e.g. \"axe-core 4.13\"). Do not just paste the raw JSON -- narrate the findings in natural language as that specific tool reported them (what failed, how many elements, what severity), the same way you already do for `analyze_page`. Never blend or relabel a remote-test result as if it came from your own multi-agent analysis, or vice versa -- the user needs to know which real source produced which finding.\n"
    "17. UNDOING A REMEDIATION: a checkpoint of the previous state is taken automatically before every `fix_and_zip_files` run, and `undo_last_fix` restores it (analysis cache plus live-preview pages). Call it when the user regrets the fix, asks to go back, or wants the applied corrections discarded. Only the most recent fix can be undone, so say so plainly if they ask to go further back. Like every other tool, rule 5's spoken explanation comes first.\n"
    "18. SCREEN READER TESTING GUIDANCE: before giving step-by-step instructions for testing with a screen reader, you MUST know the user's environment: operating system, whether it is desktop or mobile, browser, and screen reader (if they already have one in mind). If any of these is missing from the conversation, ask before giving steps -- use the `clarify` tool when it fits a plan/approval moment, or just ask directly in your message otherwise. Never give a generic 'turn on your screen reader' instruction when the combo can be identified; each screen reader + browser pairing behaves differently (NVDA+Firefox is the most complete free combo on Windows; JAWS+Chrome/Edge is the enterprise-standard Windows combo; Narrator+Edge needs no install on Windows; VoiceOver REQUIRES Safari on both macOS and iOS -- Chrome/Firefox with VoiceOver is unreliable; TalkBack pairs with Chrome on Android). Give the exact activation shortcut and the exact navigation keys for that specific combo, not generic advice.\n"
    "19. FOLLOW-UP SUGGESTIONS: after finishing a concrete result (an analysis, a fix, a generated deliverable), end with ONE short, specific next-step suggestion tied to what you just did -- not a generic 'let me know if you need anything else'. Base it on what naturally follows the artifact you just produced (e.g., after an analysis: offer to fix the critical issues, or generate a VPAT/test suite from it; after a fix: offer to see the live preview or generate a report; after a VPAT/test suite: offer to export it or address the next-highest-severity issue). Skip this when the user's own next step is already obvious from their message (e.g., they immediately followed up with a request), when you already asked a clarifying question this turn, or when the turn ended in a plan/approval prompt (rules 12/13) -- do not stack a suggestion on top of those.\n"
    "20. \"SAVE TO MY COMPUTER\" REQUESTS: you cannot write files directly to the user's local disk -- you run as a backend service, not as code on their machine. Every deliverable tool (`export_xlsx`, `export_checklist_pdf`, `fix_and_zip_files`, `generate_vpat`, `generate_test_suite`) only ever produces a download link. If the user asks you to 'save it on my computer' (or similar), do NOT just silently hand back a link -- briefly say that you can't write to their disk directly, but the link below downloads straight to their computer through the browser when clicked (which accomplishes the same thing in practice). One short sentence is enough; don't over-explain."
)



def clean_newlines(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[\r\n]+(?:\s*[\r\n]+)*', '\n', text)


class TokenFilter:
    def __init__(self):
        self.in_whitespace_block = False
        self.block_has_nl = False

    def feed(self, text: str) -> str:
        result = []
        for char in text:
            if char in ('\r', '\n'):
                self.block_has_nl = True
                self.in_whitespace_block = True
            elif char.isspace():
                self.in_whitespace_block = True
            else:
                if self.in_whitespace_block:
                    if self.block_has_nl:
                        result.append('\n')
                    else:
                        result.append(' ')
                    self.in_whitespace_block = False
                    self.block_has_nl = False
                result.append(char)
        return "".join(result)

    def flush(self) -> str:
        if self.in_whitespace_block and self.block_has_nl:
            self.in_whitespace_block = False
            self.block_has_nl = False
            return '\n'
        return ""


# Extensao -> media_type IANA, pro shape de imagem multimodal exigido pelos 4
# providers (ver run_agent.py::_*_user_content, pesquisa 2026: PNG/JPEG/WEBP/GIF
# sao aceitos universalmente pelos modelos de visao atuais dos 5 providers).
_IMAGE_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _preprocess_base64_attachments_impl(
    message: str, extract_images: bool
) -> tuple[str, list[dict[str, str]]]:
    """Implementação compartilhada. `extract_images=True` remove imagens do
    texto e as devolve separadamente (turno atual); `extract_images=False` só
    substitui por uma nota textual (histórico -- reenviar base64 de imagens
    antigas a cada turno infla custo/contexto sem benefício)."""
    if not message:
        return "", []
    import base64
    import io

    from backend.src.services.chat_tools import (
        _read_docx_text,
        _read_epub_text,
        _read_pdf_text,
        _read_pptx_text,
        _read_xlsx_structure,
    )

    pattern = r"===\s*([^\n\r=]+)\s*===\s*\n([^=]*)"
    images: list[dict[str, str]] = []

    def replacer(match):
        filename = match.group(1).strip()
        raw_content = match.group(2)
        base64_str = re.sub(r"\s+", "", raw_content)
        _, ext = os.path.splitext(filename.lower())

        if ext in _IMAGE_MEDIA_TYPES and base64_str:
            if extract_images:
                # O regex de delimitacao ([^=]*) para o conteudo captura tudo
                # ATE o proximo '=' -- inclusive o padding '=' final do base64
                # em si, que fica cortado. Mesma correcao que o caminho de
                # documento abaixo ja fazia; sem ela, decoders estritos de
                # base64 do lado do provider podem rejeitar o payload.
                padded = base64_str
                missing_padding = len(padded) % 4
                if missing_padding:
                    padded += "=" * (4 - missing_padding)
                images.append({"media_type": _IMAGE_MEDIA_TYPES[ext], "data": padded})
                return f"=== {filename} ===\n[Imagem anexada -- analisada visualmente pelo modelo]\n\n"
            return f"=== {filename} ===\n[Imagem anexada em turno anterior -- não reenviada]\n\n"

        if ext not in (".pdf", ".docx", ".pptx", ".epub", ".xlsx") or not base64_str:
            return match.group(0)

        try:
            missing_padding = len(base64_str) % 4
            if missing_padding:
                base64_str += "=" * (4 - missing_padding)

            decoded = base64.b64decode(base64_str)
            file_like = io.BytesIO(decoded)

            if ext == ".pdf":
                text_content = _read_pdf_text(file_like)
                return f"=== {filename} ===\n[Texto extraído do PDF]\n{text_content}\n\n"
            elif ext == ".docx":
                text_content = _read_docx_text(file_like)
                return f"=== {filename} ===\n[Texto extraído do Word]\n{text_content}\n\n"
            elif ext == ".pptx":
                text_content = _read_pptx_text(file_like)
                return f"=== {filename} ===\n[Texto extraído do PowerPoint]\n{text_content}\n\n"
            elif ext == ".epub":
                text_content = _read_epub_text(file_like)
                return f"=== {filename} ===\n[Texto extraído do EPUB]\n{text_content}\n\n"
            elif ext == ".xlsx":
                text_content = _read_xlsx_structure(file_like)
                return f"=== {filename} ===\n[Estrutura extraída do XLSX]\n{text_content}\n\n"
        except Exception as e:
            logger.error("[a11y:chat] Erro ao decodificar/extrair texto do anexo %s: %s", filename, e)

        return match.group(0)

    try:
        result_text = re.sub(pattern, replacer, message)
    except Exception as exc:
        logger.error("[a11y:chat] Falha no preprocessamento do anexo: %s", exc)
        return message, []

    return result_text, images


def preprocess_base64_attachments(message: str) -> str:
    """Preprocessa o conteúdo da mensagem interceptando blocos binários em
    base64 (DOCX, PDF, PPTX, EPUB, imagens) e substituindo pelo texto extraído
    correspondente. Usado no histórico: imagens de turnos passados não são
    reenviadas (ver `extract_message_with_images` para o turno atual)."""
    text, _images = _preprocess_base64_attachments_impl(message, extract_images=False)
    return text


def extract_message_with_images(message: str) -> tuple[str, list[dict[str, str]]]:
    """Como `preprocess_base64_attachments`, mas para o turno ATUAL do chat:
    imagens (PNG/JPEG/WEBP/GIF) são removidas do texto e devolvidas
    separadamente como `{"media_type": ..., "data": <base64>}`, prontas para
    virar um content block de imagem nativo no provider (Multimodal 2026, ver
    run_agent.py::AIAgent.images)."""
    return _preprocess_base64_attachments_impl(message, extract_images=True)


_URL_RE = re.compile(r"https?://[^\s)\]}\"'>]+")

# Contagem real por ferramenta (2026-08-12, pedido do usuário: "contagem real
# nas mensagens" em vez de texto fixo). Cada entrada mapeia o nome da tool
# para (chave_do_campo_no_resultado_json, singular, plural) -- a contagem vem
# de `len(result[chave])` quando o campo é lista, ou do próprio valor quando é
# um int. Só cobre os campos que os handlers em chat_tools.py REALMENTE
# retornam (conferido em cada um) -- nunca um nome de campo adivinhado.
_COUNT_FIELDS: dict[str, tuple[str, str, str]] = {
    "analyze_page": ("issues", "problema de acessibilidade encontrado", "problemas de acessibilidade encontrados"),
    "analyze_site": ("issues", "problema de acessibilidade encontrado", "problemas de acessibilidade encontrados"),
    "analyze_document": ("issues", "problema de acessibilidade encontrado", "problemas de acessibilidade encontrados"),
    "fix_and_zip_files": ("total_files", "arquivo corrigido", "arquivos corrigidos"),
    "fix_local_project_files": ("total_files", "arquivo corrigido", "arquivos corrigidos"),
    "generate_checklist": ("checklist", "item no checklist", "itens no checklist"),
    "generate_test_suite": ("tests", "teste gerado", "testes gerados"),
    "unzip_and_list_files": ("files", "arquivo no projeto", "arquivos no projeto"),
    "read_local_project_files": ("files", "arquivo lido", "arquivos lidos"),
}

# Ferramentas de pesquisa real cujo resultado carrega fontes citáveis (URL +
# título) -- alimenta a seção "Fontes consultadas" da UI. tavily/exa tem
# estrutura própria (data.web[]); run_deep_research devolve texto corrido com
# URLs embutidas (sem título estruturado), então extrai por regex.
def _extract_sources(name: str, result: dict[str, Any]) -> list[dict[str, str]]:
    if name in ("tavily_search",):
        web = ((result.get("data") or {}).get("web")) or []
        return [{"title": str(w.get("title") or w.get("url") or ""), "url": str(w.get("url") or "")} for w in web if w.get("url")]
    if name == "exa_search":
        web = ((result.get("data") or {}).get("results")) or result.get("results") or []
        return [{"title": str(w.get("title") or w.get("url") or ""), "url": str(w.get("url") or "")} for w in web if isinstance(w, dict) and w.get("url")]
    if name == "run_deep_research":
        answer = str(result.get("answer") or "")
        urls = list(dict.fromkeys(_URL_RE.findall(answer)))  # dedup preservando ordem
        return [{"title": url, "url": url} for url in urls]
    return []


def _extract_result_summary(name: str, result_str: str) -> dict[str, Any] | None:
    """Resumo estruturado leve do resultado real de uma tool (contagem +
    fontes) para a UI construir texto dinâmico em vez de um rótulo fixo.
    Nunca lança -- resultado malformado ou tool sem mapeamento devolve None,
    e a UI cai no texto estático de sempre (toolMeta.ts)."""
    try:
        result = json.loads(result_str) if isinstance(result_str, str) else result_str
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(result, dict) or result.get("error"):
        return None

    summary: dict[str, Any] = {}

    if name in _COUNT_FIELDS:
        field, singular, plural = _COUNT_FIELDS[name]
        value = result.get(field)
        count = len(value) if isinstance(value, list) else value if isinstance(value, int) else None
        if count is not None:
            summary["count"] = count
            summary["item_singular"] = singular
            summary["item_plural"] = plural

    if name == "run_cross_browser_test":
        succeeded = result.get("engines_succeeded") or []
        if isinstance(succeeded, list):
            summary["count"] = len(succeeded)
            summary["item_singular"] = "motor de navegador testado com sucesso"
            summary["item_plural"] = "motores de navegador testados com sucesso"

    sources = _extract_sources(name, result)
    if sources:
        summary["sources"] = sources

    return summary or None


async def stream_chat(
    message: str,
    history: list[dict[str, str]] | None = None,
    provider: str | None = None,
    model: str | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Executa um turno do chat agentico e produz eventos de streaming.

    `history`: lista de {"role": "user"|"assistant", "content": str} (opcional).
    `provider`/`model`: opcionais; quando omitidos, usa a config salva em
    /settings (provider + chave + modelo "Alto"). Config única, sem duplicação.
    """
    # Interruptibilidade: token de cancelamento do turno, entregue ao cliente
    # logo no início para que POST /chat/cancel possa referenciá-lo mesmo
    # antes do primeiro token de resposta chegar. Best-effort: para de entregar
    # eventos ao stream e cancela a task assim que possível, mas não pode
    # abortar uma chamada HTTP síncrona já em andamento na thread do provider
    # (limitação do SDK, não do projeto) -- ver chat_progress.py.
    stream_id = chat_progress.new_cancel_token()
    yield {"type": "stream_id", "id": stream_id}
    # Preprocessa mensagens e histórico para extrair texto de anexos base64.
    # So o turno ATUAL extrai imagem de verdade (Multimodal 2026, ver
    # preprocess_base64_attachments) -- historico so guarda a nota textual.
    message, images = extract_message_with_images(message)
    # Histórico persistido no backend (chat_history_store.py) -- grava a mensagem
    # do usuário TAL COMO enviada neste turno, antes de qualquer merge com um
    # item residual do array `history` do cliente (linha abaixo), para nunca
    # gravar um blob duplicado/concatenado no histórico autoritativo do servidor.
    chat_history_store.append_message("user", message, session_id=conversation_id)
    if history:
        for h in history:
            h["content"] = preprocess_base64_attachments(h.get("content", ""))
    # Normalização de histórico (evita consecutivas com mesmo role, p. ex., Anthropic)
    cleaned_history: list[dict[str, Any]] = []
    for msg in (history or []):
        if cleaned_history and cleaned_history[-1]["role"] == msg["role"]:
            cleaned_history[-1]["content"] = (cleaned_history[-1].get("content") or "") + "\n\n" + (msg.get("content") or "")
        else:
            cleaned_history.append(msg.copy())

    if cleaned_history and cleaned_history[-1]["role"] == "user":
        message = (cleaned_history.pop().get("content") or "") + "\n\n" + message

    settings = get_settings()
    cfg = settings.chat_model_config()
    raw_model = model or cfg["model"] or "alto"
    raw_provider = provider or cfg["provider"] or ""

    from backend.src.services.model_router import resolve_model_and_provider

    provider, model = resolve_model_and_provider(raw_provider, raw_model, tier="alto")
    api_key = cfg["api_key"]
    base_url = cfg["base_url"] or None

    # A squad planeja o turno sem substituir o orchestrator especializado.
    # O plano é enviado ao frontend para transparência e ao modelo como
    # contrato de execução (escopo -> análise -> correção -> QA -> evidência).
    wants_implementation = bool(re.search(r"\b(corrig|remedi|fix|implementar|aplicar)\w*\b", message, re.IGNORECASE))
    squad_plan = build_squad_plan(message, include_implementation=wants_implementation)
    yield {"type": "squad_plan", "plan": squad_plan.to_dict()}

    # Triagem semântica no chat: roda apenas para o primeiro turno sem histórico.
    # Quando já existe histórico de conversa (diálogo em andamento), o clarifier não deve
    # interceptar confirmações ou respostas curtas do usuário (ex.: "pode analisar", "sim", "corrija").
    is_first_turn = not (history or cleaned_history)
    has_attachments = "[Arquivos anexados" in message or "===" in message
    if is_first_turn and not has_attachments and "PYTEST_CURRENT_TEST" not in os.environ:
        from backend.src.agents.clarifier import run_clarifier
        clarifier_res = await run_clarifier(message)
        if clarifier_res.success:
            intent = clarifier_res.data.get("intent")
            if intent == _INTENT_OUT_OF_SCOPE:
                out_of_scope_text = "Desculpe, mas sou um assistente especializado exclusivamente em acessibilidade digital (WCAG, Section 508, WAI-ARIA). Não posso ajudar com assuntos gerais ou fora de escopo."
                yield {"type": "token", "text": out_of_scope_text}
                yield {"type": "done", "final": "Pedido fora de escopo de acessibilidade."}
                chat_history_store.append_message("assistant", out_of_scope_text, session_id=conversation_id)
                chat_progress.clear_cancel_token(stream_id)
                return
            if intent == _INTENT_NEEDS_CLARIFICATION:
                question = str(clarifier_res.data.get("question") or "").strip() or _DEFAULT_CLARIFY_QUESTION
                yield {"type": "token", "text": question}
                yield {"type": "done", "final": question}
                chat_history_store.append_message("assistant", question, session_id=conversation_id)
                chat_progress.clear_cancel_token(stream_id)
                return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    token_filter = TokenFilter()

    def push(event: dict[str, Any] | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    # Callbacks do AIAgent (disparam na thread worker) -> fila async.
    def on_token(text: Any) -> None:
        if text is None:
            return  # fim de um bloco de stream; o evento 'done' fecha o turno
        filtered_text = token_filter.feed(str(text))
        if filtered_text:
            push({"type": "token", "text": filtered_text})

    def on_thinking(text: Any) -> None:
        if text is None:
            return
        push({"type": "thinking", "text": str(text)})

    def on_reasoning(text: Any) -> None:
        if text is None:
            return
        push({"type": "reasoning", "text": str(text)})

    def on_tool_start(tool_id: Any, name: Any = "", args: Any = None) -> None:
        push({
            "type": "tool_start",
            "tool_call_id": str(tool_id),
            "name": str(name),
            "arguments": args if isinstance(args, dict) else {},
        })

    def on_tool_complete(tool_id: Any, name: Any = "", args: Any = None, result: Any = None) -> None:
        summary = _extract_result_summary(str(name), result) if isinstance(result, str) else None
        parsed_result: Any = None
        if isinstance(result, str):
            try:
                parsed_result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                parsed_result = None
        elif isinstance(result, dict):
            parsed_result = result
        raw_error = parsed_result.get("error") if isinstance(parsed_result, dict) else None
        error = str(raw_error).strip() if raw_error else None
        push({
            "type": "tool_result",
            "tool_call_id": str(tool_id),
            "name": str(name),
            "ok": error is None,
            "error": error,
            "result_summary": summary,
        })

    def on_context_drift(reason: Any) -> None:
        """Transparência (Context Drift Detection, ver run_agent.py::AIAgent):
        avisa o usuário quando o agente ficou girando em falso e teve que
        reconsiderar a abordagem, em vez de deixar isso invisível."""
        push({"type": "phase", "text": "Reconsiderando a abordagem..."})

    def on_clarify(question: Any, choices: Any = None) -> str:
        """O agente pergunta algo: emite o evento e BLOQUEIA (na thread worker)
        ate o usuário responder via POST /chat/clarify. Retorna a resposta."""
        rid, ev = chat_progress.new_clarify()
        push({
            "type": "clarify",
            "request_id": rid,
            "question": str(question or ""),
            "choices": [str(c) for c in (choices or [])],
        })
        return chat_progress.wait_clarify(rid, ev)

    # Sink de progresso: o orchestrator (subagentes) emite por aqui -> fila SSE.
    # ContextVar propaga pela thread worker (to_thread) e pelo asyncio.run interno.
    sink_token = chat_progress.set_sink(lambda ev: push(ev))

    # Sessão corrente (session_context.py): fonte única lida por
    # last_analysis_store, fix_checkpoint_store, last_fix_store e
    # chat_history_store -- isola cache de análise, checkpoint de remediação,
    # páginas de preview e histórico de mensagens pela mesma conversa.
    session_token = session_context.set_current_session(conversation_id)
    cache_path = last_analysis_store.get_cache_filepath(conversation_id).replace("\\", "/")

    # Base de conhecimento local: em vez de despejar a11y_reference.md inteiro a
    # cada turno, recupera só as seções relevantes para a pergunta atual
    # (BM25 + embeddings fundidos por RRF, depois rerank).
    a11y_ref = await a11y_knowledge.build_reference_block(message)

    dynamic_prompt = (
        SYSTEM_PROMPT +
        "\n\n### SQUAD DE ACESSIBILIDADE DIGITAL\n"
        "Use o plano de squad abaixo como contrato de execução. Preserve o escopo de acessibilidade, respeite as dependências, peça aprovação antes de qualquer mutação e só conclua após QA/evidência.\n"
        f"{json.dumps(squad_plan.to_dict(), ensure_ascii=False)}\n"
        f"\n\n- The JSON results of the user's last audited URL/file are stored locally. If the user asks you to write a report or perform actions based on the previous audit results, you DO NOT need to run analyze_page again. You can read the JSON results directly using your file tools from this path: '{cache_path}'. This file contains a JSON object with 'url' and 'issues' keys (issues is a list of WCAG violations). Use it to generate reports instantly!"
        "\n- STRUCTURAL RULE, NOT OPTIONAL: once a URL/site has been analyzed in this conversation, NEVER call `analyze_page`/`analyze_site` again for that same target in a later turn -- not before `fix_and_zip_files`, not before `export_xlsx`, not before `generate_checklist`, not before `open_live_preview`. All of these already read from the same cache automatically; calling analyze_page again just re-runs the entire ~15-minute multi-agent pipeline for no benefit and makes the user wait for nothing new. The ONLY valid reason to analyze the same target again is the user explicitly asking for a fresh/new/updated scan (e.g. because they changed something and want it re-checked) -- a request for a deliverable (spreadsheet, checklist, PDF, preview, fix) is never that, on its own.\n"
        "\n- CHECKLIST RULE: if the user asks for a checklist, do NOT write it yourself from the raw JSON -- call `generate_checklist` instead. It runs the dedicated ChecklistAgent, which produces properly structured pass/fail/manual-verification items (including manual QA prompts the raw issue list doesn't have) instead of an ad-hoc summary. If the user also wants it as a file/PDF, follow up with `export_checklist_pdf` (accessible, tagged PDF/UA-1)."
        "\n- ACCESSIBILITY STATEMENT RULE: if the user asks for an accessibility statement (declaração de acessibilidade), a public conformance-status page, or wants to scope/document accessibility for a platform/consultancy engagement, call `generate_accessibility_statement` -- it reports the real conformance level, methodology, and known limitations from the last analysis, never invented text. Only pass organization_name/product_name/contact_email/contact_phone if the user actually told you those values; never invent an organization name or contact info -- the tool inserts a clearly-marked placeholder when they are missing, and you must tell the user to replace it with their real data before publishing. If the user wants it as a file/PDF, follow up with `export_accessibility_statement_pdf`."
    )
    if a11y_ref:
        dynamic_prompt += (
            "\n\n### AUTHORITATIVE ACCESSIBILITY REFERENCE (W3C APG, ACCNAME, DOCUMENTATION)"
            "\nPassages retrieved from the local knowledge base for this question:\n\n"
            f"{a11y_ref}"
        )
    dynamic_prompt += RESEARCH_PROTOCOL

    agent = AIAgent(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        max_iterations=_CHAT_MAX_ITERATIONS,
        quiet_mode=True,
        # "clarify" habilita pergunta interativa. Não habilitar o toolset
        # generico "web": ele expoe web_extract e pode repetir fetch depois de
        # analyze_page. Buscas ficam nas tools controladas tavily_search/exa_search.
        enabled_toolsets=[A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET],
        ephemeral_system_prompt=dynamic_prompt,
        prefill_messages=cleaned_history or None,
        stream_delta_callback=on_token,
        thinking_callback=on_thinking,
        reasoning_callback=on_reasoning,
        tool_start_callback=on_tool_start,
        tool_complete_callback=on_tool_complete,
        clarify_callback=on_clarify,
        context_drift_callback=on_context_drift,
        images=images,
        log_prefix="[a11y:chat]",
        # Roteamento de cache do xAI (x-grok-conv-id): agrupa por conversa real,
        # nao só pelo log_prefix genérico do chat -- o historico que cresce
        # turno a turno só cacheia bem se o mesmo servidor atender a mesma
        # conversa outra vez.
        conv_id=conversation_id or "[a11y:chat]",
        previous_provider_response_id=_provider_state_get(conversation_id, provider, model)
        if provider == "gemini"
        else None,
    )

    async def _run() -> None:
        try:
            with agent_span(
                "agent.chat_turn",
                {
                    "gen_ai.system": provider,
                    "gen_ai.request.model": model,
                    "conversation.id": conversation_id or "",
                },
            ) as span:
                res = await asyncio.to_thread(agent.run_conversation, user_message=message)
                usage = res.get("usage") or {}
                if span is not None and usage:
                    span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input_tokens", 0)))
                    span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output_tokens", 0)))
            if res.get("failed"):
                friendly_err = format_human_friendly_error(res.get("error", "Erro no chat"))
                push({"type": "error", "error": friendly_err})
            else:
                if provider == "gemini":
                    _provider_state_put(
                        conversation_id,
                        provider,
                        model,
                        str(res.get("provider_response_id") or "") or None,
                    )
                final_text = res.get("final_response") or ""
                final_text_cleaned = clean_newlines(final_text)
                done_event: dict[str, Any] = {"type": "done", "final": final_text_cleaned}
                if usage:
                    done_event["usage"] = usage
                push(done_event)
                chat_history_store.append_message("assistant", final_text_cleaned, session_id=conversation_id)
        except Exception as exc:  # pragma: no cover - caminho de erro defensivo
            logger.error("[a11y:chat] erro no turno: %s", exc)
            friendly_err = format_human_friendly_error(str(exc))
            push({"type": "error", "error": friendly_err})
        finally:
            push(None)  # sentinela de fim

    task = asyncio.create_task(_run())
    cancel_ev = chat_progress.cancel_event(stream_id)
    cancelled = False
    try:
        while True:
            get_task = asyncio.ensure_future(queue.get())
            cancel_wait = asyncio.ensure_future(cancel_ev.wait()) if cancel_ev else None
            waitables = {get_task} | ({cancel_wait} if cancel_wait is not None else set())
            done, still_pending = await asyncio.wait(waitables, return_when=asyncio.FIRST_COMPLETED)

            for fut in still_pending:
                fut.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)

            if cancel_wait is not None and cancel_wait in done:
                # Best-effort: sinaliza a task para parar; NÃO espera por ela
                # aqui -- uma chamada HTTP síncrona do provider já em
                # andamento na thread worker não pode ser abortada de fora, e
                # bloquear o generator nesse await deixaria o cliente esperando
                # o turno inteiro terminar antes de ver o evento "cancelled".
                cancelled = True
                task.cancel()
                yield {"type": "cancelled"}
                break

            event = get_task.result()
            if event is None:
                flushed = token_filter.flush()
                if flushed:
                    yield {"type": "token", "text": flushed}
                break
            yield event
    finally:
        chat_progress.reset_sink(sink_token)
        chat_progress.clear_cancel_token(stream_id)
        session_context.reset_current_session(session_token)
        if not task.done():
            task.cancel()
        if cancelled:
            # Task pode terminar bem depois (thread bloqueada no provider) --
            # descarta o resultado/exceção quando finalmente acontecer, sem
            # bloquear o fechamento do stream SSE que o cliente já recebeu.
            task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        else:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
