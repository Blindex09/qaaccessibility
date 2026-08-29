import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Auditoria de acessibilidade da própria UI (chat-first).
// O app é uma ferramenta de a11y — então ele audita a si mesmo (dogfooding).
test.describe("Acessibilidade da interface (chat-first)", () => {
  test("não deve ter violações axe-core (A, AA, best-practice)", async ({ page }) => {
    await page.goto("/");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(serious, JSON.stringify(serious.map((v) => v.id))).toHaveLength(0);
  });

  test("possui exatamente um h1 (banner) e o título do chat como h2", async ({ page }) => {
    await page.goto("/");
    const h1 = await page.locator("h1, [role=heading][aria-level='1']").count();
    expect(h1).toBe(1);
    await expect(
      page.locator("h2, [role=heading][aria-level='2']").first(),
    ).toContainText("Assistente");
  });

  test("tem skip link e landmarks main/banner", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: /pular para o conteúdo/i })).toBeAttached();
    await expect(page.locator("[role=main], main")).toHaveCount(1);
    await expect(page.locator("[role=banner], header")).toHaveCount(1);
  });

  test("controles do chat têm nome acessível", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByLabel("Mensagem para o assistente")).toBeVisible();
    await expect(page.getByLabel("Anexar arquivos ou projeto para análise")).toBeVisible();
    await expect(page.getByLabel("Enviar mensagem")).toBeVisible();
  });

  test("todos os botões têm nome acessível", async ({ page }) => {
    await page.goto("/");
    const buttons = page.getByRole("button");
    const count = await buttons.count();
    for (let i = 0; i < count; i++) {
      const btn = buttons.nth(i);
      const label = await btn.getAttribute("aria-label");
      const text = await btn.textContent();
      expect(label || text?.trim()).toBeTruthy();
    }
  });

  test("botão enviar começa desabilitado", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByLabel("Enviar mensagem")).toBeDisabled();
  });
});
