"""A squad como máquina de estados real -- não como plano estático.

Contexto: até esta mudança, a camada de squad era simulada de ponta a ponta.
`TaskStatus` era atribuído na construção e NUNCA transicionava (IN_PROGRESS,
REVIEW e DONE não apareciam em lugar nenhum do código), `specialist_agents`
era escrito e nunca lido, nenhum dos papéis existia como agente, e a interface
mostrava apenas a contagem de etapas. O plano era um dicionário colado no
prompt.

Estes testes fixam o que faz dela real: estados transicionam por execução,
portões bloqueiam de verdade, e o handoff de um papel é a entrada do próximo.
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.squad import SquadCoordinator, TaskStatus
from backend.src.agents.squad.contracts import RoleDecision
from backend.src.agents.squad.roles import SquadRole


def _decisao(papel: SquadRole, **kwargs) -> RoleDecision:
    return RoleDecision(
        role=papel,
        summary=kwargs.get("summary", f"{papel.value} decidiu"),
        decisions=kwargs.get("decisions", ["algo concreto"]),
        blockers=kwargs.get("blockers", []),
        handoff=kwargs.get("handoff", {"chave": papel.value}),
    )


# ── Portões que bloqueiam de verdade ─────────────────────────────────────────


def test_tarefa_nao_pode_comecar_com_dependencia_aberta():
    squad = SquadCoordinator("auditar uma pagina")
    qa = squad.plan.task("qa-validation")
    assert not squad.plan.dependencies_met(qa)

    squad.record_done("a11y-analysis")
    assert squad.plan.dependencies_met(qa)


def test_entrega_nao_fecha_sem_qa():
    """O portão que existe para impedir 'concluído' sem evidência."""
    squad = SquadCoordinator("auditar e corrigir")
    entrega = squad.plan.task("release-readiness")

    squad.record_done("a11y-analysis")
    squad.record_done("qa-validation")
    assert not squad.plan.dependencies_met(entrega), "documentacao ainda nao fechou"

    squad.record_done("documentation-release")
    assert squad.plan.dependencies_met(entrega)


def test_correcao_nasce_bloqueada_e_so_a_aprovacao_libera():
    squad = SquadCoordinator("corrigir o contraste")
    remediacao = squad.plan.task("a11y-remediation")
    assert remediacao.status is TaskStatus.BLOCKED

    squad.unblock_remediation()
    assert remediacao.status is TaskStatus.READY
    assert remediacao.metadata["approved_by_user"] is True


# ── Transições reais de estado ───────────────────────────────────────────────


async def test_papel_transiciona_in_progress_e_done_e_emite_a_decisao():
    squad = SquadCoordinator("auditar uma pagina")
    with patch(
        "backend.src.agents.squad.coordinator.run_product_owner",
        new=AsyncMock(return_value=_decisao(SquadRole.PRODUCT_OWNER)),
    ), patch(
        "backend.src.agents.squad.coordinator.run_tech_lead",
        new=AsyncMock(return_value=_decisao(SquadRole.TECH_LEAD)),
    ), patch(
        "backend.src.agents.squad.coordinator.run_engineering_manager",
        new=AsyncMock(return_value=_decisao(SquadRole.ENGINEERING_MANAGER)),
    ):
        eventos = [evento async for evento in squad.run_planning()]

    tipos = [evento["type"] for evento in eventos]
    assert tipos.count("squad_decision") == 3
    estados = [e["status"] for e in eventos if e["type"] == "squad_task" and e["task_id"] == "product-scope"]
    assert estados == ["in_progress", "done"], "o estado tem de transicionar de verdade"
    assert squad.plan.task("cycle-planning").status is TaskStatus.DONE


async def test_papel_que_entrega_com_ressalva_conclui_e_nao_trava_a_cadeia():
    """Achado da execucao real (2026-08-30): o Product Owner quase sempre
    registra alguma ressalva (publico nao informado, URL ausente). Tratar isso
    como BLOCKED travava tech-approach e cycle-planning para sempre -- o portao
    de dependencia nunca abria -- e, como `planning_done` exige as tres DONE, o
    planejamento reexecutava a cada turno, anulando o quadro persistente.

    Levantar impedimento nao e falhar: numa squad real, apontar o bloqueio E o
    trabalho. O bloqueio continua visivel e vai para a triagem do Scrum Master.
    """
    squad = SquadCoordinator("auditar uma pagina atras de login")
    with patch(
        "backend.src.agents.squad.coordinator.run_product_owner",
        new=AsyncMock(return_value=_decisao(SquadRole.PRODUCT_OWNER, blockers=["falta credencial"])),
    ), patch(
        "backend.src.agents.squad.coordinator.run_tech_lead",
        new=AsyncMock(return_value=_decisao(SquadRole.TECH_LEAD)),
    ), patch(
        "backend.src.agents.squad.coordinator.run_engineering_manager",
        new=AsyncMock(return_value=_decisao(SquadRole.ENGINEERING_MANAGER)),
    ):
        [evento async for evento in squad.run_planning()]

    assert squad.plan.task("product-scope").status is TaskStatus.DONE
    assert squad.plan.task("tech-approach").status is TaskStatus.DONE, "a cadeia nao pode travar"
    assert squad.plan.task("cycle-planning").status is TaskStatus.DONE
    assert squad.open_blockers() == ["falta credencial"], "o impedimento continua visivel"
    assert squad.planning_done is True, "senao o planejamento reexecuta a cada turno"


async def test_papel_que_nao_entrega_decisao_nenhuma_fica_bloqueado():
    squad = SquadCoordinator("auditar")
    sem_decisao = _decisao(SquadRole.PRODUCT_OWNER, decisions=[], blockers=["nao consegui definir escopo"])
    with patch(
        "backend.src.agents.squad.coordinator.run_product_owner", new=AsyncMock(return_value=sem_decisao)
    ), patch(
        "backend.src.agents.squad.coordinator.run_tech_lead",
        new=AsyncMock(return_value=_decisao(SquadRole.TECH_LEAD)),
    ), patch(
        "backend.src.agents.squad.coordinator.run_engineering_manager",
        new=AsyncMock(return_value=_decisao(SquadRole.ENGINEERING_MANAGER)),
    ):
        eventos = [evento async for evento in squad.run_planning()]

    assert squad.plan.task("product-scope").status is TaskStatus.BLOCKED
    # E o portao segura o proximo papel: sem escopo, nao ha o que projetar.
    assert squad.plan.task("tech-approach").status is TaskStatus.BLOCKED
    assert any(e["type"] == "squad_blocked" for e in eventos)


async def test_papel_com_dependencia_aberta_nao_executa():
    """O portão não é decorativo: o agente do papel nem chega a ser chamado."""
    squad = SquadCoordinator("auditar")
    chamou = AsyncMock(return_value=_decisao(SquadRole.QA_LEAD))
    with patch("backend.src.agents.squad.coordinator.run_qa_lead", new=chamou), patch(
        "backend.src.agents.squad.coordinator.run_release", new=AsyncMock(return_value=_decisao(SquadRole.RELEASE))
    ):
        eventos = [evento async for evento in squad.run_closing()]

    chamou.assert_not_awaited()
    assert squad.plan.task("qa-validation").status is TaskStatus.BLOCKED
    assert any(evento["type"] == "squad_blocked" for evento in eventos)


# ── Handoff encadeado: a entrega de um papel é a entrada do próximo ──────────


async def test_o_proximo_papel_recebe_o_handoff_do_anterior():
    squad = SquadCoordinator("auditar uma pagina")
    tech_lead = AsyncMock(return_value=_decisao(SquadRole.TECH_LEAD))
    with patch(
        "backend.src.agents.squad.coordinator.run_product_owner",
        new=AsyncMock(return_value=_decisao(SquadRole.PRODUCT_OWNER, handoff={"scope": "home page"})),
    ), patch("backend.src.agents.squad.coordinator.run_tech_lead", new=tech_lead), patch(
        "backend.src.agents.squad.coordinator.run_engineering_manager",
        new=AsyncMock(return_value=_decisao(SquadRole.ENGINEERING_MANAGER)),
    ):
        [evento async for evento in squad.run_planning()]

    contexto = tech_lead.await_args.args[0]
    assert contexto["handoffs"]["product_owner"] == {"scope": "home page"}, (
        "sem isso os papeis seriam opinioes independentes, nao uma squad"
    )


# ── Scrum Master: determinístico, só quando há bloqueio ──────────────────────


async def test_scrum_master_nao_roda_sem_bloqueio():
    squad = SquadCoordinator("auditar")
    chamou = AsyncMock(return_value=_decisao(SquadRole.SCRUM_MASTER))
    with patch("backend.src.agents.squad.coordinator.run_scrum_master", new=chamou):
        eventos = [evento async for evento in squad.run_scrum_master()]

    chamou.assert_not_awaited(), "papel sem impedimento a triar e chamada de LLM desperdicada"
    assert eventos == []


async def test_scrum_master_roda_quando_ha_bloqueio():
    squad = SquadCoordinator("auditar")
    squad.plan.decisions.append(_decisao(SquadRole.PRODUCT_OWNER, blockers=["falta a URL"]))
    with patch(
        "backend.src.agents.squad.coordinator.run_scrum_master",
        new=AsyncMock(return_value=_decisao(SquadRole.SCRUM_MASTER)),
    ):
        eventos = [evento async for evento in squad.run_scrum_master()]

    assert len(eventos) == 1
    assert eventos[0]["type"] == "squad_decision"


# ── Falha de um papel degrada, nunca derruba o turno ─────────────────────────


async def test_papel_que_falha_vira_bloqueio_e_nao_excecao():
    from backend.src.agents.squad.role_agents._runner import run_role

    with patch(
        "backend.src.agents.squad.role_agents._runner.call_llm",
        new=AsyncMock(side_effect=RuntimeError("provider fora do ar")),
    ):
        decisao = await run_role(role=SquadRole.QA_LEAD, system_prompt="x", context={})

    assert decisao.succeeded is False
    assert decisao.blockers, "a falha tem de virar um impedimento visivel, nao silencio"
    assert "provider fora do ar" in decisao.error


async def test_resposta_do_papel_em_cerca_de_markdown_ainda_e_lida():
    from backend.src.agents.squad.role_agents._runner import run_role

    resposta = '```json\n{"summary": "ok", "decisions": ["a"], "blockers": [], "handoff": {"k": "v"}}\n```'
    with patch(
        "backend.src.agents.squad.role_agents._runner.call_llm",
        new=AsyncMock(return_value=resposta),
    ):
        decisao = await run_role(role=SquadRole.TECH_LEAD, system_prompt="x", context={})

    assert decisao.succeeded is True
    assert decisao.handoff == {"k": "v"}


# ── Quadro persistente: o ciclo sobrevive ao turno ───────────────────────────


def test_quadro_restaurado_preserva_estados_e_decisoes():
    squad = SquadCoordinator("auditar a home")
    squad.record_done("a11y-analysis", evidencia="12 achados")
    squad.plan.decisions.append(_decisao(SquadRole.PRODUCT_OWNER, handoff={"scope": "home"}))

    restaurado = SquadCoordinator.restore(squad.plan.to_dict())

    assert restaurado.objective == "auditar a home"
    assert restaurado.plan.task("a11y-analysis").status is TaskStatus.DONE
    assert restaurado.plan.task("a11y-analysis").metadata["evidencia"] == "12 achados"
    assert restaurado.plan.decisions[0].handoff == {"scope": "home"}


def test_planejamento_nao_roda_de_novo_num_ciclo_ja_planejado():
    """Nenhuma squad real replaneja a sprint a cada frase dita."""
    squad = SquadCoordinator("auditar")
    assert squad.planning_done is False

    for task_id in ("product-scope", "tech-approach", "cycle-planning"):
        squad.record_done(task_id)

    assert SquadCoordinator.restore(squad.plan.to_dict()).planning_done is True


def test_quadro_de_versao_antiga_nao_derruba_a_conversa():
    antigo = {
        "objective": "auditar",
        "tasks": [
            {"id": "tarefa-que-nao-existe-mais", "status": "done"},
            {"id": "a11y-analysis", "status": "estado-invalido"},
        ],
        "decisions": [{"role": "papel-inexistente", "summary": "x"}],
    }
    restaurado = SquadCoordinator.restore(antigo)

    assert restaurado.plan.task("a11y-analysis").status is TaskStatus.BACKLOG
    assert restaurado.plan.decisions == []


def test_tarefa_desconhecida_falha_alto_em_vez_de_silenciar():
    squad = SquadCoordinator("auditar")
    with pytest.raises(KeyError):
        squad.plan.task("nao-existe")
