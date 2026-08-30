"""Regressao: selecao do agente cognitivo por ESTRUTURA, nunca por tamanho.

O gatilho era `_has_form_controls(...) or text_len > 1200`. O numero adivinhava
complexidade a partir do tamanho -- exatamente o que o complexity_router
documenta como proibido pela regra do projeto. Consequencias reais dos dois
lados, e este arquivo fixa as duas.
"""

from backend.src.agents.orchestrator.orchestrator import _conditional_agent_reasons, _has_cognitive_surface


class TestSuperficieCognitiva:
    def test_login_curto_dispara_mesmo_com_poucos_caracteres(self):
        """Falso negativo do limiar: autenticacao e o nucleo de 3.3.8/3.3.9."""
        html = '<form><input type="password" autocomplete="new-password"></form>'
        assert len(html) < 1200
        assert _has_cognitive_surface(html)

    def test_captcha_sem_formulario_dispara(self):
        assert _has_cognitive_surface('<div class="g-captcha">Resolva o CAPTCHA</div>')

    def test_menu_longo_e_repetido_sem_conteudo_nao_dispara(self):
        """Falso positivo do limiar: 1200+ chars de markup sem prosa nem
        formulario nao exigem avaliacao cognitiva."""
        html = "<div>" + ('<span class="separador-decorativo-do-layout"></span>' * 40) + "</div>"
        assert len(html) > 1200
        assert not _has_cognitive_surface(html)

    def test_prosa_dispara_por_nivel_de_leitura(self):
        assert _has_cognitive_surface("<p>Texto corrido da pagina.</p>")

    def test_paragrafo_vazio_nao_conta_como_prosa(self):
        assert not _has_cognitive_surface("<p>   </p><div></div>")

    def test_navegacao_dispara_por_orientacao(self):
        assert _has_cognitive_surface('<nav aria-current="page"><a href="/a">A</a></nav>')

    def test_meta_refresh_dispara_por_limite_de_tempo(self):
        assert _has_cognitive_surface('<meta http-equiv="refresh" content="30">')

    def test_autoplay_dispara_por_distracao(self):
        assert _has_cognitive_surface("<video autoplay src=v.mp4></video>")

    def test_pagina_sem_nenhuma_dessas_estruturas_nao_acorda_o_agente(self):
        assert "cognitive" not in _conditional_agent_reasons("<div><span></span></div>")

    def test_selecao_continua_deterministica(self):
        html = '<form><input type="password"></form>'
        assert _conditional_agent_reasons(html) == _conditional_agent_reasons(html)
