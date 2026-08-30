"""Regressao: corrigir o que acabou de ser analisado nao pode re-auditar do zero.

Observado ponta a ponta em 2026-08-30, no fluxo do chat com anexo:
  1. `analyze_page` achou 7 problemas e o assistente anunciou isso ao usuario;
  2. o usuario aprovou a correcao;
  3. `fix_and_zip_files` re-auditou o MESMO HTML e achou 0 (18/18 agentes, todos
     devolvendo lista vazia);
  4. sem issues o fixer nao roda -> nenhuma pagina de preview -> `open_live_
     preview` falha -> o painel antes/depois nao abre.

A protecao ja existia (o comentario ao lado dela adverte exatamente sobre
"re-auditoria inconsistente, que frequentemente deixa o live preview sem
paginas"), mas estava condicionada a `files_from_fallback`: so valia quando o
modelo OMITIA os arquivos. Com um anexo, o HTML esta no proprio prompt e o
modelo manda `files` -- o caso comum caia fora da protecao.
"""

from unittest.mock import patch

from backend.src.services.chat_tools import _mesmo_conteudo_ja_analisado

_HTML = "<html lang='pt'><body><img src=b.png><button></button></body></html>"


def _com_analise(conteudo):
    return patch(
        "backend.src.services.last_analyzed_content_store.get_last_analyzed_content",
        return_value=(conteudo, ""),
    )


class TestReaproveitamentoDaAnalise:
    def test_mesmo_conteudo_reaproveita(self):
        with _com_analise(_HTML):
            assert _mesmo_conteudo_ja_analisado([{"path": "loja.html", "content": _HTML}])

    def test_diferenca_so_de_espacos_ainda_reaproveita(self):
        with _com_analise("  " + _HTML + "\n"):
            assert _mesmo_conteudo_ja_analisado([{"path": "loja.html", "content": _HTML}])

    def test_modelo_reescrevendo_o_html_ainda_reaproveita(self):
        """Observado ao vivo: ao repassar o HTML numa chamada de ferramenta, o
        modelo reescreve o texto -- aspas simples viram duplas, atributo sem
        aspas ganha aspas, quebra de linha entre tags. Nada disso muda o
        documento, mas quebrava a igualdade de string e mandava tudo para a
        re-auditoria, que e justamente o bug que este arquivo cobre."""
        reescrito = '<html lang="pt"><body>\n  <img src="b.png">\n  <button></button>\n</body></html>'
        with _com_analise(_HTML):
            assert _mesmo_conteudo_ja_analisado([{"path": "loja.html", "content": reescrito}])

    def test_conteudo_diferente_exige_auditoria_nova(self):
        """O outro lado do risco: reaproveitar analise de OUTRO arquivo daria
        correcao baseada em problema que nao existe neste."""
        with _com_analise(_HTML):
            assert not _mesmo_conteudo_ja_analisado(
                [{"path": "outro.html", "content": "<html><body><p>outra pagina</p></body></html>"}]
            )

    def test_sem_analise_previa_nao_reaproveita(self):
        with _com_analise(""):
            assert not _mesmo_conteudo_ja_analisado([{"path": "loja.html", "content": _HTML}])

    def test_varios_arquivos_nao_reaproveitam(self):
        """O cache de conteudo guarda UMA pagina; com varios arquivos nao ha
        como saber a qual deles a analise correspondia."""
        with _com_analise(_HTML):
            assert not _mesmo_conteudo_ja_analisado(
                [{"path": "a.html", "content": _HTML}, {"path": "b.html", "content": _HTML}]
            )

    def test_lista_vazia_ou_nula_nao_reaproveita(self):
        with _com_analise(_HTML):
            assert not _mesmo_conteudo_ja_analisado([])
            assert not _mesmo_conteudo_ja_analisado(None)

    def test_arquivo_sem_conteudo_nao_reaproveita(self):
        with _com_analise(_HTML):
            assert not _mesmo_conteudo_ja_analisado([{"path": "loja.html", "content": ""}])
