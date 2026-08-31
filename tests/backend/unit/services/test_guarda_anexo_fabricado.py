"""Regressao: o corretor nao pode corrigir uma pagina que o modelo inventou.

Achado real (2026-08-30, execucao ponta a ponta): o usuario anexou um HTML de
68 caracteres; ao chamar `fix_and_zip_files` o modelo passou 406 caracteres em
`files`, com conteudo que nunca esteve no arquivo -- um
`<h1>Produto em Destaque</h1>`, um `alt="Camiseta azul, tamanho M"`, uma "Loja
Online". O pipeline corrigiu a invencao: o ZIP baixado traria uma pagina que o
usuario nunca escreveu, e o painel antes/depois mostraria um "antes" que nao e
o arquivo dele.

O guarda irmao ja existia para o caso inverso (`_looks_like_placeholder_file_
list`, quando o modelo manda "---" em vez de omitir `files`).
"""

from backend.src.services import turn_attachments_store
from backend.src.services.chat_tools import _reconciliar_com_anexos

_ORIGINAL = "<html lang='pt'><body><img src=b.png><button></button></body></html>"
_INVENTADO = (
    '<html lang="pt"><head><title>Loja Online</title></head><body>'
    "<h1>Produto em Destaque</h1>"
    '<img src="b.png" alt="Camiseta azul, tamanho M">'
    "<button>Comprar produto</button></body></html>"
)


def _com_anexo(*anexos):
    turn_attachments_store.clear_turn_attachments()
    turn_attachments_store.set_turn_attachments(list(anexos))


class TestGuardaDeAnexoFabricado:
    def teardown_method(self):
        turn_attachments_store.clear_turn_attachments()

    def test_conteudo_inventado_e_trocado_pelo_arquivo_do_usuario(self):
        _com_anexo({"name": "loja.html", "content": _ORIGINAL})
        arquivos, avisos = _reconciliar_com_anexos([{"path": "loja.html", "content": _INVENTADO}])
        assert arquivos[0]["content"] == _ORIGINAL
        assert avisos and "nao corresponde" in avisos[0]

    def test_conteudo_fiel_passa_intacto_e_sem_aviso(self):
        _com_anexo({"name": "loja.html", "content": _ORIGINAL})
        arquivos, avisos = _reconciliar_com_anexos([{"path": "loja.html", "content": _ORIGINAL}])
        assert arquivos[0]["content"] == _ORIGINAL
        assert avisos == []

    def test_reformatacao_do_modelo_nao_conta_como_fabricacao(self):
        """Aspas e indentacao mudam a string, nao o documento -- trocar aqui
        seria desfazer trabalho legitimo do modelo."""
        _com_anexo({"name": "loja.html", "content": _ORIGINAL})
        reformatado = '<html lang="pt"><body>\n  <img src="b.png">\n  <button></button>\n</body></html>'
        arquivos, avisos = _reconciliar_com_anexos([{"path": "loja.html", "content": reformatado}])
        assert arquivos[0]["content"] == reformatado
        assert avisos == []

    def test_sem_anexo_conhecido_nada_e_tocado(self):
        """Projeto por ZIP ou correcao apos analise por URL seguem o caminho normal."""
        turn_attachments_store.clear_turn_attachments()
        entrada = [{"path": "x.html", "content": _INVENTADO}]
        arquivos, avisos = _reconciliar_com_anexos(entrada)
        assert arquivos == entrada
        assert avisos == []

    def test_varios_anexos_casa_pelo_nome(self):
        _com_anexo(
            {"name": "index.html", "content": _ORIGINAL},
            {"name": "sobre.html", "content": "<html><body><p>sobre</p></body></html>"},
        )
        arquivos, _ = _reconciliar_com_anexos([{"path": "index.html", "content": _INVENTADO}])
        assert arquivos[0]["content"] == _ORIGINAL

    def test_varios_anexos_e_nome_desconhecido_nao_adivinha(self):
        """Na duvida sobre qual anexo corresponde, o guarda nao age."""
        _com_anexo(
            {"name": "index.html", "content": _ORIGINAL},
            {"name": "sobre.html", "content": "<html><body><p>sobre</p></body></html>"},
        )
        entrada = [{"path": "desconhecido.html", "content": _INVENTADO}]
        arquivos, avisos = _reconciliar_com_anexos(entrada)
        assert arquivos == entrada
        assert avisos == []

    def test_caminho_com_diretorio_ainda_casa_pelo_sufixo(self):
        _com_anexo({"name": "loja.html", "content": _ORIGINAL})
        arquivos, avisos = _reconciliar_com_anexos([{"path": "projeto/loja.html", "content": _INVENTADO}])
        assert arquivos[0]["content"] == _ORIGINAL
        assert avisos

    def test_lista_vazia_devolve_vazia(self):
        _com_anexo({"name": "loja.html", "content": _ORIGINAL})
        assert _reconciliar_com_anexos([]) == ([], [])
        assert _reconciliar_com_anexos(None) == ([], [])


class TestStoreDeAnexos:
    def teardown_method(self):
        turn_attachments_store.clear_turn_attachments()

    def test_turno_sem_anexo_nao_apaga_o_anterior(self):
        """O usuario anexa uma vez e nos turnos seguintes so conversa ('pode
        corrigir', 'sim'). Apagar ali devolveria o ponto cego que o guarda cobre."""
        turn_attachments_store.set_turn_attachments([{"name": "loja.html", "content": _ORIGINAL}])
        turn_attachments_store.set_turn_attachments([])
        assert turn_attachments_store.get_turn_attachments()[0]["content"] == _ORIGINAL

    def test_novo_anexo_substitui_o_anterior(self):
        turn_attachments_store.set_turn_attachments([{"name": "a.html", "content": _ORIGINAL}])
        turn_attachments_store.set_turn_attachments([{"name": "b.html", "content": "<p>novo</p>"}])
        anexos = turn_attachments_store.get_turn_attachments()
        assert len(anexos) == 1 and anexos[0]["name"] == "b.html"

    def test_anexo_vazio_e_descartado(self):
        turn_attachments_store.set_turn_attachments([{"name": "vazio.html", "content": "   "}])
        assert turn_attachments_store.get_turn_attachments() == []
