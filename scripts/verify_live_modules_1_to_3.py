"""Repete ao vivo, em qualquer provedor (padrão Ollama Cloud, modo Alto), os cenários dos módulos 1 a 3 e compara com o medido.

Serve para uma pessoa (ou um agente) provar que uma correção feita depois não estragou o que já tinha sido provado.
Roda pela mesma rota do navegador (`POST /chat/stream`) contra o backend em http://127.0.0.1:8001.

Regras:
- Contrato de comportamento, igual para todo provedor: além de custo, confere QUAIS FERRAMENTAS foram chamadas (fato objetivo do fluxo de
  eventos). Pergunta conceitual não chama ferramenta de análise; auditoria de URL e de projeto anexado chama `analyze_page`; ZIP anexado
  nunca chama a descompactação. Foi assim que o Gemini apareceu auditando um ZIP sozinho, sem especialistas, enquanto os modelos do
  Ollama chamavam a ferramenta: o texto da regra dava margem, e o contrato torna a diferença visível em qualquer provedor.
- Só confere FATOS: a resposta terminou, não veio erro, o custo ficou perto do medido (margem larga, porque o raciocínio dos
  modelos varia), não há emoji nem tabela na resposta, o ZIP foi extraído sem erro. Se a resposta é boa é julgamento, e fica
  para quem lê a saída.
- Troca para o provedor pedido (Alto) e devolve o que estava configurado ao terminar, mesmo se falhar. A chave do provedor tem
  de estar guardada no cofre (uma por provedor).
- O custo é conferido com margem contra os números medidos DAQUELE provedor (docs/modules/provedores/evidencias.json). Cenário sem
  número do provedor ainda não reprova por custo: o resultado é só informado e pode ser registrado com --register. Sem cota (erro 429), diz isso e sai sem marcar nada como quebrado.

Uso:  .venv/Scripts/python scripts/verify_live_modules_1_to_3.py [--provider gemini] [--only m1|m2|m3] [--register]
  --register: cenário que passou em tudo atualiza o número de referência do provedor (scripts/update_protections.py).
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


def references(provider: str) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import update_protections

    scenarios = update_protections.load()["provedores"].get(provider, {}).get("cenarios", {})
    return {name: item for name, item in scenarios.items()}
sys.path.insert(0, str(ROOT / "scripts"))
import behavior_judge  # noqa: E402
import live_document_fixtures as docs  # noqa: E402

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
    ("m1-pergunta-curta", "m1", "Em duas frases, o que é o critério 1.4.3 do WCAG? (verificação {n})", 25_400, {"must_not_call": ["analyze_page", "analyze_site", "run_deep_research"], "no_repeat": True, "judge": "tone"}),
    ("m1-fora-do-nicho", "m1", "Pode me passar uma receita de bolo de cenoura? (verificação {n})", 2_300, {"max_calls": 2, "no_repeat": True, "judge": "tone"}),
    ("m1-pedido-vago", "m1", "analisa isso (verificação {n})", 2_300, {"max_calls": 2, "no_repeat": True, "judge": "tone"}),
    (
        "m1-tom-descontraido", "m1", "e aí, tudo bem? me explica rapidinho o que é contraste mínimo no wcag, tipo pra um iniciante (verificação {n})", 2_300,
        {"must_not_call": ["analyze_page", "analyze_site", "run_deep_research"], "no_repeat": True, "judge": "tone"},
    ),
    (
        "m1-tom-formal", "m1", "Prezado assistente, solicito a gentileza de esclarecer em que consiste o critério 1.4.3 das WCAG. Agradeço desde já. (verificação {n})", 2_300,
        {"must_not_call": ["analyze_page", "analyze_site", "run_deep_research"], "no_repeat": True, "judge": "tone"},
    ),
    (
        "m2-url-com-erros",
        "m2",
        "Quais problemas de acessibilidade tem nesta página? https://www.w3.org/WAI/demos/bad/before/home.html (verificação {n})",
        211_000,
        {"no_pictographs": True, "no_tables": True, "must_call": ["analyze_page"], "no_repeat": True, "judge": "tone"},
    ),
    (
        "m2-pedido-estreito",
        "m2",
        "Na página https://www.w3.org/WAI/demos/bad/before/home.html, olhe só o idioma e o texto alternativo das imagens. (verificação {n})",
        106_000,
        {"no_pictographs": True, "no_tables": True, "must_call": ["analyze_page"], "no_repeat": True, "judge": "tone"},
    ),
    (
        "m2-pagina-acessivel",
        "m2",
        "Esta página está acessível? https://www.w3.org/WAI/demos/bad/after/home.html (verificação {n})",
        174_000,
        {"no_pictographs": True, "no_tables": True, "must_call": ["analyze_page"], "no_repeat": True, "judge": "tone"},
    ),
    (
        "m2-url-inexistente",
        "m2",
        "Audite https://este-site-nao-existe-qa-9341.example/ por favor (verificação {n})",
        20_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "judge": "tone"},
    ),
    (
        "m3-zip-anexado",
        "m3",
        "Mando aqui o pacote do site da loja. O que precisa mudar para ficar acessível, arquivo por arquivo? (verificação {n})\n\n"
        + zip_attachment(),
        298_000,
        {"no_pictographs": True, "no_tables": True, "no_extraction_error": True, "must_call": ["analyze_page"], "must_not_call": ["unzip_and_list_files"], "no_repeat": True, "judge": "findings"},
    ),
    (
        "m3-zip-pede-especialistas",
        "m3",
        "Faça a auditoria completa deste projeto com os especialistas de acessibilidade e a revisão sênior, e me traga os achados por arquivo. (verificação {n})\n\n"
        + zip_attachment(),
        298_000,
        {"no_pictographs": True, "no_tables": True, "must_call": ["analyze_page"], "no_repeat": True, "judge": "findings"},
    ),
    (
        "m4-docx", "m4", "Este documento está acessível? O que precisa corrigir? (verificação {n})\n\n" + docs.attach("relatorio.docx", docs.docx_bytes()), 40_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_not_call": ["analyze_page", "analyze_site"], "judge": "findings", "expected": docs.EXPECTED["docx"]},
    ),
    (
        "m4-pptx", "m4", "Este documento está acessível? O que precisa corrigir? (verificação {n})\n\n" + docs.attach("apresentacao.pptx", docs.pptx_bytes()), 40_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_not_call": ["analyze_page", "analyze_site"], "judge": "findings", "expected": docs.EXPECTED["pptx"]},
    ),
    (
        "m4-epub", "m4", "Este documento está acessível? O que precisa corrigir? (verificação {n})\n\n" + docs.attach("livro.epub", docs.epub_bytes()), 40_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_not_call": ["analyze_page", "analyze_site"], "judge": "findings", "expected": docs.EXPECTED["epub"]},
    ),
    (
        "m4-pdf", "m4", "Este documento está acessível? O que precisa corrigir? (verificação {n})\n\n" + docs.attach("relatorio.pdf", docs.pdf_bytes()), 80_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_call": ["analyze_document"], "judge": "findings", "expected": docs.EXPECTED["pdf"]},
    ),
    (
        "m4-xlsx", "m4", "Este documento está acessível? O que precisa corrigir? (verificação {n})\n\n" + docs.attach("vendas.xlsx", docs.xlsx_bytes()), 80_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_call": ["analyze_document"], "judge": "findings", "expected": docs.EXPECTED["xlsx"]},
    ),
    (
        "m4-imagem", "m4", "Esta imagem de banner está acessível? Que texto alternativo você sugere? (verificação {n})\n\n" + docs.attach("banner.png", docs.banner_png()), 20_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_not_call": ["analyze_page", "analyze_site"], "judge": "findings", "expected": docs.EXPECTED["imagem"]},
    ),
    (
        "m4-arquivo-corrompido", "m4", "Veja se este documento está acessível (verificação {n})\n\n" + docs.attach("quebrado.docx", docs.corrupted_docx()), 10_000,
        {"no_pictographs": True, "no_tables": True, "no_repeat": True, "must_not_call": ["analyze_page", "analyze_site"], "judge": "tone"},
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
    text, done, error, waits, tools = [], False, None, 0, []
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
            elif kind == "tool_start":
                tools.append(str(event.get("name")))
            elif kind == "waiting_provider":
                waits += 1
            elif kind == "error":
                error = event.get("error")
            elif kind == "done":
                done = True
                if event.get("final") and not text:
                    text.append(event["final"])
    return {"text": "".join(text), "done": done, "error": error, "waits": waits, "tools": tools, "seconds": round(time.time() - started)}


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
    parser.add_argument("--only", choices=["m1", "m2", "m3", "m4"])
    parser.add_argument("--provider", default="ollama-cloud")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    only, provider = args.only, args.provider
    refs = references(provider)

    if provider == "ollama-cloud":
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

    judge_info = behavior_judge.make_judge_asker(provider)
    print(f"Juiz de tom e de achados: {judge_info[0] if judge_info else 'INDISPONÍVEL (sem outro provedor com chave): esses itens ficam NÃO CONFERIDOS'}")
    before = api("/settings/")
    print(f"Configuração atual (será restaurada): provedor={before['llm_provider']}, modelo={before['llm_model']}")
    api("/settings/", {"llm_provider": provider, "llm_model": "alto"})
    failures = 0
    try:
        for index, (name, module, template, _default_baseline, checks) in enumerate(SCENARIOS, 1):
            reference = refs.get(name)
            baseline = reference["tokens"] if reference else None
            if only and module != only:
                continue
            seen = count_costs()
            sent = template.replace("{n}", str(int(time.time()) % 100000 + index))
            result = run_turn(sent)
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
                if baseline and cost["total_tokens"] > baseline * MARGIN:
                    problems.append(f"custo {cost['total_tokens']} acima de {int(baseline * MARGIN)} (medido {baseline})")
                if "max_calls" in checks and cost["calls"] > checks["max_calls"]:
                    problems.append(f"{cost['calls']} chamadas, esperado no máximo {checks['max_calls']}")
            for needed in checks.get("must_call", []):
                if needed not in result["tools"]:
                    problems.append(f"não chamou {needed} (ferramentas chamadas: {sorted(set(result['tools'])) or 'nenhuma'})")
            for forbidden in checks.get("must_not_call", []):
                if forbidden in result["tools"]:
                    problems.append(f"chamou {forbidden}, que não devia")
            if checks.get("no_pictographs") and PICTOGRAPH.search(result["text"]):
                problems.append("a resposta tem emoji")
            if checks.get("no_tables") and re.search(r"^\s*\|.*\|\s*$", result["text"], re.M):
                problems.append("a resposta tem tabela")
            if checks.get("no_extraction_error") and "extração de arquivos" in result["text"]:
                problems.append("apareceu erro de extração do ZIP")
            if checks.get("no_repeat"):
                for passage in behavior_judge.repeated_passages(result["text"]):
                    problems.append(f"trecho repetido na resposta: {passage[:90]}")
            unchecked = ""
            coverage = None
            if checks.get("judge") and result["text"].strip():
                if judge_info is None:
                    unchecked = " [tom/achados NÃO CONFERIDOS: sem juiz]"
                else:
                    expected = (checks.get("expected") or behavior_judge.KNOWN_DEFECTS) if checks["judge"] == "findings" else None
                    try:
                        verdict = behavior_judge.judge(judge_info[1], re.sub(r"\s*\(verificação \d+\)", "", sent.split("=== ")[0]), result["text"], expected)
                        problems.extend(behavior_judge.problems_from(verdict, expected, (reference or {}).get("cobertura")))
                        if expected:
                            coverage = len(verdict.covered)
                            print(f"         achados conhecidos cobertos: {coverage}/{len(expected)}; faltaram: {', '.join(verdict.missing) or 'nenhum'}")
                    except Exception as exc:  # noqa: BLE001
                        unchecked = f" [juiz falhou: {type(exc).__name__}: {str(exc)[:100]}]"
            status = "OK " if not problems else "FALHOU"
            failures += bool(problems)
            tokens = cost["total_tokens"] if cost else "?"
            if args.register and not problems and cost and not unchecked:
                sys.path.insert(0, str(ROOT / "scripts"))
                import update_protections

                data = update_protections.load()
                entry = {"tokens": cost["total_tokens"], "data": time.strftime("%Y-%m-%d")}
                if coverage is not None:
                    entry["cobertura"] = coverage
                data["provedores"][provider].setdefault("cenarios", {})[name] = entry
                update_protections.save(data)
                update_protections.render(data, write=True)
            calls = cost["calls"] if cost else "?"
            print(f"[{status}] {name}: {tokens} tokens (referência {baseline or 'nenhuma ainda'}), {calls} chamadas, {result['seconds']}s, avisos de espera={result['waits']}, ferramentas={sorted(set(result['tools'])) or 'nenhuma'}{unchecked}")
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
