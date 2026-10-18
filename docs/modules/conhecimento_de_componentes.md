# Conhecimento de bibliotecas de componentes

Este módulo ensina o chat e os agentes especialistas a auditar o que uma biblioteca de componentes realmente renderiza, em qualquer plataforma, e traz o catálogo da primeira biblioteca concreta: o accessible-astro-components, usado pelo Accessible Astro Starter (projeto de teste my-accessible-site).

## O que existia antes

O catálogo genérico accessible_component_patterns.md e o especialista component_contracts já existiam e continuam. O que faltava e o que estava errado:

- O conhecimento era genérico e inspirado no starter, sem o HTML que cada componente de fato produz.
- O catálogo e o especialista exigiam button com aria-expanded e aria-controls em toda divulgação. O Accordion da biblioteca usa details e summary nativos, então seria apontado como falha sem ser.
- O especialista de formulários exigia role alert ou aria-live assertive no resumo de erros. O Form da biblioteca usa polite e move o foco para o resumo, que é aceitável.
- O Tooltip da biblioteca abre por ativação (toggletip), e a regra de hover e foco do catálogo o reprovaria.
- A Pagination da biblioteca mostra a página atual por texto de progresso, sem aria-current.
- O seletor do orquestrador que decide se o especialista de componentes roda tinha um defeito antigo: o limite de palavra no início do padrão impedia casar dialog depois de um sinal de maior. Também não reconhecia details nem popover, então uma página só com o Accordion nunca chamaria o especialista.
- Só o chat recuperava o catálogo genérico. Nenhum agente de análise o recebia.

## O que o módulo entrega e qual teste cobre cada promessa

Todos os testes estão em tests/backend/unit/shared/test_component_library_calibration.py.

- Fonte única do conhecimento, em backend/src/resources/component_library_knowledge.md, dividida em método geral e catálogo: TestSingleSource::test_method_and_catalog_come_from_the_resource_file.
- Chat recupera o conhecimento pelo índice de busca: TestSingleSource::test_chat_rag_corpus_indexes_the_library_knowledge.
- Todo componente demonstrado pelo starter tem entrada no catálogo, inclusive conferindo os imports reais da página do starter quando o projeto está na máquina: test_every_component_the_starter_demonstrates_has_an_entry e test_catalog_covers_every_import_of_the_real_starter_page_when_present.
- Especialistas que julgam componentes compostos (component_contracts e widgets_a11y) recebem método e catálogo: TestWiringIntoAgents::test_composed_component_specialists_get_method_and_catalog.
- Os demais especialistas em que o assunto se encaixa (formulários, ARIA, padrões de interação, operabilidade, leitor de tela, links) recebem só o método, sem o custo do catálogo: test_other_specialists_get_the_method_without_the_catalog_cost.
- O revisor recebe o método e continua terminando no contrato normativo: test_reviewer_gets_the_method_and_keeps_the_normative_contract_last.
- Os papéis da squad recebem o método: test_squad_roles_receive_the_method.
- O chat recebe o método no prompt: test_chat_prompt_builder_references_the_method (verifica a presença no código; a prova de comportamento ao vivo está nas lacunas abaixo).
- Divulgação nativa, resumo de erro com polite e foco, toggletip e paginação por texto são aceitos: classe TestRealDefectsFoundByTheReading.
- O seletor reconhece details, popover e dialog solto, e continua sem pagar o especialista numa página sem evidência de componente: mesmos testes da classe acima.
- O especialista de componentes envia o HTML e o catálogo ao modelo para os três formatos reais da biblioteca: test_component_specialist_sends_html_and_catalog_to_the_model.

## Arquivos .astro e .mdx como fonte

Antes: a análise de projeto e de ZIP aceitava .html, .css, .js, .jsx, .ts, .tsx, .vue e .svelte. Arquivos .astro e .mdx eram ignorados em silêncio, e o chat não os lia nem de pasta local nem de ZIP. Nenhum formato de componente (nem Vue, nem Svelte) tinha mapeamento do componente para o HTML gerado: o código-fonte entrava como texto corrido.

Agora:

- As rotas de projeto e de ZIP aceitam .astro e .mdx, e o chat os lê de pasta local e de ZIP.
- Um mapa de fonte (backend/src/services/astro_source.py) é colocado antes dos arquivos no contexto da análise de projeto e de ZIP e, no chat, pela própria ferramenta de análise de página, que reconhece o formato de arquivos separados por linhas com o caminho (e também um trecho Astro colado, que importa a biblioteca). O documento original, usado depois para corrigir, não leva o mapa. Ele lista, por arquivo, os componentes que de fato aparecem no markup, separados em biblioteca catalogada, componente do projeto (com o arquivo, quando ele foi enviado, ou aviso de que não foi), e terceiros.
- Para cada componente da biblioteca usado, o mapa traz a entrada do catálogo com o HTML que ele renderiza, só dos componentes usados. Componente sem entrada é declarado como desconhecido, sem suposição.
- O que o código decide são fatos de sintaxe (instruções de import, tags com inicial maiúscula, busca por nome de identificador). Nenhum julgamento de acessibilidade ou de intenção.
- O conteúdo do arquivo é dado não confiável: só nomes no formato de identificador e caminhos de módulo com caracteres seguros e tamanho limitado entram no mapa.

