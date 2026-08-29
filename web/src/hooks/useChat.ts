import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import {
  deleteChatHistory,
  fetchChatHistory,
  sendCancel,
  sendClarify,
  streamChat,
  type ChatEvent,
} from "../services/chat";
import { parseClarify } from "../services/clarifyModel";
import { getToolGroupKey, getToolProgressText } from "../services/toolMeta";
import { isDirectMediaOperation, toolStatusText, type ToolCallData } from "../services/toolPresentation";
import { addUsage, EMPTY_USAGE, type TokenUsage } from "../services/usage";

/** Uma fonte real citada por uma ferramenta de pesquisa (deep_research,
 * tavily_search, exa_search) neste turno -- ver ToolResultSummary. */
export interface ChatSource {
  title: string;
  url: string;
}

/**
 * Mensagens do chat. Além de user/assistant, há "status": linhas de atividade
 * observável (fase, subagente e ferramenta) que entram no histórico.
 */
export interface ChatMessage {
  role: "user" | "assistant" | "status";
  content: string;
  /** Conteúdo original da mensagem (com base64 de anexos) para enviar ao backend. */
  rawContent?: string;
  kind?: "agent" | "phase" | "tool" | "clarify";
  groupKey?: string;
  /** Estado estruturado da execução; evita inferir sucesso/falha a partir do texto visível. */
  toolCall?: ToolCallData;
  /** Tokens gastos no turno que produziu esta resposta (só no balão do assistente). */
  usage?: TokenUsage;
}

/** Pergunta do agente aguardando resposta do usuário (fluxo clarify). */
export interface PendingClarify {
  requestId: string;
  question: string;
  choices: string[];
}

function _agentLine(ev: Extract<ChatEvent, { type: "agent" }>): string {
  const friendlyNames: Record<string, string> = {
    perceiver: "Percepção e Mídia",
    operability: "Teclado e Operabilidade",
    understandability: "Formulários e Linguagem",
    robustness: "Estrutura e Tags ARIA",
    aria_specialist: "Atributos ARIA",
    section508: "Requisitos de Acessibilidade ADA/508",
    css_analyzer: "Estilos e CSS",
    ajax_dynamic: "Carregamento Dinâmico (AJAX)",
    cognitive: "Acessibilidade Cognitiva",
    screen_reader: "Leitor de Tela",
    mobile_a11y: "Layout Mobile e Toque",
    forms_a11y: "Campos de Formulário",
    widgets_a11y: "Componentes Complexos (Modais/Tabs)",
    wcag_semantics: "Semântica WCAG",
    compliance_audit: "Conformidade WCAG 2.2",
    react_framework: "Código React/JS",
    angular_framework: "Código Angular",
    vue_framework: "Código Vue",
    tailwind_css: "Estilos Tailwind CSS",
    visual_a11y: "Análise Visual de Layout",
  };
  const agentFriendlyName = friendlyNames[ev.agent] || ev.agent;
  if (ev.phase === "start") return `Verificando ${agentFriendlyName}…`;
  if (!ev.ok) return `Falha ao analisar ${agentFriendlyName}`;
  return `Verificação de ${agentFriendlyName} concluída. ${ev.issues ?? 0} problema(s) encontrado(s)`;
}

/**
 * Texto observável de cada ferramenta. Delega ao catálogo único em
 * `services/toolMeta` — aqui só fica a re-exportação que o chat consome.
 */
export function getFriendlyToolName(name: string, status: "start" | "end"): string {
  return getToolProgressText(name, status);
}

/**
 * Anúncios curtos para a live region do chat.
 *
 * Por que existirem: o balão da resposta NÃO é uma live region, e não deve
 * ser — ele cresce token a token e um `aria-live` ali dispararia a cada delta,
 * tornando a resposta impossível de ouvir. A política é deliberadamente
 * silenciosa durante ferramentas e fases internas: anuncia apenas "Digitando...",
 * a resposta pronta e estados reais de conexão/reconexão. Os cartões continuam
 * disponíveis pela navegação normal do leitor de tela, sem poluir a fala.
 */
