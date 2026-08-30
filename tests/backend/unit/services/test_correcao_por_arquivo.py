"""Regressao: cada pagina e corrigida com os issues DELA -- sem sumir com os outros.

Dois bugs, achados um depois do outro:

1) O corretor entregava a lista INTEIRA do projeto a cada pagina HTML:
   `sobre.html` era corrigido contra os problemas de `index.html`, e
   `_normalize_issue_for_fixer` sobrescrevia `url` com o arquivo corrente,
   apagando a evidencia de onde o problema realmente estava.

2) A primeira correcao filtrava por igualdade estrita e criava um bug pior.
   Medido num ZIP real de 2 paginas: dos 17 issues, 12 tinham arquivo e 5
   ficaram SEM, porque `_map_issues_to_files` e best-effort -- so marca quando
   localiza o trecho dentro do arquivo. Filtrar por igualdade faria esses 5
   nunca serem corrigidos em lugar nenhum, e sumindo calados.

Regra final: descarta so o que comprovadamente pertence a OUTRO arquivo.
"""

from backend.src.services.chat_tools import _issues_do_arquivo

_PROJETO = {"index.html", "sobre.html"}
_ISSUES = [
    {"id": "a", "url": "index.html", "criterion": "1.1.1"},
    {"id": "b", "url": "index.html", "criterion": "1.3.1"},
    {"id": "c", "url": "sobre.html", "criterion": "2.4.4"},
    {"id": "d", "url": "Projeto ZIP (Misto): 2 arquivos", "criterion": "4.1.1"},
    {"id": "e", "criterion": "1.4.3"},
]


class TestIssuesDoArquivo:
    def test_nao_recebe_o_que_e_de_outro_arquivo(self):
        ids = [i["id"] for i in _issues_do_arquivo(_ISSUES, "index.html", _PROJETO)]
        assert "c" not in ids, "issue de sobre.html vazou para index.html"
        ids_sobre = [i["id"] for i in _issues_do_arquivo(_ISSUES, "sobre.html", _PROJETO)]
        assert "a" not in ids_sobre and "b" not in ids_sobre

    def test_issue_sem_procedencia_vale_para_todos(self):
        """O bug da minha primeira correcao: sumia calado."""
        for arquivo in ("index.html", "sobre.html"):
            ids = [i["id"] for i in _issues_do_arquivo(_ISSUES, arquivo, _PROJETO)]
            assert "e" in ids, f"issue sem procedencia sumiu de {arquivo}"

    def test_issue_de_nivel_de_projeto_vale_para_todos(self):
        for arquivo in ("index.html", "sobre.html"):
            ids = [i["id"] for i in _issues_do_arquivo(_ISSUES, arquivo, _PROJETO)]
            assert "d" in ids, f"issue de nivel de projeto sumiu de {arquivo}"

    def test_nenhum_issue_se_perde_no_conjunto_das_paginas(self):
        """Invariante: todo issue e oferecido a pelo menos um arquivo."""
        vistos = set()
        for arquivo in _PROJETO:
            vistos.update(i["id"] for i in _issues_do_arquivo(_ISSUES, arquivo, _PROJETO))
        assert vistos == {i["id"] for i in _ISSUES}

    def test_fluxo_de_pagina_unica_mantem_a_lista_inteira(self):
        """Analise por URL: o `url` do issue e a URL auditada, nao um caminho."""
        issues = [{"id": "a", "url": "https://exemplo.com"}, {"id": "b", "url": "https://exemplo.com"}]
        assert _issues_do_arquivo(issues, "index.html", None) == issues
        assert _issues_do_arquivo(issues, "index.html", set()) == issues

    def test_projeto_de_um_arquivo_so_nao_descarta_nada(self):
        assert _issues_do_arquivo(_ISSUES, "index.html", {"index.html"}) == _ISSUES

    def test_procedencia_com_espacos_em_volta_ainda_casa(self):
        issues = [{"id": "a", "url": " index.html "}, {"id": "b", "url": "sobre.html"}]
        assert [i["id"] for i in _issues_do_arquivo(issues, "index.html", _PROJETO)] == ["a"]

    def test_lista_vazia_devolve_vazia(self):
        assert _issues_do_arquivo([], "index.html", _PROJETO) == []
