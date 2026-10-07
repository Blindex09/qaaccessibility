// Limite de tokens por resposta escolhido pela pessoa nas Configurações.
// Vazio ou 0 = sem limite: o sistema nunca impõe um teto de trabalho por conta própria.

export const TOKEN_BUDGET_MAX = 1_000_000_000;

export interface ParsedTokenBudget {
  /** Valor a enviar ao backend; 0 significa "sem limite". */
  value: number;
  /** Mensagem em português quando o texto digitado não é um número válido. */
  error?: string;
}

export function parseTokenBudget(text: string): ParsedTokenBudget {
  const cleaned = text.replace(/[\s.]/g, "");
  if (cleaned === "") return { value: 0 };
  if (!/^\d+$/.test(cleaned)) {
    return { value: 0, error: "Digite só números inteiros no limite de tokens, ou deixe em branco para não ter limite." };
  }
  const value = Number(cleaned);
  if (value > TOKEN_BUDGET_MAX) {
    return { value: 0, error: "O limite de tokens é grande demais. Digite um valor menor, ou deixe em branco para não ter limite." };
  }
  return { value };
}

export function describeTokenBudget(value: number): string {
  return value > 0
    ? `Cada resposta pode usar até ${value.toLocaleString("pt-BR")} tokens. Ao atingir, o assistente entrega o que já apurou e explica como continuar.`
    : "Sem limite: o assistente usa o que a tarefa precisar.";
}
