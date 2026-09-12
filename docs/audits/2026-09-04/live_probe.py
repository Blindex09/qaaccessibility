"""Bounded live audit. Secrets stay in memory, output contains only allowlisted facts.

--verify never calls a provider; it checks the latest recorded live evidence.
Factory generation is NOT allowed until its local tool boundary is verified.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load_keys(path: Path) -> dict[str, str]:
    lines = [line.strip().lstrip("\ufeff") for line in path.read_text(encoding="utf-8-sig").splitlines()]
    keys = {}
    for index, line in enumerate(lines):
        label = line.lower().strip(": ")
        if label not in {"ollama", "factory"}:
            continue
        value = next((item for item in lines[index + 1:] if item), "")
        if len(value) >= 20 and not any(char.isspace() for char in value):
            keys[label] = value
    return keys


async def factory_catalog(key: str) -> dict:
    from droid_sdk import list_models

    try:
        with tempfile.TemporaryDirectory(prefix="qa-factory-catalog-") as directory:
            models = await asyncio.wait_for(list_models(api_key=key, cwd=directory), timeout=45)
        return {"catalog_ok": bool(models), "model_count": len(models),
                "generation": "not_run_unverified_tool_boundary"}
    except Exception as exc:
        return {"catalog_ok": False, "error_type": type(exc).__name__,
                "generation": "not_run_unverified_tool_boundary"}


def main() -> int:
    output = HERE / "live-results.json"
    if "--verify" in sys.argv:
        if not output.exists():
            print("LIVE_AGENT_GATES_UNMET: evidence missing")
            return 1
        data = json.loads(output.read_text(encoding="utf-8"))
        if data.get("agent_suite_passed") is not True:
            print("LIVE_AGENT_GATES_UNMET: real quality not established")
            return 1
        print("LIVE_AGENT_GATES_MET")
        return 0
    keys = load_keys(Path(r"C:\Users\olive\Downloads\chaves de api.txt"))
    facts: dict = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                   "keys_found": sorted(keys), "agent_suite_passed": False}
    if "factory" in keys:
        facts["factory"] = asyncio.run(factory_catalog(keys["factory"]))
    if "ollama" in keys:
        try:
            response = httpx.post(
                "https://ollama.com/api/chat",
                headers={"Authorization": "Bearer " + keys["ollama"]},
                json={"model": "gpt-oss:120b", "stream": False,
                      "messages": [{"role": "user", "content": "Reply OK only."}],
                      "options": {"num_predict": 32}}, timeout=60,
            )
            facts["ollama"] = {"http_status": response.status_code,
                               "quota_indicated": response.status_code == 429 and
                               any(term in response.text.lower() for term in ("limit", "quota", "usage"))}
            if response.status_code == 200:
                env = dict(os.environ, OLLAMA_API_KEY=keys["ollama"], RUN_REAL_LLM_TESTS="1")
                with tempfile.TemporaryDirectory(prefix="qa-live-secrets-") as directory:
                    env["QA_SECRET_STORE_PATH"] = str(Path(directory) / "secrets.json")
                    run = subprocess.run(
                        [sys.executable, "-m", "pytest", "tests/backend/real_llm", "-o", "addopts=",
                         "-q", "--tb=short", "--maxfail=3", f"--junitxml={HERE / 'real-llm.xml'}"],
                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
                    )
                # Scrub every loaded value before persisting provider error text.
                log = run.stdout + run.stderr
                for secret in keys.values():
                    log = log.replace(secret, "[REDACTED]")
                xml_path = HERE / "real-llm.xml"
                if xml_path.exists():
                    xml = xml_path.read_text(encoding="utf-8")
                    for secret in keys.values():
                        xml = xml.replace(secret, "[REDACTED]")
                    xml_path.write_text(xml, encoding="utf-8")
                (HERE / "real-llm.log").write_text(log, encoding="utf-8")
                facts["real_suite_exit"] = run.returncode
                facts["agent_suite_passed"] = run.returncode == 0
        except Exception as exc:
            facts["ollama_error_type"] = type(exc).__name__
    output.write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(json.dumps(facts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
