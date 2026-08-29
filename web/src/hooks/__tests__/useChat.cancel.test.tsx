/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent } from "../../services/chat";
import { useChat } from "../useChat";

/**
 * Interruptibilidade: o backend entrega o evento `stream_id` no início de
 * cada turno (ver chat_runtime.py::stream_chat) para que `stop()` possa pedir
 * um cancelamento explícito via POST /chat/cancel, além do abort() da conexão
 * que já parava a UI. Este teste corre o hook a sério e verifica as duas
 * metades do contrato: (1) o id do evento é guardado, (2) `stop()` chama
 * sendCancel com ele -- sem bloquear o abort(), que continua imediato.
 */

let emit: (event: ChatEvent) => void;
let resolveStream: () => void;

const mockSendCancel = jest.fn(async (_streamId: string) => true);
const mockAbort = jest.fn();

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  sendClarify: jest.fn(async () => true),
  sendCancel: (streamId: string) => mockSendCancel(streamId),
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
    TestRenderer.create(<Probe out={out} />);
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

afterEach(() => {
  jest.clearAllMocks();
});

describe("useChat — interromper um turno em andamento", () => {
  test("stop() aborta a conexão mesmo sem stream_id ainda recebido", () => {
    const { chat } = mountChat();
    startTurn(chat);

    act(() => chat().stop());

    expect(mockAbort).toHaveBeenCalledTimes(1);
    expect(mockSendCancel).not.toHaveBeenCalled();
    expect(chat().streaming).toBe(false);
  });

  test("stop() pede cancelamento explícito com o stream_id do turno atual", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "abc123" });

    act(() => chat().stop());

    expect(mockAbort).toHaveBeenCalledTimes(1);
    expect(mockSendCancel).toHaveBeenCalledWith("abc123");
  });

  test("um novo turno esquece o stream_id do turno anterior", async () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "turno-1" });
    send({ type: "done", final: "Pronto." });
    await act(async () => {
      resolveStream();
      await Promise.resolve();
    });

    startTurn(chat); // 2º turno, ainda sem receber o novo stream_id

    act(() => chat().stop());
    expect(mockSendCancel).not.toHaveBeenCalledWith("turno-1");
  });

  test("evento 'cancelled' vindo do servidor limpa a atividade sem lançar erro", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "stream_id", id: "abc123" });
    send({ type: "cancelled" });

    expect(chat().activity).toBe("");
  });
});
