# Ferramentas do projeto QA Accessibility

> Inventário completo das ferramentas (tools) que o agente de IA deste
> projeto pode chamar. Gerado por exploração direta do código-fonte em
> 2026-08-18, corrigido e revalidado em 2026-08-29 (4 ferramentas do
> toolset de chat estavam faltando: `create_jira_issue`,
> `create_azure_devops_work_item`, `verify_screen_reader_announcements`,
> `design_review`) — cada entrada aqui corresponde a um `registry.register(...)`
> real em `tools/registry.py` (consumido por `backend/src/services/
> chat_tools.py` e `backend/src/services/a11y_domain_tools.py`) ou a uma
> `@mcp.tool()` real em `backend/src/services/mcp_server.py`. Nada nesta
> lista é hipotético — se não está registrado no código, não está aqui.
>
> **Total: 38 ferramentas** — 31 no toolset de chat (`a11y_chat` +
> `clarify`), 1 ferramenta compartilhada pelos agentes especialistas
> (`a11y_domain`), e 6 expostas via MCP (Model Context Protocol) para
> clientes externos como Claude Desktop e VS Code Copilot.
>
> 🔒 = a ferramenta exige aprovação explícita do usuário antes de executar
> (`requires_approval=True` em `tools/registry.py`, reforçado de verdade em
> `run_local_tool`, não só por convenção de prompt).

---

## 1. Análise e auditoria

### `analyze_page`
Analisa a acessibilidade de uma página web contra WCAG 2.2, WAI-ARIA e
Section 508. Roda o pipeline seletivo de agentes especialistas mais
verificação determinística de contraste. Aceita `url` (renderização real
com JS) OU `html` bruto. Devolve um resumo compacto: total de issues, score
0-100, contagem por severidade e os principais issues. Se a mesma URL já
foi analisada antes, também aponta regressões (issues novos) e correções
desde a última vez.

### `analyze_site`
Mesma análise de `analyze_page`, mas para várias páginas de uma vez —
crawling a partir de uma URL raiz (`url` + `max_pages`, padrão 10/máx 50)
ou uma lista explícita de `urls`. Devolve um resumo consolidado.

### `analyze_document`
Analisa a acessibilidade real de um PDF ou XLSX enviado pelo usuário
(regras PDF/UA e de acessibilidade de planilha), via agente especialista
dedicado. Para PDF, também roda o validador real veraPDF quando disponível
no servidor, mais detecção nativa de campos de formulário.

### `unzip_and_list_files`
Descompacta um ZIP em base64 (projeto enviado pelo usuário) e devolve o
caminho e conteúdo de cada arquivo de texto — usado antes de analisar/
corrigir um projeto inteiro enviado como ZIP.

### `read_local_project_files` 🔒
Lê um diretório real no disco da máquina que roda o backend (HTML, CSS, JS,
TS, JSX, TSX, Vue, Svelte, Swift, Kotlin, Dart, Java, mais imagens) — mesmo
efeito de um ZIP enviado, mas sem exigir que o usuário empacote e envie o
projeto. Só usa um caminho que o próprio usuário informou explicitamente.

### `run_remote_test` 🔒
Executa um teste de acessibilidade real. A escolha entre local e nuvem é
sempre do usuário, nunca decidida silenciosamente pelo modelo.

| `runner` | `location` | O que roda de fato | `runner` na resposta |
|---|---|---|---|
| `cypress` | `local` / `install_local` | Binário do Cypress + `cypress-axe` na máquina do backend | `cypress_local` |
| `cypress` | `cloud` | axe-core via Playwright/Browserless — **não há Cypress** | `axe_core_remote` |
| `selenium` | `local` / `install_local` | Selenium WebDriver + Chrome + axe-core injetado | `selenium_local` |
| `selenium` | `cloud` | axe-core via Playwright/Browserless — **não há Selenium** | `axe_core_remote` |
| `postman` | — | Collection real via Newman (`npx newman run`) | `postman_newman` |
| `postman` | — | Sem `npx`/Newman: checagem leve de contrato | `postman_lightweight` |

