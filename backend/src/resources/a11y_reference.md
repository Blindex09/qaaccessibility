# Referência Autoritativa de Acessibilidade Digital (W3C APG, AccName, JSX-A11y, Documentos)

Este guia serve como base de conhecimento de altíssima fidelidade para os agentes de IA do projeto QA Accessibility. Ele compila especificações formais extraídas do W3C WAI-ARIA APG, cálculo do Accessible Name, regras de JSX-A11y e normas de acessibilidade de documentos (PDF/UA e Office).

---

## 1. Algoritmo de Cálculo do Nome Acessível (AccName)

O nome acessível (Accessible Name) é o texto associado a um elemento que as tecnologias assistivas (como leitores de tela) anunciam para descrevê-lo. A IA deve seguir esta ordem de prioridade estrita para calcular e verificar o nome acessível de um elemento:

1. **`aria-labelledby`**: Se presente e válido, aponta para os IDs dos elementos que contêm o texto do nome. Pode associar múltiplos elementos.
2. **`aria-label`**: Se presente, define diretamente a string de texto para o nome acessível, sobrescrevendo rótulos visuais ou nativos.
3. **Associação de Label Nativo**:
   - Elementos `<input>`, `<select>`, `<textarea>` associados a um `<label>` via atributo `for` correspondendo ao `id` do input.
   - Elemento contido implicitamente dentro de um `<label>`.
4. **Conteúdo do Elemento ou Atributo Substituto**:
   - Para links (`<a>`) e botões (`<button>`): O texto interno (text content).
   - Para imagens (`<img>`): O atributo `alt`.
   - Para ícones de fontes ou SVGs: Atributos `title` combinados com `role="img"`.
5. **Atributo `title`**: Utilizado como último recurso de fallback.
6. **Atributo `placeholder`**: Utilizado apenas como último recurso se nenhum outro nome acessível puder ser extraído. Nunca use placeholder como a única descrição de um formulário.

*Nota de Erro Comum:* Elementos decorativos (ex: ícones puramente visuais) devem ser ocultados do cálculo do nome acessível usando `aria-hidden="true"` e `focusable="false"` (para SVGs).

---

## 2. Padrões de Teclado e Estados W3C WAI-ARIA APG

Para componentes interativos personalizados (widgets), a IA deve validar se os papéis, estados (`aria-*`) e o foco do teclado cumprem as especificações do W3C:

### A. Modal / Diálogo (`role="dialog"`)
* **Papel & Nome:** Elemento com `role="dialog"` ou `role="alertdialog"` + `aria-modal="true"`. Deve ter `aria-labelledby` apontando para o título visível do modal.
* **Foco Inicial:** Ao abrir, o foco deve ser movido imediatamente para dentro do modal (primeiro elemento interativo ou título).
* **Foco de Retorno:** Ao fechar, o foco deve retornar obrigatoriamente para o botão que disparou o modal.
* **Focus Trap (Armadilha de Foco):** O foco deve ciclar apenas entre os elementos interativos do modal (usando Tab e Shift+Tab). O usuário não pode acessar elementos do plano de fundo.
* **Tecla de Escape:** Pressionar `Escape` deve fechar o modal imediatamente.
* **Inert:** Os elementos do plano de fundo devem ter o atributo `inert` ou `aria-hidden="true"` enquanto o modal estiver aberto.

### B. Abas (`role="tablist"`)
* **Estrutura:** Um container com `role="tablist"` contendo elementos com `role="tab"`. Cada aba controla um container com `role="tabpanel"`.
* **Relações ARIA:**
   - Cada `role="tab"` deve ter `aria-selected="true"` (para ativa) ou `aria-selected="false"` (para inativas).
   - Cada `role="tab"` deve ter `aria-controls` apontando para o `id` de seu respectivo `role="tabpanel"`.
   - Cada `role="tabpanel"` deve ter `aria-labelledby` apontando para o `id` da aba correspondente.
* **Comportamento do Teclado:**
   - O foco entra na aba ativa usando a tecla `Tab`.
   - As setas `Esquerda` e `Direita` (ou `Cima` e `Baixo` em listas verticais) mudam o foco entre as abas e as selecionam.
   - Pressionar `Tab` a partir da aba selecionada move o foco diretamente para dentro do painel ativo (`tabpanel`), pulando as abas inativas.

