from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services.agent_project_audit import (
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    audit_agent_project,
    select_project_files,
)


def test_select_project_files_accepts_agent_sources_and_ignores_dependencies():
    selected, skipped = select_project_files(
        [
            ("src/agent.py", b"def run():\n    return True\n"),
            ("README.md", b"Agent architecture"),
            ("node_modules/tool.js", b"should not be sent"),
            ("dist/bundle.js", b"should not be sent"),
            ("image.png", b"not text"),
        ]
    )

    assert [name for name, _ in selected] == ["src/agent.py", "README.md"]
    assert skipped["ignored"] == 2
    assert skipped["unsupported"] == 1


def test_select_project_files_enforces_per_file_and_total_limits():
    files = [(f"file_{index}.py", b"x" * 60_000) for index in range(9)]
    selected, skipped = select_project_files(
        [("large.py", b"x" * (MAX_FILE_BYTES + 1)), *files]
    )

    assert len(selected) == MAX_TOTAL_BYTES // 60_000
    assert skipped["too_large"] == 2


@pytest.mark.asyncio
async def test_audit_agent_project_validates_structured_findings():
    raw = (
        '{"findings":[{"id":"F-1","category":"security",'
        '"severity":"high","confidence":"high","file":"src/agent.py",'
        '"evidence":"tool permissions are unrestricted",'
        '"description":"The agent has no visible permission boundary",'
        '"impact":"A compromised prompt can reach sensitive tools",'
        '"recommendation":"Add an allowlist and approval for high-risk tools"}]}'
    )
    with patch(
        "backend.src.services.agent_project_audit.call_llm_structured",
        new=AsyncMock(side_effect=lambda **kwargs: kwargs["build"](raw)),
    ) as mock_call:
        result = await audit_agent_project([("src/agent.py", "tool()")], {})

    assert result.success is True
    assert result.data["findings"][0]["category"] == "security"
    assert result.data["files_analyzed"] == ["src/agent.py"]
    mock_call.assert_awaited_once()
