"""Planejamento determinístico da squad sobre o pipeline multiagente atual.

Esta primeira camada não substitui o orchestrator. Ela define quem decide,
quem executa e quais evidências precisam existir antes de avançar.
"""

from .contracts import SquadPlan, SquadTask, TaskStatus
from .roles import SquadRole


def build_squad_plan(objective: str, *, include_implementation: bool = True) -> SquadPlan:
    """Cria um plano de acessibilidade com tarefas dependentes e gates claros."""
    tasks = [
        SquadTask(
            id="product-scope",
            title="Confirmar objetivo, público e critérios de aceite",
            role=SquadRole.PRODUCT_OWNER,
            status=TaskStatus.READY,
            acceptance_criteria=["escopo da página/projeto definido", "critérios WCAG prioritários registrados"],
        ),
        SquadTask(
            id="a11y-analysis",
            title="Executar análise especializada de acessibilidade",
            role=SquadRole.A11Y_SPECIALIST,
            depends_on=["product-scope"],
            specialist_agents=["orchestrator", "delegation_coordinator", "wcag_semantics", "aria_specialist", "screen_reader"],
            acceptance_criteria=["achados deduplicados", "evidências por elemento", "severidade e critério WCAG"],
            artifacts=["analysis_report"],
        ),
    ]
    if include_implementation:
        tasks.append(
            SquadTask(
                id="a11y-remediation",
                title="Implementar correções de acessibilidade aprovadas",
                role=SquadRole.DEVELOPER,
                depends_on=["a11y-analysis"],
                specialist_agents=["fixer"],
                acceptance_criteria=["somente mudanças aprovadas", "checkpoint reversível criado", "HTML/artefato corrigido renderiza"],
                artifacts=["fixed_artifact", "change_summary"],
            )
        )
    test_dependency = "a11y-remediation" if include_implementation else "a11y-analysis"
    tasks.extend(
        [
            SquadTask(
                id="qa-validation",
                title="Validar correções com testes funcionais e de acessibilidade",
                role=SquadRole.QA_LEAD,
                depends_on=[test_dependency],
                specialist_agents=["test_generator", "visual_a11y", "operability"],
                acceptance_criteria=["testes executados", "regressões registradas", "original e corrigido comparáveis"],
                artifacts=["test_report", "live_preview_evidence"],
            ),
            SquadTask(
                id="documentation-release",
                title="Documentar resultado e preparar entrega",
                role=SquadRole.DOCUMENTATION,
                depends_on=["qa-validation"],
                specialist_agents=["checklist", "vpat_reporter"],
                acceptance_criteria=["relatório reproduzível", "limitações registradas", "artefatos prontos para entrega"],
                artifacts=["checklist", "report", "release_evidence"],
            ),
        ]
    )
    return SquadPlan(
        objective=objective,
        tasks=tasks,
        quality_gates=[
            "não implementar sem aprovação explícita",
            "não aceitar correção que não renderize",
            "não concluir sem teste e evidência",
            "manter rastreabilidade entre achado, mudança e teste",
        ],
    )
