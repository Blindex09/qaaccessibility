/* eslint-env jest, node */

import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import type { ChatEvent } from "../../services/chat";
import {
  ANSWER_ERROR_ANNOUNCEMENT,
  TYPING_ANNOUNCEMENT,
  clarifyAnnouncement,
  useChat,
} from "../useChat";

/**
 * O maior buraco da auditoria: a resposta do assistente chegava em silêncio.
 * O balão cresce token a token e NÃO pode ser live region — dispararia a cada
 * delta e a resposta seria impossível de ouvir —, portanto quem usa leitor de
 * tela ouvia "Pensando...", depois nada, e tinha de voltar à conversa à mão
 * para descobrir que a resposta tinha chegado.
 *
 * Este teste não lê o código-fonte: corre o hook a sério, injeta os eventos do
 * stream tal como o backend os manda, e observa o estado que alimenta a live
 * region. Fixa as duas metades do contrato — anuncia no fim, e NÃO anuncia a
 * cada token.
 *
 * `react-test-renderer` vem com o `jest-expo` (devDependency) e corre sem DOM,
 * que é o ambiente `node` configurado para o jest deste projeto.
 */

let emit: (event: ChatEvent) => void;
let resolveStream: () => void;

jest.mock("../../services/chat", () => ({
  __esModule: true,
  BASE_URL: "http://localhost:8001",
  sendClarify: jest.fn(async () => true),
  sendCancel: jest.fn(async () => true),
  fetchChatHistory: jest.fn(async () => []),
  deleteChatHistory: jest.fn(async () => undefined),
  listConversations: jest.fn(async () => []),
  streamChat: jest.fn(
    (
      _text: string,
      _history: unknown,
      onEvent: (event: ChatEvent) => void,
    ) =>
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
    TestRenderer.create(<Probe out={out} />);
  });
  return {
    chat: () => {
      if (!out.chat) throw new Error("hook não montou");
      return out.chat;
    },
  };
}

/** Começa um turno e devolve o `emit` ligado a esse stream. */
function startTurn(chat: () => Chat): void {
  act(() => {
    void chat().send("analisa esta página");
  });
}

/** A live region só é escrita depois do passo de limpeza (temporizador). */
function flushAnnounce(): void {
  act(() => {
    jest.runOnlyPendingTimers();
  });
}

function send(event: ChatEvent): void {
  act(() => emit(event));
}

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
});

const APPROVAL_QUESTION =
  "A ferramenta 'fix_and_zip_files' realizará uma ação com efeito externo ou gravará um artefato. " +
  `Argumentos: {"path": "site.zip"}. Identificador da ação: ${"a".repeat(64)}. ` +
  "Aprovar exatamente esta ação?";

