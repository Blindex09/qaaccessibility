"""
crawler.py — Servico de crawling de sites para análise de acessibilidade.

Responsabilidade: descobrir e visitar todas as páginas internas de um site
usando o Firecrawl cloud crawler (se publico) ou crawling local baseado em BeautifulSoup.

Regras (README):
- Zero emojis em logger (cp1252)
- Imports no topo
- Zero keywords hardcoded
- Logger com getLogger(__name__)
"""

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_SKIP_EXTENSIONS = {
    ".pdf",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".csv",
}


def _is_internal(base: str, href: str) -> bool:
    """Retorna True se href pertence ao mesmo dominio que base."""
    try:
        base_host = urlparse(base).netloc.lower().removeprefix("www.")
        href_parsed = urlparse(urljoin(base, href))
        href_host = href_parsed.netloc.lower().removeprefix("www.")
        if not href_host:
            return True
        return href_host == base_host
    except Exception:
        return False


def _should_skip(url: str) -> bool:
    """Retorna True para URLs que não sao páginas HTML (arquivos, fragmentos)."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if parsed.fragment and not parsed.path:
        return True
    ext = "." + path.rsplit(".", 1)[-1] if "." in path.split("/")[-1] else ""
    return ext in _SKIP_EXTENSIONS


def _normalize(url: str) -> str:
    """Remove fragmentos e trailing slash para deduplicacao."""
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    return clean.geturl().rstrip("/")


def _extract_links_soup(html_content: str, page_url: str, site_url: str | None = None) -> list[str]:
    """Extrai os links internos de uma página HTML usando BeautifulSoup.

    `page_url` e a URL DA PAGINA onde o link aparece -- e a base correta para
    resolver href relativo. `site_url` e a raiz do crawl, usada so para decidir
    se o link continua no mesmo dominio.

    A distincao importa: com uma base unica, um href relativo (`../c.html`) numa
    subpagina de outro diretorio resolvia contra a URL INICIAL do crawl, gerando
    caminhos que nao existem -- as paginas descobertas a partir do segundo nivel
    saiam erradas.
    """
    from bs4 import BeautifulSoup

    dominio = site_url or page_url
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
                continue
            full = _normalize(urljoin(page_url, href))
            if _is_internal(dominio, full) and not _should_skip(full):
                links.append(full)
        return links
    except Exception as exc:
        logger.warning("[Crawler] Falha ao extrair links com BeautifulSoup: %s", exc)
        return []


class CrawlPageResult:
    """Resultado de uma página crawleada."""

    def __init__(self, url: str, html: str, error: str | None = None):
        self.url = url
        self.html = html
        self.error = error
        self.success = error is None


def _discover_site_links_firecrawl(url: str, api_key: str, limit: int = 10) -> list[str] | None:
    """Usa o endpoint /v2/map do Firecrawl para obter links internos rapidamente."""
    req_url = "https://api.firecrawl.dev/v2/map"
    payload = {"url": url, "limit": limit}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(req_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("success") and isinstance(res_data.get("links"), list):
                raw_links = res_data["links"]
                links: list[str] = []
                for lnk in raw_links:
                    if not lnk:
                        continue
                    url_str = str(lnk["url"]).strip() if isinstance(lnk, dict) and "url" in lnk else str(lnk).strip()
                    if url_str and url_str.startswith("http") and url_str not in links:
                        links.append(url_str)
                if url not in links:
                    links.insert(0, url)
                return links[:limit]
    except Exception as exc:
        logger.error("[Firecrawl] Falha no /v2/map para %s: %s", url, exc)
    return None


async def crawl_site(
    start_url: str,
    max_pages: int = 10,
    cookies: list[dict] | None = None,
    auth_headers: dict[str, str] | None = None,
) -> list[CrawlPageResult]:
    """
    Crawlea um site a partir de start_url, visitando páginas internas.
    Se o Firecrawl estiver configurado e a URL for publica, usa o Firecrawl
    para mapear os links e depois busca cada link.

    Args:
        start_url: URL raiz do site
        max_pages: Limite de páginas (padrão: 10, maximo: 50)
        cookies: Cookies opcionais para sessao de autenticacao
        auth_headers: Cabecalhos HTTP opcionais extras

    Returns:
        Lista de CrawlPageResult — uma por página visitada.
    """
    max_pages = min(max_pages, 50)
    logger.info("[Crawler] Iniciando crawl: %s (max %d páginas)", start_url, max_pages)

    from backend.src.config.settings import get_settings

    settings = get_settings()

    is_public = True
    hostname = urlparse(start_url).hostname or ""
    if (
        hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0")
        or hostname.endswith(".test")
        or hostname.endswith(".local")
    ):
        is_public = False

    # Descoberta pelo Firecrawl SEMEIA a fila do crawl local, em vez de
    # substitui-lo.
    #
    # Antes era um ou-exclusivo: se o /v2/map devolvesse qualquer coisa, essas
    # URLs eram as unicas visitadas e a descoberta local nunca rodava. Como
    # `_discover_site_links_firecrawl` insere a propria URL semente no
    # resultado, a lista NUNCA vinha vazia -- entao `if links:` era sempre
    # verdadeiro e o fallback era codigo morto. Medido em 2026-08-30 com
    # https://www.w3.org/WAI/demos/bad/before/home.html: o /v2/map devolveu 1
    # link (so a semente) enquanto a mesma pagina tinha 42 links internos no
    # HTML. O pedido era max_pages=3 e o crawl entregou 1 pagina, calado --
    # falha passando por sucesso.
    #
    # Semeando a fila, os dois caminhos se somam: o que o Firecrawl mapeia entra
    # primeiro, e a varredura local continua descobrindo ate atingir max_pages.
    fila_inicial: list[str] = [_normalize(start_url)]
    firecrawl_key = getattr(settings, "firecrawl_api_key", None)
    if firecrawl_key and is_public:
        logger.info("[Crawler] Usando Firecrawl /v2/map para descoberta de links de %s", start_url)
        import asyncio

        links = await asyncio.to_thread(_discover_site_links_firecrawl, start_url, firecrawl_key, max_pages)
        descobertos = [_normalize(link) for link in (links or []) if _normalize(link) not in fila_inicial]
        if descobertos:
            logger.info("[Crawler] Firecrawl acrescentou %d links alem da semente.", len(descobertos))
            fila_inicial.extend(descobertos)
        else:
            logger.warning(
                "[Crawler] Firecrawl nao descobriu nenhum link alem da propria URL inicial -- "
                "a varredura local segue a partir dos links do HTML."
            )

    results = []
    visited: set[str] = set()
    queue: list[str] = fila_inicial

    from backend.src.services.browser import fetch_rendered_html

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        logger.info("[Crawler] Página %d/%d: %s", len(visited), max_pages, url)
        try:
            html = await fetch_rendered_html(url, cookies=cookies, auth_headers=auth_headers)
            results.append(CrawlPageResult(url=url, html=html))
            logger.info("[Crawler] OK: %s (%d chars)", url, len(html))
            if len(visited) < max_pages:
                for link in _extract_links_soup(html, url, start_url):
                    if link not in visited and link not in queue:
                        queue.append(link)
        except Exception as exc:
            logger.error("[Crawler] Falha ao obter %s: %s", url, exc)
            results.append(CrawlPageResult(url=url, html="", error=str(exc)))

    ok = sum(1 for r in results if r.success)
    logger.info("[Crawler] Concluido: %d páginas, %d com sucesso", len(results), ok)
    return results
