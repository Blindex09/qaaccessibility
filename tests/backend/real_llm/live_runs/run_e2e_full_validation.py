"""Script descartável: re-validação E2E conversacional completa (2026-08-10,
2a rodada) -- ambíguo + direto + entregáveis, depois das correções aplicadas
na 1a rodada (retry em resposta vazia em qualquer iteração, fallback de
conteúdo placeholder, regra de cache reforçada contra reanálise repetida).
Contra Ollama Cloud tier "alto", sem mock.

Uso: python tests/backend/real_llm/live_runs/run_e2e_full_validation.py
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

OUT_LOG = Path(__file__).parent / "log_e2e_full_validation_v2.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_full_validation_v2.json"

TURNS = [
    ("1. Pedido AMBÍGUO/indireto", "Oi, será que dá pra você dar uma olhada nesse site aqui e ver se ele tá bom pra quem usa leitor de tela? https://dequeuniversity.com/demo/mars/"),
    ("2. Pedido DIRETO de correção", "Corrige os problemas de acessibilidade que você achou e gera um zip com o resultado."),
    ("3. Pedido DIRETO de planilha", "Agora gera uma planilha com os resultados dessa análise."),
    ("4. Checklist em PDF + salvar local ou link", "Quero o checklist de acessibilidade em PDF. Salva no meu computador, ou se não der, me manda um link pra eu baixar."),
    ("5. Ver o preview lado a lado", "Mostra o preview ao vivo comparando antes e depois da correção."),
]

CONVERSATION_ID = "e2e-full-validation-v2"


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