O motor de detecção é o mesmo (axe-core, Deque Systems) em todos os
caminhos; o que muda é **quem executa**. Os rótulos `cypress_remote` e
`selenium_remote` deixaram de existir porque prometiam um runner que não
estava ali.

**Gravação no Cypress Cloud.** Com `CYPRESS_PROJECT_ID` e
`CYPRESS_RECORD_KEY` configurados, o run local é disparado com
`--record --key` e gravado no Cypress Cloud; a resposta traz
`cypress_dashboard_url` com a URL real do run. Detalhe que engana: no CLI do
Cypress, `--project` é o **caminho** do projeto, não o `projectId` — o id vai
pela variável de ambiente `CYPRESS_PROJECT_ID`.

`cypress_cloud_synced` é `true` **apenas** quando a gravação de fato
aconteceu (o Cypress devolveu a URL do run). Quando as chaves estão
configuradas mas a gravação falhou, vem `false` mais um
`cypress_cloud_error` explicando o motivo. Em `location='cloud'` é sempre
`false`: não há Cypress para gravar.

**Postman.** `postman_cloud_authenticated` indica que a API do Postman
respondeu à autenticação, e `collection_source` diz se a collection veio da
nuvem do usuário (`postman_cloud`) ou foi gerada aqui (`generated`).
`results_uploaded_to_postman` é sempre `false`: nada é enviado de volta ao
Postman — o antigo `postman_cloud_synced` sugeria que era.

### `run_cross_browser_test` 🔒
Roda uma auditoria axe-core real contra uma URL nos 3 motores de
renderização que o Playwright oferece (Chromium, Firefox/Gecko, WebKit) —
importante porque o comportamento de leitor de tela genuinamente difere
entre engines (WebKit é o motor real por trás do VoiceOver, por exemplo).
Devolve um resumo por engine mais o diff de quais violações aparecem só em
alguns motores.

**Degradação honesta por motor.** A resposta traz `engines_succeeded` e
`engines_failed`, e o erro real de cada motor que não rodou. Dois casos são
distinguidos, porque a orientação certa é oposta em cada um:

- `install_suggestion` — o binário **não está instalado**. Aí faz sentido
  oferecer `install_playwright_browsers`.
- `runtime_failure_note` — o motor **está instalado mas não inicia**
  (`spawn UNKNOWN` e afins). Reinstalar não resolve, e oferecer instalação
  faria o usuário baixar centenas de MB à toa. A nota manda declarar
  explicitamente quais motores **não** foram verificados, para um resultado
  parcial nunca passar por cobertura completa.

No Windows, a causa usual do segundo caso é o cache do Playwright estar sob
`AppData\Local` — ver a seção de testes do README (`PLAYWRIGHT_BROWSERS_PATH`).

### `compute_contrast`
Calcula a razão de contraste WCAG exata entre duas cores (hex, rgb()/rgba()
ou nomes comuns) e devolve os veredictos por nível/tamanho de texto.

**Como o contraste é realmente verificado hoje:** não por tool-call. O
`contrast_verifier.py` recomputa o ratio exato dos achados 1.4.3/1.4.11 em
Python puro, dentro do `orchestrator`, depois do merge/dedup — e remove os
falsos positivos. A decisão foi deliberada e está registrada no próprio
módulo: cálculo determinístico é robusto em qualquer provider, sem depender
do loop de tool-call do modelo. Nunca estimado "no olho".

A tool `compute_contrast` está registrada no toolset `a11y_tools`, que
**nenhum agente habilita atualmente** (`enabled_toolsets` do chat é
`a11y_chat` + `clarify`). O que está em uso são as funções
`contrast_ratio_rgb`/`parse_color` do mesmo módulo, importadas diretamente
pelo verificador. Até 2026-08-30 este documento dizia que a tool era
"compartilhada pelos agentes especialistas", o que não corresponde ao
roteamento real.

