"""Resolucao do modelo "Alto" (selecao automatica do melhor modelo do provider).

Também inclui roteamento para modelos de código (tier="code") quando o agente
está gerando código (ex.: fixer de HTML/CSS/JS), preferindo modelos especializados
em coding do catálogo (Codex, Code, Kimi Code, etc.).

"Alto" e a opcao padrão por provider: o usuário so escolhe o provider e a chave
de API, e o sistema roteia para o melhor modelo RECENTE e COM SUPORTE A
FERRAMENTAS daquele provider. Nada de lista fixa que envelhece — a escolha vem
do catalogo local (`agent.models_dev`), o mesmo usado pela rota
`/models`, filtrando so modelos agenticos (tool_call=True) e rankeando por
capacidade (reasoning, depois janela de contexto, depois custo como desempate).

Resolucao no servidor (não por mensagem): "Alto" -> modelo flagship recente do
provider. Roteamento por-tarefa pode evoluir depois sem mudar este contrato.
"""

import logging
from functools import lru_cache
from typing import Any

from agent.models_dev import get_model_info, list_agentic_models

logger = logging.getLogger(__name__)

# Sentinela armazenado em LLM_MODEL quando o usuário deixa em "Alto".
ALTO_MODEL = "alto"

# Ordem de prioridade historica -- usada como desempate quando o preço não
# decide (tradeoff baixo, ou custos empatados), não mais como unico criterio.
_AUTO_PROVIDER_PRIORITY = ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]

# OpenCode Go expõe uma cadeia de modelos verificados para Structured Outputs
# garantidos (ver docs/auditoria-prompt-caching-structured-output-2026-08-26.md):
# todos os 5 seguem json_schema estrito de verdade; os 4 seguintes tambem
# confirmam prompt caching real no mesmo teste. gpt-5.6-luna primeiro (Responses
# API, 99,9% de cache observado); os demais via Chat Completions padrao (ver
# run_agent.py::run_conversation, que roteia por modelo, nao so por provider).
# É um fallback opt-in: só entra no roteamento quando o usuário configurou a
# chave correspondente, evitando chamadas inesperadas ou envio de dados para
# um provedor não habilitado.
OPENCODE_GO_PROVIDER = "opencode-go"
STRUCTURED_OUTPUT_MODEL_CHAIN = ["gpt-5.6-luna", "kimi-k2.6", "glm-5.1", "deepseek-v4-flash", "qwen3.8-max"]
OPENCODE_GO_MODEL = STRUCTURED_OUTPUT_MODEL_CHAIN[0]
OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"


def resolve_structured_output_chain() -> list[str]:
    """Cadeia de modelos verificados para Structured Outputs via OpenCode Go,
    em ordem de preferência. Vazia quando o fallback não está configurado
    (sem OPENCODE_GO_API_KEY/OPENCODE_API_KEY no ambiente).

    Usada por llm_client.call_llm para tentar o próximo modelo verificado
    automaticamente se o primeiro estiver fora do ar -- nunca fica sem
    garantia de JSON só porque um único modelo da cadeia falhou."""
    if not _opencode_go_enabled():
        return []
    return list(STRUCTURED_OUTPUT_MODEL_CHAIN)


def _opencode_go_enabled() -> bool:
    import os

    return bool(os.getenv("OPENCODE_GO_API_KEY") or os.getenv("OPENCODE_API_KEY"))


def is_alto(model: str | None) -> bool:
    """True quando o modelo selecionado e o "Alto" (ou vazio = comportamento Alto)."""
    return not model or model.strip().lower() == ALTO_MODEL


