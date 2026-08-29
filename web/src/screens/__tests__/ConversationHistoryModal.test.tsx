/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import type { ConversationSummary } from "../../services/chat";
import { ConversationHistoryModal } from "../ConversationHistoryModal";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

const mockListConversations = jest.fn(async (): Promise<ConversationSummary[]> => []);
const mockDeleteChatHistory = jest.fn(async (_id: string): Promise<void> => {});

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  listConversations: () => mockListConversations(),
  deleteChatHistory: (id: string) => mockDeleteChatHistory(id),
}));

let host: HTMLDivElement;
let root: Root;

function render(props: {
  currentConversationId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
  onCurrentConversationDeleted?: () => void;
}) {
  act(() => {
    root.render(<ConversationHistoryModal {...props} />);
  });
}

function checkboxFor(host: HTMLDivElement, title: string): HTMLElement {
  const row = Array.from(host.querySelectorAll<HTMLElement>('[role="checkbox"]')).find((el) =>
    el.getAttribute("aria-label")?.includes(title),
  );
  if (!row) throw new Error(`checkbox not found for "${title}"`);
  return row;
}

function buttonWithText(host: HTMLDivElement, text: string): HTMLElement {
  const btn = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find((el) =>
    el.textContent?.includes(text),
  );
  if (!btn) throw new Error(`button not found for "${text}"`);
  return btn;
}

