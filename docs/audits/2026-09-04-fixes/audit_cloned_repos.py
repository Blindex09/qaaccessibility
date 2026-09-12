"""Run QAAccessibility's project ZIP endpoint against each cloned project."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026-09-04"))
from live_probe import load_keys  # noqa: E402

REPOS = {
    "unlazy": Path(r"C:\unlazy"),
    "skillgate": Path(r"C:\skillgate"),
    "ArgusAgent": Path(r"C:\ArgusAgent"),
    "horizon": Path(r"C:\horizon"),
    "zaofu": Path(r"C:\zaofu"),
    "adl": Path(r"C:\adl"),
    "aga-verify-agent": Path(r"C:\aga-verify-agent"),
}
EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".vue", ".svelte"}
SKIP_PARTS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}


def make_zip(directory: Path) -> tuple[bytes, list[str]]:
    candidates = []
    for path in directory.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue
        candidates.append(path)
    candidates.sort(key=lambda p: (len(p.parts), str(p)))
    selected = candidates[:80]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in selected:
            archive.write(path, path.relative_to(directory).as_posix())
    return buffer.getvalue(), [path.relative_to(directory).as_posix() for path in selected]


def main() -> int:
    import os

    os.environ.setdefault("SECRET_KEY", "audit-only")
    os.environ.setdefault("QA_SECRET_STORE_PATH", str(Path(__file__).resolve().parent / "cloned-repo-secrets.json"))
    from fastapi.testclient import TestClient

    import backend.src.agents.orchestrator.orchestrator as orchestration
    import backend.src.config.settings as settings_module
    import backend.src.services.llm_client as llm_client
    from backend.src.config.settings import Settings
    from backend.src.main import app

    key = load_keys(Path(r"C:\Users\olive\Downloads\chaves de api.txt"))["factory"]
    settings = Settings(_env_file=None, secret_key="audit-only", llm_provider="factory",
                        llm_model="auto", llm_api_key=key, llm_base_url=None,
                        llm_fallback_provider=None, llm_fallback_model=None,
                        a11y_response_cache_enabled=False, a11y_max_concurrent_agents=2,
                        agent_timeout_seconds=210)
    records = []
    with patch.object(llm_client, "get_settings", return_value=settings), \
         patch.object(settings_module, "get_settings", return_value=settings), \
         patch.object(orchestration, "get_settings", return_value=settings), \
         patch.object(Settings, "build_fallback_model", return_value={}), \
         patch("run_agent.AIAgent._resolve_auto_fallback", return_value=None):
        for name, directory in REPOS.items():
            payload, files = make_zip(directory)
            if not files:
                records.append({"project": name, "path": str(directory), "files_sent": 0,
                                "status": "not_applicable", "reason": "Nenhum arquivo web compatível encontrado"})
                print(json.dumps(records[-1], ensure_ascii=False), flush=True)
                continue
            response = TestClient(app).post(
                "/analyze/project/zip",
                files={"file": (f"{name}.zip", payload, "application/zip")},
            )
            body = response.json()
            data = body.get("data", {}) if isinstance(body, dict) else {}
            issues = data.get("issues", []) if isinstance(data, dict) else []
            records.append({
                "project": name, "path": str(directory), "files_sent": len(files),
                "status_code": response.status_code, "status": "passed" if response.status_code == 200 and body.get("success") else "failed",
                "success": body.get("success"),
                "complete": data.get("complete"), "warning": data.get("warning"),
                "issue_count": len(issues),
                "criteria": sorted({str(issue.get("criterion", "")) for issue in issues}),
                "error": body.get("error"),
            })
            print(json.dumps(records[-1], ensure_ascii=False), flush=True)
    output = Path(__file__).resolve().parent / "cloned-repos-results.json"
    output.write_text(json.dumps({"provider": "factory", "model": "auto", "projects": records}, indent=2), encoding="utf-8")
    return 0 if all(item.get("status") in {"passed", "not_applicable"} and item.get("complete") is not False for item in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
