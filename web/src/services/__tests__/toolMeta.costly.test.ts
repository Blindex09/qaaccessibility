/* eslint-env jest */
import { getToolRisk } from "../toolMeta";

describe("risco das ferramentas que gastam muito", () => {
  it("a pesquisa profunda é custosa, não 'apenas consulta': a pessoa precisa saber antes de aprovar", () => {
    expect(getToolRisk("run_deep_research")).toBe("costly");
  });

  it("uma consulta comum continua sendo só consulta", () => {
    expect(getToolRisk("tavily_search")).toBe("read");
  });
});
