"""A ferramenta do chat que roda codigo no sandbox: concedida, com aprovacao e com a checagem de caminho."""

import json

from backend.src.services import chat_tools, code_sandbox
from backend.src.services.tool_groups import TOOL_GROUPS


def test_tool_is_in_the_tests_group():
    assert "run_code_in_sandbox" in TOOL_GROUPS["testes"]


def test_schema_has_no_time_limit_and_command_is_a_list():
    props = chat_tools._RUN_CODE_IN_SANDBOX_SCHEMA["parameters"]["properties"]
    assert props["command"]["type"] == "array"
    assert not any("timeout" in name or "second" in name for name in props)


def test_missing_folder_is_reported_without_running(tmp_path):
    out = json.loads(chat_tools.run_code_in_sandbox_tool({"project_dir": str(tmp_path / "nao_existe"), "command": ["python"]}))
    assert "Diretório não encontrado" in out["error"]


def test_without_docker_it_says_it_did_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(code_sandbox, "docker_cli", lambda: None)
    out = json.loads(chat_tools.run_code_in_sandbox_tool({"project_dir": str(tmp_path), "command": ["python", "-c", "print(1)"]}))
    assert out["status"] == "unavailable" and out["passed"] is False
