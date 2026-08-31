"""Regressao: o contrato gerado se adapta ao que a resposta E.

Ate 2026-08-31 os tres checks exigiam JSON sempre. Medido contra
https://www.w3.org/WAI/demos/bad/before/home.html, o score deu 33 porque
"Resposta e um JSON valido" falhou -- reprovando a pagina por servir HTML, o que
nao diz nada sobre a acessibilidade dela.

Com a versao adaptativa, medido ao vivo no mesmo dia:
  W3C BAD (inacessivel de proposito)  -> 80, falha em <html lang> (WCAG 3.1.1)
  W3C WAI (referencia acessivel)      -> 100
Confirmado com curl: a primeira serve `<HTML>` puro, a segunda `<html lang="en">`.
A diferenca entre as duas notas e um defeito de acessibilidade real.
"""

import json

from backend.src.services.remote_runners import _build_generated_a11y_contract_collection


def _script(url="https://exemplo.com"):
    colecao = _build_generated_a11y_contract_collection(url)
    return "\n".join(colecao["item"][0]["event"][0]["script"]["exec"])


class TestColecaoGerada:
    def test_e_uma_collection_v21_valida_e_serializavel(self):
        colecao = _build_generated_a11y_contract_collection("https://exemplo.com")
        assert "schema.getpostman.com" in colecao["info"]["schema"]
        assert colecao["item"][0]["request"]["url"] == "https://exemplo.com"
        json.dumps(colecao)  # o Newman recebe isto por arquivo: tem de serializar

    def test_ramifica_por_content_type_em_vez_de_assumir_json(self):
        s = _script()
        assert "ehJson" in s and "ehHtml" in s
        assert "indexOf('text/html')" in s

    def test_html_verifica_idioma_e_titulo(self):
        s = _script()
        assert "WCAG 3.1.1" in s, "idioma declarado"
        assert "WCAG 2.4.2" in s, "titulo nao vazio"

    def test_json_mantem_a_verificacao_de_contrato_da_api(self):
        s = _script()
        assert "pm.response.to.be.json" in s
        assert "'issues'" in s

    def test_charset_e_verificado_nos_dois_casos(self):
        """Fora do if/else: vale para JSON e para HTML."""
        s = _script()
        antes_do_ramo = s.split("if (ehJson)")[0]
        assert "charset" in antes_do_ramo

    def test_tipo_desconhecido_falha_explicito_em_vez_de_passar_calado(self):
        s = _script()
        assert "pm.expect.fail" in s
        assert "Content-Type nao reconhecido" in s

    def test_cada_assercao_explica_o_impacto_para_quem_usa_leitor_de_tela(self):
        """A mensagem que o QA le nao pode ser so o nome do criterio."""
        s = _script()
        assert "voz do idioma errado" in s
        assert "primeira coisa anunciada" in s
        assert "caracteres trocados" in s

    def test_url_alvo_e_a_recebida_nao_uma_fixa(self):
        s2 = _build_generated_a11y_contract_collection("https://outro.com/pagina")
        assert s2["item"][0]["request"]["url"] == "https://outro.com/pagina"
