"""Repete ao vivo, em qualquer provedor (padrão Ollama Cloud, modo Alto), os cenários dos módulos 1 a 3 e compara com o medido.

Serve para uma pessoa (ou um agente) provar que uma correção feita depois não estragou o que já tinha sido provado.
Roda pela mesma rota do navegador (`POST /chat/stream`) contra o backend em http://127.0.0.1:8001.

Regras:
- Só confere FATOS: a resposta terminou, não veio erro, o custo ficou perto do medido (margem larga, porque o raciocínio dos
  modelos varia), não há emoji nem tabela na resposta, o ZIP foi extraído sem erro. Se a resposta é boa é julgamento, e fica
  para quem lê a saída.
- Troca para o provedor pedido (Alto) e devolve o que estava configurado ao terminar, mesmo se falhar. A chave do provedor tem
  de estar guardada no cofre (uma por provedor).
- No Ollama Cloud o custo é conferido com margem (os números medidos são dele). Em outro provedor o custo é só informado ao lado
  do medido no Ollama, e só os fatos objetivos reprovam. Sem cota (erro 429), diz isso e sai sem marcar nada como quebrado.

Uso:  .venv/Scripts/python scripts/verify_live_modules_1_to_3.py [--provider gemini] [--only m1|m2|m3]
"""

import argparse
import base64
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "http://127.0.0.1:8001"
ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "uvicorn.out"
sys.stdout.reconfigure(encoding="utf-8")

# Medido ao vivo (docs/modules): tokens do turno inteiro. A margem (x1,6) cobre a variação do raciocínio e do modelo escolhido.
MARGIN = 1.6
PICTOGRAPH = re.compile("[\U0001F000-\U0001FAFF☀-➿⭐⭕️‍]")

LOJA = {
    "lojasol/index.html": (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head><body>'
        '<img src="logo.png"><h1>Loja Sol</h1><h4>Ofertas da semana</h4><form><input type="text" placeholder="Seu e-mail">'
        '<div class="btn" onclick="assinar()">Assinar</div></form><p>Veja mais produtos <a href="#">clique aqui</a></p>'
        '<script src="app.js"></script></body></html>'
    ),
    "lojasol/sobre.html": (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Sobre a Loja Sol</title></head><body><main>'
        "<h1>Sobre</h1><table><tr><td>Ano</td><td>Fato</td></tr><tr><td>2010</td><td>Fundação</td></tr></table></main></body></html>"
    ),
    "lojasol/style.css": ".btn { color: #aaaaaa; background: #ffffff; padding: 4px; }\n:focus { outline: none; }\n",
    "lojasol/app.js": "function assinar() { alert('Obrigado por assinar'); }\n",
}


def zip_attachment() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in LOJA.items():
            archive.writestr(name, body)
    return f"=== lojasol.zip ===\n{base64.b64encode(buffer.getvalue()).decode()}\n"


# (id, módulo, mensagem, tokens medidos, o que mais conferir)
SCENARIOS = [
    ("m1-pergunta-curta", "m1", "Em duas frases, o que é o critério 1.4.3 do WCAG? (verificação {n})", 25_400, {}),
    ("m1-fora-do-nicho", "m1", "Pode me passar uma receita de bolo de cenoura? (verificação {n})", 2_300, {"max_calls": 2}),
    ("m1-pedido-vago", "m1", "analisa isso (verificação {n})", 2_300, {"max_calls": 2}),
    (
        "m2-url-com-erros",
        "m2",
        "Quais problemas de acessibilidade tem nesta página? https://www.w3.org/WAI/demos/bad/before/home.html (verificação {n})",
        211_000,
        {"no_pictographs": True, "no_tables": True},
    ),
    (
        "m3-zip-anexado",
        "m3",
        "Mando aqui o pacote do site da loja. O que precisa mudar para ficar acessível, arquivo por arquivo? (verificação {n})\n\n"
        + zip_attachment(),
        298_000,
        {"no_pictographs": True, "no_tables": True, "no_extraction_error": True},
    ),
]


