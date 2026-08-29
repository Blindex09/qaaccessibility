"""Script descartável: valida de ponta a ponta, com execução REAL (sem mock),
o fluxo exato pedido pelo usuário (2026-08-12): "analisou uma página, pediu
para ver com qual navegador tá sendo usado, mandou instalar o playwright, se
já tiver instalado a IA avisa".

1. Roda run_cross_browser_test_tool contra uma URL real -- os 3 motores
   (Chromium/Firefox/WebKit) já estão instalados nesta máquina (instalados
   mais cedo nesta sessão), então isso valida o caminho "tudo funcionando,
   sem sugestão de instalação".
2. Roda install_playwright_browsers_tool de verdade (subprocess real,
   `playwright install`) -- como os navegadores já estão instalados, valida
   o caminho "avisa que já estava instalado" em vez de fingir que baixou algo.

Uso: python tests/backend/real_llm/live_runs/run_cross_browser_and_playwright_install_e2e.py
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.src.services.chat_tools import (  # noqa: E402
    install_playwright_browsers_tool,
    run_cross_browser_test_tool,
)

TARGET_URL = "https://dequeuniversity.com/demo/mars/"


def main() -> None:
    print(f"1) Rodando teste cross-browser REAL contra {TARGET_URL} (Chromium/Firefox/WebKit)...")
    raw = run_cross_browser_test_tool({"target_url": TARGET_URL})
    result = json.loads(raw)

    print(f"   status={result.get('status')}")
    print(f"   engines_succeeded={result.get('engines_succeeded')}")
    print(f"   engines_failed={result.get('engines_failed')}")
    if "install_suggestion" in result:
        print(f"   install_suggestion (esperado NAO aparecer, ja instalado): {result['install_suggestion']}")
    else:
        print("   install_suggestion: ausente -- confirma que os 3 motores ja estao instalados de verdade")

    for engine, summary in (result.get("per_engine_summary") or {}).items():
        if "error" in summary:
            print(f"   [{engine}] ERRO: {summary['error']}")
        else:
            print(f"   [{engine}] violacoes={summary.get('violations_count', '?')}")

    print("\n2) Rodando install_playwright_browsers REAL (subprocess de verdade, playwright install)...")
    raw_install = install_playwright_browsers_tool({"pre_exec_msg": "confirmando instalacao"})
    install_result = json.loads(raw_install)
    print(f"   status={install_result.get('status')}")
    print(f"   already_installed={install_result.get('already_installed')}")
    print(f"   message={install_result.get('message')}")

    print("\n" + "=" * 78)
    if result.get("status") == "ok" and not result.get("install_suggestion") and install_result.get("already_installed") is True:
        print("RESULTADO: fluxo completo confirmado -- os 3 motores rodaram de verdade, "
              "nenhuma sugestao de instalacao apareceu (correto, ja estavam instalados), "
              "e o install_playwright_browsers avisou 'ja instalado' em vez de fingir que baixou algo.")
    else:
        print("RESULTADO: ver detalhes acima -- nem tudo saiu como esperado (pode ser legitimo, ex.: rede indisponivel).")


if __name__ == "__main__":
    main()
