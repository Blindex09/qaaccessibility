# Conhecimento de leitor de tela: o que fala e faz cada elemento e comportamento

Este módulo dá ao chat e aos agentes de análise uma base pesquisada em documentação oficial sobre o que a pessoa que usa leitor de tela percebe em cada elemento HTML, em cada padrão ARIA, em conteúdo dinâmico (AJAX, JavaScript, React, Astro) e em efeitos de CSS, tanto quando o elemento é acessível quanto quando não é. O objetivo é acertar nos testes e nas informações, sem teste verde como prova e sem afirmar fala exata que a fonte não sustenta.

## O que existia antes

- O especialista de leitor de tela tinha uma lista de padrões a detectar, e o chat tinha um guia de teste por navegador e dispositivo, o algoritmo de nome acessível e o guia de nome para imagens. Não havia, por elemento, o que cada leitor expõe e fala, nem a diferença entre o que a especificação define e o que cada leitor faz.
- O repositório mcp do dono traz um guia de NVDA com anúncios comuns. Foi usado como roteiro de conferência, não como fonte: cada afirmação aqui foi conferida na documentação.

## O que foi entregue

Quatro referências em backend/src/resources, todas no índice de busca do chat:

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

## Orçamento de contexto

Ao ligar as referências ao índice do chat, o teste de economia do índice (test_prompt_carries_retrieved_chunks_not_the_whole_file) reprovou: a busca devolvia seções inteiras e o bloco de referência do turno chegou a 16.719 caracteres, mais que a metade do documento antigo. A causa era o tamanho dos trechos. A indexação agora reparte seções acima de 2.400 caracteres em linhas inteiras (títulos "parte 1 de 2"), o que vale para todos os documentos do índice. Testes: TestRetrievalBudget.

## O que ainda não está provado

- Nenhuma rodada ao vivo com modelo ou com leitor de tela real foi feita. O portão de mudança de instrução da regra 15 (conjunto amplo, ablação, observação) continua pendente; a proteção atual são os testes determinísticos.
- Os resultados de leitor vêm de testes públicos de terceiros, em versões datadas (NVDA 2024, JAWS 2026, VoiceOver no macOS Sequoia 15.5 e iOS 18.6.2, TalkBack 2025, Narrator 2025), e as páginas de TalkBack e Narrator se declaram trabalho em andamento. Devem ser reverificadas quando as versões mudarem.
- Fontes que não puderam ser lidas inteiras: a especificação WAI-ARIA 1.2 completa e o HTML-AAM (páginas muito grandes, lidas por trechos), o guia do VoiceOver no iPhone da Apple (página sem o conteúdo) e as páginas oficiais do JAWS e do Narrator. A tabela de papéis por atributo veio do MDN e do APG, não do texto integral da especificação.
- Afirmações marcadas nas próprias referências como não confirmadas: list-style none no VoiceOver, chaves de lista por índice no React, foco após remover um elemento, e o efeito do aria-haspopup em navegação por links (inferência da definição, não critério).
- A fala exata de cada leitor continua pendente de verificação manual com o leitor real; a árvore de acessibilidade do navegador é um substituto, não o leitor.
- Nada foi commitado.
