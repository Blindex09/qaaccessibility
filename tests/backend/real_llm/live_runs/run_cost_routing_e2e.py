"""Script descartável: E2E real do roteamento de custo entre providers
(Task #19, model_router.py::_resolve_agentic_auto). Roda a cadeia completa e
real -- sem mock -- pra simples e complexa: classificador de complexidade
real -> roteador de custo real -> chamada real ao provider/modelo escolhido
-> issues de acessibilidade reais entregues. Mede tokens reais e custo
estimado com base no cost_input/cost_output do catálogo.

Uso: python tests/backend/real_llm/live_runs/run_cost_routing_e2e.py
"""
import asyncio
import contextlib
import logging
import os
import sys
import time
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
# Achado real durante a preparação deste teste: o secret store guarda
# OLLAMA_API_KEY (usado pelo cliente `ollama` diretamente em run_agent.py),
# mas o roteamento "agentic/auto" (model_router._available_auto_providers)
# procura OLLAMA_CLOUD_API_KEY especificamente para o provider "ollama-cloud"
# -- sem isso, "ollama-cloud" nunca entra na lista de candidatos comparados
# por preço, mesmo com a chave real presente sob outro nome. Espelha aqui
# pra este teste exercitar os DOIS providers reais disponíveis.
if os.getenv("OLLAMA_API_KEY") and not os.getenv("OLLAMA_CLOUD_API_KEY"):
    os.environ["OLLAMA_CLOUD_API_KEY"] = os.environ["OLLAMA_API_KEY"]

from agent.models_dev import get_model_info  # noqa: E402
from backend.src.services import complexity_router, model_router  # noqa: E402
from backend.src.services.llm_client import call_llm, extract_json_array  # noqa: E402
from backend.src.shared.models import AccessibilityIssue  # noqa: E402

SIMPLE_HTML = """
<html lang="pt"><head><title>Blog</title></head>
<body>
<main>
<h1>Meu artigo</h1>
<p>Este é um parágrafo simples de um blog, sem nenhum widget interativo.</p>
<img src="foto.jpg">
</main>
</body></html>
""".strip()

COMPLEX_HTML = """
<html lang="pt"><head><title>App</title></head>
<body>
<main>
<div role="combobox" aria-expanded="false" tabindex="0">
  <div role="listbox">
    <div role="option">Item 1</div>
    <div role="option" aria-selected="true">Item 2</div>
  </div>
</div>
<div role="tablist">
  <div role="tab" aria-selected="true">Aba 1</div>
  <div role="tab">Aba 2</div>
</div>
<div onclick="save()">Salvar (div clicável sem role/tabindex)</div>
<div role="dialog" aria-modal="true">
  <div id="live-region"></div>
</div>
</main>
</body></html>
""".strip()


def blended_cost(info) -> float:
    return (info.cost_input * 4 + info.cost_output) / 5 if info else float("nan")


