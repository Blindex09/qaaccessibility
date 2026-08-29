"""
browser.py — Servico de rendering via Playwright Remoto (CDP / Browserless) e Firecrawl.

Responsabilidade: capturar o HTML (e screenshot) de uma URL de forma 100% remota,
utilizando o Firecrawl para extração e o Browserless CDP para rendering e screenshots.

Regras (README):
- Zero emojis em logger (cp1252)
- Imports no topo
- Zero keywords hardcoded
- Logger com getLogger(__name__)
"""

import asyncio
import base64
import json
import logging
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

from backend.src.config.settings import get_settings

logger = logging.getLogger(__name__)

_AXE_CORE_JS_PATH = Path(__file__).resolve().parent.parent / "resources" / "vendor" / "axe.min.js"

# Tempo maximo de espera para networkidle (ms)
_NETWORK_IDLE_TIMEOUT = 20_000
# Tempo maximo total de navegacao (ms)
_NAV_TIMEOUT = 30_000
# User-agent moderno para evitar bloqueios de bot
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_INJECT_GEOMETRY_JS = """() => {
    const elements = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [onclick], [role="menuitem"], [role="tab"]'));
    const rects = elements.map(el => {
        const rect = el.getBoundingClientRect();
        return { el, rect };
    }).filter(item => item.rect.width > 0 || item.rect.height > 0);

    rects.forEach(({ el, rect }) => {
        el.setAttribute('data-rendered-width', Math.round(rect.width).toString());
        el.setAttribute('data-rendered-height', Math.round(rect.height).toString());

        let minDistance = 9999;
        rects.forEach(other => {
            if (other.el === el) return;
            const dx = Math.max(0, rect.left - other.rect.right, other.rect.left - rect.right);
            const dy = Math.max(0, rect.top - other.rect.bottom, other.rect.top - rect.bottom);
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < minDistance) {
                minDistance = dist;
            }
        });

        if (minDistance < 9999) {
            el.setAttribute('data-closest-spacing', Math.round(minDistance).toString());
        }

        const style = window.getComputedStyle(el);
        const bgImage = style.backgroundImage || '';
        const opacity = style.opacity || '1';
        if (bgImage.includes('url(') || bgImage.includes('gradient') || opacity !== '1') {
            el.setAttribute('data-complex-bg', 'true');
        }
    });
}"""


def _inject_base_tag(html: str, url: str) -> str:
    """Injeta a tag <base href="..."> no head do HTML para resolver recursos relativos."""
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.head:
            # Remove base tags existentes
            for base in soup.find_all("base"):
                base.decompose()
            # Cria a nova tag base apontando para a URL original da página
            new_base = soup.new_tag("base", href=url)
            soup.head.insert(0, new_base)
            return str(soup)
    except Exception as exc:
        logger.warning("[Browser] Falha ao injetar tag <base>: %s", exc)
    return html


