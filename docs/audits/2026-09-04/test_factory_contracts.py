"""Acceptance probes, intentionally red until Factory reaches provider parity.

No credentials/network. A fake SDK response isolates the QA -> SDK boundary.
These tests are outside default discovery to preserve the measured baseline.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import backend.src.services.a11y_domain_tools  # noqa: F401 -- same registration used by llm_client
from run_agent import AIAgent


@pytest.fixture
def sdk():
    result = SimpleNamespace(
        success=True, text="{\"issues\": []}",
        usage={"input_tokens": 37, "output_tokens": 11, "total_tokens": 48},
    )
    with patch("droid_sdk.run", new=AsyncMock(return_value=result)) as mock:
        yield mock


def invoke(**kwargs):
    agent = AIAgent(provider="factory", model="auto", api_key="audit-dummy",
                    fallback_model={}, **kwargs)
    return agent.run_conversation("Audit the supplied HTML.")


def test_positive_control_response_is_returned(sdk):
    assert invoke()["final_response"] == '{"issues": []}'
    sdk.assert_awaited_once()


def test_prior_turn_context_reaches_sdk(sdk):
    invoke(prefill_messages=[{"role": "user", "content": "CONTEXT_CANARY_914"}])
    assert "CONTEXT_CANARY_914" in str(sdk.call_args), "previous turns discarded"


def test_output_schema_reaches_sdk(sdk):
    schema = {"type": "object", "properties": {"issues": {"type": "array"}}}
    invoke(response_schema=schema)
    assert dict(sdk.call_args.kwargs["output"].schema) == schema, "schema discarded"


def test_qa_toolset_reaches_sdk(sdk):
    invoke(enabled_toolsets=["a11y_tools"])
    config = sdk.call_args.kwargs.get("config")
    assert config and getattr(config, "mcp_servers", ()), "no QA tool bridge"


def test_usage_not_reported_as_zero(sdk):
    assert invoke()["usage"]["total_tokens"] != 0, "unknown/real usage reported as zero"


def test_system_instruction_uses_sdk_boundary(sdk):
    invoke(ephemeral_system_prompt="SYSTEM_CANARY_915")
    config = sdk.call_args.kwargs.get("config")
    assert config and getattr(config, "system_prompt", None), "system text demoted into user prompt"


def test_permissions_and_deadline_explicit(sdk):
    invoke()
    assert sdk.call_args.kwargs.get("timeout"), "no SDK deadline"
    assert sdk.call_args.kwargs.get("config"), "permission policy inherited"
