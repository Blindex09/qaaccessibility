"""
Deep Research Agent — Pesquisa normativa iterativa de acessibilidade.

Activado quando o utilizador precisa de investigação aprofundada
sobre normas de acessibilidade (WCAG, APG patterns, ACT rules, EN 301 549,
Section 508, PDF/UA, WAI-ARIA).

Executa pesquisas progressivas: query geral -> específica -> casos de borda.
Cita as fontes normativas consultadas. max_iterations=8 para pesquisa iterativa.
"""

import logging

from backend.src.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEEP_RESEARCH_PROMPT = """
Você é um agente especializado em pesquisa normativa de acessibilidade digital.
A sua missão é investigar aprofundadamente normas, critérios e técnicas de
acessibilidade para responder a perguntas técnicas precisas.

Processo obrigatório:
1. Formula 3 queries progressivas: (a) geral, (b) específica, (c) casos de borda.
2. Pesquisa com tavily_search e exa_search em sequência. Se você também tiver uma
   ferramenta de busca web nativa disponível neste turno, use-a como reforço
   adicional (não substitui tavily/exa, é mais uma fonte independente) --
   especialmente útil quando tavily/exa não retornarem uma fonte primária clara.
3. Avalia cada resultado: é uma fonte normativa primária (W3C, Section508.gov,
   ETSI EN 301 549, PDF Association)? Ou secundária (tutorial, artigo)?
4. Prioriza fontes primárias. Se encontrares conflito entre fontes, documenta.
5. Sintetiza a resposta final citando TODAS as fontes consultadas com URL.

Fontes prioritárias:
- https://www.w3.org/WAI/WCAG22/   (critérios de sucesso WCAG 2.2)
- https://www.w3.org/WAI/ARIA/apg/ (padrões de design WAI-ARIA APG)
- https://www.w3.org/TR/accname/   (algoritmo AccName)
- https://www.section508.gov/       (Section 508 US)
- https://www.etsi.org/             (EN 301 549)
- https://pdfa.org/                 (PDF/UA)

Regras:
- Zero emojis.
- Acentuação portuguesa rigorosa.
- Cita sempre a cláusula exacta (ex.: WCAG 2.2 Critério 1.1.1) ou o padrão APG
  (ex.: APG Dialog Pattern).
- Se a norma não existir ou não tiveres certeza, diz explicitamente.
"""


async def run_deep_research(
    question: str,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """
    Executa pesquisa normativa aprofundada sobre uma questão de acessibilidade.

    Parâmetros
    ----------
    question : str
        Pergunta normativa a investigar.
    provider / model / api_key / base_url :
        Config do LLM (usa settings se omitidos).

    Devolve
    -------
    dict com 'answer' (str), 'question' (str) e 'status' ('ok' ou 'error').
    """
    settings = get_settings()
    if not provider:
        cfg = settings.chat_model_config()
        provider = cfg.get("provider", "")
        model = model or cfg.get("model", "")
        api_key = api_key or cfg.get("api_key", "")
    from backend.src.services.model_router import resolve_model_and_provider
    provider, model = resolve_model_and_provider(provider or "", model, tier="alto")

    logger.info("[deep_research] Investigando: %s", question[:120])
    try:
        from backend.src.services.chat_tools import A11Y_CHAT_TOOLSET
        from run_agent import AIAgent

        agent = AIAgent(
            model=model or "",
            provider=provider or "",
            api_key=api_key,
            base_url=base_url,
            max_iterations=8,
            quiet_mode=True,
            enabled_toolsets=[A11Y_CHAT_TOOLSET],
            ephemeral_system_prompt=_DEEP_RESEARCH_PROMPT,
            log_prefix="[deep_research]",
            # Pedido do usuário (2026-08-11): busca nativa do provider (OpenAI/
            # xAI/Anthropic) roda em PARALELO com tavily_search/exa_search
            # abaixo -- o modelo escolhe qual usar. Ollama (sem busca nativa
            # boa) e Gemini (incompatível com function tools na mesma
            # chamada) continuam só com tavily/exa -- ver AIAgent.__init__.
            enable_native_web_search=True,
        )
        result = agent.run_conversation(user_message=question)
        answer = result.get("final_response") or ""
        return {"answer": answer, "question": question, "status": "ok"}
    except Exception as exc:
        logger.error("[deep_research] Falha: %s", exc)
        return {"answer": "", "question": question, "status": "error", "error": str(exc)}
