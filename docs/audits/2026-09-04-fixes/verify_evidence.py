"""Check this run's finite evidence, not a claim of production readiness."""
import json
from pathlib import Path

directory = Path(__file__).resolve().parent
golden = json.loads((directory / "golden.json").read_text())
tools = json.loads((directory / "tools.json").read_text())
trajectory = json.loads((directory / "trajectory.json").read_text())
assert all(r["passed"] and r["sdk_patched"] is False for r in (golden, tools, trajectory))
assert len(golden["cases"]) == 4 and all(c["passed"] for c in golden["cases"])
assert tools["tool_executions"] == 1 and tools["streamed_chunks"] > 0
assert tools["usage"]["total_tokens"] > 0
assert trajectory["complete"] is True and not trajectory["warning"]
assert trajectory["metrics"] and all(m["success"] for m in trajectory["metrics"])
assert any(m["agent"] == "a11y_expert_reviewer" and m["duration_ms"] > 0 for m in trajectory["metrics"])
print("FACTORY_LIVE_SAMPLE_MET")