def api(path: str, body: dict | None = None, method: str | None = None, timeout: int = 60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method=method or ("POST" if body is not None else "GET"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def last_cost() -> dict | None:
    if not LOG.exists():
        return None
    last = None
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[Custo] POST /chat/stream" in line:
            last = line
    return json.loads(last.split("/chat/stream ", 1)[1]) if last else None


def count_costs() -> int:
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines() if "[Custo] POST /chat/stream" in line)


def run_turn(message: str) -> dict:
    body = json.dumps({"message": message, "history": []}).encode()
    request = urllib.request.Request(BASE + "/chat/stream", data=body, headers={"Content-Type": "application/json"})
    text, done, error, waits = [], False, None, 0
    started = time.time()
    with urllib.request.urlopen(request, timeout=3600) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "token":
                text.append(event.get("text", ""))
            elif kind == "waiting_provider":
                waits += 1
            elif kind == "error":
                error = event.get("error")
            elif kind == "done":
                done = True
                if event.get("final") and not text:
                    text.append(event["final"])
    return {"text": "".join(text), "done": done, "error": error, "waits": waits, "seconds": round(time.time() - started)}


def ollama_has_quota() -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT))
    import ollama

    from backend.src.security.secret_store import load_provider_key, load_secrets

    key = load_provider_key("LLM", "ollama-cloud") or load_secrets().get("LLM_API_KEY")
    if not key:
        return False, "sem chave do Ollama Cloud no cofre"
    try:
        client = ollama.Client(host="https://ollama.com", headers={"Authorization": f"Bearer {key}"}, timeout=60)
        client.chat(model="gpt-oss:20b", messages=[{"role": "user", "content": "ok"}], think=False)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["m1", "m2", "m3"])
    parser.add_argument("--provider", default="ollama-cloud")
    args = parser.parse_args()
    only, provider = args.only, args.provider
    strict_cost = provider == "ollama-cloud"

    if strict_cost:
        has_quota, why = ollama_has_quota()
        if not has_quota:
            print(f"NÃO EXECUTADO: o Ollama Cloud não respondeu ({why}). Nada foi marcado como quebrado.")
            return 2
    else:
        sys.path.insert(0, str(ROOT))
        from backend.src.security.secret_store import load_provider_key

        if not load_provider_key("LLM", provider):
            print(f"NÃO EXECUTADO: não há chave guardada para {provider}. Coloque-a nas Configurações.")
            return 2

    before = api("/settings/")
    print(f"Configuração atual (será restaurada): provedor={before['llm_provider']}, modelo={before['llm_model']}")
    api("/settings/", {"llm_provider": provider, "llm_model": "alto"})
    failures = 0
    try:
        for index, (name, module, template, baseline, checks) in enumerate(SCENARIOS, 1):
            if only and module != only:
                continue
            seen = count_costs()
            result = run_turn(template.replace("{n}", str(int(time.time()) % 100000 + index)))
            time.sleep(1)
            cost = last_cost() if count_costs() > seen else None
            problems = []
            if not result["done"]:
                problems.append("o turno não terminou")
            if result["error"]:
                problems.append(f"veio erro: {str(result['error'])[:120]}")
            if not result["text"].strip():
                problems.append("resposta vazia")
            if cost is None:
                problems.append("sem registro de custo no log")
            else:
                if strict_cost and cost["total_tokens"] > baseline * MARGIN:
                    problems.append(f"custo {cost['total_tokens']} acima de {int(baseline * MARGIN)} (medido {baseline})")
                if "max_calls" in checks and cost["calls"] > checks["max_calls"]:
                    problems.append(f"{cost['calls']} chamadas, esperado no máximo {checks['max_calls']}")
            if checks.get("no_pictographs") and PICTOGRAPH.search(result["text"]):
                problems.append("a resposta tem emoji")
            if checks.get("no_tables") and re.search(r"^\s*\|.*\|\s*$", result["text"], re.M):
                problems.append("a resposta tem tabela")
            if checks.get("no_extraction_error") and "extração de arquivos" in result["text"]:
                problems.append("apareceu erro de extração do ZIP")
            status = "OK " if not problems else "FALHOU"
            failures += bool(problems)
            tokens = cost["total_tokens"] if cost else "?"
            calls = cost["calls"] if cost else "?"
            print(f"[{status}] {name}: {tokens} tokens (medido {baseline}), {calls} chamadas, {result['seconds']}s, avisos de espera={result['waits']}")
            for problem in problems:
                print(f"         - {problem}")
    finally:
        api(
            "/settings/",
            {"llm_provider": before["llm_provider"], "llm_model": before.get("llm_model") or ""},
        )
        print(f"Configuração restaurada: provedor={before['llm_provider']}.")
    print("RESULTADO:", "tudo igual ao medido" if not failures else f"{failures} cenário(s) fora do medido")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
