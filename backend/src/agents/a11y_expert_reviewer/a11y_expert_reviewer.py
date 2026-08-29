import json
import logging

from backend.src.services.llm_client import call_llm, extract_json_array
from backend.src.shared.models import AccessibilityIssue, AgentResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Agente: A11yExpertReviewer
#
# Fonte: accessibility-expert.toml + accessibility-specialist.toml
#   (C:\agents\frontend\accessibility-expert.toml)
#   (C:\agents\frontend\accessibility-specialist.toml)
#
# Papel no pipeline:
#   Executa APOS os sub-agentes paralelos + merge/dedup.
#   Recebe a lista consolidada de issues e aplica revisao holistica de
#   especialista senior em acessibilidade:
#
#   1. Remove falsos positivos - padrões que ferramentas automatizadas
#      flagam incorretamente (ex: aria-label em elemento ja aria-hidden)
#   2. Re-score de severidade - alinha com impacto real em AT (NVDA, JAWS,
#      VoiceOver, TalkBack) em vez de apenas com o nivel WCAG
#   3. Enriquece why_technical - adiciona modo de falha especifico por AT
#      quando ausente (ex: "NVDA + Firefox: anuncia como clickable sem label")
#   4. Detecta padrões sistemicos - agrupa issues com a mesma causa raiz
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior accessibility expert with deep expertise in WCAG 2.1/2.2,
WAI-ARIA 1.2, Section 508, EN 301 549, and real-world assistive technology
compatibility (NVDA, JAWS, VoiceOver, TalkBack, Voice Control, Switch Access).

You have received a consolidated list of accessibility issues found by multiple
specialized sub-agents. Your job is to perform a holistic expert review.

## Your four-step review process (from accessibility-expert.toml)

### Step 1 - False Positive Removal
Remove issues that are not genuine accessibility barriers:
- Flagging aria-label on an element that already has aria-hidden="true"
- Flagging missing alt on a <img> that has role="presentation"
- Flagging color contrast on text that is aria-hidden
- Flagging heading order when out-of-order heading is inside aria-modal dialog
- Duplicate issues where criterion + element are identical
- Flagging redundant native roles that browsers expose correctly (e.g. role="button" on <button>) UNLESS explicitly violating spec rules

### Step 1.5 - ARIA Prohibited Attribute (aria-prohibited-attr) & AccName 1.2 Enforcement
Ensure genuine W3C specification violations are preserved and highlighted:
- Preserve issues for aria-label/aria-labelledby on generic <div>/<span> (without role), presentation, or inline text
- Preserve issues for aria-sort on buttons (must be on <th scope="col">)
- Preserve issues for aria-checked on options (option uses aria-selected)
- Preserve SC 2.5.3 (Label in Name) violations where aria-label strips the visible text label

### Step 2 - Severity Re-scoring (by real AT user impact)
- CRITICAL: Completely blocks access for a disability group
- HIGH: Severely degrades experience but workaround exists
- MEDIUM: Reduces quality but task can be completed
- LOW: Best practice violation with minimal real-world impact

### Step 3 - AT-Specific Enrichment (from accessibility-specialist.toml)
Enrich why_technical with specific AT failure modes when missing:
- "NVDA + Firefox: announces the element as clickable without action label"
- "JAWS 2024: skips element entirely in Forms Mode due to missing role"
- "VoiceOver iOS: double-tap activates wrong target due to touch area overlap"
- "TalkBack: cannot reach this element via swipe navigation"

### Step 4 - Systemic Pattern Detection
If 3+ issues share the same root cause, add to description:
"[SYSTEMIC PATTERN] This issue appears in X+ elements, indicating a
missing global rule in the design system or CSS framework."

### Step 5 - Contextual Location Enrichment
Enrich the 'description' field to specify the exact location of the element on the page based on nearby headings, sections, or landmarks (e.g., "the 'more' link located in the popular posts section", "the search button in the top header"). Avoid vague descriptions.

## Output rules
- REMOVE false positives (do not include them)
- MODIFY severity, why_technical, description when needed
- ADD systemic pattern notes to description when applicable
- KEEP all other fields unchanged
- NEVER add new issues
- NEVER modify id, guideline, criterion, element, wcag_url, criterion_pt

