"""
Testes unitarios para browser.py e crawler.py.
Regras:
- Zero emojis em logger
- Imports no topo
- Mocks do Playwright para não abrir browser real
"""

from unittest.mock import ANY, AsyncMock, patch

import pytest

# ── browser.py ────────────────────────────────────────────────────────────────


class TestFetchRenderedHtml:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser._scrape_with_firecrawl")
    async def test_returns_html_on_success(self, mock_scrape, mock_settings):
        """Deve retornar o HTML capturado pela página."""
        mock_html = "<html><body><h1>Rendered</h1></body></html>"
        mock_scrape.return_value = mock_html
        mock_settings.return_value.firecrawl_api_key = "fake_key"

        from backend.src.services.browser import fetch_rendered_html
        result = await fetch_rendered_html("https://example.com")
        assert result == mock_html

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser._scrape_with_firecrawl")
    async def test_raises_on_navigation_failure(self, mock_scrape, mock_settings):
        """Deve propagar excecao se o browser não conseguir carregar a página."""
        mock_scrape.side_effect = Exception("net::ERR_NAME_NOT_RESOLVED")
        mock_settings.return_value.firecrawl_api_key = "fake_key"

        from backend.src.services.browser import fetch_rendered_html
        with pytest.raises(Exception, match="ERR_NAME_NOT_RESOLVED"):
            await fetch_rendered_html("https://não-existe-mesmo.xyz")

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser._scrape_with_firecrawl")
    async def test_continues_after_networkidle_timeout(self, mock_scrape, mock_settings):
        """Deve retornar HTML mesmo se networkidle exceder timeout."""
        mock_html = "<html><body>SPA content</body></html>"
        mock_scrape.return_value = mock_html
        mock_settings.return_value.firecrawl_api_key = "fake_key"

        from backend.src.services.browser import fetch_rendered_html
        result = await fetch_rendered_html("https://spa-app.com")
        assert result == mock_html


class TestFetchRenderedHtmlAndScreenshot:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser._scrape_with_firecrawl")
    async def test_fetch_rendered_html_and_screenshot_success(self, mock_scrape, mock_settings):
        """Deve retornar HTML e screenshot base64."""
        mock_html = "<html><body><h1>Rendered</h1></body></html>"
        mock_screenshot = b"fake_png_data"

        mock_scrape.return_value = mock_html
        mock_settings.return_value.firecrawl_api_key = "fake_key"
        mock_settings.return_value.browserless_ws_url = "ws://fake"

        mock_page = AsyncMock()
        mock_page.set_content = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=mock_screenshot)
        mock_page.evaluate = AsyncMock(return_value=None)
        mock_page.content = AsyncMock(return_value=mock_html)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.src.services.browser.async_playwright", return_value=mock_pw):
            from backend.src.services.browser import fetch_rendered_html_and_screenshot
            html, sshot = await fetch_rendered_html_and_screenshot("https://example.com")

        assert html == mock_html
        assert sshot == "ZmFrZV9wbmdfZGF0YQ=="  # base64.b64encode(b"fake_png_data").decode()


class TestFetchRenderedHtmlScreenshotAndFocusStates:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser._scrape_with_firecrawl")
    async def test_fetch_rendered_html_screenshot_and_focus_states_success(self, mock_scrape, mock_settings):
        """Deve retornar HTML, screenshot inicial e lista de screenshots das tags focadas."""
        mock_html = "<html><body><button id='b1'></button></body></html>"
        mock_screenshot = b"fake_png_data"
        mock_crop = b"crop_data"

        mock_scrape.return_value = mock_html
        mock_settings.return_value.firecrawl_api_key = "fake_key"
        mock_settings.return_value.browserless_ws_url = "ws://fake"

        mock_active_el = AsyncMock()
        mock_active_el.as_element = lambda: mock_active_el
        mock_active_el.bounding_box = AsyncMock(return_value={"x": 10, "y": 15, "width": 100, "height": 40})

        mock_page = AsyncMock()
        mock_page.set_content = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.screenshot = AsyncMock(side_effect=[mock_screenshot, mock_crop, mock_crop])
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.viewport_size = {"width": 1280, "height": 800}

        mock_page.content = AsyncMock(return_value=mock_html)

        # Mock evaluate para retornar primeiro None (injecao de script), depois um elemento valido, e depois None para encerrar o loop sem duplicados
        mock_page.evaluate = AsyncMock(side_effect=[
            None,
            {
                "tagName": "button",
                "id": "b1",
                "className": "btn",
                "rect": {"x": 10, "y": 15, "width": 100, "height": 40}
            },
            None, None, None, None, None, None, None, None, None, None
        ])
        mock_page.evaluate_handle = AsyncMock(return_value=mock_active_el)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.src.services.browser.async_playwright", return_value=mock_pw):
            from backend.src.services.browser import fetch_rendered_html_screenshot_and_focus_states
            html, sshot, focus_sshots = await fetch_rendered_html_screenshot_and_focus_states("https://example.com", max_tabs=2)

        assert html == mock_html
        assert sshot == "ZmFrZV9wbmdfZGF0YQ=="
        assert len(focus_sshots) == 1
        assert focus_sshots[0] == "Y3JvcF9kYXRh"




