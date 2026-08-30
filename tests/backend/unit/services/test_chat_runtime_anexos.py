"""Regressao: o fato "tem anexo" e estrutural, nunca inferido do texto.

Bug real (2026-08-30): o gate do clarifier era
``"[Arquivos anexados" in message or "===" in message``. A segunda metade
casava com QUALQUER mensagem contendo um separador markdown, um diff ou uma
tabela ASCII -- exatamente o que um usuario de QA cola no chat -- e nesses
casos a triagem semantica do primeiro turno era pulada em silencio.
"""

from backend.src.services.chat_runtime import (
    _LEGACY_ATTACHMENT_MARKER,
    _compor_mensagem_com_anexos,
)


class TestComporMensagemComAnexos:
    def test_sem_anexo_devolve_o_texto_intacto(self):
        assert _compor_mensagem_com_anexos("audita esse site", None) == "audita esse site"
        assert _compor_mensagem_com_anexos("audita esse site", []) == "audita esse site"

    def test_separador_markdown_no_texto_nao_vira_anexo(self):
        """O ponto do bug: '===' no texto do usuario nao e sinal de anexo."""
        texto = "olha esse trecho:\n=== saida do terminal ===\nfoo"
        assert _compor_mensagem_com_anexos(texto, []) == texto
        assert _LEGACY_ATTACHMENT_MARKER not in _compor_mensagem_com_anexos(texto, [])

    def test_anexo_estruturado_entra_no_prompt_com_nome_e_conteudo(self):
        saida = _compor_mensagem_com_anexos(
            "analisa",
            [{"name": "index.html", "content": "<img src=x>"}],
        )
        assert saida.startswith("analisa")
        assert "=== index.html ===" in saida
        assert "<img src=x>" in saida

    def test_texto_vazio_com_anexo_ganha_instrucao_padrao(self):
        saida = _compor_mensagem_com_anexos("   ", [{"name": "a.html", "content": "<p>x</p>"}])
        assert "Analise a acessibilidade dos arquivos anexados." in saida
        assert "=== a.html ===" in saida

    def test_multiplos_anexos_todos_presentes(self):
        saida = _compor_mensagem_com_anexos(
            "vai",
            [
                {"name": "a.html", "content": "<h1>a</h1>"},
                {"name": "b.css", "content": ".x{color:#fff}"},
            ],
        )
        assert "=== a.html ===" in saida
        assert "=== b.css ===" in saida
        assert "<h1>a</h1>" in saida
        assert ".x{color:#fff}" in saida

    def test_anexo_com_campos_ausentes_nao_quebra(self):
        saida = _compor_mensagem_com_anexos("vai", [{}])
        assert "=== arquivo ===" in saida
