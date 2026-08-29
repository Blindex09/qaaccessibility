import json
import logging
from datetime import date

from backend.src.services.llm_client import call_llm_structured, extract_json_object
from backend.src.shared.models import AccessibilityIssue, AgentResult, VPATReport

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Agente: VPATReporter
#
# Fonte: compliance-auditor.md (C:\agents\security\compliance-auditor.md)
#
# Papel no pipeline:
#   Executa APOS os issues serem consolidados (via rota /analyze/vpat).
#   Gera um VPAT - Voluntary Product Accessibility Template, WCAG 2.2 Edition.
#   Documento padrão exigido por enterprise, governo (Section 508) e licitacoes.
#
# compliance-auditor.md aplicado:
#   - Regulatory frameworks: WCAG 2.2, Section 508, EN 301 549
#   - Gap analysis: mapeia issues para criterios WCAG
#   - Conformance declarations com evidence-based remarks
#   - Risk assessment: criterios criticos com peso maior
#   - Continuous compliance: data e necessidade de reavaliacao
# ─────────────────────────────────────────────────────────────────────────────

_WCAG_22_CRITERIA = {
    "A": [
        ("1.1.1", "Non-text Content"),
        ("1.2.1", "Audio-only and Video-only (Prerecorded)"),
        ("1.2.2", "Captions (Prerecorded)"),
        ("1.2.3", "Audio Description or Media Alternative (Prerecorded)"),
        ("1.3.1", "Info and Relationships"),
        ("1.3.2", "Meaningful Sequence"),
        ("1.3.3", "Sensory Characteristics"),
        ("1.4.1", "Use of Color"),
        ("1.4.2", "Audio Control"),
        ("2.1.1", "Keyboard"),
        ("2.1.2", "No Keyboard Trap"),
        ("2.1.4", "Character Key Shortcuts"),
        ("2.2.1", "Timing Adjustable"),
        ("2.2.2", "Pause, Stop, Hide"),
        ("2.3.1", "Three Flashes or Below Threshold"),
        ("2.4.1", "Bypass Blocks"),
        ("2.4.2", "Page Titled"),
        ("2.4.3", "Focus Order"),
        ("2.4.4", "Link Purpose (In Context)"),
        ("2.5.1", "Pointer Gestures"),
        ("2.5.2", "Pointer Cancellation"),
        ("2.5.3", "Label in Name"),
        ("2.5.4", "Motion Actuation"),
        ("3.1.1", "Language of Page"),
        ("3.2.1", "On Focus"),
        ("3.2.2", "On Input"),
        ("3.3.1", "Error Identification"),
        ("3.3.2", "Labels or Instructions"),
        ("4.1.2", "Name, Role, Value"),
        ("4.1.3", "Status Messages"),
    ],
    "AA": [
        ("1.2.4", "Captions (Live)"),
        ("1.2.5", "Audio Description (Prerecorded)"),
        ("1.3.4", "Orientation"),
        ("1.3.5", "Identify Input Purpose"),
        ("1.4.3", "Contrast (Minimum)"),
        ("1.4.4", "Resize Text"),
        ("1.4.5", "Images of Text"),
        ("1.4.10", "Reflow"),
        ("1.4.11", "Non-text Contrast"),
        ("1.4.12", "Text Spacing"),
        ("1.4.13", "Content on Hover or Focus"),
        ("2.4.5", "Multiple Ways"),
        ("2.4.6", "Headings and Labels"),
        ("2.4.7", "Focus Visible"),
        ("2.4.11", "Focus Not Obscured (Minimum)"),
        ("2.5.7", "Dragging Movements"),
        ("2.5.8", "Target Size (Minimum)"),
        ("3.1.2", "Language of Parts"),
        ("3.2.3", "Consistent Navigation"),
        ("3.2.4", "Consistent Identification"),
        ("3.2.6", "Consistent Help"),
        ("3.3.3", "Error Suggestion"),
        ("3.3.4", "Error Prevention (Legal, Financial, Data)"),
        ("3.3.7", "Redundant Entry"),
        ("3.3.8", "Accessible Authentication (Minimum)"),
    ],
}