Medido sobre o projeto real my-accessible-site, sem chamar modelo: 41 arquivos .astro e .mdx, mapa de cerca de 22 mil caracteres para o projeto inteiro, e o Launcher (accessible-astro-launcher) aparece como "sem entrada no catálogo".

Testes: tests/backend/unit/services/test_astro_source.py (leitura de imports, mapa e HTML gerado, componente sem entrada, ausência de bloco sem Astro, texto hostil, cada componente do starter com entrada própria, rota de projeto, leitura de ZIP e pasta local do chat, separação de arquivos, e o conteúdo que a análise de página e o orquestrador recebem).

## Revisão do comportamento com o projeto my-accessible-site (2026-10-17)

Lidos o Navigation, o NavigationItems, o ResponsiveToggle, o Header, o Footer, o Hero, o Logo, o Feature, o PageHeader, o Contact e a página de componentes. Achados no conhecimento dos agentes, já corrigidos:

- O chat não passa pelo caminho de projeto: o modelo manda os arquivos numa única chamada de análise de página. O primeiro desenho do mapa (notas das ferramentas) chegaria ao modelo rotulado como "extração parcial" e dependeria de ele copiar o mapa. Passou a ser injetado pela própria ferramenta (teste test_analyze_page_sends_the_map_before_the_project_to_the_specialists).
- O menu de navegação do site usa o padrão por divulgação (botão com aria-expanded e lista de links). Nenhum agente conhecia esse padrão, e o aria-haspopup="true" nesse botão, que é um desacordo real, não estava coberto. Entrou no método geral e na regra de menus do especialista de widgets.
- O especialista de widgets tratava a falta de aria-haspopup="dialog" no gatilho como falha. Pelo contrato normativo é recomendação; o texto foi corrigido.

Observações sobre o código do site que um bom teste deve conseguir encontrar (não corrigidas, pois o site é só o alvo de teste): o botão do menu móvel troca o rótulo e também aria-expanded, e não tem aria-controls; aria-haspopup="true" nos botões de submenu cujo conteúdo são links; o foco vai ao primeiro item do menu ao apertar Escape em qualquer lugar do menu; a página de componentes é uma galeria com ids e landmarks repetidos.

Limites conhecidos: a correção automática (corrigir e baixar o ZIP) continua sem tratar .astro e .mdx; o mapa não expande componentes do projeto (o modelo lê o arquivo do componente quando ele foi enviado); alias de caminho é resolvido só pelo nome do arquivo, e nome repetido em duas pastas vira "não encontrado".

## Alinhamento com o repositório mcp (2026-10-17)

O repositório mcp (web-accessibility) tem o método de teste que o Qaaccessibility deve seguir: achado só vale com evidência, verde de ferramenta automática não prova acessibilidade, o que não foi verificado é dito, e o teste confere o comportamento e não a técnica. Divergências achadas no Qaaccessibility e corrigidas:

- O gerador de testes mandava afirmar que o atributo alt não pode ser vazio. O mcp (e a W3C) tratam alt vazio como marca deliberada de imagem decorativa; o teste gerado reprovaria páginas corretas, como o Hero e o Logo do starter. Corrigido: afirma-se a existência do atributo.
- O gerador exigia que o foco fosse para um h1 com tabindex -1 após troca de rota, uma técnica. Corrigido: afirma-se o resultado (título mudou e o foco ou o anúncio levou a pessoa ao novo conteúdo).
- O gerador não tinha os contratos de comportamento (diálogo, divulgação, abas, erros de formulário, passeio por Tab, tamanho de alvo). Entraram, com a regra de que submenu de navegação é divulgação e não menu, e de que dialog nativo dispensa aria-modal.
- O relator pedia para "comemorar" um resultado sem achados e definia 100 como "totalmente acessível". Corrigido: sem achados significa nenhuma violação confirmada no escopo avaliado, não é certificação, e a nota é um indicador de triagem.

Testes: tests/backend/unit/agents/test_alinhamento_conhecimento_mcp.py.

## Conferência com a documentação oficial (2026-10-17)

Consultadas: páginas do W3C (novidades do WCAG 2.2 e as páginas de entendimento de 1.4.3, 1.4.12, 2.4.13 e 2.5.3), WAI-ARIA 1.2 (papéis sem nome do autor), padrão de alerta do APG, especificação HTML do popover, e MDN (aria-checked, aria-expanded, aria-selected e regiões vivas). Erros encontrados nos prompts e corrigidos:

