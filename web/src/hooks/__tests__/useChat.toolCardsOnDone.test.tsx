/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent } from "../../services/chat";
import { useChat } from "../useChat";

/**
 * Regressão (e2e real 2026-10-07): a pesquisa profunda abre cartões de busca internos (Tavily, Exa) que
 * nunca recebem o "terminou". Ao fim do turno o cliente marcava todo cartão "em execução" como
 * "cancelado" e a tela dizia "Execução interrompida" em um turno que terminou bem, o que engana quem
 * usa leitor de tela. Só cancelamento de verdade (botão Parar ou evento cancelled) interrompe cartões.
 */

let emit: (event: ChatEvent) => void;
let resolveStream: () => void;
const mounted: TestRenderer.ReactTestRenderer[] = [];

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
        resolveStream = resolve;
      }),
  ),
}));

type Chat = ReturnType<typeof useChat>;

function Probe({ out }: { out: { chat?: Chat } }) {
  out.chat = useChat();
  return null;
}

function mountChat(): { chat: () => Chat } {
  const out: { chat?: Chat } = {};
  act(() => {
    mounted.push(TestRenderer.create(<Probe out={out} />));
  });
  return {
    chat: () => {
      if (!out.chat) throw new Error("hook não montou");
      return out.chat;
    },
  };
}

function send(event: ChatEvent): void {
  act(() => emit(event));
}

function toolCards(chat: Chat) {
  return chat.messages.filter((message) => message.toolCall).map((message) => message.toolCall!);
}

afterEach(async () => {
  await act(async () => {
    mounted.splice(0).forEach((root) => root.unmount());
  });
});

async function finishStream(): Promise<void> {
  await act(async () => {
    resolveStream();
  });
}

test("um cartão de busca que ficou em execução termina como concluído quando o turno termina bem", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("pesquise a norma");
  });
  send({ type: "tool_start", name: "tavily_search", tool_call_id: "internal-1", arguments: {} } as ChatEvent);
  expect(toolCards(chat())[0].status).toBe("running");

  send({ type: "done", final: "Aqui está a pesquisa." } as ChatEvent);
  await finishStream();

  const cards = toolCards(chat());
  expect(cards).toHaveLength(1);
  expect(cards[0].status).toBe("complete");
  expect(JSON.stringify(chat().messages)).not.toContain("Execução interrompida");
});

test("cancelamento de verdade continua marcando o cartão como interrompido", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("pesquise a norma");
  });
  send({ type: "tool_start", name: "tavily_search", tool_call_id: "internal-2", arguments: {} } as ChatEvent);
  send({ type: "cancelled" } as ChatEvent);
  await finishStream();

  expect(toolCards(chat())[0].status).toBe("cancelled");
});

test("erro do turno não finge que o cartão terminou bem", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("pesquise a norma");
  });
  send({ type: "tool_start", name: "tavily_search", tool_call_id: "internal-3", arguments: {} } as ChatEvent);
  send({ type: "error", error: "falha do provedor" } as ChatEvent);
  await finishStream();

  expect(toolCards(chat())[0].status).not.toBe("complete");
});

test("fim parcial (o servidor marca partial) deixa o cartão como interrompido, não como concluído", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("pesquise a norma");
  });
  send({ type: "tool_start", name: "tavily_search", tool_call_id: "internal-4", arguments: {} } as ChatEvent);
  send({ type: "done", final: "Cortado pelo limite.", partial: true } as ChatEvent);
  await finishStream();

  expect(toolCards(chat())[0].status).toBe("cancelled");
});

test("a espera do provedor aparece como uma linha que se atualiza no lugar", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("o que é 1.4.3?");
  });
  send({ type: "waiting_provider", seconds: 15 } as ChatEvent);
  send({ type: "waiting_provider", seconds: 30 } as ChatEvent);

  const waits = chat().messages.filter((message) => message.kind === "wait");
  expect(waits).toHaveLength(1);
  expect(waits[0].content).toBe("Aguardando o provedor há 30s.");
});

test("o aviso de espera atualiza no lugar e some quando chega o próximo evento", async () => {
  const { chat } = mountChat();
  act(() => {
    void chat().send("audite a página");
  });
  send({ type: "analysis_waiting", agents: ["robustness"], seconds: 20 } as ChatEvent);
  send({ type: "analysis_waiting", agents: ["robustness"], seconds: 40 } as ChatEvent);

  const waits = () => chat().messages.filter((message) => message.kind === "wait");
  expect(waits()).toHaveLength(1);
  expect(waits()[0].content).toBe("Ainda aguardando Estrutura e Tags ARIA há 40s.");

  send({ type: "analysis_partial", agent: "robustness", completed: 9, total: 9 } as ChatEvent);
  expect(waits()).toHaveLength(0);
});
