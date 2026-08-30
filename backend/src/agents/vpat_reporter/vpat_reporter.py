import asyncio
import json
import logging
from collections import Counter
from datetime import date

from backend.src.services.llm_client import call_llm_structured, extract_json_array
from backend.src.shared.models import (
    AccessibilityIssue,
    AgentResult,
    ConformanceLevel,
    VPATCriterion,
    VPATReport,
)

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


SYSTEM_PROMPT_NIVEL = """
You are a senior compliance auditor with expertise in WCAG 2.2, Section 508,
EN 301 549, and VPAT (Voluntary Product Accessibility Template).

You evaluate ONE WCAG conformance level at a time. You receive the audit
findings and an explicit list of criteria, and you return the conformance
declaration for EXACTLY those criteria -- no more, no fewer.

## Conformance declarations
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

## Remarks (evidence-based)
1. State what was found or why the declaration was made
2. Reference specific issue IDs when applicable (e.g., "Issues: wcag-3, aria-7")
3. For "Not Evaluated": state what manual test is recommended
4. Be concise: 1-2 sentences max. Brevity matters -- the full report is large.

## Output schema: a JSON ARRAY, one object per criterion given to you
[
  {
    "criterion_id": "1.1.1",
    "criterion_name": "Non-text Content",
    "wcag_level": "A",
    "conformance": "Supports|Partially Supports|Does Not Support|Not Applicable|Not Evaluated",
    "remarks": "<evidence-based justification>",
    "issues_found": ["issue-id-1"]
  }
]

Return ONLY the JSON array. No markdown fences, no prose.
""".strip()


def _resumo_conformidade(contagem: Counter, total: int) -> str:
    """Resumo executivo derivado da CONTAGEM real, nao pedido ao modelo.

    Antes o `overall_conformance` vinha do LLM junto do resto do relatorio, o
    que permitia o texto discordar dos numeros ao lado dele. Percentual e
    aritmetica: calcular aqui elimina a chance de um VPAT afirmar conformidade
    diferente da que os proprios criterios mostram -- e VPAT e documento de
    licitacao.
    """
    if not total:
        return "Nenhum criterio avaliado."
    plenos = contagem[ConformanceLevel.SUPPORTS]
    parciais = contagem[ConformanceLevel.PARTIALLY_SUPPORTS]
    falhos = contagem[ConformanceLevel.DOES_NOT_SUPPORT]
    pct = round(100 * plenos / total, 1)
    return (
        f"{plenos} de {total} criterios WCAG 2.2 A/AA atendidos ({pct}%): "
        f"{parciais} com suporte parcial e {falhos} nao atendidos."
    )


async def _avaliar_nivel(
    criterios: list[dict[str, str]],
    nivel: str,
    issues_summary: str,
    total_issues: int,
    product_name: str,
    target: str,
    today: str,
) -> list[VPATCriterion]:
    """Avalia os criterios de UM nivel WCAG (A ou AA) numa chamada dedicada."""
    prompt = (
        f"Product: {product_name}\n"
        f"Target: {target or 'Not specified'}\n"
        f"Evaluation date: {today}\n\n"
        f"Issues found ({total_issues}):\n{issues_summary}\n\n"
        f"Evaluate EXACTLY these {len(criterios)} WCAG 2.2 Level {nivel} criteria:\n"
        f"{json.dumps(criterios, ensure_ascii=False)}"
    )
    avaliados = await call_llm_structured(
        system_prompt=SYSTEM_PROMPT_NIVEL,
        user_prompt=prompt,
        build=lambda raw: [VPATCriterion(**c) for c in extract_json_array(raw)],
        temperature=0.1,
        max_tokens=16384,
        agent_label=f"vpat_reporter_{nivel.lower()}",
    )
    logger.info("[VPATReporter] Nivel %s avaliado -- %d criterios", nivel, len(avaliados))
    return avaliados


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
        # Um VPAT completo sao 55 criterios (30 A + 25 AA), cada um com
        # `remarks` em texto livre. Pedir os 55 numa unica resposta estourava o
        # orcamento de saida de forma nao confiavel: medido em 2026-08-30, o
        # modelo devolvia VAZIO com 16k e AINDA truncava com 32k (a escalada
        # automatica de max_tokens em call_llm_structured levava mais longe,
        # mas nao resolvia). Dobrar token e remedio fragil e dependente de
        # provider -- falhou tanto em glm-5.3 quanto em gpt-oss:20b.
        #
        # A saida e a mesma que o a11y_expert_reviewer ja usa para o mesmo
        # problema: lote. Aqui o corte natural e o proprio nivel WCAG, que ja e
        # como o VPATReport separa os campos -- duas chamadas com metade da
        # saida cada, em paralelo, e os totais recalculados em Python (numero
        # derivado nao se pede a um LLM).
        criterios_a = [c for c in all_criteria if c["level"] == "A"]
        criterios_aa = [c for c in all_criteria if c["level"] == "AA"]

        nivel_a, nivel_aa = await asyncio.gather(
            _avaliar_nivel(criterios_a, "A", issues_summary, len(issues), product_name, target, today),
            _avaliar_nivel(criterios_aa, "AA", issues_summary, len(issues), product_name, target, today),
        )

        avaliados = nivel_a + nivel_aa
        contagem: Counter = Counter(c.conformance for c in avaliados)
        vpat = VPATReport(
            product_name=product_name,
            target=target or "Not specified",
            evaluation_date=today,
            overall_conformance=_resumo_conformidade(contagem, len(avaliados)),
            level_a_criteria=nivel_a,
            level_aa_criteria=nivel_aa,
            total_criteria_evaluated=len(avaliados),
            total_supports=contagem[ConformanceLevel.SUPPORTS],
            total_partially_supports=contagem[ConformanceLevel.PARTIALLY_SUPPORTS],
            total_does_not_support=contagem[ConformanceLevel.DOES_NOT_SUPPORT],
            total_not_applicable=contagem[ConformanceLevel.NOT_APPLICABLE],
        )

        logger.info(
            "[VPATReporter] VPAT gerado -- %d criterios (A=%d, AA=%d): %d Supports, %d Partially, %d DoesNot",
            vpat.total_criteria_evaluated,
            len(nivel_a),
            len(nivel_aa),
            vpat.total_supports,
            vpat.total_partially_supports,
            vpat.total_does_not_support,
        )

        return AgentResult(agent="vpat_reporter", success=True, data={"vpat": vpat.model_dump()})

    except Exception as exc:
        logger.error("[VPATReporter] Falha ao gerar VPAT: %s", exc)
        return AgentResult(agent="vpat_reporter", success=False, data={}, error=str(exc))
