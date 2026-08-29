"""Script descartável: verifica repetidamente (N vezes) que o pedido de
auditoria multi-página dispara um clarify TOOL real (rule 12), não um plano
escrito como texto puro com "Opções: [...]" -- achado real na rodada de
cobertura E2E (2026-08-10, 3a rodada, run_e2e_full_coverage.py).

Uso: python tests/backend/real_llm/live_runs/run_clarify_regression_check.py
"""
import asyncio
import os
import sys
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

from backend.src.services import chat_history_store, chat_progress  # noqa: E402
from backend.src.services.chat_runtime import stream_chat  # noqa: E402

MESSAGE = "Preciso auditar o site inteiro, não só uma página: https://dequeuniversity.com/demo/mars/ -- pega até 3 páginas do mesmo domínio."
N_RUNS = 4


async def run_once(i: int) -> bool:
    conv_id = f"clarify-regression-check-{i}"
    chat_history_store._sessions.pop(conv_id, None)

    used_real_clarify_tool = False
    final_text = ""

    async for event in stream_chat(MESSAGE, history=[], conversation_id=conv_id):
        etype = event.get("type")
        if etype == "clarify":
            used_real_clarify_tool = True
            rid = event.get("request_id")
            chat_progress.answer_clarify(rid, "Aprovar Plano")
        elif etype == "done":
            final_text = event.get("final", "")

    contains_fake_options_text = "Opções:" in final_text and "[" in final_text
    print(f"--- run {i} ---")
    print(f"  used_real_clarify_tool = {used_real_clarify_tool}")
    print(f"  final_text contains fake 'Opções:' list = {contains_fake_options_text}")
    if not used_real_clarify_tool:
        print(f"  final_text: {final_text[:300]}")
    return used_real_clarify_tool and not contains_fake_options_text


async def main():
    results = []
    for i in range(1, N_RUNS + 1):
        ok = await run_once(i)
        results.append(ok)
    print(f"\n{sum(results)}/{N_RUNS} runs used the real clarify tool (no fake text options list)")


if __name__ == "__main__":
    asyncio.run(main())
