/* eslint-env jest */
import { getToolLabel, getToolRisk } from "../toolMeta";

describe("risco das ferramentas que gastam muito", () => {
  it("a pesquisa profunda é custosa, não 'apenas consulta': a pessoa precisa saber antes de aprovar", () => {
    expect(getToolRisk("run_deep_research")).toBe("costly");
  });

  it("uma consulta comum continua sendo só consulta", () => {
    expect(getToolRisk("tavily_search")).toBe("read");
  });
});

describe("ferramentas que só leem não aparecem como 'altera algo e não dá para desfazer'", () => {
  it.each(["verify_screen_reader_announcements", "design_review"])("%s é só consulta", (name) => {
    expect(getToolRisk(name)).toBe("read");
  });

  it.each(["create_jira_issue", "create_azure_devops_work_item"])("%s cria algo fora da app", (name) => {
    expect(getToolRisk(name)).toBe("mutating");
  });

  it("toda ferramenta cadastrada tem um nome em português para a pessoa", () => {
    for (const name of ["verify_screen_reader_announcements", "design_review", "create_jira_issue", "create_azure_devops_work_item"]) {
      expect(getToolLabel(name)).not.toBe("ação solicitada");
    }
  });
});
