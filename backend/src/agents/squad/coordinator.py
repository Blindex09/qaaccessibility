"""Coordenação real da squad de acessibilidade sobre o pipeline multiagente.

O que "real" significa aqui, e o que era antes
-----------------------------------------------
Antes esta camada devolvia um dicionário estático: os status eram atribuídos
na construção e nunca transicionavam, `specialist_agents` era escrito e nunca
lido, os papéis não existiam como agentes e a interface só mostrava a
contagem de etapas. Era um enfeite colado no prompt.

Agora:

- Cada papel é um AGENTE com responsabilidade própria (`role_agents/`), e o
  `handoff` de um é literalmente a entrada do próximo -- Product Owner define
  escopo, Tech Lead decide abordagem em cima daquele escopo, Engineering
  Manager sequencia em cima daquela abordagem, QA Lead define evidência em
  cima do que foi realmente encontrado, Release decide entrega em cima do
  veredito do QA.
- Os status transicionam de verdade (`READY -> IN_PROGRESS -> DONE/BLOCKED`),
  disparados por eventos reais de execução, não por suposição.
- Os portões BLOQUEIAM: `SquadPlan.dependencies_met` impede uma tarefa de
  começar antes das dependências fecharem, e é por isso que documentação e
  entrega não fecham sem QA ter rodado.
- Papéis que já eram agentes do pipeline não foram reimplementados: análise
  é o orchestrator + os 29 especialistas, correção é o `fixer`, revisão de
  especialista é o `a11y_expert_reviewer`, documentação é
  `checklist`/`reporter`/`vpat_reporter`. O coordenador registra o que eles
  realmente fizeram em vez de duplicá-los.

No chat, o modelo escolhe os papéis e sua ordem por contexto, via run_selected_roles.
O harness valida IDs, orçamento, cancelamento e contratos. As rotinas batch
run_planning/run_closing não são a política de mobilização do chat.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from .contracts import RoleDecision, SquadPlan, SquadTask, TaskStatus
from .role_agents import (
    run_engineering_manager,
    run_product_owner,
    run_qa_lead,
    run_release,
    run_scrum_master,
    run_tech_lead,
)
from .roles import SquadRole

logger = logging.getLogger(__name__)

# Papéis executados por agente de papel próprio, na ordem do fluxo da squad.
# Os demais são executados pelo pipeline que já existe e apenas REGISTRADOS
# aqui (ver `record_*`), nunca reimplementados.
_PLANNING_TASK_IDS = ("product-scope", "tech-approach", "cycle-planning")
_CLOSING_TASK_IDS = ("qa-validation", "release-readiness")
_ROLE_PROGRESS_INTERVAL_SECONDS = 12.0

def build_squad_plan(objective: str, approval_enabled: bool = True) -> SquadPlan:
    """Monta o quadro da squad: tarefas, papéis, dependências e portões.

    A etapa de correção segue a configuração de aprovação. A autorização
    efetiva continua no portão das ferramentas de mutação.
    """
    tasks = [
        SquadTask(
            id="product-scope",
            title="Definir escopo, público e critérios de aceite",
            role=SquadRole.PRODUCT_OWNER,
            status=TaskStatus.READY,
            acceptance_criteria=["escopo do artefato definido", "critérios WCAG prioritários registrados"],
        ),
        SquadTask(
            id="tech-approach",
            title="Definir abordagem técnica e riscos",
            role=SquadRole.TECH_LEAD,
            depends_on=["product-scope"],
            acceptance_criteria=["abordagem justificada", "riscos técnicos nomeados"],
        ),
        SquadTask(
            id="cycle-planning",
            title="Sequenciar o ciclo, dependências e risco de entrega",
            role=SquadRole.ENGINEERING_MANAGER,
            depends_on=["tech-approach"],
            acceptance_criteria=["ordem definida", "dependências externas nomeadas"],
        ),
        SquadTask(
            id="a11y-analysis",
            title="Executar análise especializada de acessibilidade",
            role=SquadRole.A11Y_SPECIALIST,
            depends_on=["cycle-planning"],
            specialist_agents=["orchestrator", "delegation_coordinator", "a11y_expert_reviewer"],
            acceptance_criteria=["achados deduplicados", "evidências por elemento", "severidade e critério WCAG"],
            artifacts=["analysis_report"],
        ),
        SquadTask(
            id="a11y-remediation",
            title="Implementar correções de acessibilidade",
            role=SquadRole.DEVELOPER,
            status=TaskStatus.BLOCKED if approval_enabled else TaskStatus.READY,
            depends_on=["a11y-analysis"],
            specialist_agents=["fixer"],
            acceptance_criteria=([
                "aprovação explícita do usuário registrada antes de qualquer mutação",
                "somente mudanças aprovadas",
            ] if approval_enabled else []) + [
                "checkpoint reversível criado",
                "HTML/artefato corrigido renderiza",
            ],
            artifacts=["fixed_artifact", "change_summary"],
        ),
        SquadTask(
            id="qa-validation",
            title="Definir evidência, verificação manual e veredito",
            role=SquadRole.QA_LEAD,
            depends_on=["a11y-analysis"],
            specialist_agents=["test_generator", "screen_reader", "operability"],
            acceptance_criteria=[
                "evidência definida por achado",
                "plano de verificação manual (teclado, leitor de tela, zoom/reflow)",
                "o que não pôde ser verificado está declarado",
            ],
            artifacts=["test_report", "live_preview_evidence"],
        ),
        SquadTask(
            id="documentation-release",
            title="Documentar resultado e preparar entrega",
            role=SquadRole.DOCUMENTATION,
            depends_on=["qa-validation"],
            specialist_agents=["checklist", "reporter", "vpat_reporter"],
            acceptance_criteria=["relatório reproduzível", "limitações registradas", "artefatos prontos"],
            artifacts=["checklist", "report"],
        ),
        SquadTask(
            id="release-readiness",
            title="Decidir prontidão de entrega e risco residual",
            role=SquadRole.RELEASE,
            depends_on=["documentation-release"],
            acceptance_criteria=["prontidão declarada", "risco residual em termos de impacto no usuário"],
            artifacts=["release_evidence"],
        ),
    ]
    return SquadPlan(
        objective=objective,
        tasks=tasks,
        quality_gates=(["não implementar sem aprovação explícita"] if approval_enabled else []) + [
            "não aceitar correção que não renderize",
            "não concluir sem teste e evidência",
            "manter rastreabilidade entre achado, mudança e teste",
            "nunca declarar verificado o que não foi verificado",
        ],
    )


class SquadCoordinator:
    """Executa o quadro da squad: transiciona estados e encadeia handoffs."""

    def __init__(self, objective: str, approval_enabled: bool = True) -> None:
        self.approval_enabled = approval_enabled
        self.plan = build_squad_plan(objective, approval_enabled)
        self.objective = objective
        self.turn_context: dict[str, Any] = {}

    @classmethod
    def restore(cls, snapshot: dict[str, Any], approval_enabled: bool = True) -> "SquadCoordinator":
        """Recria o coordenador a partir do quadro persistido.

        Tolerante de propósito: um snapshot de uma versão anterior do plano
        (tarefa renomeada, papel novo) não pode derrubar a conversa. O que
        casa é restaurado, o que não casa fica no estado inicial e o ciclo
        segue -- degradar para "quadro parcialmente restaurado" é aceitável;
        estourar no meio de um turno do usuário não é.
        """
        coordinator = cls(str(snapshot.get("objective") or ""), approval_enabled)
        estados = {
            str(task.get("id")): task
            for task in snapshot.get("tasks", [])
            if isinstance(task, dict)
        }
        if "flow-health" in estados:
            coordinator.plan.tasks.append(SquadTask(id="flow-health", title="Resolver impedimentos do trabalho", role=SquadRole.SCRUM_MASTER))
        for task in coordinator.plan.tasks:
            salvo = estados.get(task.id)
            if not salvo:
                continue
            try:
                task.status = TaskStatus(str(salvo.get("status")))
            except ValueError:
                logger.warning("[Squad] status desconhecido no quadro salvo: %s", salvo.get("status"))
            if isinstance(salvo.get("metadata"), dict):
                task.metadata.update(salvo["metadata"])
            if task.metadata.get("selection_source") == "model":
                task.depends_on = []
            if (
                task.id == "a11y-remediation"
                and not approval_enabled
                and task.status is TaskStatus.BLOCKED
                and "blocked_reason" not in task.metadata
            ):
                task.status = TaskStatus.READY
        for registro in snapshot.get("decisions", []):
            if not isinstance(registro, dict):
                continue
            try:
                papel = SquadRole(str(registro.get("role")))
            except ValueError:
                continue
            handoff_salvo = registro.get("handoff")
            coordinator.plan.decisions.append(
                RoleDecision(
                    role=papel,
                    summary=str(registro.get("summary") or ""),
                    decisions=[str(d) for d in registro.get("decisions") or []],
                    blockers=[str(b) for b in registro.get("blockers") or []],
                    handoff=handoff_salvo if isinstance(handoff_salvo, dict) else {},
                    succeeded=bool(registro.get("succeeded", True)),
                    error=registro.get("error"),
                )
            )
        return coordinator

    @property
    def planning_done(self) -> bool:
        """True quando PO, Tech Lead e EM já entregaram nesta conversa.

        É o portão determinístico que impede replanejar a cada mensagem: o
        planejamento roda uma vez por ciclo, como numa squad de verdade.
        """
        return all(
            self.plan.task(task_id).status is TaskStatus.DONE for task_id in _PLANNING_TASK_IDS
        )

    # ── estado ───────────────────────────────────────────────────────────────

    def _context(self) -> dict[str, Any]:
        """O que um papel recebe: o objetivo e o que os papéis anteriores
        entregaram. É a entrada real, não um resumo."""
        return {
            "objective": self.objective,
            "approval_enabled": self.approval_enabled,
            "quality_gates": self.plan.quality_gates,
            "handoffs": {
                decision.role.value: decision.handoff
                for decision in self.plan.decisions
                if decision.handoff
            },
            "open_blockers": self.open_blockers(),
            "current_request": self.turn_context,
            "tasks": [task.__dict__ for task in self.plan.tasks],
        }

    def open_blockers(self) -> list[str]:
        return [blocker for decision in self.plan.decisions for blocker in decision.blockers]

    def _transition(self, task: SquadTask, status: TaskStatus) -> dict[str, Any]:
        task.status = status
        logger.info("[Squad] %s (%s) -> %s", task.id, task.role.value, status.value)
        return {
            "type": "squad_task",
            "task_id": task.id,
            "role": task.role.value,
            "title": task.title,
            "status": status.value,
        }

    # ── registro do que o pipeline existente fez de verdade ──────────────────

    def record_started(self, task_id: str) -> dict[str, Any]:
        """Marca IN_PROGRESS uma tarefa executada fora dos agentes de papel
        (análise, correção, documentação). Chamado pelo runtime quando o
        trabalho REALMENTE começa -- é isso que faz o quadro refletir a
        execução em vez de descrevê-la."""
        return self._transition(self.plan.task(task_id), TaskStatus.IN_PROGRESS)

    def record_done(self, task_id: str, **evidence: Any) -> dict[str, Any]:
        task = self.plan.task(task_id)
        task.metadata.update(evidence)
        return self._transition(task, TaskStatus.DONE)

    def record_blocked(self, task_id: str, reason: str) -> dict[str, Any]:
        task = self.plan.task(task_id)
        task.metadata["blocked_reason"] = reason
        return self._transition(task, TaskStatus.BLOCKED)

    def unblock_remediation(self) -> dict[str, Any]:
        """Registra a aprovação quando o portão de aprovação está ligado."""
        task = self.plan.task("a11y-remediation")
        task.metadata["approved_by_user"] = True
        return self._transition(task, TaskStatus.READY)

    # ── execução dos papéis ──────────────────────────────────────────────────

    async def _run_role_task(self, task_id: str, runner: Any, *, enforce_dependencies: bool = True) -> AsyncIterator[dict[str, Any]]:
        task = self.plan.task(task_id)
        if enforce_dependencies and not self.plan.dependencies_met(task):
            pendentes = [dep for dep in task.depends_on if self.plan.task(dep).status is not TaskStatus.DONE]
            yield self._transition(task, TaskStatus.BLOCKED)
            yield {
                "type": "squad_blocked",
                "task_id": task.id,
                "reason": f"dependencia nao concluida: {', '.join(pendentes)}",
            }
            return

        yield self._transition(task, TaskStatus.IN_PROGRESS)
        role_task = asyncio.create_task(runner(self._context()))
        try:
            while True:
                try:
                    decision = await asyncio.wait_for(
                        asyncio.shield(role_task),
                        timeout=_ROLE_PROGRESS_INTERVAL_SECONDS,
                    )
                    break
                except asyncio.TimeoutError:
                    from backend.src.services.execution_scope import check_execution

                    check_execution()
        finally:
            if not role_task.done():
                role_task.cancel()
                await asyncio.gather(role_task, return_exceptions=True)
        self.plan.decisions.append(decision)
        yield {
            "type": "squad_decision",
            "task_id": task.id,
            **decision.to_dict(),
        }

        # Levantar um impedimento NÃO é falhar a tarefa -- numa squad real,
        # apontar o bloqueio É o trabalho. Observado ao vivo: o Product Owner
        # quase sempre registra alguma ressalva (público não informado, URL
        # ausente), e tratar isso como BLOCKED travava `tech-approach` e
        # `cycle-planning` para sempre, porque o portão de dependência nunca
        # abria. Pior: como `planning_done` exige as três DONE, o planejamento
        # reexecutava a cada turno, anulando o quadro persistente.
        #
        # BLOCKED fica para quem realmente não entregou: o papel falhou
        # (provider fora do ar) ou não produziu decisão nenhuma. Os bloqueios
        # continuam visíveis no quadro e vão para a triagem do Scrum Master.
        entregou = decision.succeeded and bool(decision.decisions)
        yield self._transition(task, TaskStatus.DONE if entregou else TaskStatus.BLOCKED)

    async def run_selected_roles(self, roles: list[str], context: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Execute exactly the model-selected order, never infer roles from text.

        A QA consultation defines evidence or reviews existing evidence; it is
        not a claim that tests ran. Only the external tool approval gate can
        authorize mutations; a role handoff never grants permissions.
        """
        runners = {
            "product_owner": ("product-scope", run_product_owner),
            "tech_lead": ("tech-approach", run_tech_lead),
            "engineering_manager": ("cycle-planning", run_engineering_manager),
            "qa_lead": ("qa-validation", run_qa_lead),
            "release": ("release-readiness", run_release),
            "scrum_master": ("flow-health", run_scrum_master),
        }
        # Validate the complete request BEFORE any role runs.
        if any(role not in runners for role in roles) or len(roles) != len(set(roles)):
            raise ValueError("Seleção de papéis da squad inválida.")
        self.enable_contextual_mobilization()
        self.turn_context = context
        for role in roles:
            from backend.src.services.execution_scope import check_execution

            check_execution()
            task_id, runner = runners[role]
            if task_id == "flow-health" and not any(task.id == task_id for task in self.plan.tasks):
                self.plan.tasks.append(SquadTask(id=task_id, title="Resolver impedimentos do trabalho", role=SquadRole.SCRUM_MASTER))
            # Static management dependencies are not a conversational policy.
            # Record the actual selected consultation, without pretending skipped
            # roles ran or converting a QA consultation into verified conformance.
            task = self.plan.task(task_id)
            task.depends_on = []
            task.metadata["selection_source"] = "model"
            task.metadata["work_kind"] = "role_consultation_not_executed_verification"
            async for event in self._run_role_task(task_id, runner, enforce_dependencies=False):
                yield event

    def enable_contextual_mobilization(self) -> None:
        """Do not expose the batch management chain as a chat prerequisite.

        Mutation approval and evidence requirements remain outside these
        consultation dependencies and cannot be granted by role selection.
        """
        for task_id in (*_PLANNING_TASK_IDS, "a11y-analysis"):
            task = self.plan.task(task_id)
            task.depends_on = []
            task.metadata["mobilization"] = "contextual"

    async def run_planning(self) -> AsyncIterator[dict[str, Any]]:
        """Product Owner -> Tech Lead -> Engineering Manager, antes da análise.

        Sequencial de propósito: cada um decide EM CIMA da entrega do anterior.
        Rodar em paralelo devolveria três opiniões independentes, que é
        justamente o que uma squad não é.
        """
        runners = (run_product_owner, run_tech_lead, run_engineering_manager)
        for task_id, runner in zip(_PLANNING_TASK_IDS, runners, strict=True):
            async for event in self._run_role_task(task_id, runner):
                yield event

    async def run_closing(self) -> AsyncIterator[dict[str, Any]]:
        """QA Lead -> Release, depois de análise/correção/documentação."""
        runners = (run_qa_lead, run_release)
        for task_id, runner in zip(_CLOSING_TASK_IDS, runners, strict=True):
            async for event in self._run_role_task(task_id, runner):
                yield event

    async def run_scrum_master(self) -> AsyncIterator[dict[str, Any]]:
        """Tria os bloqueios levantados. Determinístico: só roda quando existe
        bloqueio de verdade -- um Scrum Master que fala sem haver impedimento
        é ruído, e custa uma chamada de LLM à toa."""
        if not self.open_blockers():
            return
        decision = await run_scrum_master(self._context())
        self.plan.decisions.append(decision)
        yield {"type": "squad_decision", "task_id": "flow-health", **decision.to_dict()}
