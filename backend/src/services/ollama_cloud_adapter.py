"""
ollama_cloud_adapter.py
Adaptador agêntico dedicado para o provedor Ollama Cloud (https://ollama.com/api).

Siga os princípios da skill ai-provider-integration:
- Descoberta dinâmica de modelos via GET /api/tags e POST /api/show (zero inventário estático hardcoded).
- Normalização de capacidades (tools, vision, reasoning, janela de contexto).
- Tratamento do comportamento de Structured Outputs no Ollama Cloud (injeção de schema no prompt + validação em Python).
- Zero emojis em logs e mensagens de erro (compatibilidade cp1252 e acessibilidade).
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

OLLAMA_CLOUD_API_URL = "https://ollama.com/api"
OLLAMA_CLOUD_V1_URL = "https://ollama.com/v1"

CACHE_TTL_SECONDS = 300  # Cache de catálogo por 5 minutos


@dataclass
class OllamaCloudModelDescriptor:
    id: str
    provider: str = "ollama-cloud"
    capabilities: list[str] = field(default_factory=list)
    context_window: int = 32768
    reasoning: bool = False
    has_tools: bool = True
    has_vision: bool = False
    # Ollama Cloud currently exposes tool/thinking/vision metadata, but not
    # native JSON Schema Structured Outputs. This is deliberately explicit so
    # the router can delegate schema-constrained work to OpenCode Go/Luna.
    has_structured_outputs: bool = False
    cost_input: float = 0.0
    cost_output: float = 0.0
    release_date: str = "2026-01-01"


_catalog_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "descriptors": [],
}


def _get_api_key(api_key: str | None = None) -> str:
    if api_key:
        return api_key
    return os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY") or ""


def fetch_ollama_cloud_tags(api_key: str | None = None) -> list[dict[str, Any]]:
    """Consulta GET https://ollama.com/api/tags para obter os modelos disponíveis."""
    key = _get_api_key(api_key)
    req = urllib.request.Request(
        f"{OLLAMA_CLOUD_API_URL}/tags",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("models", [])
    except Exception as exc:
        logger.warning("[OllamaCloudAdapter] Falha ao consultar /api/tags: %s", exc)
        return []


def inspect_ollama_cloud_model(model_id: str, api_key: str | None = None) -> dict[str, Any]:
    """Consulta POST https://ollama.com/api/show para obter metadados e capacidades do modelo."""
    key = _get_api_key(api_key)
    payload = json.dumps({"model": model_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_CLOUD_API_URL}/show",
        data=payload,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[OllamaCloudAdapter] Falha ao consultar /api/show para %s: %s", model_id, exc)
        return {}


def discover_ollama_cloud_descriptors(
    api_key: str | None = None, force_refresh: bool = False
) -> list[OllamaCloudModelDescriptor]:
    """Descoberta dinâmica de modelos Ollama Cloud com cache por TTL."""
    now = time.time()
    if not force_refresh and (now - _catalog_cache["timestamp"]) < CACHE_TTL_SECONDS and _catalog_cache["descriptors"]:
        return _catalog_cache["descriptors"]

    models_raw = fetch_ollama_cloud_tags(api_key)
    descriptors: list[OllamaCloudModelDescriptor] = []

    for m in models_raw:
        model_name = m.get("name") or m.get("model")
        if not model_name:
            continue
        # Preview/beta snapshots are intentionally excluded from the product
        # catalog; only stable models and dated stable snapshots remain.
        if "preview" in model_name.lower() or ":beta" in model_name.lower() or "-beta-" in model_name.lower():
            continue
        if model_name.lower().startswith(("kimi-k3", "kimi-3")):
            continue

        details = inspect_ollama_cloud_model(model_name, api_key)
        caps = details.get("capabilities", [])
        if not caps and isinstance(m.get("details"), dict):
            caps = m.get("details", {}).get("capabilities", [])

        # Extração da janela de contexto a partir de model_info ou do parâmetro
        model_info = details.get("model_info", {})
        ctx_len = 32768
        for k, v in model_info.items():
            if k.endswith(".context_length") and isinstance(v, (int, float)):
                ctx_len = int(v)
                break

        # Identificação de suporte a ferramentas, raciocínio e visão por capacidades ou nome
        name_lower = model_name.lower()
        has_tools = "tools" in caps or any(
            w in name_lower for w in ["qwen", "llama", "deepseek", "mistral", "gemma", "gpt-oss"]
        )
        has_vision = "vision" in caps or any(w in name_lower for w in ["vl", "vision"])
        is_reasoning = "thinking" in caps or any(w in name_lower for w in ["deepseek", "think", "r1", "reasoner"])

        descriptors.append(
            OllamaCloudModelDescriptor(
                id=model_name,
                provider="ollama-cloud",
                capabilities=caps,
                context_window=ctx_len,
                reasoning=is_reasoning,
                has_tools=has_tools,
                has_vision=has_vision,
                has_structured_outputs=False,
                release_date="2026-01-01",
            )
        )

    # Fallback gracioso se a API não estiver acessível (ex.: sem chave no ambiente no momento)
    if not descriptors:
        default_models = [
            ("qwen3.5:397b", True, True, 131072),
            ("deepseek-v4-flash:0731", True, True, 65536),
            ("gpt-oss:20b", False, True, 32768),
        ]
        for name, is_think, is_tools, ctx in default_models:
            descriptors.append(
                OllamaCloudModelDescriptor(
                    id=name,
                    provider="ollama-cloud",
                    context_window=ctx,
                    reasoning=is_think,
                    has_tools=is_tools,
                )
            )

    _catalog_cache["timestamp"] = now
    _catalog_cache["descriptors"] = descriptors
    logger.info("[OllamaCloudAdapter] Catálogo descoberto: %d modelos no Ollama Cloud", len(descriptors))
    return descriptors


def score_ollama_cloud_model(
    descriptor: OllamaCloudModelDescriptor,
    *,
    tradeoff: int = 7,
    input_tokens: int = 2000,
    output_tokens: int = 1000,
    needs_tools: bool = True,
    needs_vision: bool = False,
) -> float:
    """Calcula a pontuação de adequação do modelo segundo o algoritmo multi-objetivo da skill 2026.

    Fórmula da skill (references/intelligent-routing.md):
    - Filtro de elegibilidade (ferramentas, visão, janela de contexto).
    - cost_score = 1 / (1 + log1p(cost * 100))
    - score = quality_weight*quality + cost_weight*cost_score + 0.10*latency + 0.05*reliability

    latency/reliability vêm de telemetria REAL observada (model_reliability.py),
    não de constante fixa nem de heurística por substring no nome do modelo.
    Sem amostras suficientes ainda, o shrinkage bayesiano (K=20) mantém o
    score perto do prior neutro -- um modelo novo/pouco testado não é
    penalizado nem favorecido às cegas, só passa a pesar no ranking
    gradualmente conforme o próprio uso real do produto gera sinal sobre ele.
    Padrão de gateway de produção 2026: o roteador aprende sozinho, sem lista
    fixa de "modelo bom".
    """
    import math

    from backend.src.services.model_reliability import get_latency_score, get_reliability_score

    # Filtro rígido de elegibilidade
    total_tokens = input_tokens + output_tokens
    if descriptor.context_window < total_tokens:
        return -1.0
    if needs_tools and not descriptor.has_tools:
        return -1.0
    if needs_vision and not descriptor.has_vision:
        return -1.0

    # Custo estimado em USD
    cost = (input_tokens * descriptor.cost_input + output_tokens * descriptor.cost_output) / 1_000_000
    cost_score = 0.5 if cost == 0.0 else 1.0 / (1.0 + math.log1p(cost * 100))

    # Qualidade: só o reasoning nativo do modelo é usado como sinal (metadado
    # real do catálogo, não opinião curada) -- latência e confiabilidade vêm
    # de comportamento observado de verdade, não de suposição sobre o nome.
    quality = 0.90 if descriptor.reasoning else 0.75
    latency_score = get_latency_score("ollama-cloud", descriptor.id)
    reliability_score = get_reliability_score("ollama-cloud", descriptor.id)

    ratio = max(0, min(10, tradeoff)) / 10.0
    cost_weight = 0.05 + 0.40 * ratio
    quality_weight = 0.80 - 0.40 * ratio

    return quality_weight * quality + cost_weight * cost_score + 0.10 * latency_score + 0.05 * reliability_score


def rank_ollama_cloud_candidates(
    descriptors: list[OllamaCloudModelDescriptor],
    *,
    tradeoff: int = 7,
    needs_tools: bool = True,
    needs_vision: bool = False,
) -> list[OllamaCloudModelDescriptor]:
    """Ordena os modelos elegíveis do Ollama Cloud pelo algoritmo multi-objetivo."""
    scored = [
        (d, score_ollama_cloud_model(d, tradeoff=tradeoff, needs_tools=needs_tools, needs_vision=needs_vision))
        for d in descriptors
    ]
    eligible = [item for item in scored if item[1] >= 0.0]
    eligible.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in eligible]


def adapt_ollama_cloud_request(
    system_prompt: str,
    response_schema: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    """Trata limitação do Ollama Cloud para Structured Outputs.

    O Ollama Cloud aceita mas não força nativamente validação de JSON Schema via parâmetro.
    Injeta instrução explícita de formato no prompt do sistema e permite validação em Python.
    """
    if not response_schema:
        return system_prompt, None

    schema_str = json.dumps(response_schema, indent=2, ensure_ascii=False)
    instruction = (
        "\n\nATENCAO: Voce DEVE responder EXCLUSIVAMENTE em formato JSON valido seguindo rigorosamente a estrutura do JSON Schema abaixo. "
        "Nao inclua nenhum texto introdutorio, nem cercas de markdown (```json). Apenas o JSON estrito.\n"
        f"JSON Schema obrigatorio:\n{schema_str}"
    )
    adapted_prompt = f"{system_prompt}{instruction}"
    # Retorna response_schema None para não falhar caso o proxy estrito da OpenAI rejeite schemas complexos
    return adapted_prompt, None


def clear_ollama_cloud_cache() -> None:
    """Limpa o cache de catálogo do Ollama Cloud."""
    _catalog_cache["timestamp"] = 0.0
    _catalog_cache["descriptors"] = []


def ollama_cloud_web_search(query: str, max_results: int = 5, api_key: str | None = None) -> list[dict[str, Any]]:
    """Executa busca na web nativa do Ollama Cloud (POST https://ollama.com/api/web_search).

    Parâmetros: query (termo de busca), max_results (1-10, padrão 5).
    """
    key = _get_api_key(api_key)
    if not key or not query:
        return []

    clamped_results = max(1, min(10, max_results))
    payload = json.dumps({"query": query, "max_results": clamped_results}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_CLOUD_API_URL}/web_search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])
    except Exception as exc:
        logger.warning("[OllamaCloudAdapter] Falha na busca web /api/web_search para '%s': %s", query, exc)
        return []


def ollama_cloud_web_fetch(url: str, api_key: str | None = None) -> dict[str, Any]:
    """Extrai conteúdo de URL via Ollama Cloud (POST https://ollama.com/api/web_fetch)."""
    key = _get_api_key(api_key)
    if not key or not url:
        return {}

    payload = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_CLOUD_API_URL}/web_fetch",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[OllamaCloudAdapter] Falha ao buscar conteúdo /api/web_fetch para '%s': %s", url, exc)
        return {}
