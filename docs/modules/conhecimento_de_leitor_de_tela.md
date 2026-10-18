# Conhecimento de leitor de tela: o que fala e faz cada elemento e comportamento

Este módulo dá ao chat e aos agentes de análise uma base pesquisada em documentação oficial sobre o que a pessoa que usa leitor de tela percebe em cada elemento HTML, em cada padrão ARIA, em conteúdo dinâmico (AJAX, JavaScript, React, Astro) e em efeitos de CSS, tanto quando o elemento é acessível quanto quando não é. O objetivo é acertar nos testes e nas informações, sem teste verde como prova e sem afirmar fala exata que a fonte não sustenta.

## O que existia antes

- O especialista de leitor de tela tinha uma lista de padrões a detectar, e o chat tinha um guia de teste por navegador e dispositivo, o algoritmo de nome acessível e o guia de nome para imagens. Não havia, por elemento, o que cada leitor expõe e fala, nem a diferença entre o que a especificação define e o que cada leitor faz.
- O repositório mcp do dono traz um guia de NVDA com anúncios comuns. Foi usado como roteiro de conferência, não como fonte: cada afirmação aqui foi conferida na documentação.

## O que foi entregue

Cinco referências sobre leitor de tela em backend/src/resources (a quinta, de ações, teclas e eventos, veio na segunda rodada; a terceira rodada acrescentou mais três, de frameworks, mobile e documentos, e cognitivo e conformidade), todas no índice de busca do chat:

- leitor_de_tela_elementos_html.md: 14 famílias de elementos HTML (títulos e listas, links e botões, formulários, tabelas, imagens, pontos de referência, divulgação e diálogo, progresso, texto em linha, mídia e conteúdo incorporado, elementos sem interface), com os resultados de NVDA, JAWS, VoiceOver no macOS e no iOS, TalkBack e Narrator e as lacunas de cada um.
- leitor_de_tela_aria_e_padroes.md: princípios de ARIA (nome acessível em ordem, papéis que não aceitam nome, atributos por papel, aria-hidden contra inert, presentation, modo de aplicativo) e os padrões do guia APG da W3C com teclado, papéis, estados e o que a pessoa vive quando falta (diálogo, abas, acordeão e divulgação, navegação por divulgação, menu de aplicativo, combobox, listbox, tooltip, alert, status, log, estados de formulário, botão, link, checkbox, rádio, switch, slider, toolbar, carrossel, breadcrumb, pontos de referência, tabela, grade e árvore).
- leitor_de_tela_dinamico_js_react.md: regiões vivas, foco, tabindex, inert, dialog nativo, Popover API, mudança de contexto (3.2.2), atualização automática (2.2.2), validação de formulários, React (JSX, Fragment, useId, refs, padrões de clique fora), roteamento no Astro (ClientRouter) e no Next.js (anunciador de rota).
- leitor_de_tela_css_e_modos.md: esconder conteúdo (display none, sr-only, clip, opacity, aria-hidden), conteúdo gerado, ordem visual contra ordem de leitura, foco visível, cores forçadas, movimento reduzido, espaçamento de texto e contraste, e os modos e teclas de NVDA, JAWS, VoiceOver, TalkBack e Narrator, com os dados de uso da pesquisa de usuários da WebAIM.

Mais um bloco curto (backend/src/shared/screen_reader_calibration.py) com as regras que mudam como um achado é julgado e redigido, ligado ao chat e a cinco agentes: leitor de tela, ARIA, formulários, conteúdo dinâmico e revisor. As referências completas ficam no índice do chat, para não encarecer cada chamada de agente.

## Fontes consultadas em 2026-10-17

