import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ModelInfo:
    def __init__(
        self,
        id: str,
        name: str,
        reasoning: bool = False,
        tool_call: bool = True,
        context_window: int = 131072,
        cost_input: float = 0.15,
        cost_output: float = 0.6,
        release_date: str = "2026-01-01",
        requires_extra_usage: bool = False,
    ):
        self.id = id
        self.name = name
        self.reasoning = reasoning
        self.tool_call = tool_call
        self.context_window = context_window
        self.cost_input = cost_input
        self.cost_output = cost_output
        self.release_date = release_date
        self.requires_extra_usage = requires_extra_usage


# --------------------------------------------------------------------------- #
# Catálogo dinâmico (live-first, static-fallback) — padrão 2026
# --------------------------------------------------------------------------- #
# Endpoints oficiais de listagem de modelos (confirmados 2026-07-28):
#   OpenAI/xAI/Ollama: GET /v1/models  (OpenAI-compatible)
#   Anthropic:         GET /v1/models  (capabilities granulares)
#   Gemini:            GET /v1beta/models  (token limits, supportedGenerationMethods)
#
# Cache em memória por processo, invalidado por clear_live_cache().
# O catálogo estático _CATALOG permanece como fallback offline.

_LIVE_CACHE: dict[str, dict[str, ModelInfo]] = {}
_LIVE_TTL_SECONDS = 300  # 5 min — evita thrashing sem congelar modelos novos


def _resolve_endpoint(provider: str, base_url: str | None) -> str | None:
    """Devolve o endpoint de listagem de modelos para o provider."""
    p = (provider or "").strip().lower()
    if p == "gemini":
        base = (base_url or os.getenv("GEMINI_BASE_URL") or "").strip()
        return base or "https://generativelanguage.googleapis.com/v1beta/models"
    if p in ("openai", "xai", "ollama-cloud", "ollama"):
        base = (base_url or os.getenv(f"{p.upper().replace('-', '_')}_BASE_URL") or "").strip()
        if p == "openai":
            return base or "https://api.openai.com/v1/models"
        if p == "xai":
            return base or "https://api.x.ai/v1/models"
        if p == "ollama-cloud":
            # Bug real: sem base_url explícito, isto caía pro Ollama LOCAL
            # (localhost:11434) em vez da nuvem -- só a chamada de chat real
            # (run_agent.py) tinha o default correto (https://ollama.com/v1).
            # O catálogo de modelos falhava sempre (WinError 10061), mesmo
            # com a análise em si funcionando normalmente contra a nuvem.
            return base or os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1/models")
        return base or "http://localhost:11434/v1/models"
    if p == "anthropic":
        base = (base_url or os.getenv("ANTHROPIC_BASE_URL") or "").strip()
        return base or "https://api.anthropic.com/v1/models"
    return None