# ── crawler.py ────────────────────────────────────────────────────────────────


class TestCrawlerHelpers:
    def test_is_internal_same_domain(self):
        from backend.src.services.crawler import _is_internal

        assert _is_internal("https://example.com", "https://example.com/about") is True

    def test_is_internal_www_stripped(self):
        from backend.src.services.crawler import _is_internal

        assert _is_internal("https://www.example.com", "https://example.com/page") is True

    def test_is_internal_relative(self):
        from backend.src.services.crawler import _is_internal

        assert _is_internal("https://example.com", "/contact") is True

    def test_is_internal_external(self):
        from backend.src.services.crawler import _is_internal

        assert _is_internal("https://example.com", "https://other.com/page") is False

    def test_should_skip_pdf(self):
        from backend.src.services.crawler import _should_skip

        assert _should_skip("https://example.com/doc.pdf") is True

    def test_should_skip_image(self):
        from backend.src.services.crawler import _should_skip

        assert _should_skip("https://example.com/img.png") is True

    def test_should_not_skip_html_page(self):
        from backend.src.services.crawler import _should_skip

        assert _should_skip("https://example.com/about") is False

    def test_should_not_skip_root(self):
        from backend.src.services.crawler import _should_skip

        assert _should_skip("https://example.com") is False

    def test_normalize_removes_trailing_slash(self):
        from backend.src.services.crawler import _normalize

        assert _normalize("https://example.com/page/") == "https://example.com/page"

    def test_normalize_removes_fragment(self):
        from backend.src.services.crawler import _normalize

        assert _normalize("https://example.com/page#section") == "https://example.com/page"

    def test_normalize_keeps_query(self):
        from backend.src.services.crawler import _normalize

        result = _normalize("https://example.com/search?q=test")
        assert "q=test" in result


