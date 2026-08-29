"""Script descartável: teste AMPLO e real do roteamento de custo (Task #19)
contra o pipeline COMPLETO de acessibilidade (todos os agentes especialistas,
dedup, revisor de falso positivo, verificador determinístico de contraste) --
não um agente isolado como nos scripts anteriores. Roda contra uma página real
usada nesta sessão para validar Cypress/Selenium (dequeuniversity.com/demo/mars),
conhecida por ter violações reais documentadas, permitindo cruzar o resultado
da IA com o que o axe-core real já confirmou nesta mesma sessão (6 violações:
aria-allowed-attr, image-alt, aria-prohibited-attr, color-contrast, link-name,
region).

Uso: python tests/backend/real_llm/live_runs/run_full_pipeline_cost_routing_e2e.py
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

# OPENAI_API_KEY armazenada está inválida (Task #22, achado real 2026-08-11) --
# restringe ao provider que sabemos funcionar de verdade hoje.
from backend.src.services import model_router  # noqa: E402

patcher = unittest.mock.patch.object(model_router, "_available_auto_providers", return_value=["ollama-cloud"])
patcher.start()

from backend.src.agents.orchestrator.orchestrator import orchestrate  # noqa: E402
from backend.src.services.browser import fetch_rendered_html  # noqa: E402
from backend.src.services.complexity_router import classify_and_set_tradeoff  # noqa: E402
from backend.src.shared.models import TaskType  # noqa: E402

TARGET_URL = "https://dequeuniversity.com/demo/mars/"

# Violações reais confirmadas via Cypress cloud (axe-core 4.13.0) nesta mesma
# sessão, contra a MESMA URL -- usadas aqui só como sinal de cobertura
# aproximado (a IA analisa semanticamente, não roda o mesmo ruleset do
# axe-core, então não é 1:1 esperado -- mas overlap nos achados óbvios é um
# bom sinal real de que o caminho de custo não perdeu qualidade).
AXE_CORE_REAL_FINDINGS = {
    "aria-allowed-attr", "image-alt", "aria-prohibited-attr",
    "color-contrast", "link-name", "region",
}


async def main():
    print(f"Buscando HTML real renderizado de {TARGET_URL} ...")
    html = await fetch_rendered_html(TARGET_URL)
    print(f"HTML real obtido: {len(html)} caracteres\n")

    start = time.monotonic()
    tradeoff = await classify_and_set_tradeoff(html)
    print(f"tradeoff real classificado pelo modelo: {tradeoff}")

    result = await orchestrate(html, TaskType.ANALYZE, target=TARGET_URL)
    elapsed = time.monotonic() - start

    issues = result.data.get("issues", [])
    metrics = result.data.get("agent_metrics", [])

    print(f"\nPipeline completo REAL concluído em {elapsed:.1f}s")
    print(f"success={result.success} | {len(issues)} issues reais (após dedup + revisor de falso positivo + verificador de contraste)")
    print(f"agentes executados: {len(metrics)}")

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    criteria_found = set()
    for i in issues:
        sev = str(i.get("severity", "")).lower().replace("severity.", "")
        if sev in counts:
            counts[sev] += 1
        criteria_found.add(str(i.get("criterion", "")).lower())

    print(f"\nPor severidade: crítico={counts['critical']} alto={counts['high']} médio={counts['medium']} baixo={counts['low']}")

    print("\n" + "=" * 78)
    print("TODOS OS ISSUES REAIS ENTREGUES")
    print("=" * 78)
    for i in issues:
        print(f"- [{i.get('severity')}] {i.get('criterion')}: {i.get('description', '')[:110]}")

    # Cruzamento aproximado com achados reais do axe-core (mesma URL, mesma sessão)
    desc_blob = " ".join(
        (str(i.get("description", "")) + " " + str(i.get("description_technical", "")) + " " + str(i.get("criterion", ""))).lower()
        for i in issues
    )
    coverage_signals = {
        "aria-allowed-attr": "aria" in desc_blob and ("allow" in desc_blob or "suporta" in desc_blob or "prohibited" in desc_blob or "proibid" in desc_blob),
        "image-alt": ("alt" in desc_blob) and ("imagem" in desc_blob or "image" in desc_blob or "img" in desc_blob),
        "aria-prohibited-attr": "aria" in desc_blob and ("proibid" in desc_blob or "prohibited" in desc_blob or "não suporta" in desc_blob),
        "color-contrast": "contrast" in desc_blob or "contraste" in desc_blob,
        "link-name": ("link" in desc_blob) and ("nome" in desc_blob or "name" in desc_blob or "texto" in desc_blob or "discern" in desc_blob),
        "region": "landmark" in desc_blob or "region" in desc_blob and "content" in desc_blob,
    }
    print("\n" + "=" * 78)
    print("CRUZAMENTO COM ACHADOS REAIS DO AXE-CORE (mesma URL, mesma sessão)")
    print("=" * 78)
    hits = 0
    for rule, found in coverage_signals.items():
        marker = "SIM" if found else "não"
        if found:
            hits += 1
        print(f"- {rule}: {marker}")
    print(f"\nCobertura aproximada: {hits}/{len(AXE_CORE_REAL_FINDINGS)} categorias do axe-core real também aparecem na análise semântica da IA")

    print("\n" + "=" * 78)
    print("MÉTRICAS POR AGENTE")
    print("=" * 78)
    for m in metrics:
        print(f"- {m.get('agent')}: sucesso={m.get('success')} issues={m.get('issues_found')} {m.get('duration_ms', 0):.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