- Três especialistas (React, Svelte e leitor de tela) citavam o critério 4.1.1 Parsing como ativo. Ele foi removido no WCAG 2.2.
- O especialista de CSS tratava line-height abaixo de 1,2 e texto justificado como falha do 1.4.12. O critério testa se nada se perde quando a pessoa aumenta os espaçamentos.
- O especialista de ARIA dizia que aria-checked é proibido em option e que aria-expanded é proibido em checkbox. Ambos são suportados. Ele também mandava sinalizar nome em time e blockquote, que podem ter nome; faltavam em e strong na lista de papéis sem nome.
- O especialista semântico afirmava que todo popover deve ter papel explícito de dialog, tooltip ou menu. A especificação HTML não exige isso.
- A regra do corretor sobre avisos com ação afirmava que região viva "tira a semântica interativa" e impede o uso. A fonte diz que o anúncio é texto simples e que o alerta não deve tomar o foco; o texto foi reescrito.
- A auditoria de conformidade dizia que 2.5.3 é AA; é A. A referência do chat apresentava o 2.4.13 (AAA) como requisito junto do 2.4.7 e o APCA como critério, com valores de Lc que não conferi.

Testes: tests/backend/unit/agents/test_conhecimento_normativo_fontes.py, com as fontes no cabeçalho.

Não conferido nesta rodada, a verificar contra a fonte antes de confiar: os comandos invocadores e interestfor, a afirmação de que aria-modal é pouco confiável no Safari, a de que text-transform uppercase faz leitor de tela soletrar, os palpites de contraste por classe do Tailwind, o atraso de 100 a 500 ms após uma chamada AJAX, a perda de foco por chave de lista por índice no React, e a exigência de rel noopener em target _blank (navegadores atuais já a presumem). A cobertura de React, CSS e JavaScript é uma amostra das afirmações mais arriscadas, não uma revisão completa.

## Como a decisão de conteúdo fica com a IA

Nenhuma palavra-chave decide se uma página usa a biblioteca. O catálogo é conhecimento entregue ao modelo, e a leitura do contexto continua sendo dele. O único código novo de decisão é o ajuste do seletor estrutural que já existia, e ele olha elementos presentes no HTML (details, dialog, popover), que são fato objetivo.

## Registro da mudança de instrução (regra 15)

Data: 2026-10-17.
Motivo: o conhecimento de componentes era genérico e conflitava com o HTML real da biblioteca (lista acima).
Instruções alteradas: bloco novo de calibração em oito especialistas, no revisor, nos papéis da squad e no prompt do chat; três regras reescritas (divulgação no especialista de componentes, resumo de erro no especialista de formulários, divulgação, tooltip e paginação no catálogo genérico).
Para qual modelo vale: escrito sem ajuste por modelo; nenhum provedor foi testado ao vivo.
Conjunto que rodou: lint e tipos nos arquivos tocados; suíte unitária do backend inteira, com 1932 testes aprovados e 1 teste excluído (test_run_conversation_formats_429_friendly_error, que depende do formatador de erros com alterações locais não relacionadas e não foi verificado sem elas).
Ablação ao vivo: NÃO FEITA. O portão pede o conjunto amplo de avaliações em tentativas repetidas, ligando e desligando o bloco, e depois um período de observação. Isso depende de crédito do provedor e do site de teste instalado e rodando, e fica como pendência. Até lá, a mudança está protegida só pelos testes determinísticos e não está provada em comportamento de modelo.
Como desfazer se piorar: remover as importações e as concatenações de COMPONENT_LIBRARY_METHOD e COMPONENT_LIBRARY_FULL (uma por arquivo de agente, no chat e no executor da squad).

## O que ainda não está provado

- Nenhuma auditoria ao vivo do my-accessible-site foi feita com o bloco ligado; não se sabe a taxa de acerto dos modelos nos casos do catálogo.
- O catálogo vem da leitura do código do ramo principal da biblioteca. O site declara ^5.2.0 e não tem node_modules, então a versão instalada não foi conferida.
- SkipLink, DataTable, Textarea, Radio, BreadcrumbsItem, TabsPanel, AvatarGroup e o accessible-astro-launcher estão marcados como fonte não lida.
- Os especialistas não recebem código-fonte .astro ou .mdx: a análise de arquivos aceita .html, .css, .js, .jsx, .ts, .tsx, .vue e .svelte (backend/src/routes/analyze.py). O conhecimento ajuda a ler o HTML renderizado; ler a página-fonte do Astro é uma lacuna aberta.
- A matriz de cobertura dos conceitos agênticos de 2026 não foi rodada nesta entrega.
- Nada foi commitado nem marcado com tag.
