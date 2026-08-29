/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import { ClarifyPanel } from "../ClarifyPanel";

/**
 * Teste comportamental do painel de clarify: o componente é montado a sério
 * (o `react-native` resolve para `react-native-web` no jest deste projeto) e o
 * que se verifica é o DOM e o foco resultantes — os atributos que o leitor de
 * tela lê e o `document.activeElement` que o teclado sente.
 *
 * O que está sendo corrigido: o pedido de aprovação é o ponto de decisão mais
 * arriscado da app (aprova uma ferramenta que reescreve o código do
 * usuário) e era a única superfície interativa sem tratamento de diálogo.
 * Plano e pergunta continuam a NÃO prender o teclado — são informativos.
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

const APPROVAL_QUESTION =
  "A ferramenta 'fix_and_zip_files' realizará uma ação com efeito externo ou gravará um artefato. " +
  `Argumentos: {"path": "site.zip"}. Identificador da ação: ${"b".repeat(64)}. ` +
  "Aprovar exatamente esta ação?";

const PLAN_QUESTION = "Vou fazer assim:\n1. Rastrear o site\n2. Analisar contraste";
const OPEN_QUESTION = "Qual URL devo testar?";

let host: HTMLDivElement;
let root: Root;
let outside: HTMLButtonElement;

beforeEach(() => {
  outside = document.createElement("button");
  document.body.appendChild(outside);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

function renderPanel(question: string, onAnswer: (value: string) => void = () => {}): void {
  act(() => {
    root.render(<ClarifyPanel question={question} choices={["Sim", "Não"]} onAnswer={onAnswer} />);
  });
}

/** O foco inicial do diálogo é agendado num `requestAnimationFrame`. */
async function flushFrame(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });
}

function panel(): HTMLElement {
  const node = host.firstElementChild as HTMLElement | null;
  if (!node) throw new Error("painel não montou");
  return node;
}

describe("ClarifyPanel — aprovação inline na conversa", () => {
  test("sai no DOM como região inline, sem modal", async () => {
    renderPanel(APPROVAL_QUESTION);
    await flushFrame();
    const region = panel();
    expect(region.getAttribute("role")).toBe("region");
    expect(region.getAttribute("aria-modal")).toBeNull();

    const labelledBy = region.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    // O nome acessível aponta para um nó que existe e diz alguma coisa.
    expect(document.getElementById(labelledBy as string)?.textContent).toBe(
      "Esta ação precisa da sua aprovação",
    );
  });

  test("a aprovação não rouba o foco da conversa", async () => {
    outside.focus();
    renderPanel(APPROVAL_QUESTION);
    await flushFrame();
    expect(document.activeElement).toBe(outside);
  });

  test("os botões continuam disponíveis no fluxo inline", async () => {
    renderPanel(APPROVAL_QUESTION);
    await flushFrame();
    const focusable = panel().querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input:not([disabled]), select, textarea',
    );
    expect(focusable.length).toBeGreaterThan(1);
    expect(focusable.length).toBeGreaterThan(1);
  });

  test("Escape nega a ação — sair pelo teclado nunca aprova nada", async () => {
    const onAnswer = jest.fn();
    renderPanel(APPROVAL_QUESTION, onAnswer);
    await flushFrame();
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    // Resposta vazia = negar; o backend falha-fechado.
    expect(onAnswer).toHaveBeenCalledWith("");
  });

  test("ao fechar devolve o foco a quem estava trabalhando antes", async () => {
    outside.focus();
    renderPanel(APPROVAL_QUESTION);
    await flushFrame();
    expect(document.activeElement).not.toBe(outside);
    act(() => root.render(<></>));
    expect(document.activeElement).toBe(outside);
  });

  test("não é live region: o foco já anuncia, duas vias falariam duas vezes", async () => {
    renderPanel(APPROVAL_QUESTION);
    await flushFrame();
    expect(panel().hasAttribute("aria-live")).toBe(false);
    expect(host.querySelectorAll("[aria-live]")).toHaveLength(0);
  });
});

describe("ClarifyPanel — plano e pergunta são informativos, não modais", () => {
  test.each([
    ["plano", PLAN_QUESTION],
    ["pergunta", OPEN_QUESTION],
  ])("%s sai como região com nome, não como diálogo", async (_label, question) => {
    renderPanel(question);
    await flushFrame();
    const region = panel();
    expect(region.getAttribute("role")).toBe("region");
    expect(region.hasAttribute("aria-modal")).toBe(false);
    const labelledBy = region.getAttribute("aria-labelledby");
    expect(document.getElementById(labelledBy as string)?.textContent).toBeTruthy();
  });

  test.each([
    ["plano", PLAN_QUESTION],
    ["pergunta", OPEN_QUESTION],
  ])("%s não rouba o foco de quem está lendo a conversa", async (_label, question) => {
    outside.focus();
    renderPanel(question);
    await flushFrame();
    expect(document.activeElement).toBe(outside);
  });

  test.each([
    ["plano", PLAN_QUESTION],
    ["pergunta", OPEN_QUESTION],
  ])("%s não prende o teclado nem é fechado por Escape", async (_label, question) => {
    const onAnswer = jest.fn();
    renderPanel(question, onAnswer);
    await flushFrame();
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(onAnswer).not.toHaveBeenCalled();
  });

  test.each([
    ["plano", PLAN_QUESTION],
    ["pergunta", OPEN_QUESTION],
  ])("%s não traz live region própria — quem anuncia é a região persistente do ChatScreen", async (
    _label,
    question,
  ) => {
    renderPanel(question);
    await flushFrame();
    expect(host.querySelectorAll("[aria-live]")).toHaveLength(0);
  });
});
