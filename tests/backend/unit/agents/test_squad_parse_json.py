"""Regressao: texto EXTRA depois do JSON nao pode derrubar o papel.

Observado nas trajetorias de 2026-08-31:

    [Squad:tech_lead]    Falhou: Extra data: line 13 column 1 (char 636)
    [Squad:scrum_master] Falhou: Extra data: line 1 column 1422 (char 1421)

O parser pegava de `text.find("{")` ate `text.rfind("}")` -- da primeira chave
ate a ULTIMA. Quando o modelo emitia dois objetos, ou um JSON seguido de prosa
com chaves, a fatia abrangia tudo e o json.loads estourava. O papel inteiro
falhava por causa do que vinha DEPOIS de um JSON que estava correto, e a cadeia
degradava com um blocker que nao existia de verdade.
"""

import pytest

from backend.src.agents.squad.role_agents._runner import _extract_json_object


class TestExtracaoDoObjetoDoPapel:
    def test_prosa_depois_do_json_e_ignorada(self):
        bruto = '{"summary": "ok", "decisions": ["a"]}\n\nObservacao: isso conclui o ciclo.'
        assert _extract_json_object(bruto)["summary"] == "ok"

    def test_segundo_objeto_e_ignorado(self):
        bruto = '{"summary": "primeiro"}\n{"summary": "segundo"}'
        assert _extract_json_object(bruto)["summary"] == "primeiro"

    def test_prosa_antes_e_depois(self):
        bruto = 'Segue a decisao do papel:\n{"summary": "meio"}\nFim da resposta.'
        assert _extract_json_object(bruto)["summary"] == "meio"

    def test_cerca_de_markdown_continua_tolerada(self):
        bruto = '```json\n{"summary": "com cerca"}\n```'
        assert _extract_json_object(bruto)["summary"] == "com cerca"

    def test_objeto_aninhado_nao_e_truncado(self):
        bruto = '{"summary": "x", "handoff": {"escopo": {"paginas": 3}}}\ntexto extra'
        assert _extract_json_object(bruto)["handoff"]["escopo"]["paginas"] == 3

    def test_lista_e_recusada_com_mensagem_clara(self):
        with pytest.raises(ValueError, match="objeto JSON"):
            _extract_json_object("[1, 2, 3]")

    def test_resposta_sem_json_e_recusada(self):
        with pytest.raises(ValueError, match="objeto JSON"):
            _extract_json_object("nao consegui decidir nesta rodada")

    def test_json_realmente_malformado_e_recusado(self):
        with pytest.raises(ValueError, match="malformado"):
            _extract_json_object('{"summary": "sem fechar"')

    def test_papel_usa_retry_repair_em_vez_de_chamada_crua(self):
        """Um JSON ruim nao pode mais derrubar o papel na primeira tentativa."""
        import inspect

        from backend.src.agents.squad.role_agents import _runner

        fonte = inspect.getsource(_runner.run_role)
        assert "call_llm_structured" in fonte