@lru_cache(maxsize=128)
def resolve_alto_model(
    provider: str, allow_extra_usage: bool = False, needs_vision: bool = False, tradeoff: int = 3
) -> str:
    """Melhor modelo agentico recente do provider, do catalogo models.dev.

    Rankeia os modelos tool-capable do provider por (reasoning, janela de
    contexto, menor custo). Modelos com `requires_extra_usage=True` (que exigem
    créditos extras em planos pagos) sao ignorados a menos que `allow_extra_usage=True`.

    `needs_vision=True`: restringe a modelos com suporte a imagem (usado pelo
    visual_a11y). Achado real: sem isso, "Alto" podia resolver para um modelo
    sem visão mesmo quando o pipeline decidiu rodar analise visual, causando
    HTTP 400 "this model does not support image input" com mensagem de erro
    generica pro usuario -- a filtragem ja existe em rank_ollama_cloud_candidates,
    so nao era usada aqui.

    `tradeoff` (0-10, default 3 = favorece qualidade): decidido pelo modelo em
    `complexity_router.classify_and_set_tradeoff`, nunca fixo por hardcode nem
    por heurística de tamanho -- a IA lê o conteúdo real e decide se a tarefa
    pede reasoning de ponta ou se um modelo mais barato/rápido já resolve.

    Cacheado por processo; `clear_cache()` invalida apos troca de settings.
    """
    if not provider:
        return ""

    if provider.lower() in ("agentic", "auto"):
        import os
        for p in ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]:
            env_var = f"{p.upper().replace('-', '_')}_API_KEY"
            if os.getenv(env_var) or os.getenv(f"{p.upper()}_API_KEY"):
                res = resolve_alto_model(p, allow_extra_usage, needs_vision, tradeoff)
                if res:
                    return res
        for p in ["openai", "anthropic", "gemini", "xai"]:
            res = resolve_alto_model(p, allow_extra_usage, needs_vision, tradeoff)
            if res:
                return res
        return ""

    if provider.lower() in ("ollama-cloud", "ollama_cloud"):
        from backend.src.services.ollama_cloud_adapter import (
            discover_ollama_cloud_descriptors,
            rank_ollama_cloud_candidates,
        )
        descriptors = discover_ollama_cloud_descriptors()
        ranked = rank_ollama_cloud_candidates(descriptors, tradeoff=tradeoff, needs_tools=True, needs_vision=needs_vision)
        if ranked:
            best = ranked[0].id
            logger.info(
                "[Alto] provider=ollama-cloud -> %s (ranking multi-objetivo agêntico entre %d candidatos, needs_vision=%s, tradeoff=%d)",
                best, len(ranked), needs_vision, tradeoff,
            )
            return best
        if needs_vision:
            logger.warning("[Alto] provider=ollama-cloud -- nenhum modelo com suporte a visao disponivel no catalogo")
            return ""

    try:
        candidates = list_agentic_models(provider)
        filtered = []
        for m in candidates:
            try:
                info = get_model_info(provider, m)
                if info and getattr(info, "release_date", "") >= "2026-01-01":
                    if not allow_extra_usage and getattr(info, "requires_extra_usage", False):
                        continue
                    filtered.append(m)
            except Exception as exc:
                logger.debug("[Alto] get_model_info(%s, %s) falhou: %s", provider, m, exc)
        candidates = filtered
    except Exception as exc:  # pragma: no cover - defensivo (rede/catalogo)
        logger.warning("[Alto] list_agentic_models(%s) falhou: %s", provider, exc)
        return ""

    if not candidates:
        return ""

    def _rank(model_id: str) -> tuple[int, int, float]:
        info = None
        try:
            info = get_model_info(provider, model_id)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.debug("[Alto] get_model_info(%s, %s) falhou no ranking: %s", provider, model_id, exc)
            info = None
        if info is None:
            return (0, 0, 0.0)
        reasoning = 1 if getattr(info, "reasoning", False) else 0
        context = int(getattr(info, "context_window", 0) or 0)
        # Custo entra NEGATIVO: entre modelos igualmente capazes, prefere o mais
        # barato (max() escolhe o maior, entao -custo favorece o menor custo).
        cost = float(getattr(info, "cost_input", 0.0) or 0.0) + float(
            getattr(info, "cost_output", 0.0) or 0.0
        )
        return (reasoning, context, -cost)

    best = max(candidates, key=_rank)
    logger.info("[Alto] provider=%s -> %s (entre %d agenticos)", provider, best, len(candidates))
    return best


