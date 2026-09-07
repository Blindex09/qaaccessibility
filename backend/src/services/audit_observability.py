"""Structured, provider-independent observability for an agent run.

The existing hooks and OpenTelemetry integration are useful to external
observers, but the orchestrator response did not expose a compact audit
record.  This module bridges that gap without retaining prompts, HTML or
secrets: it records routing-relevant metadata, tool lifecycle events,
approval outcomes and LLM latency/counters for the current run.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from backend.src.services import agent_hooks

_CURRENT: contextvars.ContextVar[AuditRun | None] = contextvars.ContextVar(
    "qaaccessibility_audit_run", default=None
)
_REGISTER_LOCK = threading.Lock()
_HOOKS_REGISTERED = False
_SENSITIVE_PARTS = ("key", "token", "secret", "password", "cookie", "authorization", "content")


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if any(part in str(key).casefold() for part in _SENSITIVE_PARTS) else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:240] if not any(part in value.casefold() for part in _SENSITIVE_PARTS) else "[redacted]"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:240]


class AuditRun:
    """In-memory audit record scoped to one orchestrator execution."""

    def __init__(self) -> None:
        self.run_id = f"qa-{uuid.uuid4().hex}"
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.events: list[dict[str, Any]] = []

    def add(self, event_type: str, **data: Any) -> None:
        with self._lock:
            self.events.append(
                {
                    "event_id": hashlib.sha256(f"{self.run_id}:{len(self.events)}".encode()).hexdigest()[:16],
                    "type": event_type,
                    "timestamp": time.time(),
                    **{key: _safe_value(value) for key, value in data.items()},
                }
            )

    def snapshot(self) -> dict[str, Any]:
        finished_at = time.time()
        with self._lock:
            events = list(self.events)
        llm_events = [event for event in events if event["type"] == "llm_call"]
        tool_events = [event for event in events if event["type"] == "tool_call"]
        tool_requests = [event for event in tool_events if event.get("phase") == "requested"]
        tool_completions = [event for event in tool_events if event.get("phase") == "completed"]
        approvals = [event for event in tool_requests if event.get("requires_approval")]
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_ms": round((finished_at - self.started_at) * 1000, 1),
            "counters": {
                "events": len(events),
                "llm_calls": len(llm_events),
                "llm_failures": sum(1 for event in llm_events if not event.get("success", True)),
                "tool_requests": len(tool_requests),
                "tool_calls": len(tool_completions),
                "tool_failures": sum(1 for event in tool_completions if event.get("success") is False),
                "approval_requests": len(approvals),
                "approval_cancellations": sum(1 for event in tool_events if event.get("approval") == "cancelled"),
            },
            "events": events,
        }


def _current() -> AuditRun | None:
    return _CURRENT.get()


def _on_pre_tool(tool_id: Any, name: str, args: dict[str, Any]) -> None:
    audit = _current()
    if audit is None:
        return
    requires_approval = False
    try:
        from tools.registry import registry

        requires_approval = bool(registry.tools.get(name, {}).get("requires_approval"))
    except Exception:
        pass
    audit.add("tool_call", phase="requested", tool_id=tool_id, tool=name, arguments=args, requires_approval=requires_approval)


def _on_post_tool(tool_id: Any, name: str, args: dict[str, Any], result: str) -> None:
    audit = _current()
    if audit is None:
        return
    try:
        parsed = json.loads(result) if isinstance(result, str) else result
    except (TypeError, json.JSONDecodeError):
        parsed = {}
    text = result.casefold() if isinstance(result, str) else ""
    approval = "cancelled" if "cancelada" in text or "cancelled" in text else "approved"
    audit.add(
        "tool_call",
        phase="completed",
        tool_id=tool_id,
        tool=name,
        arguments=args,
        success=not isinstance(parsed, dict) or not parsed.get("error"),
        approval=approval,
        result_summary={"has_error": bool(isinstance(parsed, dict) and parsed.get("error"))},
    )


def _on_post_llm(provider: str, model: str, task_id: str, label: str, success: bool, duration_ms: float) -> None:
    audit = _current()
    if audit is not None:
        audit.add("llm_call", provider=provider, model=model, task_id=task_id, agent=label, success=success, duration_ms=duration_ms)


def _on_error(provider: str, model: str, task_id: str, label: str, error: str) -> None:
    audit = _current()
    if audit is not None:
        audit.add("error", provider=provider, model=model, task_id=task_id, agent=label, error=error)


def _register_hooks() -> None:
    global _HOOKS_REGISTERED
    with _REGISTER_LOCK:
        if _HOOKS_REGISTERED:
            return
        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, _on_pre_tool)
        agent_hooks.register_hook(agent_hooks.POST_TOOL_CALL, _on_post_tool)
        agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, _on_post_llm)
        agent_hooks.register_hook(agent_hooks.ON_ERROR, _on_error)
        _HOOKS_REGISTERED = True


@contextmanager
def audit_scope() -> Iterator[AuditRun]:
    """Collect lifecycle events for the current execution context."""
    _register_hooks()
    audit = AuditRun()
    token = _CURRENT.set(audit)
    try:
        yield audit
    finally:
        _CURRENT.reset(token)


def audited_orchestrator(fn):
    """Decorator that attaches the structured audit to ``AgentResult.data``."""

    async def wrapper(*args: Any, **kwargs: Any):
        with audit_scope() as audit:
            result = await fn(*args, **kwargs)
            if hasattr(result, "data") and isinstance(result.data, dict):
                result.data.setdefault("audit", audit.snapshot())
            return result

    wrapper.__name__ = getattr(fn, "__name__", "audited_orchestrator")
    wrapper.__doc__ = fn.__doc__
    return wrapper
