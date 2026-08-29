// Cliente do chat agentico com streaming (SSE) do backend /chat/stream.
// axios não expoe streaming no browser, entao usamos fetch + ReadableStream.

import type { TokenUsage } from "./usage";

export const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  (typeof window !== "undefined"
    ? window.location.protocol + "//" + window.location.hostname + ":8001"
    : "http://localhost:8001");
const API_TOKEN = process.env.EXPO_PUBLIC_QA_API_TOKEN ?? "";
const API_HEADERS = {
  "Content-Type": "application/json",
  ...(API_TOKEN ? { "X-QA-Accessibility-Token": API_TOKEN } : {}),
};

/** Resumo estruturado do resultado real de uma ferramenta (ver
 * chat_runtime.py::_extract_result_summary) -- contagem real e/ou fontes
 * citáveis, quando a ferramenta suportar. `undefined`/ausente para
 * ferramentas sem mapeamento ou cujo resultado deu erro. */
export interface ToolResultSummary {
  count?: number;
  item_singular?: string;
  item_plural?: string;
  sources?: { title: string; url: string }[];
}

export type ChatEvent =
  | { type: "stream_id"; id: string }
  | { type: "token"; text: string }
  | { type: "thinking"; text?: string }
  | { type: "reasoning"; text?: string }
  | { type: "tool_start"; tool_call_id?: string; name: string; arguments?: Record<string, unknown> }
  | { type: "tool_progress"; tool_call_id?: string; name: string; message: string }
  | {
      type: "tool_result";
      tool_call_id?: string;
      name: string;
      ok?: boolean;
      error?: string | null;
      result_summary?: ToolResultSummary | null;
    }
  | { type: "phase"; text: string }
  | { type: "agent"; phase: "start" | "done"; agent: string; ok?: boolean; issues?: number }
  | { type: "squad_plan"; plan: { objective: string; tasks: { id: string; title: string; role: string; status: string }[] } }
  | { type: "clarify"; request_id: string; question: string; choices: string[] }
  | { type: "done"; final: string; usage?: TokenUsage }
  | { type: "cancelled" }
  | { type: "error"; error: string };

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ProviderModels {
  id: string;
  label: string;
  models: string[];
  model_capabilities?: Record<string, {
    tools?: boolean;
    vision?: boolean;
    thinking?: boolean;
    structured_outputs?: boolean;
    context_window?: number;
  }>;
}

/** Responde a uma pergunta do agente (evento `clarify`), desbloqueando o turno. */
export async function sendClarify(requestId: string, answer: string): Promise<boolean> {
  const resp = await fetch(`${BASE_URL}/chat/clarify`, {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify({ request_id: requestId, answer }),
  });
  if (!resp.ok) return false;
  const data = (await resp.json()) as { delivered: boolean };
  return Boolean(data.delivered);
}

/** Interrompe o turno em andamento (evento `stream_id` no início do stream).
 * Best-effort: para o backend de entregar mais eventos, mas não aborta uma
 * chamada HTTP síncrona já em andamento no provider (ver chat_progress.py). */
export async function sendCancel(streamId: string): Promise<boolean> {
  const resp = await fetch(`${BASE_URL}/chat/cancel`, {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify({ stream_id: streamId }),
  });
  if (!resp.ok) return false;
  const data = (await resp.json()) as { cancelled: boolean };
  return Boolean(data.cancelled);
}

/** Lista os providers de chat e os modelos do catálogo local revisado. */
export async function getModels(): Promise<ProviderModels[]> {
  // The catalog is live and changes when the provider key changes. Avoid a
  // browser/proxy cache keeping preview models visible after removal.
  const resp = await fetch(`${BASE_URL}/models?_ts=${Date.now()}`, { headers: API_HEADERS, cache: "no-store" });
  if (!resp.ok) throw new Error(`Falha ao listar modelos: HTTP ${resp.status}`);
  const data = (await resp.json()) as { providers: ProviderModels[] };
  return data.providers ?? [];
}

export interface StoredChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  message_count: number;
  last_updated: number;
}

/** Histórico persistido de uma conversa (chat_history_store.py no backend) --
 * usado para restaurar a tela depois de um reload em vez de começar do zero.
 * Falha de rede devolve `[]` (nunca lança): sem histórico prévio é um estado
 * normal (conversa nova), não um erro para o usuário ver. */
export async function fetchChatHistory(conversationId: string): Promise<StoredChatMessage[]> {
  try {
    const resp = await fetch(`${BASE_URL}/chat/history/${encodeURIComponent(conversationId)}`, {
      headers: API_HEADERS,
    });
    if (!resp.ok) return [];
    const data = (await resp.json()) as { messages: StoredChatMessage[] };
    return data.messages ?? [];
  } catch {
    return [];
  }
}

/** Lista as conversas mais recentes -- para um seletor de conversas na UI. */
export async function listConversations(limit = 20): Promise<ConversationSummary[]> {
  try {
    const resp = await fetch(`${BASE_URL}/chat/conversations?limit=${limit}`, { headers: API_HEADERS });
    if (!resp.ok) return [];
    const data = (await resp.json()) as { conversations: ConversationSummary[] };
    return data.conversations ?? [];
  } catch {
    return [];
  }
}

/** Apaga o histórico persistido de uma conversa (ex.: usuário pede "conversa nova"). */
export async function deleteChatHistory(conversationId: string): Promise<void> {
  try {
    await fetch(`${BASE_URL}/chat/history/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
      headers: API_HEADERS,
    });
  } catch {
    /* best-effort: limpar localmente já resolve a UI mesmo se isso falhar */
  }
}

/**
 * Abre um stream SSE com o backend e chama `onEvent` para cada evento.
 * Resolve quando o stream termina; rejeita em erro de rede/HTTP.
 */
export async function streamChat(
  message: string,
  history: ChatTurn[],
  onEvent: (event: ChatEvent) => void,
  opts: { provider?: string; model?: string; conversationId?: string; signal?: AbortSignal } = {},
): Promise<void> {
  const resp = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify({
      message,
      history,
      provider: opts.provider,
      model: opts.model,
      conversation_id: opts.conversationId,
    }),
    signal: opts.signal,
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`Chat falhou: HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload) as ChatEvent);
      } catch {
        // linha parcial/malformada — ignora
      }
    }
  }
}
