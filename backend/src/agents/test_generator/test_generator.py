import json
import logging

from backend.src.services.llm_client import call_llm_structured, extract_json_object
from backend.src.shared.models import AccessibilityIssue, AgentResult, TestSuite

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Agente: TestGenerator
#
# Fontes:
#   playwright-expert.toml    (C:\agents\general\playwright-expert.toml)
#   accessibility-tester.md   (C:\agents\security\accessibility-tester.md)
#   tdd-orchestrator.toml     (C:\agents\architecture\tdd-orchestrator.toml)
#
# Papel no pipeline:
#   Executa APOS o ReporterAgent (via rota /analyze/tests).
#   Dado o conjunto de issues encontrados, gera código de teste real -
#   Playwright + axe-core - que o time do projeto auditado pode colar
#   no seu proprio CI para garantir que as violacoes não reapareçam.
#
# playwright-expert.toml: POM, semantic locators (getByRole/getByLabel),
#   assertions com mensagens claras, retry para conteúdo dinâmico, CI config
# accessibility-tester.md: checklist WCAG 2.2, keyboard nav, SR compat,
#   form validation, live regions, landmarks, heading hierarchy
# tdd-orchestrator.toml: red-green-refactor discipline, test isolation,
#   determinism, coverage por criticidade
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an expert accessibility test engineer combining:
- Playwright & Cypress end-to-end testing (cypress-axe, Page Object Model, semantic locators)
- Selenium WebDriver testing (axe-selenium-python, Pytest)
- Postman / Newman API contract testing for accessibility attributes
- axe-core automated accessibility scanning (@axe-core/playwright, jest-axe)
- NVDA real keyboard navigation test procedures (Insert+F7, Tab, Shift+Tab, H, Esc)
- WCAG 2.2 Level AA test procedures
- TDD red-green-refactor discipline

Generate REAL, RUNNABLE test code the development team can paste into CI for Playwright, Cypress, Postman, or Selenium, along with NVDA manual test steps.

## Supported Frameworks & Testing Patterns:
1. PLAYWRIGHT + @axe-core/playwright:
   - Use page.getByRole(), page.getByLabel(), page.getByText()
   - Inject AxeBuilder from @axe-core/playwright and assert violations array is empty.
   - Test SPA route navigation: verify focus moves to page `h1[tabindex="-1"]` or `<main tabindex="-1">`.
   - Test DOM element deletion: verify focus moves to sibling element or container instead of dropping to body.
   - Code Snippet Example:
     ```typescript
     import { test, expect } from '@playwright/test';
     import AxeBuilder from '@axe-core/playwright';

     test.describe('Accessibility Suite', () => {
       test('should have zero axe-core accessibility violations', async ({ page }) => {
         await page.goto('/');
         const results = await new AxeBuilder({ page })
           .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
           .analyze();
         expect(results.violations).toEqual([]);
       });

       test('should move focus to h1 on SPA navigation', async ({ page }) => {
         await page.goto('/');
         await page.getByRole('link', { name: 'Nav' }).click();
         await expect(page.locator('h1[tabindex="-1"]')).toBeFocused();
       });
     });
     ```

2. NVDA KEYBOARD NAVIGATION PROCEDURES:
   - Include explicit test steps simulating or verifying NVDA screen reader keyboard shortcuts:
     * `Insert+F7` (or `NVDA+F7`): Open Elements List dialog (Headings outline, Links, Landmarks, Form controls).
     * `Tab` / `Shift+Tab`: Forward and backward sequential focus order across interactive controls.
     * `H` / `Shift+H`: Jump forward/backward between headings (`1`–`6` for specific heading levels).
     * `Esc`: Dismiss modal dialogs, popovers, or menus and return focus to triggering element.
     * `NVDA+space`: Toggle between Browse Mode and Focus Mode for complex custom widgets.

3. CYPRESS (cypress-axe):
   - Use cy.visit(), cy.injectAxe(), cy.checkA11y()
   - Support scoped checks: cy.checkA11y('#container', { includedImpacts: ['critical', 'serious'] })

4. POSTMAN / NEWMAN:
   - Generate JSON collection / test scripts validating API data attributes (alt_text, aria_label, status)
   - Assert pm.expect(jsonData.score).to.be.at.least(80)