export const TYPING_ANNOUNCEMENT = "Digitando...";
export const ANSWER_ERROR_ANNOUNCEMENT = "A resposta do assistente falhou.";

/**
 * Sinal curto quando o agente para e pede algo ao usuário.
 *
 * O pedido de aprovação devolve string vazia de propósito: esse é um diálogo
 * modal e o foco move-se para ele (ver `ClarifyPanel`), portanto anunciar
 * também na live region faria o leitor de tela dizer a mesma coisa duas vezes.
 * Nos outros casos o sinal é deliberadamente curto — não repete a pergunta,
 * que já está no painel — e serve só para dizer que a vez é do usuário.
 */
export function clarifyAnnouncement(question: string): string {
  const view = parseClarify(question);
  if (view.kind === "approval") return "";
  if (view.kind === "plan") {
    const n = view.steps.length;
    return `O assistente propôs um plano com ${n} passo${n === 1 ? "" : "s"}. Responda no painel abaixo.`;
  }
  return "O assistente fez uma pergunta. Responda no painel abaixo.";
}

/**
 * Intervalo entre limpar e reescrever a live region. Uma live region só fala
 * quando o texto MUDA, e estas frases repetem-se em todos os turnos; sem o
 * passo de limpeza o segundo turno seria silencioso. Mesmo padrão do
 * `navAnnouncement` no `App.tsx`.
 */
const ANNOUNCE_RESET_MS = 50;

