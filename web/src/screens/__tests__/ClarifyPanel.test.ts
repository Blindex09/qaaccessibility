/* eslint-env jest, node */

import { readFileSync } from "fs";
import { join } from "path";

/**
 * O painel de clarify é React Native e o jest aqui roda em ambiente node sem o
 * preset do RN, portanto não há renderizador. A lógica de decisão (que forma o
 * evento tem, que risco tem a ferramenta) está em funções puras testadas a sério
 * em `services/__tests__/clarifyModel.test.ts`; o que sobra e importa fixar aqui
 * é o contrato de marcação do componente — sobretudo o de acessibilidade, que é
 * o próprio produto que esta app testa.
 */
const source = readFileSync(join(__dirname, "..", "ClarifyPanel.tsx"), "utf8");

describe("ClarifyPanel — controle de aprovação", () => {
  test("o botão de negar não é rotulado como 'pular'", () => {
    expect(source).not.toMatch(/>\s*Pular\s*</);
    expect(source).not.toMatch(/accessibilityLabel="Pular/);
  });

  test("o botão que envia resposta vazia é rotulado como cancelar", () => {
    // Âncora no botão (`onPress`), não no primeiro `answer("")` do ficheiro —
    // o Escape do diálogo também nega, e nega pela mesma via.
    const denyButton = source.slice(source.indexOf('onPress={() => answer("")}'));
    expect(denyButton).toMatch(/accessibilityLabel="Cancelar/);
    expect(denyButton.slice(0, 400)).toMatch(/>\s*Cancelar\s*</);
  });
});

describe("ClarifyPanel — cartão de aprovação", () => {
  test("mostra a ferramenta como crachá, e não enterrada na prosa", () => {
    expect(source).toMatch(/toolBadge:/);
    expect(source).toMatch(/\{toolLabel\}/);
  });

  test("os argumentos saem como lista de definição no web, não como JSON cru", () => {
    expect(source).toMatch(/createElement\("dl"/);
    expect(source).toMatch(/createElement\(\s*"dt"/);
    expect(source).toMatch(/createElement\(\s*"dd"/);
  });

  test("cada nível de risco tem cor, glifo E texto próprios", () => {
    for (const risk of ["mutating", "artifact", "read"]) {
      expect(source).toMatch(new RegExp(`${risk}:\\s*\\{`));
    }
    // O texto do risco existe: a diferenciação nunca é só pela cor (WCAG 1.4.1).
    expect(source).toMatch(/label: "Altera algo fora da app/);
    expect(source).toMatch(/label: "Gera um arquivo/);
    expect(source).toMatch(/label: "Apenas consulta/);
  });

  test("o identificador da ação é mostrado por inteiro, sem truncar", () => {
    expect(source).toMatch(/\{digest\}/);
    expect(source).not.toMatch(/digest\.slice\(/);
  });
});

describe("ClarifyPanel — checklist do plano", () => {
  test("os três estados de passo têm glifo próprio", () => {
    expect(source).toMatch(/STEP_GLYPH[\s\S]*?done:[\s\S]*?current:[\s\S]*?pending:/);
  });

  test("o estado de cada passo também aparece em texto visível", () => {
    expect(source).toMatch(/\{statusText\}/);
  });

  test("cada passo anuncia posição e estado ao leitor de tela", () => {
    expect(source).toMatch(/Passo \$\{index \+ 1\} de \$\{steps\.length\}, \$\{statusText\}/);
  });

  test("no web a checklist sai com semântica de lista", () => {
    expect(source).toMatch(/createElement\("ul"/);
    expect(source).toMatch(/createElement\("li"/);
  });

  test("os glifos decorativos ficam escondidos do leitor de tela", () => {
    const glyph = source.slice(source.indexOf("function DecorativeGlyph"));
    expect(glyph.slice(0, 500)).toMatch(/accessibilityElementsHidden/);
    expect(glyph.slice(0, 500)).toMatch(/aria-hidden/);
  });
});

describe("ClarifyPanel — acessibilidade geral", () => {
  // A semântica de diálogo/região e a gestão de foco são verificadas no DOM a
  // sério em `ClarifyPanel.a11y.test.tsx`, não por texto-fonte.

  test("todos os alvos de toque respeitam os 44px do WCAG 2.5.8", () => {
    const targets = ["choiceBtn", "sendBtn", "input"];
    for (const target of targets) {
      const block = source.slice(source.indexOf(`${target}: {`));
      expect(block.slice(0, 300)).toMatch(/minHeight: 44/);
    }
  });
});
