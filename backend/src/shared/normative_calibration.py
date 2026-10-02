"""Normative facts, not a deterministic classifier of accessibility findings."""

NORMATIVE_CALIBRATION = """
NORMATIVE CALIBRATION (takes precedence over pattern checklists):
Separate an observed DOM fact, an accessibility recommendation and a proven
WCAG failure. A recommended implementation technique is not itself mandatory.
WCAG 2.4.6 requires existing headings/labels to describe their topic or purpose;
it does NOT require a heading to exist. Absence of h1, multiple h1, a skipped
heading level or absence of main/header/nav alone does not establish failure.
For 1.3.1, establish that actual information/relationships conveyed by presentation
cannot be programmatically determined or provided as text. A document's <title>
does not imply that its body contains a visually presented heading. The inability
to jump with a heading-navigation shortcut when no headings exist is not, by
itself, evidence of a WCAG failure. A claim such as 'no h1 corresponding to the
page title violates 1.3.1' is unsupported: identify an actual visually conveyed
relationship and show how the captured markup fails to represent it. Do not
invent prominent body text, a visual heading or an AT test from the page title.
If the captured document does not establish that relationship, report a heading
recommendation/limitation rather than a confirmed failure. For 2.4.1, establish
repeated blocks and lack of an effective bypass mechanism, not merely no main.
Do not emit these isolated patterns as confirmed violations, nor claim that
every page must have exactly one h1. If evidence is insufficient, explain the
limitation or recommendation separately, without inventing a failed criterion.
Judge in context; no automatic acceptance/rejection by keywords in descriptions.
For 2.4.4, assess link purpose with its programmatically determined context;
generic link text alone is not proof of failure. Do not infer inspected DOM
facts from an empty issue list: use observed_structure when supplied. If no
heading was observed, never claim an h1 exists merely because no failure was
reported. Say not confirmed / no violation identified in this limited scope,
not certified WCAG conformance from a partial automated assessment.
For partial inspections, say 'nenhuma violação confirmada no escopo avaliado',
not 'a página é conforme' or 'conforme com ressalvas'. A role's pass/fail/
pass_with_caveats verdict may describe completion of this scoped task, not certify
the site's accessibility. Preserve that distinction in summaries and final prose.
Do not soften an unsupported failure into 'not a critical violation': either the
criterion is supported by evidence or it remains an observation/recommendation.
Sources: https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html
https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html
https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks.html
""".strip()
