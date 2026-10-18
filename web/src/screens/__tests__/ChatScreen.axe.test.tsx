/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import axe from "axe-core";

import type { ChatEvent } from "../../services/chat";
import { ChatScreen } from "../ChatScreen";

/**
 * Auditoria do chat com conteúdo real, a partir da pesquisa de comportamento do
 * leitor de tela (docs/modules/conhecimento_de_leitor_de_tela.md): nome acessível
 * em elemento sem papel não é exposto, listitem precisa de list, o nome visível
 * tem de estar dentro do nome acessível (2.5.3) e estado não se diz duas vezes.
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

let emit: (event: ChatEvent) => void;
let finishStream: () => void;

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  sendClarify: jest.fn(async () => true),
  sendCancel: jest.fn(async () => true),
  fetchChatHistory: jest.fn(async () => []),
  deleteChatHistory: jest.fn(async () => undefined),
  listConversations: jest.fn(async () => []),
  streamChat: jest.fn(
    (_text: string, _history: unknown, onEvent: (event: ChatEvent) => void) =>
      new Promise<void>((resolve) => {
        emit = onEvent;
        finishStream = resolve;
      }),
  ),
}));

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(<ChatScreen />));
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

function sendMessage(text: string): void {
  const field = host.querySelector<HTMLTextAreaElement>("textarea");
  if (!field) throw new Error("campo de mensagem não encontrado");
  const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  act(() => {
    setValue?.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const sendButton = host.querySelector<HTMLElement>('[aria-label="Enviar mensagem"]');
  if (!sendButton) throw new Error("botão de enviar não encontrado");
  act(() => {
    sendButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

/** Turno com atividade da squad, ferramenta em andamento e resposta com código. */
async function populate(): Promise<void> {
  sendMessage("Audite https://example.com/");
  act(() => {
    emit({ type: "phase", text: "Lendo a página" });
    emit({ type: "agent", phase: "start", agent: "aria_specialist" });
    emit({ type: "tool_start", tool_call_id: "t1", name: "analyze_page", arguments: {} });
  });
  act(() => {
    emit({ type: "token", text: "Encontrei um problema.\n\n```html\n<button></button>\n```\n" });
  });
  await act(async () => {
    emit({ type: "done", final: "Encontrei um problema.\n\n```html\n<button></button>\n```\n" });
    finishStream();
  });
}

describe("ChatScreen — árvore de acessibilidade com conteúdo", () => {
  test("o axe não aponta violação no chat populado", async () => {
    await populate();
    const results = await axe.run(host, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    const summary = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
    expect(summary).toEqual([]);
  });

  test("nenhum elemento sem papel recebe aria-label (não é exposto pelo leitor de tela)", async () => {
    await populate();
    const generic = Array.from(host.querySelectorAll<HTMLElement>("[aria-label]")).filter((node) => {
      if (node.getAttribute("role")) return false;
      return ["DIV", "SPAN", "P"].includes(node.tagName);
    });
    expect(generic.map((node) => node.getAttribute("aria-label"))).toEqual([]);
  });

  test("todo listitem tem um list como pai", async () => {
    await populate();
    const orphans = Array.from(host.querySelectorAll<HTMLElement>('[role="listitem"]')).filter(
      (node) => !node.parentElement?.closest('[role="list"], ul, ol'),
    );
    expect(orphans).toHaveLength(0);
  });

  test("o nome visível do botão está dentro do nome acessível (2.5.3)", async () => {
    await populate();
    const offenders = Array.from(host.querySelectorAll<HTMLElement>('[role="button"][aria-label], button[aria-label]'))
      .map((node) => ({ visible: (node.textContent || "").replace(/\s+/g, " ").trim(), name: node.getAttribute("aria-label") || "" }))
      .filter(({ visible, name }) => {
        const letters = visible.replace(/[^\p{L}\p{N} ]/gu, "").replace(/\s+/g, " ").trim().toLowerCase();
        return letters.length > 0 && !name.replace(/[^\p{L}\p{N} ]/gu, "").toLowerCase().includes(letters);
      });
    expect(offenders).toEqual([]);
  });

  test("aria-selected só aparece em papéis que o suportam", async () => {
    await populate();
    const allowed = ["option", "tab", "gridcell", "row", "columnheader", "rowheader", "treeitem"];
    const bad = Array.from(host.querySelectorAll<HTMLElement>("[aria-selected]")).filter(
      (node) => !allowed.includes(node.getAttribute("role") || ""),
    );
    expect(bad.map((node) => node.outerHTML.slice(0, 100))).toEqual([]);
  });
});
