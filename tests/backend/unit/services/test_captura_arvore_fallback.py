"""Regressao: a verificacao de leitor de tela precisa alcancar o Live Preview.

`_capture_raw_accessibility_snapshot` so usava Chromium REMOTO (Browserless via
CDP). A verificacao pos-correcao aponta para a pagina do preview, servida pelo
proprio backend em `http://127.0.0.1:8001/preview/render/...` -- e para um
Browserless remoto `127.0.0.1` e o localhost DELE. Medido em 2026-08-30:

    Page.goto: Target page, context or browser has been closed

A pagina renderizava normalmente (1125 bytes, com <button> e alt), mas a captura
voltava vazia e a ferramenta do chat reportava sucesso com zero achados -- sem
nenhum sinal de que NADA tinha sido verificado.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services import browser as browser_mod


class TestFallbackLocal:
    @pytest.mark.asyncio
    async def test_cai_para_chromium_local_quando_o_remoto_falha(self):
        arvore = {"role": "WebArea", "name": "ok"}
        with (
            patch.object(browser_mod, "get_settings") as cfg,
            patch.object(browser_mod, "async_playwright") as pw_ctx,
            patch.object(browser_mod, "_snapshot_com_navegador", new=AsyncMock(return_value=arvore)),
        ):
            cfg.return_value.browserless_ws_url = "ws://remoto:3000"
            pw = MagicMock()
            pw.chromium.connect_over_cdp = AsyncMock(side_effect=Exception("Target page ... has been closed"))
            pw.chromium.launch = AsyncMock(return_value=MagicMock(close=AsyncMock()))
            pw_ctx.return_value.__aenter__ = AsyncMock(return_value=pw)
            pw_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            resultado = await browser_mod._capture_raw_accessibility_snapshot("http://127.0.0.1:8001/preview/x")

        assert resultado == arvore
        pw.chromium.launch.assert_awaited()

    @pytest.mark.asyncio
    async def test_sem_browserless_ainda_tenta_o_local(self):
        """Antes, sem `BROWSERLESS_WS_URL` a funcao devolvia None de cara --
        nenhuma verificacao de leitor de tela era possivel na maquina."""
        arvore = {"role": "WebArea", "name": "ok"}
        with (
            patch.object(browser_mod, "get_settings") as cfg,
            patch.object(browser_mod, "async_playwright") as pw_ctx,
            patch.object(browser_mod, "_snapshot_com_navegador", new=AsyncMock(return_value=arvore)),
        ):
            cfg.return_value.browserless_ws_url = None
            pw = MagicMock()
            pw.chromium.launch = AsyncMock(return_value=MagicMock(close=AsyncMock()))
            pw_ctx.return_value.__aenter__ = AsyncMock(return_value=pw)
            pw_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            resultado = await browser_mod._capture_raw_accessibility_snapshot("http://127.0.0.1:8001/preview/x")

        assert resultado == arvore
        pw.chromium.launch.assert_awaited()

    @pytest.mark.asyncio
    async def test_falha_dos_dois_devolve_none_sem_levantar(self):
        with (
            patch.object(browser_mod, "get_settings") as cfg,
            patch.object(browser_mod, "async_playwright") as pw_ctx,
        ):
            cfg.return_value.browserless_ws_url = None
            pw_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("sem navegador"))
            pw_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await browser_mod._capture_raw_accessibility_snapshot("http://x") is None


class TestFerramentaExpoeQueNadaFoiVerificado:
    """A ausencia de captura tem que chegar ao MODELO, nao morrer no servico."""

    def test_tool_devolve_tree_captured_e_motivo(self):
        from backend.src.services.chat_tools import verify_screen_reader_announcements_tool
        from backend.src.services.screen_reader_verification import ScreenReaderVerificationResult

        vazio = ScreenReaderVerificationResult(
            url="http://x",
            total_interactive_nodes=0,
            findings=[],
            nvda_running=False,
            spoken_findings=0,
            tree_captured=False,
            not_verified_reason="A arvore nao foi capturada.",
        )
        with patch(
            "backend.src.services.screen_reader_verification.verify_screen_reader_announcements",
            new=AsyncMock(return_value=vazio),
        ):
            saida = json.loads(verify_screen_reader_announcements_tool({"url": "http://x"}))

        assert saida["tree_captured"] is False
        assert saida["not_verified_reason"]
        assert saida["findings"] == []
