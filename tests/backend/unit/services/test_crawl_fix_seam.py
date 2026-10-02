"""Regressao: o crawl em UMA pagina cacheia o HTML para correcoes seguintes.

`analyze_page` (URL) sempre cacheou o HTML em `last_analyzed_content_store`;
`analyze_site` (crawl) nao — entao "analise X e depois corrija" depois de um
crawl re-auditava a página do zero (~15 min) porque o fallback do fix não
tinha HTML. O crawl de pagina unica agora grava o HTML consolidado; com
multiplas paginas nao existe UMA pagina "a pagina" e o erro orientado do fix
permanece (comportamento esperado).
"""

from backend.src.services import last_analysis_store, last_analyzed_content_store

# ── stubs de apoio ─────────────────────────────────────────────────────


def _limpar_caches_de_sessao():
    """Isolamento: os stores sao globais por sessao; limpa o slot 'default'."""
    last_analysis_store._sessions.pop(last_analysis_store.DEFAULT_SESSION_ID, None)
    last_analyzed_content_store._sessions.pop("default", None)


# ── stubs de apoio ──────────────────────────────────────────────────────────


def async_crawl_stub(html):
    from backend.src.services.crawler import CrawlPageResult

    async def crawl(_url, max_pages=3):
        return [CrawlPageResult("https://exemplo.com", html)]
    return crawl


def async_paginas(paginas):
    from backend.src.services.crawler import CrawlPageResult

    async def crawl(_url, max_pages=3):
        return [CrawlPageResult(u, h) for u, h in paginas]
    return crawl


def _orchestrate_stub(issues):
    from backend.src.shared.models import AgentResult

    async def orchestrate(_html, _tipo, **_kw):
        return AgentResult(agent="x", success=True, data={"issues": issues})
    return orchestrate


def test_analyze_site_crawl_uma_pagina_cacheia_o_html(monkeypatch):
    from backend.src.services import chat_tools

    _limpar_caches_de_sessao()
    html = "<html><body><main><h1>Titulo</h1></main></body></html>"

    # Os imports de _run_site_crawl_and_analyze sao locais: o monkeypatch mira
    # o modulo de ORIGEM de cada um (crawler/analyze/orchestrator).
    monkeypatch.setattr("backend.src.services.crawler.crawl_site", async_crawl_stub(html))
    monkeypatch.setattr("backend.src.routes.analyze._extract_semantic_html", lambda raw: raw)
    monkeypatch.setattr(
        "backend.src.agents.orchestrator.orchestrator.orchestrate",
        _orchestrate_stub([{"id": "i1", "severity": "high", "description": "x", "criterion": "1.1.1"}]),
    )

    resultado = chat_tools._safe_async_run(
        chat_tools._run_site_crawl_and_analyze("https://exemplo.com", None, 3)
    )
    assert resultado["pages_ok"] == 1
    # O HTML da pagina do crawl ficou disponivel para o fix (sem re-auditoria).
    cached_html, cached_url = last_analyzed_content_store.get_last_analyzed_content()
    assert cached_html == html
    assert cached_url == "https://exemplo.com"


def test_analyze_site_multiplas_paginas_nao_escolhe_uma_no_escuro(monkeypatch):
    from backend.src.services import chat_tools

    _limpar_caches_de_sessao()
    paginas = [("https://exemplo.com/a", "<html>a</html>"), ("https://exemplo.com/b", "<html>b</html>")]
    monkeypatch.setattr("backend.src.services.crawler.crawl_site", async_paginas(paginas))
    monkeypatch.setattr("backend.src.routes.analyze._extract_semantic_html", lambda raw: raw)
    monkeypatch.setattr("backend.src.agents.orchestrator.orchestrator.orchestrate", _orchestrate_stub([]))

    resultado = chat_tools._safe_async_run(
        chat_tools._run_site_crawl_and_analyze("https://exemplo.com", None, 3)
    )
    assert resultado["pages_ok"] == 2
    # Não há UMA página "a página": sem cache de HTML (evita corrigir a errada).
    assert last_analyzed_content_store.get_last_analyzed_content() == ("", "")
