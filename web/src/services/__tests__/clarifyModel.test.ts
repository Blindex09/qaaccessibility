/* eslint-env jest */

import { parseClarify, planStepStatusLabel } from "../clarifyModel";
import { getToolLabel, getToolRisk } from "../toolMeta";

/**
 * O backend manda plano, pedido de aprovação e pergunta simples pelo MESMO evento
 * `clarify`. Antes, a UI mostrava os três como prosa solta. Estes testes fixam a
 * convenção que separa os três casos (ver `services/clarifyModel`).
 */

/** Texto exatamente como `_approval_summary` o monta em run_agent.py. */
function approvalSummary(tool: string, shownArgs: string, digest: string): string {
  return (
    `A ferramenta '${tool}' realizará uma ação com efeito externo ou gravará um artefato. ` +
    `Argumentos: ${shownArgs}. Identificador da ação: ${digest}. Aprovar exatamente esta ação?`
  );
}

const HIGH_RISK = approvalSummary(
  "fix_and_zip_files",
  '{"apply_all": true, "session_id": "abc-123"}',
  "09967a033d330cdfddc70cd3099035d07f7d15009f0091d9edd3fabea79c5bd4",
);

const LOW_RISK = approvalSummary(
  "export_xlsx",
  '{"filename": "relatorio.xlsx"}',
  "add9f5f997946089da155d3fc832058445ff393c9b5ddaa54e956a25427be6af",
);

describe("parseClarify — pedido de aprovação", () => {
  test("uma ação que reescreve código sai como aprovação de risco 'mutating'", () => {
    const view = parseClarify(HIGH_RISK);
    expect(view.kind).toBe("approval");
    if (view.kind !== "approval") return;
    expect(view.tool).toBe("fix_and_zip_files");
    expect(view.toolLabel).toBe("Correção de código");
    expect(view.risk).toBe("mutating");
    expect(view.digest).toBe(
      "09967a033d330cdfddc70cd3099035d07f7d15009f0091d9edd3fabea79c5bd4",
    );
  });

  test("os argumentos viram lista chave→valor, não um blob de JSON", () => {
    const view = parseClarify(HIGH_RISK);
    if (view.kind !== "approval") throw new Error("esperava aprovação");
    expect(view.args).toEqual([
      { key: "apply_all", value: "true" },
      { key: "session_id", value: "abc-123" },
    ]);
  });

  test("uma ação que só gera um arquivo tem risco menor que uma que reescreve código", () => {
    const low = parseClarify(LOW_RISK);
    const high = parseClarify(HIGH_RISK);
    if (low.kind !== "approval" || high.kind !== "approval") throw new Error("esperava aprovação");
    expect(low.risk).toBe("artifact");
    expect(low.toolLabel).toBe("Relatório Excel");
    expect(low.args).toEqual([{ key: "filename", value: "relatorio.xlsx" }]);
    expect(low.risk).not.toBe(high.risk);
  });

  test("argumentos ilegíveis são mostrados crus, nunca descartados", () => {
    const view = parseClarify(
      approvalSummary("create_github_issue", "{isto não é json", "b".repeat(64)),
    );
    if (view.kind !== "approval") throw new Error("esperava aprovação");
    expect(view.args).toEqual([{ key: "argumentos", value: "{isto não é json" }]);
  });

  test("ferramenta desconhecida no canal de aprovação assume o risco mais alto", () => {
    const view = parseClarify(approvalSummary("some_future_tool", "{}", "c".repeat(64)));
    if (view.kind !== "approval") throw new Error("esperava aprovação");
    expect(view.risk).toBe("mutating");
  });
});

describe("parseClarify — plano / checklist", () => {
  const PLAN = [
    "Plano de auditoria da página:",
    "1. [x] Ler a estrutura da página",
    "2. [~] Verificar contraste e mídia",
    "3. [ ] Verificar formulários",
    "4. Gerar o relatório",
  ].join("\n");

  test("cada passo mantém o seu estado próprio", () => {
    const view = parseClarify(PLAN);
    expect(view.kind).toBe("plan");
    if (view.kind !== "plan") return;
    expect(view.intro).toBe("Plano de auditoria da página:");
    expect(view.steps).toEqual([
      { label: "Ler a estrutura da página", status: "done" },
      { label: "Verificar contraste e mídia", status: "current" },
      { label: "Verificar formulários", status: "pending" },
      { label: "Gerar o relatório", status: "pending" },
    ]);
  });

  test("listas com travessão também são planos", () => {
    const view = parseClarify("- [ ] Corrigir alt das imagens\n- [ ] Corrigir rótulos dos campos");
    expect(view.kind).toBe("plan");
    if (view.kind !== "plan") return;
    expect(view.steps).toHaveLength(2);
    expect(view.steps.every((s) => s.status === "pending")).toBe(true);
  });

  test("um único item não é plano: fica pergunta", () => {
    expect(parseClarify("1. Quer que eu continue?").kind).toBe("question");
  });

  test("cada estado tem um rótulo acessível em texto, não só cor", () => {
    expect(planStepStatusLabel("done")).toBe("Concluído");
    expect(planStepStatusLabel("current")).toBe("Em curso");
    expect(planStepStatusLabel("pending")).toBe("Pendente");
  });
});

describe("parseClarify — pergunta simples", () => {
  test("uma pergunta aberta não vira plano nem aprovação", () => {
    expect(parseClarify("Qual é a URL que devo auditar?").kind).toBe("question");
  });

  test("texto vazio não rebenta", () => {
    expect(parseClarify("").kind).toBe("question");
  });
});

describe("toolMeta", () => {
  test("as ferramentas com efeito irreversível são as de maior risco", () => {
    for (const tool of ["fix_and_zip_files", "create_github_issue", "run_remote_test", "nvda_speak"]) {
      expect(getToolRisk(tool)).toBe("mutating");
    }
  });

  test("as ferramentas que só produzem arquivo ficam no nível intermédio", () => {
    for (const tool of ["export_xlsx", "generate_vpat", "generate_test_suite", "generate_automation_script"]) {
      expect(getToolRisk(tool)).toBe("artifact");
    }
  });

  test("as ferramentas de leitura não são marcadas como perigosas", () => {
    for (const tool of ["analyze_page", "analyze_site", "tavily_search", "open_live_preview"]) {
      expect(getToolRisk(tool)).toBe("read");
    }
  });

  test("o crachá usa um rótulo curto, não a frase de progresso", () => {
    expect(getToolLabel("fix_and_zip_files")).toBe("Correção de código");
    expect(getToolLabel("fix_and_zip_files").length).toBeLessThan(30);
  });
});
