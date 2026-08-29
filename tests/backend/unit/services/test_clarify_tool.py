"""Testes da tool `clarify` (pergunta interativa do agente).

Bug real de auditoria: o `chat_runtime` habilitava o toolset "clarify"
(`enabled_toolsets=[A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET]`), mas nenhuma tool com
esse nome era registrada -- `get_tool_names_for_toolset("clarify")` devolvia
lista vazia. As regras 12 (PLANNING & APPROVAL) e 13 (REMEDIATION CHECKPOINT) do
system prompt mandam o modelo usar a tool `clarify`, ou seja: eram literalmente
inexecutáveis, o modelo nunca teve essa tool para chamar.
"""

import json

from backend.src.services.chat_tools import CLARIFY_TOOLSET, register_chat_tools
from run_agent import run_local_tool
from tools.registry import registry


class TestClarifyToolRegistration:
    def test_clarify_toolset_exposes_the_clarify_tool(self):
        register_chat_tools()
        assert registry.get_tool_names_for_toolset(CLARIFY_TOOLSET) == ["clarify"]
        assert "clarify" in registry.tools

    def test_clarify_schema_declares_question_and_options(self):
        register_chat_tools()
        schema = registry.tools["clarify"]["schema"]
        properties = schema["parameters"]["properties"]
        assert "question" in properties
        assert "options" in properties
        assert schema["parameters"]["required"] == ["question"]


class TestClarifyToolRoundTrip:
    def test_call_round_trips_through_the_clarify_callback(self):
        """A tool tem de usar o mesmo callback de clarify que o agente já recebe."""
        register_chat_tools()
        asked: list[tuple[str, list[str]]] = []

        def fake_clarify_callback(question: str, choices: list[str]) -> str:
            asked.append((question, choices))
            return "Aprovar Plano"

        raw = run_local_tool(
            "clarify",
            {"question": "Posso rodar o perceiver e o forms_a11y?", "options": ["Aprovar Plano", "Cancelar"]},
            fake_clarify_callback,
        )

        out = json.loads(raw)
        assert asked == [("Posso rodar o perceiver e o forms_a11y?", ["Aprovar Plano", "Cancelar"])]
        assert out["answer"] == "Aprovar Plano"
        assert out["question"] == "Posso rodar o perceiver e o forms_a11y?"
        assert out["options"] == ["Aprovar Plano", "Cancelar"]

    def test_without_a_clarify_channel_the_call_fails_explicitly(self):
        register_chat_tools()
        out = json.loads(run_local_tool("clarify", {"question": "Posso corrigir?"}))
        assert "error" in out
        assert "clarify" in out["error"]

    def test_empty_question_is_rejected_without_asking_the_user(self):
        register_chat_tools()
        calls: list[str] = []
        out = json.loads(
            run_local_tool("clarify", {"question": "   "}, lambda q, _c: calls.append(q) or "x")
        )
        assert "error" in out
        assert calls == []
