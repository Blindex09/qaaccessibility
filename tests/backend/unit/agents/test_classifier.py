import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.classifier.classifier import run_classifier

_ALVO = "backend.src.agents.classifier.classifier.call_llm_structured"


def _falso_structured(raw: str):
    """Imita `call_llm_structured`: chama o `build` com a saida crua e propaga
    a excecao dele -- que e o que dispara o retry/repair na versao real. O
    agente passou a usar esse mecanismo em 2026-08-31, quando o preambulo do
    modelo consumia o orcamento inteiro antes de qualquer `[`."""

    async def _chamada(*_a, build, **_kw):
        return build(raw)

    return AsyncMock(side_effect=_chamada)


@pytest.mark.asyncio
class TestClassifierAgent:
    async def test_classifier_on_success(self):
        with patch(_ALVO, new=_falso_structured(json.dumps(["react", "tailwind"]))):
            result = await run_classifier("<html></html>")
        assert result.success is True
        assert result.agent == "classifier"
        assert set(result.data["technologies"]) == {"react", "tailwind"}

    async def test_classifier_detects_svelte(self):
        with patch(_ALVO, new=_falso_structured(json.dumps(["svelte"]))):
            result = await run_classifier("<html data-svelte-h='1'></html>")
        assert result.success is True
        assert result.data["technologies"] == ["svelte"]

    async def test_classifier_filters_invalid_techs(self):
        # Deve filtrar tecnologias desconhecidas
        with patch(_ALVO, new=_falso_structured(json.dumps(["react", "jquery", "tailwind", "cobol"]))):
            result = await run_classifier("<html></html>")
        assert result.success is True
        assert set(result.data["technologies"]) == {"react", "tailwind"}

    async def test_classifier_empty_html(self):
        result = await run_classifier("")
        assert result.success is True
        assert result.data["technologies"] == []

    async def test_classifier_failure_on_invalid_json(self):
        with patch(_ALVO, new=_falso_structured("not a json array")):
            result = await run_classifier("<html></html>")
        assert result.success is False
        assert result.data["technologies"] == []
        assert result.error is not None

    async def test_classifier_failure_on_llm_exception(self):
        with patch(_ALVO, new=AsyncMock(side_effect=Exception("API connection error"))):
            result = await run_classifier("<html></html>")
        assert result.success is False
        assert result.data["technologies"] == []
        assert "API connection error" in result.error


class TestPreambuloAntesDoJson:
    """Regressao: o preambulo do modelo nao pode consumir o orcamento inteiro.

    Achado em 2026-08-31, auditando a PROPRIA interface do produto. O prompt ja
    proibia preambulo ("no explanations, and no preamble") e o modelo escreveu
    assim mesmo:

        'Let me analyze this HTML for the specific technologies:

         1. **React**: I see `<style id="react-native-stylesheet">` -- this is a
         React Native Web marker. Also, the class names like `css-175oi2r'

    Com `max_tokens=100` o orcamento acabava antes de qualquer `[` e o agente
    falhava inteiro (era `call_llm` cru, sem retry). `extract_json_array` sempre
    tolerou prosa ANTES do array -- o que faltava era o array caber depois dela.

    Eu tinha olhado esse mesmo `max_tokens=100` na varredura de orcamentos e
    concluido que "100 sobra para uma lista de 5 strings curtas". Raciocinei
    sobre o tamanho da RESPOSTA e ignorei o preambulo.
    """

    def test_orcamento_comporta_preambulo_antes_do_array(self):
        import inspect

        from backend.src.agents.classifier.classifier import run_classifier

        fonte = inspect.getsource(run_classifier)
        assert "max_tokens=100" not in fonte, "100 tokens nao cabem preambulo + array"
        assert "call_llm_structured" in fonte, "sem retry/repair, um preambulo derruba o agente"

    def test_array_e_lido_mesmo_com_prosa_antes(self):
        from backend.src.agents.classifier.classifier import _extrair_tecnologias

        bruto = 'Let me analyze this HTML:\n\n1. **React**: I see markers.\n\n["react", "tailwind"]'
        assert _extrair_tecnologias(bruto) == ["react", "tailwind"]

    def test_resposta_sem_array_levanta_para_disparar_o_repair(self):
        from backend.src.agents.classifier.classifier import _extrair_tecnologias

        with pytest.raises((ValueError, TypeError, KeyError)):
            _extrair_tecnologias("Let me analyze this HTML for the specific technologies:")

    def test_lista_vazia_e_resposta_valida(self):
        """Nenhum framework detectado e um resultado, nao uma falha."""
        from backend.src.agents.classifier.classifier import _extrair_tecnologias

        assert _extrair_tecnologias("[]") == []
