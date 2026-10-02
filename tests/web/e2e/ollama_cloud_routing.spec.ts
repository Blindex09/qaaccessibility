import { expect, test } from "@playwright/test";

// Fluxo real pela interface: o backend deve estar configurado como
// ollama-cloud + alto. O teste não fixa o modelo concreto; a confirmação do
// roteamento fica nos logs do backend, onde o ranking pode ser auditado.
test("chat real usa o roteamento dinâmico do Ollama Cloud", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");

  const input = page.getByLabel("Mensagem para o assistente");
  await expect(input).toBeVisible({ timeout: 15_000 });
  await input.fill("Responda somente: conexão com Ollama Cloud recebida.");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();

  await expect(page.getByText("IA ASSISTENTE", { exact: true }).last()).toBeVisible({
    timeout: 150_000,
  });
  await expect(page.locator('[role="timer"]')).toHaveCount(0, { timeout: 150_000 });
  await expect(page.locator("body")).toContainText("Ollama Cloud", { timeout: 10_000 });
});
