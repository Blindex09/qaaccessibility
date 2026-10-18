"""What screen readers expose and say, as facts the chat and the specialists must respect.

The long, sourced references live in resources/leitor_de_tela_*.md (HTML elements per reader,
ARIA patterns, dynamic content / JavaScript / React / Astro, CSS and reader modes). This short
block carries only the rules that change how a finding is worded or judged, so every call that
talks about screen reader behaviour stays honest about what is defined and what is observed.
"""

SCREEN_READER_EXPECTATIONS = """
SCREEN READER EXPECTATIONS (sourced from W3C APG, WAI-ARIA 1.2, HTML-AAM, MDN, WCAG 2.2 and the
TetraLogical HTML support tests; the full references are in the knowledge base):
- The platform defines the role, name and state exposed to the reader; the exact words spoken, their
  order and the extra hints vary by reader, version, browser and verbosity setting. Never assert an
  exact utterance as a rule. Name the reader, browser and version when you cite behaviour, and mark
  speech and announcements as pending manual verification unless the accessibility tree proves them.
- Elements ignored or reduced when they lack a name: form and section (no landmark), fieldset (no group),
  figure and unnamed details. An <a> without href is plain text. header and footer inside article, section
  or main are not banner or contentinfo. alt="" is the valid mark for a decorative image; a missing alt
  attribute is the defect, and readers fall back differently (file name, "unlabelled"). Decorative or
  unnamed svg, canvas, iframe without title, and dd in item navigation are common silent spots.
- ARIA adds no behaviour: a role promises focus, keys and state the code must supply. Prefer the native
  element. aria-hidden removes content from the accessibility tree but NOT from the tab order; inert removes
  both. Names cannot be given to roles like paragraph, code, strong, emphasis, generic or presentation.
- Dynamic content is silent unless it is in a live region that already existed or it receives focus. A
  live region announcement is plain text and an alert must not take focus, so actions inside a toast can be
  missed; offer them in a dialog that takes focus or a permanent control. Moving focus is how a new screen,
  dialog or error summary is conveyed, and the router may already announce the page (Astro ClientRouter and
  Next.js read the title, then the h1, then the path), so do not require two mechanisms.
- A navigation menu of links is a disclosure pattern (button with aria-expanded and a list of links), not a
  role=menu widget; role=menu belongs to application menus with the full menu keyboard model.
""".strip()
