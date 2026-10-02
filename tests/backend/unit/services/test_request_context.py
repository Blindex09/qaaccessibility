import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.request_context import (
    SCOPE_CONTRACT,
    context_payload,
    record_public_update,
    redirect_request,
    request_context,
    update_request,
)


@pytest.mark.asyncio
async def test_concurrent_requests_keep_scope_and_progress_isolated():
    async def run(request):
        with request_context(request, [{"role": "user", "content": "previous context"}]):
            record_public_update({"type": "phase", "text": request + " evidence"})
            await asyncio.sleep(0)
            return json.loads(context_payload())

    first, second = await asyncio.gather(run("only language"), run("only keyboard"))
    assert first["current_request"] == "only language"
    assert first["already_communicated"] == ["only language evidence"]
    assert second["current_request"] == "only keyboard"
    assert second["already_communicated"] == ["only keyboard evidence"]
    assert first["history"][0]["content"] == "previous context"
    assert context_payload() == ""


@pytest.mark.asyncio
async def test_sync_tool_async_bridge_preserves_request_context():
    from backend.src.services.chat_tools import _safe_async_run

    async def inspect():
        return json.loads(context_payload())

    with request_context("headings only"):
        update_request("language only")
        redirect_request("now review the captured evidence, without another inspection")
        result = _safe_async_run(inspect())
    assert result["current_request"].startswith("language only")
    assert "now review the captured evidence, without another inspection" in result["current_request"]


@pytest.mark.asyncio
@pytest.mark.parametrize("multimodal", [False, True])
async def test_scope_and_prior_updates_reach_actual_leaf_agent(multimodal, monkeypatch):
    from backend.src.config.settings import get_settings
    from backend.src.services.llm_client import call_llm
    from backend.src.services.response_cache import clear_cache

    clear_cache()
    monkeypatch.setattr(get_settings(), "a11y_route_advisor_enabled", False)
    prompt = [{"type": "text", "text": "captured evidence"}] if multimodal else "captured evidence"
    with patch("backend.src.services.llm_client.AIAgent") as agent:
        instance = MagicMock()
        instance.run_conversation.return_value = {"final_response": "[]", "failed": False}
        agent.return_value = instance
        with request_context("Examine apenas idioma e títulos"):
            record_public_update({"type": "phase", "text": "Recebi o documento."})
            await call_llm(system_prompt="Specialist contract", user_prompt=prompt, agent_label="wcag_semantics")
    assert SCOPE_CONTRACT in agent.call_args.kwargs["ephemeral_system_prompt"]
    sent = str(instance.run_conversation.call_args)
    assert "Examine apenas idioma e títulos" in sent
    assert "Recebi o documento." in sent
    assert "captured evidence" in sent
