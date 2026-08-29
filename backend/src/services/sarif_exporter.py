import logging
from typing import Any

from backend.src.shared.models import AccessibilityIssue

logger = logging.getLogger(__name__)


def export_to_sarif(issues: list[AccessibilityIssue], url: str = "http://localhost") -> dict[str, Any]:
    """
    Converte a lista de AccessibilityIssue para o formato padrao SARIF 2.1.0 JSON.
    Permite integrar os relatorios de acessibilidade diretamente com o GitHub Actions / GitLab CI.
    """
    logger.info(f"[SARIFExporter] Gerando relatorio SARIF 2.1.0 para {len(issues)} issues...")

    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    level_map = {
        "critical": "error",
        "high": "error",
        "medium": "warning",
        "low": "note",
    }

    for issue in issues:
        rule_id = issue.id
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": issue.criterion.replace(" ", "_"),
                "shortDescription": {"text": issue.description},
                "fullDescription": {"text": issue.description_technical or issue.description},
                "help": {"text": f"{issue.suggestion}\n\nTechnical fix: {issue.suggestion_technical}"},
                "properties": {
                    "guideline": issue.guideline,
                    "level": issue.level,
                    "severity": issue.severity,
                },
            }

        sarif_level = level_map.get(issue.severity.lower(), "warning")

        results.append({
            "ruleId": rule_id,
            "level": sarif_level,
            "message": {
                "text": f"{issue.description} - Element: {issue.element}"
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": url,
                        },
                        "region": {
                            "snippet": {
                                "text": issue.element
                            }
                        }
                    }
                }
            ],
            "properties": {
                "why_technical": issue.why_technical,
                "suggestion_technical": issue.suggestion_technical,
            }
        })

    sarif_doc = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "QA Accessibility Engine",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/qa-accessibility",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ]
    }

    return sarif_doc