@lru_cache(maxsize=64)
def resolve_fast_model(provider: str, allow_extra_usage: bool = False) -> str:
    """Resolve o melhor modelo rapido e barato (Flash/Lite/Mini) do provedor.

    Ordena pelo menor custo combinado. Se empatar ou não houver dados de custo,
    usa heuristica de nome (nano, flash, lite, mini, small, 3b, 8b) e desempata
    com a janela de contexto.
    """
    if not provider:
        return ""

    if provider.lower() in ("agentic", "auto"):
        import os
        for p in ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]:
            env_var = f"{p.upper().replace('-', '_')}_API_KEY"
            if os.getenv(env_var) or os.getenv(f"{p.upper()}_API_KEY"):
                res = resolve_fast_model(p, allow_extra_usage)
                if res:
                    return res
        for p in ["gemini", "openai", "anthropic", "xai"]:
            res = resolve_fast_model(p, allow_extra_usage)
            if res:
                return res
        return ""

    if provider.lower() in ("ollama-cloud", "ollama_cloud"):
        from backend.src.services.ollama_cloud_adapter import (
            discover_ollama_cloud_descriptors,
            rank_ollama_cloud_candidates,
        )
        descriptors = discover_ollama_cloud_descriptors()
        ranked = rank_ollama_cloud_candidates(descriptors, tradeoff=9, needs_tools=False)  # tradeoff=9: foco em velocidade/custo (Fast)
        if ranked:
            best = ranked[0].id
            logger.info("[Fast] provider=ollama-cloud -> %s (ranking multi-objetivo agêntico)", best)
            return best

    try:
        candidates = list_agentic_models(provider)
        filtered = []
        for m in candidates:
            try:
                info = get_model_info(provider, m)
                if info and getattr(info, "release_date", "") >= "2026-01-01":
                    if not allow_extra_usage and getattr(info, "requires_extra_usage", False):
                        continue
                    filtered.append(m)
            except Exception as exc:
                logger.debug("[Fast] get_model_info(%s, %s) falhou: %s", provider, m, exc)
        candidates = filtered
    except Exception as exc:  # pragma: no cover
        logger.warning("[Fast] list_agentic_models(%s) falhou: %s", provider, exc)
        return ""

    if not candidates:
        return ""

    def _rank(model_id: str) -> tuple[float, int, int]:
        info = None
        try:
            info = get_model_info(provider, model_id)
        except Exception:  # pragma: no cover
            info = None

        lower_id = model_id.lower()
        is_fast_name = 1 if any(w in lower_id for w in ["nano", "flash", "lite", "mini", "small", "3b", "8b", "haiku"]) else 0

        if info is None:
            return (0.0, is_fast_name, 0)

        cost_input = float(getattr(info, "cost_input", 0.0) or 0.0)
        cost_output = float(getattr(info, "cost_output", 0.0) or 0.0)
        cost = cost_input + cost_output
        context = int(getattr(info, "context_window", 0) or 0)

        if cost == 0.0:
            cost = 0.0001 if is_fast_name else 99.0

        return (-cost, is_fast_name, context)

    best = max(candidates, key=_rank)
    logger.info("[Fast] provider=%s -> %s (entre %d candidatos)", provider, best, len(candidates))
    return best