TetraLogical (matriz de suporte de HTML: NVDA, JAWS, VoiceOver Mac e iOS, TalkBack, Narrator); W3C: HTML-AAM, Accessible Name 1.2, WAI-ARIA 1.2, APG (diálogo, alertdialog, abas, acordeão, divulgação e navegação por divulgação, menu e menubar, botão de menu, combobox, listbox, tooltip, breadcrumb, carrossel, grade, árvore, tabela, toolbar, checkbox, rádio, slider, switch, botão, link, pontos de referência, alerta), páginas de entendimento do WCAG 2.2 (1.3.1, 1.3.5, 2.2.2, 2.4.7, 2.4.13, 3.1.1, 3.2.2, 4.1.2, 4.1.3), tutoriais da WAI (tabelas, títulos, menus, imagens, formulários); MDN (papéis alert, status, log e presentation e application; aria-hidden, aria-describedby, aria-invalid, aria-errormessage, aria-current, aria-busy, regiões vivas; tabindex, inert, dialog, Popover API; CSS e JavaScript; content, prefers-reduced-motion, forced-colors, :focus-visible; widgets navegáveis por teclado); WebAIM (conteúdo invisível, JAWS, NVDA, VoiceOver, pesquisa de usuários edição 10); guia do usuário do NVDA; ajuda do TalkBack; React (acessibilidade, useId); Astro (view transitions); Next.js (acessibilidade).

## O que o módulo entrega e qual teste cobre cada promessa

Todos em tests/backend/unit/shared/test_leitor_de_tela_conhecimento.py.

- Cada referência declara fontes e data, está no índice do chat e é dividida em trechos de tamanho limitado: TestSourcesAndCorpus.
- Cobertura por família de elemento HTML, com leitores e versões nomeadas e o aviso de que a fala varia: TestHtmlElementsCoverage.
- Cobertura dos padrões ARIA, de navegação por divulgação contra menu, e do que as fontes dizem e não dizem sobre tabindex e retorno do foco no dialog: TestAriaPatternsCoverage.
- Cobertura de região viva, foco, validação, React e Astro, e rótulo das afirmações não confirmadas: TestDynamicAndFrameworkCoverage.
- Cobertura de CSS e dos modos e teclas de cada leitor: TestCssAndReaderModes.
- Bloco curto coerente com as referências, entregue aos agentes e ao chat: TestCompactBlockAndWiring.
- Correções que a pesquisa exigiu: TestCorrectionsFoundByTheResearch.

## Correções que a pesquisa exigiu

- O especialista de leitor de tela afirmava que região viva "remove a semântica" de botões e que ações em avisos "nunca" devem usar aria-live. A fonte diz que o anúncio é texto simples, pode não transmitir o papel, e que o alert não toma o foco. Reescrito como risco, com a alternativa.
- Exigia mover o foco para um h1 com tabindex -1 após troca de rota. Roteadores como o ClientRouter do Astro e o do Next.js já anunciam a página; passou a julgar o resultado e a não exigir os dois mecanismos.
- Tratava a falta de h1, mais de um h1 e nível de título pulado como falha de critério e trazia isso como exemplo de achado com alta confiança. A W3C apresenta o nível pulado como orientação. Passou a recomendação, sem critério falho, e o exemplo virou botão sem nome (4.1.2).
- Dizia que imagem sem alt sempre fala o nome do arquivo e que todo SVG decorativo é anunciado. Cada leitor se comporta de um jeito (VoiceOver lê o nome do arquivo, JAWS diz "sem rótulo", TalkBack diz que não está rotulada) e muitos ignoram SVG sem nome. Reescrito por leitor.
- Dava 100 a 500 ms como regra de espera após AJAX. Não há número documentado; ficou como solução comum.

## Segunda rodada: ações, teclas, eventos e mudanças de estado (2026-10-17)

A pedido do dono, uma nova varredura procurou o que ainda faltava: como o leitor age em cada ação e tecla, em cada menu, lista suspensa e acordeão, o que fala, e como isso se liga a eventos de JavaScript, AJAX, conteúdo dinâmico, React e CSS. O que faltava e foi acrescentado:

- Nova referência leitor_de_tela_acoes_teclas_e_eventos.md: quando cada leitor troca de modo (NVDA conferido no código-fonte do repositório nvaccess/nvda, com a lista exata de papéis que ligam o modo de foco e dos que não ligam; JAWS, Narrator, VoiceOver e TalkBack pelos guias disponíveis), como a ativação chega à página (a tecla de ativar em modo de navegação gera click; elemento com click é "clicável" mas não é botão), o que é anunciado quando um estado muda (expectativas por recurso do projeto Accessibility Support, ARIA a ARIA), menu, lista suspensa nativa e personalizada, combobox, acordeão, abas e diálogo, atributos HTML (required, disabled, readonly, maxlength, min, max, list, scope, headers, title, lang, inert), AJAX (padrão feed, mensagens de status, aria-busy) e os critérios 2.1.1, 2.2.2, 2.4.3, 3.2.1, 3.2.2 e 1.4.13.
- Acréscimos às referências existentes: React (rótulos e campos controlados, documentação oficial do React Router), CSS (display contents, tabelas com display alterado, content-visibility, scroll-padding para o 2.4.11) e SVG em linha.
- Correção de prompts: aria-controls é opcional na divulgação do APG e a maioria dos leitores não o anuncia, então os especialistas de widgets, ARIA e componentes passaram a tratá-lo como recomendação, e os valores novos de aria-haspopup (dialog, grid, listbox, tree), mal suportados, ganharam o aviso de que podem ser falados como menu. O combobox exige aria-controls só enquanto o popup está visível.
- O bloco curto dos agentes ganhou as regras de ativação e os alertas de suporte.

