import contextlib
import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, Literal

from backend.src.services import agent_hooks
from backend.src.services.telemetry import agent_span

logger = logging.getLogger(__name__)

_SENSITIVE_ARGUMENT_PARTS = ("token", "secret", "password", "api_key", "authorization", "cookie")

# Cada provider nomeia os contadores de tokens à sua maneira: OpenAI Responses usa
# input/output_tokens, Chat Completions usa prompt/completion_tokens e o Gemini usa
# *_token_count. Normalizamos para um shape único no resultado do turno.
_USAGE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # prompt_eval_count/eval_count: nomes nativos da API /api/chat do Ollama
    # (biblioteca oficial `ollama`, ChatResponse) -- usado por _run_ollama_native.
    "input_tokens": ("input_tokens", "prompt_tokens", "prompt_token_count", "prompt_eval_count"),
    "output_tokens": ("output_tokens", "completion_tokens", "candidates_token_count", "eval_count"),
    "total_tokens": ("total_tokens", "total_token_count"),
}


# Fração de max_tokens reservada ao extended thinking da Anthropic por nível de
# esforço. O orçamento tem de ser menor que max_tokens e >= 1024 (docs Anthropic).
_ANTHROPIC_THINKING_BUDGET_RATIO: dict[str, float] = {
    "low": 0.25,
    "medium": 0.5,
    "high": 0.8,
    "xhigh": 0.8,
    "max": 0.8,
}
_ANTHROPIC_MIN_THINKING_BUDGET = 1024

# Níveis aceitos por `output_config.effort` na API Anthropic (docs Anthropic,
# Adaptive thinking / Effort).
_ANTHROPIC_EFFORT_LEVELS: frozenset[str] = frozenset(
    {"low", "medium", "high", "xhigh", "max"}
)

# Modelos Anthropic anteriores ao Claude 4.6 que ainda aceitam o extended
# thinking legado por orçamento de tokens. Nos modelos 4.6+ esse formato foi
# removido e a API devolve 400; por isso o default (qualquer modelo fora desta
# lista) é adaptive thinking, o que também mantém modelos futuros corretos.
_ANTHROPIC_LEGACY_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
        "claude-opus-4-5",
        "claude-opus-4-1",
        "claude-opus-4-0",
        "claude-sonnet-4-0",
    }
)

# Modelos em que o raciocínio é sempre ativo e `thinking: {"type": "disabled"}`
# devolve 400; desligar raciocínio significa omitir o campo.
_ANTHROPIC_ALWAYS_THINKING_MODELS: frozenset[str] = frozenset(
    {"claude-fable-5", "claude-mythos-5"}
)


def _anthropic_supports_adaptive_thinking(model: str) -> bool:
    """Indica se o modelo usa adaptive thinking + `output_config.effort`.

    Todo modelo Anthropic a partir do Claude 4.6 usa adaptive thinking. Só os
    modelos explicitamente listados como legado seguem no formato antigo, de
    modo que modelos novos passam a usar o formato correto sem alteração aqui.
    """
    return model not in _ANTHROPIC_LEGACY_THINKING_MODELS

# Compactacao de historico (Long-Horizon). Mensagens recentes mantidas verbatim:
# a doc de compaction da Anthropic preserva as 3 ultimas (troca anterior + turno
# atual); usamos 4 para o par completo sobreviver mesmo com uma mensagem de tool.
_KEEP_RECENT_MESSAGES = 4
# Teto por mensagem no caminho de truncamento (fallback e pares de tool).
_MAX_MESSAGE_CHARS = 2000

# Context Drift Detection (2026): janela deslizante de assinaturas de tool
# call (tool+args+resultado) e limiar de repeticao pra disparar a reflexao
# unica por conversa. Ver comentario em AIAgent.__init__.
_CONTEXT_DRIFT_WINDOW = 6
_CONTEXT_DRIFT_REPEAT_THRESHOLD = 3

# Compaction API nativa dos providers (2026): rede de seguranca SERVER-SIDE,
# complementar a compactacao CLIENT-SIDE acima (_compress_history_if_needed).
# O client-side ja mantem o historico bem abaixo do minimo de trigger nativo
# (80_000 chars ~= 20k tokens vs. minimo de 50k tokens da Anthropic), entao a
# API nativa raramente dispara em uso normal -- ela so entra para o caso raro
# de uma unica mensagem/turno estourar o limite antes da proxima compactacao
# client-side rodar. Degrada silenciosamente para a chamada padrao (sem o
# beta/param) se a conta ou versao do SDK ainda nao suportar -- zero risco de
# regressao no caminho normal.
_ANTHROPIC_COMPACTION_BETA = "compact-2026-01-12"
_ANTHROPIC_COMPACTION_MIN_TRIGGER_TOKENS = 50_000
_OPENAI_COMPACTION_THRESHOLD_TOKENS = 150_000

# Achado real (teste E2E de chat completo, 2026-08-10, provider ollama-cloud):
# em turnos de follow-up, o modelo às vezes responde só a frase de anúncio da
# ação (regra 5 do SYSTEM_PROMPT: "explicação falada ANTES de chamar a
# ferramenta") e encerra o turno sem nunca emitir a tool_call correspondente --
# sem erro, sem truncamento, o modelo simplesmente não chamou a ferramenta.
# Detecção puramente estrutural (sem lista de palavras/dominio, ver regra do
# projeto): resposta CURTA + nenhuma tool_call + ferramentas disponíveis +
# primeira chamada do turno. Respostas finais genuínas (relatórios, resumos)
# observadas no teste real tinham milhares de caracteres; anúncios de ação
# tinham uma frase única. Só dispara UMA retentativa por turno de usuário.
_NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS = 220
_NO_TOOL_CALL_NUDGE = (
    "[SYSTEM] Sua última resposta pareceu anunciar uma ação, mas nenhuma "
    "ferramenta foi chamada neste turno. Se você pretendia executar uma "
    "ação (gerar planilha, checklist, preview, corrigir arquivos, etc.), "
    "chame a ferramenta correspondente agora. Se sua resposta já estava "
    "completa e nenhuma ação era necessária, ignore esta nota e não repita "
    "o texto anterior."
)

# Achado real (validação E2E 2026-08-10, 3a rodada): um turno pedindo
# generate_accessibility_statement voltou com final_response contendo o JSON
# {"name": "...", "arguments": {...}} escrito como TEXTO, em vez de uma
# tool_call real via function-calling -- o modelo "alucinou" a chamada em
# vez de executá-la. Como o texto não é vazio nem curto o bastante pro
# gatilho de anúncio (_NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS), o nudge normal
# não disparava e o turno terminava sem a ferramenta jamais rodar. Deteccao
# puramente estrutural (formato JSON {name, arguments}, nao vocabulario de
# dominio) -- forca o nudge independente de tamanho/iteracao quando detectado.
#
# Variante achada depois (2026-08-10, mesma sessao, apos trocar pra API
# nativa do Ollama): o modelo às vezes escreve só os ARGUMENTOS de uma tool
# especifica -- ex.: {"question": "...", "options": [...]} pros parametros
# de `clarify` -- sem sequer o wrapper {"name",...}. `tools_arg` (schema das
# ferramentas disponiveis neste turno, formato OpenAI) permite reconhecer
# esse padrao tambem: se as chaves do JSON baterem com as `properties`
# esperadas de alguma tool real, e uma alucinacao parcial da mesma familia.
def _looks_like_fake_tool_call_json(text: str, tools_arg: list[dict[str, Any]] | None = None) -> bool:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(parsed, dict):
        return False
    if isinstance(parsed.get("name"), str) and isinstance(parsed.get("arguments"), dict):
        return True
    if not tools_arg or not parsed:
        return False
    parsed_keys = set(parsed.keys())
    for tool in tools_arg:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        props = fn.get("parameters", {}).get("properties", {}) if isinstance(fn, dict) else {}
        if not props:
            continue
        prop_keys = set(props.keys())
        # Pelo menos 2 chaves reais do schema da tool, e nenhuma chave estranha
        # que nao pertenca ao schema -- evita falso positivo com um JSON
        # legitimo qualquer que o agente esteja narrando/citando na resposta.
        if len(parsed_keys & prop_keys) >= min(2, len(prop_keys)) and parsed_keys <= prop_keys:
            return True
    return False


_FAKE_TOOL_CALL_NUDGE = (
    "[SYSTEM] Sua última resposta continha o texto de uma chamada de "
    "ferramenta (JSON com \"name\"/\"arguments\"), mas ela não foi executada "
    "de verdade -- foi só escrita como texto. Chame a ferramenta agora usando "
    "o mecanismo real de function-calling, não escrevendo o JSON na resposta."
)


