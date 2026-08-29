/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent, ConversationSummary, StoredChatMessage } from "../../services/chat";
import { useChat } from "../useChat";

/**
 * Histórico de sessão persistido: antes desta feature, o `conversation_id`
 * era gerado de novo a cada montagem do hook (recarregar a página = conversa
 * nova, sem jeito de voltar). Agora persiste em localStorage (ambiente de
 * teste é `testEnvironment: "node"`, sem localStorage nativo -- por isso o
 * hook usa `typeof localStorage !== "undefined"` defensivamente, e este
 * arquivo instala um mock em memória para exercitar o caminho real).
 */

function installLocalStorageMock(): Storage {
  const store = new Map<string, string>();
  const mock: Storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, "localStorage", { value: mock, configurable: true, writable: true });
  return mock;
}

const mockFetchChatHistory = jest.fn(async (_id: string): Promise<StoredChatMessage[]> => []);
const mockDeleteChatHistory = jest.fn(async (_id: string): Promise<void> => {});
const mockListConversations = jest.fn(async (_limit?: number): Promise<ConversationSummary[]> => []);

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  sendClarify: jest.fn(async () => true),
  sendCancel: jest.fn(async () => true),
  fetchChatHistory: (id: string) => mockFetchChatHistory(id),
  deleteChatHistory: (id: string) => mockDeleteChatHistory(id),
  listConversations: (limit?: number) => mockListConversations(limit),
  streamChat: jest.fn(
    (_text: string, _history: unknown, _onEvent: (event: ChatEvent) => void, _opts: unknown) =>
      new Promise<void>(() => {
        /* nunca resolve -- estes testes não precisam completar um turno */
      }),
  ),
}));

type Chat = ReturnType<typeof useChat>;

function Probe({ out }: { out: { chat?: Chat } }) {
  out.chat = useChat();
  return null;
}

async function mountChat(): Promise<{ chat: () => Chat }> {
  const out: { chat?: Chat } = {};
  await act(async () => {
    TestRenderer.create(<Probe out={out} />);
    await Promise.resolve();
  });
  return {
    chat: () => {
      if (!out.chat) throw new Error("hook não montou");
      return out.chat;
    },
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  installLocalStorageMock();
});

describe("useChat — histórico de sessão persistido", () => {
  test("gera um conversation_id e persiste em localStorage", async () => {
    const { chat } = await mountChat();
    const id = chat().conversationId;
    expect(id).toBeTruthy();
    expect(localStorage.getItem("qa_a11y_conversation_id")).toBe(id);
  });

  test("uma segunda montagem reaproveita o mesmo conversation_id (simula reload)", async () => {
    const { chat: chat1 } = await mountChat();
    const idAfterFirstMount = chat1().conversationId;

    const { chat: chat2 } = await mountChat();
    expect(chat2().conversationId).toBe(idAfterFirstMount);
  });

  test("busca o histórico persistido no backend ao montar", async () => {
    const { chat } = await mountChat();
    expect(mockFetchChatHistory).toHaveBeenCalledWith(chat().conversationId);
  });

  test("hidrata as mensagens com o histórico devolvido pelo backend", async () => {
    mockFetchChatHistory.mockResolvedValueOnce([
      { role: "user", content: "oi", timestamp: 1 },
      { role: "assistant", content: "olá! como posso ajudar?", timestamp: 2 },
    ]);

    const { chat } = await mountChat();

    expect(chat().historyLoaded).toBe(true);
    expect(chat().messages).toEqual([
      { role: "user", content: "oi", rawContent: "oi" },
      { role: "assistant", content: "olá! como posso ajudar?", rawContent: "olá! como posso ajudar?" },
    ]);
  });

  test("sem histórico prévio, começa com a tela vazia normal (sem erro)", async () => {
    const { chat } = await mountChat();
    expect(chat().historyLoaded).toBe(true);
    expect(chat().messages).toEqual([]);
  });

  test("startNewConversation troca o id, persiste o novo e limpa as mensagens", async () => {
    mockFetchChatHistory.mockResolvedValueOnce([{ role: "user", content: "conversa antiga", timestamp: 1 }]);
    const { chat } = await mountChat();
    const oldId = chat().conversationId;
    await act(async () => {
      await Promise.resolve();
    });
    expect(chat().messages.length).toBe(1);

    await act(async () => {
      chat().startNewConversation();
      await Promise.resolve();
    });

    expect(chat().conversationId).not.toBe(oldId);
    expect(chat().messages).toEqual([]);
    expect(localStorage.getItem("qa_a11y_conversation_id")).toBe(chat().conversationId);
  });

  test("forgetConversation apaga a conversa no backend e começa uma nova", async () => {
    const { chat } = await mountChat();
    const oldId = chat().conversationId;

    await act(async () => {
      await chat().forgetConversation();
    });

    expect(mockDeleteChatHistory).toHaveBeenCalledWith(oldId);
    expect(chat().conversationId).not.toBe(oldId);
    expect(chat().messages).toEqual([]);
  });

  test("switchConversation troca para uma conversa existente e carrega o histórico dela", async () => {
    const { chat } = await mountChat();
    const originalId = chat().conversationId;

    mockFetchChatHistory.mockResolvedValueOnce([
      { role: "user", content: "mensagem da outra conversa", timestamp: 1 },
    ]);

    await act(async () => {
      chat().switchConversation("conversa-existente-xyz");
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(chat().conversationId).toBe("conversa-existente-xyz");
    expect(chat().conversationId).not.toBe(originalId);
    expect(mockFetchChatHistory).toHaveBeenCalledWith("conversa-existente-xyz");
    expect(chat().messages).toEqual([
      { role: "user", content: "mensagem da outra conversa", rawContent: "mensagem da outra conversa" },
    ]);
    expect(localStorage.getItem("qa_a11y_conversation_id")).toBe("conversa-existente-xyz");
  });

  test("switchConversation para o mesmo id corrente não faz nada", async () => {
    const { chat } = await mountChat();
    const id = chat().conversationId;
    mockFetchChatHistory.mockClear();

    await act(async () => {
      chat().switchConversation(id);
      await Promise.resolve();
    });

    expect(mockFetchChatHistory).not.toHaveBeenCalled();
  });
});
