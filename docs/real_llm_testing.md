# Testes reais contra Ollama Cloud (`tests/backend/real_llm/`)

O resto de `tests/backend/` é 100% mockado/determinístico (AsyncMock no lugar do
LLM) -- rápido e reprodutível, roda em todo CI. Esta suite é o oposto: chama o
Ollama Cloud de verdade, tier "alto" (`model_router.resolve_alto_model`), para
validar a pirâmide completa de evals do produto contra comportamento real de
modelo, não uma resposta fixada em código.

## Como rodar

```bash
RUN_REAL_LLM_TESTS=1 python -m pytest tests/backend/real_llm/ -o addopts="" -q
```

Requer `OLLAMA_API_KEY` (ou `OLLAMA_CLOUD_API_KEY`) no ambiente. Sem
`RUN_REAL_LLM_TESTS=1`, todos os testes desta suite são pulados com motivo
explícito -- nunca rodam em CI por padrão (custam tempo e tokens reais).

Para rodar só uma camada: aponte para o arquivo (`test_03_trajectory_evals_real.py`
etc). Runtime total da suite completa: ~2-4 min, ~40-50 chamadas reais de LLM.

## As 9 camadas

| # | Arquivo | O que valida |
|---|---|---|
| 1 | `test_01_component_real.py` | Um agente isolado respeita o schema Pydantic contra output real; não alucina issues em HTML limpo |
| 2 | `test_02_agent_evals_real.py` | Golden dataset (reusa `test_prompt_regression.GOLDEN_CASES`) detectado pelo agente real correto |
| 3 | `test_03_trajectory_evals_real.py` | Roteamento condicional do orquestrador (`_conditional_agent_reasons`), sucesso de cada passo, dedup final |
| 4 | `test_04_e2e_environment_real.py` | `POST /analyze/file` via `TestClient` real, contrato HTTP completo |
| 5 | `test_05_adversarial_evals_real.py` | Resistência a prompt injection embutido no HTML analisado |
| 6 | `test_06_accessibility_evals_real.py` | Recall/precisão do produto num corpus multi-issue |
| 7 | `test_07_regression_evals_real.py` | Compara execução de hoje contra `baseline_snapshot.json` gravado |
| 8 | `test_08_online_evals_real.py` | `telemetry.score_trace` (LLM-as-judge) discrimina trace bom vs ruim de verdade |
| 9 | `test_09_production_observability_real.py` | Falha de rede real vira erro humanizado; logs estruturados; JSON malformado do provider falha explícito, nunca silencioso |

A 10ª camada da pirâmide original ("Production") não é um teste -- é o estado
implantado do sistema; as camadas 8 e 9 são o proxy dela em ambiente de teste.

## Decisões de design

- **Cache desligado** (`A11Y_RESPONSE_CACHE_ENABLED=false` via fixture de sessão):
  o cache de respostas guarda o texto cru do provider antes de validar que é
  JSON parseável. Uma resposta truncada vira um cache hit repetido por até
  5 minutos (TTL) -- inaceitável numa suite que existe pra medir comportamento
  real a cada chamada.
- **Retry único em falha de parsing** (`run_agent_with_retry` no `conftest.py`):
  o Ollama Cloud, contra os modelos testados (`deepseek-v4-flash:*`), devolveu
  JSON truncado em ~1 a cada 15-20 chamadas nesta sessão de validação -- ruído
  de provider real, não um bug do parser (`extract_json_array` falha explícito
  e correto: `success=False`, nunca um falso "zero issues"). Um retry tolera
  isso sem mascarar regressão persistente (duas falhas seguidas ainda falha o teste).
- **`xfail(strict=True)` em vez de esconder falha**: os dois testes de
  `test_05_adversarial_evals_real.py` que reproduzem uma vulnerabilidade real
  (prompt injection no HTML analisado consegue suprimir/rebaixar issues) ficam
  marcados como falha esperada e documentada -- não removidos, não afrouxados.
  Se alguém endurecer o system prompt e o teste passar a acertar, `strict=True`
  vira uma falha de XPASS, forçando quem mexeu a remover o marker conscientemente.
- **Baseline versionado** (`baseline_snapshot.json`): fonte de verdade para
  regressão. Recapturar deliberadamente após mudança intencional de prompt/modelo:

```bash
python - <<'PY'
import asyncio, json, os, sys
os.environ["LLM_PROVIDER"] = "ollama-cloud"
sys.path.insert(0, ".")
from backend.src.config.settings import get_settings
get_settings.cache_clear()
from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.agents.robustness.robustness import run_robustness
from backend.src.agents.forms_a11y.forms_a11y import run_forms_a11y
from backend.src.agents.screen_reader.screen_reader import run_screen_reader
from tests.backend.unit.test_prompt_regression import GOLDEN_CASES
from backend.src.services.model_router import resolve_alto_model

AGENT = {"GC001": run_perceiver, "GC002": run_robustness, "GC003": run_forms_a11y, "GC005": run_screen_reader}

async def main():
    snapshot = {"model": resolve_alto_model("ollama-cloud"), "provider": "ollama-cloud", "cases": {}}
    for case in GOLDEN_CASES:
        if case["id"] not in AGENT:
            continue
        result = await AGENT[case["id"]](case["html"])
        issues = result.data.get("issues", []) if result.success else []
        snapshot["cases"][case["id"]] = {
            "description": case["description"],
            "issue_count": len(issues),
            "criteria": sorted({i["criterion"] for i in issues}),
        }
    with open("tests/backend/real_llm/baseline_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

asyncio.run(main())
PY
```

## Achados desta validação (2026-08-09)

Descobertas reais que só uma suite contra o modelo de verdade revela (não
aparecem contra mocks):

1. **Prompt injection funciona contra o perceiver** (não corrigido, documentado
   como `xfail` em `test_05`). O HTML analisado é conteúdo não confiável por
   natureza do produto (URLs externas, uploads); instruções textuais dentro
   dele conseguiram suprimir e rebaixar severidade de issues reais. Requer
   hardening do system prompt (delimitar o HTML como dado, nunca instrução).
2. **JSON truncado ocasional do provider real**, tratado corretamente pelo
   parser (`success=False` explícito), mas cacheado sem validação -- corrigido
   no nível de teste (cache desligado + retry), não no produto.
3. **Roteamento por criterion WCAG não é 1:1 com o agente "óbvio"**: um modelo
   real forte pode escolher um criterion irmão igualmente válido (`1.3.5` em
   vez de `1.3.1`, por exemplo) -- golden datasets escritos para mock exato
   precisam de matching por família de guideline, não substring exata, para
   julgar um LLM de verdade sem gerar falsos negativos no próprio teste.
4. **`resolve_alto_model("ollama-cloud")` não é perfeitamente estável entre
   execuções** (variou entre `deepseek-v4-flash:0731` e
   `deepseek-v4-flash:preview` nesta sessão) -- esperado dado o roteamento
   dinâmico por design, mas afeta reprodutibilidade de baseline; ver
   `test_baseline_model_matches_or_flags_drift`.