class TestCrawlSite:
    @pytest.mark.asyncio
    async def test_crawl_respects_max_pages(self):
        """Crawler não deve visitar mais páginas do que max_pages."""
        html_with_many_links = """
        <html><body>
          <a href="/page1">P1</a><a href="/page2">P2</a>
          <a href="/page3">P3</a><a href="/page4">P4</a>
        </body></html>
        """

        with patch("backend.src.services.browser.fetch_rendered_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html_with_many_links
            from backend.src.services.crawler import crawl_site

            results = await crawl_site("https://example.com", max_pages=2)

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_crawl_max_pages_capped_at_50(self):
        """max_pages acima de 50 deve ser reduzido para 50."""
        call_count = 0
        async def mock_fetch_impl(url):
            nonlocal call_count
            call_count += 1
            return f'<html><body><a href="/page{call_count}">link</a></body></html>'

        with patch("backend.src.services.browser.fetch_rendered_html", side_effect=mock_fetch_impl):
            from backend.src.services.crawler import crawl_site

            results = await crawl_site("https://example.com", max_pages=999)

        assert len(results) <= 50

    @pytest.mark.asyncio
    async def test_crawl_handles_page_failure_gracefully(self):
        """Falha em uma página não deve interromper o crawl."""
        call_count = 0

        async def mock_fetch_impl(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection refused")
            return "<html><body>OK</body></html>"

        with patch("backend.src.services.browser.fetch_rendered_html", side_effect=mock_fetch_impl):
            from backend.src.services.crawler import crawl_site

            results = await crawl_site("https://example.com", max_pages=2)

        # Deve retornar resultado com erro, não levantar excecao
        assert len(results) >= 1
        failed = [r for r in results if not r.success]
        assert len(failed) >= 1
        assert failed[0].error is not None


class TestCrawlSiteWithFirecrawl:
    @pytest.mark.asyncio
    async def test_crawl_site_with_firecrawl_success(self):
        """Deve usar Firecrawl para descobrir os links e buscar HTML via fetch_rendered_html."""
        from backend.src.config.settings import Settings
        fake_settings = Settings(secret_key="test_secret", firecrawl_api_key="fc-test-key")

        mock_links = ["https://example.com/1", "https://example.com/2"]

        with patch(
            "backend.src.config.settings.get_settings",
            return_value=fake_settings,
        ), patch(
            "backend.src.services.crawler._discover_site_links_firecrawl",
            return_value=mock_links,
        ) as map_mock, patch(
            "backend.src.services.browser.fetch_rendered_html",
            new=AsyncMock(return_value="<html>OK</html>"),
        ) as fetch_mock:
            from backend.src.services.crawler import crawl_site
            results = await crawl_site("https://example.com/1", max_pages=2)

        map_mock.assert_called_once_with("https://example.com/1", "fc-test-key", 2)
        assert fetch_mock.await_count == 2
        assert len(results) == 2
        assert results[0].url == "https://example.com/1"
        assert results[0].html == "<html>OK</html>"
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_crawl_site_with_firecrawl_fallback(self):
        """Deve cair de volta para o Playwright se o Firecrawl retornar None."""
        from backend.src.config.settings import Settings
        fake_settings = Settings(secret_key="test_secret", firecrawl_api_key="fc-test-key")

        with patch(
            "backend.src.config.settings.get_settings",
            return_value=fake_settings,
        ), patch(
            "backend.src.services.crawler._discover_site_links_firecrawl",
            return_value=None,
        ) as map_mock, patch(
            "backend.src.services.browser.fetch_rendered_html",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = "<html>Fallback</html>"
            from backend.src.services.crawler import crawl_site
            results = await crawl_site("https://example.com/1", max_pages=1)

        map_mock.assert_called_once()
        assert len(results) == 1
        assert results[0].html == "<html>Fallback</html>"
        assert results[0].success is True


class TestFetchRenderedHtmlWithAuthenticationAndActions:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser._fetch_via_direct_browser", new_callable=AsyncMock)
    async def test_fetch_rendered_html_direct_browser_called(self, mock_direct):
        mock_direct.return_value = ("<html>authenticated</html>", "fake_screenshot", None)
        from backend.src.services.browser import fetch_rendered_html

        cookies = [{"name": "test", "value": "123"}]
        headers = {"Authorization": "Bearer test"}
        actions = [{"type": "click", "selector": "button"}]

        res = await fetch_rendered_html(
            "https://example.com",
            cookies=cookies,
            auth_headers=headers,
            actions=actions
        )

        assert res == "<html>authenticated</html>"
        mock_direct.assert_called_once_with(
            url="https://example.com",
            ws_url=ANY,
            cookies=cookies,
            auth_headers=headers,
            actions=actions
        )

    @pytest.mark.asyncio
    @patch("backend.src.services.browser._fetch_via_direct_browser", new_callable=AsyncMock)
    async def test_fetch_rendered_html_and_screenshot_direct_browser_called(self, mock_direct):
        mock_direct.return_value = ("<html>authenticated</html>", "fake_screenshot", None)
        from backend.src.services.browser import fetch_rendered_html_and_screenshot

        cookies = [{"name": "test", "value": "123"}]

        html, sshot = await fetch_rendered_html_and_screenshot(
            "https://example.com",
            cookies=cookies
        )

        assert html == "<html>authenticated</html>"
        assert sshot == "fake_screenshot"
        mock_direct.assert_called_once_with(
            url="https://example.com",
            ws_url=ANY,
            cookies=cookies,
            auth_headers=None,
            actions=None
        )

    @pytest.mark.asyncio
    @patch("backend.src.services.browser._fetch_via_direct_browser", new_callable=AsyncMock)
    async def test_fetch_rendered_html_screenshot_and_focus_states_direct_browser_called(self, mock_direct):
        mock_direct.return_value = ("<html>authenticated</html>", "fake_screenshot", ["focus1"])
        from backend.src.services.browser import fetch_rendered_html_screenshot_and_focus_states

        cookies = [{"name": "test", "value": "123"}]

        html, sshot, focus = await fetch_rendered_html_screenshot_and_focus_states(
            "https://example.com",
            max_tabs=5,
            cookies=cookies
        )

        assert html == "<html>authenticated</html>"
        assert sshot == "fake_screenshot"
        assert focus == ["focus1"]
        mock_direct.assert_called_once_with(
            url="https://example.com",
            ws_url=ANY,
            cookies=cookies,
            auth_headers=None,
            actions=None,
            max_tabs=5
        )

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.async_playwright")
    async def test_direct_browser_execution_flow(self, mock_pw_ctx):
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>loaded</html>")
        mock_page.screenshot = AsyncMock(return_value=b"fake_png")

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=False)

        mock_pw_ctx.return_value = mock_pw

        from backend.src.services.browser import _fetch_via_direct_browser

        cookies = [{"name": "test", "value": "123"}]
        headers = {"Authorization": "Bearer 123"}
        actions = [
            {"type": "click", "selector": "#btn"},
            {"type": "type", "selector": "#input", "text": "hello"},
            {"type": "wait", "selector": "#loaded"},
            {"type": "wait_time", "ms": 500}
        ]

        html, screenshot, focus = await _fetch_via_direct_browser(
            url="https://example.com",
            ws_url="ws://fake-browserless",
            cookies=cookies,
            auth_headers=headers,
            actions=actions,
            max_tabs=None
        )

        assert html == "<html>loaded</html>"
        assert screenshot == "ZmFrZV9wbmc="
        assert focus is None

        mock_context.add_cookies.assert_called_once_with([
            {"name": "test", "value": "123", "url": "https://example.com"}
        ])
        mock_context.set_extra_http_headers.assert_called_once_with(headers)
        mock_page.goto.assert_called_once_with("https://example.com", timeout=30000, wait_until="load")
        mock_page.click.assert_called_once_with("#btn", timeout=5000)
        mock_page.fill.assert_called_once_with("#input", "hello", timeout=5000)
        mock_page.wait_for_selector.assert_called_once_with("#loaded", timeout=5000)
        mock_page.wait_for_timeout.assert_called_once_with(500)


class TestCrawlSiteWithAuthentication:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.fetch_rendered_html", new_callable=AsyncMock)
    async def test_crawl_site_passes_auth_parameters(self, mock_fetch):
        mock_fetch.return_value = "<html><body><a href='/p1'>link</a></body></html>"
        from backend.src.services.crawler import crawl_site

        cookies = [{"name": "session", "value": "abc"}]
        headers = {"Authorization": "Token 123"}

        results = await crawl_site(
            "https://example.com",
            max_pages=2,
            cookies=cookies,
            auth_headers=headers
        )

        assert len(results) >= 1
        mock_fetch.assert_any_call(
            "https://example.com",
            cookies=cookies,
            auth_headers=headers
        )



class TestFormatAccessibilityNode:
    """Achado real (2026-08-11, Task #25): motor real de anúncio de leitor de
    tela, via a árvore de acessibilidade que o Playwright/Chromium já expõe
    (page.accessibility.snapshot) -- não uma estimativa da IA."""

    def test_formats_role_and_name(self):
        from backend.src.services.browser import _format_accessibility_node

        node = {"role": "button", "name": "Salvar", "pressed": True}
        lines: list[str] = []
        _format_accessibility_node(node, 0, lines)
        assert lines == ['- button: "Salvar" [pressed=True]']

    def test_missing_accessible_name_is_flagged_explicitly(self):
        """O caso mais importante: nome vazio/ausente vira um aviso explícito
        e inequívoco, não uma string vazia silenciosa."""
        from backend.src.services.browser import _format_accessibility_node

        node = {"role": "link", "name": ""}
        lines: list[str] = []
        _format_accessibility_node(node, 0, lines)
        assert lines == ["- link: (SEM NOME ACESSÍVEL)"]

    def test_recurses_into_children_with_indentation(self):
        from backend.src.services.browser import _format_accessibility_node

        node = {
            "role": "WebArea", "name": "Página",
            "children": [
                {"role": "button", "name": "OK"},
                {"role": "link", "name": ""},
            ],
        }
        lines: list[str] = []
        _format_accessibility_node(node, 0, lines)
        assert lines == [
            '- WebArea: "Página"',
            '  - button: "OK"',
            "  - link: (SEM NOME ACESSÍVEL)",
        ]

    def test_truncates_at_max_lines(self):
        from backend.src.services.browser import _A11Y_SNAPSHOT_MAX_LINES, _format_accessibility_node

        node = {"role": "list", "name": "", "children": [
            {"role": "listitem", "name": f"item {i}"} for i in range(_A11Y_SNAPSHOT_MAX_LINES + 20)
        ]}
        lines: list[str] = []
        _format_accessibility_node(node, 0, lines)
        assert len(lines) <= _A11Y_SNAPSHOT_MAX_LINES + 1  # +1 pela linha de truncamento


class TestFetchAccessibilityTreeSnapshot:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    async def test_returns_empty_string_without_browserless_configured(self, mock_settings):
        """Sem BROWSERLESS_WS_URL, best-effort -- não derruba a análise."""
        mock_settings.return_value.browserless_ws_url = None

        from backend.src.services.browser import fetch_accessibility_tree_snapshot
        result = await fetch_accessibility_tree_snapshot("https://example.com")
        assert result == ""

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser.async_playwright")
    async def test_returns_formatted_tree_on_success(self, mock_pw, mock_settings):
        mock_settings.return_value.browserless_ws_url = "wss://fake-browserless"

        mock_page = AsyncMock()
        mock_page.accessibility.snapshot = AsyncMock(
            return_value={"role": "WebArea", "name": "Teste", "children": [
                {"role": "button", "name": "Enviar"},
            ]}
        )
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        from backend.src.services.browser import fetch_accessibility_tree_snapshot
        result = await fetch_accessibility_tree_snapshot("https://example.com")

        assert '"Teste"' in result
        assert '"Enviar"' in result
        mock_page.goto.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser.async_playwright")
    async def test_returns_empty_string_on_navigation_failure(self, mock_pw, mock_settings):
        """Best-effort real: falha de rede/navegação não propaga -- só devolve
        string vazia, análise continua sem a árvore real."""
        mock_settings.return_value.browserless_ws_url = "wss://fake-browserless"
        mock_pw.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("conexao recusada"))

        from backend.src.services.browser import fetch_accessibility_tree_snapshot
        result = await fetch_accessibility_tree_snapshot("https://example.com")
        assert result == ""


class TestFetchAccessibilityTreeNodes:
    """Versão estruturada (achatada) da árvore real, usada por
    screen_reader_verification.py -- compartilha a mesma captura CDP de
    `fetch_accessibility_tree_snapshot` via `_capture_raw_accessibility_snapshot`."""

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    async def test_returns_empty_list_without_browserless_configured(self, mock_settings):
        mock_settings.return_value.browserless_ws_url = None

        from backend.src.services.browser import fetch_accessibility_tree_nodes
        result = await fetch_accessibility_tree_nodes("https://example.com")
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser.async_playwright")
    async def test_flattens_tree_and_marks_interactive_roles(self, mock_pw, mock_settings):
        mock_settings.return_value.browserless_ws_url = "wss://fake-browserless"

        mock_page = AsyncMock()
        mock_page.accessibility.snapshot = AsyncMock(
            return_value={
                "role": "WebArea", "name": "Teste",
                "children": [
                    {"role": "heading", "name": "Titulo da pagina"},
                    {"role": "button", "name": "Enviar formulario de contato"},
                    {"role": "button", "name": ""},
                ],
            }
        )
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        from backend.src.services.browser import fetch_accessibility_tree_nodes
        nodes = await fetch_accessibility_tree_nodes("https://example.com")

        assert len(nodes) == 4  # WebArea + heading + 2 buttons
        by_role_name = {(n.role, n.name): n for n in nodes}
        assert by_role_name[("heading", "Titulo da pagina")].is_interactive is False
        assert by_role_name[("button", "Enviar formulario de contato")].is_interactive is True
        assert by_role_name[("button", "")].is_interactive is True
        assert by_role_name[("button", "")].path == "WebArea > button"

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.get_settings")
    @patch("backend.src.services.browser.async_playwright")
    async def test_returns_empty_list_on_navigation_failure(self, mock_pw, mock_settings):
        mock_settings.return_value.browserless_ws_url = "wss://fake-browserless"
        mock_pw.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("conexao recusada"))

        from backend.src.services.browser import fetch_accessibility_tree_nodes
        result = await fetch_accessibility_tree_nodes("https://example.com")
        assert result == []


