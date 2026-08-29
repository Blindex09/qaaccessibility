/* eslint-env jest, node */

import { toolStatusText, type ToolCallData } from "../toolPresentation";

describe("toolStatusText — alinhado com agent-chat-app", () => {
  const base: ToolCallData = { name: "analyze_page", status: "running" };

  test("genérico: Executando ferramenta X... → Executou X.", () => {
    expect(toolStatusText({ ...base, status: "running" })).toBe("Executando ferramenta analyze_page...");
    expect(toolStatusText({ ...base, status: "complete" })).toBe("Executou analyze_page.");
  });

  test("web: Pesquisando na web... → Executou pesquisa web; navegou em X páginas.", () => {
    const web: ToolCallData = { name: "tavily_search", status: "running" };
    expect(toolStatusText(web)).toBe("Pesquisando na web...");
    expect(toolStatusText({ ...web, status: "complete", affectedCount: 1 })).toBe("Executou pesquisa web; navegou em 1 página.");
    expect(toolStatusText({ ...web, status: "complete", affectedCount: 3 })).toBe("Executou pesquisa web; navegou em 3 páginas.");
    expect(toolStatusText({ ...web, status: "complete" })).toBe("Executou pesquisa web.");
  });

  test("web múltipla: Pesquisando e navegando na web...", () => {
    expect(toolStatusText({ name: "tavily_search", status: "running", executionCount: 2 })).toBe("Pesquisando e navegando na web...");
  });

  test("file_edit: Editando arquivo... → Editou um arquivo.", () => {
    const edit: ToolCallData = { name: "fix_and_zip_files", status: "running", params: { path: "src/App.tsx" } };
    expect(toolStatusText(edit)).toBe("Editando arquivo src/App.tsx...");
    expect(toolStatusText({ ...edit, status: "complete" })).toBe("Editou um arquivo.");
  });

  test("file_edit múltiplo: Editando arquivos... → Editou arquivos.", () => {
    const edit: ToolCallData = { name: "fix_and_zip_files", status: "running", affectedCount: 2 };
    expect(toolStatusText(edit)).toBe("Editando arquivos...");
    expect(toolStatusText({ ...edit, status: "complete" })).toBe("Editou arquivos.");
  });

  test("command: Executando comando... → Executou comando.", () => {
    const cmd: ToolCallData = { name: "run_command", status: "running", params: { command: "npm test" } };
    expect(toolStatusText(cmd)).toBe("Executando comando npm test...");
    expect(toolStatusText({ ...cmd, status: "complete" })).toBe("Executou comando npm test.");
  });

  test("command múltiplo: Executando comandos... → Executou comandos.", () => {
    const cmd: ToolCallData = { name: "run_command", status: "running", affectedCount: 2 };
    expect(toolStatusText(cmd)).toBe("Executando comandos...");
    expect(toolStatusText({ ...cmd, status: "complete" })).toBe("Executou comandos.");
  });

  test("falha genérica", () => {
    expect(toolStatusText({ ...base, status: "failed" })).toBe("A ferramenta analyze_page falhou.");
  });

  test("falha web", () => {
    expect(toolStatusText({ name: "tavily_search", status: "failed" })).toBe("Não foi possível concluir a pesquisa web.");
  });
});
