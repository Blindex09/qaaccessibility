/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import axe from "axe-core";

import { ConversationSidebar } from "../ConversationSidebar";
import { LivePreviewModal } from "../LivePreviewModal";

/**
 * Barra lateral e painel de preview: estado só em papéis que o suportam
 * (aria-selected não existe em botão), alternância como botão com aria-pressed
 * (não há painéis nem setas para justificar tablist) e nome visível dentro do
 * nome acessível (WCAG 2.5.3).
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  listConversations: jest.fn(async () => [
    { conversation_id: "a", title: "Auditoria do site", message_count: 4, last_updated: 1 },
    { conversation_id: "b", title: "Outra", message_count: 2, last_updated: 2 },
  ]),
}));

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

function plain(text: string): string {
  return text.replace(/[^\p{L}\p{N} ]/gu, "").replace(/\s+/g, " ").trim().toLowerCase();
}

function labelOffenders(): string[] {
  return Array.from(host.querySelectorAll<HTMLElement>("[aria-label]"))
    .filter((node) => node.matches('[role="button"], button, a[href]'))
    .filter((node) => {
      const visible = plain(node.textContent || "");
      return visible.length > 0 && !plain(node.getAttribute("aria-label") || "").includes(visible);
    })
    .map((node) => `${node.textContent} -> ${node.getAttribute("aria-label")}`);
}

describe("ConversationSidebar", () => {
  async function render() {
    await act(async () => {
      root.render(
        <ConversationSidebar
          currentConversationId="a"
          streaming={false}
          onSelect={() => undefined}
          onNew={() => undefined}
          onManage={() => undefined}
          onOpenSettings={() => undefined}
        />,
      );
    });
  }

  test("conversa atual usa aria-current e não aria-selected em botão", async () => {
    await render();
    expect(host.querySelector('[aria-current="true"]')).not.toBeNull();
    expect(host.querySelectorAll("[aria-selected]")).toHaveLength(0);
  });

  test("nomes visíveis estão dentro dos nomes acessíveis e o axe não aponta nada", async () => {
    await render();
    expect(labelOffenders()).toEqual([]);
    const results = await axe.run(host, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("LivePreviewModal", () => {
  test("o alternador é um grupo de botões com aria-pressed, sem tablist", () => {
    act(() => root.render(<LivePreviewModal sessionId="s1" totalPages={3} />));
    expect(host.querySelector('[role="tablist"], [role="tab"]')).toBeNull();
    const group = host.querySelector('[role="group"][aria-label="Modo de visualização"]');
    const pressed = Array.from(group?.querySelectorAll<HTMLElement>("[aria-pressed]") ?? []);
    expect(pressed.map((n) => n.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
  });

  test("nomes visíveis estão dentro dos nomes acessíveis (2.5.3)", () => {
    act(() => root.render(<LivePreviewModal sessionId="s1" totalPages={3} />));
    expect(labelOffenders()).toEqual([]);
  });
});
