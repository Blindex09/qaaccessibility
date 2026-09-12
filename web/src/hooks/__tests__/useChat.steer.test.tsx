/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent } from "../../services/chat";
import { useChat } from "../useChat";

/**
 * Redirecionar um turno em andamento sem perder o progresso já feito
 * (CLAUDE.md, "agente = modelo + harness" -> comportamento conversacional
 * obrigatório): diferente de `stop()`, `steer()` não aborta a conexão -- só
 * entrega uma correção via POST /chat/steer para o backend injetar no próximo
 * ponto de checagem do agente.
 */

let emit: (event: ChatEvent) => void;
let resolveStream: () => void;
const mounted: TestRenderer.ReactTestRenderer[] = [];

const mockSendSteer = jest.fn(async (_streamId: string, _message: string) => true);
const mockAbort = jest.fn();

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  sendClarify: jest.fn(async () => true),
  sendCancel: jest.fn(async () => true),
  sendSteer: (streamId: string, message: string) => mockSendSteer(streamId, message),
  fetchChatHistory: jest.fn(async () => []),
  deleteChatHistory: jest.fn(async () => undefined),
  listConversations: jest.fn(async () => []),
  streamChat: jest.fn(
    (
      _text: string,
      _history: unknown,
      onEvent: (event: ChatEvent) => void,
      opts: { signal?: AbortSignal },
    ) =>
      new Promise<void>((resolve) => {
        emit = onEvent;
        resolveStream = resolve;
        opts.signal?.addEventListener("abort", mockAbort);
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

function startTurn(chat: () => Chat): void {
  act(() => {
    void chat().send("audita esta página");
  });
}

function send(event: ChatEvent): void {
  act(() => emit(event));
}

afterEach(async () => {
  await act(async () => {
    mounted.splice(0).forEach((root) => root.unmount());
    resolveStream?.();
    await Promise.resolve();
  });
  jest.clearAllMocks();
});

describe("useChat — redirecionar um turno em andamento", () => {
  test("steer() sem stream_id ainda recebido não chama o backend e não aborta", async () => {
    const { chat } = mountChat();
    startTurn(chat);

    let delivered: boolean | undefined;
    await act(async () => {
      delivered = await chat().steer("checa só o contraste");
    });

    expect(delivered).toBe(false);
    expect(mockSendSteer).not.toHaveBeenCalled();
    expect(mockAbort).not.toHaveBeenCalled();
    // Turno continua rodando -- diferente de stop(), steer() nunca cancela.
    expect(chat().streaming).toBe(true);
  });

  test("steer() envia a correção com o stream_id do turno atual, sem abortar", async () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "abc123" });

    let delivered: boolean | undefined;
    await act(async () => {
      delivered = await chat().steer("na verdade, olhe só os formulários");
    });

    expect(delivered).toBe(true);
    expect(mockSendSteer).toHaveBeenCalledWith("abc123", "na verdade, olhe só os formulários");
    expect(mockAbort).not.toHaveBeenCalled();
    expect(chat().streaming).toBe(true);
  });

  test("steer() com correção vazia é um no-op", async () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "abc123" });

    let delivered: boolean | undefined;
    await act(async () => {
      delivered = await chat().steer("   ");
    });

    expect(delivered).toBe(false);
    expect(mockSendSteer).not.toHaveBeenCalled();
  });

  test("correção entregue é registrada no histórico visível", async () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "abc123" });

    await act(async () => {
      await chat().steer("checa só o contraste");
    });

    const registrada = chat().messages.some(
      (m) => m.role === "status" && m.content.includes("checa só o contraste"),
    );
    expect(registrada).toBe(true);
  });
});
