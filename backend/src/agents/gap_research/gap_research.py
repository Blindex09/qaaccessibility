import logging

from backend.src.shared.models import AccessibilityIssue, AgentResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Agente: GapResearch (verificação automática de lacuna)
#
# Papel no pipeline:
#   Roda DEPOIS do merge/dedup + delegação, ANTES da revisão final do
#   a11y_expert_reviewer. Quando um sub-agente reporta baixa confiança num
#   achado (confidence=low -- "se isso for real é grave, mas não tenho
#   certeza que é"), esse é exatamente o sinal real de que o modelo sozinho
#   não tem base suficiente pra decidir. Em vez de deixar essa incerteza sem
#   resolução, delega pro agente de Deep Research já existente (pesquisa real
#   na web, fontes normativas primárias: W3C/WCAG, WAI-ARIA APG,
#   Section508.gov, EN 301 549, PDF/UA) e anexa a resposta pesquisada como
#   contexto extra no issue -- nunca sobrescreve severidade/confiança
#   sozinho (isso continua sendo decisão do a11y_expert_reviewer, que já lê
#   o campo enriquecido).
#
#   Bounded: no máximo MAX_GAP_RESEARCH_ISSUES por análise, numa ÚNICA
#   chamada de pesquisa cobrindo todos eles (não uma por issue) -- pesquisa
#   web real custa tempo/tokens, então isso é reforço seletivo pros casos
#   mais incertos, não uma segunda passada completa.
# ─────────────────────────────────────────────────────────────────────────────

MAX_GAP_RESEARCH_ISSUES = 3


def _build_gap_research_question(issues: list[AccessibilityIssue]) -> str:
    lines = [f"- Criterion {i.criterion} on element `{i.element[:150]}`: {i.description[:200]}" for i in issues]
    return (
        "An automated accessibility audit agent flagged the following findings "
        "but reported LOW confidence in each one (uncertain whether it's a genuine "
        "violation). For EACH finding below, research the applicable normative "
        "source (WCAG 2.2, WAI-ARIA APG, Section 508, EN 301 549, or PDF/UA as "
        "relevant) and state whether the described pattern is a genuine violation "
        "according to the spec, citing the exact clause. If the spec is ambiguous "
        "or the pattern depends on context you cannot verify, say so explicitly "
        "instead of guessing.\n\n" + "\n".join(lines)
    )


async def run_gap_research_check(issues: list[AccessibilityIssue]) -> AgentResult:
    """Verifica achados de baixa confianca via pesquisa normativa real
    (delega pro deep_research existente). `issues` ja deve vir filtrada e
    limitada pelo chamador (ver MAX_GAP_RESEARCH_ISSUES). Falha de forma
    graciosa -- verificacao e reforco best-effort, nunca deve derrubar o
    pipeline principal."""
    if not issues:
        return AgentResult(agent="gap_research", success=True, data={"answer": "", "issue_ids": []})

    capped = issues[:MAX_GAP_RESEARCH_ISSUES]
    try:
        from backend.src.agents.deep_research.deep_research import run_deep_research

        question = _build_gap_research_question(capped)
        research = await run_deep_research(question)
        if research.get("status") != "ok" or not research.get("answer"):
            return AgentResult(
                agent="gap_research",
                success=False,
                data={"answer": "", "issue_ids": []},
                error=research.get("error") or "deep_research não retornou resposta utilizável",
            )
        logger.info(
            "[GapResearch] Pesquisa normativa concluída para %d achado(s) de baixa confiança",
            len(capped),
        )
        return AgentResult(
            agent="gap_research",
            success=True,
            data={"answer": research["answer"], "issue_ids": [i.id for i in capped]},
        )
    except Exception as exc:
        logger.warning("[GapResearch] Falha na verificação de lacuna (seguindo sem ela): %s", exc)
        return AgentResult(agent="gap_research", success=False, data={"answer": "", "issue_ids": []}, error=str(exc))