Testes: TestActionsKeysAndEvents e TestAriaControlsIsNotATreatedAsMandatory, no mesmo arquivo de testes. A suíte unitária inteira passou: 2144 testes.

Fontes que não puderam ser lidas nesta rodada: o guia de teclas do JAWS (Freedom Scientific, acesso negado), a página de gestos do VoiceOver no iPhone e o artigo da Vispero sobre eventos no JAWS e no NVDA (as páginas não trouxeram o conteúdo), e a especificação WAI-ARIA 1.2 completa. Os dados do projeto Accessibility Support são expectativas revisadas pela comunidade, de datas variadas (a maioria de 2019 a 2023), e não medições de uma versão de leitor.

## Terceira rodada: frameworks, mobile, documentos, cognitivo, conformidade e conhecimento por especialista (2026-10-17)

A pedido do dono, uma pesquisa exaustiva para que tanto o chat quanto cada especialista tenham o conhecimento. Duas frentes.

Novas referências, todas no índice do chat (três, que somam oito com as anteriores):

- acessibilidade_frameworks_e_componentes.md: guias oficiais do Vue (rota, formulários, ids com useId, RouterLink que já aplica aria-current), do Angular (elementos nativos, as duas formas de ligar ARIA, CDK, rota, @defer), todos os avisos de acessibilidade do compilador do Svelte, Tailwind (sr-only, variantes, outline-hidden, anéis que somem em cores forçadas, forced-color-adjust) e Web Components (ElementInternals, delegatesFocus, referências por id que não atravessam o shadow DOM, Reference Target).
- acessibilidade_mobile_documentos_e_midia.md: rascunho móvel da W3C e os critérios 1.3.4, 1.4.4, 1.4.10, 2.5.1, 2.5.4, 2.5.7 e 2.5.8, princípios do Android, Word, Excel e PowerPoint da Microsoft, técnicas de PDF do WCAG, Protocolo Matterhorn, PDF/UA-1 e 2, EPUB Accessibility 1.1 e legendas (1.2.2).
- acessibilidade_cognitiva_conformidade_e_metodologia.md: modelo de conformidade e lista dos 31 critérios A e 24 AA do WCAG 2.2, critérios de erro, rótulo, entrada redundante, autenticação, ajuda e tempo, COGA, Revised 508 Standards (lido no site do Access Board), EN 301 549 V3.2.1 (lida no texto da norma, cláusulas 4 a 12), Lei Europeia de Acessibilidade (sem texto oficial lido), VPAT, WCAG-EM, ACT e cobertura da automação.

Conhecimento por especialista (backend/src/shared/specialist_knowledge.py): cada um dos 28 especialistas de análise recebe, no prompt, as seções do seu próprio domínio, com um teto de caracteres por especialista (de 4.000 a 8.000). Exemplos: leitor de tela recebe elementos HTML por leitor; formulários recebe campos, estado de formulário e validação; widgets recebe diálogo, abas, acordeão, menu e combobox; mobile recebe mobile; PDF recebe PDF; cognitivo e compreensão recebem erro, rótulo, autenticação, ajuda e tempo; Seção 508 e auditoria de conformidade recebem a base legal; cada framework recebe a própria seção. Custo medido: cerca de 126 mil caracteres somados se os 28 rodarem; o orquestrador só chama os que têm evidência no HTML, então uma análise comum paga uma fração disso. Os 28 estão em SLICES; um teste confere que cada seção pedida existe e que o teto é respeitado.

Erros achados nos prompts e corrigidos (cada um com teste):

