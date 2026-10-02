import json
from types import SimpleNamespace

from backend.src.services import agent_hooks
from backend.src.services.audit_observability import audit_scope, audited_orchestrator
from run_agent import AIAgent
from tools.registry import registry


def test_audit_scope_records_tool_llm_and_approval_events():
    with audit_scope() as audit:
        audit.add(
            "tool_call",
            phase="requested",
            tool_id="tool-1",
            tool="fix_and_zip_files",
            arguments={"html_content": "secret"},
            requires_approval=True,
        )
        agent_hooks.fire(agent_hooks.TOOL_APPROVAL, "tool-1", "cancelled")
        agent_hooks.fire(
            agent_hooks.POST_TOOL_CALL,
            "tool-1",
            "fix_and_zip_files",
            {"html_content": "secret"},
            json.dumps({"error": "Ação cancelada pelo usuário."}),
        )
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama-cloud", "model-x", "task-1", "perceiver", True, 12.5)

    snapshot = audit.snapshot()
    assert snapshot["counters"]["tool_calls"] == 1
    assert snapshot["counters"]["llm_calls"] == 1
    assert snapshot["counters"]["approval_requests"] == 1
    assert snapshot["counters"]["approval_cancellations"] == 1
    assert all(event.get("arguments", {}).get("html_content") != "secret" for event in snapshot["events"])


def test_audit_hooks_are_scoped_to_the_current_run():
    with audit_scope() as first:
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama", "model", "task", "agent", True, 1)
    with audit_scope() as second:
        pass

    assert first.snapshot()["counters"]["llm_calls"] == 1
    assert second.snapshot()["counters"]["llm_calls"] == 0


def test_real_tool_path_restores_audit_hooks_after_registry_clear(monkeypatch):
    """Regressão: outra suíte limpa hooks, mas o próximo turno precisa auditar."""
    monkeypatch.setitem(
        registry.tools,
        "audit_probe",
        {"handler": lambda args: json.dumps({"value": args["value"]}), "requires_approval": False},
    )
    agent = AIAgent(model="probe", provider="openai")

    with audit_scope() as first:
        agent._execute_tool_calls([("call-1", "audit_probe", {"value": 1})])
    assert first.snapshot()["counters"]["tool_calls"] == 1

    agent_hooks.clear_all_hooks()
    with audit_scope() as second:
        agent._execute_tool_calls([("call-2", "audit_probe", {"value": 2})])
    assert second.snapshot()["counters"]["tool_requests"] == 1
    assert second.snapshot()["counters"]["tool_calls"] == 1


def test_parallel_tool_results_keep_the_audit_context(monkeypatch):
    """Regressão: tools paralelas concluíam, mas o contexto sumia nas threads."""
    monkeypatch.setitem(
        registry.tools,
        "audit_probe",
        {"handler": lambda args: json.dumps({"value": args["value"]}), "requires_approval": False},
    )
    agent = AIAgent(model="probe", provider="openai")
    with audit_scope() as audit:
        results = agent._execute_tool_calls([
            ("call-1", "audit_probe", {"value": 1}),
            ("call-2", "audit_probe", {"value": 2}),
        ])

    assert len(results) == 2
    assert audit.snapshot()["counters"]["tool_requests"] == 2
    assert audit.snapshot()["counters"]["tool_calls"] == 2


# O NOME da variavel não pode casar com API_KEY/SECRET/TOKEN/PASSWORD: o scanner de
# credenciais embutidas (test_no_hardcoded_secrets) varre o proprio repositorio e
# qualquer "nome_com_esses_marcadores = "<literal 24+ chars>" é um falso positivo --
# o valor aqui é prosa de teste, nao credencial.
def test_audit_keeps_argument_names_without_user_content():
    fragmento_de_prova = "conteudo-privado-da-pagina"
    with audit_scope() as audit:
        agent_hooks.fire(
            agent_hooks.PRE_TOOL_CALL, "call-1", "probe",
            {"custom_instruction": fragmento_de_prova, "zip_base64": fragmento_de_prova, "html": fragmento_de_prova},
        )
        agent_hooks.fire(
            agent_hooks.POST_TOOL_CALL, "call-1", "probe", {"html": fragmento_de_prova},
            json.dumps({"error": "falha"}),
        )
        agent_hooks.fire(agent_hooks.ON_ERROR, "openai", "model", "task", "agent", fragmento_de_prova)

    snapshot = audit.snapshot()
    assert fragmento_de_prova not in json.dumps(snapshot, ensure_ascii=False)
    assert snapshot["events"][0]["arguments"] == {
        "custom_instruction": "[redacted]",
        "zip_base64": "[redacted]",
        "html": "[redacted]",
    }
    assert snapshot["events"][-1]["error_present"] is True


def test_direct_audit_event_redacts_content_fields():
    with audit_scope() as audit:
        audit.add("probe", html="pagina privada", prompt="pedido privado", zip_base64="arquivo privado")
    assert audit.snapshot()["events"][0]["html"] == "[redacted]"
    assert audit.snapshot()["events"][0]["prompt"] == "[redacted]"
    assert audit.snapshot()["events"][0]["zip_base64"] == "[redacted]"


def test_audit_marks_confirmation_as_disabled_when_setting_is_off(monkeypatch):
    monkeypatch.setattr(
        "backend.src.services.audit_observability.get_settings",
        lambda: SimpleNamespace(approval_enabled=False),
    )
    monkeypatch.setitem(registry.tools, "write_test", {"requires_approval": True})

    with audit_scope() as audit:
        agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, "call-1", "write_test", {})
        agent_hooks.fire(agent_hooks.TOOL_APPROVAL, "call-1", "disabled")
        agent_hooks.fire(agent_hooks.POST_TOOL_CALL, "call-1", "write_test", {}, "executed")

    snapshot = audit.snapshot()
    assert snapshot["counters"]["approval_requests"] == 0
    assert snapshot["events"][-1]["approval"] == "disabled"


def test_tool_error_text_cannot_impersonate_approval_decision(monkeypatch):
    """O resultado da ferramenta não é a fonte da decisão de autorização."""
    monkeypatch.setitem(
        registry.tools,
        "approval_probe",
        {"handler": lambda _args: "Ação cancelada pelo usuário.", "requires_approval": True},
    )
    # Deny-by-default: sem concessão explícita a ferramenta é negada ANTES do
    # portão, e `run_local_tool` termina com approval="denied" sem jamais
    # chegar ao handler nem à aprovação — o cenário que este teste cobre
    # (texto do handler não decide o audit log) não aconteceria. Conceder a
    # tool ao agente é o mínimo para o portão de aprovação ser exercitado.
    registry.toolsets["test_approval_probe"] = ["approval_probe"]
    agent = AIAgent(
        model="probe", provider="openai",
        enabled_toolsets=["test_approval_probe"],
        clarify_callback=lambda _question, _choices: "Aprovar",
    )

    try:
        with audit_scope() as audit:
            agent._execute_tool_calls([("call-1", "approval_probe", {})])

        completed = [event for event in audit.snapshot()["events"] if event.get("phase") == "completed"]
        assert completed[0]["approval"] == "approved"
    finally:
        registry.toolsets.pop("test_approval_probe", None)


def test_audited_orchestrator_attaches_audit_to_result_data():
    class Result:
        def __init__(self):
            self.data = {}

    @audited_orchestrator
    async def fake_orchestrator():
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama", "model", "task", "agent", True, 1)
        return Result()

    import asyncio

    result = asyncio.run(fake_orchestrator())
    assert result.data["audit"]["counters"]["llm_calls"] == 1
    assert result.data["audit"]["run_id"].startswith("qa-")
