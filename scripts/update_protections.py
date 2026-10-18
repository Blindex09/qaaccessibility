"""Mantém as proteções por provedor e por módulo sempre atualizadas, a partir de UMA fonte: docs/modules/provedores/evidencias.json.

Depois de testar um provedor em um módulo (qualquer provedor, qualquer módulo, em qualquer ordem), registre o resultado aqui e
tudo o que depende dele é regenerado, em vez de depender de alguém lembrar de editar vários arquivos:
  - a matriz de paridade (docs/modules/paridade_provedores.md);
  - a seção "Provedores" do README de cada módulo;
  - a tabela "Estado por módulo" da ficha de cada provedor (a ficha é criada se não existir);
  - os números de referência por cenário que o script ao vivo usa como base daquele provedor.

Comandos:
  update_protections.py render                          regenera os arquivos a partir da fonte
  update_protections.py check                           reprova se algo está desatualizado ou incompleto (usado pelo verify_all)
  update_protections.py set <provedor> <m1..m4> <PROVADO|PARCIAL|NÃO TESTADO> --nota "o que funcionou e o que falta"
  update_protections.py scenario <provedor> <cenario> <tokens>     números de referência medidos ao vivo

Regras que o `check` impõe (para a proteção nunca ficar para trás):
  - qualquer provedor com algum módulo PROVADO ou PARCIAL tem ficha, sem trechos "A PREENCHER";
  - provedor PROVADO ou PARCIAL tem contrato real gravado, ou diz por que está pendente;
  - módulo PROVADO ou PARCIAL tem data e nota;
  - nenhum arquivo gerado está diferente do que a fonte manda.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = ROOT / "docs" / "modules"
PROVIDERS_DIR = MODULES_DIR / "provedores"
SOURCE = PROVIDERS_DIR / "evidencias.json"
MATRIX_DOC = MODULES_DIR / "paridade_provedores.md"
STATES = ("PROVADO", "PARCIAL", "NÃO TESTADO")
TODO = "A PREENCHER"
sys.stdout.reconfigure(encoding="utf-8")


def load() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    SOURCE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def br(day: str | None) -> str:
    return "sem data" if not day else f"{day[8:10]}/{day[5:7]}/{day[:4]}"


def marked(text: str, name: str, content: str) -> str | None:
    start, end = f"<!-- PROTECOES:{name}:INICIO -->", f"<!-- PROTECOES:{name}:FIM -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        return None
    return pattern.sub(lambda _m: f"{start}\n{content}\n{end}", text, count=1)


def matrix(data: dict) -> str:
    providers = data["provedores"]
    header = "| Módulo | " + " | ".join(p["nome"] for p in providers.values()) + " |"
    rule = "|---|" + "---|" * len(providers)
    rows = []
    for key, module in data["modulos"].items():
        cells = []
        for provider in providers.values():
            entry = provider["modulos"][key]
            cells.append(entry["estado"] + (f" ({br(entry['data'])[:5]})" if entry["data"] else ""))
        rows.append(f"| {key[1:]} {module['titulo']} | " + " | ".join(cells) + " |")
    return "\n".join([header, rule, *rows])


def module_section(data: dict, key: str) -> str:
    lines = [
        "Este módulo vale para todos os provedores (todas as regras do CLAUDE.md valem para todos). Estado de cada um, gerado de",
        "`provedores/evidencias.json` por `scripts/update_protections.py` (não editar a mão):",
        "",
    ]
    for provider_id, provider in data["provedores"].items():
        entry = provider["modulos"][key]
        when = f" em {br(entry['data'])}" if entry["data"] else ""
        note = f" {entry['nota']}." if entry["nota"] else ""
        sheet = f" Ficha: `provedores/{provider['ficha']}`." if entry["estado"] != "NÃO TESTADO" else ""
        lines.append(f"- {provider['nome']}: {entry['estado']}{when}.{note}{sheet}")
    lines += ["", "O roteiro para testar um provedor novo, sem retrabalho, está em `provedores/_roteiro_para_novo_provedor.md`."]
    return "\n".join(lines)


def provider_state(data: dict, provider_id: str) -> str:
    provider = data["provedores"][provider_id]
    rows = ["| Módulo | Estado | Data | Nota |", "|---|---|---|---|"]
    for key, module in data["modulos"].items():
        entry = provider["modulos"][key]
        rows.append(f"| {key[1:]} {module['titulo']} | {entry['estado']} | {br(entry['data']) if entry['data'] else '-'} | {entry['nota'] or '-'} |")
    scenarios = provider.get("cenarios") or {}
    extra = ["", "Números de referência dos cenários ao vivo (base do script `verify_live_modules_1_to_3.py` para este provedor):", ""]
    if scenarios:
        extra += [f"- {name}: {item['tokens']} tokens (medido em {br(item['data'])})" for name, item in scenarios.items()]
    else:
        extra.append("- nenhum medido ainda")
    contract = provider.get("contrato")
    extra += ["", f"Contrato real gravado: `{contract}`." if contract else f"Contrato real: pendente ({provider.get('contrato_pendente') or 'ainda não gravado'})."]
    return "\n".join(["Estado por módulo (gerado de `evidencias.json` por `scripts/update_protections.py`, não editar a mão):", "", *rows, *extra])


def stub(provider: dict) -> str:
    return f"""# Ficha do provedor: {provider['nome']}

