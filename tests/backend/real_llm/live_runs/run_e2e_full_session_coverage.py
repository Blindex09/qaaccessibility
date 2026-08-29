"""Script descartável: E2E conversacional real, UMA conversa contínua, com
chamadas REAIS de LLM (sem mock), cobrindo TODAS as funcionalidades
implementadas nesta sessão (2026-08-11/12), do começo ao fim:

  1. Analisar uma página real (exercita: fan-out de especialistas, delegação
     dinâmica agente-a-agente, retry com esforço reduzido, gap-research
     automático, pipeline_graph explícito -- tudo dentro do orchestrator).
  2. Testar a mesma página nos 3 motores de navegador reais (cross-browser
     real via Playwright local).
  3. Corrigir os problemas encontrados.
  4. Gerar o checklist estruturado.
  5. Exportar o checklist em PDF.
  6. Fazer uma pergunta normativa real (exercita deep_research + busca web
     nativa do provider em paralelo com tavily/exa).
  7. Tentar corrigir um projeto local SEM nome de acessibilidade -- espera
     recusa amigável (guard de escopo).
  8. Tentar o MESMO projeto, mas apontando pro diretório COM nome de
     acessibilidade -- espera sucesso real.
  9. Reanalisar a MESMA URL do passo 1 -- exercita o diff de regressão
     (shift-right sob demanda, url_scan_history_store).

Uso: python tests/backend/real_llm/live_runs/run_e2e_full_session_coverage.py
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

OUT_LOG = Path(__file__).parent / "log_e2e_full_session_coverage.txt"
OUT_JSON = Path(__file__).parent / "out_e2e_full_session_coverage.json"
CONVERSATION_ID = "e2e-full-session-coverage-v1"

_TMP_ROOT = Path(os.path.abspath("/tmp/e2e_scope_test"))
_GENERIC_DIR = str(_TMP_ROOT / "loja-generica")
_A11Y_DIR = str(_TMP_ROOT / "projeto-acessibilidade")

TARGET_URL = "https://dequeuniversity.com/demo/mars/"

TURNS = [
    ("1. Análise real da página", f"Analisa essa página pra mim: {TARGET_URL}"),
    ("1b. Confirmação do plano", "Aprovo o plano, pode rodar a análise completa agora."),
    ("2. Cross-browser real", "Testa essa mesma página nos 3 motores de navegador (Chrome, Firefox e Safari/WebKit) pra ver se o comportamento muda entre eles."),
    ("3. Correção direta", "Corrige os problemas que você encontrou e gera o zip."),
    ("3b. Confirmação da correção", "Aplica as correções agora, pode gerar o zip."),
    ("4. Checklist estruturado", "Agora gera o checklist estruturado dessa análise."),
    ("5. Checklist em PDF", "Exporta esse checklist em PDF acessível."),
    ("6. Pergunta normativa real", "Tenho uma dúvida técnica normativa: qual é exatamente o algoritmo AccName do W3C pra calcular o nome acessível de um elemento, e onde isso é definido oficialmente? Pesquisa e me cita a fonte."),
    ("7. Projeto local SEM nome de acessibilidade (espera recusa)", f"Corrige os arquivos do projeto que está em {_GENERIC_DIR}"),
    ("7b. Confirmação (espera recusa mesmo confirmando)", "Sim, aplica as correções nesse projeto."),
    ("8. Projeto local COM nome de acessibilidade (espera sucesso)", f"Agora corrige os arquivos do projeto que está em {_A11Y_DIR}"),
    ("8b. Confirmação da correção do projeto acessível", "Sim, aplica as correções nesse projeto."),
    ("9. Reanálise da mesma URL (shift-right)", f"Analisa de novo essa página: {TARGET_URL} -- quero saber se algo mudou desde a última vez."),
    ("9b. Confirmação do plano de reanálise", "Aprovo o plano, pode rodar."),
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
