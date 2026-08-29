"""
ticket_integrations.py
Criacao automatica de tickets de acessibilidade em sistemas de gestao de
defeitos externos (Jira e Azure DevOps), a partir dos achados dos agentes.

Mesmo padrao de github_service.py: credenciais lidas de variaveis de
ambiente quando omitidas, simulacao graciosa (nunca derruba o chamador)
quando incompletas, chamada REST real caso contrario.

Fontes oficiais (pesquisadas 2026-08-27, nao memoria):
- Jira Cloud REST API v2 (developer.atlassian.com/cloud/jira/platform/rest/v2):
  POST {base_url}/rest/api/2/issue, Basic Auth (email + API token), aceita
  'description' em texto plano (a v3 exige Atlassian Document Format --
  desnecessario aqui).
- Azure DevOps REST API (learn.microsoft.com/rest/api/azure/devops/wit/work-items/create):
  POST https://dev.azure.com/{org}/{project}/_apis/wit/workitems/${type}?api-version=7.1,
  Content-Type application/json-patch+json, Basic Auth (usuario vazio + PAT),
  corpo e um array de operacoes JSON Patch.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Severity (shared.models.Severity) -> prioridade Jira. Jira Cloud usa os
# nomes de prioridade padrao do esquema default; instalacoes customizadas
# podem ter nomes diferentes, mas estes sao os nomes-padrao documentados.
_JIRA_PRIORITY_BY_SEVERITY = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

# Severity -> Microsoft.VSTS.Common.Severity do work item type "Bug" no
# processo padrao (Agile/Scrum/CMMI) do Azure DevOps.
_AZURE_SEVERITY_BY_SEVERITY = {
    "critical": "1 - Critical",
    "high": "2 - High",
    "medium": "3 - Medium",
    "low": "4 - Low",
}

_REQUEST_TIMEOUT_SECONDS = 15


def create_jira_issue(
    summary: str,
    description: str,
    severity: str = "medium",
    base_url: str | None = None,
    email: str | None = None,
    api_token: str | None = None,
    project_key: str | None = None,
    issue_type: str = "Bug",
) -> dict[str, Any]:
    """
    Cria uma Issue no Jira Cloud via REST API v2.

    Parametros
    ----------
    summary : str
        Titulo da issue (ex.: '[A11Y] WCAG 4.1.2 - Botão sem nome acessível').
    description : str
        Descrição em texto plano com os detalhes da violação e recomendação
        (ex.: `why_simple` + `suggestion` de um AccessibilityIssue).
    severity : str
        Um dos valores de shared.models.Severity ('critical'/'high'/'medium'/'low')
        -- mapeado para a prioridade do Jira.
    base_url / email / api_token / project_key :
        Dados da instância. Se omitidos, lê das variáveis de ambiente:
        JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY.
    """
    url_base = (base_url if base_url else os.getenv("JIRA_BASE_URL", "")).strip().rstrip("/")
    auth_email = (email if email else os.getenv("JIRA_EMAIL", "")).strip()
    token = (api_token if api_token else os.getenv("JIRA_API_TOKEN", "")).strip()
    project = (project_key if project_key else os.getenv("JIRA_PROJECT_KEY", "")).strip()

    if not url_base or not auth_email or not token or not project:
        logger.warning("[ticket_integrations] Credenciais do Jira incompletas. Simulando criação da issue.")
        return {
            "status": "simulated",
            "provider": "jira",
            "issue_key": "MOCK-1",
            "issue_url": f"{url_base or 'https://your-domain.atlassian.net'}/browse/MOCK-1",
            "summary": summary,
        }

    endpoint = f"{url_base}/rest/api/2/issue"
    payload: dict[str, Any] = {
        "fields": {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
            "priority": {"name": _JIRA_PRIORITY_BY_SEVERITY.get(severity, "Medium")},
        }
    }

    try:
        response = requests.post(endpoint, json=payload, auth=(auth_email, token), timeout=_REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 201:
            data = response.json()
            issue_key = data.get("key", "")
            issue_url = f"{url_base}/browse/{issue_key}"
            logger.info("[ticket_integrations] Issue Jira criada com sucesso: %s", issue_url)
            return {
                "status": "created",
                "provider": "jira",
                "issue_key": issue_key,
                "issue_url": issue_url,
                "summary": summary,
            }
        logger.error(
            "[ticket_integrations] Erro ao criar issue no Jira (HTTP %d): %s",
            response.status_code,
            response.text,
        )
        return {"status": "error", "provider": "jira", "error": response.text, "status_code": response.status_code}
    except Exception as exc:
        logger.error("[ticket_integrations] Exceção ao conectar ao Jira: %s", exc)
        return {"status": "error", "provider": "jira", "error": str(exc)}


def create_azure_devops_work_item(
    title: str,
    description: str,
    severity: str = "medium",
    organization: str | None = None,
    project: str | None = None,
    personal_access_token: str | None = None,
    work_item_type: str = "Bug",
) -> dict[str, Any]:
    """
    Cria um Work Item no Azure DevOps via REST API (JSON Patch).

    Parametros
    ----------
    title : str
        Titulo do work item.
    description : str
        Descrição em HTML/texto simples com os detalhes da violação e recomendação.
    severity : str
        Um dos valores de shared.models.Severity -- mapeado para
        Microsoft.VSTS.Common.Severity (só aplicável ao tipo "Bug").
    organization / project / personal_access_token :
        Dados da organização. Se omitidos, lê das variáveis de ambiente:
        AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT.
    """
    org = (organization if organization else os.getenv("AZURE_DEVOPS_ORG", "")).strip()
    proj = (project if project else os.getenv("AZURE_DEVOPS_PROJECT", "")).strip()
    pat = (personal_access_token if personal_access_token else os.getenv("AZURE_DEVOPS_PAT", "")).strip()

    if not org or not proj or not pat:
        logger.warning("[ticket_integrations] Credenciais do Azure DevOps incompletas. Simulando criação do work item.")
        return {
            "status": "simulated",
            "provider": "azure_devops",
            "work_item_id": 1,
            "work_item_url": f"https://dev.azure.com/{org or 'org'}/{proj or 'project'}/_workitems/edit/1",
            "title": title,
        }

    endpoint = f"https://dev.azure.com/{org}/{proj}/_apis/wit/workitems/${work_item_type}?api-version=7.1"
    patch_document = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": description},
    ]
    if work_item_type == "Bug":
        patch_document.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.Severity",
                "value": _AZURE_SEVERITY_BY_SEVERITY.get(severity, "3 - Medium"),
            }
        )

    try:
        response = requests.post(
            endpoint,
            json=patch_document,
            auth=("", pat),
            headers={"Content-Type": "application/json-patch+json"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code in (200, 201):
            data = response.json()
            work_item_id = data.get("id")
            work_item_url = f"https://dev.azure.com/{org}/{proj}/_workitems/edit/{work_item_id}"
            logger.info("[ticket_integrations] Work item Azure DevOps criado com sucesso: %s", work_item_url)
            return {
                "status": "created",
                "provider": "azure_devops",
                "work_item_id": work_item_id,
                "work_item_url": work_item_url,
                "title": title,
            }
        logger.error(
            "[ticket_integrations] Erro ao criar work item no Azure DevOps (HTTP %d): %s",
            response.status_code,
            response.text,
        )
        return {
            "status": "error",
            "provider": "azure_devops",
            "error": response.text,
            "status_code": response.status_code,
        }
    except Exception as exc:
        logger.error("[ticket_integrations] Exceção ao conectar ao Azure DevOps: %s", exc)
        return {"status": "error", "provider": "azure_devops", "error": str(exc)}