def _scrape_with_firecrawl(url: str, api_key: str) -> str:
    """
    Realiza o scrape da URL usando a API do Firecrawl (/v2/scrape) retornando o HTML.
    """
    logger.info("[Browser] Executando scrape do Firecrawl para: %s", url)
    req_url = "https://api.firecrawl.dev/v2/scrape"
    payload = {"url": url, "formats": ["html"]}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(req_url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        if not res_data.get("success") or "data" not in res_data:
            raise RuntimeError(f"Erro no scrape do Firecrawl: {res_data.get('error', 'Resposta invalida')}")
        return res_data["data"].get("html") or ""


async def _fetch_via_direct_browser(
    url: str,
    ws_url: str | None = None,
    cookies: list[dict] | None = None,
    auth_headers: dict[str, str] | None = None,
    actions: list[dict] | None = None,
    max_tabs: int | None = None,
) -> tuple[str, str, list[str] | None]:
    """
    Navega diretamente para a URL usando Playwright CDP,
    aplica cookies/headers, executa as ações de fluxo interativo e extrai o HTML,
    screenshot e focus states.
    """
    if not ws_url:
        raise ValueError("Configuração ausente: BROWSERLESS_WS_URL e obrigatória para navegacao no direct browser.")
    logger.info("[Browser] Executando navegacao direta para: %s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws_url)

        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        if cookies:
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            formatted_cookies = []
            for c in cookies:
                cookie_copy = c.copy()
                if "url" not in cookie_copy and "domain" not in cookie_copy:
                    cookie_copy["url"] = origin
                formatted_cookies.append(cookie_copy)
            await context.add_cookies(formatted_cookies)  # type: ignore[arg-type]  # dicts already match Playwright's SetCookieParam shape at runtime

        if auth_headers:
            await context.set_extra_http_headers(auth_headers)

        page = await context.new_page()
        try:
            await page.goto(url, timeout=_NAV_TIMEOUT, wait_until="load")

            # Executa as ações ordenadas
            if actions:
                for act in actions:
                    act_type = act.get("type")
                    selector = act.get("selector")
                    if act_type == "click" and selector:
                        await page.click(selector, timeout=5000)
                    elif act_type == "type" and selector:
                        text = act.get("text", "")
                        await page.fill(selector, text, timeout=5000)
                    elif act_type == "wait" and selector:
                        await page.wait_for_selector(selector, timeout=5000)
                    elif act_type == "wait_time":
                        ms = act.get("ms", 1000)
                        await page.wait_for_timeout(ms)

            try:
                await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
            except PWTimeout:
                logger.warning("[Browser] Timeout networkidle na navegacao direta para %s", url)

            # Injeta atributos de geometria
            await page.evaluate(_INJECT_GEOMETRY_JS)
            updated_html = await page.content()

            # Captura de tela principal
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Simulacao de focus states se max_tabs for solicitado
            focus_screenshots = None
            if max_tabs is not None:
                focus_screenshots = []
                seen_elements = set()
                for _ in range(max_tabs):
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(50)

                    active_info = await page.evaluate("""() => {
                        const el = document.activeElement;
                        if (!el || el === document.body || el === document.documentElement) return null;
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return null;
                        return {
                            tagName: el.tagName.toLowerCase(),
                            id: el.id || "",
                            className: el.className || "",
                            rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                        };
                    }""")

                    if not active_info:
                        continue

                    key = f"{active_info['tagName']}|{active_info['id']}|{active_info['rect']['x']:.1f}|{active_info['rect']['y']:.1f}"
                    if key in seen_elements:
                        continue
                    seen_elements.add(key)

                    active_element = await page.evaluate_handle("document.activeElement")
                    active_element_handle = active_element.as_element() if active_element else None
                    if active_element_handle:
                        box = await active_element_handle.bounding_box()
                        if box:
                            padding = 20
                            viewport = page.viewport_size or {"width": 1280, "height": 800}

                            x = max(0.0, box["x"] - padding)
                            y = max(0.0, box["y"] - padding)
                            w = min(viewport["width"] - x, box["width"] + 2 * padding)
                            h = min(viewport["height"] - y, box["height"] + 2 * padding)

                            if w > 0 and h > 0:
                                crop_bytes = await page.screenshot(
                                    clip={"x": x, "y": y, "width": w, "height": h}, type="png"
                                )
                                crop_b64 = base64.b64encode(crop_bytes).decode("utf-8")
                                focus_screenshots.append(crop_b64)

            return updated_html, screenshot_base64, focus_screenshots
        finally:
            await context.close()
            browser_closed = False
            for _attempt in range(3):
                try:
                    await browser.close()
                    browser_closed = True
                    break
                except Exception:
                    await asyncio.sleep(0.5)
            if not browser_closed:
                logger.warning("[Browser] Não foi possivel fechar o browser remotamente de forma limpa.")


_A11Y_SNAPSHOT_MAX_LINES = 150


def _format_accessibility_node(node: dict[str, Any], depth: int, lines: list[str]) -> None:
    """Formata um nó da árvore de acessibilidade REAL (computada pelo motor de
    acessibilidade do Chromium via `page.accessibility.snapshot`) em uma linha
    legível pro LLM -- role, nome acessível (ou aviso explícito de ausência) e
    estado (checked/pressed/expanded/etc), recursivamente pelos filhos."""
    if len(lines) >= _A11Y_SNAPSHOT_MAX_LINES:
        return
    role = node.get("role", "")
    name = node.get("name", "")
    extras = [
        f"{key}={node[key]}"
        for key in ("checked", "pressed", "expanded", "selected", "disabled", "required", "invalid", "value")
        if node.get(key) not in (None, False, "")
    ]
    extras_str = f" [{', '.join(extras)}]" if extras else ""
    name_str = f'"{name}"' if name else "(SEM NOME ACESSÍVEL)"
    lines.append("  " * depth + f"- {role}: {name_str}{extras_str}")
    for child in node.get("children") or []:
        _format_accessibility_node(child, depth + 1, lines)
        if len(lines) >= _A11Y_SNAPSHOT_MAX_LINES:
            lines.append("  " * depth + "  ... (árvore truncada)")
            return


async def _capture_raw_accessibility_snapshot(url: str) -> dict[str, Any] | None:
    """Abre a URL num Chromium remoto (Browserless/CDP) e devolve a árvore de
    acessibilidade bruta (`page.accessibility.snapshot`), sem formatação.

    Núcleo compartilhado por `fetch_accessibility_tree_snapshot` (formata como
    texto pro prompt do LLM) e `fetch_accessibility_tree_nodes` (achata em
    lista estruturada pra verificação determinística -- ver
    `screen_reader_verification.py`). Best-effort: devolve None sem
    BROWSERLESS_WS_URL configurado, se a navegação falhar, ou se a página não
    expuser nós "interesting"; nunca levanta exceção pro chamador."""
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)
    if not ws_url:
        return None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(ws_url)
            try:
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                page = await context.new_page()
                await page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
                except PWTimeout:
                    logger.warning("[Browser] networkidle timeout na captura da árvore de acessibilidade real: %s", url)
                accessibility = getattr(page, "accessibility", None)
                snapshot = await accessibility.snapshot(interesting_only=True) if accessibility else None
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning("[Browser] Falha ao capturar árvore de acessibilidade real de %s: %s", url, exc)
        return None

    return snapshot or None


async def fetch_accessibility_tree_snapshot(url: str) -> str:
    """Captura a árvore de acessibilidade REAL da página, computada pelo motor
    de acessibilidade do navegador real (Chromium via Playwright/CDP) -- não
    uma estimativa da IA a partir do HTML bruto. É a mesma API que motores de
    assistive technology consultam via a árvore de acessibilidade do SO, então
    um nó com nome vazio aqui é uma violação confirmada pelo próprio
    navegador, não um chute.

    Best-effort: nunca derruba a análise. Devolve string vazia se
    BROWSERLESS_WS_URL não estiver configurado, se a navegação falhar, ou se
    a página não expuser nós "interesting" (ex.: página em branco)."""
    snapshot = await _capture_raw_accessibility_snapshot(url)
    if not snapshot:
        return ""
    lines: list[str] = []
    _format_accessibility_node(snapshot, 0, lines)
    return "\n".join(lines)


# Roles ARIA/HTML que representam controles interativos -- um leitor de tela
# SEMPRE anuncia o nome acessível desses (nunca só o role) antes do usuário
# poder agir sobre eles. Fonte: W3C WAI-ARIA APG (mesma lista de referência
# usada por `widgets_a11y`/`aria_specialist`), restrita aos papéis que
# `page.accessibility.snapshot()` de fato emite no Chromium.
_INTERACTIVE_AT_ROLES = frozenset(
    {
        "button",
        "link",
        "checkbox",
        "radio",
        "switch",
        "textbox",
        "combobox",
        "listbox",
        "slider",
        "spinbutton",
        "tab",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "searchbox",
    }
)


@dataclass(frozen=True)
class AccessibilityTreeNode:
    """Um nó achatado da árvore de acessibilidade REAL, com o caminho de roles
    dos ancestrais preservado (útil pra descrever ONDE o nó está sem reprocessar
    a árvore inteira de novo)."""

    role: str
    name: str
    path: str  # ex.: "WebArea > main > button"
    is_interactive: bool


def _flatten_accessibility_node(node: dict[str, Any], ancestors: str, nodes: list[AccessibilityTreeNode]) -> None:
    role = str(node.get("role", ""))
    name = str(node.get("name", ""))
    path = f"{ancestors} > {role}" if ancestors else role
    nodes.append(AccessibilityTreeNode(role=role, name=name, path=path, is_interactive=role in _INTERACTIVE_AT_ROLES))
    for child in node.get("children") or []:
        _flatten_accessibility_node(child, path, nodes)


async def fetch_accessibility_tree_nodes(url: str) -> list[AccessibilityTreeNode]:
    """Versão estruturada (achatada) da árvore de acessibilidade REAL, pra
    verificação determinística (ver `screen_reader_verification.py`) em vez de
    formatação textual pro prompt do LLM (`fetch_accessibility_tree_snapshot`,
    acima -- ambas compartilham a mesma captura via `_capture_raw_accessibility_snapshot`).

    Lista vazia nos mesmos casos best-effort da função irmã (sem Browserless
    configurado, navegação falhou, página sem nós "interesting")."""
    snapshot = await _capture_raw_accessibility_snapshot(url)
    if not snapshot:
        return []
    nodes: list[AccessibilityTreeNode] = []
    _flatten_accessibility_node(snapshot, "", nodes)
    return nodes


async def fetch_rendered_html(
    url: str,
    cookies: list[dict] | None = None,
    auth_headers: dict[str, str] | None = None,
    actions: list[dict] | None = None,
) -> str:
    """
    Captura o HTML de uma URL usando Firecrawl de forma obrigatória (sem fallback),
    ou via Playwright direto se cookies/headers/ações de fluxo interativo forem fornecidos.
    """
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)

    # Se dados de autenticacao/fluxo forem fornecidos, fazemos a navegacao direta
    if cookies or auth_headers or actions:
        html, _, _ = await _fetch_via_direct_browser(
            url=url,
            ws_url=ws_url,
            cookies=cookies,
            auth_headers=auth_headers,
            actions=actions,
        )
        return html

    firecrawl_key = getattr(settings, "firecrawl_api_key", None)
    if not firecrawl_key:
        raise ValueError("Configuração ausente: FIRECRAWL_API_KEY e obrigatória para a análise.")

    html = _scrape_with_firecrawl(url, firecrawl_key)
    if not html:
        raise RuntimeError(f"Firecrawl não conseguiu obter o HTML para a URL: {url}")
    return html