def _empty_usage() -> dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _extract_usage(raw: Any) -> dict[str, int] | None:
    """Normaliza o bloco de usage de um provider. None quando não veio nada utilizável."""
    if raw is None:
        return None
    usage: dict[str, int] = {}
    for canonical, aliases in _USAGE_FIELD_ALIASES.items():
        for alias in aliases:
            value = raw.get(alias) if isinstance(raw, dict) else getattr(raw, alias, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[canonical] = int(value)
                break
    if not usage:
        return None
    usage.setdefault("total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
    return usage


def _accumulate_usage(accumulator: dict[str, int], raw: Any) -> None:
    """Soma o usage de mais uma chamada ao acumulador do turno (loops multi-iteração)."""
    usage = _extract_usage(raw)
    if usage is None:
        return
    for key in accumulator:
        accumulator[key] += usage.get(key, 0)


def _approval_summary(name: str, args: dict[str, Any]) -> str:
    redacted = {
        key: "[redigido]" if any(part in key.casefold() for part in _SENSITIVE_ARGUMENT_PARTS) else value
        for key, value in args.items()
    }
    canonical = json.dumps({"tool": name, "arguments": args}, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    shown = json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)
    return (
        f"A ferramenta '{name}' realizará uma ação com efeito externo ou gravará um artefato. "
        f"Argumentos: {shown}. Identificador da ação: {digest}. Aprovar exatamente esta ação?"
    )

def run_local_tool(
    name: str,
    args: dict[str, Any],
    approval_callback: Callable[[str, list[str]], str] | None = None,
) -> str:
    from tools.registry import registry
    if name not in registry.tools:
        return json.dumps({"error": f"Tool {name} not found"})

    tool = registry.tools[name]
    if tool.get("requires_approval"):
        if approval_callback is None:
            return json.dumps(
                {"error": "A ação foi bloqueada porque exige aprovação explícita do usuário."},
                ensure_ascii=False,
            )
        answer = approval_callback(
            _approval_summary(name, args),
            ["Aprovar", "Cancelar"],
        )
        if str(answer).strip().casefold() not in {"aprovar", "aprovado", "sim", "yes"}:
            return json.dumps({"error": "Ação cancelada pelo usuário."}, ensure_ascii=False)

    handler = tool["handler"]
    clean_args = {key: value for key, value in args.items() if value is not None}
    # Tools that talk back to the user (clarify) receive the same callback the
    # agent was built with; without it they cannot ask anything, so fail loudly.
    needs_callback = bool(tool.get("needs_clarify_callback"))
    if needs_callback and approval_callback is None:
        return json.dumps(
            {"error": f"A ferramenta '{name}' precisa de um canal de pergunta ao usuário, indisponível neste contexto."},
            ensure_ascii=False,
        )
    try:
        with agent_span("agent.tool", {"gen_ai.tool.name": name}):
            res = handler(clean_args, approval_callback) if needs_callback else handler(clean_args)
        if not isinstance(res, str):
            res = json.dumps(res, ensure_ascii=False)
        return res
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

class AIAgent:
    def __init__(
        self,
        model: str = "",
        provider: str = "",
        api_key: str | None = None,
        base_url: str | None = None,
        max_iterations: int = 1,
        quiet_mode: bool = False,
        max_tokens: int | None = None,
        max_context_chars: int = 80000,
        request_overrides: dict[str, Any] | None = None,
        fallback_model: dict[str, Any] | None = None,
        ephemeral_system_prompt: str | None = None,
        enabled_toolsets: list[str] | None = None,
        log_prefix: str = "",
        prefill_messages: list[dict[str, Any]] | None = None,
        stream_delta_callback: Callable[[str], None] | None = None,
        thinking_callback: Callable[[str], None] | None = None,
        reasoning_callback: Callable[[str], None] | None = None,
        tool_start_callback: Callable[[Any, str, dict[str, Any]], None] | None = None,
        tool_complete_callback: Callable[[Any, str, dict[str, Any], str], None] | None = None,
        clarify_callback: Callable[[str, list[str]], str] | None = None,
        previous_provider_response_id: str | None = None,
        conv_id: str | None = None,
        response_schema: dict[str, Any] | None = None,
        context_drift_callback: Callable[[str], None] | None = None,
        images: list[dict[str, str]] | None = None,
        enable_native_web_search: bool = False,
    ):
        self.model = model
        self.provider = (provider or "").strip().lower()
        self.api_key = api_key
        self.base_url = base_url
        self.max_iterations = max_iterations
        self.quiet_mode = quiet_mode
        self.max_tokens = max_tokens or 4096
        self.max_context_chars = max_context_chars
        self.request_overrides = request_overrides or {}
        self.fallback_model = fallback_model
        self.ephemeral_system_prompt = ephemeral_system_prompt
        self.enabled_toolsets = enabled_toolsets or []
        self.log_prefix = log_prefix
        # Busca web NATIVA do provider (2026-08-11, pedido do usuário): roda EM
        # PARALELO com tavily_search/exa_search (tools/funcao proprias do
        # projeto, ja usadas por deep_research), nunca em vez delas -- o
        # modelo escolhe qual ferramenta usar a cada chamada, tem as duas
        # disponiveis. So aplicado quando o chamador pede explicitamente (op-in
        # por agente, nao global) porque so faz sentido pra agentes que
        # realmente pesquisam a web (deep_research); a maioria dos ~25
        # especialistas de analise nao usa AIAgent com toolsets, entao nem
        # passa por aqui. Ollama/Ollama Cloud nao tem busca nativa boa (motivo
        # original do usuario pra usar tavily/exa) e Gemini NAO suporta
        # combinar google_search com function tools na mesma chamada (doc
        # oficial 2026: "The Gemini API doesn't support combining search tools
        # like googleSearch with non-search tools in the same generateContent
        # request") -- ver _native_web_search_tool_gemini_supported() abaixo,
        # que documenta essa exclusao real em vez de tentar e quebrar o
        # tool-calling normal do agente.
        self.enable_native_web_search = enable_native_web_search
        self.prefill_messages = prefill_messages or []

        self.stream_delta_callback = stream_delta_callback
        self.thinking_callback = thinking_callback
        self.reasoning_callback = reasoning_callback
        self.tool_start_callback = tool_start_callback
        self.tool_complete_callback = tool_complete_callback
        self.clarify_callback = clarify_callback
        self.previous_provider_response_id = previous_provider_response_id
        # Roteamento de cache do xAI (docs 2026, "Maximizing Cache Hits"): o
        # header x-grok-conv-id agrupa chamadas no mesmo servidor, aumentando o
        # cache hit rate. Sem valor explicito, cai no proprio log_prefix (que
        # ja identifica o especialista/turno de chat) -- nunca fica vazio.
        self.conv_id = conv_id or self.log_prefix or None
        # Structured Outputs (2026): schema JSON opcional que restringe a
        # decodificacao do modelo -- ativado so quando o chamador passa um
        # schema explicito (call_llm com response_schema=...). Nunca aplicado
        # em turnos com tools (chat): a maioria dos providers nao combina
        # "chame uma tool" com "responda so nesse schema" no mesmo turno.
        self.response_schema = response_schema if not self.enabled_toolsets else None
        # Context Drift Detection (2026): nenhum provider expoe um sinal nativo
        # de "o modelo esta travado" -- e um efeito emergente, invisivel na API
        # (pesquisa 2026: so ha finish_reason/stop_reason por limite de tokens,
        # nunca por qualidade). A tecnica pratica e barata (sem chamada extra a
        # LLM) e detectar REPETICAO: mesma tool+args+resultado varias vezes na
        # janela recente = o agente esta girando em falso. Ao detectar, injeta
        # UMA reflexao no proprio resultado da tool (o modelo sempre le isso de
        # volta) pedindo pra reconsiderar a abordagem -- e a acao de
        # "Replanning" em resposta ao "Reflection".
        self.context_drift_callback = context_drift_callback
        self._tool_call_signatures: list[str] = []
        self._drift_reflected = False
        # Multimodal (2026): imagens do turno atual, cada uma
        # {"media_type": "image/png", "data": "<base64 sem prefixo data URI>"}.
        # So o TURNO ATUAL carrega imagem -- nao faz parte do historico
        # (prefill_messages), entao nao ha replay de imagem em turnos futuros.
        # Shape verificado nas docs oficiais dos 4 caminhos de provider (ver
        # _*_user_content abaixo). Providers com visao universal nos modelos
        # atuais (OpenAI/Anthropic/Gemini/xAI); Ollama Cloud tem catalogo majoritariamente
        # texto-only e um bug documentado de 500 no endpoint OpenAI-compat com
        # alguns modelos de visao -- por isso todo caminho tenta com imagem e
        # cai para texto-only com uma nota, nunca falha o turno por causa disso.
        self.images = images or []

    @staticmethod
    def _is_plain_text_message(message: dict[str, Any]) -> bool:
        """True for a message that can be folded into a summary without breaking the API contract.

        Tool exchanges must stay intact: a `tool_calls` assistant message and its
        matching `role: "tool"` results are a pair, and every provider rejects a
        payload where one half went missing. Only plain conversational turns are
        safe to replace with a summary.
        """
        return (
            message.get("role") in ("user", "assistant")
            and isinstance(message.get("content"), str)
            and not message.get("tool_calls")
        )

    def _compress_history_if_needed(self, messages: list) -> list:
        """
        Compactacao automatica de historico para agentes Long-Horizon.

        Quando o total de caracteres do historico ultrapassa max_context_chars,
        resume por LLM o bloco mais antigo de turnos conversacionais e mantem as
        ultimas mensagens verbatim. O que nao puder ser resumido (pares de
        tool_call/tool_result) passa pela compressao estrutural existente.

        Pratica oficial Anthropic 2026 ("Compaction" / context engineering):
        resumir-e-substituir os turnos antigos ao cruzar um limiar, preservando
        os mais recentes literalmente.
        """
        total_chars = sum(len(str(m.get("content") or "")) for m in messages)
        if total_chars <= self.max_context_chars:
            return messages
        # Preserva: primeira mensagem (system) + as ultimas (contexto imediato)
        if len(messages) <= _KEEP_RECENT_MESSAGES + 1:
            return messages

        head = messages[:1]
        tail = messages[-_KEEP_RECENT_MESSAGES:]
        middle = messages[1:-_KEEP_RECENT_MESSAGES]

        # Maior prefixo do meio que e seguro resumir (so turnos de texto puro).
        foldable_end = 0
        while foldable_end < len(middle) and self._is_plain_text_message(middle[foldable_end]):
            foldable_end += 1
        foldable, remainder = middle[:foldable_end], middle[foldable_end:]

        summary_messages: list[dict[str, Any]] = []
        if foldable:
            try:
                from backend.src.services.history_summarizer import summarize_messages

                summary = summarize_messages(
                    foldable,
                    provider=self.provider,
                    model=self.model,
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                summary_messages = [{
                    "role": "user",
                    "content": f"[Resumo da conversa anterior]\n{summary}",
                }]
            except Exception as exc:
                # O resumo custa uma chamada de rede e pode falhar; degradar para
                # o truncamento antigo e melhor do que derrubar o turno.
                logger.error(
                    "%s Resumo do historico falhou (%s); caindo para truncamento.",
                    self.log_prefix, exc,
                )
                summary_messages = self._truncate_messages(foldable)

        result = head + summary_messages + self._truncate_messages(remainder) + tail
        new_total = sum(len(str(m.get("content") or "")) for m in result)
        logger.info(
            "%s Long-Horizon: historico compactado %d -> %d chars (%d resumidas, %d truncadas)",
            self.log_prefix, total_chars, new_total, len(foldable), len(remainder),
        )
        return result

    def _truncate_messages(self, messages: list) -> list:
        """Compressao estrutural por mensagem (fallback e caminho dos pares de tool)."""
        if not messages:
            return []
        try:
            from backend.src.services.context_compressor import compress as _compress
        except ImportError:
            logger.warning("%s context_compressor indisponivel, historico não comprimido.", self.log_prefix)
            return messages
        truncated = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) and len(content) > _MAX_MESSAGE_CHARS:
                truncated.append({**msg, "content": _compress(content, max_chars=_MAX_MESSAGE_CHARS)})
            else:
                truncated.append(msg)
        return truncated

    def _get_api_tools(self) -> list[dict[str, Any]]:
        """
        Constrói a lista de ferramentas no formato esperado pelo OpenAI, xAI e Ollama.

        Boa prática 2026 (platform.openai.com/docs):
        - additionalProperties: false e obrigatório em todos os schemas de parametros.
        - strict: true NÃO e usado aqui porque os schemas tem campos opcionais
          (ex.: url/html sao mutuamente exclusivos). O modo strict exige que TODOS
          os campos em properties estejam em required, o que e incompativel com a
          flexibilidade necessaria para as ferramentas de acessibilidade.
        """
        import copy

        from tools.registry import registry
        api_tools = []
        for tset in self.enabled_toolsets:
            tnames = registry.get_tool_names_for_toolset(tset)
            for name in tnames:
                if name in registry.tools:
                    schema = registry.tools[name]["schema"]
                    # Copia profunda para não mutar o schema original do registry
                    params = copy.deepcopy(
                        schema.get("parameters", {"type": "object", "properties": {}})
                    )
                    # additionalProperties: false e obrigatório pela doc oficial OpenAI 2026
                    if params.get("type") == "object":
                        params.setdefault("additionalProperties", False)
                    api_tools.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": schema.get("description", ""),
                            "parameters": params
                        }
                    })
        return api_tools

    def _get_response_tools(self) -> list[dict[str, Any]]:
        """Render tool definitions for OpenAI/xAI Responses and Gemini Interactions."""
        tools = [
            {
                "type": "function",
                "name": tool["function"]["name"],
                "description": tool["function"]["description"],
                "parameters": tool["function"]["parameters"],
                # The current schemas intentionally contain optional properties.
                "strict": False,
            }
            for tool in self._get_api_tools()
        ]
        # Busca web nativa (Responses API, docs OpenAI 2026): {"type": "web_search"}
        # -- xAI usa o mesmo formato Responses-compativel (rota pelo mesmo
        # _run_openai via base_url proprio), tools[] aceita web_search junto
        # de function tools nos dois. Ver __init__ pra escopo/motivo completo.
        if self.enable_native_web_search and self.provider in {"openai", "xai"}:
            tools.append({"type": "web_search"})
        return tools

    def _resolve_auto_fallback(self) -> dict[str, str] | None:
        """
        Calcula dinamicamente um provider/modelo de reserva (Cascata Automática / Failover 2026)
        quando o primário falha e nenhum fallback foi configurado explicitamente.
        """
        import os
        try:
            from agent.models_dev import list_agentic_models
            from backend.src.services.model_router import resolve_alto_model
        except Exception:  # pragma: no cover
            return None

        curr = (self.provider or "").strip().lower()

        # Provedor concreto individual: cascata RESTRITA ao mesmo provedor
        if curr not in {"agentic", "auto", ""}:
            try:
                models = list_agentic_models(curr)
            except Exception:
                models = []
            alternatives = [m for m in models if m != self.model]
            if alternatives:
                return {
                    "provider": curr,
                    "model": alternatives[0],
                    "api_key": self.api_key or "",
                    "base_url": self.base_url or "",
                }
            return None

        # Agentic / Auto: cascata entre múltiplos provedores com API key ativa
        providers_order = ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]
        for p in providers_order:
            env_var = f"{p.upper().replace('-', '_')}_API_KEY"
            key = os.getenv(env_var) or os.getenv(f"{p.upper()}_API_KEY")
            if key or p == "ollama":
                model = resolve_alto_model(p)
                if model:
                    return {
                        "provider": p,
                        "model": model,
                        "api_key": key or "",
                    }
        return None

    def run_conversation(self, user_message: str, task_id: str | None = None) -> dict[str, Any]:
        """
        Roda o loop do agente conversacional utilizando os SDKs oficiais.
        Sem simulação: faz chamadas reais para as APIs e executa as tools locais.
        """
        from backend.src.shared.error_formatter import format_human_friendly_error

        def _run_current() -> dict[str, Any]:
            if self.provider == "anthropic":
                return self._run_anthropic(user_message)
            if self.provider == "gemini":
                return self._run_gemini(user_message)
            if self.provider == "opencode-go" and self.model != "gpt-5.6-luna":
                # Achado real (auditoria docs/auditoria-prompt-caching-structured-
                # output-2026-08-26.md): OpenCode Go só expõe a Responses API
                # (usada por _run_openai) para o único modelo OpenAI-family do
                # catálogo (gpt-5.6-luna). Todo o resto da cadeia verificada de
                # structured output (Kimi, GLM, DeepSeek, Qwen) usa o endpoint
                # Chat Completions padrão, como o restante do catálogo do provider.
                return self._run_chat_completions(user_message)
            return self._run_openai(user_message)

        try:
            result = _run_current()
            if not result.get("failed"):
                return result
            primary_error = str(result.get("error") or "falha sem detalhe")
        except Exception as exc:
            primary_error = str(exc)

        # Multimodal (2026): nenhum provider documenta um jeito confiavel de
        # saber ANTES da chamada se o modelo aceita imagem (nem o catalogo do
        # projeto tem esse metadado -- pesquisa 2026 confirmou a lacuna); o
        # unico teste real e a resposta da API. Se a chamada com imagem falhou,
        # refaz UMA vez sem a imagem (nota explicando o porque) antes de cair
        # pra outro provider inteiro -- degradacao mais leve primeiro.
        if self.images:
            logger.warning(
                "%s Turno com imagem falhou (%s); refazendo sem a imagem.",
                self.log_prefix, primary_error,
            )
            self.images = []
            user_message = user_message + self._IMAGE_UNSUPPORTED_NOTE
            try:
                result = _run_current()
                if not result.get("failed"):
                    return result
                primary_error = str(result.get("error") or "falha sem detalhe")
            except Exception as exc:
                primary_error = str(exc)

        fallback = self.fallback_model if self.fallback_model is not None else (self._resolve_auto_fallback() or {})
        if not (fallback.get("provider") and fallback.get("model")):
            logger.error("%s Conversa falhou: %s", self.log_prefix, primary_error)
            return {"failed": True, "error": format_human_friendly_error(primary_error)}

        logger.warning(
            "%s Provider primário falhou; tentando o fallback configurado: %s",
            self.log_prefix,
            primary_error,
        )
        secondary = AIAgent(
            model=str(fallback["model"]),
            provider=str(fallback["provider"]),
            api_key=fallback.get("api_key"),
            base_url=fallback.get("base_url"),
            max_iterations=self.max_iterations,
            quiet_mode=self.quiet_mode,
            max_tokens=self.max_tokens,
            max_context_chars=self.max_context_chars,
            request_overrides=self.request_overrides,
            fallback_model={},
            ephemeral_system_prompt=self.ephemeral_system_prompt,
            enabled_toolsets=self.enabled_toolsets,
            log_prefix=f"{self.log_prefix}[fallback]",
            prefill_messages=self.prefill_messages,
            stream_delta_callback=self.stream_delta_callback,
            thinking_callback=self.thinking_callback,
            reasoning_callback=self.reasoning_callback,
            tool_start_callback=self.tool_start_callback,
            tool_complete_callback=self.tool_complete_callback,
            clarify_callback=self.clarify_callback,
            conv_id=self.conv_id,
            response_schema=self.response_schema,
            context_drift_callback=self.context_drift_callback,
            images=self.images,
        )
        fallback_result = secondary.run_conversation(user_message, task_id=task_id)
        if fallback_result.get("failed"):
            sec_err = str(fallback_result.get("error") or "falha sem detalhe")
            formatted_pri = format_human_friendly_error(primary_error)
            formatted_sec = format_human_friendly_error(sec_err)
            if "Desculpe" in formatted_pri or "Rate Limit" in formatted_pri:
                final_err = formatted_pri
            elif "Desculpe" in formatted_sec or "Rate Limit" in formatted_sec:
                final_err = formatted_sec
            else:
                final_err = (
                    f"Provider primário: {primary_error}. "
                    f"Provider de reserva: {sec_err}."
                )
            return {
                "failed": True,
                "error": final_err,
            }
        fallback_result["used_fallback"] = True
        return fallback_result

    def _check_context_drift(self, name: str, args: dict[str, Any], result: str) -> str | None:
        """Registra a assinatura (tool+args+resultado) e detecta repeticao sem
        progresso. Retorna a nota de reflexao a anexar ao resultado, ou None.
        So dispara UMA vez por conversa (`_drift_reflected`) para nao virar um
        segundo nag a cada repeticao."""
        sig = hashlib.sha256(
            f"{name}:{json.dumps(args, sort_keys=True, default=str)}:{result}".encode()
        ).hexdigest()
        self._tool_call_signatures.append(sig)
        self._tool_call_signatures = self._tool_call_signatures[-_CONTEXT_DRIFT_WINDOW:]
        if self._drift_reflected or self._tool_call_signatures.count(sig) < _CONTEXT_DRIFT_REPEAT_THRESHOLD:
            return None
        self._drift_reflected = True
        reason = f"tool '{name}' repetida {_CONTEXT_DRIFT_REPEAT_THRESHOLD}x com os mesmos argumentos e resultado, sem progresso"
        if self.context_drift_callback:
            with contextlib.suppress(Exception):
                self.context_drift_callback(reason)
        logger.warning("%s Context drift detectado: %s", self.log_prefix, reason)
        return (
            "\n\n[SYSTEM REFLECTION] Você chamou esta mesma ferramenta com os mesmos "
            "argumentos e obteve o mesmo resultado repetidamente, sem progresso. "
            "Pare e reconsidere: tente uma abordagem diferente, ou responda agora com "
            "o melhor resultado que você já tem em vez de repetir a mesma chamada."
        )

    def _execute_tool_calls(self, calls: list[tuple[str, str, dict[str, Any]]]) -> dict[str, str]:
        """Executa `run_local_tool` para cada chamada pedida pelo modelo no
        mesmo turno. Com 2+ chamadas, roda em paralelo via ThreadPoolExecutor
        em vez de sequencial -- tools de rede (tavily_search, exa_search,
        run_remote_test) sao I/O-bound, e esperar N delas uma apos a outra
        soma os tempos em vez de esperar so a mais lenta. run_local_tool ja e
        chamado de fora da thread principal (todo _run_* roda via
        asyncio.to_thread), entao os callbacks (que ja lidam com essa troca de
        thread, ex.: loop.call_soon_threadsafe do lado do chat) sao seguros de
        disparar de threads adicionais do pool. tool_complete_callback dispara
        dentro do worker assim que ESSA tool termina, nao só ao final de
        todas -- UI progressiva, nao em lote.

        Cada resultado passa por `_check_context_drift`: se a mesma tool+args
        repetir o mesmo resultado varias vezes (o agente girando em falso sem
        sinal nativo do provider pra isso -- ver comentario no __init__), uma
        nota de reflexao e anexada ao resultado que volta pro modelo.
        """
        for tool_id, name, args in calls:
            if self.tool_start_callback:
                self.tool_start_callback(tool_id, name, args)
            # Hooks plugáveis (agent_hooks.py): observadores externos registrados
            # em runtime, distintos de tool_start_callback (estrategia fixa da UI
            # de streaming). Isolado internamente -- nunca derruba o loop do agente.
            agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, tool_id, name, args)

        if len(calls) <= 1:
            results: dict[str, str] = {}
            for tool_id, name, args in calls:
                result = run_local_tool(name, args, self.clarify_callback)
                if self.tool_complete_callback:
                    self.tool_complete_callback(tool_id, name, args, result)
                agent_hooks.fire(agent_hooks.POST_TOOL_CALL, tool_id, name, args, result)
                drift_note = self._check_context_drift(name, args, result)
                results[tool_id] = result + drift_note if drift_note else result
            return results

        def _run_one(call: tuple[str, str, dict[str, Any]]) -> tuple[str, str]:
            tool_id, name, args = call
            result = run_local_tool(name, args, self.clarify_callback)
            if self.tool_complete_callback:
                self.tool_complete_callback(tool_id, name, args, result)
            agent_hooks.fire(agent_hooks.POST_TOOL_CALL, tool_id, name, args, result)
            return tool_id, result

        from concurrent.futures import ThreadPoolExecutor

        results = {}
        with ThreadPoolExecutor(max_workers=len(calls)) as executor:
            for tool_id, result in executor.map(_run_one, calls):
                results[tool_id] = result
        # Deteccao de drift roda sequencialmente apos o paralelismo -- so
        # atualiza um contador local, custo desprezivel, e evita que duas
        # threads decidam "e a minha vez de refletir" ao mesmo tempo.
        name_by_id = {tool_id: name for tool_id, name, _args in calls}
        args_by_id = {tool_id: args for tool_id, name, args in calls}
        for tool_id, result in list(results.items()):
            drift_note = self._check_context_drift(name_by_id[tool_id], args_by_id[tool_id], result)
            if drift_note:
                results[tool_id] = result + drift_note
        return results

    def _openai_user_content(self, user_message: str) -> Any:
        """Content block do turno atual pra Responses API (OpenAI/xAI). Doc
        oficial: `input_text`/`input_image` (data URI base64 ou URL) no mesmo
        array `content` da mensagem `user` -- mesmo endpoint de texto, sem
        campo separado."""
        if not self.images:
            return user_message
        parts: list[dict[str, Any]] = [{"type": "input_text", "text": user_message}]
        for img in self.images:
            parts.append({
                "type": "input_image",
                "image_url": f"data:{img['media_type']};base64,{img['data']}",
            })
        return parts

    def _anthropic_user_content(self, user_message: str) -> Any:
        """Content block do turno atual pra Messages API (Anthropic). Doc
        oficial: blocos `{"type": "image", "source": {"type": "base64", ...}}`
        misturados com `{"type": "text", ...}` no mesmo array `content`."""
        if not self.images:
            return user_message
        parts: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]}}
            for img in self.images
        ]
        parts.append({"type": "text", "text": user_message})
        return parts

    def _gemini_user_parts(self, user_message: str) -> list[dict[str, Any]]:
        """Parts do turno atual pra Interactions API (Gemini). Doc oficial:
        `inlineData` (mimeType + base64) misturado com parts de texto no
        mesmo array -- todo modelo Gemini atual e multimodal nativamente."""
        parts: list[dict[str, Any]] = [
            {"inlineData": {"mimeType": img["media_type"], "data": img["data"]}}
            for img in self.images
        ]
        parts.append({"text": user_message})
        return parts

    def _chat_completions_user_content(self, user_message: str) -> Any:
        """Content block do turno atual pro endpoint Chat Completions
        OpenAI-compat (Ollama/Ollama Cloud). Doc oficial: `image_url` com data
        URI, mesmo shape usado pela OpenAI nesse endpoint legado. Catalogo da
        Ollama Cloud e majoritariamente texto-only e ha bug documentado de 500
        nesse endpoint com alguns modelos de visao -- por isso quem chama isto
        SEMPRE trata falha caindo pra texto puro (ver _run_chat_completions)."""
        if not self.images:
            return user_message
        parts: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
        for img in self.images:
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"},
            })
        return parts

    _IMAGE_UNSUPPORTED_NOTE = (
        "\n\n[Nota: uma ou mais imagens foram enviadas mas o modelo atual não "
        "conseguiu processá-las. Descreva o que a imagem mostra, se possível.]"
    )

    def _run_openai(self, user_message: str) -> dict[str, Any]:
        if self.provider in {"ollama", "ollama-cloud"}:
            # Achado real (2026-08-10): o endpoint OpenAI-compat /v1 do Ollama Cloud
            # tem bug documentado de tool-calling (ver _run_ollama_native). A API
            # nativa /api/chat, sem esse problema, e o caminho por padrao agora.
            try:
                return self._run_ollama_native(user_message)
            except Exception as exc:
                logger.warning(
                    "%s API nativa do Ollama indisponivel (%s); caindo para o "
                    "endpoint OpenAI-compat como fallback.", self.log_prefix, exc,
                )
                return self._run_chat_completions(user_message)

        from openai import OpenAI

        base_url = self.base_url
        if not base_url and self.provider == "xai":
            base_url = "https://api.x.ai/v1"
        client = OpenAI(api_key=self.api_key or "no-key", base_url=base_url)

        # Long-Horizon: o historico so e compactado aqui, ANTES do loop. Dentro do
        # loop `input_items` vira replay de function_call + function_call_output, e
        # a Responses API rejeita um payload onde uma metade do par sumiu.
        input_items: list[Any] = self._compress_history_if_needed(
            [
                {"role": message["role"], "content": message["content"]}
                for message in self.prefill_messages
            ]
            + [{"role": "user", "content": self._openai_user_content(user_message)}]
        )
        tools = self._get_response_tools()
        final_response = ""
        usage_total = _empty_usage()

        for _iteration in range(self.max_iterations):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "input": input_items,
                "instructions": self.ephemeral_system_prompt,
                "max_output_tokens": self.max_tokens,
                "tools": tools or None,
                "store": False,
            }
            effort = self.request_overrides.get("reasoning_effort")
            if effort is not None:
                kwargs["reasoning"] = {"effort": effort}
                kwargs["include"] = ["reasoning.encrypted_content"]

            if self.provider == "xai" and self.conv_id:
                # Docs xAI 2026 ("Maximizing Cache Hits"): x-grok-conv-id roteia
                # chamadas da mesma conversa/especialista para o mesmo servidor
                # -- cache de prompt e por-servidor, sem o header o roteamento e
                # aleatorio e o hit rate cai. self.conv_id agrupa por label do
                # especialista (leaf) ou por conversation_id (chat). xAI usa
                # este metodo (Responses API), nao _run_chat_completions.
                kwargs["extra_headers"] = {"x-grok-conv-id": self.conv_id}

            # Compaction API nativa da OpenAI (2026): mesma logica de rede de
            # seguranca server-side do lado Anthropic (ver _ANTHROPIC_COMPACTION_BETA).
            # extra_body e o mecanismo padrao do SDK para campos ainda nao
            # tipados no metodo .create()/.stream() -- passar context_management
            # como kwarg direto e descartado em silencio por versoes do SDK que
            # nao conhecem o campo (nunca chega a ir para a rede); extra_body
            # forca o merge no corpo da requisicao mesmo assim. Se o servidor
            # rejeitar (conta sem o recurso), a excecao acontece na propria
            # chamada .stream()/.create(), antes de qualquer evento ser
            # consumido, e caimos para o kwargs padrao.
            kwargs_with_compaction = {
                **kwargs,
                "extra_body": {
                    "context_management": [{
                        "type": "compaction",
                        "compact_threshold": _OPENAI_COMPACTION_THRESHOLD_TOKENS,
                    }],
                },
            }
            if self.response_schema is not None:
                # Structured Outputs (2026): restringe a decodificacao ao
                # schema exato -- funciona tanto para OpenAI quanto para o
                # endpoint Responses-compativel do xAI (mesmo formato
                # "text.format", docs OpenAI). Só entra na tentativa "com
                # extras"; se o modelo/conta nao suportar, o fallback abaixo
                # tenta de novo sem NENHUM extra (compaction + schema juntos),
                # nunca deixando o subagente sem resposta.
                kwargs_with_compaction["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "accessibility_issues",
                        "schema": self.response_schema,
                        "strict": True,
                    }
                }

            if self.stream_delta_callback or self.thinking_callback or self.reasoning_callback:
                try:
                    stream_cm = client.responses.stream(**kwargs_with_compaction)
                except Exception as exc:
                    logger.debug(
                        "%s Compaction API indisponivel (%s); stream sem ela.",
                        self.log_prefix, exc,
                    )
                    stream_cm = client.responses.stream(**kwargs)
                with stream_cm as stream:
                    for event in stream:
                        event_type = str(getattr(event, "type", ""))
                        if event_type == "response.output_text.delta":
                            delta = str(getattr(event, "delta", ""))
                            if delta and self.stream_delta_callback:
                                self.stream_delta_callback(delta)
                        elif "reasoning" in event_type or "thinking" in event_type:
                            r_delta = str(getattr(event, "delta", ""))
                            if r_delta:
                                if self.thinking_callback:
                                    self.thinking_callback(r_delta)
                                if self.reasoning_callback:
                                    self.reasoning_callback(r_delta)
                    response = stream.get_final_response()
            else:
                try:
                    response = client.responses.create(**kwargs_with_compaction)
                except Exception as exc:
                    logger.debug(
                        "%s Compaction API indisponivel (%s); create sem ela.",
                        self.log_prefix, exc,
                    )
                    response = client.responses.create(**kwargs)

            _accumulate_usage(usage_total, getattr(response, "usage", None))

            status = str(getattr(response, "status", "completed"))
            if status not in {"completed", "requires_action"}:
                return {"failed": True, "error": f"Responses terminou com status {status}."}

            final_response = str(getattr(response, "output_text", "") or "")
            output = list(getattr(response, "output", []) or [])
            calls = [item for item in output if getattr(item, "type", "") == "function_call"]
            if not calls:
                return {"final_response": final_response, "failed": False, "usage": usage_total}

            replay: list[Any] = []
            for item in output:
                if hasattr(item, "model_dump"):
                    replay.append(item.model_dump(mode="json", exclude_none=True))
                elif isinstance(item, dict):
                    replay.append(item)
            parsed_calls: list[tuple[str, str, dict[str, Any]]] = []
            for call in calls:
                tool_id = str(getattr(call, "call_id", None) or getattr(call, "id", ""))
                name = str(getattr(call, "name", ""))
                raw_arguments = str(getattr(call, "arguments", "") or "")
                try:
                    args = json.loads(raw_arguments) if raw_arguments else {}
                except json.JSONDecodeError:
                    args = {"raw_args": raw_arguments}
                parsed_calls.append((tool_id, name, args))
            tool_results = self._execute_tool_calls(parsed_calls)
            results: list[dict[str, Any]] = [
                {"type": "function_call_output", "call_id": tool_id, "output": tool_results[tool_id]}
                for tool_id, _name, _args in parsed_calls
            ]
            input_items = replay + results

        return {
            "failed": True,
            "error": "O limite de iterações foi atingido enquanto ainda havia ferramentas pendentes.",
        }

    def _chat_completions_create(self, client: Any, **kwargs: Any) -> Any:
        """`client.chat.completions.create` com Structured Outputs
        (`response_format`, ver `self.response_schema`) quando aplicavel --
        formato Chat Completions padrao (mesmo shape do OpenAI). Ollama Cloud
        documentadamente NAO suporta structured outputs hoje (so a instalacao
        local suporta, via o param nativo `format` -- fora de escopo deste
        client, que usa o endpoint OpenAI-compat); a tentativa e inofensiva
        porque cai para a chamada padrao no primeiro erro.
        """
        if self.response_schema is None:
            return client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
        try:
            return client.chat.completions.create(  # type: ignore[call-overload]
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "accessibility_issues",
                        "schema": self.response_schema,
                        "strict": True,
                    },
                },
                **kwargs,
            )
        except Exception as exc:
            logger.debug(
                "%s Structured Outputs indisponivel (%s); chamada padrao sem schema.",
                self.log_prefix, exc,
            )
            return client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

    def _run_chat_completions(self, user_message: str) -> dict[str, Any]:
        from openai import OpenAI

        from agent.models_dev import get_model_info
        base_url = self.base_url
        if not base_url and self.provider in ("ollama-cloud", "ollama"):
            base_url = "https://ollama.com/v1"
        elif not base_url and self.provider == "xai":
            base_url = "https://api.x.ai/v1"
        client = OpenAI(
            api_key=self.api_key or "no-key",
            base_url=base_url
        )

        # Reasoning models on OpenAI's real API reject `max_tokens` on Chat Completions
        # and require `max_completion_tokens` instead (developers.openai.com guidance:
        # "For newer models such as GPT-5... the API no longer accepts max_tokens").
        # Scoped to provider=="openai" specifically: xAI/Ollama's OpenAI-compatible
        # endpoints were never confirmed to enforce (or even recognize) this rename, so
        # forwarding max_completion_tokens to them would risk a NEW, unverified bug.
        model_info = get_model_info(self.provider, self.model)
        is_reasoning_model = bool(model_info and model_info.reasoning)
        uses_max_completion_tokens = self.provider == "openai" and is_reasoning_model
        token_limit_kwarg = "max_completion_tokens" if uses_max_completion_tokens else "max_tokens"


        # Constrói o histórico de mensagens
        messages: list[dict[str, Any]] = []
        if self.ephemeral_system_prompt:
            messages.append({"role": "system", "content": self.ephemeral_system_prompt})
        for m in self.prefill_messages:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": self._chat_completions_user_content(user_message)})

        tools = self._get_api_tools()
        tools_arg = tools if tools else None

        final_response = ""
        usage_total = _empty_usage()
        no_tool_call_nudge_used = False
        any_tool_called = False
        for _iteration in range(self.max_iterations):
            # Long-Horizon: comprime historico se ultrapassar o limite de contexto
            messages = self._compress_history_if_needed(messages)
            kwargs = {token_limit_kwarg: self.max_tokens}
            if "temperature" in self.request_overrides:
                kwargs["temperature"] = self.request_overrides["temperature"]
            # Forwarded so leaf subagents can actually disable/tune reasoning depth
            # (llm_client.py computes this into request_overrides but it previously
            # went nowhere -- only "temperature" was ever read out of the dict here).
            # xAI's OpenAI-compatible endpoint accepts the same param name. Ollama:
            # o campo "think" e so da API nativa /api/chat -- este client usa o
            # endpoint OpenAI-compat (base_url=https://ollama.com/v1), que suporta
            # reasoning_effort igual (docs Ollama 2026, /api/openai-compatibility).
            # Sem isso, a feature "desligar raciocinio" (reasoning_effort="none")
            # de sub-agentes folha nunca chegava aos modelos hospedados no Ollama
            # Cloud (Kimi/GLM/DeepSeek), so pra OpenAI/xAI.
            if "reasoning_effort" in self.request_overrides and self.provider in ("openai", "xai", "ollama", "ollama-cloud"):
                kwargs["reasoning_effort"] = self.request_overrides["reasoning_effort"]

            # Se for streaming, processa em pedaços
            if self.stream_delta_callback or self.thinking_callback or self.reasoning_callback:
                # **kwargs no meio dos argumentos nomeados impede o mypy de resolver o
                # overload correto de .create() (stream=True vs False); ver mesma nota
                # no bloco Anthropic acima.
                response_stream: Any = self._chat_completions_create(
                    client,
                    model=self.model,
                    messages=messages,
                    tools=tools_arg,
                    stream=True,
                    # Sem include_usage o endpoint OpenAI-compat não manda contagem de
                    # tokens nenhuma no modo stream (docs OpenAI/Ollama, stream_options).
                    stream_options={"include_usage": True},
                    **kwargs
                )

                content_chunks = []
                tool_calls_dict = {}

                for chunk in response_stream:
                    # O chunk final de usage vem sem choices.
                    _accumulate_usage(usage_total, getattr(chunk, "usage", None))
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # Captura eventos de pensamento/raciocínio (OpenAI, xAI, Ollama Cloud, DeepSeek, Kimi)
                    reasoning_chunk = (
                        getattr(delta, "reasoning_content", None)
                        or getattr(delta, "reasoning", None)
                        or getattr(delta, "thinking", None)
                    )
                    if isinstance(reasoning_chunk, str) and reasoning_chunk:
                        if self.thinking_callback:
                            self.thinking_callback(reasoning_chunk)
                        if self.reasoning_callback:
                            self.reasoning_callback(reasoning_chunk)

                    # Trata texto simples
                    if delta.content:
                        content_chunks.append(delta.content)
                        if self.stream_delta_callback:
                            self.stream_delta_callback(delta.content)

                    # Trata tool calls no stream
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {"id": tc.id, "name": tc.function.name, "arguments": ""}
                            if tc.id:
                                tool_calls_dict[idx]["id"] = tc.id
                            if tc.function.name:
                                tool_calls_dict[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_dict[idx]["arguments"] += tc.function.arguments

                final_response = "".join(content_chunks)

                # Se detectou chamadas de ferramenta
                if tool_calls_dict:
                    any_tool_called = True
                    # Registra a chamada na história de mensagens do modelo
                    assistant_message = {
                        "role": "assistant",
                        "content": final_response or None,
                        "tool_calls": [
                            {
                                "id": tc_val["id"],
                                "type": "function",
                                "function": {
                                    "name": tc_val["name"],
                                    "arguments": tc_val["arguments"]
                                }
                            }
                            for tc_val in tool_calls_dict.values()
                        ]
                    }
                    messages.append(assistant_message)

                    # Executa cada ferramenta (paralelo se houver mais de uma)
                    parsed_calls = []
                    for tc_val in tool_calls_dict.values():
                        tool_id = tc_val["id"]
                        name = tc_val["name"]
                        args_str = tc_val["arguments"]
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except Exception:
                            args = {"raw_args": args_str}
                        parsed_calls.append((tool_id, name, args))

                    tool_results = self._execute_tool_calls(parsed_calls)
                    for tool_id, _name, _args in parsed_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": tool_results[tool_id]
                        })
                    continue  # Continua no próximo turno do loop do agente
                elif (
                    not no_tool_call_nudge_used
                    and tools_arg
                    and (
                        # Achado real (validação E2E 2026-08-10): resposta
                        # TOTALMENTE vazia sem tool_call nunca é um fim de
                        # turno válido -- dispara em QUALQUER iteração, não só
                        # na primeira (aconteceu na 4a chamada de um turno real,
                        # depois de um segundo clarify dentro do mesmo turno).
                        len(final_response.strip()) == 0
                        or (_iteration == 0 and len(final_response.strip()) <= _NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS)
                        or _looks_like_fake_tool_call_json(final_response, tools_arg)
                    )
                ):
                    no_tool_call_nudge_used = True
                    nudge = _FAKE_TOOL_CALL_NUDGE if _looks_like_fake_tool_call_json(final_response, tools_arg) else _NO_TOOL_CALL_NUDGE
                    messages.append({"role": "assistant", "content": final_response})
                    messages.append({"role": "user", "content": nudge})
                    continue
                else:
                    break  # Sem ferramentas chamadas, encerra o loop
            else:
                # Chamada síncrona/não streaming (para subagentes rápidos). **kwargs
                # splat impede o mypy de resolver o overload correto, ver nota acima.
                resp = self._chat_completions_create(
                    client,
                    model=self.model,
                    messages=messages,
                    tools=tools_arg,
                    **kwargs
                )
                _accumulate_usage(usage_total, getattr(resp, "usage", None))
                msg = resp.choices[0].message
                final_response = msg.content or ""

                if msg.tool_calls:
                    any_tool_called = True
                    messages.append(msg)
                    parsed_calls = []
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except Exception:
                            args = {"raw_args": tc.function.arguments}
                        parsed_calls.append((tc.id, tc.function.name, args))

                    tool_results = self._execute_tool_calls(parsed_calls)
                    for tool_id, _name, _args in parsed_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": tool_results[tool_id]
                        })
                    continue
                elif (
                    not no_tool_call_nudge_used
                    and tools_arg
                    and (
                        # Achado real (validação E2E 2026-08-10): resposta
                        # TOTALMENTE vazia sem tool_call nunca é um fim de
                        # turno válido -- dispara em QUALQUER iteração, não só
                        # na primeira (aconteceu na 4a chamada de um turno real,
                        # depois de um segundo clarify dentro do mesmo turno).
                        len(final_response.strip()) == 0
                        or (_iteration == 0 and len(final_response.strip()) <= _NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS)
                        or _looks_like_fake_tool_call_json(final_response, tools_arg)
                    )
                ):
                    no_tool_call_nudge_used = True
                    nudge = _FAKE_TOOL_CALL_NUDGE if _looks_like_fake_tool_call_json(final_response, tools_arg) else _NO_TOOL_CALL_NUDGE
                    messages.append({"role": "assistant", "content": final_response})
                    messages.append({"role": "user", "content": nudge})
                    continue
                else:
                    break

        if not final_response.strip() and not any_tool_called and tools_arg:
            # Achado real (validação E2E 2026-08-10): depois do retry de nudge
            # acima, se o modelo ainda voltar vazio e sem nenhuma tool_call em
            # NENHUMA iteração do turno inteiro, o loop simplesmente `break`ava
            # e devolvia final_response="" -- o usuário via uma resposta
            # completamente em branco, sem explicação e sem a ação pedida ter
            # ocorrido (reproduzido ao vivo: turno "Corrige os problemas... gera
            # o zip" não chamou fix_and_zip_files nem respondeu nada). Nunca
            # devolver silêncio: se nenhuma ferramenta rodou no turno inteiro,
            # é honesto dizer isso ao usuário em vez de deixá-lo sem resposta.
            #
            # `and tools_arg`: achado real (2026-08-10, mesma sessão) -- sem
            # essa condicao, chamadas SEM ferramentas (ClassifierAgent,
            # ClarifierAgent e outros agentes especialistas que so esperam JSON
            # cru, nunca tool_calls) tambem recebiam esse texto de chat como
            # "resposta", quebrando o parser JSON deles com uma mensagem
            # humana em vez de uma string vazia -- pior que o problema original
            # pra esses chamadores. O fallback humanizado so faz sentido pra
            # turnos de chat conversacional de verdade, que sempre tem tools_arg.
            final_response = (
                "Não consegui processar esse pedido -- a resposta do modelo veio "
                "vazia mesmo após uma nova tentativa. Pode reformular o pedido ou "
                "tentar novamente?"
            )

        return {"final_response": final_response, "failed": False, "usage": usage_total}

    def _ollama_native_user_content(self, user_message: Any) -> tuple[str, list[str] | None]:
        """Conteudo do turno atual pra API nativa do Ollama (/api/chat, biblioteca
        oficial `ollama`). Diferente do endpoint OpenAI-compat (content-array com
        image_url), a API nativa usa uma lista simples de imagens base64 no campo
        `images` da mensagem -- sem wrapper de content-array.

        Achado real (2026-08-11, validando fix_local_project_files/
        _verify_layout_visually em chat_tools.py): alguns chamadores montam o
        proprio content-array estilo OpenAI (`[{"type": "text", ...},
        {"type": "image_url", ...}]`) e passam direto como `user_message`, em
        vez de usar `self.images` (a convencao que os outros `_xxx_user_content`
        desta classe esperam). O endpoint OpenAI-compat aceita esse shape sem
        conversao (e' o mesmo formato), mas a API nativa do Ollama exige
        `content` como string -- um `user_message` lista causava erro de
        validacao Pydantic ("content deveria ser string, veio lista") e a
        chamada caia sempre pro fallback OpenAI-compat, nunca usando a API
        nativa de verdade. Normaliza os dois formatos aqui."""
        text_parts: list[str] = []
        images: list[str] = []

        if isinstance(user_message, list):
            for block in user_message:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "image_url":
                    url = (block.get("image_url") or {}).get("url", "")
                    if url.startswith("data:") and ";base64," in url:
                        images.append(url.split(";base64,", 1)[1])
        else:
            text_parts.append(user_message)

        if self.images:
            images.extend(img["data"] for img in self.images)

        return "\n".join(text_parts), (images or None)

    def _run_ollama_native(self, user_message: str) -> dict[str, Any]:
        """Achado real (validação E2E 2026-08-10, pesquisa confirmada via docs
        oficiais Ollama/openclaw): o endpoint OpenAI-compat `/v1` do Ollama Cloud
        tem um problema DOCUMENTADO de tool-calling -- o modelo pode emitir o JSON
        da chamada como texto puro em vez de uma tool_call estruturada de verdade
        (exatamente o bug reproduzido ao vivo nesta sessão: generate_accessibility_
        statement virou texto `{"name": ..., "arguments": ...}` em vez de executar).
        A correção definitiva (não so o nudge defensivo em _run_chat_completions) e
        usar a API nativa `/api/chat` via a biblioteca oficial `ollama`, que nao tem
        esse problema conhecido. Mantem a mesma logica de nudge/fallback como rede
        de seguranca adicional, mas o objetivo aqui e o tool-calling ser confiavel
        por construcao, nao so detectado e corrigido depois."""
        import ollama as ollama_lib

        host = self.base_url or "https://ollama.com"
        if host.endswith("/v1"):
            host = host[: -len("/v1")]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        client = ollama_lib.Client(host=host, headers=headers)

        messages: list[dict[str, Any]] = []
        if self.ephemeral_system_prompt:
            messages.append({"role": "system", "content": self.ephemeral_system_prompt})
        for m in self.prefill_messages:
            messages.append({"role": m["role"], "content": m["content"]})
        user_text, user_images = self._ollama_native_user_content(user_message)
        user_msg: dict[str, Any] = {"role": "user", "content": user_text}
        if user_images:
            user_msg["images"] = user_images
        messages.append(user_msg)

        tools = self._get_api_tools()
        tools_arg = tools if tools else None

        # Traduz reasoning_effort (escala interna do projeto) pro parametro nativo
        # `think` (bool ou 'low'/'medium'/'high') -- "none" desliga, o resto mapeia
        # pro nivel mais proximo. Best-effort: modelo sem suporte a thinking ignora.
        think: bool | Literal["low", "medium", "high"] | None = None
        effort = self.request_overrides.get("reasoning_effort")
        if effort == "none":
            think = False
        elif effort == "low":
            think = "low"
        elif effort == "medium":
            think = "medium"
        elif effort in ("high", "xhigh", "max"):
            think = "high"

        options: dict[str, Any] = {"num_predict": self.max_tokens}
        if "temperature" in self.request_overrides:
            options["temperature"] = self.request_overrides["temperature"]

        final_response = ""
        usage_total = _empty_usage()
        no_tool_call_nudge_used = False
        any_tool_called = False

        for _iteration in range(self.max_iterations):
            messages = self._compress_history_if_needed(messages)

            stream = client.chat(
                model=self.model,
                messages=messages,
                tools=tools_arg,
                stream=True,
                think=think,
                options=options,
            )

            content_chunks: list[str] = []
            captured_tool_calls: list[Any] = []
            for chunk in stream:
                if chunk.message.thinking:
                    if self.thinking_callback:
                        self.thinking_callback(chunk.message.thinking)
                    if self.reasoning_callback:
                        self.reasoning_callback(chunk.message.thinking)
                if chunk.message.content:
                    content_chunks.append(chunk.message.content)
                    if self.stream_delta_callback:
                        self.stream_delta_callback(chunk.message.content)
                if chunk.message.tool_calls:
                    # A API nativa manda a tool_call ja completa num unico chunk
                    # (arguments ja vem como dict parseado, nao fragmento de JSON
                    # incremental por indice como no endpoint OpenAI-compat) --
                    # sem necessidade de reconstrucao incremental aqui.
                    captured_tool_calls.extend(chunk.message.tool_calls)
                if chunk.done:
                    _accumulate_usage(usage_total, chunk)

            final_response = "".join(content_chunks)

            if captured_tool_calls:
                any_tool_called = True
                messages.append({
                    "role": "assistant",
                    "content": final_response or None,
                    "tool_calls": [
                        {"function": {"name": tc.function.name, "arguments": dict(tc.function.arguments)}}
                        for tc in captured_tool_calls
                    ],
                })
                parsed_calls = [
                    (f"call-{idx}", tc.function.name, dict(tc.function.arguments))
                    for idx, tc in enumerate(captured_tool_calls)
                ]
                tool_results = self._execute_tool_calls(parsed_calls)
                for tool_id, name, _args in parsed_calls:
                    messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "content": tool_results[tool_id],
                    })
                continue
            elif (
                not no_tool_call_nudge_used
                and tools_arg
                and (
                    len(final_response.strip()) == 0
                    or (_iteration == 0 and len(final_response.strip()) <= _NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS)
                    or _looks_like_fake_tool_call_json(final_response, tools_arg)
                )
            ):
                no_tool_call_nudge_used = True
                nudge = _FAKE_TOOL_CALL_NUDGE if _looks_like_fake_tool_call_json(final_response, tools_arg) else _NO_TOOL_CALL_NUDGE
                messages.append({"role": "assistant", "content": final_response})
                messages.append({"role": "user", "content": nudge})
                continue
            else:
                break

        if not final_response.strip() and not any_tool_called and tools_arg:
            # `and tools_arg`: sem ferramentas disponiveis (chamadas de agentes
            # especialistas so-JSON como ClassifierAgent/ClarifierAgent, nunca
            # tool_calls) este fallback humanizado quebraria o parser JSON deles
            # -- ver comentario completo na mesma condicao em _run_chat_completions.
            final_response = (
                "Não consegui processar esse pedido -- a resposta do modelo veio "
                "vazia mesmo após uma nova tentativa. Pode reformular o pedido ou "
                "tentar novamente?"
            )

        return {"final_response": final_response, "failed": False, "usage": usage_total}

    def _anthropic_reasoning_kwargs(self, model: str, effort: str) -> dict[str, Any]:
        """Traduz reasoning_effort para os campos de raciocínio da API Anthropic.

        Modelos a partir de Claude 4.6 (Opus 4.6/4.7/4.8/5, Sonnet 4.6/5, Fable 5)
        usam adaptive thinking + `output_config.effort`; o formato legado
        `thinking: {"type": "enabled", "budget_tokens": N}` foi removido e devolve
        400 nesses modelos. Modelos anteriores continuam no formato legado.
        Devolve um fragmento de kwargs (possivelmente vazio) para `messages.create`.
        """
        if _anthropic_supports_adaptive_thinking(model):
            if effort == "none":
                if model in _ANTHROPIC_ALWAYS_THINKING_MODELS:
                    # Fable 5 rejeita thinking desabilitado explicitamente; omitir
                    # o campo é a forma suportada de não configurar raciocínio.
                    return {}
                return {"thinking": {"type": "disabled"}}
            if effort not in _ANTHROPIC_EFFORT_LEVELS:
                logger.warning(
                    "%s reasoning_effort '%s' desconhecido para Anthropic; "
                    "enviando adaptive thinking sem effort.",
                    self.log_prefix, effort,
                )
                return {"thinking": {"type": "adaptive"}}
            return {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": effort},
            }

        if effort == "none":
            return {"thinking": {"type": "disabled"}}
        ratio = _ANTHROPIC_THINKING_BUDGET_RATIO.get(effort)
        if ratio is None:
            logger.warning(
                "%s reasoning_effort '%s' desconhecido para Anthropic; enviando sem thinking.",
                self.log_prefix, effort,
            )
            return {}
        budget = int(self.max_tokens * ratio)
        if budget < _ANTHROPIC_MIN_THINKING_BUDGET:
            logger.warning(
                "%s max_tokens=%d é baixo demais para o orçamento mínimo de thinking (%d); "
                "enviando sem thinking.",
                self.log_prefix, self.max_tokens, _ANTHROPIC_MIN_THINKING_BUDGET,
            )
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    def _anthropic_messages_create(self, client: Any, **kwargs: Any) -> Any:
        """`client.messages.create` com o Compaction API nativo da Anthropic
        (beta `compact-2026-01-12`) e Structured Outputs (`output_config.format`,
        ver `self.response_schema`) como redes de seguranca -- ver comentario em
        `_ANTHROPIC_COMPACTION_BETA` acima. `extra_headers`/`extra_body` sao o
        mecanismo padrao do SDK para campos de beta ainda nao tipados; se a
        conta ou a versao do SDK nao suportar o beta OU o schema, a API rejeita
        a chamada e caimos para a chamada padrao (SEM nenhum extra, `kwargs`
        original intocado) sem nenhum efeito no restante do fluxo. `output_config`
        e mesclado (nao sobrescrito) porque `_anthropic_reasoning_kwargs` pode
        ja ter posto `effort` la; a chamada de fallback usa o `kwargs` original,
        entao nunca herda um schema/effort que a API tenha rejeitado.
        """
        try:
            call_kwargs = dict(kwargs)
            if self.response_schema is not None:
                call_kwargs["output_config"] = {
                    **kwargs.get("output_config", {}),
                    "format": {"type": "json_schema", "schema": self.response_schema},
                }
            return client.messages.create(
                extra_headers={"anthropic-beta": _ANTHROPIC_COMPACTION_BETA},
                extra_body={
                    "context_management": {
                        "edits": [{
                            "type": "compact_20260112",
                            "trigger": {
                                "type": "input_tokens",
                                "value": _ANTHROPIC_COMPACTION_MIN_TRIGGER_TOKENS,
                            },
                        }],
                    },
                },
                **call_kwargs,
            )
        except Exception as exc:
            logger.debug(
                "%s Compaction API/Structured Outputs indisponivel (%s); chamada padrao sem eles.",
                self.log_prefix, exc,
            )
            return client.messages.create(**kwargs)

    def _run_anthropic(self, user_message: str) -> dict[str, Any]:
        from anthropic import Anthropic

        from agent.models_dev import get_model_info
        client = Anthropic(api_key=self.api_key)

        system = self.ephemeral_system_prompt or ""
        # Prompt caching (Anthropic): o system prompt de cada sub-agente/turno de
        # chat e 100% estatico entre chamadas -- so a mensagem do usuario (HTML
        # analisado, pergunta do chat) varia por request. Marcar o bloco como
        # cache_control=ephemeral evita reprocessar/re-cobrar o prompt inteiro em
        # cada uma das ~25 chamadas por auditoria (docs Anthropic: reduz custo em
        # ate 90% e latencia em ate 85% em prefixos repetidos). Abaixo do minimo
        # de tokens cacheavel do modelo, a API ignora o cache_control em silencio
        # -- sem risco de erro em prompts curtos.
        system_arg: str | list[dict[str, Any]] = system
        if system:
            system_arg = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

        messages = []
        for m in self.prefill_messages:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": self._anthropic_user_content(user_message)})

        # Mapeia as ferramentas para o formato do Anthropic
        tools = []
        from tools.registry import registry
        for tset in self.enabled_toolsets:
            tnames = registry.get_tool_names_for_toolset(tset)
            for name in tnames:
                if name in registry.tools:
                    schema = registry.tools[name]["schema"]
                    tools.append({
                        "name": name,
                        "description": schema.get("description", ""),
                        "input_schema": schema.get("parameters", {"type": "object", "properties": {}})
                    })
        if tools:
            # Os schemas de ferramenta tambem sao estaticos por toolset -- mesmo
            # tratamento de cache do system prompt, marcado no ultimo bloco (a
            # API cacheia o prefixo acumulado até o breakpoint marcado).
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

        # Busca web nativa (Anthropic server tool, docs 2026): roda EM PARALELO
        # com tavily_search/exa_search, o modelo escolhe qual usar. Adicionado
        # DEPOIS da marcacao de cache acima (nao faz parte do prefixo cacheavel
        # das function tools). Ver AIAgent.__init__ pra escopo/motivo completo.
        if self.enable_native_web_search and self.provider == "anthropic":
            tools.append({"type": "web_search_20260209", "name": "web_search"})

        tools_arg = tools if tools else None
        model_info = get_model_info(self.provider, self.model)
        is_reasoning_model = bool(model_info and model_info.reasoning)

        final_response = ""
        usage_total = _empty_usage()
        for _iteration in range(self.max_iterations):
            # Long-Horizon: comprime historico se ultrapassar o limite de contexto
            messages = self._compress_history_if_needed(messages)
            kwargs: dict[str, Any] = {}
            if "temperature" in self.request_overrides:
                kwargs["temperature"] = self.request_overrides["temperature"]
            # Encaminha reasoning_effort como os outros três providers fazem. Só
            # modelos de reasoning aceitam thinking, então o catálogo é o gate --
            # mesmo critério do max_completion_tokens em _run_chat_completions.
            effort = self.request_overrides.get("reasoning_effort")
            if effort is not None and is_reasoning_model:
                kwargs.update(self._anthropic_reasoning_kwargs(self.model, str(effort)))
            if _anthropic_supports_adaptive_thinking(self.model):
                # Claude 4.6+ removeu temperature/top_p/top_k: enviar qualquer um
                # devolve 400 (docs Anthropic, migração Opus 4.7).
                kwargs.pop("temperature", None)
            elif kwargs.get("thinking", {}).get("type") == "enabled":
                # Nos modelos legados a API rejeita temperature com thinking ligado.
                kwargs.pop("temperature", None)

            if self.stream_delta_callback or self.thinking_callback or self.reasoning_callback:
                # Anotado como Any: **kwargs no meio dos argumentos nomeados impede o mypy
                # de resolver o overload correto de .create() (stream=True vs False), então
                # ele cai num union amplo que não bate com o shape real dos eventos. O código
                # já faz o narrowing correto em runtime via `.type ==` abaixo.
                response_stream: Any = self._anthropic_messages_create(
                    client,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_arg,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    messages=messages,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    tools=tools_arg,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    stream=True,
                    **kwargs
                )

                content_chunks = []
                tool_calls_dict = {}
                # Blocos de thinking precisam ser ecoados de volta com a `signature`
                # opaca da API (docs Anthropic: "pass them back unchanged... the
                # server decrypts the signature to reconstruct the original
                # thinking"). No streaming, a signature chega via `signature_delta`
                # pouco antes do `content_block_stop`; sem capturar aqui, o replay
                # da próxima iteração do loop de tools perde o bloco de thinking e a
                # API pode rejeitar ("Invalid signature in thinking block") ou
                # degradar o raciocinio encadeado entre chamadas de tool.
                thinking_blocks: dict[int, dict[str, str]] = {}

                # Para streaming do Anthropic, processamos cada tipo de evento
                for event in response_stream:
                    # message_start traz input_tokens; message_delta traz output_tokens.
                    if event.type == "message_start":
                        _accumulate_usage(usage_total, getattr(event.message, "usage", None))
                    elif event.type == "message_delta":
                        _accumulate_usage(usage_total, getattr(event, "usage", None))
                    elif event.type == "content_block_start":
                        block = event.content_block
                        block_type = getattr(block, "type", "")
                        idx = event.index
                        if block_type == "thinking":
                            thinking_init = getattr(block, "thinking", "")
                            thinking_blocks[idx] = {"thinking": thinking_init, "signature": ""}
                            if thinking_init:
                                if self.thinking_callback:
                                    self.thinking_callback(thinking_init)
                                if self.reasoning_callback:
                                    self.reasoning_callback(thinking_init)
                        elif block_type == "tool_use":
                            tool_calls_dict[idx] = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": ""
                            }
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        idx = event.index
                        if delta.type == "text_delta":
                            content_chunks.append(delta.text)
                            if self.stream_delta_callback:
                                self.stream_delta_callback(delta.text)
                        elif delta.type == "thinking_delta":
                            thinking_text = getattr(delta, "thinking", "")
                            if thinking_text:
                                if idx in thinking_blocks:
                                    thinking_blocks[idx]["thinking"] += thinking_text
                                if self.thinking_callback:
                                    self.thinking_callback(thinking_text)
                                if self.reasoning_callback:
                                    self.reasoning_callback(thinking_text)
                        elif delta.type == "signature_delta":
                            signature = getattr(delta, "signature", "")
                            if idx in thinking_blocks and signature:
                                thinking_blocks[idx]["signature"] += signature
                        elif delta.type == "input_json_delta":
                            # Acumula argumentos JSON da tool
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {"id": "", "name": "", "arguments": ""}
                            tool_calls_dict[idx]["arguments"] += delta.partial_json

                final_response = "".join(content_chunks)

                if tool_calls_dict:
                    # Registra a chamada na história do assistente. Blocos de
                    # thinking vem primeiro (Claude sempre pensa antes de
                    # responder/agir), preservados com a signature para o proximo
                    # turno do loop de tools poder reenviar sem quebrar validacao.
                    assistant_content: list[dict[str, Any]] = []
                    for idx in sorted(thinking_blocks):
                        tb = thinking_blocks[idx]
                        thinking_block: dict[str, Any] = {"type": "thinking", "thinking": tb["thinking"]}
                        if tb["signature"]:
                            thinking_block["signature"] = tb["signature"]
                        assistant_content.append(thinking_block)
                    if final_response:
                        assistant_content.append({"type": "text", "text": final_response})
                    for tc_val in tool_calls_dict.values():
                        try:
                            input_args = json.loads(tc_val["arguments"]) if tc_val["arguments"] else {}
                        except Exception:
                            input_args = {}
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tc_val["id"],
                            "name": tc_val["name"],
                            "input": input_args
                        })
                    messages.append({"role": "assistant", "content": assistant_content})

                    # Executa e gera a resposta de ferramenta (paralelo se houver mais de uma)
                    parsed_calls = []
                    for tc_val in tool_calls_dict.values():
                        try:
                            args = json.loads(tc_val["arguments"]) if tc_val["arguments"] else {}
                        except Exception:
                            args = {}
                        parsed_calls.append((tc_val["id"], tc_val["name"], args))

                    tool_call_results = self._execute_tool_calls(parsed_calls)
                    tool_results = [
                        {"type": "tool_result", "tool_use_id": tool_id, "content": tool_call_results[tool_id]}
                        for tool_id, _name, _args in parsed_calls
                    ]
                    messages.append({"role": "user", "content": tool_results})
                    continue
                else:
                    break
            else:
                resp = self._anthropic_messages_create(
                    client,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_arg,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    messages=messages,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    tools=tools_arg,  # type: ignore[arg-type]  # payload já no shape esperado pela API
                    **kwargs
                )
                _accumulate_usage(usage_total, getattr(resp, "usage", None))
                final_response = "".join(block.text for block in resp.content if block.type == "text")

                tool_uses = [block for block in resp.content if block.type == "tool_use"]
                if tool_uses:
                    messages.append({"role": "assistant", "content": resp.content})
                    parsed_calls = [(tc.id, tc.name, tc.input) for tc in tool_uses]
                    tool_call_results = self._execute_tool_calls(parsed_calls)
                    tool_results = [
                        {"type": "tool_result", "tool_use_id": tool_id, "content": tool_call_results[tool_id]}
                        for tool_id, _name, _args in parsed_calls
                    ]
                    messages.append({"role": "user", "content": tool_results})
                    continue
                else:
                    break

        return {"final_response": final_response, "failed": False, "usage": usage_total}

    def _gemini_interactions_create(self, client: Any, base_kwargs: dict[str, Any], **extra: Any) -> Any:
        """`client.interactions.create` com Structured Outputs (`response_format`,
        ver `self.response_schema`) quando aplicavel -- doc oficial da
        Interactions API. Tenta primeiro com o schema; se o modelo/conta nao
        suportar, cai para `base_kwargs` original sem `response_format`, mesmo
        padrao de fallback usado do lado Anthropic/OpenAI.
        """
        if self.response_schema is None:
            return client.interactions.create(**base_kwargs, **extra)
        try:
            return client.interactions.create(
                **base_kwargs,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": self.response_schema,
                },
                **extra,
            )
        except Exception as exc:
            logger.debug(
                "%s Structured Outputs indisponivel (%s); chamada padrao sem schema.",
                self.log_prefix, exc,
            )
            return client.interactions.create(**base_kwargs, **extra)

    def _run_gemini(self, user_message: str) -> dict[str, Any]:
        from google import genai

        client = genai.Client(api_key=self.api_key)
        # NUNCA adiciona busca nativa (google_search) aqui mesmo com
        # enable_native_web_search=True: doc oficial 2026 do Gemini -- "The
        # Gemini API doesn't support combining search tools like googleSearch
        # with non-search tools in the same generateContent request". Misturar
        # quebraria o tool-calling normal do agente (tavily_search,
        # read_local_project_files, etc.) inteiro, nao so a busca. Ver
        # AIAgent.__init__ pra escopo completo -- _get_response_tools() ja so
        # adiciona o tool nativo pra provider in {"openai", "xai"}.
        tools = [
            {key: value for key, value in tool.items() if key != "strict"}
            for tool in self._get_response_tools()
        ]
        if self.previous_provider_response_id:
            next_input: Any = self._gemini_user_parts(user_message) if self.images else user_message
        else:
            # Long-Horizon: compacta o historico antes de virar transcript. Depois
            # da primeira volta o Gemini fica STATEFUL (previous_interaction_id) e
            # o proprio servidor guarda o contexto, entao nao ha o que compactar.
            compacted = self._compress_history_if_needed(
                [
                    {"role": message["role"], "content": message["content"]}
                    for message in self.prefill_messages
                ]
                + [{"role": "user", "content": user_message}]
            )
            if self.images:
                # Historico anterior (sem o turno atual) vira UM part de texto;
                # o turno atual entra como parts separadas (imagem(ns) + texto),
                # no shape inlineData da API oficial -- ver _gemini_user_parts.
                history_text = "\n".join(
                    f"{message['role']}: {message['content']}" for message in compacted[:-1]
                )
                next_input = (
                    ([{"text": history_text}] if history_text else [])
                    + self._gemini_user_parts(user_message)
                )
            else:
                next_input = "\n".join(
                    f"{message['role']}: {message['content']}" for message in compacted
                )
        previous_interaction_id = self.previous_provider_response_id
        effort = str(self.request_overrides.get("reasoning_effort", "medium"))
        thinking_level = {
            "none": "minimal",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "xhigh": "high",
            "max": "high",
        }.get(effort, "medium")
        generation_config = {
            "max_output_tokens": self.max_tokens,
            "thinking_level": thinking_level,
        }
        usage_total = _empty_usage()

        for _iteration in range(self.max_iterations):
            # Risco conhecido (auditoria 2026-07-26, nao implementado): Gemini 3
            # exige o echo de `thoughtSignature` em partes function_call na
            # proxima chamada (400 se omitido). Aqui usamos `store: True` +
            # `previous_interaction_id`, ou seja, modo STATEFUL -- nesse modo o
            # servidor gerencia os thought blocks/assinaturas automaticamente,
            # entao este client nao precisa (nem deveria) ecoa-los manualmente.
            # O risco so existiria em modo STATELESS/streaming sem
            # previous_interaction_id, que este client nao usa. Documentado em
            # vez de implementado porque o schema exato dos steps `thought` na
            # Interactions API nao foi confirmado o suficiente para um fix as cegas.
            kwargs: dict[str, Any] = {
                "model": self.model,
                "input": next_input,
                "system_instruction": self.ephemeral_system_prompt or "",
                "tools": tools,
                "generation_config": generation_config,
                "store": True,
            }
            if previous_interaction_id:
                kwargs["previous_interaction_id"] = previous_interaction_id

            if self.stream_delta_callback or self.thinking_callback or self.reasoning_callback:
                interaction = None
                for event in self._gemini_interactions_create(client, kwargs, stream=True):
                    event_type = getattr(event, "event_type", "")
                    delta = getattr(event, "delta", None)
                    if event_type == "content.delta":
                        delta_type = str(getattr(delta, "type", "") or "")
                        if delta_type == "text":
                            text = str(getattr(delta, "text", "") or "")
                            if text and self.stream_delta_callback:
                                self.stream_delta_callback(text)
                        elif delta_type in ("thought", "thinking"):
                            thought_text = str(
                                getattr(delta, "thought", "")
                                or getattr(delta, "thinking", "")
                                or getattr(delta, "text", "")
                                or ""
                            )
                            if thought_text:
                                if self.thinking_callback:
                                    self.thinking_callback(thought_text)
                                if self.reasoning_callback:
                                    self.reasoning_callback(thought_text)

                    candidates = getattr(event, "candidates", None) or getattr(delta, "candidates", None)
                    if candidates and isinstance(candidates, (list, tuple)):
                        for cand in candidates:
                            content = getattr(cand, "content", None)
                            parts = getattr(content, "parts", []) if content else []
                            for part in parts:
                                thought_val = getattr(part, "thought", None) or getattr(part, "thinking", None)
                                if thought_val:
                                    t_str = str(thought_val) if isinstance(thought_val, str) else str(getattr(part, "text", "") or "")
                                    if t_str:
                                        if self.thinking_callback:
                                            self.thinking_callback(t_str)
                                        if self.reasoning_callback:
                                            self.reasoning_callback(t_str)
                    if event_type == "interaction.complete":
                        interaction = getattr(event, "interaction", None)
                if interaction is None:
                    return {"failed": True, "error": "Gemini encerrou o stream sem interaction.complete."}
            else:
                interaction = self._gemini_interactions_create(client, kwargs)

            # A Interactions API expõe usage_metadata (*_token_count); aceitamos
            # também `usage` para não depender de uma só versão do SDK.
            _accumulate_usage(
                usage_total,
                _extract_usage(getattr(interaction, "usage_metadata", None))
                or _extract_usage(getattr(interaction, "usage", None)),
            )

            status = str(getattr(interaction, "status", "completed"))
            if status not in {"completed", "requires_action"}:
                return {"failed": True, "error": f"Gemini Interactions terminou com status {status}."}
            # Interactions shipped with `outputs` in google-genai 2.14, while
            # newer documentation/preview responses may expose equivalent
            # `steps`. Accept both native shapes without reconstructing state.
            raw_steps = getattr(interaction, "steps", None)
            steps = list(raw_steps) if isinstance(raw_steps, (list, tuple)) else []
            outputs = list(getattr(interaction, "outputs", []) or []) if not steps else []
            final_response = "".join(
                str(getattr(content_item, "text", "") or "")
                for step in steps
                if getattr(step, "type", "") == "model_output"
                for content_item in (getattr(step, "content", []) or [])
                if getattr(content_item, "type", "") == "text"
            ) or "".join(
                str(getattr(output, "text", "") or "")
                for output in outputs
                if getattr(output, "type", "") == "text"
            )
            calls = [
                step for step in steps
                if getattr(step, "type", "") == "function_call"
            ] or [
                output for output in outputs
                if getattr(output, "type", "") == "function_call"
            ]
            if not calls:
                return {
                    "final_response": final_response,
                    "failed": False,
                    "provider_response_id": str(getattr(interaction, "id", "")),
                    "usage": usage_total,
                }

            previous_interaction_id = str(interaction.id)
            parsed_calls = [
                (str(call.id), str(call.name), dict(getattr(call, "arguments", {}) or {}))
                for call in calls
            ]
            tool_call_results = self._execute_tool_calls(parsed_calls)
            results: list[dict[str, Any]] = [
                {
                    "type": "function_result",
                    "call_id": tool_id,
                    "name": name,
                    "result": [{"type": "text", "text": tool_call_results[tool_id]}],
                }
                for tool_id, name, _args in parsed_calls
            ]
            next_input = results

        return {
            "failed": True,
            "error": "O limite de iterações foi atingido enquanto o Gemini ainda solicitava ferramentas.",
        }