function plainTextForAnnouncement(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/^```[^\n]*\n?|```$/g, ""))
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*(?:[-*_]\s*){3,}$/gm, "")
    .replace(/[*_~`>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Chave no localStorage que guarda o `conversation_id` corrente -- só existe
 * no navegador (guardado por `typeof localStorage`, mesmo padrão defensivo já
 * usado neste arquivo para `crypto.randomUUID`); em runtimes nativos (Expo em
 * iOS/Android, sem `localStorage`) a conversa simplesmente não persiste entre
 * aberturas do app, igual ao comportamento de antes desta mudança. */
const CONVERSATION_ID_STORAGE_KEY = "qa_a11y_conversation_id";

function generateConversationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function readStoredConversationId(): string | null {
  if (typeof localStorage === "undefined") return null;
  try {
    return localStorage.getItem(CONVERSATION_ID_STORAGE_KEY);
  } catch {
    return null; // localStorage pode lançar em modo privado/quota cheia -- degrada para sessão nova
  }
}

function persistConversationId(id: string): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, id);
  } catch {
    /* best-effort -- a conversa ainda funciona nesta aba, só não sobrevive a um reload */
  }
}

function initialConversationId(): string {
  return readStoredConversationId() || generateConversationId();
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string>("");
  const [pendingClarify, setPendingClarify] = useState<PendingClarify | null>(null);
  const [sessionUsage, setSessionUsage] = useState<TokenUsage>(EMPTY_USAGE);
  const [announcement, setAnnouncement] = useState<string>("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [conversationId, setConversationId] = useState(initialConversationId);
  /** Raciocínio acumulado do turno corrente -- diferente da linha de status
   * transitória ("Raciocinando: ...", que some), fica disponível numa seção
   * recolhível ("Ver raciocínio") mesmo depois do turno terminar. Reseta a
   * cada novo `send()`. */
  const [reasoningText, setReasoningText] = useState("");
  /** Fontes reais citadas pelas ferramentas de pesquisa neste turno (dedup
   * por URL), pra seção "Fontes consultadas". Reseta a cada novo `send()`. */
  const [turnSources, setTurnSources] = useState<ChatSource[]>([]);
  const announceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const announcementClearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  /** ID do turno em andamento (evento `stream_id`), usado por `stop()` para
   * pedir cancelamento explícito ao backend além do abort() da conexão. */
  const streamIdRef = useRef<string | null>(null);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;

  // Restaura o histórico da conversa persistida ao montar -- sem isso, um
  // reload de página sempre começava do zero mesmo com o backend lembrando
  // tudo (chat_history_store.py). Roda uma vez por `conversationId` (troca ao
  // chamar `startNewConversation`).
  useEffect(() => {
    let cancelled = false;
    persistConversationId(conversationId);
    setHistoryLoaded(false);
    fetchChatHistory(conversationId).then((stored) => {
      if (cancelled) return;
      if (stored.length > 0) {
        setMessages(stored.map((m) => ({ role: m.role, content: m.content, rawContent: m.content })));
      }
      setHistoryLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  /** Começa uma conversa nova: novo `conversation_id`, histórico local limpo.
   * Não apaga a conversa anterior no backend -- só deixa de ser a corrente
   * (fica disponível para retomar depois via `GET /chat/conversations`). */
  const startNewConversation = useCallback(() => {
    const id = generateConversationId();
    persistConversationId(id);
    setConversationId(id);
    setMessages([]);
    setSessionUsage(EMPTY_USAGE);
    setPendingClarify(null);
  }, []);

  /** Apaga esta conversa (backend + local) e começa uma nova do zero. */
  const forgetConversation = useCallback(async () => {
    await deleteChatHistory(conversationIdRef.current);
    startNewConversation();
  }, [startNewConversation]);

  /** Troca para uma conversa existente (ex.: escolhida num seletor de
   * histórico). O `useEffect` de `conversationId` cuida de persistir o novo id
   * e buscar o histórico dela -- aqui só limpamos estado transitório do turno
   * atual (o que sobrar de `messages` é substituído assim que o histórico
   * daquela conversa chegar). No-op se já for a conversa corrente. */
  const switchConversation = useCallback(
    (id: string) => {
      if (!id || id === conversationIdRef.current) return;
      setConversationId(id);
      setSessionUsage(EMPTY_USAGE);
      setPendingClarify(null);
    },
    [],
  );

  /**
   * Escreve na live region. Ao contrário de `activity` — que é falatório de
   * progresso e é limpa no fim do turno — o anúncio fica: é ele que diz que a
   * resposta chegou, e apagá-lo no `finally` faria com que nunca fosse falado.
   */
  const announce = useCallback((message: string, clearAfter = false) => {
    if (announceTimerRef.current) clearTimeout(announceTimerRef.current);
    if (announcementClearTimerRef.current) clearTimeout(announcementClearTimerRef.current);
    setAnnouncement("");
    if (!message) return;
    announceTimerRef.current = setTimeout(() => {
      setAnnouncement(message);
      if (clearAfter) {
        announcementClearTimerRef.current = setTimeout(() => setAnnouncement(""), 1000);
      }
    }, ANNOUNCE_RESET_MS);
  }, []);

  useEffect(
    () => () => {
      if (announceTimerRef.current) clearTimeout(announceTimerRef.current);
      if (announcementClearTimerRef.current) clearTimeout(announcementClearTimerRef.current);
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    },
    [],
  );

  const send = useCallback(
    async (text: string, displayText?: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      const history = messages
        .filter((m) => m.role !== "status")
        .map((m) => ({ role: m.role as "user" | "assistant", content: m.rawContent || m.content }));
      
      const uiText = (displayText || trimmed).trim();
      setMessages((m) => [...m, { role: "user", content: uiText, rawContent: trimmed }, { role: "assistant", content: "" }]);
      setStreaming(true);
      setActivity("");
      setDurationMs(null);
      setElapsedMs(0);
      setReasoningText("");
      setTurnSources([]);
      const startedAt = globalThis.performance?.now?.() ?? Date.now();
      const elapsedTimer = setInterval(() => {
        setElapsedMs((globalThis.performance?.now?.() ?? Date.now()) - startedAt);
      }, 1000);
      elapsedTimerRef.current = elapsedTimer;
      announce(TYPING_ANNOUNCEMENT);

      const controller = new AbortController();
      abortRef.current = controller;
      streamIdRef.current = null;

      // Anexa um delta ao último balão do assistente (resposta token a token).
      const appendToAssistant = (delta: string) =>
        setMessages((m) => {
          const copy = m.slice();
          // acha o último assistant (pode haver status depois dele)
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].role === "assistant") {
              copy[i] = { role: "assistant", content: copy[i].content + delta };
              return copy;
            }
          }
          return [...copy, { role: "assistant", content: delta }];
        });

      const setAssistant = (content: string) =>
        setMessages((m) => {
          const copy = m.slice();
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].role === "assistant") {
              copy[i] = { role: "assistant", content };
              return copy;
            }
          }
          return [...copy, { role: "assistant", content }];
        });

      // Linha curta de status observável no histórico.
      const pushStatus = (content: string, kind: ChatMessage["kind"], coalesce: boolean) => {
        setActivity(content);
        setMessages((m) => {
          const last = m[m.length - 1];
          // Evita adicionar mensagens de status idênticas consecutivamente no histórico
          if (last && last.role === "status" && last.content === content) {
            return m;
          }
          if (coalesce) {
            if (last && last.role === "status" && last.kind === kind) {
              const copy = m.slice();
              copy[copy.length - 1] = { ...last, content: last.content + content };
              return copy;
            }
          }
          return [...m, { role: "status", content, kind }];
        });
      };

      const setToolStatus = (
        name: string,
        status: "start" | "end",
        resultSummary?: import("../services/chat").ToolResultSummary | null,
        details: {
          id?: string;
          params?: Record<string, unknown>;
          ok?: boolean;
          error?: string | null;
        } = {},
      ) => {
        const groupKey = getToolGroupKey(name);
        if (resultSummary?.sources?.length) {
          setTurnSources((current) => {
            const seen = new Set(current.map((s) => s.url));
            const fresh = resultSummary.sources!.filter((s) => s.url && !seen.has(s.url));
            return fresh.length ? [...current, ...fresh] : current;
          });
        }
        const accessibleStatus = toolStatusText({
          id: details.id,
          name,
          params: details.params,
          status: status === "start" ? "running" : details.ok === false ? "failed" : "complete",
          affectedCount: resultSummary?.count,
          itemSingular: resultSummary?.item_singular,
          itemPlural: resultSummary?.item_plural,
          error: details.error || undefined,
        });
        setActivity(accessibleStatus);
        const updateMessages = (current: ChatMessage[]) => {
          const copy = current.slice();
          for (let index = copy.length - 1; index >= 0; index -= 1) {
            if (copy[index].role === "user") break;
            if (copy[index].role === "status" && copy[index].groupKey === groupKey) {
              const previousTool = copy[index].toolCall;
              const nextTool: ToolCallData = {
                ...previousTool,
                id: details.id || previousTool?.id,
                name,
                params: details.params || previousTool?.params,
                status: status === "start" ? "running" : details.ok === false ? "failed" : "complete",
                executionCount: status === "start" ? (previousTool?.executionCount || 0) + 1 : previousTool?.executionCount || 1,
                affectedCount: (previousTool?.affectedCount || 0) + (resultSummary?.count || 0),
                itemSingular: resultSummary?.item_singular || previousTool?.itemSingular,
                itemPlural: resultSummary?.item_plural || previousTool?.itemPlural,
                logs: previousTool?.logs,
                error: details.error || undefined,
              };
              const content = toolStatusText(nextTool);
              if (status === "end" && isDirectMediaOperation(nextTool)) {
                copy.splice(index, 1);
                return copy;
              }
              copy[index] = { ...copy[index], content, toolCall: nextTool };
              return copy;
            }
          }
          const toolCall: ToolCallData = {
            id: details.id,
            name,
            params: details.params,
            status: status === "start" ? "running" : details.ok === false ? "failed" : "complete",
            executionCount: 1,
            affectedCount: resultSummary?.count,
            itemSingular: resultSummary?.item_singular,
            itemPlural: resultSummary?.item_plural,
            error: details.error || undefined,
          };
          const content = toolStatusText(toolCall);
          return status === "end" && isDirectMediaOperation(toolCall)
            ? copy
            : [...copy, { role: "status", content, kind: "tool", groupKey, toolCall } as ChatMessage];
        };
        // Garante que tool_starts consecutivos do mesmo grupo sejam agrupados
        // em vez de criarem cards duplicados devido ao batching do React.
        if (status === "start") {
          flushSync(() => setMessages(updateMessages));
        } else {
          setMessages(updateMessages);
        }
      };

      const appendToolLog = (name: string, message: string) => {
        const groupKey = getToolGroupKey(name);
        setMessages((current) => {
          const copy = current.slice();
          for (let index = copy.length - 1; index >= 0; index -= 1) {
            if (copy[index].role === "user") break;
            if (copy[index].role === "status" && copy[index].groupKey === groupKey) {
              const previousTool = copy[index].toolCall;
              if (!previousTool) return current;
              const nextTool: ToolCallData = {
                ...previousTool,
                logs: [...(previousTool.logs || []), message],
              };
              copy[index] = { ...copy[index], toolCall: nextTool };
              return copy;
            }
          }
          // O tool_start pode ainda não ter sido commitido no estado (eventos
          // do mesmo chunk de SSE são batched pelo React). Cria um card
          // provisório para não perder o andamento; o tool_start seguinte
          // encontra essa mensagem pelo groupKey e a atualiza.
          const provisionalTool: ToolCallData = {
            name,
            status: "running",
            logs: [message],
          };
          const provisionalContent = toolStatusText(provisionalTool);
          return [...copy, { role: "status", content: provisionalContent, kind: "tool", groupKey, toolCall: provisionalTool }];
        });
      };

      try {
        await streamChat(
          trimmed,
          history,
          (event: ChatEvent) => {
            switch (event.type) {
              case "stream_id":
                streamIdRef.current = event.id;
                break;
              case "token":
                setActivity("");
                appendToAssistant(event.text);
                break;
              case "thinking":
              case "reasoning":
                if (event.text) {
                  setReasoningText((current) => current + event.text);
                  setActivity("Pensando...");
                }
                break;
              case "phase":
                setActivity(event.text);
                pushStatus(event.text, "phase", false);
                break;
              case "agent":
                pushStatus(_agentLine(event), "agent", false);
                break;
              case "squad_plan":
                pushStatus(
                  `Squad de acessibilidade: ${event.plan.tasks.length} etapas planejadas`,
                  "phase",
                  false,
                );
                break;
              case "tool_start":
                setToolStatus(event.name, "start", null, {
                  id: event.tool_call_id,
                  params: event.arguments,
                });
                break;
              case "tool_progress":
                appendToolLog(event.name, event.message);
                break;
              case "tool_result":
                setToolStatus(event.name, "end", event.result_summary, {
                  id: event.tool_call_id,
                  ok: event.ok,
                  error: event.error,
                });
                break;
              case "clarify":
                // Padrão Hermes (cli.py _clarify_callback): a pergunta vive SO no
                // painel interativo (transitorio) — não ecoa no historico nem na
                // regiao viva. O registro permanente vem depois, em answerClarify
                // (pergunta -> resposta numa unica linha). Evita a pergunta
                // triplicada (historico + activity + painel).
                setPendingClarify({
                  requestId: event.request_id,
                  question: event.question,
                  choices: event.choices,
                });
                announce(clarifyAnnouncement(event.question));
                break;
              case "done":
                if (event.final) setAssistant(event.final);
                // Custo do turno: fica preso ao balão que ele produziu e soma-se
                // ao acumulado da conversa.
                if (event.usage) {
                  const turnUsage = event.usage;
                  setMessages((m) => {
                    const copy = m.slice();
                    for (let i = copy.length - 1; i >= 0; i--) {
                      if (copy[i].role === "assistant") {
                        copy[i] = { ...copy[i], usage: turnUsage };
                        return copy;
                      }
                    }
                    return copy;
                  });
                  setSessionUsage((total) => addUsage(total, turnUsage));
                }
                announce(plainTextForAnnouncement(event.final), true);
                setDurationMs((globalThis.performance?.now?.() ?? Date.now()) - startedAt);
                break;
              case "cancelled":
                // Normalmente o abort() do fetch (stop() abaixo) já fechou a
                // leitura antes deste evento chegar -- mas cobre o caso de
                // cancelamento vindo de outra aba/dispositivo com o mesmo stream_id.
                setActivity("");
                break;
              case "error":
                setActivity("");
                {
                  const errText = (event.error || "").trim();
                  const fullError = errText.toLowerCase().startsWith("desculpe") || errText.toLowerCase().startsWith("ocorreu um erro")
                    ? errText
                    : `Desculpe, ocorreu um erro: ${errText}`;
                  setAssistant(fullError);
                }
                announce(ANSWER_ERROR_ANNOUNCEMENT);
                setDurationMs((globalThis.performance?.now?.() ?? Date.now()) - startedAt);
                break;
            }
          },
          { signal: controller.signal, conversationId: conversationIdRef.current },
        );
      } catch (err) {
        const isAbort = err instanceof Error && (err.name === "AbortError" || err.message.includes("aborted"));
        if (!isAbort) {
          setAssistant(`Falha na conexão: ${err instanceof Error ? err.message : String(err)}`);
        }
      } finally {
        clearInterval(elapsedTimer);
        if (elapsedTimerRef.current === elapsedTimer) elapsedTimerRef.current = null;
        setDurationMs((globalThis.performance?.now?.() ?? Date.now()) - startedAt);
        setStreaming(false);
        setActivity("");
        setPendingClarify(null);
        abortRef.current = null;
      }
    },
    [announce, messages, streaming],
  );

  // Responde a pergunta do agente: envia ao backend e some com o prompt.
  const answerClarify = useCallback(
    async (answer: string) => {
      const p = pendingClarify;
      if (!p) return;
      setPendingClarify(null);
      // Registro permanente único da interacao (pergunta -> resposta), legivel
      // com as setas. A pergunta so existia no painel transitorio ate aqui.
      setMessages((m) => [
        ...m,
        { role: "status", content: `Pergunta do assistente: ${p.question}`, kind: "clarify" },
        { role: "status", content: `Você respondeu: ${answer || "(pulado)"}`, kind: "clarify" },
      ]);
      try {
        await sendClarify(p.requestId, answer);
      } catch {
        /* o turno segue; se expirou, o agente trata o vazio */
      }
    },
    [pendingClarify],
  );

  const stop = useCallback(() => {
    // abort() é o que garante a UI parar já — não espera a resposta do
    // cancelamento explícito. sendCancel é só um sinal extra ao backend para
    // ele parar de trabalhar (best-effort; ver chat_progress.py), disparado
    // sem bloquear a UI.
    abortRef.current?.abort();
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    if (streamIdRef.current) {
      void sendCancel(streamIdRef.current).catch(() => {
        /* best-effort: a UI já parou via abort() independente disto */
      });
    }
    setStreaming(false);
    setActivity("");
    setPendingClarify(null);
  }, []);

  return {
    messages,
    streaming,
    activity,
    announcement,
    elapsedMs,
    durationMs,
    reasoningText,
    turnSources,
    pendingClarify,
    sessionUsage,
    send,
    answerClarify,
    stop,
    /** Id da conversa corrente -- estável entre reloads (persistido em localStorage). */
    conversationId,
    /** `false` enquanto o histórico persistido ainda está sendo buscado no mount/troca de conversa. */
    historyLoaded,
    startNewConversation,
    forgetConversation,
    switchConversation,
  };
}