async def fetch_rendered_html_and_screenshot(
    url: str,
    cookies: list[dict] | None = None,
    auth_headers: dict[str, str] | None = None,
    actions: list[dict] | None = None,
) -> tuple[str, str]:
    """
    Extrai o HTML e gera o screenshot. Se cookies/headers/ações forem fornecidos,
    usa a navegacao direta via Playwright; caso contrario, extrai via Firecrawl e renderiza no CDP.
    """
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)

    if cookies or auth_headers or actions:
        html, screenshot, _ = await _fetch_via_direct_browser(
            url=url,
            ws_url=ws_url,
            cookies=cookies,
            auth_headers=auth_headers,
            actions=actions,
        )
        return html, screenshot

    firecrawl_key = getattr(settings, "firecrawl_api_key", None)
    if not firecrawl_key or not ws_url:
        raise ValueError("Configuração ausente: FIRECRAWL_API_KEY e BROWSERLESS_WS_URL sao obrigatórios.")

    # 1. Extração via Firecrawl
    html = _scrape_with_firecrawl(url, firecrawl_key)
    if not html:
        raise RuntimeError(f"Firecrawl não retornou HTML para: {url}")

    # 2. Rendering e Screenshot via Playwright CDP remoto
    logger.info("[Browser] Conectando via CDP ao Browserless para Screenshot: %s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws_url)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            html_with_base = _inject_base_tag(html, url)
            await page.set_content(html_with_base, timeout=_NAV_TIMEOUT)

            try:
                await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
            except PWTimeout:
                logger.warning("[Browser] networkidle timeout para screenshot %s", url)

            await page.evaluate(_INJECT_GEOMETRY_JS)
            updated_html = await page.content()

            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return updated_html, screenshot_base64
        finally:
            await context.close()
            await browser.close()


async def fetch_rendered_html_screenshot_and_focus_states(
    url: str,
    max_tabs: int = 10,
    cookies: list[dict] | None = None,
    auth_headers: dict[str, str] | None = None,
    actions: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    """
    Extrai o HTML, gera screenshot e simula navegacoes Tab. Se cookies/headers/ações forem fornecidos,
    usa a navegacao direta via Playwright; caso contrario, extrai via Firecrawl e simula interacoes no CDP.
    """
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)

    if cookies or auth_headers or actions:
        html, screenshot, focus_screenshots = await _fetch_via_direct_browser(
            url=url,
            ws_url=ws_url,
            cookies=cookies,
            auth_headers=auth_headers,
            actions=actions,
            max_tabs=max_tabs,
        )
        return html, screenshot, focus_screenshots or []

    firecrawl_key = getattr(settings, "firecrawl_api_key", None)
    if not firecrawl_key or not ws_url:
        raise ValueError("Configuração ausente: FIRECRAWL_API_KEY e BROWSERLESS_WS_URL sao obrigatórios.")

    # 1. Extração via Firecrawl
    html = _scrape_with_firecrawl(url, firecrawl_key)
    if not html:
        raise RuntimeError(f"Firecrawl não retornou HTML para: {url}")

    # 2. Rendering interativo via Playwright CDP remoto
    logger.info("[Browser] Conectando via CDP ao Browserless para foco e tabs: %s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws_url)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            html_with_base = _inject_base_tag(html, url)
            await page.set_content(html_with_base, timeout=_NAV_TIMEOUT)

            try:
                await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
            except PWTimeout:
                logger.warning("[Browser] networkidle timeout para simulacao de foco %s", url)

            await page.evaluate(_INJECT_GEOMETRY_JS)
            updated_html = await page.content()

            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            focus_screenshots = []
            seen_elements = set()

            for _ in range(max_tabs):
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(50)

                active_info = await page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body || el === document.documentElement) return null;
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return null;
                    return {
                        tagName: el.tagName.toLowerCase(),
                        id: el.id || "",
                        className: el.className || "",
                        rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                    };
                }""")

                if not active_info:
                    continue

                key = f"{active_info['tagName']}|{active_info['id']}|{active_info['rect']['x']:.1f}|{active_info['rect']['y']:.1f}"
                if key in seen_elements:
                    continue
                seen_elements.add(key)

                active_element = await page.evaluate_handle("document.activeElement")
                active_element_handle = active_element.as_element() if active_element else None
                if active_element_handle:
                    box = await active_element_handle.bounding_box()
                    if box:
                        padding = 20
                        viewport = page.viewport_size or {"width": 1280, "height": 800}

                        x = max(0.0, box["x"] - padding)
                        y = max(0.0, box["y"] - padding)
                        w = min(viewport["width"] - x, box["width"] + 2 * padding)
                        h = min(viewport["height"] - y, box["height"] + 2 * padding)

                        if w > 0 and h > 0:
                            crop_bytes = await page.screenshot(
                                clip={"x": x, "y": y, "width": w, "height": h}, type="png"
                            )
                            crop_b64 = base64.b64encode(crop_bytes).decode("utf-8")
                            focus_screenshots.append(crop_b64)

            return updated_html, screenshot_base64, focus_screenshots
        finally:
            await context.close()
            await browser.close()


@lru_cache
def _load_axe_core_js() -> str:
    """Le o axe-core vendorizado uma unica vez por processo (arquivo de 580KB
    nao muda em runtime -- ver backend/src/resources/vendor/README.md)."""
    return _AXE_CORE_JS_PATH.read_text(encoding="utf-8")


def get_axe_core_js() -> str:
    """Acesso publico ao axe-core vendorizado, para quem injeta via outro
    driver (ex.: Selenium local em remote_runners.py) em vez do Playwright."""
    return _load_axe_core_js()


async def run_axe_core_audit(url: str) -> dict[str, Any]:
    """
    Roda o axe-core DE VERDADE (Deque Systems, vendorizado localmente) contra a
    pagina renderizada via CDP/Browserless -- o MESMO motor que cypress-axe,
    axe-playwright e axe-selenium-python usam por baixo dos panos.

    Achado real (auditoria 2026-08-10): os runners `run_remote_cypress_simulation`
    e `run_remote_selenium` em remote_runners.py nao rodavam Cypress nem Selenium
    nenhum -- so re-executavam o orquestrador de IA proprio do projeto e devolviam
    o resultado relabeled como "cypress_remote"/"selenium_remote". Esta funcao
    substitui isso por uma auditoria determinística e real, sem chamada de LLM.
    """
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)
    firecrawl_key = getattr(settings, "firecrawl_api_key", None)
    if not firecrawl_key or not ws_url:
        raise ValueError("Configuração ausente: FIRECRAWL_API_KEY e BROWSERLESS_WS_URL sao obrigatórios.")

    html = _scrape_with_firecrawl(url, firecrawl_key)
    if not html:
        raise RuntimeError(f"Firecrawl não retornou HTML para: {url}")

    axe_js = _load_axe_core_js()

    logger.info("[Browser] Conectando via CDP ao Browserless para auditoria axe-core real: %s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws_url)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            html_with_base = _inject_base_tag(html, url)
            await page.set_content(html_with_base, timeout=_NAV_TIMEOUT)
            try:
                await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
            except PWTimeout:
                logger.warning("[Browser] networkidle timeout para auditoria axe-core %s", url)

            await page.add_script_tag(content=axe_js)
            # axe.run() e assincrono (retorna Promise) -- page.evaluate aguarda
            # a resolucao antes de devolver o objeto pro Python.
            axe_results = await page.evaluate(
                "async () => { return await window.axe.run(document, { resultTypes: ['violations', 'incomplete'] }); }"
            )
            return axe_results
        finally:
            await context.close()
            await browser.close()


_CROSS_BROWSER_ENGINES = ("chromium", "firefox", "webkit")


async def run_axe_core_cross_browser_audit(url: str) -> dict[str, Any]:
    """Roda axe-core DE VERDADE contra os 3 motores de renderização reais que o
    Playwright empacota (Chromium, Firefox/Gecko, WebKit) -- não apenas
    Chromium via Browserless -- e compara os achados entre eles.

    Achado real do usuário (2026-08-11): comportamento de acessibilidade
    genuinamente difere entre motores (ex.: WebKit é o motor que o VoiceOver
    do macOS/iOS de fato usa; Firefox/Gecko tem sua própria implementação da
    árvore de acessibilidade, com bugs e comportamentos que Chromium não
    reproduz). Rodar só num motor mascara isso.

    Usa launch LOCAL de cada motor (não Browserless, que é só Chromium) --
    cada motor navega e executa o JS da página de forma independente, então
    diferenças de comportamento real (não só de renderização visual) ficam
    visíveis. Best-effort por motor: se um não estiver instalado/falhar, os
    outros dois continuam e o resultado indica exatamente quais rodaram.
    """
    axe_js = _load_axe_core_js()
    per_engine: dict[str, dict[str, Any]] = {}

    async with async_playwright() as pw:
        launchers = {"chromium": pw.chromium, "firefox": pw.firefox, "webkit": pw.webkit}

        async def _audit_engine(engine_name: str) -> tuple[str, dict[str, Any]]:
            try:
                browser = await launchers[engine_name].launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        ignore_https_errors=True,
                    )
                    page = await context.new_page()
                    await page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
                    except PWTimeout:
                        logger.warning(
                            "[Browser] networkidle timeout na auditoria cross-browser (%s): %s", engine_name, url
                        )
                    await page.add_script_tag(content=axe_js)
                    axe_results = await page.evaluate(
                        "async () => { return await window.axe.run(document, "
                        "{ resultTypes: ['violations', 'incomplete'] }); }"
                    )
                    return engine_name, {"success": True, "results": axe_results}
                finally:
                    await context.close()
                    await browser.close()
            except Exception as exc:
                logger.warning("[Browser] Falha ao rodar axe-core em %s para %s: %s", engine_name, url, exc)
                return engine_name, {"success": False, "error": str(exc)}

        results = await asyncio.gather(*[_audit_engine(engine_name) for engine_name in _CROSS_BROWSER_ENGINES])
        per_engine = dict(results)

    return {"url": url, "per_engine": per_engine}


def diff_cross_browser_violations(per_engine: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compara os IDs de regra violados entre os motores que rodaram com
    sucesso -- devolve quais violações aparecem em alguns motores mas não em
    todos (diferença de comportamento real entre engines, não estimativa)."""
    engine_rule_ids: dict[str, set[str]] = {}
    for engine, data in per_engine.items():
        if data.get("success"):
            violations = data.get("results", {}).get("violations", []) or []
            engine_rule_ids[engine] = {v.get("id", "") for v in violations}

    all_rules: set[str] = set()
    for ids in engine_rule_ids.values():
        all_rules |= ids

    differences: dict[str, list[str]] = {}
    for rule in sorted(all_rules):
        engines_with_rule = sorted(e for e, ids in engine_rule_ids.items() if rule in ids)
        if 0 < len(engines_with_rule) < len(engine_rule_ids):
            differences[rule] = engines_with_rule

    return {
        "engines_succeeded": sorted(engine_rule_ids.keys()),
        "engines_failed": sorted(e for e, d in per_engine.items() if not d.get("success")),
        "cross_browser_only_differences": differences,
    }