@lru_cache(maxsize=64)
def resolve_code_model(
    provider: str,
    allow_extra_usage: bool = False,
    needs_vision: bool = False,
    tradeoff: int = 3,
) -> str:
    """Resolve o melhor modelo especializado em codigo do provedor.

    Filtra modelos agenticos cujo id ou nome sugira foco em codigo
    (codex, code, coder). Se nenhum candidato existir, fallback para o
    modelo "Alto" padrao, mantendo o roteamento provider-agnostico.
    """
    if not provider:
        return ""

    if provider.lower() in ("agentic", "auto"):
        import os
        for p in ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]:
            env_var = f"{p.upper().replace('-', '_')}_API_KEY"
            if os.getenv(env_var) or os.getenv(f"{p.upper()}_API_KEY"):
                res = resolve_code_model(p, allow_extra_usage, needs_vision, tradeoff)
                if res:
                    return res
        for p in ["openai", "anthropic", "gemini", "xai"]:
            res = resolve_code_model(p, allow_extra_usage, needs_vision, tradeoff)
            if res:
                return res
        return ""

    if provider.lower() in ("ollama-cloud", "ollama_cloud"):
        from backend.src.services.ollama_cloud_adapter import (
            discover_ollama_cloud_descriptors,
            rank_ollama_cloud_candidates,
        )
        descriptors = discover_ollama_cloud_descriptors()
        ranked = rank_ollama_cloud_candidates(descriptors, tradeoff=tradeoff, needs_tools=True, needs_vision=needs_vision)
        # Preferencia por nomes que evidenciam modelo de codigo
        code_pref = [d for d in ranked if any(w in d.id.lower() for w in ("code", "codex", "coder"))]
        if code_pref:
            best = code_pref[0].id
            logger.info(
                "[Code] provider=ollama-cloud -> %s (ranking com preferencia por codigo, needs_vision=%s, tradeoff=%d)",
                best, needs_vision, tradeoff,
            )
            return best
        if ranked:
            best = ranked[0].id
            logger.info(
                "[Code] provider=ollama-cloud -> %s (fallback alto, nenhum modelo de codigo identificado, needs_vision=%s, tradeoff=%d)",
                best, needs_vision, tradeoff,
            )
            return best
        if needs_vision:
            logger.warning("[Code] provider=ollama-cloud -- nenhum modelo com suporte a visao disponivel no catalogo")
        return ""

    try:
        candidates = list_agentic_models(provider)
        filtered = []
        for m in candidates:
            try:
                info = get_model_info(provider, m)
                if info and getattr(info, "release_date", "") >= "2026-01-01":
                    if not allow_extra_usage and getattr(info, "requires_extra_usage", False):
                        continue
                    lower_id = m.lower()
                    lower_name = str(getattr(info, "name", "") or "").lower()
                    if any(w in lower_id or w in lower_name for w in ("codex", "code", "coder")):
                        filtered.append(m)
            except Exception as exc:
                logger.debug("[Code] get_model_info(%s, %s) falhou: %s", provider, m, exc)
        candidates = filtered
    except Exception as exc:  # pragma: no cover - defensivo (rede/catalogo)
        logger.warning("[Code] list_agentic_models(%s) falhou: %s", provider, exc)
        return ""

    if not candidates:
        logger.info(
            "[Code] provider=%s -> nenhum modelo de codigo identificado; fallback para alto", provider
        )
        return resolve_alto_model(provider, allow_extra_usage, needs_vision, tradeoff)

    def _rank(model_id: str) -> tuple[int, int, float]:
        info = None
        try:
            info = get_model_info(provider, model_id)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.debug("[Code] get_model_info(%s, %s) falhou no ranking: %s", provider, model_id, exc)
            info = None
        if info is None:
            return (0, 0, 0.0)
        reasoning = 1 if getattr(info, "reasoning", False) else 0
        context = int(getattr(info, "context_window", 0) or 0)
        cost = float(getattr(info, "cost_input", 0.0) or 0.0) + float(
            getattr(info, "cost_output", 0.0) or 0.0
        )
        return (reasoning, context, -cost)

    best = max(candidates, key=_rank)
    logger.info(
        "[Code] provider=%s -> %s (entre %d modelos de codigo)", provider, best, len(candidates)
    )
    return best


def _available_auto_providers() -> list[str]:
    """Providers com API key presente no ambiente, na ordem de prioridade
    histórica (usada só como desempate quando o preço não decide sozinho)."""
    import os
    available = []
    for p in _AUTO_PROVIDER_PRIORITY:
        env_var = f"{p.upper().replace('-', '_')}_API_KEY"
        if os.getenv(env_var) or os.getenv(f"{p.upper()}_API_KEY"):
            available.append(p)
    return available


def _blended_cost(info: Any) -> float:
    """Custo estimado por chamada, ponderado 4:1 a favor do input. O pipeline
    de acessibilidade manda HTML inteiro como entrada e recebe JSON curto como
    saída -- tokens de entrada dominam o volume real de cada chamada, então
    cost_input + cost_output puro (peso igual) subestimaria o impacto real do
    provider mais caro em input para este caso de uso."""
    cost_input = float(getattr(info, "cost_input", 0.0) or 0.0)
    cost_output = float(getattr(info, "cost_output", 0.0) or 0.0)
    return (cost_input * 4 + cost_output) / 5