{TODO}: preencher esta ficha antes de dar qualquer módulo como PROVADO ou PARCIAL para este provedor. O roteiro está em
`_roteiro_para_novo_provedor.md`.

<!-- PROTECOES:ESTADO:INICIO -->
<!-- PROTECOES:ESTADO:FIM -->

## Como o produto fala com o provedor

{TODO}: API usada, SDK e versão, formato do fluxo (gravado em tests/backend/fixtures/providers), nomes do uso de tokens.

## O que funciona (provado ao vivo)

{TODO}: cenário, números medidos e data.

## O que não foi testado ainda

{TODO}

## Particularidades e defeitos já resolvidos (cada um com a causa provada)

{TODO}

## Como repetir e conferir

{TODO}

## Pendências

{TODO}
"""


def render(data: dict, write: bool) -> list[str]:
    """Devolve os arquivos que mudariam (ou mudaram)."""
    changed: list[str] = []

    def put(path: Path, new: str) -> None:
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != new:
            changed.append(str(path.relative_to(ROOT)))
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new, encoding="utf-8")

    text = MATRIX_DOC.read_text(encoding="utf-8")
    updated = marked(text, "MATRIZ", matrix(data))
    if updated is None:
        raise SystemExit(f"Faltam os marcadores PROTECOES:MATRIZ em {MATRIX_DOC.relative_to(ROOT)}")
    put(MATRIX_DOC, updated)

    for key, module in data["modulos"].items():
        path = MODULES_DIR / module["readme"]
        text = path.read_text(encoding="utf-8")
        block = module_section(data, key)
        updated = marked(text, "PROVEDORES", block)
        if updated is None:
            body = f"<!-- PROTECOES:PROVEDORES:INICIO -->\n{block}\n<!-- PROTECOES:PROVEDORES:FIM -->"
            head, found, _ = text.partition("\n## Provedores")
            updated = (head if found else text.rstrip("\n")) + f"\n\n## Provedores\n\n{body}\n"
        put(path, updated)

    for provider_id, provider in data["provedores"].items():
        used = any(entry["estado"] != "NÃO TESTADO" for entry in provider["modulos"].values())
        path = PROVIDERS_DIR / provider["ficha"]
        if not path.exists():
            if not used:
                continue
            put(path, stub(provider))
            if write:
                path = PROVIDERS_DIR / provider["ficha"]
        if path.exists() or write:
            text = path.read_text(encoding="utf-8") if path.exists() else stub(provider)
            updated = marked(text, "ESTADO", provider_state(data, provider_id))
            if updated is None:
                updated = text.rstrip("\n") + f"\n\n<!-- PROTECOES:ESTADO:INICIO -->\n{provider_state(data, provider_id)}\n<!-- PROTECOES:ESTADO:FIM -->\n"
            put(path, updated)
    return changed


def registry_problems(data: dict, root: Path = ROOT, tags: dict[str, str] | None = None) -> list[str]:
    """Regra 15: todo módulo tem seus testes automáticos, e a tag do último estado provado aponta para o commit declarado."""
    found: list[str] = []
    for key, module in data["modulos"].items():
        tests = module.get("testes_automaticos")
        if not tests:
            found.append(f"{key}: sem testes automáticos registrados")
        for test in tests or []:
            if not (root / test).exists():
                found.append(f"{key}: teste registrado não existe: {test}")
        tag, commit = module.get("tag_ultimo_estado_provado"), module.get("commit_ultimo_estado_provado")
        if bool(tag) != bool(commit):
            found.append(f"{key}: tag e commit do último estado provado precisam vir juntos")
        if tag and tags is not None and not tags.get(tag, "").startswith(commit or "?"):
            found.append(f"{key}: a tag {tag} não existe ou não aponta para o commit {commit}")
    return found


def local_tags() -> dict[str, str]:
    import subprocess

    out = subprocess.run(["git", "-C", str(ROOT), "tag", "--format=%(refname:short) %(objectname)"], capture_output=True, text=True).stdout
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def problems(data: dict) -> list[str]:
    found: list[str] = registry_problems(data, ROOT, local_tags() or None)
    for provider_id, provider in data["provedores"].items():
        used = {k: e for k, e in provider["modulos"].items() if e["estado"] != "NÃO TESTADO"}
        for key, entry in provider["modulos"].items():
            if entry["estado"] not in STATES:
                found.append(f"{provider_id} {key}: estado inválido {entry['estado']!r}")
            if entry["estado"] != "NÃO TESTADO" and (not entry["data"] or not entry["nota"]):
                found.append(f"{provider_id} {key}: {entry['estado']} sem data ou sem nota do que funcionou e do que falta")
        if not used:
            continue
        sheet = PROVIDERS_DIR / provider["ficha"]
        if not sheet.exists():
            found.append(f"{provider_id}: sem ficha em provedores/{provider['ficha']}")
        elif TODO in sheet.read_text(encoding="utf-8"):
            found.append(f"{provider_id}: a ficha ainda tem trechos '{TODO}'")
        contract = provider.get("contrato")
        if contract:
            if not (ROOT / contract).exists():
                found.append(f"{provider_id}: contrato gravado não encontrado em {contract}")
        elif not provider.get("contrato_pendente"):
            found.append(f"{provider_id}: sem contrato real gravado e sem explicação do porquê está pendente")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("render")
    sub.add_parser("check")
    setter = sub.add_parser("set")
    setter.add_argument("provider")
    setter.add_argument("module", choices=["m1", "m2", "m3", "m4"])
    setter.add_argument("state", choices=STATES)
    setter.add_argument("--nota", default="")
    scenario = sub.add_parser("scenario")
    scenario.add_argument("provider")
    scenario.add_argument("name")
    scenario.add_argument("tokens", type=int)
    args = parser.parse_args()
    data = load()

    if args.command == "set":
        if args.provider not in data["provedores"]:
            raise SystemExit(f"Provedor desconhecido: {args.provider}. Acrescente-o em evidencias.json.")
        entry = data["provedores"][args.provider]["modulos"][args.module]
        entry.update(estado=args.state, data=None if args.state == "NÃO TESTADO" else date.today().isoformat(), nota=args.nota)
        save(data)
    elif args.command == "scenario":
        data["provedores"][args.provider].setdefault("cenarios", {})[args.name] = {"tokens": args.tokens, "data": date.today().isoformat()}
        save(data)

    if args.command == "check":
        stale = render(data, write=False)
        issues = problems(data)
        for path in stale:
            print(f"DESATUALIZADO: {path} (rode: update_protections.py render)")
        for issue in issues:
            print(f"INCOMPLETO: {issue}")
        print("PROTEÇÕES: " + ("em dia" if not stale and not issues else "há pendências, não commitar"))
        return 0 if not stale and not issues else 1

    changed = render(data, write=True)
    print("Atualizados:", ", ".join(changed) if changed else "nada mudou")
    for issue in problems(data):
        print(f"ATENÇÃO: {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
