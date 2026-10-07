/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import type { ChatEvent } from "../../services/chat";
import { fetchChatHistory } from "../../services/chat";
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
  test("enviar vazio mantem nome curto e estado indisponivel", () => {
    const button = host.querySelector('[aria-label="Enviar mensagem"]');
    expect(button).not.toBeNull();
    expect(button?.getAttribute("aria-disabled")).toBe("true");
    expect(host.innerHTML).not.toContain("digite uma mensagem ou anexe um arquivo primeiro");
  });
  test("histórico sem duração não mostra mensagem fixa nem tempo inventado", async () => {
    act(() => root.unmount());
    jest.mocked(fetchChatHistory).mockResolvedValueOnce([
      { role: "user", content: "Olá", timestamp: 1 },
      { role: "assistant", content: "Resposta restaurada.", timestamp: 2 },
    ]);
    root = createRoot(host);
    await act(async () => { root.render(<ChatScreen />); });
    expect(host.textContent).toContain("Resposta restaurada.");
    expect(host.textContent).not.toContain("Processamento concluído");
    expect(host.textContent).not.toContain("Processou em");
    expect(host.querySelector('[role="timer"]')).toBeNull();
  });

  test("mantém o timer em andamento e a duração real após concluir o turno", async () => {
    sendMessage("Olá");
    expect(host.querySelector('[role="timer"]')?.textContent).toContain("Processando há");
    await act(async () => {
      emit({ type: "done", final: "Resposta nova." });
      finishStream();
    });
    expect(host.textContent).toContain("Resposta nova.");
    expect(host.textContent).toContain("Processou em");
    expect(host.textContent).not.toContain("Processamento concluído");
    expect(host.querySelector('[role="timer"]')).toBeNull();
  });

  test("identifica a resposta com o cabeçalho qaaccessibility", () => {
    sendMessage("olá");
    act(() => emit({ type: "token", text: "Olá!" }));
    const heading = Array.from(host.querySelectorAll("h2")).find(
      (node) => node.textContent === "qaaccessibility",
    );
    expect(heading).toBeDefined();
    expect(heading?.style.textTransform).not.toBe("uppercase");
    expect(host.textContent).not.toContain("IA ASSISTENTE");
  });

  test.each([
    "Avalie a acessibilidade de https://example.com/ — somente a página inicial.",
    "Avalie a acessibilidade de [exemplo](https://example.com/) — somente a página inicial.",
    "Avalie a acessibilidade de https://example.com/ e compare com https://example.org/.",
  ])("texto antes de links é exibido uma vez: %s", (text) => {
    sendMessage(text);
    const userBubble = host.querySelector('[aria-label^="Mensagem de Você:"]');
    expect(userBubble?.textContent?.split("Avalie a acessibilidade de")).toHaveLength(2);
    expect(userBubble?.querySelectorAll("a").length).toBe(text.includes("compare") ? 2 : 1);
  });

  test("atividade já no feed é exibida uma vez, inclusive quando a fase é retransmitida", () => {
    sendMessage("audite este site");
    const update = "Vou iniciar a inspeção da página inicial, sem alterar nada.";
    act(() => emit({ type: "phase", text: update }));
    expect(host.textContent?.split(update)).toHaveLength(2);
    act(() => emit({ type: "phase", text: "Já recebi o documento da página." }));
    act(() => emit({ type: "phase", text: update }));
    expect(host.textContent?.split(update)).toHaveLength(2);
    expect(host.textContent).toContain("Já recebi o documento da página.");
    const item = host.querySelector('[role="listitem"][aria-label="' + update + '"]');
    expect(item?.getAttribute("tabindex")).toBe("0");
    expect(item?.closest("[aria-live]")).toBeNull();
  });

  test("atividade sem entrada no feed continua disponível", () => {
    sendMessage("audite este site");
    act(() => emit({ type: "reasoning", text: "private" }));
    expect(host.textContent).toContain("Pensando...");
    expect(host.textContent).not.toContain("private");
  });

  test("oculta a mensagem de roteamento antiga e o título sem perder progresso útil", () => {
    sendMessage("audite este site");
    act(() => emit({ type: "phase", text: "Estou considerando o contexto para escolher como atender este pedido." }));
    expect(host.textContent).not.toContain("Estou considerando o contexto para escolher como atender este pedido.");
    expect(host.textContent).not.toContain("Andamento dos especialistas");

    act(() => emit({ type: "phase", text: "Verificando os nomes acessíveis dos botões." }));
    expect(host.textContent).toContain("Verificando os nomes acessíveis dos botões.");
    expect(host.textContent).not.toContain("Atualizações da execução");
    const item = host.querySelector('[role="listitem"][aria-label="Verificando os nomes acessíveis dos botões."]');
    expect(item?.getAttribute("tabindex")).toBe("0");
    expect(item?.closest("[aria-live]")).toBeNull();
  });

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

  test("a resposta visível não exibe marcadores markdown crus", () => {
    sendMessage("responda normalmente");
    act(() => emit({ type: "token", text: "### Título\n\n***Importante***: `texto`" }));

    expect(host.textContent).toContain("Título");
    expect(host.textContent).toContain("Importante: texto");
    expect(host.textContent).not.toContain("###");
    expect(host.textContent).not.toContain("***");
    expect(host.textContent).not.toContain("`");
    const reply = host.querySelector('[aria-label^="Resposta do Assistente:"]');
    expect(reply?.getAttribute("aria-label")).toContain("Importante: texto");
    expect(reply?.getAttribute("aria-label")).not.toContain("###");
    expect(reply?.getAttribute("aria-label")).not.toContain("***");
  });

  test("o andamento da squad fica navegável pelas setas, sem anúncio automático", () => {
    sendMessage("audite este site com a squad");
    act(() => emit({
      type: "squad_task",
      task_id: "task-1",
      role: "qa_lead",
      title: "Preparar verificações",
      status: "in_progress",
    }));
    act(() => emit({
      type: "squad_progress",
      task_id: "task-1",
      role: "qa_lead",
      message: "Reunindo as evidências necessárias.",
    }));
    act(() => emit({
      type: "squad_progress", task_id: "task-1", role: "qa_lead",
      message: "O documento recebido declara o idioma inglês.",
    }));

    const items = Array.from(host.querySelectorAll<HTMLElement>("[data-squad-status='true']"));
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Reunindo as evidências");
    expect(host.textContent).not.toContain("Preparar verificações");
    expect(liveRegions()[0].textContent).not.toContain("Reunindo as evidências");

    items[0].focus();
    act(() => items[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    expect(document.activeElement).toBe(items[1]);
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
