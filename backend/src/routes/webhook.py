"""
webhook.py
Endpoint FastAPI para integração CI/CD com GitHub e GitLab.

Permite que pipelines de CI executem auditoria de acessibilidade automaticamente
em cada Pull Request, retornando um relatório estruturado com score e issues.

Segurança: valida assinatura HMAC-SHA256 (X-Hub-Signature-256) quando
WEBHOOK_SECRET estiver configurado na variável de ambiente.

Fonte: documentação oficial GitHub Webhooks 2026 + FastAPI BackgroundTasks.
"""

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Armazenamento em memória dos resultados de jobs (produção deve usar Redis/DB)
_job_results: dict[str, dict[str, Any]] = {}


class AnalyzePayload(BaseModel):
    url: str = ""
    html: str = ""
    max_pages: int = 1
    callback_url: str = ""


def _verify_github_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Valida a assinatura HMAC-SHA256 do GitHub/GitLab se WEBHOOK_SECRET estiver definido."""
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if not secret:
        return True  # Sem segredo configurado, aceita todos os pedidos
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _run_analysis_job(job_id: str, payload: AnalyzePayload) -> None:
    """Executa a análise em background e guarda o resultado no dicionário de jobs."""
    _job_results[job_id] = {"status": "running"}
    try:
        from backend.src.agents.orchestrator.orchestrator import orchestrate
        from backend.src.routes.analyze import _extract_semantic_html
        from backend.src.shared.models import TaskType

        html = payload.html
        url = payload.url

        if url and not html:
            from backend.src.services.browser import fetch_rendered_html_screenshot_and_focus_states
            html, _screenshot, _focus_screenshots = await fetch_rendered_html_screenshot_and_focus_states(url)

        if not html:
            _job_results[job_id] = {"status": "error", "error": "Nenhum html ou url fornecido."}
            return

        semantic_html = _extract_semantic_html(html)
        result = await orchestrate(semantic_html, TaskType.ANALYZE)
        if not result.success:
            _job_results[job_id] = {"status": "error", "error": result.error or "Falha na análise."}
            return
        issues = result.data.get("issues", [])
        _severity_deduction = {"critical": 20, "high": 10, "medium": 5, "low": 2}
        by_severity: dict[str, int] = {}
        for iss in issues:
            sev = iss.get("severity", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
        score = max(0, 100 - sum(_severity_deduction.get(sev, 0) * count for sev, count in by_severity.items()))

        _job_results[job_id] = {
            "status": "done",
            "url": url or "(html inline)",
            "score": score,
            "total_issues": len(issues),
            "issues_by_severity": by_severity,
            "critical_issues": issues[:5],
            "passed": score >= 80,
        }
        logger.info("[webhook] Job %s concluído: score=%s issues=%d", job_id, score, len(issues))
    except Exception as exc:
        logger.error("[webhook] Job %s falhou: %s", job_id, exc)
        _job_results[job_id] = {"status": "error", "error": str(exc)}


@router.post("/analyze")
async def webhook_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Inicia uma auditoria de acessibilidade via webhook.

    Compatível com GitHub Actions, GitLab CI e qualquer sistema de CI/CD.
    Responde imediatamente com job_id e executa a análise em background.
    Valida assinatura HMAC-SHA256 se WEBHOOK_SECRET estiver configurado.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_github_signature(body, signature):
        raise HTTPException(status_code=401, detail="Assinatura de webhook inválida.")

    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido.") from exc

    payload = AnalyzePayload(
        url=data.get("url", ""),
        html=data.get("html", ""),
        max_pages=int(data.get("max_pages", 1)),
        callback_url=data.get("callback_url", ""),
    )

    if not payload.url and not payload.html:
        raise HTTPException(status_code=400, detail="Forneça url ou html no payload.")

    job_id = str(uuid.uuid4())
    background_tasks.add_task(_run_analysis_job, job_id, payload)
    logger.info("[webhook] Job %s aceite: url=%s", job_id, payload.url)
    return {"status": "accepted", "job_id": job_id}


@router.get("/result/{job_id}")
async def webhook_result(job_id: str) -> dict[str, Any]:
    """
    Consulta o resultado de um job de auditoria iniciado via /webhook/analyze.
    Devolve status 'running' enquanto a análise está em curso, ou o resultado completo.
    """
    result = _job_results.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return result
