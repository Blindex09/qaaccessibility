/* eslint-env jest */

import { addUsage } from "../../services/usage";
import { getFriendlyToolName } from "../useChat";
import { getToolResultText } from "../../services/toolMeta";

/**
 * Bug real de auditoria: só 8 das ferramentas do chat tinham texto amigável; as
 * restantes caíam no default genérico "Processando ação...", deixando o usuário
 * sem saber o que o agente estava fazendo.
 */
const TOOLS_WITH_FRIENDLY_TEXT = [
  "tavily_search",
  "exa_search",
  "analyze_page",
  "analyze_site",
  "fix_and_zip_files",
  "unzip_and_list_files",
  "export_xlsx",
  "generate_vpat",
  "generate_test_suite",
  "generate_automation_script",
  "create_github_issue",
  "run_remote_test",
  "nvda_speak",
  "open_live_preview",
  "evaluate_research",
  "run_deep_research",
  "clarify",
  "analyze_document",
  "generate_checklist",
  "export_checklist_pdf",
  "generate_accessibility_statement",
  "export_accessibility_statement_pdf",
  "read_local_project_files",
  "fix_local_project_files",
  "undo_last_fix",
  "run_cross_browser_test",
  "install_playwright_browsers",
];

describe("getFriendlyToolName", () => {
  test.each(TOOLS_WITH_FRIENDLY_TEXT)("%s has specific start and end text", (tool) => {
    const start = getFriendlyToolName(tool, "start");
    const end = getFriendlyToolName(tool, "end");
    expect(start).not.toBe("Processando ação...");
    expect(end).not.toBe("Ação finalizada");
    expect(start.length).toBeGreaterThan(0);
    expect(end.length).toBeGreaterThan(0);
  });

  test("unknown tools still fall back to the generic text", () => {
    expect(getFriendlyToolName("some_future_tool", "start")).toBe("Processando ação...");
    expect(getFriendlyToolName("some_future_tool", "end")).toBe("Ação finalizada");
  });
});

/**
 * Contagem real vinda do backend (ver chat_runtime.py::_extract_result_summary)
 * -- pedido do usuário (2026-08-12): "Corrigiu 8 arquivos" em vez de texto
 * fixo genérico, quando o backend souber a contagem real.
 */
describe("getToolResultText", () => {
  test("usa a contagem real (plural) quando o backend forneceu result_summary", () => {
    const text = getToolResultText("fix_and_zip_files", {
      count: 8,
      item_singular: "arquivo corrigido",
      item_plural: "arquivos corrigidos",
    });
    expect(text).toContain("8 arquivos corrigidos");
  });

  test("usa o singular quando a contagem é 1", () => {
    const text = getToolResultText("generate_checklist", {
      count: 1,
      item_singular: "item no checklist",
      item_plural: "itens no checklist",
    });
    expect(text).toContain("1 item no checklist");
  });

  test("sem result_summary cai no texto estático de sempre", () => {
    expect(getToolResultText("export_xlsx", undefined)).toBe(getFriendlyToolName("export_xlsx", "end"));
  });

  test("result_summary sem count cai no texto estático de sempre", () => {
    expect(getToolResultText("run_deep_research", { sources: [{ title: "x", url: "https://x" }] }))
      .toBe(getFriendlyToolName("run_deep_research", "end"));
  });
});

/**
 * O backend já devolve `usage` nos 4 caminhos de provider, mas o total da
 * conversa é a soma dos turnos — é isso que o indicador do cabeçalho mostra.
 */
describe("addUsage", () => {
  test("soma cada campo do turno ao acumulado da conversa", () => {
    const total = addUsage(
      { input_tokens: 800, output_tokens: 434, total_tokens: 1234 },
      { input_tokens: 100, output_tokens: 50, total_tokens: 150 },
    );
    expect(total).toEqual({ input_tokens: 900, output_tokens: 484, total_tokens: 1384 });
  });

  test("partir do zero devolve exatamente o turno", () => {
    const turn = { input_tokens: 10, output_tokens: 5, total_tokens: 15 };
    expect(addUsage({ input_tokens: 0, output_tokens: 0, total_tokens: 0 }, turn)).toEqual(turn);
  });
});
