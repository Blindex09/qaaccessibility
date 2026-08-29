"""
github_service.py
Módulo para criação automática de Issues no GitHub / GitLab a partir dos
achados de acessibilidade.

Suporta a API REST oficial do GitHub (versão 2026-03-10).
Permite que os agentes registrem automaticamente bugs de acessibilidade
em repositórios remotos.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def create_github_issue(
    title: str,
    body: str,
    repo_owner: str | None = None,
    repo_name: str | None = None,
    token: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """
    Cria uma nova Issue no repositório GitHub especificado via REST API.

    Parâmetros
    ----------
    title : str
        Título da Issue (ex.: '[A11Y] WCAG 1.1.1 - Imagem sem alt').
    body : str
        Descrição em Markdown contendo os detalhes da violação e recomendação.
    repo_owner / repo_name / token :
        Dados do repositório. Se omitidos, lê das variáveis de ambiente:
        GITHUB_OWNER, GITHUB_REPO, GITHUB_TOKEN.
    labels : list[str]
        Tags para a Issue (default: ['accessibility', 'automated-audit']).
    """
    owner = repo_owner or os.getenv("GITHUB_OWNER", "").strip()
    repo = repo_name or os.getenv("GITHUB_REPO", "").strip()
    auth_token = token or os.getenv("GITHUB_TOKEN", "").strip()

    if not owner or not repo or not auth_token:
        logger.warning("[github_service] Credenciais do GitHub incompletas. Simulando criação da Issue.")
        return {
            "status": "simulated",
            "issue_url": f"https://github.com/{owner or 'owner'}/{repo or 'repo'}/issues/mock-1",
            "title": title,
        }

    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    payload = {
        "title": title,
        "body": body,
        "labels": labels or ["accessibility", "automated-audit"],
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 201:
            data = response.json()
            logger.info("[github_service] Issue criada com sucesso: %s", data.get("html_url"))
            return {
                "status": "created",
                "issue_url": data.get("html_url"),
                "number": data.get("number"),
                "title": title,
            }
        else:
            logger.error(
                "[github_service] Erro ao criar Issue (HTTP %d): %s",
                response.status_code, response.text
            )
            return {"status": "error", "error": response.text, "status_code": response.status_code}
    except Exception as exc:
        logger.error("[github_service] Exceção ao conectar ao GitHub: %s", exc)
        return {"status": "error", "error": str(exc)}
