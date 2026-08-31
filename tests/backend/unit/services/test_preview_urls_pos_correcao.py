"""Regressao: a verificacao pos-correcao precisa de uma URL que exista de verdade.

`open_live_preview` devolvia so {session_id, total_pages}. A ferramenta
`verify_screen_reader_announcements` recebe URL -- entao nao havia como apontar
a verificacao para a pagina recem-corrigida. A regra 20 do prompt (percorrer a
pagina como um leitor de tela depois da correcao) seria uma promessa impossivel
de cumprir, que e pior do que nao prometer.

Este teste amarra os dois lados: o formato que a tool devolve e o caminho que a
rota de preview de fato serve.
"""

import json
from unittest.mock import patch

from backend.src.services.chat_tools import open_live_preview

_PAGINAS = [{"path": "index.html", "original_html": "<img src=x>", "fixed_html": '<img src=x alt="y">'}]


class TestOpenLivePreviewURLs:
    def _chamar(self, base="http://127.0.0.1:8001"):
        with (
            patch("backend.src.services.last_fix_store.get_last_fix", return_value=_PAGINAS),
            patch("backend.src.routes.preview.register_preview_session", return_value="sessao123"),
            patch("backend.src.config.settings.get_settings") as cfg,
        ):
            # Metodo, nao atributo -- foi assim que a versao anterior deste
            # teste deixou passar um `resolved_public_base_url` chamado SEM
            # parenteses: o mock devolvia a string de qualquer jeito, e a URL
            # real saia com um '<bound method ...>' no lugar da base.
            cfg.return_value.resolved_public_base_url = lambda: base
            return json.loads(open_live_preview({}))

    def test_devolve_url_da_pagina_corrigida_e_da_original(self):
        d = self._chamar()
        assert d["fixed_url"] == "http://127.0.0.1:8001/preview/render/sessao123/0?mode=fixed"
        assert d["original_url"] == "http://127.0.0.1:8001/preview/render/sessao123/0?mode=original"

    def test_mantem_os_campos_que_a_interface_ja_consumia(self):
        d = self._chamar()
        assert d["session_id"] == "sessao123"
        assert d["total_pages"] == 1

    def test_usa_a_base_publica_configurada_nunca_host_fixo(self):
        d = self._chamar(base="https://qa.exemplo.com")
        assert d["fixed_url"].startswith("https://qa.exemplo.com/")
        assert "localhost" not in d["fixed_url"]

    def test_caminho_bate_com_a_rota_registrada_no_app(self):
        """A costura: o caminho devolvido tem que existir no roteador."""
        from backend.src.routes.preview import router

        caminhos = {r.path for r in router.routes}
        assert "/preview/render/{session_id}/{page_index}" in caminhos

    def test_sem_correcao_recente_falha_explicito_e_sem_urls(self):
        with patch("backend.src.services.last_fix_store.get_last_fix", return_value=[]):
            d = json.loads(open_live_preview({}))
        assert "error" in d
        assert "fixed_url" not in d


class TestRegra20NoPrompt:
    """A regra existe e aponta para a ferramenta e o campo certos."""

    def test_prompt_manda_verificar_a_url_corrigida_apos_o_preview(self):
        from backend.src.services.chat_runtime import SYSTEM_PROMPT

        assert "POST-FIX SCREEN READER WALKTHROUGH" in SYSTEM_PROMPT
        assert "verify_screen_reader_announcements" in SYSTEM_PROMPT
        # o campo citado na regra tem que ser o que a tool realmente devolve
        assert "fixed_url" in SYSTEM_PROMPT
