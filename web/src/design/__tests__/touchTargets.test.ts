/* eslint-env jest, node */

import { readFileSync } from "fs";
import { join } from "path";

import { a11y } from "../tokens";

/**
 * WCAG 2.5.8 (Target Size, Minimum) — 44×44 CSS px.
 *
 * Honestidade sobre a força deste teste: isto é uma verificação do VALOR
 * declarado no StyleSheet, não do tamanho renderizado. Não há renderizador de
 * RN neste projeto de teste, portanto não é possível medir a caixa real. Ainda
 * assim é mais forte do que procurar a string "44": lê o valor efetivo de cada
 * estilo e compara-o com `a11y.minTarget`, de modo que descer o valor faz o
 * teste falhar.
 */

const screensDir = join(__dirname, "..", "..", "screens");

function styleBlock(file: string, name: string): string {
  const source = readFileSync(join(screensDir, file), "utf8");
  const start = source.indexOf(`${name}: {`);
  if (start === -1) throw new Error(`estilo ${name} não encontrado em ${file}`);
  return source.slice(start, source.indexOf("},", start));
}

/** Lê `minHeight`/`height`/`width`/`minWidth`, resolvendo `a11y.minTarget`. */
function dimension(block: string, prop: string): number | null {
  const match = new RegExp(`${prop}:\\s*([A-Za-z0-9_.]+)`).exec(block);
  if (!match) return null;
  const raw = match[1];
  if (raw === "a11y.minTarget") return a11y.minTarget;
  const numeric = Number(raw);
  return Number.isNaN(numeric) ? null : numeric;
}

describe("WCAG 2.5.8 — alvos de toque de 44px", () => {
  test("a constante do design system é o mínimo da norma", () => {
    expect(a11y.minTarget).toBeGreaterThanOrEqual(44);
  });

  const targets: readonly [string, string, string][] = [
    ["ChatScreen.tsx", "backBtn", "minHeight"],
    ["SettingsScreen.tsx", "backBtn", "minHeight"],
    ["SettingsScreen.tsx", "radioButton", "minHeight"],
    ["SettingsScreen.tsx", "toggleBtn", "width"],
    ["SettingsScreen.tsx", "serviceKeySaveBtn", "height"],
    ["SettingsScreen.tsx", "serviceKeySaveBtn", "minWidth"],
  ];

  test.each(targets)("%s › %s.%s ≥ 44", (file, style, prop) => {
    const value = dimension(styleBlock(file, style), prop);
    expect(value).not.toBeNull();
    expect(value as number).toBeGreaterThanOrEqual(44);
  });

  test("toggleBtn mantém também a altura de 44", () => {
    expect(dimension(styleBlock("SettingsScreen.tsx", "toggleBtn"), "height")).toBeGreaterThanOrEqual(44);
  });
});
