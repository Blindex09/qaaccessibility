"""Script descartável: valida de ponta a ponta, com chamadas REAIS de LLM
(sem mock do provider), as duas capacidades novas do orchestrator (2026-08-11):

1. Delegação dinâmica agente-a-agente (delegation_coordinator.py): um agente
   pulado pela detecção estrutural é acionado em uma rodada extra quando o
   coordenador, lendo os achados reais da rodada 1, decide que há evidência
   suficiente -- verificado contra uma página com um widget customizado que a
   detecção estrutural (regex sobre role=/aria-*) plausivelmente não pega
   (um "tab" implementado só com classes CSS + onclick, sem role ARIA).
2. `pipeline_graph` explícito no resultado (Graph Engineering): nós e arestas
   observáveis no próprio AgentResult, não só em log.

Uso: python tests/backend/real_llm/live_runs/run_delegation_and_graph_e2e.py
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

patcher = unittest.mock.patch.object(model_router, "_available_auto_providers", return_value=["ollama-cloud"])
patcher.start()

from backend.src.agents.orchestrator.orchestrator import orchestrate  # noqa: E402
from backend.src.services.complexity_router import classify_and_set_tradeoff  # noqa: E402
from backend.src.shared.models import TaskType  # noqa: E402

# "Tab" implementado só via classes/onclick -- sem role="tab"/aria-selected,
# então a detecção estrutural (_has_widget_surface em orchestrator.py) NÃO
# deve selecionar widgets_a11y na rodada 1. Se o coordenador ler os achados
# de outros agentes (ex.: aria_specialist notando falta de semântica em
# controle interativo) e delegar widgets_a11y mesmo assim, é sinal real de
# delegação funcionando -- não é garantido (depende do LLM), mas é o cenário
# desenhado pra dar a melhor chance real de acontecer.
HTML_WITH_IMPLICIT_WIDGET = """
<!DOCTYPE html>
<html lang="en">
<head><title>Painel de configurações</title></head>
<body>
  <div class="tablist">
    <div class="tab-item active" onclick="showTab('geral')">Geral</div>
    <div class="tab-item" onclick="showTab('avancado')">Avançado</div>
    <div class="tab-item" onclick="showTab('sobre')">Sobre</div>
  </div>
  <div class="tab-panel" id="geral">
    <p>Configurações gerais da conta.</p>
    <img src="/icon.png">
  </div>
  <div class="tab-panel" id="avancado" style="display:none">
    <p>Opções avançadas.</p>
  </div>
  <script>
    function showTab(id) {
      document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
      document.getElementById(id).style.display = 'block';
    }
  </script>
</body>
</html>
""".strip()


async def main():
    start = time.monotonic()
    tradeoff = await classify_and_set_tradeoff(HTML_WITH_IMPLICIT_WIDGET)
    print(f"tradeoff real classificado pelo modelo: {tradeoff}")

    result = await orchestrate(HTML_WITH_IMPLICIT_WIDGET, TaskType.ANALYZE, target="delegation-e2e-test")
    elapsed = time.monotonic() - start

    issues = result.data.get("issues", [])
    metrics = result.data.get("agent_metrics", [])
    graph = result.data.get("pipeline_graph")

    print(f"\nPipeline completo REAL concluído em {elapsed:.1f}s")
    print(f"success={result.success} | {len(issues)} issues reais")
    print(f"agentes executados: {len(metrics)}")

    print("\n" + "=" * 78)
    print("PIPELINE_GRAPH (Graph Engineering) -- presente e observável?")
    print("=" * 78)
    if graph is None:
        print("FALHA: 'pipeline_graph' ausente do resultado.")
    else:
        print(f"nós: {len(graph.get('nodes', []))} | arestas: {len(graph.get('edges', []))}")
        states = {}
        for n in graph.get("nodes", []):
            states[n["state"]] = states.get(n["state"], 0) + 1
        print(f"nós por estado: {states}")
        delegated_nodes = [n for n in graph.get("nodes", []) if n["state"] == "delegated"]
        if delegated_nodes:
            print(f"nós DELEGADOS nesta rodada real: {[n['agent'] for n in delegated_nodes]}")
        else:
            print("nenhum nó delegado nesta rodada (coordenador real decidiu que não havia evidência suficiente -- resultado válido).")

    print("\n" + "=" * 78)
    print("MÉTRICAS POR AGENTE (delegated_by marca quem veio da delegação)")
    print("=" * 78)
    for m in metrics:
        delegated_marker = f" [delegado por {m.get('delegated_by')}]" if m.get("delegated_by") else ""
        print(f"- {m.get('agent')}: sucesso={m.get('success')} issues={m.get('issues_found')} {m.get('duration_ms', 0):.0f}ms{delegated_marker}")

    print("\n" + "=" * 78)
    print("ISSUES REAIS ENCONTRADOS")
    print("=" * 78)
    for i in issues:
        print(f"- [{i.get('severity')}] {i.get('criterion')}: {i.get('description', '')[:110]}")


if __name__ == "__main__":
    asyncio.run(main())