def _resolve_auth_header(provider: str, api_key: str | None) -> dict[str, str]:
    """Devolve os headers de auth para o provider."""
    p = (provider or "").strip().lower()
    key = api_key or os.getenv(f"{p.upper().replace('-', '_')}_API_KEY") or os.getenv(f"{p.upper()}_API_KEY") or ""
    if p == "anthropic":
        headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
        if key:
            headers["x-api-key"] = key
        return headers
    if p == "gemini":
        # Gemini usa query param, não header
        return {"content-type": "application/json"}
    # OpenAI-compatible (openai, xai, ollama)
    headers = {"content-type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


_EXPLICIT_DEPRECATED_MODELS: frozenset[str] = frozenset({
    "o1",
    "o1-preview",
    "o1-mini",
    "o3-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-2024-12-17",
    "gpt-4-0613",
    "gpt-4-0314",
    "gpt-3.5-turbo-0613",
    "kimi-k3",
    "kimi-k3:cloud",
})


def _is_preview_model(model_id: str) -> bool:
    """Preview/beta model IDs are never selectable in the product."""
    normalized = (model_id or "").strip().lower()
    return "preview" in normalized or normalized.endswith(":beta") or "-beta-" in normalized


def _parse_openai_models(data: dict[str, Any]) -> dict[str, ModelInfo]:
    """Parse da resposta GET /v1/models (OpenAI-compatible: {data: [{id, ...}]})."""
    out: dict[str, ModelInfo] = {}
    for item in data.get("data", []):
        mid = item.get("id")
        if not mid or mid in _EXPLICIT_DEPRECATED_MODELS or _is_preview_model(mid):
            continue
        # Descartar snapshots legados/antigos (ex: modelos com -2024-, -2025-)
        if any(f"-202{y}-" in mid for y in ("4", "5")):
            continue
        lower = mid.lower()
        # Descartar rigorosamente modelos pré-2026 (ex: o1*, gpt-4*, gpt-3.5*, gpt-3*)
        if lower.startswith(("o1", "gpt-4", "gpt-3.5", "gpt-3", "o3-mini")):
            continue
        # Descartar modelos com timestamp unix de criação anterior a 2026 (1767225600)
        created = item.get("created")
        if isinstance(created, (int, float)) and created < 1767225600:
            continue

        # Heurística de reasoning por nome (OpenAI não expõe capabilities no /models)
        reasoning = any(w in lower for w in ("reason", "sol", "pro", "opus", "o3"))
        out[mid] = ModelInfo(
            id=mid,
            name=item.get("id", mid),
            reasoning=reasoning,
            tool_call=True,  # OpenAI-compatible assume tool-capable
        )
    return out


def _parse_anthropic_models(data: dict[str, Any]) -> dict[str, ModelInfo]:
    """Parse da resposta GET /v1/models da Anthropic (capabilities granulares)."""
    out: dict[str, ModelInfo] = {}
    for item in data.get("data", []):
        mid = item.get("id")
        if not mid or _is_preview_model(mid):
            continue
        caps = item.get("capabilities", {}) or {}
        reasoning = bool(caps.get("thinking", {}).get("supported", False))
        # structured_outputs indica tool/JSON capability
        tool_capable = bool(caps.get("structured_outputs", {}).get("supported", True))
        max_input = int(item.get("max_input_tokens", 0) or 0)
        out[mid] = ModelInfo(
            id=mid,
            name=item.get("display_name", mid),
            reasoning=reasoning,
            tool_call=tool_capable,
            context_window=max_input or 131072,
            release_date=(item.get("created_at", "2026-01-01") or "2026-01-01")[:10],
        )
    return out


def _parse_gemini_models(data: dict[str, Any]) -> dict[str, ModelInfo]:
    """Parse da resposta GET /v1beta/models do Gemini."""
    out: dict[str, ModelInfo] = {}
    for item in data.get("models", []):
        name = item.get("name", "")
        mid = name.replace("models/", "") if name else ""
        if not mid or _is_preview_model(mid):
            continue
        methods = item.get("supportedGenerationMethods", [])
        tool_capable = "generateContent" in methods
        reasoning = bool(item.get("thinking", False))
        input_limit = int(item.get("inputTokenLimit", 0) or 0)
        out[mid] = ModelInfo(
            id=mid,
            name=item.get("displayName", mid),
            reasoning=reasoning,
            tool_call=tool_capable,
            context_window=input_limit or 131072,
        )
    return out


def fetch_live_models(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 8.0,
) -> dict[str, ModelInfo]:
    """
    Consulta as APIs reais dos providers para obter o catálogo de modelos vivo.

    Padrão 2026 (live-first, static-fallback): chamado por list_agentic_models
    quando há conectividade. Em caso de qualquer falha (rede, auth, parse),
    devolve {} e o chamador cai no catálogo estático _CATALOG.

    Cacheado por processo (_LIVE_CACHE) com TTL de _LIVE_TTL_SECONDS.
    Nunca levanta exceção — falhas são logadas e devolvem {}.
    """

    p = (provider or "").strip().lower()
    if not p:
        return {}

    cached = _LIVE_CACHE.get(p)
    if cached is not None:
        return cached

    endpoint = _resolve_endpoint(p, base_url)
    if not endpoint:
        return {}

    headers = _resolve_auth_header(p, api_key)
    try:
        params: dict[str, Any] | None = None
        if p == "gemini":
            key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
            params = {"key": key} if key else None

        resp = requests.get(endpoint, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        if p == "anthropic":
            parsed = _parse_anthropic_models(data)
        elif p == "gemini":
            parsed = _parse_gemini_models(data)
        else:
            parsed = _parse_openai_models(data)

        _LIVE_CACHE[p] = parsed
        logger.info("[models_dev] catálogo live para %s: %d modelos", p, len(parsed))
        return parsed
    except Exception as exc:
        logger.warning("[models_dev] fetch_live_models(%s) falhou: %s — usando fallback estático", p, exc)
        _LIVE_CACHE[p] = {}  # cacheia o vazio pelo TTL para não retentar a cada chamada
        return {}


def clear_live_cache() -> None:
    """Invalida o cache de catálogo live (chamar quando settings mudam)."""
    _LIVE_CACHE.clear()


def fetch_models_dev() -> None:
    """No-op local — catálogo dinâmico é via fetch_live_models() agora."""
    return None


# Catálogo real e oficial de modelos de 2026 (ou posterior)
_CATALOG: dict[str, dict[str, ModelInfo]] = {
    "openai": {
        "gpt-5.5-pro": ModelInfo("gpt-5.5-pro", "GPT 5.5 Pro", reasoning=True, release_date="2026-04-23"),
        "gpt-5.4": ModelInfo("gpt-5.4", "GPT 5.4", reasoning=False, release_date="2026-03-05"),
        "gpt-5.4-pro": ModelInfo("gpt-5.4-pro", "GPT 5.4 Pro", reasoning=True, release_date="2026-03-05"),
        "gpt-realtime-2.1": ModelInfo("gpt-realtime-2.1", "GPT Realtime 2.1", release_date="2026-07-06"),
        # gpt-5.3-chat-latest removido (auditoria 2026-07-26): deprecated desde
        # 08/mai/2026, desligamento previsto 10/ago/2026 (docs OpenAI
        # deprecations page) -- nao deveria continuar selecionavel no catalogo.
        "gpt-5.3-codex-spark": ModelInfo("gpt-5.3-codex-spark", "GPT 5.3 Codex Spark", release_date="2026-02-05"),
        "gpt-5.4-mini": ModelInfo("gpt-5.4-mini", "GPT 5.4 Mini", release_date="2026-03-17"),
        "gpt-5.6-terra": ModelInfo("gpt-5.6-terra", "GPT 5.6 Terra", reasoning=True, release_date="2026-07-09"),
        "gpt-5.3-codex": ModelInfo("gpt-5.3-codex", "GPT 5.3 Codex", release_date="2026-02-05"),
        "gpt-5.4-nano": ModelInfo("gpt-5.4-nano", "GPT 5.4 Nano", release_date="2026-03-17"),
        "gpt-5.6": ModelInfo("gpt-5.6", "GPT 5.6", reasoning=True, release_date="2026-07-09"),
        "gpt-5.6-luna": ModelInfo("gpt-5.6-luna", "GPT 5.6 Luna", reasoning=True, release_date="2026-07-09"),
        "gpt-5.6-sol": ModelInfo("gpt-5.6-sol", "GPT 5.6 Sol", reasoning=True, release_date="2026-07-09"),
        "gpt-5.5": ModelInfo("gpt-5.5", "GPT 5.5", release_date="2026-04-23"),
    },
    "anthropic": {
        # claude-opus-5: current flagship (GA ~09/jun/2026), supersedes claude-opus-4-8.
        "claude-opus-5": ModelInfo("claude-opus-5", "Claude 5 Opus", reasoning=True, release_date="2026-06-09"),
        "claude-opus-4-8": ModelInfo("claude-opus-4-8", "Claude 4 Opus 4.8", reasoning=True, release_date="2026-05-28"),
        "claude-sonnet-4-6": ModelInfo("claude-sonnet-4-6", "Claude 4 Sonnet 4.6", release_date="2026-02-17"),
        "claude-fable-5": ModelInfo("claude-fable-5", "Claude 5 Fable", reasoning=True, release_date="2026-06-07", requires_extra_usage=True),
        "claude-sonnet-5": ModelInfo("claude-sonnet-5", "Claude 5 Sonnet", release_date="2026-06-29"),
        "claude-opus-4-7": ModelInfo("claude-opus-4-7", "Claude 4 Opus 4.7", reasoning=True, release_date="2026-04-14"),
        "claude-opus-4-6": ModelInfo("claude-opus-4-6", "Claude 4 Opus 4.6", reasoning=True, release_date="2026-02-04"),
        # claude-haiku-4-5: current fast/cheap tier (id claude-haiku-4-5-20251001).
        "claude-haiku-4-5": ModelInfo("claude-haiku-4-5", "Claude 4.5 Haiku", reasoning=True, release_date="2025-10-01"),
    },
    "gemini": {
        "gemini-3.1-flash-lite": ModelInfo("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", release_date="2026-05-07"),
        "gemini-3.5-flash": ModelInfo("gemini-3.5-flash", "Gemini 3.5 Flash", release_date="2026-05-19"),
        "gemini-3.6-flash": ModelInfo("gemini-3.6-flash", "Gemini 3.6 Flash", release_date="2026-07-21"),
        "gemini-3.5-flash-lite": ModelInfo("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", release_date="2026-07-21"),
        "gemini-flash-latest": ModelInfo("gemini-flash-latest", "Gemini Flash Latest", release_date="2026-05-19"),
        "gemini-flash-lite-latest": ModelInfo("gemini-flash-lite-latest", "Gemini Flash Lite Latest", release_date="2026-05-07"),
    },
    "xai": {
        "grok-4.20-0309-reasoning": ModelInfo("grok-4.20-0309-reasoning", "Grok 4.20 Reasoning", reasoning=True, release_date="2026-03-09"),
        "grok-build-0.1": ModelInfo("grok-build-0.1", "Grok Build 0.1", release_date="2026-04-16"),
        "grok-4.3": ModelInfo("grok-4.3", "Grok 4.3", release_date="2026-04-17"),
        "grok-4.20-0309-non-reasoning": ModelInfo("grok-4.20-0309-non-reasoning", "Grok 4.20 Non-Reasoning", release_date="2026-03-09"),
        "grok-4.5": ModelInfo("grok-4.5", "Grok 4.5", reasoning=True, release_date="2026-07-08"),
    },
    "ollama-cloud": {
        # IDs verificados 2026-08-11 CONTRA A CHAMADA REAL da API ao vivo
        # (ollama_cloud_adapter.discover_ollama_cloud_descriptors(), 18 modelos
        # retornados) -- achado real: os IDs anteriores deste catálogo tinham
        # sufixos inventados/desatualizados (":cloud" que a API não usa mais,
        # "deepseek-v4-flash" sem o sufixo de snapshot real) que NUNCA batiam
        # com o ID que a API de fato devolve, então o merge de custo estático
        # em get_model_info() nunca disparava pra esses modelos -- o preço
        # pesquisado ficava morto no código, mascarado como se estivesse ativo.
        #
        # cost_input/cost_output pesquisados em 2026-08-11 direto na fonte
        # ORIGINAL de cada modelo (a Ollama Cloud não publica $/token próprio --
        # cobra por assinatura/GPU-time, ver model_router.py::
        # _SUBSCRIPTION_BASED_PROVIDERS): Moonshot/Kimi, Zhipu/z.ai/GLM,
        # MiniMax, DeepSeek, Alibaba/Qwen, NVIDIA/Nemotron, OpenAI/gpt-oss,
        # Mistral -- é a estimativa mais real disponível pra comparação de
        # custo entre providers, mesmo que a fatura real do usuário na Ollama
        # Cloud seja por assinatura, não por token.
        "nemotron-3-ultra": ModelInfo("nemotron-3-ultra", "Nemotron 3 Ultra", release_date="2026-01-01", cost_input=0.50, cost_output=2.20),
        "kimi-k2.7-code": ModelInfo("kimi-k2.7-code", "Kimi K2.7 Code", release_date="2026-01-01", cost_input=0.95, cost_output=4.00),
        # DeepSeek V4 Flash: API ao vivo devolve dois snapshots, nenhum bare "deepseek-v4-flash".
        "deepseek-v4-flash:0731": ModelInfo("deepseek-v4-flash:0731", "DeepSeek V4 Flash (0731)", release_date="2026-01-01", cost_input=0.14, cost_output=0.28),
        "kimi-k2.6": ModelInfo("kimi-k2.6", "Kimi K2.6", release_date="2026-01-01", cost_input=0.95, cost_output=4.00),
        "deepseek-v4-pro": ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro", reasoning=True, release_date="2026-01-01", cost_input=0.435, cost_output=0.87),
        "qwen3.5:397b": ModelInfo("qwen3.5:397b", "Qwen 3.5 397B", reasoning=True, release_date="2026-01-01", cost_input=0.60, cost_output=3.60),
        "gemma4:31b": ModelInfo("gemma4:31b", "Gemma 4 31B", release_date="2026-01-01", cost_input=0.09, cost_output=0.34),
        "glm-5.2": ModelInfo("glm-5.2", "GLM 5.2", release_date="2026-01-01", cost_input=1.40, cost_output=4.40),
        "nemotron-3-super": ModelInfo("nemotron-3-super", "Nemotron 3 Super", release_date="2026-01-01", cost_input=0.085, cost_output=0.40),
        "nemotron-3-nano:30b": ModelInfo("nemotron-3-nano:30b", "Nemotron 3 Nano 30B", release_date="2026-01-01", cost_input=0.05, cost_output=0.20),
        "gpt-oss:20b": ModelInfo("gpt-oss:20b", "GPT-OSS 20B", release_date="2026-01-01", cost_input=0.030, cost_output=0.130),
        "gpt-oss:120b": ModelInfo("gpt-oss:120b", "GPT-OSS 120B", release_date="2026-01-01", cost_input=0.037, cost_output=0.100),
        "mistral-large-3:675b": ModelInfo("mistral-large-3:675b", "Mistral Large 3 675B", reasoning=True, release_date="2026-01-01", cost_input=0.50, cost_output=1.50),
        # kimi-k2.5 removido (auditoria 2026-07-26): sunsetting per Moonshot's
        # own models page (platform.kimi.ai/docs/models). minimax-m2.5 removido
        # (2026-08-11): não aparece mais nos 18 modelos retornados pela API ao
        # vivo -- provavelmente sunset como o kimi-k2.5, mesma decisão.
        "minimax-m3": ModelInfo("minimax-m3", "MiniMax M3", release_date="2026-01-01", cost_input=0.30, cost_output=1.20),
        "glm-5.1": ModelInfo("glm-5.1", "GLM 5.1", release_date="2026-01-01", cost_input=0.952, cost_output=2.99),
        "minimax-m2.7": ModelInfo("minimax-m2.7", "MiniMax M2.7", release_date="2026-01-01", cost_input=0.24, cost_output=0.96),
    }
}


def list_agentic_models(provider: str) -> list[str]:
    """Lista modelos agenticos do provider, preferindo catálogo live (fallback estático).

    Padrão 2026 (live-first, static-fallback): tenta o catálogo dinâmico primeiro;
    se vazio (offline/sem auth), cai no catálogo estático _CATALOG.
    """
    p = (provider or "").strip().lower()
    live = fetch_live_models(p)
    if live:
        return [mid for mid, info in live.items() if info.tool_call]
    if p not in _CATALOG:
        return []
    return list(_CATALOG[p].keys())

def get_model_info(provider: str, model_id: str) -> ModelInfo | None:
    """Devolve info do modelo, preferindo catálogo live (fallback estático).

    Mescla metadados estáticos conhecidos (ex.: `requires_extra_usage`, `context_window`,
    `cost_input`/`cost_output`) sobre o modelo live para garantir que flags de billing e
    capacidade sejam respeitadas.

    Achado real (2026-08-11): o endpoint /v1/models da própria Ollama Cloud não devolve
    preço por token (ela cobra por assinatura/GPU-time, não por chamada -- ver
    model_router.py::_SUBSCRIPTION_BASED_PROVIDERS) -- sem este merge, um
    cost_input/cost_output pesquisado manualmente no catálogo estático (preço real do
    laboratório original de cada modelo hospedado) era sobrescrito silenciosamente pelo
    default genérico de ModelInfo sempre que o catálogo live estava disponível, mascarando
    dado pesquisado como se fosse placeholder.
    """
    p = (provider or "").strip().lower()
    m = (model_id or "").strip()
    live = fetch_live_models(p)
    info = live.get(m) if live else None
    if info is None and p in _CATALOG and m in _CATALOG[p]:
        info = _CATALOG[p][m]
    elif info and p in _CATALOG and m in _CATALOG[p]:
        static_info = _CATALOG[p][m]
        if getattr(static_info, "requires_extra_usage", False):
            info.requires_extra_usage = True
        if getattr(static_info, "reasoning", False):
            info.reasoning = True
        if getattr(static_info, "context_window", 0) > getattr(info, "context_window", 0):
            info.context_window = static_info.context_window
        static_cost_input = getattr(static_info, "cost_input", 0.0) or 0.0
        static_cost_output = getattr(static_info, "cost_output", 0.0) or 0.0
        if static_cost_input or static_cost_output:
            info.cost_input = static_cost_input
            info.cost_output = static_cost_output
    return info