SYSTEM_PROMPT = """
You are a senior compliance auditor with expertise in WCAG 2.2, Section 508,
EN 301 549, and VPAT (Voluntary Product Accessibility Template).

Generate a WCAG 2.2 Edition VPAT based on accessibility audit findings.

## Conformance declarations (compliance-auditor.md)
For each criterion declare ONE of:
- "Supports": No issues; product meets this criterion
- "Partially Supports": Some issues or criterion partially met
- "Does Not Support": Critical/high issues blocking conformance
- "Not Applicable": Criterion does not apply to this content type
- "Not Evaluated": Requires manual testing not yet performed

## Decision rules based on issues
- Criterion has CRITICAL issues -> "Does Not Support"
- Criterion has HIGH issues -> "Partially Supports" or "Does Not Support"
- Criterion has MEDIUM issues -> "Partially Supports"
- Criterion has LOW issues only -> "Supports" with caveat note
- No issues for this criterion -> "Supports"
- Criterion requires AT/human testing (1.2.x audio/video, 2.3.1 flashes) -> "Not Evaluated"
- Criterion clearly not applicable -> "Not Applicable"

## Remarks format (evidence-based, per compliance-auditor.md)
Each remarks must:
1. State what was found or why the declaration was made
2. Reference specific issue IDs when applicable (e.g., "Issues: wcag-3, aria-7")
3. For "Not Evaluated": state what manual test is recommended
4. Be concise: 1-3 sentences max

## Overall conformance summary
2-3 sentences: % Level A met, % Level AA met, most critical remediation areas.

## Output schema (JSON object, no markdown):
{
  "product_name": "<name>",
  "target": "<url or filename>",
  "wcag_version": "WCAG 2.2",
  "evaluation_date": "<YYYY-MM-DD>",
  "overall_conformance": "<executive summary>",
  "level_a_criteria": [
    {
      "criterion_id": "1.1.1",
      "criterion_name": "Non-text Content",
      "wcag_level": "A",
      "conformance": "Supports|Partially Supports|Does Not Support|Not Applicable|Not Evaluated",
      "remarks": "<evidence-based justification>",
      "issues_found": ["issue-id-1"]
    }
  ],
  "level_aa_criteria": [ ... ],
  "total_criteria_evaluated": <number>,
  "total_supports": <number>,
  "total_partially_supports": <number>,
  "total_does_not_support": <number>,
  "total_not_applicable": <number>
}

Return ONLY valid JSON. No markdown fences.
""".strip()


async def run_vpat_reporter(
    issues: list[AccessibilityIssue],
    target: str = "",
    product_name: str = "Produto Avaliado",
) -> AgentResult:
    """
    Gera VPAT - Voluntary Product Accessibility Template (WCAG 2.2 Edition).

    Baseado em compliance-auditor.md:
    - Gap analysis: mapeia issues para criterios WCAG 2.2 A e AA
    - Evidence-based conformance declarations por criterio
    - Resumo executivo de conformidade
    Exigido por enterprise, governo (Section 508) e processos de licitacao.
    """
    today = date.today().isoformat()
    logger.info("[VPATReporter] Gerando VPAT WCAG 2.2 -- %d issues, alvo: %s", len(issues), target or "desconhecido")

    all_criteria = [{"id": c[0], "name": c[1], "level": "A"} for c in _WCAG_22_CRITERIA["A"]] + [
        {"id": c[0], "name": c[1], "level": "AA"} for c in _WCAG_22_CRITERIA["AA"]
    ]

    issues_summary = json.dumps(
        [
            {
                "id": i.id,
                "criterion": i.criterion,
                "severity": i.severity.value,
                "guideline": i.guideline.value,
                "description": i.description[:200],
            }
            for i in issues
        ],
        ensure_ascii=False,
        indent=2,
    )

    try:
        vpat = await call_llm_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=(
                f"Generate WCAG 2.2 VPAT:\n"
                f"Product: {product_name}\n"
                f"Target: {target or 'Not specified'}\n"
                f"Evaluation date: {today}\n\n"
                f"Issues found ({len(issues)}):\n{issues_summary}\n\n"
                f"Criteria to evaluate ({len(all_criteria)}):\n"
                f"{json.dumps(all_criteria, ensure_ascii=False)}"
            ),
            build=lambda raw: VPATReport(**extract_json_object(raw)),
            temperature=0.1,
            max_tokens=8192,
            agent_label="vpat_reporter",
        )

        logger.info(
            "[VPATReporter] VPAT gerado -- %d criterios: %d Supports, %d Partially, %d DoesNot",
            vpat.total_criteria_evaluated,
            vpat.total_supports,
            vpat.total_partially_supports,
            vpat.total_does_not_support,
        )

        return AgentResult(agent="vpat_reporter", success=True, data={"vpat": vpat.model_dump()})

    except Exception as exc:
        logger.error("[VPATReporter] Falha ao gerar VPAT: %s", exc)
        return AgentResult(agent="vpat_reporter", success=False, data={}, error=str(exc))
