/**
 * Consumo de tokens de um turno de chat.
 *
 * O backend soma o `usage` nos quatro caminhos de provider e devolve-o no evento
 * SSE `done` (ver `chat_runtime.py`). Aqui fica o tipo, a soma por conversa e a
 * formatação — tudo puro, para poder ser testado sem renderizador.
 */

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export const EMPTY_USAGE: TokenUsage = {
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
};

/** Soma o consumo de mais um turno ao acumulado da conversa. */
export function addUsage(total: TokenUsage, turn: TokenUsage): TokenUsage {
  return {
    input_tokens: total.input_tokens + turn.input_tokens,
    output_tokens: total.output_tokens + turn.output_tokens,
    total_tokens: total.total_tokens + turn.total_tokens,
  };
}

/** Formata a contagem para leitura humana (agrupamento pt-BR). */
export function formatTokenCount(value: number): string {
  return value.toLocaleString("pt-BR");
}
