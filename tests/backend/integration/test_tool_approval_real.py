"""Contrato real do portão com uma ferramenta registrada de leitura local."""

import json
from types import SimpleNamespace

from backend.src.services.audit_observability import audit_scope
from backend.src.services.chat_tools import register_chat_tools
from run_agent import AIAgent


def test_real_registered_tool_obeys_approval_setting_and_audits_decisions(tmp_path, monkeypatch):
    project = tmp_path / "a11y_demo"
    project.mkdir()
    (project / "index.html").write_text('<html lang="pt-BR"><title>Teste</title></html>', encoding="utf-8")
    register_chat_tools()
    args = {"project_dir": str(project), "pre_exec_msg": "Lendo o projeto de teste"}

    # Deny-by-default: a ferramenta precisa ser CONCEDIDA ao agente para o
    # portão de aprovação ser exercitado; sem concessão o resultado é
    # "denied" antes de qualquer decisão de aprovação.
    # O portão de aprovação é incondicional (regra do harness: configuração
    # não desativa aprovação de ferramenta marcada), então settings de
    # approval_enabled não controlam o caminho blocked/cancelled/approved.
    monkeypatch.setattr(
        "backend.src.services.audit_observability.get_settings",
        lambda: SimpleNamespace(approval_enabled=True),
    )

    prompts: list[str] = []
    agent = AIAgent(model="probe", provider="openai", enabled_toolsets=["a11y_chat"])
    with audit_scope() as blocked_audit:
        blocked = agent._execute_tool_calls([("blocked", "read_local_project_files", args)])
    assert "aprovação explícita" in json.loads(blocked["blocked"])["error"]
    assert _approval(blocked_audit) == "blocked"

    agent.clarify_callback = lambda question, _choices: prompts.append(question) or "Cancelar"
    with audit_scope() as cancelled_audit:
        cancelled = agent._execute_tool_calls([("cancelled", "read_local_project_files", args)])
    assert "cancelada" in json.loads(cancelled["cancelled"])["error"]
    assert _approval(cancelled_audit) == "cancelled"
    assert json.dumps(str(project))[1:-1] in prompts[0]

    agent.clarify_callback = lambda _question, _choices: "Aprovar"
    with audit_scope() as approved_audit:
        approved = agent._execute_tool_calls([("approved", "read_local_project_files", args)])
    assert json.loads(approved["approved"])["files"][0]["path"] == "index.html"
    assert _approval(approved_audit) == "approved"

    # Portão incondicional (contrato atual): a configuração approval_enabled
    # NÃO desativa a aprovação de ferramenta marcada -- ao contrário do que
    # este teste verificava no contrato de 2026-09-25 (que executava sem
    # confirmação quando a configuração estava desligada), hoje nada é lido:
    # sem canal de aprovação a ação termina bloqueada, com o portão ativo.
    monkeypatch.setattr(
        "backend.src.services.audit_observability.get_settings",
        lambda: SimpleNamespace(approval_enabled=False),
    )
    agent.clarify_callback = None
    with audit_scope() as disabled_audit:
        disabled = agent._execute_tool_calls([("disabled", "read_local_project_files", args)])
    assert "aprovação explícita" in json.loads(disabled["disabled"])["error"]
    assert _approval(disabled_audit) == "blocked"
    assert disabled_audit.snapshot()["counters"]["approval_requests"] == 0


def _approval(audit):
    completed = [event for event in audit.snapshot()["events"] if event.get("phase") == "completed"]
    assert len(completed) == 1
    return completed[0]["approval"]