# Provider genuinamente sem preço por token pra pesquisar: Ollama LOCAL roda
# o peso do modelo na própria máquina do usuário -- não há laboratório
# terceiro cobrando por chamada, custo real é hardware/eletricidade já
# pago, não $/token. Tratado como custo marginal ~$0 nas comparações.
#
# "ollama-cloud" NÃO está mais aqui (pesquisado 2026-08-11): apesar da
# própria Ollama cobrar por assinatura/GPU-time (não $/token -- ver
# ollama.com/pricing), os modelos que ela hospeda são pesos de laboratórios
# terceiros (Moonshot/Kimi, Zhipu/GLM, MiniMax, DeepSeek, Alibaba/Qwen) que
# TÊM preço oficial publicado por token -- usado no catálogo
# (agent/models_dev.py) como a estimativa mais real disponível pra comparar
# custo entre providers, em vez de tratar como placeholder ou como grátis.
_SUBSCRIPTION_BASED_PROVIDERS = {"ollama"}


def _resolve_agentic_auto(
    tier: str,
    agent_label: str,
    allow_extra_usage: bool,
    needs_vision: bool,
    tradeoff: int,
) -> tuple[str, str]:
    """Roteamento de CUSTO REAL entre providers -- não só entre modelos de um
    provider já escolhido. Pesquisa de mercado 2026 (padrão RouteLLM e afins:
    rotear só a fração de tarefas que realmente precisa do modelo caro mantém
    a maior parte da qualidade com economia substancial) confirma que
    comparar preço entre providers, e não apenas a ordem fixa de qual API key
    está presente no ambiente, é o padrão -- ver Task #19 /
    AI_MODULE_SPEC.md § Pendências de arquitetura (item 2, agora resolvido).

    Em `tradeoff` baixo (favorece qualidade, default histórico=3): mantém o
    comportamento antigo -- primeiro provider disponível na ordem de
    prioridade, preço não decide. Em `tradeoff` alto (favorece custo): compara
    o custo estimado (`_blended_cost`) entre TODOS os candidatos com API key
    disponível e escolhe o mais barato capaz de fazer a tarefa (tool-call,
    visão se necessário) -- a partir de tradeoff>=8 ignora até a preferência
    por `reasoning=True`, indo direto no mais barato entre todos.
    """
    available = _available_auto_providers()
    label_lower = (agent_label or "").lower().strip()
    is_fast = tier == "fast" or label_lower == "classifier"
    is_code = tier == "code" or label_lower in ("fixer", "coder")

    if not available:
        # Sem nenhuma API key detectada: mantém o comportamento histórico de
        # "tenta todo mundo" -- pode falhar rio abaixo por falta de
        # credencial, mas não há preço a comparar sem nenhum candidato.
        for p in ["openai", "anthropic", "gemini", "xai"]:
            if is_code:
                model = resolve_code_model(p, allow_extra_usage, needs_vision, tradeoff)
            elif is_fast:
                model = resolve_fast_model(p, allow_extra_usage)
            else:
                model = resolve_alto_model(p, allow_extra_usage, needs_vision, tradeoff)
            if model:
                return p, model
        return "", ""

    candidates: list[dict[str, Any]] = []
    for p in available:
        if is_code:
            model = resolve_code_model(p, allow_extra_usage, needs_vision, tradeoff)
        elif is_fast:
            model = resolve_fast_model(p, allow_extra_usage)
        else:
            model = resolve_alto_model(p, allow_extra_usage, needs_vision, tradeoff)
        if not model:
            continue
        try:
            info = get_model_info(p, model)
        except Exception:
            info = None
        # Sem $/token real publicado pra providers de assinatura (ver nota em
        # _SUBSCRIPTION_BASED_PROVIDERS) -- custo marginal por chamada tratado
        # como ~$0, não a placeholder genérica do catálogo.
        cost = 0.0 if p in _SUBSCRIPTION_BASED_PROVIDERS else (_blended_cost(info) if info else None)
        candidates.append({
            "provider": p,
            "model": model,
            "cost": cost,
            "reasoning": bool(info and getattr(info, "reasoning", False)),
        })

    if not candidates:
        return "", ""

    priority_order = {p: i for i, p in enumerate(available)}
    # Tier "fast"/classifier já favorece custo por design (mesmo tradeoff=9
    # usado dentro de resolve_fast_model/rank_ollama_cloud_candidates) --
    # aplica o mesmo aqui pra escolher entre providers, não só entre modelos.
    effective_tradeoff = 9 if is_fast else tradeoff

    if effective_tradeoff <= 3:
        pool = candidates
    else:
        reasoning_pool = [c for c in candidates if c["reasoning"]]
        pool = reasoning_pool if (reasoning_pool and effective_tradeoff < 8) else candidates

    def _sort_key(c: dict[str, Any]) -> tuple[float, int]:
        if effective_tradeoff <= 3:
            # Qualidade primeiro: preço não decide, só a ordem de prioridade.
            return (priority_order.get(c["provider"], 99), 0)
        cost = c["cost"] if c["cost"] is not None else float("inf")
        return (cost, priority_order.get(c["provider"], 99))

    chosen = min(pool, key=_sort_key)
    logger.info(
        "[Alto] provider=agentic/auto -> %s/%s (roteamento de custo entre %d provider(s) disponíveis %s, tradeoff=%d)",
        chosen["provider"], chosen["model"], len(candidates),
        [c["provider"] for c in candidates], effective_tradeoff,
    )
    return chosen["provider"], chosen["model"]