### `verify_screen_reader_announcements` 🔒
Verifica os anúncios de leitor de tela de uma URL cruzando a árvore de
acessibilidade REAL computada pelo motor do navegador (Chromium/CDP — a
mesma API que NVDA/JAWS/Narrator consultam no Windows) contra regras
determinísticas de nome acessível ausente ou genérico. Diferente de
`analyze_page` (que estima a partir do HTML bruto via LLM), aqui o achado é
confirmado pelo próprio motor de acessibilidade do navegador — zero
inferência de IA nessa etapa. Tenta `BROWSERLESS_WS_URL` remoto e cai
para Chromium local headless quando a variável não existe ou a conexão falha.
Também aceita passos declarativos de teclado/interação (`Tab`, `Shift+Tab`,
teclas, clique, preenchimento e espera) e valida foco, nome/papel, diálogos e
mensagens na árvore de acessibilidade após cada passo — sem capturar áudio e
sem executar JavaScript arbitrário.

### `design_review`
Único agente do projeto que não audita HTML/código já existente: recebe um
requisito, user story ou trecho de PRD em texto livre e antecipa riscos de
acessibilidade — com critérios WCAG 2.2 prováveis, severidade, motivo
específico preso ao texto real do requisito e recomendação acionável —
antes de qualquer linha de código ser escrita. Requisito sem risco real →
lista vazia, resposta válida, não uma falha.

---

## 2. Correção (remediação)

### `fix_and_zip_files` 🔒
Aplica correções de acessibilidade a múltiplos arquivos locais (HTML, CSS,
JS, TS, Swift, Kotlin, Dart, Java, DOCX, PDF) e empacota tudo num ZIP para
download. Se o usuário quiser corrigir a última página analisada via
`analyze_page(url=...)`, basta omitir `files` — a página buscada
anteriormente é reaproveitada automaticamente.

### `fix_local_project_files` 🔒
Igual a `fix_and_zip_files`, mas GRAVA a correção direto nos MESMOS
arquivos no disco local do usuário (além de ainda gerar o ZIP como
salvaguarda). Um backup de cada arquivo original é criado antes de
sobrescrever, e o caminho do backup é devolvido.

### `undo_last_fix` 🔒
Desfaz a última execução de `fix_and_zip_files`, restaurando o cache de
análise e as páginas do live preview ao estado anterior à correção. Só a
correção mais recente pode ser desfeita.

---

## 3. Geração de entregáveis

### `export_xlsx` 🔒
Devolve o link de download da planilha Excel com os resultados da última
auditoria (página ou site).

### `generate_checklist` 🔒
Gera um checklist estruturado de acessibilidade (itens pass/fail/
verificação manual, um por critério WCAG) a partir dos issues da última
análise, via o `ChecklistAgent` dedicado — nunca texto livre escrito pelo
próprio modelo.

### `export_checklist_pdf` 🔒
Devolve o link de download do checklist da última página analisada como
PDF acessível e tagueado (PDF/UA-1 — árvore de estrutura real, não uma
exportação visual plana).

### `generate_accessibility_statement` 🔒
Gera uma Declaração de Acessibilidade (documento público de status de
conformidade, ex. publicado em `/accessibility`) cobrindo meta de
conformidade WCAG, metodologia de avaliação, limitações conhecidas (a
partir dos issues reais da última análise) e como reportar uma barreira.
Nunca inventa nome da organização ou contato — usa placeholder claro se o
usuário não informou.

### `export_accessibility_statement_pdf` 🔒
Devolve o link de download da Declaração de Acessibilidade da última
análise como PDF acessível tagueado (PDF/UA-1).

### `generate_vpat` 🔒
Gera um VPAT WCAG 2.2 (Voluntary Product Accessibility Template) — o
documento de conformidade exigido em processos empresariais, governamentais
(Section 508) e de licitação — a partir dos issues da análise mais
recente.

