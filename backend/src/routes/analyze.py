import hashlib
import ipaddress
import json
import logging
import os
import socket
import tempfile
from typing import Annotated
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, Tag
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.config.settings import get_settings
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.services import batch_collector, batch_job_store
from backend.src.services.batch_inference import (
    BatchNotSupportedError,
    BatchRequest,
    BatchStatus,
    fetch_batch_results,
    poll_batch,
    submit_batch,
)
from backend.src.services.browser import (
    fetch_accessibility_tree_snapshot,
    fetch_rendered_html_screenshot_and_focus_states,
)
from backend.src.services.crawler import crawl_site
from backend.src.services.response_cache import set_cached_response
from backend.src.shared.models import (
    AccessibilityIssue,
    AgentMetrics,
    AgentResult,
    AnalyzeUrlRequest,
    CrawlPageIssues,
    CrawlRequest,
    CrawlResult,
    TaskType,
)

_BATCH_SUPPORTED_PROVIDERS = {"openai", "anthropic", "gemini"}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"], dependencies=[Depends(rate_limit_dependency)])

_SUPPORTED_EXT = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
}
_SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "coverage",
    ".cache",
    "out",
}

# Limits to avoid exceeding LLM context
_MAX_BYTES_PER_FILE = 60_000  # 60 KB per file
_MAX_TOTAL_BYTES = 400_000  # 400 KB assembled context
# Max HTML sent to LLM after semantic extraction (prevents context overflow)
_MAX_HTML_FOR_LLM = 80_000  # 80 KB

# Private/internal IP ranges blocked for SSRF protection
_BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# Tags stripped entirely (noise that carries no a11y signal).
# NOTE: iframe is intentionally NOT stripped here — it is collected via selectors
# so the wcag_semantics agent can check for missing title attributes.
_STRIP_TAGS = {
    "script",
    "noscript",
    "template",
    "meta",
    "link",
    "base",
    "object",
    "embed",
}

# Landmark/container tags whose inner content (truncated) is also captured
_CONTAINER_TAGS = frozenset(
    {
        "nav",
        "main",
        "header",
        "footer",
        "aside",
        "section",
        "article",
        "form",
        "fieldset",
    }
)

# All CSS attributes that carry a11y signal (kept on elements; BeautifulSoup
# preserves them unless we strip — we only strip them from noise tags above)
_A11Y_ATTRS = (
    "id",
    "class",
    "role",
    "aria-label",
    "aria-labelledby",
    "aria-describedby",
    "aria-hidden",
    "aria-expanded",
    "aria-selected",
    "aria-checked",
    "aria-pressed",
    "aria-current",
    "aria-live",
    "aria-atomic",
    "aria-busy",
    "aria-controls",
    "aria-haspopup",
    "aria-modal",
    "aria-required",
    "aria-invalid",
    "aria-errormessage",
    "aria-activedescendant",
    "aria-valuenow",
    "aria-valuemin",
    "aria-valuemax",
    "aria-valuetext",
    "tabindex",
    "href",
    "src",
    "alt",
    "title",
    "lang",
    "type",
    "name",
    "for",
    "autocomplete",
    "required",
    "disabled",
    "placeholder",
    "scope",
    "headers",
    "colspan",
    "rowspan",
    "width",
    "height",
    "data-rendered-width",
    "data-rendered-height",
    "data-closest-spacing",
    "data-complex-bg",
)

# CSS properties that carry a11y signal (kept in inline style attributes)
_A11Y_CSS_PROPS = (
    "outline",
    "color",
    "background",
    "background-color",
    "font-size",
    "line-height",
    "letter-spacing",
    "word-spacing",
    "display",
    "visibility",
    "opacity",
    "pointer-events",
    "cursor",
    "text-transform",
    "text-align",
    "position",
    "z-index",
    "overflow",
)

# Elements relevant for accessibility analysis — collected from entire DOM
_A11Y_SELECTORS = [
    # Non-text content & media
    "img",
    "svg",
    "canvas",
    "video",
    "audio",
    "track",
    "figure",
    "figcaption",
    # Interactive
    "button",
    "a",
    "input",
    "select",
    "textarea",
    "details",
    "summary",
    # Headings
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    # Landmark containers (content captured inline)
    "nav",
    "main",
    "header",
    "footer",
    "aside",
    "section",
    "article",
    # Forms
    "form",
    "fieldset",
    "legend",
    "label",
    # Tables
    "table",
    "th",
    "caption",
    "thead",
    "tbody",
    # Lists
    "ul",
    "ol",
    "dl",
    # iframes — needed for title attribute check
    "iframe",
    # ARIA widgets and live regions
    "[role]",
    "[aria-label]",
    "[aria-labelledby]",
    "[aria-describedby]",
    "[aria-live]",
    "[aria-atomic]",
    "[aria-busy]",
    "[aria-expanded]",
    "[aria-selected]",
    "[aria-checked]",
    "[aria-pressed]",
    "[aria-current]",
    "[aria-modal]",
    "[aria-required]",
    "[aria-invalid]",
    # Focus management
    "[tabindex]",
    # Abbreviations / semantic
    "abbr",
    "time",
]