def resolve_provider(provider: str) -> str:
    """Resolve o provider concreto quando o usuário usa o provider logico 'agentic' ou 'auto'.

    Verifica as variaveis de ambiente na ordem (openai -> anthropic -> gemini -> xai -> ollama-cloud -> ollama).
    Devolve o primeiro provider que tiver chave de API (ou ollama local).
    Se o provider ja for concreto (ex.: 'openai'), devolve verbatim.
    """
    p = (provider or "").strip().lower()
    if p in ("agentic", "auto", ""):
        import os

        for candidate in ["openai", "anthropic", "gemini", "xai", "ollama-cloud", "ollama"]:
            env_var = f"{candidate.upper().replace('-', '_')}_API_KEY"
            if os.getenv(env_var) or os.getenv(f"{candidate.upper()}_API_KEY") or candidate == "ollama":
                return candidate
        return "openai"
    return p


def resolve_model(
    provider: str,
    model: str | None,
    tier: str = "alto",
    agent_label: str = "",
    allow_extra_usage: bool = False,
    needs_vision: bool = False,
    tradeoff: int | None = None,
) -> str:
    """
    Resolve o modelo efetivo:
    1. Se o usuário digitou um modelo concreto, respeita verbatim (mesmo com extra usage).
    2. Se estiver em modo "Alto" (automatico), usa o catalogo local atual:
       - classifier/tier fast -> modelo rapido e barato do provider.
       - demais agentes -> melhor modelo agentico recente do provider, pontuado
         pelo `tradeoff` custo/qualidade decidido pelo classificador de
         complexidade (ver complexity_router.py) -- nunca um valor fixo.

    Mantem o roteamento provider-agnostico para não envelhecer com nomes fixos
    de modelos. O catalogo `models.dev` e a fonte de verdade.

    `needs_vision=True` restringe a "Alto" a modelos com suporte a imagem
    (ver resolve_alto_model) -- usado quando o prompt e multimodal.

    `tradeoff=None` (default): lê o valor corrente de
    `complexity_router.get_current_tradeoff()` -- classificado pelo modelo a
    partir do conteúdo real sendo analisado, uma vez por pipeline. Passar um
    inteiro explícito sobrepõe isso (usado pelo tier "fast", que é sempre
    barato por design, independente da complexidade da tarefa).
    """
    concrete_provider = resolve_provider(provider)
    if not is_alto(model):
        return model or ""

    label_lower = (agent_label or "").lower().strip()

    if tier == "code" or label_lower in ("fixer", "coder"):
        return resolve_code_model(concrete_provider, allow_extra_usage, needs_vision, tradeoff or 3) or resolve_alto_model(
            concrete_provider, allow_extra_usage, needs_vision, tradeoff or 3
        )

    if tier == "fast" or label_lower == "classifier":
        return resolve_fast_model(concrete_provider, allow_extra_usage) or resolve_alto_model(
            concrete_provider, allow_extra_usage, needs_vision, 9
        )

    if tradeoff is None:
        from backend.src.services.complexity_router import get_current_tradeoff
        tradeoff = get_current_tradeoff()
    return resolve_alto_model(concrete_provider, allow_extra_usage, needs_vision, tradeoff)


