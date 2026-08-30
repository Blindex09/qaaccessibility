import logging

from backend.src.services.llm_client import call_llm_structured, extract_json_object
from backend.src.shared.models import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the QA Accessibility Clarifier and Semantic Router. Your ONLY job is to analyze the user's incoming message and route it to the correct intent, determining if the message is within the scope of digital accessibility auditing or if it is ambiguous and needs clarification.

You must categorize the user's message into one of these intents:
- "analyze_url": User explicitly wants to audit/analyze an external URL or web page.
- "analyze_code": User explicitly wants to audit/analyze a local file path, directory, or a raw HTML/CSS/JS/TSX code snippet.
- "chat_a11y": User is asking a conversational question, requesting a tutorial, explaining a concept, discussing accessibility rules (WCAG, Section 508, WAI-ARIA, contrast, screen readers), OR sending greetings/pleasantries/introductory remarks (e.g. "fala meu amigo, blz?", "olá", "tudo bem?", "bom dia", "pode me ajudar?"). All greetings and chat starters must be routed to "chat_a11y" so the conversational agent can greet the user naturally and keep the focus on accessibility.
- "fix_code": User provides a code snippet or describes accessibility issues and wants the agent to generate/provide a fixed, accessible version of that code.
- "out_of_scope": User is explicitly asking for general programming tasks (e.g. "write a backend database script"), general software engineering, or completely unrelated topics (cooking, politics, history) that have absolutely no connection to accessibility.
- "needs_clarification": The request is related to accessibility but is ambiguous, incomplete, or lacks critical details (e.g., "analyze this" without providing any code, file, or URL target, or "how do I fix" without a code snippet or context).

## Rules:
1. "out_of_scope": digital accessibility is the core limit. If a user asks "how do I center a div" without any accessibility context, it is out of scope. If they ask "how do I make a centered div focusable for screen readers", it is "chat_a11y".
2. Greetings and pleasantries ("olá", "tudo bem", "fala meu amigo, blz", "está aí?") are NOT out of scope. Route them to "chat_a11y" so the agent can respond conversationally.
3. "needs_clarification": Set this to true if the intent is "needs_clarification". In this case, you MUST generate 1 specific, polite clarification question to ask the user. For all other intents, questions should be empty.
4. Be highly semantic and ignore keywords. Analyze the meaning.

## Output Format:
You MUST return ONLY a valid JSON object matching this schema:
{
  "intent": "analyze_url | analyze_code | chat_a11y | fix_code | out_of_scope | needs_clarification",
  "needs_clarification": true | false,
  "question": "Clarification question text here, or empty if needs_clarification is false",
  "explanation": "Brief reasoning for the classification (Portuguese if user prompt is Portuguese, otherwise English)"
}

Return ONLY raw JSON. No markdown fences, no formatting, no conversational text.
""".strip()


_INTENTS_VALIDOS = (
    "analyze_url",
    "analyze_code",
    "chat_a11y",
    "fix_code",
    "out_of_scope",
    "needs_clarification",
)

CLASSIFICACAO_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(_INTENTS_VALIDOS)},
        "needs_clarification": {"type": "boolean"},
        "question": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["intent", "needs_clarification", "question", "explanation"],
    "additionalProperties": False,
}


def _construir_classificacao(raw: str) -> dict[str, object]:
    """Parse + validacao da classificacao, usado por `call_llm_structured`.

    Levantar aqui e o que dispara o retry/repair -- um `intent` fora da lista e
    tao inutil quanto JSON quebrado, e antes passava direto para o roteamento.
    """
    data = extract_json_object(raw)
    intent = str(data.get("intent") or "").strip()
    if intent not in _INTENTS_VALIDOS:
        raise ValueError(f"intent invalido: {intent!r}; esperado um de {_INTENTS_VALIDOS}")
    return {
        "intent": intent,
        "needs_clarification": bool(data.get("needs_clarification", intent == "needs_clarification")),
        "question": str(data.get("question") or ""),
        "explanation": str(data.get("explanation") or ""),
    }


async def run_clarifier(user_message: str) -> AgentResult:
    """
    Analisa semanticamente o input do usuário para definir a intencao do chat.
    Evita chamadas caras de ferramentas se a query for fora de escopo ou ambigua.
    """
    logger.info("[ClarifierAgent] Analisando intencao da mensagem do usuário...")
    if not user_message.strip():
        return AgentResult(
            agent="clarifier",
            success=True,
            data={
                "intent": "needs_clarification",
                "needs_clarification": True,
                "question": "Olá! Como posso ajudar você hoje com a acessibilidade do seu projeto?",
                "explanation": "Mensagem vazia.",
            },
        )

    try:
        data = await call_llm_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Analyze this user message:\n\n{user_message}",
            build=_construir_classificacao,
            temperature=0.0,
            # 250 tokens nao cabiam intent + question + explanation em portugues.
            # Medido em 2026-08-30 com 10 prompts reais: 6 respostas vieram
            # cortadas no meio do JSON -- e com a intencao JA correta no inicio
            # da saida ('{"intent": "out_of_scope", ... "explanation": "O usuario')
            # -- mas o objeto nao fechava, o parse falhava e a classificacao
            # inteira era descartada. 4/10 de acerto. Mesma causa do estouro de
            # orcamento ja corrigido no VPAT e no gerador de testes.
            max_tokens=800,
            agent_label="clarifier",
            response_schema=CLASSIFICACAO_SCHEMA,
        )

        # Garante fallback e chaves basicas
        intent = data.get("intent", "needs_clarification")
        needs_clarify = bool(data.get("needs_clarification", intent == "needs_clarification"))
        question = data.get("question", "")
        explanation = data.get("explanation", "")

        logger.info("[ClarifierAgent] Intencao classificada: %s", intent)
        return AgentResult(
            agent="clarifier",
            success=True,
            data={
                "intent": intent,
                "needs_clarification": needs_clarify,
                "question": question,
                "explanation": explanation,
            },
        )
    except Exception as exc:
        logger.error("[ClarifierAgent] Falha na clarificacao: %s", exc)
        return AgentResult(
            agent="clarifier",
            success=False,
            data={},
            error=str(exc),
        )
