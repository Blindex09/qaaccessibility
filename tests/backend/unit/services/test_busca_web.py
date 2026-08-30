"""Regressao: a busca web tem que devolver CONTEUDO, nao so titulo e url.

Bug real (2026-08-30, medido contra a API): o POST para o Exa nao pedia
`contents`, entao a resposta vinha sem os campos `text`/`highlights` e todo
resultado saia com `content` vazio. A ferramenta reportava `success: True`
com zero substancia -- o agente recebia so links para raciocinar. Mesma classe
de falha do crawl e do Firecrawl: vazio passando por sucesso.
"""

import json
from unittest.mock import MagicMock, patch

from backend.src.services.chat_tools import exa_search


def _resposta(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestExaSearch:
    def test_pede_contents_no_corpo_da_requisicao(self):
        """Sem `contents`, a API nao devolve texto -- e a causa do bug."""
        with (
            patch("httpx.post", return_value=_resposta({"results": []})) as mock_post,
            patch("backend.src.config.settings.get_settings") as mock_cfg,
        ):
            mock_cfg.return_value.exa_api_key = "k"
            exa_search({"query": "wcag 2.4.11"})

        corpo = mock_post.call_args.kwargs["json"]
        assert "contents" in corpo, "sem `contents` o Exa nao devolve o texto da pagina"
        assert corpo["contents"].get("text"), "`text` precisa ser pedido explicitamente"

    def test_texto_da_pagina_chega_em_content(self):
        with (
            patch(
                "httpx.post",
                return_value=_resposta(
                    {"results": [{"title": "T", "url": "https://x", "text": "corpo real da pagina"}]}
                ),
            ),
            patch("backend.src.config.settings.get_settings") as mock_cfg,
        ):
            mock_cfg.return_value.exa_api_key = "k"
            saida = json.loads(exa_search({"query": "q"}))

        assert saida["data"]["web"][0]["content"] == "corpo real da pagina"

    def test_cai_para_highlights_quando_nao_ha_texto(self):
        with (
            patch(
                "httpx.post",
                return_value=_resposta(
                    {"results": [{"title": "T", "url": "https://x", "highlights": ["frase um", "frase dois"]}]}
                ),
            ),
            patch("backend.src.config.settings.get_settings") as mock_cfg,
        ):
            mock_cfg.return_value.exa_api_key = "k"
            saida = json.loads(exa_search({"query": "q"}))

        assert saida["data"]["web"][0]["content"] == "frase um frase dois"

    def test_sem_texto_e_sem_highlights_nao_estoura(self):
        """A versao anterior fazia `r.get("highlights", [""])[0]`, que levanta
        IndexError quando a chave existe mas vem como lista vazia."""
        with (
            patch(
                "httpx.post",
                return_value=_resposta({"results": [{"title": "T", "url": "https://x", "highlights": []}]}),
            ),
            patch("backend.src.config.settings.get_settings") as mock_cfg,
        ):
            mock_cfg.return_value.exa_api_key = "k"
            saida = json.loads(exa_search({"query": "q"}))

        assert saida["data"]["web"][0]["content"] == ""

    def test_sem_chave_de_api_falha_explicito(self):
        with patch("backend.src.config.settings.get_settings") as mock_cfg:
            mock_cfg.return_value.exa_api_key = ""
            with patch.dict("os.environ", {"EXA_API_KEY": ""}, clear=False):
                saida = json.loads(exa_search({"query": "q"}))
        assert "error" in saida
