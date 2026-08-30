"""Regressao: cada pagina e corrigida com os issues DELA, nao com os do projeto.

A analise de ZIP grava a procedencia (`issue["url"] = nome do arquivo`), mas o
corretor entregava a lista inteira a cada pagina HTML: `sobre.html` era
corrigido contra os problemas de `index.html`, e o resumo de mudancas atribuia
todo issue ao arquivo que estivesse sendo processado no momento.
"""

from backend.src.services.chat_tools import _issues_do_arquivo

_ISSUES = [
    {"id": "a", "url": "index.html", "criterion": "1.1.1"},
    {"id": "b", "url": "index.html", "criterion": "1.3.1"},
    {"id": "c", "url": "sobre.html", "criterion": "2.4.4"},
]


class TestIssuesDoArquivo:
    def test_cada_arquivo_recebe_apenas_os_proprios(self):
        assert [i["id"] for i in _issues_do_arquivo(_ISSUES, "index.html")] == ["a", "b"]
        assert [i["id"] for i in _issues_do_arquivo(_ISSUES, "sobre.html")] == ["c"]

    def test_fluxo_de_pagina_unica_mantem_a_lista_inteira(self):
        """Analise por URL: o `url` do issue e a URL auditada, nao o caminho do
        arquivo. Filtrar ali zeraria a correcao -- a lista toda continua valendo."""
        issues = [
            {"id": "a", "url": "https://exemplo.com", "criterion": "1.1.1"},
            {"id": "b", "url": "https://exemplo.com", "criterion": "1.3.1"},
        ]
        assert _issues_do_arquivo(issues, "index.html") == issues

    def test_issue_sem_procedencia_nao_e_descartado(self):
        issues = [{"id": "x", "criterion": "1.1.1"}, {"id": "y", "url": "", "criterion": "1.3.1"}]
        assert _issues_do_arquivo(issues, "index.html") == issues

    def test_arquivo_sem_nenhum_issue_proprio_nao_herda_os_outros(self):
        """O ponto do bug: pagina limpa nao pode ser 'corrigida' com problema alheio."""
        issues = [{"id": "a", "url": "index.html"}, {"id": "b", "url": "contato.html"}]
        assert _issues_do_arquivo(issues, "index.html") == [issues[0]]

    def test_procedencia_com_espacos_em_volta_ainda_casa(self):
        issues = [{"id": "a", "url": " index.html "}, {"id": "b", "url": "sobre.html"}]
        assert [i["id"] for i in _issues_do_arquivo(issues, "index.html")] == ["a"]

    def test_lista_vazia_devolve_vazia(self):
        assert _issues_do_arquivo([], "index.html") == []
