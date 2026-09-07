/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent } from "../../services/chat";
import { useChat } from "../useChat";

/**
 * Regressão: "uma auditoria nova começou" é um FATO do backend, não um palpite
 * sobre a frase do usuário.
 *
 * A versão anterior decidia isso na ChatScreen com
 * `/https?:\/\/|\b(analise|audite|auditoria|verifique|examinar|scan)\b/i` sobre
 * a última mensagem do usuário, e errava dos dois lados: não reconhecia "roda o
 * axe nesse site" (nem nada em inglês), e disparava a limpeza do painel num
 * acompanhamento sobre a MESMA auditoria ("verifique se o botão ficou certo").
 * Agora o sinal é o evento `tool_start` das ferramentas de análise.
 */

let emit: (event: ChatEvent) => void;
let mounted: TestRenderer.ReactTestRenderer[] = [];

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
      new Promise<void>(() => {
        emit = onEvent;
      }),
  ),
}));

type Chat = ReturnType<typeof useChat>;

function Probe({ out }: { out: { chat?: Chat } }) {
  out.chat = useChat();
  return null;
}

function mountChat(): () => Chat {
  const out: { chat?: Chat } = {};
  act(() => {
    mounted.push(TestRenderer.create(<Probe out={out} />));
  });
  return () => {
    if (!out.chat) throw new Error("hook não montou");
    return out.chat;
  };
}

function toolStart(name: string): ChatEvent {
  return { type: "tool_start", tool_call_id: `t-${name}`, name, arguments: {} } as ChatEvent;
}

/** Inicia um turno e dispara as ferramentas; encerra com stop() para liberar o
 * timer de duracao do turno (o mock de streamChat nunca resolve sozinho). */
function turno(chat: () => Chat, texto: string, ferramentas: string[]): void {
  act(() => {
    void chat().send(texto);
  });
  for (const nome of ferramentas) {
    act(() => emit(toolStart(nome)));
  }
  act(() => chat().stop());
}

afterEach(async () => {
  await act(async () => {
    await Promise.resolve();
  });
  act(() => {
    for (const renderer of mounted.splice(0)) renderer.unmount();
  });
  jest.clearAllMocks();
});

describe("useChat — auditRunCount", () => {
  test("começa em zero", () => {
    expect(mountChat()().auditRunCount).toBe(0);
  });

  test("frase sem palavra-chave ainda conta como auditoria", () => {
    const chat = mountChat();
    turno(chat, "roda o axe nesse site", ["analyze_page"]);
    expect(chat().auditRunCount).toBe(1);
  });

  test("acompanhamento sobre a mesma auditoria não conta de novo", () => {
    const chat = mountChat();
    turno(chat, "audita https://exemplo.com", ["analyze_page"]);
    expect(chat().auditRunCount).toBe(1);

    // "verifique" casava com a regex antiga e limpava o painel indevidamente
    turno(chat, "verifique se o botão ficou certo", ["export_xlsx"]);
    expect(chat().auditRunCount).toBe(1);
  });

  test("cada ferramenta de análise incrementa uma vez", () => {
    const chat = mountChat();
    turno(chat, "vai", ["analyze_page", "analyze_site", "analyze_document"]);
    expect(chat().auditRunCount).toBe(3);
  });

  test("ferramenta que não é de análise não incrementa", () => {
    const chat = mountChat();
    turno(chat, "vai", ["generate_vpat", "fix_and_zip_files"]);
    expect(chat().auditRunCount).toBe(0);
  });
});
