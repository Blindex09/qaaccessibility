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
  const APP = fs.readFileSync(path.join(RAIZ, "App.tsx"), "utf-8");

  test("existe UM skip link, renderizado pelo App", () => {
    // Eu adicionei um segundo no template do index.html achando que nao havia
    // nenhum -- meu grep procurou `class="skip-link"` no fonte e o do App usa
    // outra marcacao. O proprio pipeline pegou na rodada seguinte: "two skip
    // links with identical visible text".
    expect(APP).toMatch(/Pular para o conteúdo principal/);
    expect(TEMPLATE).not.toMatch(/<a[^>]*class="skip-link"/);
  });

  test("aponta para o conteudo principal, nao para o wrapper da pagina", () => {
    // O meu apontava para `#root`, que CONTEM o cabecalho -- pular para ele nao
    // pula nada. O do App aponta para o `role="main"`.
    expect(APP).toMatch(/href:\s*"#main-content"/);
    expect(APP).toMatch(/nativeID="main-content"/);
    expect(APP).toMatch(/role="main"/);
    expect(TEMPLATE).not.toMatch(/href="#root"/);
  });

  test("fica visivel ao receber foco", () => {
    expect(TEMPLATE).toMatch(/\.skip-link:focus\s*\{[^}]*top:\s*0/);
  });

  test("move o foco para o alvo ao ser ativado", () => {
    // Sem isso o link "funciona" sem levar o foco a lugar nenhum.
    expect(APP).toMatch(/getElementById\("main-content"\)/);
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

describe("WCAG 2.1.1 Keyboard -- botoes indisponiveis continuam alcancaveis", () => {
  test("o botao de enviar nao usa `disabled`", () => {
    // `disabled` no React Native Web tira do tab order: quem navega por teclado
    // nao encontra o botao nem descobre POR QUE esta indisponivel.
    const bloco = CHAT.slice(CHAT.indexOf("onPress={streaming ? stop : handleSend}"));
    const fim = bloco.indexOf("</TouchableOpacity>");
    expect(bloco.slice(0, fim)).not.toMatch(/\sdisabled=\{/);
  });

  test("usa accessibilityState.disabled (-> aria-disabled)", () => {
    expect(CHAT).toMatch(/accessibilityState=\{\{ disabled: naoPodeEnviar \}\}/);
  });

  test("o rotulo diz POR QUE esta indisponivel", () => {
    expect(CHAT).toMatch(/digite uma mensagem ou anexe um arquivo primeiro/);
  });

  test("o rotulo indisponivel ainda contem o texto visivel (2.5.3)", () => {
    // "Enviar mensagem — digite uma mensagem..." contem "Enviar mensagem".
    const m = CHAT.match(/"(Enviar mensagem — [^"]+)"/);
    expect(m).not.toBeNull();
    expect((m as RegExpMatchArray)[1]).toContain("Enviar mensagem");
  });

  test("o botao de anexar recebeu o mesmo tratamento", () => {
    expect(CHAT).toMatch(/accessibilityState=\{\{ disabled: streaming \}\}/);
    expect(CHAT).toMatch(/Anexar arquivos — indisponível enquanto/);
  });

  test("a condicao de envio e uma constante unica, nao repetida", () => {
    expect(CHAT).toMatch(/const naoPodeEnviar = /);
  });
});

describe("WCAG 4.1.3 Status Messages -- resposta anunciada ao final", () => {
  const HOOK = fs.readFileSync(path.join(RAIZ, "src", "hooks", "useChat.ts"), "utf-8");

  test("o balao da resposta NAO e live region", () => {
    // Ele cresce token a token; um aria-live ali falaria cada delta.
    expect(HOOK).toMatch(/balão da resposta NÃO é uma live region/);
  });

  test("a resposta pronta e anunciada, com o texto final", () => {
    // `event.final` so existe no evento `done` -- o anuncio acontece quando a
    // execucao termina, nunca durante o streaming.
    expect(HOOK).toMatch(/announce\(plainTextForAnnouncement\(event\.final\)/);
    expect(HOOK).toMatch(/case "done":/);
  });

  test("o markdown e limpo antes de ser falado", () => {
    // Sem isso o leitor de tela leria asteriscos, crases e URLs de link.
    expect(HOOK).toMatch(/function plainTextForAnnouncement/);
  });

  test("existe uma live region separada, polite", () => {
    expect(CHAT).toMatch(/accessibilityLiveRegion="polite"/);
    expect(CHAT).toMatch(/"aria-live": "polite"/);
  });
});