def _as_str(value: object) -> str:
    """Normaliza um valor de atributo do BeautifulSoup (str | list | None) para str."""
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def _filter_style_attr(style_val: str) -> str:
    """Keep only a11y-relevant CSS declarations from an inline style attribute."""
    kept: list[str] = []
    for decl in style_val.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        prop = decl.split(":")[0].strip().lower()
        if any(prop.startswith(a) for a in _A11Y_CSS_PROPS):
            kept.append(decl)
    return "; ".join(kept)


def _extract_semantic_html(raw_html: str, accessibility_tree: str | None = None) -> str:
    """
    Extracts accessibility-relevant context from the full DOM for all specialist agents.

    Produces a structured document with sections:
      [PAGE CONTEXT]            — html lang, title, meta charset/viewport (WCAG 3.1.1, 2.4.2)
      [STYLES]                  — embedded <style> blocks truncated (for css_analyzer)
      [ELEMENTS]                — all a11y-relevant elements collected from the entire body
      [REAL ACCESSIBILITY TREE] — optional, when `accessibility_tree` is provided (see
                                   browser.py::fetch_accessibility_tree_snapshot): role +
                                   accessible name + state computed by the REAL browser
                                   accessibility engine, not estimated by the LLM from raw
                                   markup -- ground truth for AccName/role/state judgment.

    Sites like globo.com have 600KB of <head> before any body content — naive
    truncation sends zero useful elements to the LLM.
    """
    try:
        soup = BeautifulSoup(raw_html, "html.parser")

        # ── 1. PAGE CONTEXT (head-level attributes) ────────────────────────────
        html_tag = soup.find("html")
        page_lang = html_tag.get("lang", "") if isinstance(html_tag, Tag) else ""
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else ""
        meta_charset = ""
        meta_viewport = ""
        for meta in soup.find_all("meta"):
            if meta.get("charset"):
                meta_charset = _as_str(meta.get("charset"))
            if _as_str(meta.get("name")).lower() == "viewport":
                meta_viewport = _as_str(meta.get("content"))

        page_context = f'<html lang="{page_lang}">\n' f"<title>{page_title}</title>\n"
        if meta_charset:
            page_context += f'<meta charset="{meta_charset}">\n'
        if meta_viewport:
            page_context += f'<meta name="viewport" content="{meta_viewport}">\n'

        # ── 2. EMBEDDED STYLES (for css_analyzer) ─────────────────────────────
        style_blocks: list[str] = []
        style_bytes = 0
        _MAX_STYLE_BYTES = 12_000
        for style_tag in soup.find_all("style"):
            block = style_tag.get_text()
            remaining = _MAX_STYLE_BYTES - style_bytes
            if remaining <= 0:
                break
            snippet = block[:remaining]
            style_blocks.append(snippet)
            style_bytes += len(snippet)

        # ── 3. ELEMENT COLLECTION ──────────────────────────────────────────────
        # Remove noise tags first (keep style blocks already collected above)
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            comment.extract()

        parts: list[str] = []
        total = 0
        seen_ids: set[int] = set()

        for selector in _A11Y_SELECTORS:
            for el in soup.select(selector):
                el_id = id(el)
                if el_id in seen_ids:
                    continue
                seen_ids.add(el_id)

                if el.name in _CONTAINER_TAGS:
                    # Render tag with a11y attributes + truncated inner content
                    attrs = ""
                    for attr in (
                        "id",
                        "aria-label",
                        "aria-labelledby",
                        "role",
                        "class",
                        "lang",
                        "aria-current",
                    ):
                        val = el.get(attr)
                        if val:
                            if isinstance(val, list):
                                val = " ".join(val)
                            attrs += f' {attr}="{val}"'
                    inner = el.decode_contents()[:2000]
                    chunk = f"<{el.name}{attrs}>{inner}</{el.name}>"
                else:
                    # Render full element with a11y-relevant attributes preserved
                    # Filter inline style to only a11y properties
                    style_val = _as_str(el.get("style"))
                    if style_val:
                        filtered = _filter_style_attr(style_val)
                        if filtered:
                            el["style"] = filtered
                        else:
                            del el["style"]
                    chunk = str(el)

                chunk = chunk[:500]  # cap per-element
                if total + len(chunk) > _MAX_HTML_FOR_LLM:
                    break
                parts.append(chunk)
                total += len(chunk)

        elements_block = "\n".join(parts)

        # ── 4. ASSEMBLE ────────────────────────────────────────────────────────
        # ELEMENTS antes de STYLES de proposito: se o orcamento de contexto for
        # estourado a jusante (context_compressor.compress, truncamento downstream),
        # o que sobrevive e o que fica mais perto do inicio da string. CSS embutido
        # de terceiros (ex.: SDK do Facebook, ~12KB) nao pode ter prioridade sobre
        # <form>/<input>/<button> reais -- achado real: numa pagina com 7 forms e 96
        # inputs, a ordem antiga (STYLES antes de ELEMENTS) fez o orcamento de 24KB
        # do compressor ser consumido pelo CSS antes de qualquer elemento interativo
        # sobreviver, cegando forms_a11y/widgets_a11y (0 issues mesmo pedidos via
        # only_agents, roteamento condicional nunca disparado).
        sections: list[str] = [
            "<!-- [PAGE CONTEXT] -->",
            page_context,
            "<!-- [ELEMENTS] -->",
            elements_block,
        ]
        if style_blocks:
            sections += ["<!-- [STYLES] -->", "\n".join(style_blocks)]
        if accessibility_tree:
            sections += [
                "<!-- [REAL ACCESSIBILITY TREE — computada pelo motor de acessibilidade real "
                "do navegador (Chromium), NÃO estimada. Um nó '(SEM NOME ACESSÍVEL)' aqui é "
                "uma violação confirmada, não uma suposição] -->",
                accessibility_tree,
            ]

        extracted = "\n".join(sections)

        logger.info(
            "[Route] HTML extraido: %d -> %d chars (%.1f%%) — %d elementos a11y",
            len(raw_html),
            len(extracted),
            len(extracted) / max(len(raw_html), 1) * 100,
            len(seen_ids),
        )
        return extracted if extracted else raw_html[:_MAX_HTML_FOR_LLM]

    except Exception as exc:
        logger.warning(
            "[Route] Falha ao extrair HTML semantico (%s) — usando truncamento simples",
            exc,
        )
        return raw_html[:_MAX_HTML_FOR_LLM]


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _assemble_project(files: list[tuple[str, str]]) -> str:
    """
    Assembles a multi-file project into a single annotated context string.
    files: list of (filename, content) sorted: HTML first, then CSS, then JS/TS.
    """
    order = {
        ".html": 0,
        ".htm": 0,
        ".css": 1,
        ".js": 2,
        ".jsx": 2,
        ".ts": 2,
        ".tsx": 2,
        ".vue": 2,
        ".svelte": 2,
    }
    sorted_files = sorted(files, key=lambda fc: order.get(_ext(fc[0]), 9))

    parts: list[str] = [f"=== PROJECT ANALYSIS: {len(sorted_files)} file(s) ===\n"]
    total = len(parts[0])

    for filename, content in sorted_files:
        if total >= _MAX_TOTAL_BYTES:
            logger.warning(
                "[Project] Context limit reached -- %d files truncated",
                len(sorted_files),
            )
            break
        snippet = content[:_MAX_BYTES_PER_FILE]
        block = f"\n=== FILE: {filename} ===\n{snippet}\n"
        total += len(block)
        parts.append(block)

    return "".join(parts)


