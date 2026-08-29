"""Script descartável: E2E conversacional real cobrindo TODOS os runners
remotos -- Cypress (nuvem E local, com instalação real via npm quando ainda
não está instalado), Postman/Newman real, Selenium -- via chat de verdade
(stream_chat), contra Ollama Cloud real (API nativa, pós-correção de
2026-08-10), sem mock. Cada decisão de local/nuvem é respondida via clarify
de verdade, exatamente como um usuário real responderia.

Uso: python tests/backend/real_llm/live_runs/run_e2e_remote_testing_full.py
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

OUT_LOG = Path(__file__).parent / "log_e2e_remote_testing_full.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_remote_testing_full.json"

TARGET_URL = "https://dequeuniversity.com/demo/mars/"

TURNS = [
    ("1. Análise rápida", f"Analisa essa página: {TARGET_URL}"),
    ("2. Cypress na nuvem", "Roda um teste real com Cypress nessa página."),
    ("3. Cypress na nuvem -- confirma escolha", "Pode rodar na nuvem."),
    ("4. Cypress local (vai pedir instalação)", "Agora roda o mesmo teste, mas com Cypress local dessa vez."),
    ("5. Cypress local -- confirma local + instalar", "Roda localmente, e sim, pode instalar o Cypress de verdade se não tiver."),
    ("6. Postman/Newman real", "Agora roda um teste de contrato de API real com Postman nessa mesma URL."),
    ("7. Selenium", "Por último, roda um teste de acessibilidade real com Selenium nessa página."),
    ("8. Selenium -- confirma nuvem (mais rápido)", "Pode rodar na nuvem, sem precisar instalar driver local."),
]

# Respostas automáticas quando o clarify perguntar 'onde rodar' -- escolhas
# REAIS que um usuário daria, na ordem em que os clarifies devem aparecer.
CLARIFY_ANSWERS_BY_TOOL_HINT = {
    "nuvem": "Rodar na nuvem",
    "local": "Executar localmente uma vez",
    "instal": "Sim, pode instalar",
}

CONVERSATION_ID = "e2e-remote-testing-full-v1"


def log(fh, line: str):
    print(line)
    fh.write(line + "\n")
    fh.flush()


def _pick_clarify_answer(question: str, options: list[str] | None) -> str:
    """Escolhe a resposta mais adequada dada as opções reais oferecidas pelo
    clarify -- nunca aprova cegamente 'Aprovar', escolhe a opção que combina
    com o que o roteiro deste turno realmente quer (nuvem/local/instalar)."""
    q_lower = question.lower()
    opts = options or []
    for opt in opts:
        opt_lower = opt.lower()
        if ("nuvem" in opt_lower or "cloud" in opt_lower) and ("nuvem" in q_lower or "cloud" in q_lower):
            return opt
    for opt in opts:
        if "instal" in opt.lower():
            return opt
    for opt in opts:
        if "local" in opt.lower() and "vez" in opt.lower():
            return opt
    for opt in opts:
        if "aprova" in opt.lower():
            return opt
    return opts[0] if opts else "Aprovar"


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
            choices = event.get("choices")
            rid = event.get("request_id")
            answer = _pick_clarify_answer(question, choices)
            log(fh, f"  [CLARIFY] {question[:250]}")
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
