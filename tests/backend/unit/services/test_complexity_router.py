"""Testes do classificador de complexidade (dial custo/qualidade decidido pelo
modelo, nunca por heurística fixa de tamanho -- ver complexity_router.py)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services import complexity_router


@pytest.fixture(autouse=True)
def _reset_tradeoff():
    complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)
    yield
    complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)


class TestGetSetCurrentTradeoff:
    def test_default_is_favor_quality(self):
        assert complexity_router.get_current_tradeoff() == complexity_router.DEFAULT_TRADEOFF

    def test_set_and_get(self):
        complexity_router.set_current_tradeoff(8)
        assert complexity_router.get_current_tradeoff() == 8

    def test_clamps_out_of_range_values(self):
        complexity_router.set_current_tradeoff(999)
        assert complexity_router.get_current_tradeoff() == 10
        complexity_router.set_current_tradeoff(-5)
        assert complexity_router.get_current_tradeoff() == 0


class TestClassifyAndSetTradeoff:
    @pytest.mark.asyncio
    async def test_empty_content_uses_default_without_calling_llm(self):
        with patch("backend.src.services.llm_client.call_llm", new=AsyncMock()) as mock_call:
            result = await complexity_router.classify_and_set_tradeoff("")
        assert result == complexity_router.DEFAULT_TRADEOFF
        mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_model_decides_favor_cost_for_simple_content(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps({"tradeoff": 9, "reasoning": "simple static text"})),
        ):
            result = await complexity_router.classify_and_set_tradeoff("<p>hello</p>")
        assert result == 9
        assert complexity_router.get_current_tradeoff() == 9

    @pytest.mark.asyncio
    async def test_model_decides_favor_quality_for_complex_content(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps({"tradeoff": 1, "reasoning": "dense ARIA widgets"})),
        ):
            result = await complexity_router.classify_and_set_tradeoff("<div role='combobox'>...</div>")
        assert result == 1
        assert complexity_router.get_current_tradeoff() == 1

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_default_without_crashing(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("provider unreachable")),
        ):
            result = await complexity_router.classify_and_set_tradeoff("<p>content</p>")
        assert result == complexity_router.DEFAULT_TRADEOFF
        assert complexity_router.get_current_tradeoff() == complexity_router.DEFAULT_TRADEOFF

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_default(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not valid json at all"),
        ):
            result = await complexity_router.classify_and_set_tradeoff("<p>content</p>")
        assert result == complexity_router.DEFAULT_TRADEOFF

    @pytest.mark.asyncio
    async def test_out_of_range_tradeoff_from_model_is_clamped(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps({"tradeoff": 42, "reasoning": "overconfident model"})),
        ):
            result = await complexity_router.classify_and_set_tradeoff("<p>content</p>")
        assert result == 10

    @pytest.mark.asyncio
    async def test_classifier_uses_fast_tier_never_alto(self):
        """A classificação em si tem que ser barata -- nunca deve rodar no tier
        "alto" (isso pagaria uma chamada cara so pra decidir se economiza)."""
        mock_call = AsyncMock(return_value=json.dumps({"tradeoff": 5, "reasoning": "x"}))
        with patch("backend.src.services.llm_client.call_llm", new=mock_call):
            await complexity_router.classify_and_set_tradeoff("<p>content</p>")
        _, kwargs = mock_call.call_args
        assert kwargs.get("model_tier") == "fast"


class TestOrcamentoDoRoteador:
    """Regressao: 3 de 20 chamadas reais eram descartadas por JSON cortado.

    Medido nos logs de 2026-08-30 (15% de falha). A saida vinha truncada no meio
    e o tradeoff JA estava decidido; cada falha caia no DEFAULT_TRADEOFF, que
    favorece QUALIDADE -- a otimizacao de custo desligava calada, justamente na
    feature que existe para economizar. Mesma causa do clarifier, do VPAT e do
    gerador de testes.
    """

    def test_orcamento_comporta_o_reasoning_em_prosa(self):
        import inspect

        from backend.src.services.complexity_router import classify_and_set_tradeoff

        fonte = inspect.getsource(classify_and_set_tradeoff)
        assert "max_tokens=150" not in fonte, "150 tokens truncavam o JSON no meio"
        assert "call_llm_structured" in fonte, "sem retry/repair, um JSON cortado vira fallback silencioso"

    def test_json_cortado_levanta_para_disparar_o_repair(self):
        from backend.src.services.complexity_router import _extrair_tradeoff

        with pytest.raises((ValueError, TypeError, KeyError)):
            _extrair_tradeoff('{"tradeoff": 9, "reasoning": "Conteudo muito simples: entao uma analise de ba')

    def test_tradeoff_fora_da_escala_e_limitado_nao_rejeitado(self):
        """Um 42 diz claramente "maximizar economia"; rejeitar pagaria um retry
        para descartar um sinal usavel. O que precisa levantar e o JSON cortado."""
        from backend.src.services.complexity_router import _extrair_tradeoff

        assert _extrair_tradeoff('{"tradeoff": 42, "reasoning": "x"}') == 10
        assert _extrair_tradeoff('{"tradeoff": -5, "reasoning": "x"}') == 0

    def test_tier_barato_preservado_ao_migrar_para_structured(self):
        """Regressao introduzida na propria migracao: `call_llm_structured` nao
        tinha `model_tier`, entao decidir SE vale economizar passaria a rodar no
        modelo caro."""
        import inspect

        from backend.src.services.complexity_router import classify_and_set_tradeoff

        assert 'model_tier="fast"' in inspect.getsource(classify_and_set_tradeoff)

    def test_resposta_sem_tradeoff_e_rejeitada(self):
        from backend.src.services.complexity_router import _extrair_tradeoff

        with pytest.raises(ValueError, match="sem o campo"):
            _extrair_tradeoff('{"reasoning": "so a justificativa"}')

    def test_resposta_valida_devolve_o_inteiro(self):
        from backend.src.services.complexity_router import _extrair_tradeoff

        assert _extrair_tradeoff('{"tradeoff": 8, "reasoning": "markup simples"}') == 8
        assert _extrair_tradeoff('{"tradeoff": 0, "reasoning": "widgets ARIA densos"}') == 0
