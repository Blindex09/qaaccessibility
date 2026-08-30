"""Planejamento determinístico da squad sobre o pipeline multiagente atual.

Esta primeira camada não substitui o orchestrator. Ela define quem decide,
quem executa e quais evidências precisam existir antes de avançar.

Por que a correção está SEMPRE no plano, e sempre BLOQUEADA
-----------------------------------------------------------
Antes, quem chamava esta função decidia por regex de palavras-chave
(`corrig|remedi|fix|implementar|aplicar`) se a tarefa de correção entrava no
plano. Isso quebrava de dois jeitos:

1. Violava a regra do README ("zero keywords hardcoded que bloqueiem ou
   condicionem o comportamento da LLM"): o plano é injetado no prompt como
   contrato de execução, então a regex condicionava o modelo.
2. Errava em pedidos comuns. "melhore o contraste", "ajuste os rótulos",
   "deixe acessível" não casam com nenhuma daquelas raízes -- o plano chegava
   ao modelo sem etapa de correção justamente quando o usuário pediu correção.

A correção agora é sempre um passo do plano, com status `BLOCKED`: ela existe,
está visível e é explicitamente inalcançável sem aprovação. Nada precisa
adivinhar a intenção do usuário a partir do texto dele, e a autorização real
continua onde sempre esteve -- no `requires_approval` das ferramentas de
mutação e na regra 13 do prompt do chat (checkpoint de remediação).
"""

from .contracts import SquadPlan, SquadTask, TaskStatus
from .roles import SquadRole


def build_squad_plan(objective: str) -> SquadPlan:
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
            specialist_agents=[
                "orchestrator",
                "delegation_coordinator",
                "wcag_semantics",
                "aria_specialist",
                "screen_reader",
            ],
            acceptance_criteria=["achados deduplicados", "evidências por elemento", "severidade e critério WCAG"],
            artifacts=["analysis_report"],
        ),
    ]
    tasks.append(
        SquadTask(
            id="a11y-remediation",
            title="Implementar correções de acessibilidade aprovadas",
            role=SquadRole.DEVELOPER,
            # BLOCKED, nunca BACKLOG: o bloqueio é a aprovação do usuário, e o
            # plano tem de dizer isso em vez de sugerir uma fila que anda sozinha.
            status=TaskStatus.BLOCKED,
            depends_on=["a11y-analysis"],
            specialist_agents=["fixer"],
            acceptance_criteria=[
                "aprovação explícita do usuário registrada antes de qualquer mutação",
                "somente mudanças aprovadas",
                "checkpoint reversível criado",
                "HTML/artefato corrigido renderiza",
            ],
            artifacts=["fixed_artifact", "change_summary"],
        )
    )
    tasks.extend(
        [
            SquadTask(
                id="qa-validation",
                title="Validar correções com testes funcionais e de acessibilidade",
                role=SquadRole.QA_LEAD,
                # Depende da análise, não da correção: uma auditoria sem
                # correção aprovada continua tendo QA e entrega. Quando houve
                # correção, o critério abaixo obriga a comparar com o original.
                depends_on=["a11y-analysis"],
                specialist_agents=["test_generator", "visual_a11y", "operability"],
                acceptance_criteria=[
                    "testes executados",
                    "regressões registradas",
                    "se houve correção, original e corrigido comparáveis",
                ],
                artifacts=["test_report", "live_preview_evidence"],
            ),
            SquadTask(
                id="documentation-release",
                title="Documentar resultado e preparar entrega",
                role=SquadRole.DOCUMENTATION,
                depends_on=["qa-validation"],
                specialist_agents=["checklist", "vpat_reporter"],
                acceptance_criteria=[
                    "relatório reproduzível",
                    "limitações registradas",
                    "artefatos prontos para entrega",
                ],
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
