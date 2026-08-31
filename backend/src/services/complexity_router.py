"""
complexity_router.py
Classificação de complexidade da tarefa, decidida pelo modelo -- nunca por
heurística fixa (tamanho de HTML, contagem de tags, palavra-chave). Alimenta
o dial custo/qualidade (`tradeoff`, 0-10) que o roteamento "Alto" usa para
pontuar candidatos em `ollama_cloud_adapter.score_ollama_cloud_model`.

Por quê um classificador, e não um limiar fixo: "zero keywords hardcoded que
prejudiquem ou condicionem o comportamento da IA" é regra do projeto (README).
Um `if len(html) > 50000: tradeoff = baixo` é exatamente o tipo de heurística
fixa que a regra proíbe -- uma página de 60KB pode ser um blog simples
(complexidade real baixa) e uma de 8KB pode ser um formulário denso com dezenas
de widgets ARIA (complexidade real alta). Só o modelo, lendo o conteúdo de
verdade, decide -- mesmo padrão do `AgenticAutoProvider._classify_complexity`
em C:\\agentic e do `ComplexityTier` citado como referência de mercado (OpenRouter
Auto Router, roteador do GPT-5, adaptive-reasoning-effort da Anthropic).

Roda UMA vez por pipeline de análise (não uma vez por sub-agente) -- mesma
economia documentada no roteador do NVDAStudio: classificar por chamada
individual pagaria uma chamada de LLM extra para cada um dos ~20 agentes.
O resultado viaja por ContextVar (mesmo padrão de chat_progress.py e
last_analysis_store.py) para que `llm_client.call_llm` o leia automaticamente
sem que cada agente precise repassar o parâmetro.
"""

import contextvars
import logging

logger = logging.getLogger(__name__)

# tradeoff 0-10: 0 = favorece qualidade/reasoning ao máximo, 10 = favorece
# custo/velocidade ao máximo. Mesma escala já usada em rank_ollama_cloud_candidates.
DEFAULT_TRADEOFF = 3  # comportamento historico do "Alto": favorece qualidade

_current_tradeoff: contextvars.ContextVar[int] = contextvars.ContextVar("complexity_tradeoff", default=DEFAULT_TRADEOFF)

SYSTEM_PROMPT = """
You are a task-complexity classifier for an accessibility-auditing pipeline.
Your ONLY job is to read the actual content being analyzed and decide how much
the pipeline should favor QUALITY/REASONING vs COST/SPEED when picking which
LLM model tier to run the analysis agents on.

Judge REAL complexity from what you actually see -- never from length alone:
- Low complexity (favor cost): simple static markup, few interactive elements,
  no custom ARIA widgets, straightforward semantic structure, small number of
  distinct components even if the raw HTML is long (e.g. a long article page).
- High complexity (favor quality): dense custom ARIA widgets (comboboxes, tab
  panels, live regions, modals), ambiguous or non-semantic markup needing
  careful judgment, many interacting form controls, ambiguous accessible-name
  computation, framework-heavy dynamic UI -- cases where a weaker model is
  more likely to miss or misjudge a real WCAG violation.

Return ONLY a JSON object:
{
  "tradeoff": <int 0-10, 0=maximize quality, 10=maximize cost savings>,
  "reasoning": "<one short sentence, in the same language as the content>"
}
No markdown fences, no prose outside the JSON.
""".strip()


TRADEOFF_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "tradeoff": {"type": "integer", "minimum": 0, "maximum": 10},
        "reasoning": {"type": "string"},
    },
    "required": ["tradeoff", "reasoning"],
    "additionalProperties": False,
}


def _extrair_tradeoff(raw: str) -> int:
    """Parse + validacao, usado por `call_llm_structured` para disparar o repair.

    Levantar aqui e o que faz um JSON cortado ser REFEITO, em vez de virar
    fallback silencioso para o default.
    """
    from backend.src.services.llm_client import extract_json_object

    data = extract_json_object(raw)
    if "tradeoff" not in data:
        raise ValueError("resposta sem o campo 'tradeoff'")
    # Fora da escala e LIMITADO, nao rejeitado: um 42 diz claramente
    # "maximizar economia", e `set_current_tradeoff` ja limita de qualquer
    # forma -- levantar aqui pagaria um retry para descartar um sinal usavel.
    # O que precisa levantar e o JSON cortado, que e o bug de verdade.
    valor = max(0, min(10, int(data["tradeoff"])))
    logger.info("[ComplexityRouter] %s", str(data.get("reasoning", ""))[:200])
    return valor


def set_current_tradeoff(tradeoff: int) -> contextvars.Token:
    """Define o tradeoff corrente (0-10). Devolve o token para reset."""
    clamped = max(0, min(10, int(tradeoff)))
    return _current_tradeoff.set(clamped)


def reset_current_tradeoff(token: contextvars.Token) -> None:
    _current_tradeoff.reset(token)


def get_current_tradeoff() -> int:
    """Lido por `llm_client.call_llm` ao resolver o tier "alto" -- sem
    classificação prévia nesta pipeline (ex.: chamada direta a um agente fora
    de `orchestrate()`, como nos testes de componente), devolve o default
    histórico (favorece qualidade), nunca um valor adivinhado."""
    return _current_tradeoff.get()


async def classify_and_set_tradeoff(content: str) -> int:
    """Classifica a complexidade real do conteúdo e define o tradeoff corrente
    para o resto da pipeline via ContextVar. Chamado uma vez por análise em
    `orchestrator.py`, nunca por sub-agente individual.

    Falha do classificador (rede, JSON malformado) -> mantém DEFAULT_TRADEOFF
    e loga aviso; nunca derruba a análise inteira por causa de uma otimização
    de custo.
    """
    if not content or not content.strip():
        set_current_tradeoff(DEFAULT_TRADEOFF)
        return DEFAULT_TRADEOFF

    try:
        from backend.src.services.llm_client import call_llm_structured

        tradeoff = await call_llm_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Classify the complexity of this content for accessibility analysis:\n\n{content[:15000]}",
            build=_extrair_tradeoff,
            temperature=0.0,
            # 150 tokens nao cabiam o JSON com o `reasoning` em prosa. Medido nos
            # logs de 2026-08-30: 3 falhas em 20 chamadas reais (15%), todas com a
            # saida cortada no meio e o tradeoff JA decidido ('off": 9,
            # "reasoning": "Conteudo muito simples: ... entao uma analise de ba').
            # Cada falha caia no DEFAULT_TRADEOFF, que favorece QUALIDADE: a
            # otimizacao de custo desligava calada, justamente na feature que
            # existe para economizar.
            # 400 tambem nao bastava: o modelo escreve preambulo antes do JSON
            # e o orcamento acabava antes do `{`. Medido em 2026-08-31 na
            # auditoria da propria interface -- as DUAS tentativas do
            # retry/repair falharam com "Let me analyze this content for
            # accessibility complexity. The content is a Portuguese..." --
            # `extract_json_object` ja tolera prosa antes; falta o objeto caber
            # depois dela.
            max_tokens=1200,
            agent_label="complexity_router",
            response_schema=TRADEOFF_SCHEMA,
            model_tier="fast",
        )
        set_current_tradeoff(tradeoff)
        logger.info("[ComplexityRouter] tradeoff=%d", tradeoff)
        return tradeoff
    except Exception as exc:
        logger.warning(
            "[ComplexityRouter] Falha na classificação (%s) -- mantendo tradeoff default=%d",
            exc,
            DEFAULT_TRADEOFF,
        )
        set_current_tradeoff(DEFAULT_TRADEOFF)
        return DEFAULT_TRADEOFF