def resolve_model_and_provider(
    provider: str,
    model: str | None,
    tier: str = "alto",
    agent_label: str = "",
    allow_extra_usage: bool = False,
    needs_vision: bool = False,
    needs_structured_outputs: bool = False,
    tradeoff: int | None = None,
) -> tuple[str, str]:
    """Resolve o par (provider_concreto, modelo_efetivo) garantindo suporte total a 'agentic' e 'auto'.

    Quando o provider lógico é 'agentic'/'auto' E o modelo está em modo "Alto"
    (automático), o provider concreto TAMBÉM é escolhido por roteamento de
    custo real entre os providers com API key disponível (ver
    `_resolve_agentic_auto`) -- não mais só pela ordem fixa de qual chave está
    presente no ambiente. Quando o usuário digitou um modelo concreto (não
    "Alto"), mantém o comportamento antigo: só precisa saber qual provider
    tem esse modelo, não há preço a comparar entre alternativas."""
    p = (provider or "").strip().lower()
    if p in ("agentic", "auto", "") and is_alto(model):
        eff_tradeoff = tradeoff
        if eff_tradeoff is None:
            from backend.src.services.complexity_router import get_current_tradeoff
            eff_tradeoff = get_current_tradeoff()
        return _resolve_agentic_auto(tier, agent_label, allow_extra_usage, needs_vision, eff_tradeoff)

    concrete_provider = resolve_provider(provider)

    # Ollama Cloud documenta que não oferece Structured Outputs nativos. Para
    # contratos JSON/schema, não fazemos downgrade para prompt injection +
    # parsing: roteamos para o endpoint Responses do OpenCode Go, que publica
    # GPT 5.6 Luna. Ollama local permanece no caminho nativo, pois suporta
    # `format`/structured outputs localmente.
    if (
        concrete_provider in ("ollama-cloud", "ollama_cloud")
        and needs_structured_outputs
        and _opencode_go_enabled()
    ):
        logger.info(
            "[ModelRouter] Structured Outputs indisponível no Ollama Cloud; "
            "roteando para %s/%s",
            OPENCODE_GO_PROVIDER,
            OPENCODE_GO_MODEL,
        )
        return OPENCODE_GO_PROVIDER, OPENCODE_GO_MODEL

    resolved_model = resolve_model(
        concrete_provider,
        model,
        tier=tier,
        agent_label=agent_label,
        allow_extra_usage=allow_extra_usage,
        needs_vision=needs_vision,
        tradeoff=tradeoff,
    )
    # Ollama Cloud pode expor um catálogo sem um modelo elegível para a
    # capacidade pedida (tools/vision/context). Nesse caso, use o fallback Go
    # somente se explicitamente configurado; devolver apenas o nome Luna com
    # provider=ollama-cloud faria a chamada ir para o endpoint errado.
    if (
        concrete_provider in ("ollama-cloud", "ollama_cloud")
        and is_alto(model)
        and not resolved_model
        and _opencode_go_enabled()
    ):
        logger.warning(
            "[ModelRouter] Ollama Cloud sem modelo elegível; usando %s/%s",
            OPENCODE_GO_PROVIDER,
            OPENCODE_GO_MODEL,
        )
        return OPENCODE_GO_PROVIDER, OPENCODE_GO_MODEL
    return concrete_provider, resolved_model


def clear_cache() -> None:
    """Limpa o cache de resolucao (chamar quando settings mudam)."""
    resolve_alto_model.cache_clear()
    resolve_fast_model.cache_clear()
    resolve_code_model.cache_clear()
    try:
        from backend.src.services.ollama_cloud_adapter import clear_ollama_cloud_cache
        clear_ollama_cloud_cache()
    except Exception as exc:
        logger.debug("[ModelRouter] clear_ollama_cloud_cache falhou: %s", exc)
    # Limpa também o cache de catálogo live (models_dev) para que a próxima
    # resolução pegue modelos novos após troca de provider/chave.
    try:
        from agent.models_dev import clear_live_cache

        clear_live_cache()
    except Exception as exc:  # pragma: no cover - defensivo
        logger.debug("[ModelRouter] clear_live_cache falhou: %s", exc)
