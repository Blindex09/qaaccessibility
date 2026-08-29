import contextlib
import io
import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from backend.src.services.sarif_exporter import export_to_sarif
from backend.src.services.xlsx_exporter import export_issues_xlsx

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/export",
    tags=["export"],
)


@router.post("/xlsx")
async def export_xlsx(payload: dict) -> StreamingResponse:
    """
    Exporta issues de acessibilidade para XLSX acessível.

    Body: { "issues": [...], "url": "https://..." }
    Retorna: arquivo .xlsx para download
    """
    issues = payload.get("issues", [])
    url = payload.get("url", "")

    if not issues:
        raise HTTPException(status_code=400, detail="Nenhum issue fornecido para exportacao.")

    # Injeta URL em cada issue se não tiver
    for issue in issues:
        if not issue.get("url"):
            issue["url"] = url

    try:
        xlsx_bytes = export_issues_xlsx(issues)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar XLSX: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar planilha.") from exc

    filename = f"qa-accessibility-{url.replace('https://', '').replace('http://', '').replace('/', '-')}.xlsx"

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/last_xlsx")
@router.get("/last_xlsx**")
@router.get("/last_xlsx/")
async def export_last_xlsx() -> StreamingResponse:
    """
    Exporta os últimos issues de acessibilidade salvos em cache para XLSX acessível.
    """
    from backend.src.services.last_analysis_store import get_last_analysis
    issues, url = get_last_analysis()

    if not issues:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma auditoria recente encontrada no cache para exportação.",
        )

    try:
        xlsx_bytes = export_issues_xlsx(issues)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar XLSX do cache: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar planilha do cache.") from exc

    # Sanitiza nome do arquivo
    clean_url = url.replace("https://", "").replace("http://", "").replace("/", "-")
    filename = f"qa-accessibility-{clean_url}.xlsx"

    exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
    os.makedirs(exports_dir, exist_ok=True)
    with contextlib.suppress(Exception), open(os.path.join(exports_dir, filename), "wb") as f_out:
        f_out.write(xlsx_bytes)

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/last_checklist_pdf")
@router.get("/last_checklist_pdf/")
async def export_last_checklist_pdf() -> StreamingResponse:
    """
    Gera o checklist de acessibilidade da última análise em cache como PDF
    acessível (PDF/UA-1, com árvore de estrutura taggeada real) via o
    ChecklistAgent estruturado -- não texto solto escrito pelo chat.
    """
    from backend.src.agents.checklist.checklist import run_checklist
    from backend.src.services.checklist_pdf_exporter import export_checklist_pdf
    from backend.src.services.last_analysis_store import get_last_analysis
    from backend.src.services.last_analyzed_content_store import get_last_analyzed_content
    from backend.src.shared.models import AccessibilityIssue

    issues_raw, url = get_last_analysis()
    if not issues_raw:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma auditoria recente encontrada no cache para gerar o checklist.",
        )

    html_content, _ = get_last_analyzed_content()
    issues = [AccessibilityIssue(**i) for i in issues_raw]

    result = await run_checklist(issues, html_content=html_content or None)
    if not result.success:
        logger.error("[Export] ChecklistAgent falhou ao gerar checklist para PDF: %s", result.error)
        raise HTTPException(status_code=500, detail="Falha ao gerar o checklist.")

    from backend.src.shared.models import ChecklistItem
    items = [ChecklistItem(**i) for i in result.data.get("checklist", [])]
    if not items:
        raise HTTPException(status_code=500, detail="Checklist gerado veio vazio.")

    try:
        pdf_bytes = export_checklist_pdf(items, url)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar PDF do checklist: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar PDF do checklist.") from exc

    clean_url = url.replace("https://", "").replace("http://", "").replace("/", "-")
    filename = f"checklist-acessibilidade-{clean_url or 'analise'}.pdf"

    exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
    os.makedirs(exports_dir, exist_ok=True)
    with contextlib.suppress(Exception), open(os.path.join(exports_dir, filename), "wb") as f_out:
        f_out.write(pdf_bytes)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/last_accessibility_statement_pdf")
@router.get("/last_accessibility_statement_pdf/")
async def export_last_accessibility_statement_pdf() -> StreamingResponse:
    """
    Gera a Declaração de Acessibilidade da última análise em cache como PDF
    acessível (PDF/UA-1) -- dados reais dos issues encontrados, nunca texto
    inventado pelo chat. Organização/contato vêm do que o usuário informou em
    `generate_accessibility_statement` (accessibility_statement_store.py);
    quando não informados, o PDF usa placeholders visíveis.
    """
    from backend.src.services.accessibility_statement_generator import (
        build_accessibility_statement,
        export_accessibility_statement_pdf,
    )
    from backend.src.services.accessibility_statement_store import get_accessibility_statement_options
    from backend.src.services.last_analysis_store import get_last_analysis

    issues, url = get_last_analysis()
    if not issues:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma auditoria recente encontrada no cache para gerar a declaração de acessibilidade.",
        )

    options = get_accessibility_statement_options()
    statement = build_accessibility_statement(issues, url, **options)

    try:
        pdf_bytes = export_accessibility_statement_pdf(statement)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar PDF da declaração de acessibilidade: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar PDF da declaração de acessibilidade.") from exc

    clean_url = url.replace("https://", "").replace("http://", "").replace("/", "-")
    filename = f"declaracao_acessibilidade_{clean_url or 'analise'}.pdf"
    exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
    os.makedirs(exports_dir, exist_ok=True)
    with contextlib.suppress(Exception), open(os.path.join(exports_dir, filename), "wb") as f_out:
        f_out.write(pdf_bytes)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download_zip/{filename}")
async def download_zip(filename: str) -> FileResponse:
    """
    Download de arquivos ZIP temporários gerados com as correções.
    """
    clean_name = os.path.basename(filename).rstrip("*_)\n\r ")
    temp_dir = tempfile.gettempdir()
    exports_dir = os.path.join(temp_dir, "qa_accessibility_exports")
    file_path = os.path.join(exports_dir, clean_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado.")

    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=clean_name,
    )


@router.post("/sarif")
async def export_sarif(payload: dict) -> dict:
    """
    Exporta issues de acessibilidade no formato SARIF 2.1.0 JSON.

    Body: { "issues": [...], "url": "https://..." }
    Retorna: Objeto JSON SARIF 2.1.0
    """
    from backend.src.shared.models import AccessibilityIssue
    issues_raw = payload.get("issues", [])
    url = payload.get("url", "http://localhost")

    if not issues_raw:
        raise HTTPException(status_code=400, detail="Nenhum issue fornecido para exportacao SARIF.")

    try:
        issues = [AccessibilityIssue(**i) for i in issues_raw]
        return export_to_sarif(issues, url)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar SARIF: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar relatorio SARIF.") from exc


@router.get("/last_sarif")
async def export_last_sarif() -> dict:
    """
    Exporta os ultimos issues de acessibilidade salvos em cache no formato SARIF 2.1.0 JSON.
    """
    from backend.src.services.last_analysis_store import get_last_analysis
    from backend.src.shared.models import AccessibilityIssue
    issues_raw, url = get_last_analysis()

    if not issues_raw:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma auditoria recente encontrada no cache para exportacao SARIF.",
        )

    try:
        issues = [AccessibilityIssue(**i) for i in issues_raw]
        return export_to_sarif(issues, url)
    except Exception as exc:
        logger.error("[Export] Falha ao gerar SARIF do cache: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar relatorio SARIF do cache.") from exc


