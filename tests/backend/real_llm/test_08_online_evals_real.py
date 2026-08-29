"""
Camada 8/9 -- Online Evals (real).

`telemetry.score_trace` é o LLM-as-judge que pontua traces de produção
(padrão Braintrust/DeepEval) -- em `test_telemetry_scoring.py` (suite mock)
ele é validado com `call_llm` mockado. Aqui ele roda com o judge de verdade
(Ollama Cloud tier alto) contra um trace bom e um trace ruim, provando que o
scoring online distingue qualidade real, não só que o parsing de JSON funciona.
"""
from unittest.mock import patch

import pytest

from backend.src.services import telemetry

pytestmark = pytest.mark.real_llm

_GOOD_TRACE = """
Turno do agente:
User: analise este HTML e aponte problemas de acessibilidade: <img src="logo.png">
Agent (tool_call): run_perceiver(html="<img src=\\"logo.png\\">")
Tool result: {"issues": [{"criterion": "1.1.1 Non-text Content", "severity": "critical",
  "description": "A imagem logo.png não possui atributo alt, impedindo leitores de tela
  de identificá-la.", "suggestion": "Adicione alt=\\"Logo da empresa\\" na tag img."}]}
Agent (final): Encontrei 1 problema crítico: a imagem <img src="logo.png"> não tem texto
alternativo (WCAG 1.1.1). Sugiro adicionar alt="Logo da empresa".
"""

_BAD_TRACE = """
Turno do agente:
User: analise este HTML e aponte problemas de acessibilidade: <img src="logo.png">
Agent (final): Tudo certo, não achei nenhum problema.
"""


@pytest.mark.asyncio
async def test_online_eval_scores_good_trace_as_passing(alto_model_id: str) -> None:
    result = await telemetry.score_trace(_GOOD_TRACE, provider="ollama-cloud")

    assert result is not None, "judge real não retornou score (no-op inesperado)"
    assert "score" in result and "pass" in result
    assert 0.0 <= result["score"] <= 1.0
    assert result["pass"] is True, f"judge real ({alto_model_id}) reprovou um trace correto: {result}"


@pytest.mark.asyncio
async def test_online_eval_scores_bad_trace_lower_than_good_trace(alto_model_id: str) -> None:
    """Discriminação real: o judge precisa pontuar o trace incompleto/incorreto abaixo do bom."""
    good_result = await telemetry.score_trace(_GOOD_TRACE, provider="ollama-cloud")
    bad_result = await telemetry.score_trace(_BAD_TRACE, provider="ollama-cloud")

    assert good_result is not None and bad_result is not None
    assert bad_result["score"] < good_result["score"], (
        f"judge real ({alto_model_id}) não discriminou qualidade: "
        f"bom={good_result['score']} ruim={bad_result['score']}"
    )


@pytest.mark.asyncio
async def test_online_eval_noop_without_provider() -> None:
    """Sem NENHUM provider configurado (nem override, nem settings) -- no-op seguro (contrato existente).
    O fixture de sessão desta suite força LLM_PROVIDER=ollama-cloud, então isolamos esse teste
    simulando settings sem provider, sem depender do estado global da suite real."""
    settings_stub = type("S", (), {"llm_provider": ""})()
    with patch("backend.src.config.settings.get_settings", return_value=settings_stub):
        result = await telemetry.score_trace(_GOOD_TRACE, provider="")
    assert result is None