5. SELENIUM (python/java):
   - Use Axe(driver) from axe_selenium_python
   - Call axe.inject() and axe.run() with assertions.

## Test rules:
1. Use semantic locators whenever possible
2. Each test is fully isolated
3. Assertions have descriptive failure messages
4. Include waitFor/waitForSelector for dynamic content

## WCAG 2.2 test patterns:
- Missing alt text: check img.getAttribute("alt") not null/empty
- Keyboard access: Tab navigation, verify focus reaches interactive element
- SPA routing focus: verify focus moves to h1[tabindex="-1"] on route change
- Element deletion focus: verify focus moves to sibling control after item deletion
- ARIA labels: check accessible name via aria-label or aria-labelledby
- Color contrast: use axe-core "color-contrast" rule
- Form errors: verify aria-describedby links to error element
- Focus management: verify focus moves correctly after user action

- Each test targets ONE specific issue
- Descriptive names: "should have alt text on hero image"
- Critical/high: Playwright E2E tests (most reliable)
- Medium/low: axe-core rule-specific tests (faster)

## Output schema (JSON object, no markdown):
{
  "target": "<url or filename>",
  "total_tests": <number>,
  "setup_snippet": "<imports and config>",
  "ci_instructions": "<step-by-step CI integration>",
  "tests": [
    {
      "test_id": "test-<n>",
      "criterion": "<WCAG criterion>",
      "severity": "critical|high|medium|low",
      "framework": "playwright|axe-core|jest-axe",
      "description": "<plain language what it validates>",
      "code": "<complete runnable test code>",
      "element_hint": "<selector or context>"
    }
  ]
}

ONE test per unique issue pattern. Group duplicate element instances.
Prioritize: critical > high > medium > low.
Return ONLY valid JSON object. No markdown fences.
"""


async def run_test_generator(
    issues: list[AccessibilityIssue],
    target: str = "",
) -> AgentResult:
    """
    Gera suite de testes Playwright + axe-core a partir dos issues encontrados.

    Baseado em:
    - playwright-expert.toml: POM, semantic locators, CI integration
    - accessibility-tester.md: WCAG 2.2 test procedures, AT testing patterns
    - tdd-orchestrator.toml: TDD discipline, test isolation, red-green-refactor
    """
    if not issues:
        logger.info("[TestGenerator] Nenhum issue -- suite vazia")
        return AgentResult(
            agent="test_generator",
            success=True,
            data={
                "suite": TestSuite(
                    target=target or "unknown",
                    total_tests=0,
                    tests=[],
                    setup_snippet="// Nenhum issue encontrado",
                    ci_instructions="Mantenha scans periodicos com axe-core.",
                ).model_dump()
            },
        )

    logger.info("[TestGenerator] Gerando testes para %d issues -- alvo: %s", len(issues), target or "desconhecido")

    # Ordena: critical primeiro (TDD: test critical paths first)
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_issues = sorted(issues, key=lambda i: (_order.get(i.severity.value, 9), i.criterion))

    issues_summary = json.dumps(
        [
            {
                "id": i.id,
                "criterion": i.criterion,
                "severity": i.severity.value,
                "element": i.element,
                "description": i.description,
                "suggestion": i.suggestion,
                "suggestion_technical": i.suggestion_technical or "",
                "wcag_url": i.wcag_url or "",
            }
            for i in sorted_issues
        ],
        ensure_ascii=False,
        indent=2,
    )

    try:
        suite = await call_llm_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=(
                f"Generate accessibility test suite for: {target or 'the analyzed page'}\n\n"
                f"Issues ({len(sorted_issues)}, ordered by severity):\n\n{issues_summary}"
            ),
            build=lambda raw: TestSuite(**extract_json_object(raw)),
            temperature=0.1,
            max_tokens=8192,
            agent_label="test_generator",
        )

        logger.info("[TestGenerator] Suite gerada -- %d testes para %d issues", suite.total_tests, len(issues))

        return AgentResult(agent="test_generator", success=True, data={"suite": suite.model_dump()})

    except Exception as exc:
        logger.error("[TestGenerator] Falha ao gerar testes: %s", exc)
        return AgentResult(agent="test_generator", success=False, data={}, error=str(exc))