describe("useChat — anúncio da resposta na live region", () => {
  test("anuncia somente Digitando enquanto os tokens vão chegando", () => {
    const { chat } = mountChat();
    startTurn(chat);

    send({ type: "token", text: "Encontrei " });
    flushAnnounce();
    expect(chat().announcement).toBe(TYPING_ANNOUNCEMENT);

    send({ type: "token", text: "3 problemas" });
    send({ type: "token", text: " de contraste." });
    flushAnnounce();
    expect(chat().announcement).toBe(TYPING_ANNOUNCEMENT);

    // O texto chegou mesmo ao balão — o silêncio acima é da live region, não
    // do stream.
    expect(chat().messages.at(-1)?.content).toBe("Encontrei 3 problemas de contraste.");
  });

  test("progresso de ferramentas também não escreve na live region de anúncios", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "phase", text: "Analisando..." });
    send({ type: "tool_start", name: "analyze_page" });
    send({ type: "tool_result", name: "analyze_page" });
    flushAnnounce();
    expect(chat().announcement).toBe(TYPING_ANNOUNCEMENT);
    // O progresso continua escrito em `activity`, mas fora da região viva.
    expect(chat().activity).not.toBe("");
  });

  test("anuncia uma única vez quando o stream termina", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "token", text: "Pronto." });
    flushAnnounce();
    expect(chat().announcement).toBe(TYPING_ANNOUNCEMENT);

    send({ type: "done", final: "Pronto." });
    flushAnnounce();
    expect(chat().announcement).toBe("Pronto.");
  });

  test("o anúncio sobrevive ao fim do turno em vez de ser apagado com o resto", async () => {
    // Regressão exata do bug anterior: a conclusão era escrita em `activity`,
    // que o `finally` do turno limpa logo a seguir — na prática nunca era
    // falada.
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "done", final: "Pronto." });

    await act(async () => {
      resolveStream();
      await Promise.resolve();
    });
    flushAnnounce();

    expect(chat().streaming).toBe(false);
    expect(chat().activity).toBe("");
    expect(chat().announcement).toBe("Pronto.");
  });

  test("o anúncio é limpo antes de ser reescrito, para falar em todos os turnos", () => {
    // Uma live region só fala quando o texto MUDA. Sem o passo de limpeza, o
    // segundo turno escreveria a mesma frase e ficaria mudo.
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "done", final: "Primeira." });
    flushAnnounce();
    expect(chat().announcement).toBe("Primeira.");

    send({ type: "done", final: "Segunda." });
    expect(chat().announcement).toBe("");
    flushAnnounce();
    expect(chat().announcement).toBe("Segunda.");
  });

  test("uma falha também é anunciada, e não só escrita no balão", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "error", error: "timeout" });
    flushAnnounce();
    expect(chat().announcement).toBe(ANSWER_ERROR_ANNOUNCEMENT);
  });

  test("agrupa ferramentas equivalentes durante o turno inteiro", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "tool_start", name: "web_search" });
    send({ type: "phase", text: "Verificando resultados..." });
    send({ type: "tool_result", name: "web_search" });
    send({ type: "tool_start", name: "web_extract" });
    send({ type: "tool_result", name: "web_extract" });
    const webActivities = chat().messages.filter((message) => message.groupKey === "web_research");
    expect(webActivities).toHaveLength(1);
    expect(webActivities[0].content).toBe("Executou pesquisa web.");
  });

  test("mídia mostra só o estado inicial e depois o resultado direto", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "tool_start", name: "transcribe_audio" });
    expect(chat().messages.some((message) => message.content === "Transcrevendo áudio...")).toBe(true);
    send({ type: "tool_result", name: "transcribe_audio" });
    expect(chat().messages.some((message) => message.groupKey === "tool:transcribe_audio")).toBe(false);
  });

  test("tool_progress acumula logs no card da ferramenta", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "tool_start", name: "analyze_page" });
    send({ type: "tool_progress", name: "analyze_page", message: "Obtendo conteúdo da página..." });
    send({ type: "tool_progress", name: "analyze_page", message: "Executando especialistas..." });
    const toolMessages = chat().messages.filter((message) => message.groupKey === "tool:analyze_page");
    expect(toolMessages).toHaveLength(1);
    expect(toolMessages[0].toolCall?.logs).toEqual([
      "Obtendo conteúdo da página...",
      "Executando especialistas...",
    ]);
  });

  test("tool_progress sem tool_start anterior cria card provisório", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "tool_progress", name: "analyze_page", message: "Mensagem órfã" });
    const toolMessages = chat().messages.filter((message) => message.groupKey === "tool:analyze_page");
    expect(toolMessages).toHaveLength(1);
    expect(toolMessages[0].toolCall?.logs).toEqual(["Mensagem órfã"]);
  });
});

describe("useChat — anúncio quando a vez passa para o usuário", () => {
  test("um plano anuncia quantos passos tem", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({
      type: "clarify",
      request_id: "r1",
      question: "Plano:\n1. Rastrear o site\n2. Analisar contraste",
      choices: [],
    });
    flushAnnounce();
    expect(chat().announcement).toBe(
      "O assistente propôs um plano com 2 passos. Responda no painel abaixo.",
    );
  });

  test("uma pergunta aberta anuncia que a vez é do usuário", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "clarify", request_id: "r2", question: "Qual URL devo testar?", choices: [] });
    flushAnnounce();
    expect(chat().announcement).toBe(
      "O assistente fez uma pergunta. Responda no painel abaixo.",
    );
  });

  test("o pedido de aprovação NÃO usa a live region: é diálogo modal e o foco move-se", () => {
    const { chat } = mountChat();
    startTurn(chat);
    send({ type: "clarify", request_id: "r3", question: APPROVAL_QUESTION, choices: ["Sim", "Não"] });
    flushAnnounce();
    // Anunciar aqui faria o leitor de tela dizer o mesmo duas vezes: uma pela
    // região, outra quando o foco entra no diálogo.
    expect(chat().announcement).toBe("");
    expect(chat().pendingClarify?.requestId).toBe("r3");
  });
});

describe("clarifyAnnouncement", () => {
  test("concorda com a forma que o painel vai desenhar", () => {
    expect(clarifyAnnouncement(APPROVAL_QUESTION)).toBe("");
    expect(clarifyAnnouncement("1. um passo\n2. outro passo")).toBe(
      "O assistente propôs um plano com 2 passos. Responda no painel abaixo.",
    );
    // Um só item não é plano para o `parseClarify`, logo cai em pergunta.
    expect(clarifyAnnouncement("1. um passo")).toMatch(/^O assistente fez uma pergunta\./);
    expect(clarifyAnnouncement("Posso continuar?")).toMatch(/^O assistente fez uma pergunta\./);
  });
});
