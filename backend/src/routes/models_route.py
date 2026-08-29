import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])

# Providers suportados (todos tool-capable). Labels para a UI.
# "agentic" é um provider LÓGICO (não conecta a um endpoint próprio): resolve
# para o primeiro provider concreto com API key configurada, em cascata —
# ver model_router.resolve_alto_model/resolve_fast_model. Vem primeiro para
# ser a opção recomendada/default na UI. A ordem é a fonte de verdade que a
# UI espelha (SettingsScreen.tsx).
CHAT_PROVIDERS: list[tuple[str, str]] = [
    ("agentic", "Agentic Auto (Seleção Inteligente)"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("gemini", "Google Gemini"),
    ("xai", "xAI Grok"),
    ("ollama-cloud", "Ollama Cloud"),
]


@router.get("")
async def list_models() -> dict:
    """
    Lista os providers de chat e o catálogo local revisado de modelos agênticos.
    A disponibilidade real ainda precisa ser confirmada na conta do usuário.
    """
    from agent.models_dev import fetch_models_dev, list_agentic_models

    try:
        fetch_models_dev()  # garante o catalogo em cache (rede na 1a vez)
    except Exception as exc:  # pragma: no cover - rede indisponivel
        logger.warning("[Models] fetch_models_dev falhou (usando cache se houver): %s", exc)

    providers = []
    for provider_id, label in CHAT_PROVIDERS:
        descriptors = []
        try:
            if provider_id in ("ollama-cloud", "ollama_cloud"):
                try:
                    from backend.src.services.ollama_cloud_adapter import discover_ollama_cloud_descriptors

                    descriptors = discover_ollama_cloud_descriptors()
                    models = [d.id for d in descriptors]
                except Exception:
                    models = []
            else:
                from agent.models_dev import get_model_info, list_agentic_models

                models = list_agentic_models(provider_id)
                filtered = []
                for m in models:
                    try:
                        info = get_model_info(provider_id, m)
                        if info and getattr(info, "release_date", "") >= "2026-01-01":
                            filtered.append(m)
                    except Exception as exc:
                        logger.debug("[Models] get_model_info(%s, %s) falhou: %s", provider_id, m, exc)
                models = filtered
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning("[Models] listagem de modelos para (%s) falhou: %s", provider_id, exc)
            models = []
        # "alto" e a opcao padrão/recomendada: roteia para o melhor modelo
        # agentico recente do provider (resolvido no servidor). Vem sempre
        # primeiro; os modelos concretos seguem como override manual.
        model_capabilities: dict[str, dict[str, object]] = {}
        if provider_id in ("ollama-cloud", "ollama_cloud"):
            # Keep the live Ollama catalog and its native capabilities visible
            # to the UI. IDs are returned exactly as the user's API returns
            # them (including stable snapshot suffixes such as :0813).
            try:
                model_capabilities = {
                    d.id: {
                        "tools": d.has_tools,
                        "vision": d.has_vision,
                        "thinking": d.reasoning,
                        "structured_outputs": d.has_structured_outputs,
                        "context_window": d.context_window,
                    }
                    for d in descriptors
                }
            except UnboundLocalError:
                model_capabilities = {}
        providers.append(
            {
                "id": provider_id,
                "label": label,
                "models": ["alto"] + models,
                "model_capabilities": model_capabilities,
            }
        )

    return {"providers": providers}