### `generate_test_suite` 🔒
Gera uma suíte de testes de acessibilidade pronta para uso (Playwright +
axe-core) a partir dos issues da análise mais recente, para o time
auditado plugar no próprio CI e travar regressões.

### `generate_automation_script` 🔒
Gera um script de teste de acessibilidade automatizado pronto para uso em
Cypress (cypress-axe), Postman (collection JSON/Newman), Selenium
(axe-selenium-python) ou Playwright (`@axe-core/playwright`).

---

## 4. Visualização

### `open_live_preview`
Abre uma sessão de Live Preview mostrando as páginas HTML corrigidas pela
última chamada de `fix_and_zip_files`, lado a lado (original vs. corrigida
com destaques de acessibilidade). Só pode ser chamada depois de
`fix_and_zip_files` já ter produzido pelo menos um HTML corrigido na
conversa.

---

## 5. Pesquisa e RAG normativo

### `tavily_search`
Busca na web via Tavily Search API — usada para achar páginas-alvo de
auditoria, diretrizes WCAG ou artigos de acessibilidade.

### `exa_search`
Busca na web via Exa.ai Search API — focada em especificações técnicas
profundas, WCAG ACT Rules e soluções técnicas de acessibilidade.

### `evaluate_research`
Usada depois de `tavily_search`/`exa_search` para o próprio agente
registrar seu veredito de suficiência: a informação recolhida já é
suficiente para responder com precisão normativa, ou é preciso pesquisar
mais? Parte do ciclo Agentic RAG / ReAct.

### `run_deep_research`
Executa uma pesquisa normativa profunda de acessibilidade (WCAG 2.2,
WAI-ARIA APG, Section 508, EN 301 549, PDF/UA), investigando fontes
primárias e trazendo citações completas — mais aprofundada que uma busca
simples via `tavily_search`/`exa_search`.

---

## 6. Integração externa e infraestrutura

> **Credencial ausente = erro, nunca um ticket falso.** As três ferramentas
> de ticket devolvem `status: "error"` com `missing_config` listando as
> variáveis que faltam, e **nenhum identificador ou URL é inventado**. Até
> a auditoria de 2026-08-30 elas devolviam `status: "simulated"` junto de um
> `issue_url`/`work_item_url` plausível (`.../issues/mock-1`, `MOCK-1`,
> `_workitems/edit/1`) nos mesmos campos do caminho de sucesso — o modelo lia
> aquilo e respondia "abri o ticket: <link>" a quem tinha aprovado a ação e
> não recebeu ticket nenhum.

### `create_github_issue` 🔒
Cria uma nova Issue no repositório GitHub configurado, contendo o
diagnóstico e a sugestão de correção de um problema de acessibilidade
encontrado.

### `create_jira_issue` 🔒
Cria uma nova Issue no projeto Jira configurado (`summary`, `description`,
`severity` mapeada para a prioridade do Jira, `project_key` opcional —
usa `JIRA_PROJECT_KEY` se omitido), contendo o diagnóstico e a sugestão de
correção de um problema de acessibilidade encontrado.

### `create_azure_devops_work_item` 🔒
Cria um novo Work Item no Azure DevOps configurado (`title`, `description`,
`severity` mapeada para `Microsoft.VSTS.Common.Severity`, `project`
opcional — usa `AZURE_DEVOPS_PROJECT` se omitido), contendo o diagnóstico e
a sugestão de correção de um problema de acessibilidade encontrado.

### `install_playwright_browsers` 🔒
Instala de verdade os binários de navegador do Playwright (Chromium,
Firefox, WebKit) na máquina que roda o backend, via
`python -m playwright install`. Só é chamada depois de confirmação
explícita do usuário nesta conversa.

---

## 7. Interação com o usuário

### `clarify`
Pergunta algo ao usuário e AGUARDA a resposta (bloqueia de verdade,
via `POST /chat/clarify`) antes de continuar — usada para apresentar um
plano e pedir aprovação, ou confirmar uma correção antes de alterar
código. É também o mecanismo que implementa o gate de aprovação (🔒) de
toda ferramenta efeituosa acima: `run_local_tool` chama exatamente este
fluxo antes de liberar a execução.