- O especialista de Seção 508 e a auditoria de conformidade usavam os parágrafos 1194.21 e 1194.22, que são da norma de 2000, substituída pelas Revised 508 Standards (em vigor para TIC usada após 18 de janeiro de 2018), que incorporam o WCAG 2.0 A e AA (E205.4). Também havia regras inventadas ("vídeo produzido depois de 1997 precisa de audiodescrição", "CAPTCHA precisa de áudio, 508(f)", "páginas devem funcionar sem script"). Reescritos sobre E205.4 e E207, com a regra de que critérios novos do WCAG 2.1 e 2.2 são boa prática, não base legal, e com as quatro isenções de documentos fora da web.
- O VPAT classificava 4.1.3 Mensagens de Status como nível A e 3.2.6 e 3.3.7 como AA. Os níveis certos são 4.1.3 AA, 3.2.6 A e 3.3.7 A; A tem 31 critérios e AA tem 24. Um teste compara a lista do código com a lista da referência.
- Conselho de região viva com v-show (Vue, React/Vue, AJAX e Svelte com "visibility/display"): display none tira o elemento da árvore de acessibilidade, então v-show não resolve; a correção é manter o contêiner sempre renderizado e exposto e trocar só o texto.
- O especialista de Angular dava como erro o [aria-label]="..." por sintaxe, e o guia oficial atual aceita as duas formas; o exemplo do prompt era esse falso erro e foi trocado por um div com clique sem teclado. O especialista de Vue cobrava aria-current em RouterLink, que o roteador já aplica.
- O especialista de Tailwind sugeria outline-none com anel; os anéis são box-shadow e somem em cores forçadas, e o Tailwind v4 tem outline-hidden para isso.
- O especialista mobile atribuía type email, tel e number ao 1.3.5 (que trata de autocomplete) e mandava trocar todo campo numérico por type number (a orientação do W3C é não usar number para códigos como CEP).
- O especialista cognitivo tratava todo CAPTCHA como falha de 3.3.8 (as exceções de reconhecimento de objetos e de conteúdo pessoal valem no AA), o botão de mostrar senha como exigência (é recomendação do COGA), nível de leitura e breadcrumb como falha (3.1.5 é AAA; breadcrumb é técnica).
- O especialista de leitor de tela citava "30 a 50 por cento" para a cobertura da automação sem fonte; o estudo da Deque (2021, fornecedor) mede 57 por cento em volume de ocorrências.
- A referência do chat e a regra 18 afirmavam "Safari obrigatório" no VoiceOver e "NVDA com Firefox é a combinação mais completa". Os testes públicos da TetraLogical mostram que o VoiceOver funciona no Chrome e no Firefox com diferenças, e a pesquisa da WebAIM mostra NVDA com Chrome (21,3 por cento) mais usado que com Firefox (10,0 por cento). Reescritos.

Testes: tests/backend/unit/shared/test_conhecimento_ampliado_dos_especialistas.py (80 casos). A suíte unitária inteira: 2224 aprovados.

Não conferido nesta rodada: o texto oficial da Diretiva (UE) 2019/882 (EUR-Lex devolveu página vazia), a ISO 14289 (paga), a página do Adobe, a página de acessibilidade da Apple (44 pontos no iOS), o mínimo de 48 dp do Android na página lida, as páginas do PDF Association (acesso negado; o conteúdo vem de resumos de busca), o guia oficial de teclas do JAWS, a especificação WAI-ARIA 1.2 completa. Os resultados de leitor continuam sendo de testes públicos em versões datadas e a fala exata continua pendente de teste manual.

## Orçamento de contexto

Ao ligar as referências ao índice do chat, o teste de economia do índice (test_prompt_carries_retrieved_chunks_not_the_whole_file) reprovou: a busca devolvia seções inteiras e o bloco de referência do turno chegou a 16.719 caracteres, mais que a metade do documento antigo. A causa era o tamanho dos trechos. A indexação agora reparte seções acima de 2.400 caracteres em linhas inteiras (títulos "parte 1 de 2"), o que vale para todos os documentos do índice. Testes: TestRetrievalBudget.

## O que ainda não está provado

