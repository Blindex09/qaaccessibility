import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.src.agents.fixer.fixer import run_fixer
from backend.src.config.settings import get_settings
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AgentResult, FixRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fix", tags=["fix"], dependencies=[Depends(rate_limit_dependency)])

# Guardrail: hard wall-clock timeout para o agente fixer (iteration limit)
_FIX_TIMEOUT_SECONDS = 60.0


@router.post("/", response_model=AgentResult)
async def fix_html(body: FixRequest) -> AgentResult:
    request_id = uuid.uuid4().hex[:8]
    logger.info(
        "[Route] POST /fix request_id=%s issues=%d approved=%s instruction=%s self_healing=%s",
        request_id,
        len(body.issues),
        body.approved_issue_ids,
        bool(body.custom_instruction),
        body.self_healing,
    )
    try:
        if body.self_healing:
            from backend.src.services.self_healing import run_self_healing_loop
            try:
                fixed_html, changes_summary, enriched_issues = await asyncio.wait_for(
                    run_self_healing_loop(
                        body.html_content,
                        body.issues,
                        approved_issue_ids=body.approved_issue_ids,
                        custom_instruction=body.custom_instruction,
                    ),
                    timeout=_FIX_TIMEOUT_SECONDS,
                )
                result = AgentResult(
                    agent="fixer",
                    success=True,
                    data={
                        "fixed_html": fixed_html,
                        "changes_summary": changes_summary,
                        "enriched_issues": enriched_issues,
                    },
                )
            except Exception as exc:
                logger.error("[Route] Self-healing failed: %s", exc)
                result = AgentResult(
                    agent="fixer",
                    success=False,
                    data={},
                    error=str(exc),
                )
        else:
            result = await asyncio.wait_for(
                run_fixer(
                    body.html_content,
                    body.issues,
                    request_id=request_id,
                    approved_issue_ids=body.approved_issue_ids,
                    custom_instruction=body.custom_instruction,
                ),
                timeout=_FIX_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        logger.error(
            "[Route] /fix timeout request_id=%s after %.0fs",
            request_id,
            _FIX_TIMEOUT_SECONDS,
        )
        raise HTTPException(status_code=504, detail="Fixer agent timed out") from None
    return result


@router.post("/project/zip", response_model=AgentResult)
async def fix_project_zip(
    file: UploadFile = File(...),  # noqa: B008 -- FastAPI dependency-injection idiom, not a real mutable-default
    issues: str = Form(...),
    approved_issue_ids: str | None = Form(default=None),
    custom_instruction: str | None = Form(default=None),
    self_healing: bool = Form(default=True),
) -> AgentResult:
    """
    Descompacta um ZIP contendo o projeto, aplica correções automáticas (Self-healing ou fixer básico)
    com base nas violações enviadas e gera um novo ZIP com os arquivos corrigidos para download.
    Suporta arquivos HTML, CSS, JS, TS, TSX, Vue, Svelte, além de documentos DOCX e PDF.
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info(
        "[Route] POST /fix/project/zip request_id=%s filename=%s custom_instruction=%s self_healing=%s",
        request_id,
        file.filename,
        bool(custom_instruction),
        self_healing,
    )

    import io
    import json
    import os
    import tempfile
    import zipfile

    from backend.src.shared.models import AccessibilityIssue

    # Parse list of issues
    try:
        issues_list = json.loads(issues)
        issues_parsed = [AccessibilityIssue(**issue) for issue in issues_list]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Parâmetro 'issues' inválido: {e}") from e

    # Parse approved_issue_ids
    approved_ids = None
    if approved_issue_ids:
        try:
            approved_ids = json.loads(approved_issue_ids)
        except Exception:
            approved_ids = [x.strip() for x in approved_issue_ids.split(",") if x.strip()]

    try:
        # Descompacta arquivos na memória
        zip_content = await file.read()
        accepted_files = {} # path -> bytes
        ignored_patterns = {"node_modules/", ".git/", "dist/", "build/", ".next/", "__pycache__/"}

        with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
            for name in z.namelist():
                if name.endswith("/") or any(pattern in name for pattern in ignored_patterns):
                    continue
                with z.open(name) as f:
                    accepted_files[name] = f.read()

        changes_summary_all = []
        fixed_count = 0

        for name, file_bytes in list(accepted_files.items()):
            # Filtra issues deste arquivo específico
            file_issues = [
                issue for issue in issues_parsed
                if issue.url == name or (issue.url and issue.url.replace("\\", "/").rstrip("/") == name.replace("\\", "/").rstrip("/"))
            ]
            if not file_issues:
                continue

            if approved_ids is not None:
                file_issues = [issue for issue in file_issues if issue.id in approved_ids]
                if not file_issues:
                    continue

            ext = os.path.splitext(name)[1].lower()

            try:
                if ext == ".docx":
                    from backend.src.services.chat_tools import _fix_docx_document, _read_docx_text
                    content_str = _read_docx_text(io.BytesIO(file_bytes))
                    fixed_bytes = await _fix_docx_document(name, content_str, custom_instruction)
                    accepted_files[name] = fixed_bytes
                    changes_summary_all.append(f"[{name}] Documento DOCX estruturado de forma acessível.")
                    fixed_count += 1
                elif ext == ".pdf":
                    from backend.src.services.chat_tools import _fix_pdf_document_to_html, _read_pdf_text
                    content_str = _read_pdf_text(io.BytesIO(file_bytes))
                    fixed_html = await _fix_pdf_document_to_html(name, content_str, custom_instruction)
                    html_name = os.path.splitext(name)[0] + ".html"
                    # Remove o PDF original e insere o HTML gerado
                    del accepted_files[name]
                    accepted_files[html_name] = fixed_html.encode("utf-8")
                    changes_summary_all.append(f"[{name}] PDF convertido para HTML acessível: {html_name}")
                    fixed_count += 1
                else:
                    content_str = file_bytes.decode("utf-8", errors="replace")
                    if self_healing:
                        from backend.src.services.self_healing import run_self_healing_loop
                        fixed_str, changes, _ = await run_self_healing_loop(
                            content_str,
                            file_issues,
                            approved_issue_ids=approved_ids,
                            custom_instruction=custom_instruction
                        )
                        changes_summary_all.extend([f"[{name}] {c}" for c in changes])
                    else:
                        from backend.src.agents.fixer.fixer import run_fixer
                        fix_res = await run_fixer(
                            content_str,
                            file_issues,
                            request_id=request_id,
                            approved_issue_ids=approved_ids,
                            custom_instruction=custom_instruction
                        )
                        if fix_res.success:
                            fixed_str = fix_res.data.get("fixed_html", content_str)
                            changes = fix_res.data.get("changes_summary", [])
                            changes_summary_all.extend([f"[{name}] {c}" for c in changes])
                        else:
                            fixed_str = content_str
                    accepted_files[name] = fixed_str.encode("utf-8")
                    fixed_count += 1
            except Exception as e:
                logger.error("[Route] Falha ao corrigir arquivo do ZIP %s: %s", name, e)
                changes_summary_all.append(f"[{name}] Falha na correção: {e}")

        # Compacta os arquivos resultantes
        unique_id = uuid.uuid4().hex[:12]
        zip_filename = f"qa-project-fixed-{unique_id}.zip"
        temp_dir = tempfile.gettempdir()
        exports_dir = os.path.join(temp_dir, "qa_accessibility_exports")
        os.makedirs(exports_dir, exist_ok=True)
        zip_filepath = os.path.join(exports_dir, zip_filename)

        with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as z:
            for name, file_bytes in accepted_files.items():
                z.writestr(name, file_bytes)

        download_url = f"{get_settings().resolved_public_base_url()}/export/download_zip/{zip_filename}"

        return AgentResult(
            agent="fixer",
            success=True,
            data={
                "download_url": download_url,
                "zip_filename": zip_filename,
                "changes_summary": changes_summary_all,
                "fixed_count": fixed_count,
            }
        )
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Arquivo ZIP inválido ou corrompido.") from exc
    except Exception as exc:
        logger.error("[Route] Falha ao processar ZIP para correção: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