### C. Acordeão (Accordion)
* **Estrutura:** Um cabeçalho que contém um botão (`<button>`) acionador associado a um painel de conteúdo.
* **Atributos:**
   - O botão deve ter `aria-expanded="true"` (expandido) ou `aria-expanded="false"` (recolhido).
   - O botão deve ter `aria-controls` apontando para o `id` do painel associado.
   - O painel colapsado deve ser ocultado programaticamente usando `hidden` ou `display: none`.

### D. Caixa de Seleção / Combobox (`role="combobox"`)
* **Estrutura:** Um campo de texto `input` com `role="combobox"`, `aria-expanded="true|false"` e `aria-haspopup="listbox"`. Deve apontar via `aria-controls` para a lista de opções (`role="listbox"`).
* **Opções:** A lista contém nós filhos com `role="option"`. A opção ativa atual deve ser indicada no input usando `aria-activedescendant` apontando para o `id` da opção.
* **Teclado:** `Alt+Seta para Baixo` abre a lista, `Escape` fecha e limpa, setas `Cima`/`Baixo` navegam nas opções, `Enter` seleciona.

---

## 3. Diretrizes de Linter Estático (JSX-A11y)

Ao revisar código React, JSX ou componentes modernos, a IA deve inspecionar padrões que quebram as seguintes regras estáticas de acessibilidade:

* **`alt-text`**: Imagens (`<img>`, `<area>`, `<input type="image">`) precisam de um atributo `alt` definido. Imagens decorativas precisam de `alt=""`.
* **`anchor-has-content`**: Elementos de link (`<a>`) precisam de conteúdo de texto acessível (texto visível ou `aria-label`).
* **`click-events-have-key-events`**: Elementos que possuem eventos de clique (`onclick`/`onClick`) e não são semanticamente interativos (ex: `<div>`, `<span>`) precisam de tratamento de eventos de teclado equivalente (`onKeyDown`, `onKeyPress`) para responder a `Enter` e `Espaço`.
* **`no-noninteractive-element-interactions`**: Elementos não interativos (como `<li>`, `<div>`, `<h1>`, `<td>`) não devem possuir handlers de clique ou teclado a menos que recebam um papel semântico adequado (ex: `role="button"`).
* **`no-autofocus`**: O uso de `autofocus` é desencorajado por confundir leitores de tela e mudar o contexto sem aviso prévio ao usuário.

---

## 4. Normas de Acessibilidade em Documentos (PDF/UA e Office)

Ao auditar e revisar documentos (gerados ou recebidos), os agentes devem aplicar os critérios formais para PDF e Office (Word, Excel, PowerPoint):

### A. PDF Acessível (Norma ISO 14289 - PDF/UA)
* **Tagging (Marcação):** O documento precisa conter uma árvore estrutural de marcas (`/StructTreeRoot`). Todo elemento de texto deve estar associado a uma tag (como `H1`, `P`, `L`, `Table`).
* **Idioma Principal:** Deve possuir metadado declarando o idioma principal (ex: `pt-BR`) para calibração de sintetizadores de voz.
* **Ordem de Leitura:** A ordem lógica de leitura (definida pela árvore de tags) deve ser coerente com a leitura visual, mesmo em colunas múltiplas.
* **Metadados:** Título do documento deve estar configurado nos metadados principais e configurado para exibir o "Título" em vez do nome do arquivo nas barras de título dos visualizadores.

### B. Microsoft Word (DOCX)
* **Estilos de Cabeçalho:** Os títulos devem usar os Estilos de Título do Word (`Título 1` a `Título 6`) em sequência lógica. Nunca use texto simples em negrito/tamanho maior para simular títulos.
* **Texto Alternativo:** Todas as imagens devem possuir descrição alternativa significativa. Imagens decorativas devem ser marcadas como tal.
* **Tabelas:** Devem possuir a linha de cabeçalho explicitamente marcada nas propriedades da tabela ("Repetir como linha de cabeçalho em cada página").

### C. Microsoft Excel (XLSX)
* **Tabelas Nomeadas:** Intervalos de dados tabulares devem ser convertidos em tabelas de dados reais.
* **Células Mescladas:** Evite mesclar células em intervalos de dados. Células mescladas impedem a navegação correta de leitores de tela por coordenadas de colunas.
* **Rótulos de Planilhas:** As abas das planilhas devem possuir nomes descritivos exclusivos (evitar "Planilha1", "Planilha2").

---

## 5. Diretrizes de Frameworks Frontend (React, Vue, Angular, Svelte)

