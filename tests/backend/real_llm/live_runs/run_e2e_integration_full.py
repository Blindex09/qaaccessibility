"""Script descartável: valida que os subsistemas se encaixam de verdade numa
sequência real única -- analyze_page -> fix_and_zip_files -> export_xlsx ->
export_checklist_pdf -> run_remote_test (cypress cloud) -> create_github_issue
-- tudo contra Ollama Cloud tier "alto" e APIs reais (Postman/Cypress/GitHub),
sem passar pelo chat conversacional (chama os handlers direto, então sem o
custo de tokens/tempo de decisão do modelo -- foco em "os sistemas se
encaixam", não em comportamento conversacional, que já foi validado à parte).

Uso: python tests/backend/real_llm/live_runs/run_e2e_integration_full.py
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

os.environ["LLM_PROVIDER"] = "ollama-cloud"
os.environ.pop("LLM_MODEL", None)
os.environ["A11Y_RESPONSE_CACHE_ENABLED"] = "false"

from backend.src.config.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from backend.src.security.secret_store import load_secrets_into_environment  # noqa: E402

load_secrets_into_environment()

from backend.src.services import session_context  # noqa: E402

TARGET_URL = "https://dequeuniversity.com/demo/mars/"
CONVERSATION_ID = "e2e-integration-full"

OUT_LOG = Path(__file__).parent / "log_e2e_integration_full.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_integration_full.json"

steps: list[dict] = []


def log(fh, line: str):
    print(line)
    fh.write(line + "\n")
    fh.flush()


def record(fh, name: str, start: float, ok: bool, detail: str):
    elapsed = round(time.monotonic() - start, 1)
    steps.append({"step": name, "ok": ok, "elapsed_s": elapsed, "detail": detail[:500]})
    log(fh, f"[{'OK' if ok else 'FALHA'}] {name} ({elapsed}s): {detail[:300]}")


async def main():
    token = session_context.set_current_session(CONVERSATION_ID)
    with open(OUT_LOG, "w", encoding="utf-8") as fh:
        try:
            # 1. analyze_page (real, URL)
            from backend.src.services.chat_tools import analyze_page
            t = time.monotonic()
            res = json.loads(await asyncio.to_thread(analyze_page, {"url": TARGET_URL}))
            record(fh, "analyze_page", t, "error" not in res, json.dumps(res)[:400])

            # 2. fix_and_zip_files (sem files -- usa o cache da análise por URL, Fix #1)
            from backend.src.services.chat_tools import fix_and_zip_files
            t = time.monotonic()
            res = json.loads(await asyncio.to_thread(fix_and_zip_files, {}))
            record(fh, "fix_and_zip_files (via cache, sem files)", t, "download_url" in res, json.dumps(res)[:400])

            # 3. export_xlsx (link real)
            from backend.src.services.chat_tools import export_xlsx
            t = time.monotonic()
            res = json.loads(await asyncio.to_thread(export_xlsx, {}))
            record(fh, "export_xlsx", t, "download_url" in res, json.dumps(res)[:400])

            # 4. export_checklist_pdf (link real -- gera sob demanda no GET)
            from backend.src.services.chat_tools import export_checklist_pdf_tool
            t = time.monotonic()
            res = json.loads(await asyncio.to_thread(export_checklist_pdf_tool, {}))
            record(fh, "export_checklist_pdf_tool", t, "download_url" in res, json.dumps(res)[:400])

            # 4b. bate no endpoint de verdade pra confirmar que o PDF gera sem erro fim-a-fim
            from fastapi.testclient import TestClient

            from backend.src.main import app
            t = time.monotonic()
            with TestClient(app) as client:
                http_res = client.get("/export/last_checklist_pdf")
            ok = http_res.status_code == 200 and http_res.headers.get("content-type") == "application/pdf"
            record(fh, "GET /export/last_checklist_pdf (fim-a-fim)", t, ok, f"status={http_res.status_code} content-type={http_res.headers.get('content-type')} bytes={len(http_res.content)}")

            # 5. run_remote_test real (cypress, nuvem)
            from backend.src.services.remote_runners import run_remote_cypress_simulation
            t = time.monotonic()
            res = await run_remote_cypress_simulation(TARGET_URL, location="cloud")
            record(fh, "run_remote_test (cypress cloud, axe-core real)", t, res.get("status") == "ok", json.dumps({k: v for k, v in res.items() if k != "critical_issues"}))

            # 6. create_github_issue real, a partir de um achado real do passo 5
            from backend.src.services.github_service import create_github_issue
            t = time.monotonic()
            gh_res = create_github_issue(
                title="[A11Y] Validação de integração completa (analyze->fix->export->remote_test->github)",
                body=(
                    "Issue gerada automaticamente pela suíte de integração real (2026-08-10) "
                    f"para confirmar que os subsistemas se encaixam de ponta a ponta. Página: {TARGET_URL}. "
                    f"Violações reais via axe-core: {res.get('total_violations')}."
                ),
                repo_owner="Blindex09",
                repo_name="qaaccessibility",
            )
            record(fh, "create_github_issue", t, gh_res.get("status") == "created", json.dumps(gh_res))

        finally:
            session_context.reset_current_session(token)

        log(fh, "\n" + "=" * 78)
        log(fh, "RESUMO DA INTEGRAÇÃO")
        log(fh, "=" * 78)
        for s in steps:
            log(fh, f"- {'OK' if s['ok'] else 'FALHA'} {s['step']} ({s['elapsed_s']}s)")
        all_ok = all(s["ok"] for s in steps)
        log(fh, f"\nTODOS OS PASSOS OK: {all_ok}")

    OUT_JSON.write_text(json.dumps(steps, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLog: {OUT_LOG}")
    print(f"JSON: {OUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
