"""Script descartável: confirma que, com o Cypress JÁ instalado localmente
(pela rodada anterior), pedir 'local' via chat roda o binário real sem
precisar reinstalar -- fecha o loop detecção -> instalar -> usar de verdade.

Uso: python tests/backend/real_llm/live_runs/run_cypress_local_installed_check.py
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

TARGET_URL = "https://dequeuniversity.com/demo/mars/"
CONVERSATION_ID = "cypress-local-installed-check-v1"

OUT_LOG = Path(__file__).parent / "log_cypress_local_installed_check.txt"


def log(fh, line: str):
    print(line)
    fh.write(line + "\n")
    fh.flush()


def _pick_clarify_answer(question: str, choices: list[str] | None) -> str:
    opts = choices or []
    for opt in opts:
        if "local" in opt.lower():
            return opt
    for opt in opts:
        if "aprova" in opt.lower():
            return opt
    return opts[0] if opts else "Aprovar"


async def main():
    from backend.src.services import chat_history_store
    chat_history_store._sessions.pop(CONVERSATION_ID, None)

    history: list[dict[str, str]] = []
    user_message = f"Roda um teste real de acessibilidade com Cypress LOCAL (não na nuvem) nessa página: {TARGET_URL}"

    with open(OUT_LOG, "w", encoding="utf-8") as fh:
        log(fh, f"USER: {user_message}")
        log(fh, "-" * 78)

        tools_called = []
        final_text = ""
        start = time.monotonic()

        async for event in stream_chat(user_message, history=history, conversation_id=CONVERSATION_ID):
            etype = event.get("type")
            if etype == "tool_start":
                tools_called.append(event.get("name", ""))
                log(fh, f"  [TOOL_START] {event.get('name', '')}")
            elif etype == "tool_result":
                log(fh, f"  [TOOL_RESULT] {event.get('name', '')}")
            elif etype == "clarify":
                question = event.get("question", "")
                choices = event.get("choices")
                rid = event.get("request_id")
                answer = _pick_clarify_answer(question, choices)
                log(fh, f"  [CLARIFY] {question[:200]}")
                log(fh, f"  [CLARIFY CHOICES] {choices}")
                log(fh, f"  -> respondendo: {answer!r}")
                chat_progress.answer_clarify(rid, answer)
            elif etype == "phase":
                log(fh, f"  [AGENT] {event.get('text', '')}")
            elif etype == "error":
                log(fh, f"  [ERROR] {event.get('error', '')}")
            elif etype == "done":
                final_text = event.get("final", "")

        elapsed = time.monotonic() - start
        log(fh, f"\nASSISTANT ({elapsed:.1f}s):\n{final_text}\n")
        log(fh, f"\ntools_called: {tools_called}")

    print(f"\nLog completo: {OUT_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
