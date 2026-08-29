"""
url_scan_history_store.py
Histórico da última análise real POR URL (não por sessão/conversa) -- permite
comparar uma nova análise contra a análise anterior da MESMA URL, mesmo vindo
de uma conversa diferente, dias depois, pra detectar regressão real.

Decisão do usuário (2026-08-11): "shift-right" sob demanda -- roda quando o
usuário pede via chat (reanalisando uma URL já vista antes), não agendado
sozinho (sem scheduler, sem infraestrutura nova de cron). Regressão real
achada é reportada pra IA oferecer `create_github_issue` (ferramenta já
existente) -- nunca cria a issue sozinha, segue a mesma regra de aprovação
de qualquer ação com efeito.
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["get_previous_scan", "save_scan", "diff_scans"]

_HISTORY_DIR = os.path.join(tempfile.gettempdir(), "qa_accessibility_url_history")


def _url_slug(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]


def _filepath(url: str) -> str:
    return os.path.join(_HISTORY_DIR, f"{_url_slug(url)}.json")


def get_previous_scan(url: str) -> dict[str, Any] | None:
    """Devolve o snapshot da última análise real dessa URL (issues +
    timestamp), ou None se nunca foi analisada antes neste ambiente."""
    if not url:
        return None
    path = _filepath(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[UrlScanHistory] Falha ao ler histórico de %s: %s", url, exc)
        return None


def save_scan(url: str, issues: list[dict[str, Any]]) -> None:
    """Salva o snapshot atual como a nova referência pra próxima comparação
    dessa URL. Sobrescreve o snapshot anterior -- guarda só o mais recente,
    suficiente pro caso de uso "mudou desde a última vez que testei isso"."""
    if not url:
        return
    path = _filepath(url)
    try:
        os.makedirs(_HISTORY_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"url": url, "issues": issues, "scanned_at": time.time()},
                f, ensure_ascii=False, indent=2,
            )
    except OSError as exc:
        logger.warning("[UrlScanHistory] Falha ao salvar histórico de %s: %s", url, exc)


def _issue_key(issue: dict[str, Any]) -> tuple[str, str]:
    """Chave de correspondência entre scans -- aproximada por natureza:
    (criterion, element) é o par mais estável disponível entre execuções
    reais do LLM (severidade/descrição podem variar levemente na redação
    entre chamadas mesmo pro MESMO problema real; criterion+element é o que
    mais se repete de forma consistente)."""
    return (
        str(issue.get("criterion", "")).strip().lower(),
        str(issue.get("element", "")).strip().lower(),
    )


def diff_scans(previous_issues: list[dict[str, Any]], current_issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Compara dois snapshots reais de issues -- devolve o que é NOVO
    (regressão real, não existia antes) e o que foi RESOLVIDO (existia antes,
    não aparece mais)."""
    previous_keys = {_issue_key(i) for i in previous_issues}
    current_keys = {_issue_key(i) for i in current_issues}

    new_issues = [i for i in current_issues if _issue_key(i) not in previous_keys]
    resolved_issues = [i for i in previous_issues if _issue_key(i) not in current_keys]

    return {
        "new_issues_count": len(new_issues),
        "resolved_issues_count": len(resolved_issues),
        "new_issues": new_issues,
        "resolved_issues": resolved_issues,
    }