- Nenhuma rodada ao vivo com modelo ou com leitor de tela real foi feita. O portão de mudança de instrução da regra 15 (conjunto amplo, ablação, observação) continua pendente; a proteção atual são os testes determinísticos.
- Os resultados de leitor vêm de testes públicos de terceiros, em versões datadas (NVDA 2024, JAWS 2026, VoiceOver no macOS Sequoia 15.5 e iOS 18.6.2, TalkBack 2025, Narrator 2025), e as páginas de TalkBack e Narrator se declaram trabalho em andamento. Devem ser reverificadas quando as versões mudarem.
- Fontes que não puderam ser lidas inteiras: a especificação WAI-ARIA 1.2 completa e o HTML-AAM (páginas muito grandes, lidas por trechos), o guia do VoiceOver no iPhone da Apple (página sem o conteúdo) e as páginas oficiais do JAWS e do Narrator. A tabela de papéis por atributo veio do MDN e do APG, não do texto integral da especificação.
- Afirmações marcadas nas próprias referências como não confirmadas: list-style none no VoiceOver, chaves de lista por índice no React, foco após remover um elemento, e o efeito do aria-haspopup em navegação por links (inferência da definição, não critério).
- A fala exata de cada leitor continua pendente de verificação manual com o leitor real; a árvore de acessibilidade do navegador é um substituto, não o leitor.
- Nada foi commitado.

## Quarta rodada (2026-10-18): foco, títulos, listas, tabelas e navegação

Nova referência: backend/src/resources/leitor_de_tela_estrutura_foco_e_navegacao.md, no corpus do chat e em fatias de seis especialistas (screen_reader, tables_data, wcag_semantics, operability, css_analyzer, interaction_pattern). Teste: tests/backend/unit/shared/test_conhecimento_estrutura_foco_navegacao.py.

O que ela entrega, com a fonte de cada ponto dentro do próprio documento: ordem de foco e de leitura (2.4.3, 1.3.2, tabindex, order do flex, reading-flow), hierarquia de títulos, listas (inclusive list-style none no Safari), marcação e fala de tabelas, grade e teclado, e as teclas de navegação por tipo e por tabela no NVDA, JAWS e VoiceOver.

Medido: o custo somado das fatias subiu de cerca de 126 mil para cerca de 146 mil caracteres (limite do teste atualizado para 155 mil). Suíte unitária: 2260 passaram; 1 falhou, test_run_conversation_formats_429_friendly_error, que é do trabalho antigo e não commitado em error_formatter (não é desta rodada).

Não confirmado: teclas de tabela do JAWS na página oficial, VO com Command e setas em tabela, suporte de dl por leitor, e se o reading-flow é respeitado na fala. O portão da regra 15 (conjunto amplo ao vivo, ablação e período de observação) continua pendente.

## Auditoria da interface web (2026-10-18)

Método: teste com o axe-core sobre o chat populado (turno com atividade da squad, ferramenta, resposta com bloco de código) e testes de papel, rótulo e estado. Arquivos: web/src/screens/__tests__/ChatScreen.axe.test.tsx e Paineis.axe.test.tsx.

Defeitos reais achados e corrigidos:
- Itens do feed de andamento tinham role listitem sem um list como pai (violação aria-required-parent do axe). O contêiner agora tem role list.
- aria-label em div sem papel (balões de mensagem, cartão de ferramenta, feed): o rótulo não é exposto de forma confiável. Agora têm role group ou list. Os balões ganharam nome curto (Mensagem de Você, Resposta do assistente) em vez de repetir a mensagem inteira, que seria lida duas vezes; o texto da mensagem continua sendo o conteúdo.
- Nome visível fora do nome acessível (2.5.3): Salvar e Continuar, Anexos adicionados e os dois botões do preview (Corrigido, Original) e o link de nova aba.
- Estado dito duas vezes: o botão de anexos trocava o rótulo e também tinha aria-expanded. O rótulo agora é fixo.
- aria-selected em botão (barra lateral e histórico), que não existe nesse papel; ficou aria-current na barra lateral e o rótulo "Conversa atual" no histórico.
- O alternador Corrigido e Original era tablist sem painéis nem setas; virou grupo de botões com aria-pressed.

Não alterado, por falta de prova com leitor real: aria-busy no bloco do turno e no cartão de ferramenta (a referência diz que o leitor pode esconder a região ocupada, mas o MDN usa "pode"); a tela de carregamento das Configurações cria a região de status já com texto.