---

## 7b. Rotas HTTP sem ferramenta de chat correspondente

Endpoints que existem na API mas não são chamados pelo toolset do chat — a
interface ou um integrador externo os consome diretamente. Não estavam
documentados até a auditoria de 2026-08-30.

| Rota | Para que serve |
|---|---|
| `POST /analyze/project/zip` | Analisa um projeto inteiro enviado como ZIP, sem exigir seleção de pasta |
| `POST /analyze/agent-project` | Audita arquitetura e comportamento de um projeto de agente sem executar o código |
| `POST /analyze/agent-project/zip` | Audita um projeto agentivo enviado como ZIP, filtrando dependências e builds |
| `POST /fix/project/zip` | Corrige um projeto enviado como ZIP e devolve o resultado empacotado |
| `POST /preview/create` | Registra uma sessão de live preview a partir das páginas corrigidas e devolve `session_id` |
| `GET /preview/render/{session_id}/{page_index}` | Renderiza uma página da sessão de preview (`mode=fixed` por padrão) para comparação lado a lado |
| `POST /a2a/v1/tasks/{task_id}/cancel` | Cancela uma tarefa delegada via A2A |
| `POST /a2a/v1/tasks/{task_id}:cancel` | Mesma operação na forma `:cancel` do protocolo A2A |
| `GET /a2a/v1/tasks/{task_id}/subscribe` | Stream de atualizações de uma tarefa A2A em andamento |

Removido na mesma auditoria: `GET /last_xlsx**`, uma rota com asteriscos
literais no caminho — registrada como URL literal, sem chamador nenhum.

---

## 8. Servidor MCP (clientes externos: Claude Desktop, VS Code Copilot, etc.)

Ferramentas expostas via `backend/src/services/mcp_server.py`
(`FastMCP("QA-Accessibility-Tools")`), independentes do chat interno —
qualquer cliente MCP compatível pode chamá-las diretamente por stdio.

### `get_rendered_page`
Renderiza uma URL (com JS) e devolve o HTML resultante.

### `run_axe_audit`
Roda o axe-core real (via Playwright) contra um HTML fornecido e devolve a
lista de violações em JSON.

### `export_xlsx` (MCP)
Recebe uma lista de issues em JSON e devolve a planilha Excel gerada,
codificada em base64 — versão standalone da exportação, sem depender de
uma sessão de chat prévia.

### `analyze_page_full`
Pipeline completo de auditoria numa única chamada: fornece `url` (renderiza
remotamente) OU `html` cru. Devolve score (0-100), total de issues,
contagem por severidade e os 10 principais issues.

### `analyze_site_full`
Faz o crawl de um site a partir da URL raiz e audita até `max_pages`
páginas (padrão 10, máx. 50). Devolve páginas auditadas, score agregado,
total de issues e contagem por severidade.

### `describe_repository`
Repository Intelligence: devolve o índice estruturado
(`docs/REPO_MAP.json`) dos agentes especialistas deste repositório — nome,
arquivo, entry-point, prefixo de ID de issue e diretriz (WCAG/WAI-ARIA/
Section 508) de cada um. Permite que um cliente MCP descubra "quem cobre
ARIA?" ou "qual arquivo trata contraste?" sem precisar ler todos os módulos
de `agents/` ou o `AI_MODULE_SPEC.md` inteiro.

---

## Referência rápida (contagem)

| Categoria | Qtd |
|---|---|
| Análise e auditoria | 10 |
| Correção (remediação) | 3 |
| Geração de entregáveis | 8 |
| Visualização | 1 |
| Pesquisa e RAG normativo | 4 |
| Integração externa e infraestrutura | 5 |
| Interação com o usuário | 1 |
| Servidor MCP (clientes externos) | 6 |
| **Total** | **38** |

Ferramentas com 🔒 (exigem aprovação explícita do usuário): 20 de 38.
