"""Script descartável: E2E conversacional real, FOCADO, testando só o guard de
escopo local (backend/src/services/local_project_guard.py) via chat completo
-- não a página de análise inteira, pra ser rápido. Separado do
run_e2e_full_session_coverage.py porque aquele script bateu no timeout de
3000s antes de chegar nesses turnos (turnos de checklist com retry real
consumiram ~1870s sozinhos).

Cobre:
  1. Corrigir um projeto local SEM nome de acessibilidade -- espera recusa
     amigável, mesmo com confirmação explícita.
  2. Corrigir o MESMO projeto, mas apontando pro diretório COM nome de
     acessibilidade -- espera sucesso real.

Uso: python tests/backend/real_llm/live_runs/run_local_scope_guard_e2e.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

os.environ["LLM_PROVIDER"] = "ollama-cloud"
os.environ.pop("LLM_MODEL", None)
os.environ["A11Y_RESPONSE_CACHE_ENABLED"] = "false"

from backend.src.config.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from backend.src.security.secret_store import load_secrets_into_environment  # noqa: E402

load_secrets_into_environment()

from backend.src.services import chat_progress  # noqa: E402
from backend.src.services.chat_runtime import stream_chat  # noqa: E402

OUT_LOG = Path(__file__).parent / "log_local_scope_guard_e2e.txt"
CONVERSATION_ID = "e2e-local-scope-guard-v1"

_TMP_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "e2e_scope_test"
_GENERIC_DIR = str(_TMP_ROOT / "loja-generica")
_A11Y_DIR = str(_TMP_ROOT / "projeto-acessibilidade")

TURNS = [
    ("1. Projeto SEM nome de acessibilidade (espera recusa)", f"Corrige os arquivos do projeto que está em {_GENERIC_DIR}"),
    ("1b. Confirmação (espera recusa mesmo confirmando)", "Sim, aplica as correções nesse projeto."),
    ("2. Projeto COM nome de acessibilidade (espera sucesso)", f"Agora corrige os arquivos do projeto que está em {_A11Y_DIR}"),
    ("2b. Confirmação da correção do projeto acessível", "Sim, aplica as correções nesse projeto."),
]


def log(fh, line: str):
    print(line)
    fh.write(line + "\n")
    fh.flush()


async def run_turn(fh, label: str, user_message: str, history: list[dict[str, str]]):
    log(fh, "\n" + "=" * 78)
    log(fh, f"TURNO: {label}")
    log(fh, f"USER: {user_message}")
    log(fh, "-" * 78)

    tools_called: list[str] = []
    final_text = ""
    start = time.monotonic()

    async for event in stream_chat(user_message, history=history, conversation_id=CONVERSATION_ID):
        etype = event.get("type")
        if etype == "tool_start":
            name = event.get("name", "")
            tools_called.append(name)
            log(fh, f"  [TOOL_START] {name}")
        elif etype == "tool_result":
            log(fh, f"  [TOOL_RESULT] {event.get('name', '')} summary={event.get('result_summary')}")
        elif etype == "clarify":
            question = event.get("question", "")
            rid = event.get("request_id")
            log(fh, f"  [CLARIFY] {question[:300]}")
            log(fh, "  -> auto-aprovando ('Aprovar')")
            chat_progress.answer_clarify(rid, "Aprovar")
        elif etype == "phase":
            log(fh, f"  [AGENT] {event.get('text', '')}")
        elif etype == "error":
            log(fh, f"  [ERROR] {event.get('error', '')}")
        elif etype == "done":
            final_text = event.get("final", "")

    elapsed = time.monotonic() - start
    log(fh, f"\nASSISTANT ({elapsed:.1f}s):\n{final_text}\n")

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": final_text})

    return {"label": label, "tools": tools_called, "elapsed_s": round(elapsed, 1)}


async def main():
    from backend.src.services import chat_history_store
    chat_history_store._sessions.pop(CONVERSATION_ID, None)

    results = []
    history: list[dict[str, str]] = []
    with open(OUT_LOG, "w", encoding="utf-8") as fh:
        for label, msg in TURNS:
            res = await run_turn(fh, label, msg, history)
            results.append(res)

        log(fh, "\n" + "=" * 78)
        log(fh, "RESUMO")
        log(fh, "=" * 78)
        for r in results:
            log(fh, f"- {r['label']}: tools={r['tools']} ({r['elapsed_s']}s)")

    print(f"\nLog completo: {OUT_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
