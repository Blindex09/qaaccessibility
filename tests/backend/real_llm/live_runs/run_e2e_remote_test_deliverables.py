"""Script descartável: E2E conversacional real cobrindo Cypress (nuvem e
local), Postman/Newman e Selenium -- e, depois de cada um, pede planilha,
checklist e preview ao vivo, confirmando que os resultados REAIS desses
runners alimentam last_analysis_store/last_analyzed_content_store (achado
real corrigido em 2026-08-11) e que os downloads/preview funcionam de
ponta a ponta contra o modelo real (API nativa do Ollama).

Uso: python tests/backend/real_llm/live_runs/run_e2e_remote_test_deliverables.py
"""
import asyncio
import json
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

OUT_LOG = Path(__file__).parent / "log_e2e_remote_test_deliverables.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_remote_test_deliverables.json"

TARGET_URL = "https://dequeuniversity.com/demo/mars/"

TURNS = [
    # (label, mensagem, hint de local/nuvem para ESTE turno se um clarify pedir a decisão)
    ("1. Cypress na nuvem", f"Roda um teste real de acessibilidade com Cypress nessa página: {TARGET_URL}", "cloud"),
    ("2. Confirma nuvem", "Pode rodar na nuvem.", "cloud"),
    ("3. Planilha a partir do Cypress", "Agora gera a planilha Excel com esses resultados do Cypress.", None),
    ("4. Checklist a partir do Cypress", "Gera também o checklist estruturado em PDF.", None),
    ("5. Corrige e mostra o preview", "Corrige os problemas encontrados pelo Cypress e me mostra o preview ao vivo comparando antes e depois.", None),
    ("6. Cypress local", "Agora roda o mesmo teste, mas com Cypress local dessa vez.", "local"),
    ("7. Confirma local", "Executar localmente uma vez.", "local"),
    ("8. Planilha a partir do Cypress local", "Gera a planilha Excel de novo, agora com os resultados do teste local.", None),
    ("9. Selenium", "Roda um teste real com Selenium nessa mesma página.", "cloud"),
    ("10. Confirma nuvem pro Selenium", "Pode rodar na nuvem.", "cloud"),
    ("11. Checklist a partir do Selenium", "Gera o checklist em PDF com os resultados do Selenium.", None),
    ("12. Postman", "Por último, roda um teste de contrato de API com Postman nessa URL.", None),
]

CONVERSATION_ID = "e2e-remote-test-deliverables-v1"


def log(fh, line: str):
    print(line)
    fh.write(line + "\n")
    fh.flush()


def _pick_clarify_answer(choices: list[str] | None, location_hint: str | None) -> str:
    """Escolhe a opção certa dentre as choices REAIS oferecidas pelo clarify,
    usando o hint explícito do turno atual (não tenta adivinhar pelo texto da
    pergunta -- um clarify neutro tipo "onde você quer executar?" não
    menciona "nuvem" na pergunta em si, só nas opções)."""
    opts = choices or []
    if location_hint == "cloud":
        for opt in opts:
            if "nuvem" in opt.lower():
                return opt
    if location_hint == "local":
        for opt in opts:
            if "local" in opt.lower() and "vez" in opt.lower():
                return opt
    for opt in opts:
        if "aprova" in opt.lower():
            return opt
    return opts[0] if opts else "Aprovar"


async def run_turn(fh, label: str, user_message: str, history: list[dict[str, str]], location_hint: str | None):
    log(fh, "\n" + "=" * 78)
    log(fh, f"TURNO: {label}")
    log(fh, f"USER: {user_message}")
    log(fh, "-" * 78)

    tools_called: list[str] = []
    final_text = ""
    live_preview_marker_seen = False
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
            choices = event.get("choices")
            rid = event.get("request_id")
            answer = _pick_clarify_answer(choices, location_hint)
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
    if "[LIVE_PREVIEW:" in final_text:
        live_preview_marker_seen = True
    log(fh, f"\nASSISTANT ({elapsed:.1f}s):\n{final_text}\n")

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": final_text})

    return {
        "label": label,
        "tools": tools_called,
        "elapsed_s": round(elapsed, 1),
        "final_text": final_text,
        "live_preview_marker_seen": live_preview_marker_seen,
    }


async def main():
    from backend.src.services import chat_history_store, last_analysis_store, last_analyzed_content_store
    chat_history_store._sessions.pop(CONVERSATION_ID, None)
    last_analysis_store._sessions.pop(CONVERSATION_ID, None)
    last_analyzed_content_store._sessions.pop(CONVERSATION_ID, None)
    from backend.src.services import session_context
    session_context.set_current_session(CONVERSATION_ID)

    results = []
    history: list[dict[str, str]] = []
    with open(OUT_LOG, "w", encoding="utf-8") as fh:
        for label, msg, location_hint in TURNS:
            res = await run_turn(fh, label, msg, history, location_hint)
            results.append(res)

        log(fh, "\n" + "=" * 78)
        log(fh, "RESUMO")
        log(fh, "=" * 78)
        for r in results:
            log(fh, f"- {r['label']}: tools={r['tools']} preview_marker={r['live_preview_marker_seen']} ({r['elapsed_s']}s)")
        log(fh, f"\nhistórico persistido: {len(history)} mensagens")

    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLog completo: {OUT_LOG}")
    print(f"JSON: {OUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
