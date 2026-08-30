import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.clarifier.clarifier import _construir_classificacao, run_clarifier

_ALVO = "backend.src.agents.clarifier.clarifier.call_llm_structured"


def _falso_structured(raw: str):
    """Imita `call_llm_structured`: chama o `build` com a saida crua e propaga
    a excecao dele -- que e o que dispara o retry/repair na versao real."""

    async def _chamada(*_a, build, **_kw):
        return build(raw)

    return AsyncMock(side_effect=_chamada)


@pytest.mark.asyncio
class TestClarifierAgent:
    async def test_empty_message_returns_needs_clarification_without_calling_llm(self):
        mock_llm = AsyncMock()
        with patch(_ALVO, new=mock_llm):
            result = await run_clarifier("   ")
        assert result.success is True
        assert result.data["intent"] == "needs_clarification"
        assert result.data["needs_clarification"] is True
        mock_llm.assert_not_called()

    async def test_analyze_url_intent_classified(self):
        payload = json.dumps(
            {
                "intent": "analyze_url",
                "needs_clarification": False,
                "question": "",
                "explanation": "Usuario pediu analise de uma URL especifica.",
            }
        )
        with patch(_ALVO, new=_falso_structured(payload)):
            result = await run_clarifier("analise https://example.com por favor")
        assert result.success is True
        assert result.data["intent"] == "analyze_url"
        assert result.data["needs_clarification"] is False

    async def test_ambiguous_message_generates_clarification_question(self):
        payload = json.dumps(
            {
                "intent": "needs_clarification",
                "needs_clarification": True,
                "question": "Qual URL ou arquivo você gostaria que eu analisasse?",
                "explanation": "Pedido ambiguo, sem alvo definido.",
            }
        )
        with patch(_ALVO, new=_falso_structured(payload)):
            result = await run_clarifier("analisa isso ai")
        assert result.data["needs_clarification"] is True
        assert result.data["question"]

    async def test_missing_keys_in_llm_response_fall_back_to_defaults(self):
        with patch(_ALVO, new=_falso_structured(json.dumps({"intent": "chat_a11y"}))):
            result = await run_clarifier("o que é WCAG?")
        assert result.success is True
        assert result.data["intent"] == "chat_a11y"
        assert result.data["needs_clarification"] is False
        assert result.data["question"] == ""

    async def test_failure_on_invalid_json(self):
        with patch(_ALVO, new=_falso_structured("not json")):
            result = await run_clarifier("qualquer coisa")
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(_ALVO, new=AsyncMock(side_effect=Exception("provider down"))):
            result = await run_clarifier("qualquer coisa")
        assert result.success is False
        assert "provider down" in result.error


class TestOrcamentoEValidacao:
    """Regressao: 6 de 10 classificacoes reais eram descartadas por JSON cortado.

    Medido em 2026-08-30 com 10 prompts. As respostas vinham truncadas no meio do
    objeto -- e com a intencao JA correta no inicio da saida -- porque
    `max_tokens=250` nao cabia intent + question + explanation em portugues.
    Acerto: 4/10. Mesma causa do estouro de orcamento ja corrigido no VPAT e no
    gerador de testes.
    """

    def test_orcamento_de_saida_comporta_pergunta_e_explicacao(self):
        import inspect

        fonte = inspect.getsource(run_clarifier)
        assert "max_tokens=250" not in fonte, "250 tokens truncavam o JSON no meio"
        assert "call_llm_structured" in fonte, "sem retry/repair, um JSON cortado descarta a classificacao"

    def test_json_truncado_e_rejeitado_para_disparar_o_repair(self):
        with pytest.raises((ValueError, TypeError, KeyError)):
            _construir_classificacao('{"intent": "out_of_scope", "explanation": "O usuario')

    def test_intent_fora_da_lista_e_rejeitado(self):
        """Antes passava direto para o roteamento."""
        with pytest.raises(ValueError, match="intent invalido"):
            _construir_classificacao(json.dumps({"intent": "fazer_cafe"}))

    def test_intent_valido_normaliza_os_demais_campos(self):
        d = _construir_classificacao(json.dumps({"intent": "needs_clarification"}))
        assert d["intent"] == "needs_clarification"
        assert d["needs_clarification"] is True
        assert d["question"] == ""

    def test_todos_os_intents_do_prompt_sao_aceitos(self):
        from backend.src.agents.clarifier.clarifier import _INTENTS_VALIDOS, SYSTEM_PROMPT

        for intent in _INTENTS_VALIDOS:
            assert intent in SYSTEM_PROMPT, f"{intent} validado mas ausente do prompt"
            assert _construir_classificacao(json.dumps({"intent": intent}))["intent"] == intent
