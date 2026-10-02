import { cleanAssistantMarkup } from "../ChatScreen";

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