class TestDiffCrossBrowserViolations:
    """Achado real (2026-08-11, pedido do usuário): comportamento de
    acessibilidade difere entre motores de navegador -- este diff identifica
    quais violações aparecem só em alguns motores, não em todos."""

    def test_no_differences_when_all_engines_agree(self):
        from backend.src.services.browser import diff_cross_browser_violations

        per_engine = {
            "chromium": {"success": True, "results": {"violations": [{"id": "image-alt"}]}},
            "firefox": {"success": True, "results": {"violations": [{"id": "image-alt"}]}},
            "webkit": {"success": True, "results": {"violations": [{"id": "image-alt"}]}},
        }
        diff = diff_cross_browser_violations(per_engine)
        assert diff["engines_succeeded"] == ["chromium", "firefox", "webkit"]
        assert diff["engines_failed"] == []
        assert diff["cross_browser_only_differences"] == {}

    def test_detects_rule_found_only_in_some_engines(self):
        from backend.src.services.browser import diff_cross_browser_violations

        per_engine = {
            "chromium": {"success": True, "results": {"violations": [{"id": "color-contrast"}]}},
            "firefox": {"success": True, "results": {"violations": []}},
            "webkit": {"success": True, "results": {"violations": [{"id": "color-contrast"}]}},
        }
        diff = diff_cross_browser_violations(per_engine)
        assert diff["cross_browser_only_differences"] == {"color-contrast": ["chromium", "webkit"]}

    def test_failed_engine_excluded_from_comparison_not_treated_as_zero_violations(self):
        """Um motor que falhou ao rodar (não instalado, timeout) não deve
        contar como "achou zero violações" -- isso mascararia diferenças reais
        como se fossem confirmadas por todos os motores."""
        from backend.src.services.browser import diff_cross_browser_violations

        per_engine = {
            "chromium": {"success": True, "results": {"violations": [{"id": "link-name"}]}},
            "firefox": {"success": False, "error": "Executable doesn't exist"},
        }
        diff = diff_cross_browser_violations(per_engine)
        assert diff["engines_succeeded"] == ["chromium"]
        assert diff["engines_failed"] == ["firefox"]
        # Só 1 motor rodou com sucesso -- nada "só em alguns" quando só há um.
        assert diff["cross_browser_only_differences"] == {}


