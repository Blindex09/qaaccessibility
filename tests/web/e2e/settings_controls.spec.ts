import { expect, test } from "@playwright/test";

test("configurações preservam aprovação obrigatória e permitem escolher modelos", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Configurações" }).click();

  await expect(page.getByText("Ações com efeito externo exigem sua aprovação antes da execução. Essa proteção não pode ser desligada.")).toBeVisible();
  await expect(page.getByRole("switch", { name: "Pedir aprovação antes de ações com efeito externo" })).toHaveCount(0);

  const models = page.locator('select[aria-labelledby="modelLabel"]');
  await expect(models).toBeVisible();
  await expect(models.locator('option[value="alto"]')).toContainText("seleção dinâmica");
});

test("trocar de provedor preserva a escolha de modelo de cada um sem salvar", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Configurações" }).click();
  const models = page.locator('select[aria-labelledby="modelLabel"]');
  await expect(models).toBeVisible();

  await page.getByRole("radio", { name: "OpenAI" }).click();
  await models.selectOption("alto");
  await page.getByRole("radio", { name: "Anthropic" }).click();
  await models.selectOption("");
  await page.getByRole("radio", { name: "OpenAI" }).click();
  await expect(models).toHaveValue("alto");
});