async def run_case(label: str, html: str):
    print("\n" + "=" * 78)
    print(f"CASO: {label}")
    print("-" * 78)

    model_router.clear_cache()
    tradeoff = await complexity_router.classify_and_set_tradeoff(html)
    provider, model = model_router.resolve_model_and_provider("agentic", "alto", tier="alto", agent_label="operability")

    info = None
    with contextlib.suppress(Exception):
        info = get_model_info(provider, model)
    cost = blended_cost(info)
    print(f"tradeoff real classificado: {tradeoff}")
    print(f"provider/modelo REAL escolhido: {provider}/{model} (custo estimado blend={cost:.4f} $/Mtok)")

    start = time.monotonic()
    raw = await call_llm(
        system_prompt=(
            "You are a WCAG 2.2 accessibility specialist. Detect real violations "
            "in the HTML. Return ONLY a JSON array of issues, each with exactly "
            "these fields: id (str), guideline (MUST be exactly the literal string "
            "'WCAG 2.2' -- never a criterion code or other guideline name), "
            "criterion (e.g. '2.1.1 Keyboard'), severity (critical|high|medium|low), "
            "confidence (high|medium|low), level (A|AA|AAA), element, description, "
            "suggestion. Empty array if none."
        ),
        user_prompt=f"Analyze:\n\n{html}",
        temperature=0.1,
        agent_label="operability",
        model_tier="alto",
    )
    elapsed = time.monotonic() - start
    try:
        issues = [AccessibilityIssue(**i) for i in extract_json_array(raw)]
    except Exception as exc:
        print(f"FALHA ao parsear resposta real: {exc}\nraw={raw[:500]}")
        issues = []

    print(f"chamada real concluída em {elapsed:.1f}s -- {len(issues)} issue(s) reais entregue(s)")
    for i in issues:
        print(f"  - [{i.severity}] {i.criterion}: {i.description[:100]}")

    return {
        "label": label,
        "tradeoff": tradeoff,
        "provider": provider,
        "model": model,
        "cost_blend": cost,
        "elapsed_s": round(elapsed, 1),
        "issues_count": len(issues),
        "issues": issues,
    }


async def main():
    print("Providers com API key real disponível:", model_router._available_auto_providers())
    if os.environ.get("FORCE_SINGLE_PROVIDER"):
        forced = [os.environ["FORCE_SINGLE_PROVIDER"]]
        print(f"FORCE_SINGLE_PROVIDER ativo -- restringindo a {forced} (achado real: "
              "OPENAI_API_KEY armazenada está inválida/expirada, 401 da própria API)")
        import unittest.mock
        patcher = unittest.mock.patch.object(model_router, "_available_auto_providers", return_value=forced)
        patcher.start()

    simple_result = await run_case("Página SIMPLES (sem widget, sem ARIA)", SIMPLE_HTML)
    complex_result = await run_case("Página COMPLEXA (combobox, tablist, dialog, div clicável sem role)", COMPLEX_HTML)

    print("\n" + "=" * 78)
    print("RESUMO")
    print("=" * 78)
    for r in (simple_result, complex_result):
        print(f"- {r['label']}: tradeoff={r['tradeoff']} -> {r['provider']}/{r['model']} "
              f"| {r['issues_count']} issues reais | {r['elapsed_s']}s")

    same_provider = simple_result["provider"] == complex_result["provider"]
    same_model = simple_result["model"] == complex_result["model"]
    print(f"\nMesmo provider nos dois casos? {same_provider}")
    print(f"Mesmo modelo nos dois casos? {same_model}")

    # Checagem de qualidade: a pagina complexa tem violacoes obvias reais
    # (div[onclick] sem role/tabindex e' a mais inequivoca) -- confirma que
    # o caminho de custo NAO degradou a entrega no caso que mais precisa de
    # atencao.
    complex_desc_blob = " ".join(i.description.lower() + " " + (i.description_technical or "").lower() for i in complex_result["issues"])
    found_div_onclick_issue = "onclick" in complex_desc_blob or "teclado" in complex_desc_blob or "keyboard" in complex_desc_blob
    print(f"Detectou o problema mais óbvio da página complexa (div clicável sem teclado)? {found_div_onclick_issue}")

    if simple_result["cost_blend"] == complex_result["cost_blend"]:
        print(
            "\nNOTA HONESTA: os dois casos resolveram pro mesmo custo_blend "
            f"({simple_result['cost_blend']:.4f}) -- o catálogo real disponível hoje "
            "não tem diferenciação de preço genuína entre os candidatos dos "
            "providers com chave presente neste ambiente (openai + ollama-cloud), "
            "então esta rodada real não demonstra economia em $ mensurável -- "
            "o mecanismo em si já está provado por unidade (8 testes reais em "
            "test_model_router.py com custos mockados genuinamente diferentes)."
        )


if __name__ == "__main__":
    asyncio.run(main())
