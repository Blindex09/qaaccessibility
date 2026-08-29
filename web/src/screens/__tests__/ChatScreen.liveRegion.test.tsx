/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import type { ChatEvent } from "../../services/chat";
import { ChatScreen } from "../ChatScreen";

/**
 * Teste comportamental das live regions do chat, no DOM a sério.
 *
 * Dois defeitos ficam fixados aqui:
 *
 * Há uma única região persistente para "Digitando..." e a resposta final.
 * Progresso das ferramentas e o balão token a token não são regiões vivas.
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

let emit: (event: ChatEvent) => void;

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
        void resolve;
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

function liveRegions(): HTMLElement[] {
  return Array.from(host.querySelectorAll<HTMLElement>("[aria-live]"));
}

/** Escreve no campo e envia, como faria o usuário. */
function sendMessage(text: string): void {
  const field = host.querySelector<HTMLTextAreaElement>("textarea");
  if (!field) throw new Error("campo de mensagem não encontrado");
  const setValue = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    "value",
  )?.set;
  act(() => {
    setValue?.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const sendButton = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find(
    (node) => node.getAttribute("aria-label") === "Enviar mensagem",
  );
  if (!sendButton) throw new Error("botão de enviar não encontrado");
  act(() => {
    sendButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

describe("ChatScreen — live regions persistentes", () => {
  test("as regiões já existem num tela vazio, antes de haver o que anunciar", () => {
    const regions = liveRegions();
    expect(regions).toHaveLength(1);
    for (const region of regions) {
      expect(region.getAttribute("aria-live")).toBe("polite");
      expect(region.hasAttribute("aria-label")).toBe(false);
      // Montadas vazias: é a mudança de texto que dispara o anúncio.
      expect(region.textContent).toBe("");
    }
  });

  test("as regiões estão no DOM mesmo sem mensagem nenhuma na conversa", () => {
    expect(host.textContent).toContain("Nenhuma conversa iniciada");
    expect(liveRegions().length).toBeGreaterThan(0);
  });

  test("Ctrl+Alt+I leva o foco ao campo de mensagem", () => {
    const field = host.querySelector<HTMLTextAreaElement>("textarea");
    const button = host.querySelector<HTMLButtonElement>('[aria-label="Anexar arquivos ou projeto para análise"]');
    if (!field || !button) throw new Error("controles do chat não encontrados");

    button.focus();
    expect(document.activeElement).toBe(button);
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", {
        key: "i",
        ctrlKey: true,
        altKey: true,
        bubbles: true,
      }));
    });
    expect(document.activeElement).toBe(field);
  });

  test("estando vazias ficam fora do fluxo — não abrem espaço morto na conversa", () => {
    // Manter a região montada não pode custar um buraco no fim do histórico.
    for (const region of liveRegions()) {
      expect(window.getComputedStyle(region).position).toBe("absolute");
    }
  });

  test("nenhuma live region é `assertive`: nada aqui interrompe a leitura", () => {
    for (const region of liveRegions()) {
      expect(region.getAttribute("aria-live")).not.toBe("assertive");
    }
  });

  test("são os MESMOS nós depois de a conversa encher — não são remontadas", () => {
    // A propriedade que interessa não é "existem", é "persistem": um leitor de
    // tela perde de vista uma região que é desmontada e reinserida.
    const before = liveRegions();
    expect(before).toHaveLength(1);

    sendMessage("analisa https://exemplo.pt");
    act(() => emit({ type: "tool_start", name: "analyze_page" }));
    act(() => emit({ type: "token", text: "Encontrei 3 problemas." }));

    expect(host.textContent).toContain("Encontrei 3 problemas.");
    const after = liveRegions();
    expect(after).toHaveLength(1);
    // Identidade de nó preservada apesar de todo o conteúdo ao redor ter mudado.
    expect(after[0]).toBe(before[0]);
  });

  test("o balão da resposta NÃO é live region — dispararia a cada token", () => {
    sendMessage("analisa https://exemplo.pt");
    act(() => emit({ type: "token", text: "Encontrei 3 problemas." }));

    // O renderer de markdown-lite do balão usa <p> para parágrafos de texto
    // simples (mais semântico que <div>) -- consulta qualquer elemento, não só div.
    const bubble = Array.from(host.querySelectorAll<HTMLElement>("div, p")).find(
      (node) =>
        node.textContent === "Encontrei 3 problemas." && !node.hasAttribute("aria-live"),
    );
    expect(bubble).toBeTruthy();
    // O texto da resposta não vive dentro de nenhuma live region.
    for (const region of liveRegions()) {
      expect(region.textContent).not.toContain("Encontrei 3 problemas.");
    }
  });

  test("marcador [LIVE_PREVIEW:] abre o painel persistente sem expor botão", () => {
    sendMessage("corrija e abra o preview");
    act(() =>
      emit({
        type: "done",
        final: "Pronto. [LIVE_PREVIEW:abc123:1]",
      }),
    );

    // O marcador de wiring não deve aparecer como texto cru.
    expect(host.textContent).not.toContain("[LIVE_PREVIEW:abc123:1]");

    // A correção abre o painel automaticamente e não cria botão de abertura.
    expect(host.textContent).toContain("Live Preview Acessível");
    expect(host.querySelector('[aria-label="Abrir painel Live Preview do site corrigido"]')).toBeNull();
  });
});
