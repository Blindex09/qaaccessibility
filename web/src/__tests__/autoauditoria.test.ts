/* eslint-env jest, node */
import fs from "fs";
import path from "path";

/**
 * Regressão dos achados que o PRÓPRIO pipeline do produto encontrou na própria
 * interface (2026-08-31), confirmados em duas execuções independentes.
 *
 * O Lighthouse dá 1.0 nesta interface e não pegou nenhum dos dois -- é a tese do
 * produto se aplicando a ele mesmo: scanner automático cobre 30-40%.
 */

const RAIZ = path.resolve(__dirname, "..", "..");
const TEMPLATE = fs.readFileSync(path.join(RAIZ, "web", "index.html"), "utf-8");
const CHAT = fs.readFileSync(path.join(RAIZ, "src", "screens", "ChatScreen.tsx"), "utf-8");

describe("WCAG 2.4.1 Bypass Blocks -- skip link", () => {
  test("o elemento existe, nao so o CSS", () => {
    // O CSS `.skip-link` existia ha tempos, mas nenhum ELEMENTO o usava: estilo
    // orfao. Sem link, nao havia como pular o cabecalho.
    expect(TEMPLATE).toMatch(/<a[^>]*class="skip-link"[^>]*>/);
  });

  test("aponta para o conteudo principal", () => {
    const m = TEMPLATE.match(/<a[^>]*class="skip-link"[^>]*href="([^"]+)"/);
    expect(m).not.toBeNull();
    const alvo = (m as RegExpMatchArray)[1].replace("#", "");
    expect(TEMPLATE).toMatch(new RegExp(`id="${alvo}"`));
  });

  test("o alvo pode receber foco", () => {
    // Sem tabindex="-1" o foco nao vai para o container ao seguir o link.
    expect(TEMPLATE).toMatch(/id="root"[^>]*tabindex="-1"/);
  });

  test("fica visivel ao receber foco", () => {
    expect(TEMPLATE).toMatch(/\.skip-link:focus\s*\{[^}]*top:\s*0/);
  });

  test("tem texto perceptivel", () => {
    const m = TEMPLATE.match(/<a[^>]*class="skip-link"[^>]*>([^<]+)<\/a>/);
    expect(m).not.toBeNull();
    expect((m as RegExpMatchArray)[1].trim().length).toBeGreaterThan(5);
  });
});

describe("WCAG 2.5.3 Label in Name -- campo de mensagem", () => {
  test("o nome acessivel e derivado do texto visivel", () => {
    // Antes eram tres strings soltas para o mesmo campo. Derivar de uma
    // constante unica impede que voltem a divergir.
    expect(CHAT).toMatch(/const PLACEHOLDER_MENSAGEM = /);
    expect(CHAT).toMatch(/const ROTULO_ACESSIVEL_MENSAGEM = .*PLACEHOLDER_MENSAGEM/);
  });

  test("o nome acessivel CONTEM o texto visivel", () => {
    const vis = CHAT.match(/const PLACEHOLDER_MENSAGEM = "([^"]+)"/);
    const rot = CHAT.match(/const ROTULO_ACESSIVEL_MENSAGEM = `([^`]+)`/);
    expect(vis).not.toBeNull();
    expect(rot).not.toBeNull();
    // o template usa a interpolacao, entao a constante aparece literalmente
    expect((rot as RegExpMatchArray)[1]).toContain("${PLACEHOLDER_MENSAGEM}");
  });

  test("o campo usa as constantes, nao strings soltas", () => {
    expect(CHAT).toMatch(/placeholder=\{PLACEHOLDER_MENSAGEM\}/);
    expect(CHAT).toMatch(/accessibilityLabel=\{ROTULO_ACESSIVEL_MENSAGEM\}/);
    expect(CHAT).not.toMatch(/accessibilityLabel="Mensagem para o assistente"/);
  });
});