Ao tirar dúvidas ou analisar código de frameworks modernos, a IA deve aplicar os seguintes conhecimentos específicos dos subagentes:

### A. React & JSX
* **Eventos em Elementos Não Interativos:** `<div>`, `<span>`, `<li>` com `onClick` sem equivalência de teclado (`onKeyDown`/`onKeyUp`) e sem `role="button"` + `tabindex="0"`.
* **Chaves Instáveis em Listas:** Uso de índices de array (`key={index}`) em listas dinâmicas interativas causa perda de foco durante re-renderizações (violando WCAG 2.4.3).
* **Portais (React Portals):** Modais renderizados via portal (`ReactDOM.createPortal`) devem obrigatoriamente aplicar *Focus Trap* e manter o atributo `inert` nos contêineres raiz do plano de fundo.
* **Biblioteca recomendada (fonte oficial):** para widgets compostos (combobox, menu, listbox, dialog) construídos do zero, recomendar **React Aria Components** ([react-aria.adobe.com](https://react-aria.adobe.com)) em vez de reimplementar ARIA manualmente — headless, mantida pela Adobe, segue WAI-ARIA APG e já resolve foco/teclado/anúncio de leitor de tela. `eslint-plugin-jsx-a11y` continua sendo a ferramenta de lint estático de referência (já coberto na seção 3).

### B. Vue.js
* **Regiões Live Condicionais:** Uso de `v-if` em elementos com `aria-live`. Como o `v-if` remove o elemento do DOM quando falso, o leitor de tela falha em anunciar as mudanças. Deve-se preferir `v-show` (que aplica `display: none` mantendo o nó no DOM).

### C. Angular
* **Binding de Atributos ARIA:** Sintaxe incorreta `[aria-label]="var"` em vez de `[attr.aria-label]="var"`. O binding direto de propriedade falha ao renderizar o atributo no HTML final.
* **Biblioteca recomendada (fonte oficial):** o próprio time do Angular mantém o módulo **`@angular/cdk/a11y`** ([github.com/angular/components](https://github.com/angular/components/blob/main/src/cdk/a11y/a11y.md)) — `LiveAnnouncer` para anúncios programáticos em região `aria-live` (nível de urgência configurável, default `polite`), e a diretiva `cdkTrapFocus` para prender o foco em modais/diálogos. Sinalizar quando um projeto reimplementa foco de modal ou anúncio de leitor de tela na mão em vez de usar esse módulo já mantido oficialmente.

### D. Svelte (4 legado e 5 runes — 2026)
* **Tratamento de Teclado:** `on:click` (Svelte 4) ou `onclick` (Svelte 5 runes) em elementos não interativos sem equivalente de teclado (`on:keydown`/`onkeydown`) e sem `role="button"` + `tabindex="0"`.
* **Regiões Live Condicionais:** Bloco `{#if condition}` envolvendo elemento com `aria-live`/`role="status"` remove o nó do DOM quando falso — mesma falha do `v-if` do Vue. Preferir manter o container sempre montado, alternando só o texto.
* **Injeção de HTML Perigosa:** `{@html rawContent}` sem sanitização — equivalente ao `dangerouslySetInnerHTML`/`v-html`.
* **Composição de Snippets (Svelte 5):** `{#snippet}`/`{@render}` que renderiza elemento interativo sem repassar `aria-*`/`id`/`tabindex` recebidos no ponto de chamada — a reutilização do snippet pode perder silenciosamente o nome acessível já configurado.
* **Animações sem Preferência de Movimento:** Uso de transições Svelte (`transition:*`, `in:`/`out:`) sem alternativa em `@media (prefers-reduced-motion)`.

---

## 6. Diretrizes de CSS, Contraste Visual e APCA

* **WCAG 2.2 Contraste Mínimo (Critério 1.4.3):** Texto normal exige relação mínima de `4.5:1`; texto grande (18pt ou 14pt em negrito) exige no mínimo `3.0:1`.
* **Algoritmo APCA (Advanced Perceptual Contrast Algorithm):** Avalia a relação de contraste percebido com base na espessura e tamanho da fonte (Lc 60 para texto do corpo, Lc 45 para texto grande).
* **Indicadores Visuais de Foco (Critério 2.4.13 / 2.4.7):** Todo elemento focável deve ter um indicador visual claro com área mínima de 2px e contraste suficiente contra o fundo. Proibido remover outline (`outline: none` ou `outline: 0`) sem fornecer um estilo alternativo em `:focus` / `:focus-visible`.
* **Dimensão do Alvo de Toque (Critério 2.5.8):** O tamanho mínimo do alvo de toque deve ser de 24x24 pixels (ou espaçamento equivalente), recomendando-se 44x44 pixels para mobile.

---

## 7. Padrões de Automação de Testes de Acessibilidade (Cypress, Postman e Selenium)

Ao tirar dúvidas ou gerar scripts de teste de acessibilidade automatizados, a IA deve aplicar os conhecimentos atualizados das plataformas de QA:

### A. Cypress (`cypress-axe`)
* **Comandos Principais:** `cy.injectAxe()` (injeta o motor axe-core após `cy.visit()`) e `cy.checkA11y()` (executa a varredura).
* **Escopo de Análise:** Recomendado limitar a busca a contêineres específicos para evitar ruído e acelerar os testes (ex.: `cy.checkA11y('#modal-root')` ou `cy.checkA11y('[data-cy="form-checkout"]')`).
* **Filtragem por Severidade:** Configurar `includedImpacts` para falhar o pipeline apenas em violações de alto impacto inicial (ex.: `['critical', 'serious']`).
* **Estrutura Recomendada:** Importar `'cypress-axe'` no arquivo `cypress/support/e2e.js`.

### B. Postman / Newman (Testes de Contrato de API)
* **Validação de Atributos de Acessibilidade:** Testar se os endpoints REST devolvem campos essenciais como `alt_text`, `aria_label` e `description` preenchidos e não nulos.
* **Asserções em Scripts de Teste:**
  ```javascript
  pm.test("Score de Acessibilidade >= 80", function () {
      var jsonData = pm.response.json();
      pm.expect(jsonData.score).to.be.at.least(80);
  });
  pm.test("Sem violações críticas", function () {
      var jsonData = pm.response.json();
      pm.expect(jsonData.issues_by_severity.critical || 0).to.eql(0);
  });
  ```
* **Execução via CLI (Newman):** Automação em CI/CD via comando `newman run collection.json --reporters cli,html`.

### C. Selenium (`axe-selenium-python` / Java)
* **Injeção do Motor Axe:** Utilizar `axe = Axe(driver)` e `axe.inject()` para carregar o motor `axe-core` na sessão do navegador.
* **Varredura e Asserção:** Executar `results = axe.run()` e validar `assert len(results['violations']) == 0, axe.report(results['violations'])`.
* **Tratamento de Elementos Dinâmicos:** Forçar a abertura de modais ou menus colapsados antes de invocar `axe.run()`, pois elementos ocultos (`display: none` ou `inert`) não são escaneados automaticamente.

---

## 8. Internacionalização (i18n) e Texto Bidirecional (RTL) — 2026

* **`dir` no `<html>`:** Idiomas RTL (árabe, hebraico, persa, urdu) exigem `dir="rtl"` no `<html>` — leitores de tela e a ordem de seleção/busca do navegador seguem o atributo `dir`, nunca só o CSS `direction`.
* **`lang` em sub-regiões (WCAG 3.1.2):** Trecho em idioma diferente do declarado na página precisa de `lang` próprio no elemento que o envolve, senão o motor de fala pronuncia errado.
* **`<bdi>`/`<bdo>`:** Texto gerado pelo usuário ou de idioma misto (nome próprio, busca) sem `<bdi>` pode embaralhar visualmente a pontuação ao redor quando RTL e LTR se encontram. `<bdo>` força ordem visual e deve ser raro — o leitor de tela lê literalmente essa ordem forçada.
* **Propriedades CSS lógicas vs físicas (WCAG 1.3.2):** `margin-left`/`padding-right`/`left`/`text-align: left` NÃO se invertem sob `dir="rtl"`. Preferir `margin-inline-start/end`, `padding-inline-start/end`, `inset-inline-start/end`, `text-align: start/end` — essas se ajustam automaticamente com `dir` e `writing-mode`.

---

## 9. Data Grids Virtualizados e Editores de Texto Colaborativos

### A. Data Grid / TreeGrid Virtualizado
* **Índices Dinâmicos:** Grids que montam/desmontam linhas ao rolar (virtualização) precisam atualizar `aria-rowindex`/`aria-colindex`/`aria-rowcount`/`aria-colcount` com a posição ABSOLUTA no dataset — senão o leitor de tela anuncia a posição relativa da janela visível ("linha 3 de 20") em vez da real ("linha 340 de 50.000").
* **Foco:** Roving `tabindex` (célula ativa `tabindex="0"`, resto `-1"`) é o padrão-ouro; `aria-activedescendant` (foco real no container) também é válido, especialmente em grids muito virtualizados. Falta de ambos é o problema.
* **Seleção Múltipla:** `aria-multiselectable="true"` + `aria-selected` nas células selecionadas, com uma região de resumo ("Selecionadas 40 células de A1 a D10") para não sobrecarregar o leitor de tela célula por célula.

### B. Editor de Texto Colaborativo (WAI-ARIA 1.3)
* **Papéis de Controle de Alterações:** `role="suggestion"` (contêiner), `role="insertion"` (texto adicionado), `role="deletion"` (texto removido), `role="comment"` (com `aria-details` apontando para o comentário), `role="mark"` (destaque). Estilo visual (cor, tachado) sem esses papéis é invisível para leitor de tela.
* **Anúncios de Co-autoria:** Presença/atividade em tempo real deve ser anunciada em eventos macro ("Alice entrou", "Bob comentou"), nunca caractere por caractere.

---

## 10. Guia de Teste com Leitor de Tela por Navegador e Dispositivo (2026)

Cada combinação de leitor de tela + navegador interpreta ARIA/HTML de forma diferente — o mesmo componente pode funcionar perfeitamente num par e falhar silenciosamente noutro. Antes de dar instruções de teste, a IA deve saber (perguntar se não souber): sistema operacional, se é desktop ou mobile, navegador e leitor de tela.

| Ambiente | Leitor de tela recomendado | Navegador obrigatório/recomendado | Atalho para ligar |
|---|---|---|---|
| Windows desktop (gratuito) | NVDA | Firefox (combinação mais completa) ou Chrome | `Ctrl+Alt+N` (se configurado) ou atalho do instalador |
| Windows desktop (enterprise) | JAWS | Chrome ou Edge (padrão de mercado); também funciona com Firefox | Atalho do JAWS no desktop |
| Windows desktop (built-in, sem instalar nada) | Narrator | Edge | `Ctrl+Win+Enter` |
| macOS desktop | VoiceOver | **Safari obrigatório** — é o único navegador que expõe a API de acessibilidade do macOS por completo ao VoiceOver | `Cmd+F5` |
| iOS (iPhone/iPad) | VoiceOver | Safari | Ajustes > Acessibilidade > VoiceOver, ou pedir ao Siri |
| Android | TalkBack | Chrome | Ajustes > Acessibilidade > TalkBack |

Regras práticas para a IA usar ao orientar um teste:
* Nunca dar instrução genérica de "ative o leitor de tela do seu computador" quando o combo puder ser identificado — cada combo tem atalho e comportamento próprios.
* VoiceOver + Chrome/Firefox no macOS não é uma combinação confiável — sempre indicar Safari.
* NVDA e JAWS interpretam alguns padrões ARIA de forma diferente (ex.: `aria-activedescendant`, `role="application"`) — um problema real pode aparecer só em um dos dois.
* Se o usuário não disser o ambiente, perguntar antes de dar o passo a passo: sistema operacional, navegador, e se já tem um leitor de tela específico em mente.

---

## 11. Onde ARIA se Encaixa (e Onde Não Se Encaixa)

* **Regra de ouro — semântica nativa primeiro:** prefira `<button>`, `<a href>`, `<input>`, `<dialog>`, `<nav>` e `<main>` a qualquer recriação com `<div>`/`<span>` + ARIA. ARIA só entra para preencher uma LACUNA semântica real que o HTML nativo não cobre (ex.: um `tablist` customizado, um `combobox` com sugestões). Se existe elemento nativo equivalente, usar ARIA por cima dele é redundante na melhor hipótese e quebra o comportamento nativo (foco, teclado, formulário) na pior.
* **ARIA é uma promessa comportamental, não decoração:** cada `role` assumido implica manter os atributos obrigatórios daquele papel, o comportamento de teclado esperado (setas, Home/End, Escape conforme o padrão APG da seção 2) e a saída correta no leitor de tela. Declarar `role="tablist"` sem implementar navegação por setas é pior do que não declarar nada — o usuário de leitor de tela espera o padrão e não o recebe.
* **Remediação remove ARIA incorreta, não empilha mais ARIA por cima:** quando um componente já tem marcação ARIA errada ou redundante, a correção certa é limpar/corrigir essa marcação — nunca adicionar uma segunda camada de ARIA tentando compensar a primeira.
* **Nunca expor o mesmo significado duas vezes:** não duplicar o mesmo texto/instrução/status simultaneamente como texto visível E `aria-label` diferente, como região `aria-live` duplicada, ou como DOM espelhado (a mesma informação renderizada duas vezes para "garantir" que o leitor de tela pegue). Isso não reforça a acessibilidade — cria ruído e, em vários leitores de tela, faz o conteúdo ser anunciado duas vezes.
* **Itens repetidos (atalhos, opções relacionadas, passos, resultados) são listas, não parágrafos:** quando um conjunto de ações/opções/passos forma um grupo de itens repetidos, cada um vira um item de lista semântica (`<ul>/<ol>` + `<li>`) com um único controle focável nativo por ação — nunca concatenados num parágrafo separados por vírgula/espaço/`<br>`, e nunca usando ARIA como substituto de `<ul>`/`<li>` reais.
* **Anúncios ao vivo (`aria-live`) com moderação:** uma interface que muda visualmente não precisa necessariamente de fala. Evitar anunciar por token/por progresso (ex.: uma resposta de chat crescendo caractere a caractere) — isso satura o leitor de tela. Preferir anúncios pontuais e delimitados (início/fim de uma ação), com controle do usuário quando possível.
* **Rascunho de especificação não é norma estável:** WCAG 3.0 (ainda em Working Draft), WAI-ARIA 1.3 (Working Draft) e APIs HTML/CSS experimentais devem ser tratados como pesquisa, nunca apresentados como requisito normativo de produção. Sempre rotular claramente quando uma recomendação vem de material em rascunho.

### Árvore de Decisão — Qual Componente Usar

```text
Precisa de uma interação?
├── Existe elemento HTML/nativo da plataforma que já expressa isso? → use-o diretamente, sem ARIA
├── É modal/bloqueante? → <dialog> nativo (ou modal nativo da plataforma) + foco inicial + contenção de foco + retorno de foco ao fechar
├── É mostrar/esconder conteúdo? → <details>/<summary>, ou botão com aria-expanded + aria-controls
├── É selecionar um valor entre opções? → <select>/radio nativos primeiro; listbox customizado só se o nativo genuinamente não suportar o caso
├── É um menu de ações estilo aplicativo? → padrão APG de menu, só para comandos (não para navegação comum)
├── São abas? → tablist/tab/tabpanel com navegação por setas documentada (ver seção 2.B)
└── É um widget composto sem equivalente acima? → seguir o padrão APG/da plataforma específico e testar com leitor de tela real
```

Nem todo bloco visualmente separado precisa de landmark ou heading — landmarks/headings representam estrutura real do documento; texto de status operacional (ex.: progresso de uma ferramenta de IA rodando) é texto comum, não uma região.

---

## 12. Árvore de Decisão Oficial para Texto Alternativo de Imagens (W3C WAI)

Fonte primária: [W3C WAI — An alt Decision Tree](https://www.w3.org/WAI/tutorials/images/decision-tree/) e [W3C WAI — Images Tutorial](https://www.w3.org/WAI/tutorials/images/). A categoria certa muda o `alt` certo — a IA deve identificar a categoria ANTES de sugerir o texto, nunca escrever um `alt` genérico sem passar por essa árvore.

### Sequência oficial de decisão

1. **A imagem contém texto?**
   - Texto duplicado em outro lugar da página → `alt=""` (vazio). Categoria: **Decorativa**.
   - Texto puramente estético/estilístico → `alt=""`. Categoria: **Decorativa**.
   - O texto funciona como ícone/ação (ex.: botão com a palavra "Buscar" desenhada como imagem) → `alt` descreve a FUNÇÃO, não o texto literal. Categoria: **Funcional**.
   - Texto que não aparece em nenhum outro lugar da página → `alt` deve conter o texto literal da imagem. Categoria: **Imagem de Texto** (ver também seção 1.4.5 — evitar sempre que der pra usar texto real em HTML).

2. **A imagem está dentro de um link/botão que ficaria confuso sem ela?**
   - Sim → `alt` descreve o DESTINO do link ou a AÇÃO do botão (não a aparência visual da imagem). Categoria: **Funcional**. Ex.: um ícone de lupa dentro de `<button>` vira `alt="Buscar"`, nunca `alt="ícone de lupa"`.
   - Não → segue pro passo 3.

3. **A imagem agrega significado ao conteúdo/contexto da página?**
   - Foto/gráfico simples → descrição breve que transmite o SIGNIFICADO relevante ao contexto (não uma descrição exaustiva de tudo que aparece visualmente). Categoria: **Informativa**.
   - Gráfico, diagrama, mapa ou infográfico com informação complexa → `alt` curto resume o propósito geral, e a informação detalhada completa vai em texto próximo na página (ou `aria-describedby` apontando pra ela) — nunca tentar enfiar tudo num `alt` só. Categoria: **Complexa**.
   - Redundante com texto já visível ao lado da imagem → `alt=""`. Categoria: **Funcional (redundante)**.

4. **A imagem é puramente decorativa** (não passa em nenhum dos critérios acima)?
   - Sim → `alt=""` (nunca omitir o atributo `alt` inteiramente — omitir faz alguns leitores de tela lerem o nome do arquivo).

### Categorias adicionais (fora da sequência principal, mas oficiais)

- **Grupo de imagens**: quando várias imagens juntas formam uma única informação (ex.: estrelas de avaliação, bandeira + nome do país repetido), só UMA delas recebe o `alt` descritivo do conjunto; as demais do grupo recebem `alt=""` — evita repetição no leitor de tela.
- **Mapa de imagem (`<map>`/`<area>`)**: cada `<area>` precisa do próprio `alt` descrevendo o destino daquela região específica, igual a um link individual — a imagem-mãe (`<img usemap>`) normalmente leva `alt=""` quando as áreas já cobrem toda a informação.

### Erros comuns que a IA deve sinalizar (todos observados na prática)

- `alt="imagem.jpg"`, `alt="foto"`, `alt="icon"` — nome de arquivo ou texto genérico no lugar de descrição real.
- `alt` descrevendo a APARÊNCIA da imagem em vez do PROPÓSITO/FUNÇÃO (comum em botões-ícone: `alt="lápis"` em vez de `alt="Editar"`).
- Imagem complexa (gráfico/mapa) com `alt` tentando descrever cada detalhe numa frase só, em vez de resumir e apontar pra informação completa em texto normal.
- `role="presentation"` ou `aria-hidden="true"` num `<img>` que na verdade é informativo (esconde informação real do leitor de tela).
- Emoji ou caractere decorativo solto no meio de texto sem `aria-hidden="true"`, fazendo o leitor de tela verbalizar o nome do emoji no meio da frase.

---

## 13. Acessibilidade Mobile Nativa (iOS/Android) — conhecimento de referência para o chat

Os agentes especialistas (`mobile_a11y`, etc.) analisam **HTML/CSS de páginas web abertas em navegador mobile** — não código nativo iOS/Android compilado. Esta seção existe para o chat conseguir explicar corretamente regras de apps nativos quando o usuário perguntar, mesmo sem poder rodar um teste automatizado sobre elas. Fontes: Apple Human Interface Guidelines (Accessibility), Android Developers (Accessibility), Material Design Accessibility.

### Tamanho de alvo de toque por plataforma (não confundir os três)

| Plataforma | Mínimo | Fonte |
|---|---|---|
| Web (CSS) | **24×24 CSS px** (WCAG 2.2 AA, SC 2.5.8) — círculo de 24px sem interseção se o alvo visual for menor | W3C |
| iOS (UIKit/SwiftUI) | **44×44 pt** | Apple HIG |
| Android (Compose/Views) | **48×48 dp** | Material Design |

Nunca apresentar 44 CSS px como "o mínimo do WCAG 2.2 AA" — o mínimo normativo AA na web é 24×24; 44×44 é a recomendação nativa da Apple (e frequentemente citada como boa prática web também, mas não é o SC 2.5.8).

### iOS — VoiceOver

- Ativar: Ajustes → Acessibilidade → VoiceOver, ou triplo-clique no botão lateral.
- Navegação: deslizar direita/esquerda move entre elementos; toque duplo ativa; deslizar com três dedos rola.
- Rotor: menu giratório (girar dois dedos na tela) para saltar por cabeçalhos, links, landmarks, campos de formulário.
- SwiftUI: `.accessibilityElement(children: .combine/.ignore/.contain)`, `.accessibilityAddTraits(.isButton/.isHeader/.isModal)`, `.accessibilityRepresentation` (mapeia um controle visual customizado para um controle nativo equivalente, ex. um "knob" customizado vira `Slider` para o VoiceOver), `@ScaledMetric` (escala dimensões de layout junto com Dynamic Type, evitando clipping de texto grande).
- UIKit: `isAccessibilityElement`, `accessibilityLabel`, `accessibilityTraits`, `accessibilityCustomActions`; anúncios via `UIAccessibility.post(notification: .announcement, argument:)` — só para eventos importantes e delimitados, nunca duplicando o que o controle nativo já fala sozinho.

### Android — TalkBack

- Ativar: Configurações → Acessibilidade → TalkBack.
- Navegação: deslizar direita/esquerda; toque duplo ativa.
- Jetpack Compose: TalkBack/Switch Access inspecionam a **Semantics Tree**, não a árvore visual. `Modifier.semantics { ... }` define `contentDescription`, `role`, `stateDescription`, `liveRegion`; `mergeDescendants = true` agrupa nós filhos (ícone + título + subtítulo) num único alvo de toque para o TalkBack; `customActions` fornece alternativa sem arraste (satisfaz o equivalente de WCAG 2.5.7 no mundo nativo).
- Views legadas (XML): `AccessibilityNodeInfoCompat` / `AccessibilityDelegateCompat` para ações customizadas, descrições de nó, `setAccessibilityLiveRegion`.

### O que NÃO fazer (erros comuns cross-platform)

- Confundir o mínimo de toque web (24px) com o nativo (44pt/48dp) ao dar recomendação — são padrões de plataformas diferentes.
- Recomendar `aria-grabbed`/`aria-dropeffect` para padrões de arraste — deprecados; a alternativa correta é um controle real sem arraste (botão mover/menu de posição), tanto na web (WCAG 2.5.7) quanto o equivalente nativo (`customActions` no Compose, ações customizadas no UIKit).
- Tratar app nativo como auditável pelas mesmas ferramentas de HTML deste produto — para apps nativos, a auditoria real precisa do dispositivo/simulador com VoiceOver/TalkBack ligado; o chat pode explicar a regra, mas não pode rodar a análise automatizada sobre o binário do app.

---

## 14. Benchmark WebAIM Million e Priorização de Achados — referência para o chat

Fonte: WebAIM Million 2026 (análise de fevereiro/2026 do 1 milhão de home pages mais acessadas). Usar estes números quando o usuário pedir contexto/comparação ("isso é normal?", "quão grave é isso comparado com outros sites?") ou ajuda pra priorizar o backlog — nunca apresentar como número exato do site do usuário, é um benchmark de mercado.

### Números de referência (não confundir com resultado da análise atual)
- Média de **56,1 erros detectáveis por página** no mercado em geral (site específico do usuário pode ter mais ou menos).
- **95,9%** das home pages têm alguma falha WCAG 2 A/AA detectável — a não-conformidade real é maior porque ferramentas automáticas pegam só ~30–40% dos problemas (por isso este produto combina execução determinística de regras + LLM especialista, não só regex).
- **Os mesmos 6 tipos de erro somam ~96% de todas as falhas detectadas, há 7 anos seguidos**: contraste baixo (83,9% das páginas), `alt` ausente (>50%), campo de formulário sem label (33,1%), links vazios, botões vazios, `<html lang>` ausente. Esses são o "quick-win sweep" — corrigir só esses 6 já resolve a maioria do volume de erros de qualquer site.
- **ARIA em excesso correlaciona com MAIS erros, não menos**: páginas que usam ARIA têm em média 59,1 erros vs 42 sem ARIA (+40%). Reforça a Regra nº1 de ARIA (seção 12 acima): preferir HTML nativo, e nunca sugerir adicionar ARIA como resposta padrão a um problema.

### Rubrica de priorização (usar ao ajudar o usuário a montar backlog/sprint)
Pontuar cada achado de 1 (baixo) a 4 (alto) em 5 dimensões: impacto no usuário, frequência (% de usuários afetados), impacto no negócio/qualidade, esforço pra corrigir (invertido: <1 dia = 4, >7 dias = 1), risco de regressão (invertido: isolado = 4, alto risco = 1). Somar os 5:
- **17–20 → P0/Crítico**: hotfix, corrigir o quanto antes.
- **12–16 → P1/Alto**: próxima sprint.
- **7–11 → P2/Médio**: limpeza programada.
- **≤6 → P3/Baixo**: backlog.

Isso é uma ferramenta de conversa/priorização — não substitui a severidade técnica (`critical/high/medium/low`) que os agentes já atribuem a cada issue com base no critério WCAG e no impacto de acessibilidade em si.
