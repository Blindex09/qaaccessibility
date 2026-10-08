import { cleanAssistantMarkup, splitCodeFences } from "../ChatScreen";

describe("cleanAssistantMarkup — preserva underscores em URLs de markdown", () => {
  test("URL de download com underscore permanece intacta", () => {
    const md =
      "Baixar [checklist](http://127.0.0.1:8001/export/last_checklist_pdf) agora.";
    expect(cleanAssistantMarkup(md)).toContain("/export/last_checklist_pdf");
  });

  test("URL de ZIP com underscore permanece intacta", () => {
    const md = "[Download do arquivo corrigido (ZIP)](http://h/export/download_zip/x.zip)";
    expect(cleanAssistantMarkup(md)).toContain("/export/download_zip/x.zip");
  });

  test("ênfase markdown continua sendo limpa fora de URLs", () => {
    const md = "**Negrito** e _itálico_ [link](http://x/y_z)";
    const out = cleanAssistantMarkup(md);
    expect(out).toContain("Negrito");
    expect(out).toContain("itálico");
    expect(out).toContain("http://x/y_z");
  });

  test("múltiplas URLs com underscore são restauradas na ordem", () => {
    const md =
      "[a](http://x/a_b) e [c](http://y/c_d)";
    const out = cleanAssistantMarkup(md);
    expect(out).toContain("http://x/a_b");
    expect(out).toContain("http://y/c_d");
  });

  test("URLs com underscores no meio de texto longo continuam clicáveis", () => {
    const md =
      "Intro.\n\n📦 **[Baixar Checklist de Acessibilidade (PDF)](http://127.0.0.1:8001/export/last_checklist_pdf)**\n\nFim.";
    const out = cleanAssistantMarkup(md);
    expect(out).toContain("http://127.0.0.1:8001/export/last_checklist_pdf");
  });
});

describe("cleanAssistantMarkup — sublinhado no meio de palavra é nome, não ênfase", () => {
  it("mantém nomes de pasta, arquivo e identificador com sublinhado", () => {
    const out = cleanAssistantMarkup("O projeto está em C:\\Temp\\m3\\lojasol_local e o campo only_agents usa aria_label.");
    expect(out).toContain("lojasol_local");
    expect(out).toContain("only_agents");
    expect(out).toContain("aria_label");
  });

  it("continua removendo o sublinhado que é ênfase", () => {
    expect(cleanAssistantMarkup("isto é _importante_ e __muito__ sério")).toBe("isto é importante e muito sério");
  });
});


describe("splitCodeFences — código vai em bloco próprio e chega inteiro", () => {
  it("separa texto e código, mantendo as crases do próprio código", () => {
    const text = "Use assim:\n```tsx\nconst a = `x ${y}`;\n```\nPronto.";
    const parts = splitCodeFences(text);
    expect(parts.map((p) => p.kind)).toEqual(["text", "code", "text"]);
    expect(parts[1].lang).toBe("tsx");
    expect(parts[1].content).toBe("const a = `x ${y}`;");
  });

  it("trata um bloco ainda aberto (resposta chegando) como código", () => {
    const parts = splitCodeFences("Veja:\n```html\n<div>");
    expect(parts[1]).toEqual({ kind: "code", content: "<div>", lang: "html" });
  });

  it("sem cerca, devolve só texto", () => {
    expect(splitCodeFences("só texto")).toEqual([{ kind: "text", content: "só texto", lang: "" }]);
  });
});
