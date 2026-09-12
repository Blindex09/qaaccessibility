"""Adapter for the official Factory Droid Python SDK.

Factory subscriptions are exposed through the authenticated ``droid`` runtime,
not a public Chat Completions endpoint.  Keep this boundary explicit so the
provider cannot accidentally be treated as an OpenAI-compatible proxy.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _usage(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None  # Unknown is not zero; chat omits its usage event.

    def get(name: str, default: Any = 0) -> Any:
        return raw.get(name, default) if isinstance(raw, dict) else getattr(raw, name, default)

    incoming, outgoing = int(get("input_tokens")), int(get("output_tokens"))
    return {"input_tokens": incoming, "output_tokens": outgoing, "total_tokens": incoming + outgoing,
            "cache_read_tokens": int(get("cache_read_tokens")),
            "cache_creation_tokens": int(get("cache_creation_tokens")),
            "factory_credits": get("factory_credits", None)}


def run_factory(
    prompt: Any, system_prompt: str | None, model: str, api_key: str | None, *,
    history: list[dict[str, Any]] | None = None,
    response_schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    execute_tools: Callable[..., dict[str, str]] | None = None,
    stream_callback: Callable[[str], None] | None = None,
    thinking_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    max_tool_calls: int = 40,
    timeout: float = 180,
    images: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Only QA tools are allowlisted; temporary cwd avoids repository instructions.

    This is a tool permission boundary, not an OS sandbox. QA tools retain
    their existing approval checks through AIAgent._execute_tool_calls.
    """
    import droid_sdk as sdk
    from droid_sdk.mcp import DroidTool, create_sdk_mcp_server

    executable = shutil.which("droid")
    if not executable:
        local = Path.home() / "bin" / ("droid.exe" if os.name == "nt" else "droid")
        if local.is_file():
            executable = str(local)
    if not executable:
        raise RuntimeError("Factory requer o Droid CLI instalado e acessível no PATH.")

    image_inputs = []
    def make_image(encoded: str, media_type: str) -> Any:
        if media_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise ValueError("Formato de imagem não suportado pelo Factory")
        return sdk.Image.from_bytes(base64.b64decode(encoded, validate=True),
                                    media_type=cast(sdk.ImageMediaType, media_type))

    text_parts = []
    if isinstance(prompt, list):
        for block in prompt:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "image_url":
                value = block.get("image_url", {})
                url = value.get("url", "") if isinstance(value, dict) else value
                if not url.startswith("data:"):
                    raise ValueError("Factory aceita imagens inline base64; URL remota não é suportada.")
                media, encoded = url[5:].split(";base64,", 1)
                image_inputs.append(make_image(encoded, media))
    else:
        text_parts.append(str(prompt))
    for image in images or []:
        image_inputs.append(make_image(image["data"], image.get("media_type", "image/png")))
    user_prompt = "\n".join(text_parts)
    if history:
        # No replayed model calls/tools: ordered prior transcript is supplied as data.
        user_prompt = "Prior conversation (JSON transcript):\n" + json.dumps(history, ensure_ascii=False) + "\n\nCurrent user message:\n" + user_prompt

    async def run_turn(directory: str) -> Any:
        tool_count = 0
        lock = asyncio.Lock()
        definitions = []
        for definition in tools or []:
            fn = definition["function"]
            name = fn["name"]

            def handler_for(tool_name: str) -> Callable[..., Any]:
                async def handler(arguments: dict[str, Any]) -> str:
                    nonlocal tool_count
                    async with lock:
                        if (cancel_check and cancel_check()) or tool_count >= max_tool_calls:
                            return json.dumps({"error": "Execução cancelada ou limite de ferramentas atingido."})
                        tool_count += 1
                    if execute_tools is None:
                        raise RuntimeError("Ponte de ferramentas QA ausente")
                    call_id = uuid.uuid4().hex
                    result = await asyncio.to_thread(execute_tools, [(call_id, tool_name, arguments)])
                    return result[call_id]
                return handler

            definitions.append(DroidTool(name, fn.get("description", ""), fn["parameters"], handler_for(name)))
        servers = [create_sdk_mcp_server("qa", definitions)] if definitions else []
        # Droid uses server___tool IDs (not the OpenAI-style mcp__ prefix).
        # An empty restriction is interpreted as unrestricted by the runtime.
        allowed = [f"qa___{tool.name}" for tool in definitions] or ["qa___no_tools_allowed"]

        def permission(request: Any) -> Any:
            # Approve only our registered bridge; its QA approval gate still runs.
            permitted = bool(request.actions) and all(
                isinstance(action, sdk.McpToolAction) and action.tool_name in allowed
                for action in request.actions
            ) and not (cancel_check and cancel_check())
            outcome = sdk.ToolConfirmationOutcome.PROCEED_ONCE if permitted else sdk.ToolConfirmationOutcome.CANCEL
            return request.respond(outcome)

        config = sdk.SessionConfig(
            system_prompt=system_prompt or "Follow the user's request using only the supplied QA tools.",
            autonomy=sdk.Autonomy.LOW, auto_reject_permission_requests=False,
            disable_builtin_skills=True, mcp_servers=servers, restrict_tools=allowed,
        )
        kwargs: dict[str, Any] = dict(cwd=directory, model=model if model not in ("", "alto") else "auto",
                      config=config, api_key=api_key or os.getenv("FACTORY_API_KEY"),
                      runtime=sdk.Runtime(executable=executable),
                      interactions=sdk.InteractionHandlers(on_permission=permission))
        output = sdk.JsonSchema(response_schema) if response_schema is not None else None

        async def invoke() -> Any:
            if stream_callback is None and thinking_callback is None:
                return await sdk.run(user_prompt, **kwargs, output=output, images=image_inputs, timeout=timeout)
            async with sdk.Session(**kwargs) as session:
                async with session.stream(user_prompt, output=output, images=image_inputs,
                                          timeout=timeout, include_partial_messages=True) as stream:
                    async for event in stream:
                        if isinstance(event, sdk.TextDelta) and stream_callback:
                            stream_callback(event.text)
                        elif isinstance(event, sdk.ThinkingDelta) and thinking_callback:
                            thinking_callback(event.text)
                return stream.result

        task = asyncio.create_task(invoke())
        try:
            async with asyncio.timeout(timeout + 15):
                while not task.done():
                    if cancel_check and cancel_check():
                        raise asyncio.CancelledError("Factory: turno cancelado")
                    await asyncio.wait({task}, timeout=0.1)
                return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    with tempfile.TemporaryDirectory(prefix="qa-factory-") as directory:
        result = asyncio.run(run_turn(directory))
    if not getattr(result, "success", False):
        detail = getattr(result, "error", None) or getattr(result, "structured_output_error", None)
        message = f"Factory Droid falhou ({getattr(result, 'subtype', 'error')}): {detail or 'sem detalhe'}"
        key = api_key or os.getenv("FACTORY_API_KEY")
        raise RuntimeError(message.replace(key, "[REDACTED]") if key else message)
    structured = getattr(result, "structured_output", None)
    text = json.dumps(_plain(structured), ensure_ascii=False) if structured is not None else str(result.text or "")
    response: dict[str, Any] = {"final_response": text, "failed": False}
    usage = _usage(getattr(result, "usage", None))
    if usage is not None:
        response["usage"] = usage
    return response
