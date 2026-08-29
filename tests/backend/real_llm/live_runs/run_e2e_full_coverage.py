"""Script descartável: E2E conversacional real com cenários NOVOS (2026-08-10,
3a rodada) -- cobre ferramentas que as rodadas anteriores não exercitaram ao
vivo: analyze_site (crawl multi-página), undo_last_fix, generate_vpat,
generate_accessibility_statement (com dados reais de organização, não
placeholder) + export_accessibility_statement_pdf, generate_test_suite.
Contra Ollama Cloud tier "alto", sem mock.

Uso: python tests/backend/real_llm/live_runs/run_e2e_full_coverage.py
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

from backend.src.services import chat_progress  # noqa: E402
from backend.src.services.chat_runtime import stream_chat  # noqa: E402

OUT_LOG = Path(__file__).parent / "log_e2e_full_coverage.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_full_coverage.json"

TURNS = [
    ("1. Auditoria de site inteiro (multi-página)", "Preciso auditar o site inteiro, não só uma página: https://dequeuniversity.com/demo/mars/ -- pega até 3 páginas do mesmo domínio."),
    ("2. Correção direta", "Corrige os problemas que encontrou e gera o zip."),
    ("3. Desfazer a correção", "Na verdade desfaz essa correção, quero comparar com o time antes de aplicar."),
    ("4. VPAT completo", "Gera o VPAT WCAG 2.2 completo dessa auditoria. O produto se chama 'MarsCommuter Web'."),
    ("5. Declaração de acessibilidade com dados reais", "Agora gera a declaração de acessibilidade pública pra publicarmos no site. A organização é 'MarsCommuter Inc', o e-mail de contato é a11y@marscommuter.example.com e o telefone é +1 555-0142."),
    ("6. Declaração em PDF", "Perfeito, agora gera essa declaração em PDF pra eu publicar."),
    ("7. Suíte de testes para CI", "Por último, gera a suíte de testes automatizados Playwright + axe-core pro nosso CI pegar regressões."),
]

CONVERSATION_ID = "e2e-full-coverage-v1"


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
            log(fh, f"  [TOOL_RESULT] {event.get('name', '')}")
        elif etype == "clarify":
            question = event.get("question", "")
            rid = event.get("request_id")
            log(fh, f"  [CLARIFY] {question[:200]}")
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

    return {
        "label": label,
        "tools": tools_called,
        "elapsed_s": round(elapsed, 1),
        "final_text": final_text,
    }


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
        log(fh, f"\nhistórico persistido: {len(history)} mensagens")

    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLog completo: {OUT_LOG}")
    print(f"JSON: {OUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