class TestRunAxeCoreCrossBrowserAudit:
    @pytest.mark.asyncio
    @patch("backend.src.services.browser.async_playwright")
    async def test_runs_all_three_engines_and_returns_per_engine_results(self, mock_pw):
        from backend.src.services.browser import run_axe_core_cross_browser_audit

        mock_page = AsyncMock()
        mock_page.accessibility = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"violations": [{"id": "image-alt"}], "incomplete": []})
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_launcher = AsyncMock()
        mock_launcher.launch = AsyncMock(return_value=mock_browser)

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium = mock_launcher
        mock_pw_instance.firefox = mock_launcher
        mock_pw_instance.webkit = mock_launcher
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await run_axe_core_cross_browser_audit("https://example.com")

        assert set(result["per_engine"].keys()) == {"chromium", "firefox", "webkit"}
        for engine_data in result["per_engine"].values():
            assert engine_data["success"] is True
            assert engine_data["results"]["violations"][0]["id"] == "image-alt"

    @pytest.mark.asyncio
    @patch("backend.src.services.browser.async_playwright")
    async def test_one_engine_failing_does_not_block_the_others(self, mock_pw):
        """Best-effort por motor: um motor não instalado/falhando não derruba
        a auditoria inteira -- os outros dois continuam e o resultado indica
        exatamente qual falhou."""
        from backend.src.services.browser import run_axe_core_cross_browser_audit

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"violations": [], "incomplete": []})
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        working_launcher = AsyncMock()
        working_launcher.launch = AsyncMock(return_value=mock_browser)
        broken_launcher = AsyncMock()
        broken_launcher.launch = AsyncMock(side_effect=RuntimeError("Executable doesn't exist"))

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium = working_launcher
        mock_pw_instance.firefox = broken_launcher
        mock_pw_instance.webkit = working_launcher
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await run_axe_core_cross_browser_audit("https://example.com")

        assert result["per_engine"]["chromium"]["success"] is True
        assert result["per_engine"]["webkit"]["success"] is True
        assert result["per_engine"]["firefox"]["success"] is False
        assert "Executable" in result["per_engine"]["firefox"]["error"]
