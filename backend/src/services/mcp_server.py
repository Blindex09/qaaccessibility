import json
import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from backend.src.services.browser import fetch_rendered_html_screenshot_and_focus_states
from backend.src.services.self_healing import verify_html_with_axe
from backend.src.services.xlsx_exporter import export_issues_xlsx

# Configura o logger para direcionar mensagens para stderr.
# IMPORTANTE: Nunca escreva mensagens de log para stdout em servidores stdio MCP,
# pois isso corrompe o fluxo JSON-RPC e causa falhas de comunicação com o cliente.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Inicializa o servidor FastMCP
mcp = FastMCP("QA-Accessibility-Tools")


@mcp.tool()
async def get_rendered_page(url: str) -> str:
    """
    Carrega uma URL de forma remota via Playwright CDP (Browserless) e Firecrawl.
    Realiza o cálculo e a injeção geométrica em tempo de execução dos atributos
    de tamanho e espaçamento (data-rendered-width, data-rendered-height, data-closest-spacing)
    nos botões e links da página, retornando o HTML estático totalmente preparado para auditoria.
    """
    logger.info("Ferramenta get_rendered_page chamada para URL: %s", url)
    try:
        html, _screenshot, _focus_screenshots = await fetch_rendered_html_screenshot_and_focus_states(url)
        return html
    except Exception as exc:
        logger.error("Erro em get_rendered_page: %s", exc)
        return f"Erro ao carregar e renderizar a página: {str(exc)}"


@mcp.tool()
async def run_axe_audit(html_content: str) -> str:
    """
    Injeta o script axe-core e executa a auditoria de acessibilidade contra o HTML fornecido
    usando um navegador remoto Playwright CDP. Retorna um array JSON com todos os problemas
    identificados (tags, seletores e descrição dos critérios violados).
    """
    logger.info("Ferramenta run_axe_audit chamada.")
    try:
        issues = await verify_html_with_axe(html_content)
        return json.dumps([issue.model_dump() for issue in issues], ensure_ascii=False)
    except Exception as exc:
        logger.error("Erro em run_axe_audit: %s", exc)
        return f"Erro ao executar a auditoria Axe: {str(exc)}"


@mcp.tool()
def export_xlsx(issues_json: str) -> str:
    """
    Recebe um array JSON serializado contendo os problemas de acessibilidade encontrados
    e exporta os dados formatados em uma planilha XLSX. Retorna o conteúdo do arquivo
    codificado em base64.
    """
    import base64
    logger.info("Ferramenta export_xlsx chamada.")
    try:
        data = json.loads(issues_json)
        xlsx_bytes = export_issues_xlsx(data)
        return base64.b64encode(xlsx_bytes).decode("utf-8")
    except Exception as exc:
        logger.error("Erro em export_xlsx: %s", exc)
        return f"Erro ao exportar planilha XLSX: {str(exc)}"



@mcp.tool()
async def analyze_page_full(url: str = "", html: str = "") -> str:
    """
    Executa o pipeline completo de auditoria de acessibilidade numa página web.
    Fornece APENAS url (para renderizacao remota via Browserless) OU html (conteúdo raw).
    Devolve JSON com: score (0-100), total_issues, issues_by_severity, top_issues (ate 10).
    Compativel com Claude Desktop, VS Code Copilot e qualquer cliente MCP.
    """
    logger.info("[MCP] analyze_page_full: url=%s html_len=%d", url, len(html))
    try:
        from backend.src.agents.orchestrator.orchestrator import orchestrate
        from backend.src.routes.analyze import _extract_semantic_html
        from backend.src.shared.models import TaskType

        if url and not html:
            html, _screenshot, _focus_screenshots = await fetch_rendered_html_screenshot_and_focus_states(url)

        if not html:
            return json.dumps({"error": "Forneca url ou html."}, ensure_ascii=False)

        semantic_html = _extract_semantic_html(html)
        result = await orchestrate(semantic_html, TaskType.ANALYZE)
        if not result.success:
            return json.dumps({"error": result.error or "Falha na análise."}, ensure_ascii=False)
        issues = result.data.get("issues", [])
        _severity_deduction = {"critical": 20, "high": 10, "medium": 5, "low": 2}
        by_severity: dict[str, int] = {}
        for iss in issues:
            sev = iss.get("severity", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
        score = max(0, 100 - sum(_severity_deduction.get(sev, 0) * count for sev, count in by_severity.items()))

        return json.dumps({
            "url": url or "(html inline)",
            "score": score,
            "total_issues": len(issues),
            "issues_by_severity": by_severity,
            "top_issues": issues[:10],
        }, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("[MCP] analyze_page_full erro: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
async def analyze_site_full(url: str, max_pages: int = 10) -> str:
    """
    Crawla um site a partir da URL raiz e audita ate max_pages páginas (default 10, max 50).
    Devolve JSON com: pages_audited, aggregate_score, total_issues, issues_by_severity.
    Compativel com Claude Desktop, VS Code Copilot e qualquer cliente MCP.
    """
    logger.info("[MCP] analyze_site_full: url=%s max_pages=%d", url, max_pages)
    try:
        from backend.src.services.chat_tools import _run_site_crawl_and_analyze
        max_pages = min(max(1, max_pages), 50)
        result = await _run_site_crawl_and_analyze(url=url, urls=None, max_pages=max_pages)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("[MCP] analyze_site_full erro: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def describe_repository() -> str:
    """
    Repository Intelligence: devolve o indice estruturado (docs/REPO_MAP.json)
    dos sub-agentes de acessibilidade deste repositorio -- nome, arquivo,
    entry-point, prefixo de ID de issue e diretriz (WCAG/WAI-ARIA/Section 508)
    de cada um. Permite a um agente cliente (Claude Desktop, VS Code Copilot,
    outra sessao de Claude Code) descobrir "quem cobre ARIA?" ou "qual arquivo
    trata contraste?" sem precisar ler os 33 modulos de agents/ ou o
    AI_MODULE_SPEC.md inteiro. Gerado por scripts/generate_repo_map.py --
    sempre reflete o codigo-fonte atual, nao uma copia que pode ficar obsoleta.
    """
    logger.info("Ferramenta describe_repository chamada.")
    repo_map_path = Path(__file__).resolve().parents[3] / "docs" / "REPO_MAP.json"
    try:
        return repo_map_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Erro em describe_repository: %s", exc)
        return json.dumps({"error": f"Nao foi possivel ler REPO_MAP.json: {exc}"}, ensure_ascii=False)


if __name__ == "__main__":
    _VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")
    _transport_env = os.getenv("MCP_TRANSPORT", "stdio")
    if _transport_env not in _VALID_TRANSPORTS:
        logger.warning(
            "[MCP] MCP_TRANSPORT=%s inválido (esperado um de %s); usando 'stdio'.",
            _transport_env, _VALID_TRANSPORTS,
        )
        _transport_env = "stdio"
    logger.info("Iniciando servidor MCP 'QA-Accessibility-Tools' (transport=%s)...", _transport_env)
    mcp.run(transport=_transport_env)  # type: ignore[arg-type]  # narrowed to _VALID_TRANSPORTS above
