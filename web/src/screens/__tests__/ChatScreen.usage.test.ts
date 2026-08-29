/* eslint-env jest, node */

import { readFileSync } from "fs";
import { join } from "path";

import { formatTokenCount } from "../../services/usage";

/**
 * O `usage` já vinha do backend em todos os caminhos de provider, mas nada na UI
 * o mostrava. O indicador é deliberadamente discreto (metadado de rodapé), não um
 * dashboard — o resto do contrato de marcação é verificado sobre o texto-fonte,
 * porque o jest aqui roda em node sem o preset do React Native.
 */
const source = readFileSync(join(__dirname, "..", "ChatScreen.tsx"), "utf8");

describe("formatTokenCount", () => {
  test("agrupa milhares à maneira pt-BR", () => {
    expect(formatTokenCount(1234)).toBe("1.234");
    expect(formatTokenCount(0)).toBe("0");
  });
});

describe("indicador de tokens", () => {
  test("retorna null para não exibir metadados de tokens na interface", () => {
    const note = source.slice(source.indexOf("function UsageNote"), source.indexOf("function processInlineLinks"));
    expect(note).toMatch(/return null;/);
  });
});
