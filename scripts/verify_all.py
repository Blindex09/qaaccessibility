"""Roda de uma vez tudo o que protege contra regressão, antes de qualquer commit (vale para qualquer provedor).

  .venv/Scripts/python scripts/verify_all.py            # suítes, lint e tipos (sem gastar cota)
  .venv/Scripts/python scripts/verify_all.py --formats  # também confere se algum provedor mudou o formato da API (gasta 3 chamadas mínimas por provedor)

Não substitui o teste ao vivo pela interface (`verify_live_modules_1_to_3.py` e o uso real): ele prova a lógica, não o modelo.
Sai com 0 só se tudo passou.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe") if (ROOT / ".venv" / "Scripts" / "python.exe").exists() else sys.executable
sys.stdout.reconfigure(encoding="utf-8")


def run(name: str, command: list[str], cwd: Path = ROOT, shell: bool = False) -> bool:
    print(f"== {name}", flush=True)
    result = subprocess.run(command, cwd=cwd, shell=shell, capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = (result.stdout + result.stderr).strip().splitlines()
    print("   " + "\n   ".join(lines[-3:]) if lines else "   (sem saída)")
    ok = result.returncode == 0
    print(f"   -> {'OK' if ok else 'FALHOU'}", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formats", action="store_true")
    args = parser.parse_args()

    results = [
        run("backend: pytest", [PY, "-m", "pytest", "tests/backend", "-q", "--no-cov", "-p", "no:cacheprovider"]),
        run("backend: ruff", [PY, "-m", "ruff", "check", "."]),
        run("backend: mypy", [PY, "-m", "mypy", "backend"]),
        run("front: jest", ["npx", "jest", "--silent"], cwd=ROOT / "web", shell=True),
        run("front: tsc", ["npx", "tsc", "--noEmit"], cwd=ROOT / "web", shell=True),
    ]
    if args.formats:
        sys.path.insert(0, str(ROOT))
        from backend.src.security.secret_store import load_provider_key

        for provider in sorted(p.name for p in (ROOT / "tests" / "backend" / "fixtures" / "providers").iterdir() if p.is_dir()):
            if load_provider_key("LLM", provider):
                results.append(run(f"formato da API: {provider}", [PY, "scripts/record_provider_contract.py", "--provider", provider, "--check"]))
            else:
                print(f"== formato da API: {provider}\n   -> PULADO (sem chave guardada)")
    print("RESULTADO:", "tudo verde" if all(results) else "HÁ FALHAS, não commitar")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
