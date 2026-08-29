# QA Accessibility — Workspace Agent Rules (2026)

Guidelines and behaviors for AI coding assistants working in the `qaaccessibility` repository.

## Rules & Constraints
1. **Model Filtering:** Only models released on or after `2026-01-01` are valid. Pre-2026 configurations and models are strictly excluded.
2. **Zero Hermes Dependency:** The codebase is fully decoupled from `hermes-agent`. Never import or configure anything from it.
3. **Scope Discipline:** Strictly stick to digital accessibility (WCAG 2.2, WAI-ARIA, Section 508, EAA, EN 301 549). Do not expand the scope or do unrequested general development tasks.
4. **No Emojis:** Zero emojis in terminals, logs, or chat replies.
5. **Portuguese Accentuation:** Rigorous Portuguese spelling and accentuation (use á, é, í, ó, ú, â, ê, ô, ã, õ, ç) to avoid screen reader mispronouncements.
