import json
import logging
import uuid

from backend.src.services.llm_client import call_llm, extract_json_object
from backend.src.shared.models import (
    AccessibilityIssue,
    AgentResult,
    ChecklistItem,
    ReportOutput,
    Severity,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a caring and empathetic accessibility consultant writing a report for a
development team. Your tone is warm, direct, and human — like a colleague who
genuinely wants to help the team improve, not a robot listing errors.

Given a list of accessibility issues and a checklist, write a short executive
summary and calculate an accessibility score (0–100).

TONE RULES (strictly enforced):
- Write as if speaking to a person, not a machine
- Use plain, conversational language — no technical jargon unless necessary
- Acknowledge effort made and frame issues as opportunities
- Never use markdown formatting: no **, no ***, no ###, no bullet dashes with dashes
- Write in flowing prose, not bullet points
- Keep it to 2–4 natural sentences
- If there are no issues, celebrate it genuinely

Score guide: 100 = fully accessible, 0 = completely inaccessible.
Deduct points: critical=-20, high=-10, medium=-5, low=-2 (minimum 0).

Return a JSON object with:
- summary: the human, empathetic summary string (2-4 sentences, plain prose only)
- score: integer 0-100

Return ONLY valid JSON. No markdown, no preamble.
""".strip()


def _calculate_score(issues: list[AccessibilityIssue]) -> int:
    deductions = {
        Severity.CRITICAL: 20,
        Severity.HIGH: 10,
        Severity.MEDIUM: 5,
        Severity.LOW: 2,
    }
    total = sum(deductions.get(i.severity, 0) for i in issues)
    return max(0, 100 - total)


async def run_reporter(
    issues: list[AccessibilityIssue],
    checklist: list[ChecklistItem],
    fixed_html: str | None = None,
) -> AgentResult:
    logger.info("[ReporterAgent] Gerando relatório com %d issues", len(issues))

    payload = {
        "issues": [i.model_dump() for i in issues],
        "checklist": [c.model_dump() for c in checklist],
    }
    user_prompt = f"Generate report for:\n{json.dumps(payload, indent=2)}"

    try:
        raw = await call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
        )
        result: dict = extract_json_object(raw)
        report = ReportOutput(
            report_id=str(uuid.uuid4()),
            summary=result["summary"],
            score=result.get("score", _calculate_score(issues)),
            issues=issues,
            checklist=checklist,
            fixed_html=fixed_html,
        )
        logger.info("[ReporterAgent] Relatório gerado, score=%d", report.score)
        return AgentResult(
            agent="reporter",
            success=True,
            data=report.model_dump(),
        )
    except Exception as exc:
        logger.error("[ReporterAgent] Erro: %s", exc)
        return AgentResult(agent="reporter", success=False, data={}, error=str(exc))