def _validate_url_ssrf(url: str) -> None:
    """Validates URL against SSRF attacks — blocks private IPs and non-HTTP protocols."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Protocolo não suportado: {parsed.scheme}. Use http ou https.",
        )
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="URL invalida: hostname ausente.")
    # Block obviously internal hostnames
    if hostname in ("localhost", "0.0.0.0"):
        raise HTTPException(
            status_code=400,
            detail="URLs internas/localhost não sao permitidas.",
        )
    # Resolve hostname and check against blocked IP ranges

    try:
        resolved = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_IP_NETWORKS:
                if ip in network:
                    raise HTTPException(
                        status_code=400,
                        detail="URLs apontando para redes internas não sao permitidas.",
                    )
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possivel resolver o hostname: {hostname}",
        ) from exc


@router.post("/url", response_model=AgentResult)
async def analyze_url(body: AnalyzeUrlRequest) -> AgentResult:
    """
    Analisa uma URL externa.
    Usa Playwright (Chromium headless) para renderizar o JavaScript antes de analisar,
    garantindo que SPAs e sites com conteúdo dinâmico sejam capturados corretamente.
    """
    logger.info("[Route] POST /analyze/url url=%s", body.url)
    _validate_url_ssrf(body.url)
    try:
        html, screenshot_base64, focus_screenshots = await fetch_rendered_html_screenshot_and_focus_states(
            body.url,
            cookies=body.cookies,
            auth_headers=body.auth_headers,
            actions=body.actions,
        )
    except Exception as exc:
        logger.error("[Route] Falha ao renderizar URL e capturar screenshot: %s", exc)
        raise HTTPException(status_code=400, detail=f"Não foi possivel acessar a URL: {exc}") from exc

    # Best-effort: árvore de acessibilidade REAL (motor do navegador), nunca
    # derruba a análise se indisponível (ver fetch_accessibility_tree_snapshot).
    accessibility_tree = await fetch_accessibility_tree_snapshot(body.url)
    semantic_html = _extract_semantic_html(html, accessibility_tree)
    result = await orchestrate(
        semantic_html,
        TaskType.ANALYZE,
        screenshot_base64=screenshot_base64,
        focus_screenshots=focus_screenshots,
        only_agents=body.only_agents,
    )
    is_success = result.get("success") if isinstance(result, dict) else result.success
    if is_success:
        issues = result.get("data", {}).get("issues", []) if isinstance(result, dict) else result.data.get("issues", [])
        from backend.src.services.last_analysis_store import set_last_analysis
        set_last_analysis(issues, body.url)
    return result


@router.post("/file", response_model=AgentResult)
async def analyze_file(file: UploadFile = File(...)) -> AgentResult:  # noqa: B008
    logger.info("[Route] POST /analyze/file filename=%s", file.filename)
    content = await file.read()
    max_bytes = _MAX_BYTES_PER_FILE  # 60 KB per file
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {max_bytes // 1000} KB.",
        )
    html = content.decode("utf-8", errors="replace")
    semantic_html = _extract_semantic_html(html)
    result = await orchestrate(semantic_html, TaskType.ANALYZE)
    is_success = result.get("success") if isinstance(result, dict) else result.success
    if is_success:
        issues = result.get("data", {}).get("issues", []) if isinstance(result, dict) else result.data.get("issues", [])
        from backend.src.services.last_analysis_store import set_last_analysis
        set_last_analysis(issues, f"Arquivo: {file.filename}")
    return result


def _get_cache_path() -> str:
    return os.path.join(tempfile.gettempdir(), "qa_accessibility_cache.json")

def _load_cache() -> dict:
    path = _get_cache_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.debug("[Cache] Falha ao carregar cache de %s: %s", path, exc)
    return {}

def _save_cache(cache: dict) -> None:
    path = _get_cache_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.debug("[Cache] Falha ao salvar cache em %s: %s", path, exc)

def _md5(text: str) -> str:
    # Uso nao-criptografico (chave de cache), nunca para senha/token/assinatura.
    return hashlib.md5(text.encode("utf-8", errors="replace"), usedforsecurity=False).hexdigest()


def _map_issues_to_files(issues: list[dict], accepted_files: list[tuple[str, str]]) -> None:
    """Tenta mapear cada issue de volta para o arquivo de origem correspondente no projeto."""
    import re
    for issue in issues:
        element = issue.get("element", "")
        if not element:
            continue

        # Se for snippet HTML
        is_html_snippet = "<" in element or ">" in element
        clean_el = element.strip()

        found_file = None
        for filename, content in accepted_files:
            if is_html_snippet:
                if clean_el in content:
                    found_file = filename
                    break
                # Se não achou exato, busca a tag crua (ex: <button class="...">)
                tag_match = re.search(r'<[a-zA-Z0-9]+[^>]*>', clean_el)
                if tag_match and tag_match.group(0) in content:
                    found_file = filename
                    break
            else:
                if element in content:
                    found_file = filename
                    break

        if found_file:
            issue["url"] = found_file


@router.post("/project", response_model=AgentResult)
async def analyze_project(
    files: Annotated[list[UploadFile], File()],
) -> AgentResult:
    """Analyzes a full project: accepts HTML, CSS, JS, TS, TSX, Vue, Svelte files."""
    _MAX_PROJECT_FILES = 200
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    if len(files) > _MAX_PROJECT_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Limite de {_MAX_PROJECT_FILES} arquivos por projeto excedido ({len(files)} enviados).",
        )

    accepted: list[tuple[str, str]] = []
    for upload in files:
        filename = upload.filename or "unknown"
        ext = _ext(filename)
        if ext not in _SUPPORTED_EXT:
            continue
        raw = await upload.read()
        text = raw.decode("utf-8", errors="replace")
        accepted.append((filename, text))

    if not accepted:
        raise HTTPException(
            status_code=422,
            detail="Nenhum arquivo compativel encontrado. Envie arquivos .html, .css, .js, .ts ou .tsx.",
        )

    logger.info("[Route] POST /analyze/project files=%d accepted=%d", len(files), len(accepted))

    # Carrega o cache de arquivos
    cache = _load_cache()
    cached_issues = []
    to_analyze = []
    file_hashes = {}

    for name, text in accepted:
        file_hash = _md5(text)
        file_hashes[name] = file_hash
        if name in cache and cache[name].get("hash") == file_hash:
            file_issues = cache[name].get("issues", [])
            for issue in file_issues:
                issue["url"] = name
            cached_issues.extend(file_issues)
        else:
            to_analyze.append((name, text))

    logger.info("[Route] POST /analyze/project Cache hit: %d. Cache miss: %d", len(accepted) - len(to_analyze), len(to_analyze))

    if not to_analyze:
        from backend.src.services.last_analysis_store import set_last_analysis
        set_last_analysis(cached_issues, f"Projeto (Cache): {len(accepted)} arquivos")
        return AgentResult(agent="project_analyzer_cache", success=True, data={"issues": cached_issues}, error=None)

    context = _assemble_project(to_analyze)
    result = await orchestrate(context, TaskType.ANALYZE)
    is_success = result.get("success") if isinstance(result, dict) else result.success

    if is_success:
        new_issues = result.get("data", {}).get("issues", []) if isinstance(result, dict) else result.data.get("issues", [])
        _map_issues_to_files(new_issues, to_analyze)

        # Atualiza o cache
        for name, _ in to_analyze:
            file_issues = [issue for issue in new_issues if issue.get("url") == name]
            cache[name] = {
                "hash": file_hashes[name],
                "issues": file_issues
            }
        _save_cache(cache)

        all_issues = cached_issues + new_issues
        if isinstance(result, dict):
            result["data"]["issues"] = all_issues
        else:
            result.data["issues"] = all_issues

        from backend.src.services.last_analysis_store import set_last_analysis
        set_last_analysis(all_issues, f"Projeto (Misto): {len(accepted)} arquivos")

    return result


@router.post("/crawl", response_model=CrawlResult)
async def analyze_crawl(body: CrawlRequest) -> CrawlResult:
    """
    Crawlea um site inteiro a partir da URL raiz.

    - Renderiza cada página com Playwright (JS rendering completo)
    - Descobre e visita links internos automaticamente
    - Analisa cada página com o pipeline de agentes em paralelo
    - Consolida todos os issues em um único resultado
    - Retorna score geral + issues por página

    Limite: max_pages (1-50, padrão 10).
    """
    _validate_url_ssrf(body.url)
    logger.info("[Route] POST /analyze/crawl url=%s max_pages=%d", body.url, body.max_pages)

    page_results = await crawl_site(
        body.url,
        max_pages=body.max_pages,
        cookies=body.cookies,
        auth_headers=body.auth_headers,
    )

    if not page_results:
        raise HTTPException(status_code=400, detail="Nenhuma página foi acessada com sucesso.")

    all_issues: list[AccessibilityIssue] = []
    pages_detail: list[CrawlPageIssues] = []
    pages_ok = 0
    pages_failed = 0

    for page in page_results:
        if not page.success or not page.html:
            pages_failed += 1
            pages_detail.append(
                CrawlPageIssues(
                    url=page.url,
                    issues=[],
                    success=False,
                    error=page.error,
                )
            )
            continue

        semantic_html = _extract_semantic_html(page.html)
        result: AgentResult = await orchestrate(semantic_html, TaskType.ANALYZE)

        if result.success:
            pages_ok += 1
            page_issues = [AccessibilityIssue(**i) for i in result.data.get("issues", [])]
            metrics = [AgentMetrics(**m) for m in result.data.get("agent_metrics", [])]
            # Anota de qual página veio cada issue
            for issue in page_issues:
                issue_with_page = issue.model_copy(update={"element": f"[{page.url}] {issue.element}"})
                all_issues.append(issue_with_page)
            pages_detail.append(
                CrawlPageIssues(
                    url=page.url,
                    issues=page_issues,
                    agent_metrics=metrics,
                    success=True,
                )
            )
        else:
            pages_failed += 1
            pages_detail.append(
                CrawlPageIssues(
                    url=page.url,
                    issues=[],
                    success=False,
                    error=result.error,
                )
            )

    # Score global: 100 - deducoes por severidade (mesmo calculo do ReporterAgent)
    _deductions = {"critical": 20, "high": 10, "medium": 5, "low": 2}
    total_deduction = sum(_deductions.get(i.severity.value, 0) for i in all_issues)
    score = max(0, 100 - total_deduction)

    logger.info(
        "[Route] Crawl concluido: %d páginas OK, %d falhas, %d issues, score=%d",
        pages_ok,
        pages_failed,
        len(all_issues),
        score,
    )

    from backend.src.services.last_analysis_store import set_last_analysis
    set_last_analysis([i.model_dump() for i in all_issues], f"Crawl: {body.url}")

    return CrawlResult(
        total_pages=len(page_results),
        pages_ok=pages_ok,
        pages_failed=pages_failed,
        all_issues=all_issues,
        pages=pages_detail,
        total_issues=len(all_issues),
        score=score,
    )


class CrawlBatchSubmitResponse(BaseModel):
    batch_id: str = Field(..., description="ID do job de batch no provider")
    provider: str = Field(..., description="Provider que processou o batch (openai/anthropic/gemini)")
    pages_submitted: int = Field(..., description="Páginas com conteúdo enviadas ao batch")
    pages_failed_at_crawl: int = Field(..., description="Páginas que já falharam no crawl, antes do batch")


class CrawlBatchStatusResponse(BaseModel):
    status: str = Field(..., description="pending | running | completed | failed")
    result: CrawlResult | None = Field(default=None, description="Presente só quando status=='completed'")


def _build_crawl_page_result(url: str, result: AgentResult) -> tuple[CrawlPageIssues, list[AccessibilityIssue]]:
    """Espelha o bloco de sucesso do `/analyze/crawl` sincrono: cada issue
    ganha o prefixo `[url]` no elemento SÓ na lista consolidada
    (`all_issues`), nunca no `CrawlPageIssues.issues` (que fica limpo, por
    página)."""
    if not result.success:
        return CrawlPageIssues(url=url, issues=[], success=False, error=result.error), []
    page_issues = [AccessibilityIssue(**i) for i in result.data.get("issues", [])]
    metrics = [AgentMetrics(**m) for m in result.data.get("agent_metrics", [])]
    prefixed = [i.model_copy(update={"element": f"[{url}] {i.element}"}) for i in page_issues]
    return CrawlPageIssues(url=url, issues=page_issues, agent_metrics=metrics, success=True), prefixed


@router.post("/crawl/batch", response_model=CrawlBatchSubmitResponse)
async def analyze_crawl_batch_submit(body: CrawlRequest) -> CrawlBatchSubmitResponse:
    """
    Como `/analyze/crawl`, mas submete a análise das páginas como UM job de
    Batch Inference (ver batch_inference.py) em vez de rodar em tempo real.

    SLA de até 24h (documentado pelos 3 providers suportados) -- não devolve o
    resultado nesta requisição. Devolve `batch_id`; consulte o resultado via
    `GET /analyze/crawl/batch/{batch_id}`.

    Só disponível com provider OpenAI, Anthropic ou Gemini configurado (os 3
    com Batch API e desconto de custo documentados -- ver VERIFICATION.md §21).
    Faz sentido pra crawls grandes sem urgência (relatório agendado, análise
    noturna) -- pro fluxo normal, use `/analyze/crawl`.
    """
    _validate_url_ssrf(body.url)
    settings = get_settings()
    from backend.src.services.model_router import resolve_model_and_provider

    provider, model = resolve_model_and_provider(settings.llm_provider, settings.llm_model, tier="alto")
    if provider not in _BATCH_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Batch mode só está disponível com provider OpenAI, Anthropic ou Gemini "
                f"(atual: '{provider}'). Use /analyze/crawl para o pipeline em tempo real."
            ),
        )

    logger.info("[Route] POST /analyze/crawl/batch url=%s max_pages=%d provider=%s", body.url, body.max_pages, provider)
    page_results = await crawl_site(
        body.url, max_pages=body.max_pages, cookies=body.cookies, auth_headers=body.auth_headers,
    )
    if not page_results:
        raise HTTPException(status_code=400, detail="Nenhuma página foi acessada com sucesso.")

    page_htmls: dict[str, str] = {}
    failed_pages: list[dict[str, str]] = []
    for page in page_results:
        if page.success and page.html:
            page_htmls[page.url] = _extract_semantic_html(page.html)
        else:
            failed_pages.append({"url": page.url, "error": page.error or ""})

    if not page_htmls:
        raise HTTPException(status_code=400, detail="Nenhuma página teve conteúdo renderizado com sucesso.")

    # Fase de coleta: roda o pipeline normal por página com batch_collect=True --
    # cada `call_llm` dos agentes de análise grava a chamada em vez de ligar pro
    # provider (ver batch_collector.py). O resultado desta passada é descartável.
    list_token, pending = batch_collector.bind_pending_list()
    try:
        for html in page_htmls.values():
            await orchestrate(html, TaskType.ANALYZE, batch_collect=True)
    finally:
        batch_collector.unbind_pending_list(list_token)

    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma chamada de agente precisou ser feita para estas páginas (sem conteúdo relevante).",
        )

    batch_requests = [
        BatchRequest(
            custom_id=r.cache_key, system_prompt=r.system_prompt, user_prompt=r.user_prompt, model=r.model,
        )
        for r in pending
    ]
    try:
        batch_id = submit_batch(batch_requests, provider, settings.llm_api_key or "")
    except BatchNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Falhas de crawl já são conhecidas aqui -- persistidas junto do job pra
    # reaparecerem no resultado final sem precisar re-crawlear.
    batch_job_store.save(batch_job_store.BatchJob(
        batch_id=batch_id,
        provider=provider,
        model=model,
        root_url=body.url,
        page_htmls=page_htmls,
        failed_pages=failed_pages,
    ))

    logger.info(
        "[Route] Batch submetido: batch_id=%s provider=%s %d páginas, %d chamadas coletadas",
        batch_id, provider, len(page_htmls), len(pending),
    )
    return CrawlBatchSubmitResponse(
        batch_id=batch_id,
        provider=provider,
        pages_submitted=len(page_htmls),
        pages_failed_at_crawl=len(failed_pages),
    )


@router.get("/crawl/batch/{batch_id}", response_model=CrawlBatchStatusResponse)
async def analyze_crawl_batch_status(batch_id: str) -> CrawlBatchStatusResponse:
    """Consulta o status de um job submetido via `POST /analyze/crawl/batch`.
    Enquanto `status` não for `"completed"`, `result` vem vazio -- consulte de
    novo mais tarde (o batch pode levar até 24h)."""
    job = batch_job_store.load(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail="batch_id não encontrado (job expirado ou nunca existiu).")

    settings = get_settings()
    try:
        status = poll_batch(batch_id, job.provider, settings.llm_api_key or "")
    except BatchNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if status != BatchStatus.COMPLETED:
        return CrawlBatchStatusResponse(status=status.value)

    results = fetch_batch_results(batch_id, job.provider, settings.llm_api_key or "")
    for cache_key, text in results.items():
        set_cached_response(cache_key, text, ttl_seconds=600.0)

    # Segunda passada, coleta desligada: cada `call_llm` acerta a cache com o
    # texto real (mesma chave da coleta) e cada agente faz seu próprio parsing
    # normal -- nenhum dos 25 agentes precisa saber que isto é um batch.
    all_issues: list[AccessibilityIssue] = []
    pages_detail: list[CrawlPageIssues] = []
    for url, html in job.page_htmls.items():
        result: AgentResult = await orchestrate(html, TaskType.ANALYZE)
        page_result, prefixed_issues = _build_crawl_page_result(url, result)
        pages_detail.append(page_result)
        all_issues.extend(prefixed_issues)

    # Páginas que já tinham falhado no crawl (antes do batch existir) --
    # reaparecem aqui sem precisar re-crawlear.
    for failed in job.failed_pages:
        pages_detail.append(CrawlPageIssues(
            url=failed.get("url", ""), issues=[], success=False, error=failed.get("error") or None,
        ))

    pages_ok = sum(1 for p in pages_detail if p.success)
    pages_failed = len(pages_detail) - pages_ok

    _deductions = {"critical": 20, "high": 10, "medium": 5, "low": 2}
    total_deduction = sum(_deductions.get(i.severity.value, 0) for i in all_issues)
    score = max(0, 100 - total_deduction)

    from backend.src.services.last_analysis_store import set_last_analysis
    set_last_analysis([i.model_dump() for i in all_issues], f"Crawl (batch): {job.root_url}")

    logger.info(
        "[Route] Batch %s concluído: %d páginas OK, %d falhas, %d issues, score=%d",
        batch_id, pages_ok, pages_failed, len(all_issues), score,
    )
    batch_job_store.delete(batch_id)

    return CrawlBatchStatusResponse(
        status="completed",
        result=CrawlResult(
            total_pages=len(pages_detail),
            pages_ok=pages_ok,
            pages_failed=pages_failed,
            all_issues=all_issues,
            pages=pages_detail,
            total_issues=len(all_issues),
            score=score,
        ),
    )


@router.post("/project/zip", response_model=AgentResult)
async def analyze_project_zip(
    file: UploadFile = File(...),  # noqa: B008 -- FastAPI dependency-injection idiom, not a real mutable-default
) -> AgentResult:
    """
    Analisa um projeto enviado como um arquivo ZIP.
    Descompacta em memória, filtra dependências/builds e analisa os arquivos de código.
    """
    import io
    import zipfile
    logger.info("[Route] POST /analyze/project/zip filename=%s", file.filename)
    try:
        content = await file.read()
        accepted: list[tuple[str, str]] = []

        # Filtra pastas gigantes ou irrelevantes para otimizar tempo e tokens
        ignored_patterns = {"node_modules/", ".git/", "dist/", "build/", ".next/", "__pycache__/"}

        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for name in z.namelist():
                if name.endswith("/") or any(pattern in name for pattern in ignored_patterns):
                    continue
                ext = _ext(name)
                if ext in _SUPPORTED_EXT:
                    try:
                        with z.open(name) as f:
                            raw_file = f.read()
                            text = raw_file.decode("utf-8", errors="replace")
                            accepted.append((name, text))
                    except Exception as e:
                        logger.warning("[Route] Erro ao ler arquivo do ZIP %s: %s", name, e)

        if not accepted:
            raise HTTPException(
                status_code=422,
                detail="Nenhum arquivo compatível encontrado no ZIP. Envie arquivos .html, .css, .js, .ts ou .tsx.",
            )

        logger.info("[Route] POST /analyze/project/zip arquivos_filtrados=%d", len(accepted))

        # Carrega o cache de arquivos
        cache = _load_cache()
        cached_issues = []
        to_analyze = []
        file_hashes = {}

        for name, text in accepted:
            file_hash = _md5(text)
            file_hashes[name] = file_hash
            if name in cache and cache[name].get("hash") == file_hash:
                # Recupera do cache
                file_issues = cache[name].get("issues", [])
                for issue in file_issues:
                    issue["url"] = name
                cached_issues.extend(file_issues)
            else:
                to_analyze.append((name, text))

        logger.info("[Route] Cache hit: %d arquivos. Cache miss (para analisar): %d arquivos", len(accepted) - len(to_analyze), len(to_analyze))

        if not to_analyze:
            # Todos os arquivos estão em cache! Retorna diretamente.
            from backend.src.services.last_analysis_store import set_last_analysis
            set_last_analysis(cached_issues, f"Projeto ZIP (Cache): {len(accepted)} arquivos")
            return AgentResult(agent="project_analyzer_cache", success=True, data={"issues": cached_issues}, error=None)

        context = _assemble_project(to_analyze)
        result = await orchestrate(context, TaskType.ANALYZE)
        is_success = result.get("success") if isinstance(result, dict) else result.success

        if is_success:
            new_issues = result.get("data", {}).get("issues", []) if isinstance(result, dict) else result.data.get("issues", [])
            _map_issues_to_files(new_issues, to_analyze)

            # Atualiza o cache para os arquivos recém-analisados
            for name, _ in to_analyze:
                file_issues = [issue for issue in new_issues if issue.get("url") == name]
                cache[name] = {
                    "hash": file_hashes[name],
                    "issues": file_issues
                }
            _save_cache(cache)

            # Mescla questões novas e antigas
            all_issues = cached_issues + new_issues

            # Atualiza o resultado de retorno
            if isinstance(result, dict):
                result["data"]["issues"] = all_issues
            else:
                result.data["issues"] = all_issues

            from backend.src.services.last_analysis_store import set_last_analysis
            set_last_analysis(all_issues, f"Projeto ZIP (Misto): {len(accepted)} arquivos")

        return result
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Arquivo ZIP inválido ou corrompido.") from exc
    except Exception as exc:
        logger.error("[Route] Falha ao analisar ZIP do projeto: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
