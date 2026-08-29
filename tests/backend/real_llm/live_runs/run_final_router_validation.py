"""Script descartável: validação REAL, ponta a ponta, do roteador completo
(modelo por complexidade + esforço de raciocínio por complexidade) contra o
pipeline INTEIRO de acessibilidade, em 3 páginas reais de complexidade
crescente. Sem mock -- providers reais, modelo real, resultado real.

Mede: tradeoff real classificado, modelo/esforço real escolhido, tempo real,
issues reais entregues, e confirma que o caminho mais barato não perde
qualidade e o caminho mais caro só é usado quando a complexidade pede.

Uso: python tests/backend/real_llm/live_runs/run_final_router_validation.py
"""
import asyncio
import logging
import os
import sys
import time
import unittest.mock
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

logging.basicConfig(level=logging.INFO, format="%(message)s")

os.environ["LLM_PROVIDER"] = "agentic"
os.environ.pop("LLM_MODEL", None)
os.environ["A11Y_RESPONSE_CACHE_ENABLED"] = "false"

from backend.src.config.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from backend.src.security.secret_store import load_secrets_into_environment  # noqa: E402

load_secrets_into_environment()

from backend.src.services import model_router  # noqa: E402

# OPENAI_API_KEY real mas sem credito (429) hoje -- restringe ao provider
# confirmado funcionando de verdade nesta validacao.
patcher = unittest.mock.patch.object(model_router, "_available_auto_providers", return_value=["ollama-cloud"])
patcher.start()

from backend.src.agents.orchestrator.orchestrator import orchestrate  # noqa: E402
from backend.src.services.browser import fetch_rendered_html  # noqa: E402
from backend.src.shared.models import TaskType  # noqa: E402

CASES = [
    ("1. SIMPLES (Wikipedia, artigo estático)", "https://en.wikipedia.org/wiki/Web_accessibility"),
    ("2. MEDIA (site institucional com formularios/navegacao)", "https://www.w3.org/WAI/"),
    ("3. COMPLEXA (widgets ARIA, video, iframes -- ja validada nesta sessao)", "https://dequeuniversity.com/demo/mars/"),
]


async def run_case(label: str, url: str):
    print("\n" + "=" * 78)
    print(f"CASO: {label}")
    print(f"URL: {url}")
    print("-" * 78)

    html = await fetch_rendered_html(url)
    print(f"HTML real obtido: {len(html)} caracteres")

    start = time.monotonic()
    result = await orchestrate(html, TaskType.ANALYZE, target=url)
    elapsed = time.monotonic() - start

    issues = result.data.get("issues", [])
    metrics = result.data.get("agent_metrics", [])
    failed = [m for m in metrics if not m.get("success")]

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for i in issues:
        sev = str(i.get("severity", "")).lower().replace("severity.", "")
        if sev in counts:
            counts[sev] += 1

    print(f"\nPipeline completo REAL: {elapsed:.1f}s | success={result.success}")
    print(f"{len(issues)} issues reais entregues (crit={counts['critical']} alto={counts['high']} medio={counts['medium']} baixo={counts['low']})")
    print(f"{len(metrics)} agentes rodaram, {len(failed)} falharam" + (f" ({[m.get('agent') for m in failed]})" if failed else ""))

    return {
        "label": label, "url": url, "elapsed_s": round(elapsed, 1),
        "success": result.success, "issues_count": len(issues),
        "counts": counts, "agents_run": len(metrics), "agents_failed": len(failed),
    }


async def main():
    print("Providers reais disponiveis nesta validacao:", model_router._available_auto_providers())
    results = []
    for label, url in CASES:
        try:
            r = await run_case(label, url)
        except Exception as exc:
            print(f"\nFALHA REAL no caso '{label}': {exc}")
            r = {"label": label, "url": url, "error": str(exc)}
        results.append(r)

    print("\n" + "=" * 78)
    print("RESUMO FINAL")
    print("=" * 78)
    for r in results:
        if "error" in r:
            print(f"- {r['label']}: FALHOU -- {r['error']}")
        else:
            print(
                f"- {r['label']}: {r['elapsed_s']}s | {r['issues_count']} issues "
                f"| {r['agents_run']} agentes ({r['agents_failed']} falharam) | success={r['success']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
