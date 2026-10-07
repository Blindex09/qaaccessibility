/* eslint-env jest */
import { describeTokenBudget, parseTokenBudget, TOKEN_BUDGET_MAX } from "../tokenBudget";

describe("parseTokenBudget", () => {
  it("vazio significa sem limite", () => {
    expect(parseTokenBudget("")).toEqual({ value: 0 });
    expect(parseTokenBudget("   ")).toEqual({ value: 0 });
  });

  it("aceita inteiros, com separador de milhar ou espaços", () => {
    expect(parseTokenBudget("250000")).toEqual({ value: 250000 });
    expect(parseTokenBudget("250.000")).toEqual({ value: 250000 });
    expect(parseTokenBudget(" 1 000 ")).toEqual({ value: 1000 });
  });

  it("zero também é sem limite", () => {
    expect(parseTokenBudget("0")).toEqual({ value: 0 });
  });

  it("rejeita texto, decimais e negativos com mensagem em português", () => {
    for (const bad of ["abc", "12,5", "-5", "1e6"]) {
      const result = parseTokenBudget(bad);
      expect(result.error).toMatch(/números inteiros/);
    }
  });

  it("rejeita valor acima do máximo aceito pelo backend", () => {
    expect(parseTokenBudget(String(TOKEN_BUDGET_MAX + 1)).error).toMatch(/grande demais/);
    expect(parseTokenBudget(String(TOKEN_BUDGET_MAX))).toEqual({ value: TOKEN_BUDGET_MAX });
  });
});

describe("describeTokenBudget", () => {
  it("explica o que acontece com e sem limite", () => {
    expect(describeTokenBudget(0)).toMatch(/Sem limite/);
    expect(describeTokenBudget(250000)).toMatch(/250\.000 tokens/);
    expect(describeTokenBudget(250000)).toMatch(/entrega o que já apurou/);
  });
});
