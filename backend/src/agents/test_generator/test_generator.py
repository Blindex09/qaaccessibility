import asyncio
import json
import logging

from backend.src.services.llm_client import call_llm_structured, extract_json_array
from backend.src.shared.models import AccessibilityIssue, AccessibilityTest, AgentResult, TestSuite

logger = logging.getLogger(__name__)

# Um teste por issue, cada um com bloco de codigo pronto para colar no CI --
# a saida cresce linearmente com os achados. Pedir tudo numa resposta so
# estourava o orcamento com volume real: medido em 2026-08-30, /analyze/tests
# devolveu 500 ("empty final response") com 32 issues, e passou com os mesmos
# 32 numa execucao anterior -- ou seja, ficava na borda e falhava por sorte.
# Mesmo lote de 20 que o a11y_expert_reviewer usa pelo mesmo motivo.
_BATCH_SIZE = 20

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


# Variante em LOTE: mesma disciplina de teste do SYSTEM_PROMPT acima, mas
# devolvendo apenas a LISTA de testes. O envelope da suite (setup, instrucoes
# de CI, contagem) e identico entre lotes e e montado em Python -- pedi-lo N
# vezes gastaria tokens repetindo a mesma coisa e deixaria `total_tests`
# discordar da lista.
SYSTEM_PROMPT_LOTE = (
    SYSTEM_PROMPT.split("## Output schema")[0]
    + """## Output schema: a JSON ARRAY, one object per issue given to you
[
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

ONE test per issue given to you. Do NOT invent tests for issues not listed.
Do NOT emit setup/imports or CI instructions -- those are added separately.
Return ONLY the JSON array. No markdown fences, no prose.
"""
).strip()


_SETUP_SNIPPET = """// npm i -D @playwright/test @axe-core/playwright
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';"""

_CI_INSTRUCTIONS = (
    "Rode `npx playwright test` no seu pipeline. Falhe o build quando houver violacao "
    "critical/serious. Reexecute a suite a cada PR que toque template, CSS ou componente "
    "de UI -- barreira de acessibilidade volta silenciosa em refactor."
)


async def _gerar_testes_do_lote(lote: list[AccessibilityIssue], target: str) -> list[AccessibilityTest]:
    """Gera os testes de UM lote de issues.

    Devolve uma LISTA de testes, nao a suite inteira: o envelope (setup,
    instrucoes de CI, contagem) e identico entre lotes e e montado pelo
    chamador, sem gastar tokens repetindo-o nem arriscar `total_tests`
    discordar da lista.
    """
    resumo = json.dumps(
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
            for i in lote
        ],
        ensure_ascii=False,
        indent=2,
    )
    testes = await call_llm_structured(
        system_prompt=SYSTEM_PROMPT_LOTE,
        user_prompt=(
            f"Target under test: {target or 'the analyzed page'}\n\n"
            f"Generate one test per issue for these {len(lote)} issues "
            f"(ordered by severity):\n\n{resumo}"
        ),
        build=lambda raw: [AccessibilityTest(**t) for t in extract_json_array(raw)],
        temperature=0.1,
        max_tokens=16384,
        agent_label="test_generator",
    )
    logger.info("[TestGenerator] Lote de %d issues -> %d testes", len(lote), len(testes))
    return testes


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

    # A serializacao dos issues foi para `_gerar_testes_do_lote`: cada lote
    # manda so os seus, e nao a lista inteira.
    try:
        lotes = [sorted_issues[i : i + _BATCH_SIZE] for i in range(0, len(sorted_issues), _BATCH_SIZE)]
        resultados = await asyncio.gather(*[_gerar_testes_do_lote(lote, target) for lote in lotes])
        testes = [teste for lote in resultados for teste in lote]

        # O envelope da suite (setup, instrucoes de CI, contagem) e o MESMO
        # qualquer que seja o lote -- montar em Python evita pedir N vezes a
        # mesma coisa ao modelo e evita `total_tests` discordar da lista.
        suite = TestSuite(
            target=target or "unknown",
            total_tests=len(testes),
            tests=testes,
            setup_snippet=_SETUP_SNIPPET,
            ci_instructions=_CI_INSTRUCTIONS,
        )

        logger.info(
            "[TestGenerator] Suite gerada -- %d testes para %d issues em %d lote(s)",
            suite.total_tests,
            len(issues),
            len(lotes),
        )

        return AgentResult(agent="test_generator", success=True, data={"suite": suite.model_dump()})

    except Exception as exc:
        logger.error("[TestGenerator] Falha ao gerar testes: %s", exc)
        return AgentResult(agent="test_generator", success=False, data={}, error=str(exc))
