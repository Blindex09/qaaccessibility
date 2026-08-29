/**
 * Teste E2E de acessibilidade REAL contra globo.com
 * Usa axe-core diretamente no browser — sem mock, sem API do backend.
 * Objetivo: verificar se o site tem problemas REAIS que o QA tool deveria detectar.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const TARGET_URL = "https://www.globo.com";

test.describe(`Auditoria de Acessibilidade Real — ${TARGET_URL}`, () => {
  test.setTimeout(60_000);

  test("axe-core: violações WCAG 2.x A e AA críticas e altas", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    // Aguarda conteúdo JS renderizar
    await page.waitForTimeout(3000);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();

    const critical = results.violations.filter((v) => v.impact === "critical");
    const serious = results.violations.filter((v) => v.impact === "serious");
    const moderate = results.violations.filter((v) => v.impact === "moderate");

    console.log("\n========== RESULTADO AXE-CORE EM GLOBO.COM ==========");
    console.log(`Total de violações: ${results.violations.length}`);
    console.log(`  critical: ${critical.length}`);
    console.log(`  serious:  ${serious.length}`);
    console.log(`  moderate: ${moderate.length}`);
    console.log(`  passes:   ${results.passes.length}`);
    console.log(`  incomplete: ${results.incomplete.length}`);

    if (results.violations.length > 0) {
      console.log("\n---------- DETALHAMENTO DAS VIOLAÇÕES ----------");
      for (const v of results.violations) {
        console.log(`\n[${v.impact?.toUpperCase()}] ${v.id}`);
        console.log(`  Descrição: ${v.description}`);
        console.log(`  Critério:  ${v.helpUrl}`);
        console.log(`  Elementos afetados: ${v.nodes.length}`);
        for (const node of v.nodes.slice(0, 3)) {
          console.log(`    - HTML: ${node.html.slice(0, 120)}`);
          console.log(`      Falha: ${node.failureSummary?.split("\n")[0]}`);
        }
      }
    }

    // O teste DEVE encontrar violações — globo.com tem issues conhecidos
    // Se violations === 0, isso prova que o axe também tem "silêncio" aqui
    console.log("\n========== FIM DO RELATÓRIO ==========\n");

    // NÃO falhar — apenas reportar; queremos o log completo
    expect(results.violations.length).toBeGreaterThanOrEqual(0);
  });

  test("Imagens sem alt text — verificação manual", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3000);

    const imgsWithoutAlt = await page.evaluate(() => {
      const imgs = Array.from(document.querySelectorAll("img"));
      return imgs
        .filter((img) => !img.hasAttribute("alt") || img.getAttribute("alt") === null)
        .map((img) => ({
          src: img.src?.slice(0, 80) || "(sem src)",
          role: img.getAttribute("role"),
          ariaLabel: img.getAttribute("aria-label"),
          html: img.outerHTML.slice(0, 120),
        }));
    });

    console.log(`\n[MANUAL] Imagens sem atributo alt: ${imgsWithoutAlt.length}`);
    for (const img of imgsWithoutAlt.slice(0, 10)) {
      console.log(`  src: ${img.src}`);
      console.log(`  html: ${img.html}\n`);
    }

    expect(imgsWithoutAlt.length).toBeGreaterThanOrEqual(0); // Só reportar
  });

  test("Links sem texto acessível — verificação manual", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3000);

    const emptyLinks = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll("a"));
      return links
        .filter((a) => {
          const text = a.textContent?.trim() || "";
          const ariaLabel = a.getAttribute("aria-label") || "";
          const title = a.getAttribute("title") || "";
          return !text && !ariaLabel && !title;
        })
        .map((a) => a.outerHTML.slice(0, 120));
    });

    console.log(`\n[MANUAL] Links sem texto acessível: ${emptyLinks.length}`);
    for (const link of emptyLinks.slice(0, 10)) {
      console.log(`  ${link}`);
    }

    expect(emptyLinks.length).toBeGreaterThanOrEqual(0);
  });

  test("Botões sem nome acessível — verificação manual", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3000);

    const emptyButtons = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button, [role='button']"));
      return buttons
        .filter((btn) => {
          const text = btn.textContent?.trim() || "";
          const ariaLabel = btn.getAttribute("aria-label") || "";
          const ariaLabelledby = btn.getAttribute("aria-labelledby") || "";
          const title = btn.getAttribute("title") || "";
          return !text && !ariaLabel && !ariaLabelledby && !title;
        })
        .map((btn) => btn.outerHTML.slice(0, 120));
    });

    console.log(`\n[MANUAL] Botões sem nome acessível: ${emptyButtons.length}`);
    for (const btn of emptyButtons.slice(0, 10)) {
      console.log(`  ${btn}`);
    }

    expect(emptyButtons.length).toBeGreaterThanOrEqual(0);
  });

  test("Campos de formulário sem label — verificação manual", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3000);

    const unlabeledInputs = await page.evaluate(() => {
      const inputs = Array.from(
        document.querySelectorAll("input:not([type='hidden']):not([type='submit']):not([type='button'])")
      );
      return inputs
        .filter((input) => {
          const id = input.getAttribute("id");
          const ariaLabel = input.getAttribute("aria-label") || "";
          const ariaLabelledby = input.getAttribute("aria-labelledby") || "";
          const title = input.getAttribute("title") || "";
          const placeholder = input.getAttribute("placeholder") || "";
          const hasLabel = id ? document.querySelector(`label[for="${id}"]`) : null;
          return !hasLabel && !ariaLabel && !ariaLabelledby && !title;
        })
        .map((input) => input.outerHTML.slice(0, 120));
    });

    console.log(`\n[MANUAL] Inputs sem label acessível: ${unlabeledInputs.length}`);
    for (const input of unlabeledInputs.slice(0, 10)) {
      console.log(`  ${input}`);
    }

    expect(unlabeledInputs.length).toBeGreaterThanOrEqual(0);
  });

  test("Heading hierarchy — verificação manual", async ({ page }) => {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3000);

    const headings = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, h6")).map((h) => ({
        tag: h.tagName,
        text: h.textContent?.trim().slice(0, 80) || "",
      }));
    });

    const h1count = headings.filter((h) => h.tag === "H1").length;

    console.log(`\n[MANUAL] Headings encontrados: ${headings.length}`);
    console.log(`  H1: ${h1count} (esperado: 1)`);
    for (const h of headings.slice(0, 15)) {
      console.log(`  <${h.tag.toLowerCase()}> ${h.text}`);
    }

    if (h1count !== 1) {
      console.log(
        `  ⚠️  PROBLEMA: ${h1count} h1 encontrados — deveria haver exatamente 1`
      );
    }

    expect(headings.length).toBeGreaterThanOrEqual(0);
  });
});
