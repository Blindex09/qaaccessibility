/* eslint-env jest, node */

import { colors } from "../tokens";

/**
 * Teste de contraste real: calcula a razão a partir dos valores dos tokens pela
 * fórmula de luminância relativa da WCAG 2.2, em vez de comparar strings de cor.
 *
 * Um teste que só verifica "o hex não mudou" dá falsa confiança em acessibilidade
 * — foi exatamente assim que `accent.DEFAULT` (2.49:1 com texto branco) e
 * `danger.DEFAULT` (3.76:1) passaram despercebidos enquanto o cabeçalho do
 * ficheiro de tokens afirmava que tudo estava validado contra a WCAG AA. Aqui,
 * qualquer cor nova que reprove faz o teste falhar sozinho.
 */

function relativeLuminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => {
    const srgb = parseInt(value.slice(offset, offset + 2), 16) / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : Math.pow((srgb + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string): number {
  const a = relativeLuminance(foreground);
  const b = relativeLuminance(background);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("fórmula de contraste", () => {
  test("reproduz os valores de referência da WCAG", () => {
    // Preto sobre branco é o máximo teórico, 21:1.
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 2);
    // Uma cor contra ela própria é o mínimo, 1:1.
    expect(contrastRatio("#14B8A6", "#14B8A6")).toBeCloseTo(1, 5);
    // Par conhecido: #767676 é o cinzento-limite de 4.5:1 sobre branco.
    expect(contrastRatio("#767676", "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#777777", "#FFFFFF")).toBeLessThan(4.54);
  });
});

describe("WCAG 1.4.3 — texto branco sobre fundos de botão sólidos (≥4.5:1)", () => {
  // Estes são os fundos que recebem `text.onAccent`: botão enviar, botão parar,
  // botão de resposta do ClarifyPanel, guardar do modal, guardar das definições
  // e o botão flutuante de pré-visualização.
  const solidButtonBackgrounds: readonly [string, string][] = [
    ["accent.DEFAULT", colors.accent.DEFAULT],
    ["accent.hover", colors.accent.hover],
    ["danger.DEFAULT", colors.danger.DEFAULT],
  ];

  test.each(solidButtonBackgrounds)("%s vs text.onAccent", (name, background) => {
    const ratio = contrastRatio(colors.text.onAccent, background);
    expect({ name, ratio: Number(ratio.toFixed(2)) }).toMatchObject({
      name,
      ratio: expect.any(Number),
    });
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  test("os valores antigos reprovados não voltam", () => {
    // Regressão explícita: teal-500 e red-500 como fundo de botão.
    expect(contrastRatio("#FFFFFF", "#14B8A6")).toBeLessThan(4.5);
    expect(contrastRatio("#FFFFFF", "#EF4444")).toBeLessThan(4.5);
    expect(colors.accent.DEFAULT).not.toBe("#14B8A6");
    expect(colors.danger.DEFAULT).not.toBe("#EF4444");
  });
});

describe("WCAG 1.4.3 — tokens de texto sobre as suas superfícies (≥4.5:1)", () => {
  const textPairs: readonly [string, string, string][] = [
    ["text.primary sobre bg.root", colors.text.primary, colors.bg.root],
    ["text.secondary sobre bg.root", colors.text.secondary, colors.bg.root],
    ["text.tertiary sobre bg.root", colors.text.tertiary, colors.bg.root],
    ["accent.text sobre bg.root", colors.accent.text, colors.bg.root],
    ["accent.text sobre bg.surface", colors.accent.text, colors.bg.surface],
    ["danger.text sobre bg.surface", colors.danger.text, colors.bg.surface],
    ["warning.text sobre bg.surface", colors.warning.text, colors.bg.surface],
    ["success.text sobre bg.surface", colors.success.text, colors.bg.surface],
    ["info.text sobre bg.surface", colors.info.text, colors.bg.surface],
  ];

  test.each(textPairs)("%s", (_name, foreground, background) => {
    expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("WCAG 1.4.11 — bordas e indicadores não textuais (≥3:1)", () => {
  // `accent.DEFAULT` também é borda (ClarifyPanel, cartão de estado das
  // definições, rádio ativo) e cor do ActivityIndicator: escurecê-lo para passar
  // 1.4.3 não pode fazê-lo reprovar 1.4.11 contra o fundo escuro.
  const nonTextPairs: readonly [string, string, string][] = [
    ["accent.DEFAULT sobre bg.root", colors.accent.DEFAULT, colors.bg.root],
    ["accent.DEFAULT sobre bg.surface", colors.accent.DEFAULT, colors.bg.surface],
    ["border.focus sobre bg.root", colors.border.focus, colors.bg.root],
    ["border.focus sobre bg.surface", colors.border.focus, colors.bg.surface],
  ];

  test.each(nonTextPairs)("%s", (_name, foreground, background) => {
    expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(3);
  });
});