beforeEach(() => {
  jest.clearAllMocks();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

describe("ConversationHistoryModal", () => {
  test("mostra estado de carregamento e depois a lista de conversas", async () => {
    mockListConversations.mockResolvedValueOnce([
      { conversation_id: "c1", title: "primeira pergunta", message_count: 3, last_updated: Date.now() / 1000 },
      { conversation_id: "c2", title: "segunda pergunta", message_count: 1, last_updated: Date.now() / 1000 },
    ]);

    render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });
    expect(host.textContent).toContain("Carregando conversas");

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(host.textContent).toContain("primeira pergunta");
    expect(host.textContent).toContain("segunda pergunta");
  });

  test("lista vazia mostra mensagem clara, não uma tela em branco", async () => {
    mockListConversations.mockResolvedValueOnce([]);
    render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });

    await act(async () => {
      await Promise.resolve();
    });

    expect(host.textContent).toContain("Nenhuma conversa anterior");
  });

  test("clicar numa conversa chama onSelect com o id certo e fecha o modal", async () => {
    mockListConversations.mockResolvedValueOnce([
      { conversation_id: "c1", title: "atual", message_count: 2, last_updated: Date.now() / 1000 },
      { conversation_id: "c2", title: "outra conversa", message_count: 5, last_updated: Date.now() / 1000 },
    ]);
    const onSelect = jest.fn();
    const onClose = jest.fn();
    render({ currentConversationId: "c1", onSelect, onClose });

    await act(async () => {
      await Promise.resolve();
    });

    const button = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find((el) =>
      el.textContent?.includes("outra conversa"),
    );
    expect(button).toBeTruthy();
    act(() => {
      button!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onSelect).toHaveBeenCalledWith("c2");
    expect(onClose).toHaveBeenCalled();
  });

  test("botão fechar chama onClose", async () => {
    mockListConversations.mockResolvedValueOnce([]);
    const onClose = jest.fn();
    render({ currentConversationId: "c1", onSelect: jest.fn(), onClose });

    await act(async () => {
      await Promise.resolve();
    });

    const closeBtn = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find((el) =>
      el.textContent?.includes("Fechar"),
    );
    expect(closeBtn).toBeTruthy();
    act(() => {
      closeBtn!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onClose).toHaveBeenCalled();
  });

  test("marca a conversa atual como selecionada", async () => {
    mockListConversations.mockResolvedValueOnce([
      { conversation_id: "c1", title: "atual", message_count: 2, last_updated: Date.now() / 1000 },
    ]);
    render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });

    await act(async () => {
      await Promise.resolve();
    });

    expect(host.textContent).toContain("conversa atual");
  });

  describe("seleção múltipla e exclusão em lote", () => {
    function seed() {
      mockListConversations.mockResolvedValue([
        { conversation_id: "c1", title: "conversa um", message_count: 2, last_updated: Date.now() / 1000 },
        { conversation_id: "c2", title: "conversa dois", message_count: 4, last_updated: Date.now() / 1000 },
        { conversation_id: "c3", title: "conversa tres", message_count: 1, last_updated: Date.now() / 1000 },
      ]);
    }

    test("clicar no checkbox marca a conversa sem trocar de conversa", async () => {
      seed();
      const onSelect = jest.fn();
      render({ currentConversationId: "c1", onSelect, onClose: jest.fn() });
      await act(async () => {
        await Promise.resolve();
      });

      const checkbox = checkboxFor(host, "conversa dois");
      act(() => checkbox.dispatchEvent(new MouseEvent("click", { bubbles: true })));

      expect(checkbox.getAttribute("aria-checked")).toBe("true");
      expect(onSelect).not.toHaveBeenCalled();
    });

    test("tecla Espaço no checkbox focado marca a conversa", async () => {
      seed();
      render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });
      await act(async () => {
        await Promise.resolve();
      });

      const checkbox = checkboxFor(host, "conversa um");
      act(() => {
        checkbox.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
      });

      expect(checkbox.getAttribute("aria-checked")).toBe("true");
    });

    test("Selecionar tudo marca todas, e alterna para Desmarcar tudo", async () => {
      seed();
      render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });
      await act(async () => {
        await Promise.resolve();
      });

      act(() => buttonWithText(host, "Selecionar tudo").dispatchEvent(new MouseEvent("click", { bubbles: true })));

      expect(checkboxFor(host, "conversa um").getAttribute("aria-checked")).toBe("true");
      expect(checkboxFor(host, "conversa dois").getAttribute("aria-checked")).toBe("true");
      expect(checkboxFor(host, "conversa tres").getAttribute("aria-checked")).toBe("true");
      expect(host.textContent).toContain("Desmarcar tudo");

      act(() => buttonWithText(host, "Desmarcar tudo").dispatchEvent(new MouseEvent("click", { bubbles: true })));
      expect(checkboxFor(host, "conversa um").getAttribute("aria-checked")).toBe("false");
    });

    test("botão excluir só aparece com pelo menos uma conversa marcada", async () => {
      seed();
      render({ currentConversationId: "c1", onSelect: jest.fn(), onClose: jest.fn() });
      await act(async () => {
        await Promise.resolve();
      });

      expect(host.textContent).not.toContain("Excluir selecionadas");

      act(() => checkboxFor(host, "conversa um").dispatchEvent(new MouseEvent("click", { bubbles: true })));
      expect(host.textContent).toContain("Excluir selecionadas (1)");
    });

    test("excluir selecionadas apaga cada uma no backend e atualiza a lista", async () => {
      seed();
      render({ currentConversationId: "c3", onSelect: jest.fn(), onClose: jest.fn() });
      await act(async () => {
        await Promise.resolve();
      });

      act(() => checkboxFor(host, "conversa um").dispatchEvent(new MouseEvent("click", { bubbles: true })));
      act(() => checkboxFor(host, "conversa dois").dispatchEvent(new MouseEvent("click", { bubbles: true })));

      mockListConversations.mockResolvedValueOnce([
        { conversation_id: "c3", title: "conversa tres", message_count: 1, last_updated: Date.now() / 1000 },
      ]);

      await act(async () => {
        buttonWithText(host, "Excluir selecionadas").dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockDeleteChatHistory).toHaveBeenCalledWith("c1");
      expect(mockDeleteChatHistory).toHaveBeenCalledWith("c2");
      expect(mockDeleteChatHistory).not.toHaveBeenCalledWith("c3");
      expect(host.textContent).not.toContain("conversa um");
      expect(host.textContent).not.toContain("Excluir selecionadas");
    });

    test("excluir a conversa aberta no momento notifica onCurrentConversationDeleted", async () => {
      seed();
      const onCurrentConversationDeleted = jest.fn();
      render({
        currentConversationId: "c1",
        onSelect: jest.fn(),
        onClose: jest.fn(),
        onCurrentConversationDeleted,
      });
      await act(async () => {
        await Promise.resolve();
      });

      act(() => checkboxFor(host, "conversa um").dispatchEvent(new MouseEvent("click", { bubbles: true })));

      mockListConversations.mockResolvedValueOnce([]);
      await act(async () => {
        buttonWithText(host, "Excluir selecionadas").dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(onCurrentConversationDeleted).toHaveBeenCalled();
    });

    test("excluir uma conversa que NÃO é a atual não dispara onCurrentConversationDeleted", async () => {
      seed();
      const onCurrentConversationDeleted = jest.fn();
      render({
        currentConversationId: "c3",
        onSelect: jest.fn(),
        onClose: jest.fn(),
        onCurrentConversationDeleted,
      });
      await act(async () => {
        await Promise.resolve();
      });

      act(() => checkboxFor(host, "conversa um").dispatchEvent(new MouseEvent("click", { bubbles: true })));

      mockListConversations.mockResolvedValueOnce([
        { conversation_id: "c2", title: "conversa dois", message_count: 4, last_updated: Date.now() / 1000 },
        { conversation_id: "c3", title: "conversa tres", message_count: 1, last_updated: Date.now() / 1000 },
      ]);
      await act(async () => {
        buttonWithText(host, "Excluir selecionadas").dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(onCurrentConversationDeleted).not.toHaveBeenCalled();
    });
  });
});