Return ONLY valid JSON array. No markdown. Empty array [] if all false positives.
""".strip()


async def run_a11y_expert_reviewer(
    issues: list[AccessibilityIssue],
    known_false_positive_patterns: list[dict] | None = None,
) -> AgentResult:
    """
    Revisao holistica especializada dos issues consolidados.

    Invocado sequencialmente apos os agentes paralelos + merge/dedup.
    Aplica expertise de accessibility-expert.toml + accessibility-specialist.toml:
    - Remove falsos positivos
    - Re-score severidade por impacto AT real (NVDA/JAWS/VoiceOver/TalkBack)
    - Enriquece why_technical com modo de falha especifico por AT
    - Detecta padrões sistemicos entre issues

    `known_false_positive_patterns` (ver lessons_store.py): padrões
    (criterion + assinatura de elemento) já confirmados como falso positivo
    repetidamente em análises PASSADAS de páginas diferentes -- memória
    persistente entre análises, não desta chamada. Quando presente, vira uma
    dica extra no prompt: reforça a decisão quando o padrão bate de novo,
    nunca remove automaticamente sem o modelo reavaliar o caso concreto.

    Batch processing: quando ha muitos issues (>25), processa em lotes para
    não estourar o limite de tokens de saida do modelo.
    Falha graceful: se falhar, retorna os issues originais sem perda de dados.
    """
    if not issues:
        logger.info("[A11yExpertReviewer] Nenhum issue para revisar")
        return AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [], "removed_false_positives": 0},
        )

    logger.info(
        "[A11yExpertReviewer] Revisando %d issues -- AT: NVDA/JAWS/VoiceOver/TalkBack",
        len(issues),
    )

    # Batch processing: quando muitos issues, divide em lotes de 20
    BATCH_SIZE = 20
    if len(issues) > BATCH_SIZE:
        return await _review_in_batches(
            issues, batch_size=BATCH_SIZE, known_false_positive_patterns=known_false_positive_patterns
        )

    return await _review_single_batch(issues, known_false_positive_patterns=known_false_positive_patterns)


def _format_known_patterns_hint(known_false_positive_patterns: list[dict] | None) -> str:
    if not known_false_positive_patterns:
        return ""
    lines = [
        f"- {p['criterion']} on elements matching `{p['element_signature']}` "
        f"(confirmed false positive {int(p.get('count', 0))}x across past analyses)"
        for p in known_false_positive_patterns
    ]
    return (
        "\n\n## Learned false-positive patterns (from past analyses of OTHER pages)\n"
        "These structural patterns have been repeatedly confirmed as false positives "
        "in previous reviews. If a current issue matches one of these patterns AND your "
        "own analysis agrees it's not a genuine violation, remove it with more confidence. "
        "This is a HINT, not a rule -- always verify against the actual element, never "
        "remove solely because it matches a past pattern.\n" + "\n".join(lines)
    )


async def _review_single_batch(
    issues: list[AccessibilityIssue],
    known_false_positive_patterns: list[dict] | None = None,
) -> AgentResult:
    """Processa um único lote de issues (ate ~20 itens)."""
    issues_json = json.dumps(
        [i.model_dump() for i in issues],
        ensure_ascii=False,
        indent=2,
    )

    try:
        raw = await call_llm(
            system_prompt=SYSTEM_PROMPT + _format_known_patterns_hint(known_false_positive_patterns),
            user_prompt=(
                f"Review these {len(issues)} consolidated accessibility issues "
                f"and apply the four-step expert review:\n\n{issues_json}"
            ),
            temperature=0.1,
            max_tokens=16384,
        )

        reviewed_dicts = extract_json_array(raw)
        reviewed = [AccessibilityIssue(**i) for i in reviewed_dicts]
        removed = len(issues) - len(reviewed)

        logger.info(
            "[A11yExpertReviewer] Revisao concluida -- %d issues mantidos, %d falsos positivos removidos",
            len(reviewed),
            removed,
        )

        return AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={
                "issues": [i.model_dump() for i in reviewed],
                "removed_false_positives": removed,
                "original_count": len(issues),
                "reviewed_count": len(reviewed),
            },
        )

    except Exception as exc:
        logger.error("[A11yExpertReviewer] Falha na revisao especializada: %s", exc)
        return AgentResult(
            agent="a11y_expert_reviewer",
            success=False,
            data={
                "issues": [i.model_dump() for i in issues],
                "removed_false_positives": 0,
                "fallback": True,
            },
            error=str(exc),
        )


async def _review_in_batches(
    issues: list[AccessibilityIssue],
    batch_size: int = 20,
    known_false_positive_patterns: list[dict] | None = None,
) -> AgentResult:
    """
    Divide issues em lotes, processa cada lote em paralelo, e mergea.
    Garante que nenhum lote estoure o limite de tokens de saida.
    """
    logger.info(
        "[A11yExpertReviewer] Batch review: %d issues em lotes de %d",
        len(issues),
        batch_size,
    )

    batches = [issues[i : i + batch_size] for i in range(0, len(issues), batch_size)]

    # Processa lotes em paralelo (max 3 concorrentes)
    import asyncio

    semaphore = asyncio.Semaphore(3)

    async def _process_batch(batch: list[AccessibilityIssue], idx: int) -> AgentResult:
        async with semaphore:
            logger.info("[A11yExpertReviewer] Processando lote %d/%d (%d issues)", idx + 1, len(batches), len(batch))
            return await _review_single_batch(batch, known_false_positive_patterns=known_false_positive_patterns)

    results = await asyncio.gather(*[_process_batch(batch, i) for i, batch in enumerate(batches)])

    # Merge: mantem so os issues que passaram na revisao de cada lote
    all_reviewed: list[dict] = []
    total_removed = 0
    total_original = 0
    has_failure = False

    for result in results:
        if result.success:
            all_reviewed.extend(result.data.get("issues", []))
            total_removed += result.data.get("removed_false_positives", 0)
            total_original += result.data.get("original_count", 0)
        else:
            has_failure = True
            # Se um lote falhou, mantem os issues originais daquele lote
            all_reviewed.extend(result.data.get("issues", []))
            total_original += len(result.data.get("issues", []))

    logger.info(
        "[A11yExpertReviewer] Batch review concluido -- %d issues mantidos, %d falsos positivos removidos",
        len(all_reviewed),
        total_removed,
    )

    return AgentResult(
        agent="a11y_expert_reviewer",
        success=not has_failure,
        data={
            "issues": all_reviewed,
            "removed_false_positives": total_removed,
            "original_count": total_original,
            "reviewed_count": len(all_reviewed),
            "batch_count": len(batches),
        },
        error="Um ou mais lotes falharam" if has_failure else None,
    )
