import json

from backend.src.services.public_updates import PublicUpdates


def test_partial_json_never_leaks_and_updates_arrive_before_final():
    seen = []
    reader = PublicUpdates(seen.append)
    raw = json.dumps({"updates": ["Vou conferir o escopo informado.", "Vou preparar as dependências."],
                      "handoff": {"secret": "private protocol"}}, ensure_ascii=False)
    for char in raw:
        reader.feed(char)
    assert seen == ["Vou conferir o escopo informado.", "Vou preparar as dependências."]
    assert reader.emitted == 2
    assert "private protocol" not in "".join(seen)


def test_only_explicit_first_root_field_is_public():
    seen = []
    reader = PublicUpdates(seen.append)
    reader.feed('{"reasoning":"private", "updates":["not exposed"]}')
    assert seen == []
    assert reader.emitted == 0


def test_public_string_does_not_leak_until_complete():
    seen = []
    reader = PublicUpdates(seen.append)
    reader.feed('{"updates":["Vou conferir')
    assert seen == []
    assert reader.emitted == 0
    reader.feed(' o escopo.",')
    assert seen == ["Vou conferir o escopo."]
    assert reader.emitted == 1


async def test_role_runner_wires_public_stream_before_structured_result(monkeypatch):
    from backend.src.agents.squad.role_agents import _runner
    from backend.src.agents.squad.roles import SquadRole
    from backend.src.services import chat_progress

    seen = []

    async def leaf(**kwargs):
        callback = kwargs["public_update_callback"]
        callback('{"updates":["Vou delimitar a página inicial."],')
        assert seen[0]["message"] == "Vou delimitar a página inicial."
        return {"summary": "Uma página, sem alterações.", "decisions": ["Inspecionar homepage"], "handoff": {}}

    monkeypatch.setattr(_runner, "call_llm_structured", leaf)
    token = chat_progress.set_sink(seen.append)
    try:
        result = await _runner.run_role(role=SquadRole.PRODUCT_OWNER, system_prompt="scope", context={})
    finally:
        chat_progress.reset_sink(token)
    assert result.succeeded
    assert seen[0]["type"] == "squad_progress"
