# Ferramentas do projeto QA Accessibility

> Inventário completo das ferramentas (tools) que o agente de IA deste
> projeto pode chamar. Gerado por exploração direta do código-fonte em
> 2026-08-18 — cada entrada aqui corresponde a um `registry.register(...)`
> real em `tools/registry.py` (consumido por `backend/src/services/
> chat_tools.py` e `backend/src/services/a11y_domain_tools.py`) ou a uma
> `@mcp.tool()` real em `backend/src/services/mcp_server.py`. Nada nesta
> lista é hipotético — se não está registrado no código, não está aqui.
>
> **Total: 34 ferramentas** — 27 no toolset de chat (`a11y_chat` +
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
Executa um teste de acessibilidade real: `cypress`/`selenium` rodam o
axe-core de verdade (mesmo motor da Deque Systems) contra a página
renderizada; `postman` roda uma collection real via Newman quando `npx`
está disponível no servidor. Para cypress/selenium, a execução pode ser
`local` (binário real na máquina do backend) ou `cloud` (via Playwright/
Browserless remoto) — a escolha é sempre do usuário, nunca decidida
silenciosamente pelo modelo.

### `run_cross_browser_test` 🔒
Roda uma auditoria axe-core real contra uma URL nos 3 motores de
renderização que o Playwright oferece (Chromium, Firefox/Gecko, WebKit) —
importante porque o comportamento de leitor de tela genuinamente difere
entre engines (WebKit é o motor real por trás do VoiceOver, por exemplo).
Devolve um resumo por engine mais o diff de quais violações aparecem só em
alguns motores.

### `compute_contrast`
Ferramenta compartilhada pelos agentes especialistas (não pelo chat
diretamente): calcula a razão de contraste WCAG exata entre duas cores
(hex, rgb()/rgba() ou nomes comuns), usada para VERIFICAR um achado 1.4.3/
1.4.11 antes de reportá-lo — nunca estimado "no olho".

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
Cypress (cypress-axe), Postman (collection JSON/Newman) ou Selenium
(axe-selenium-python).

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

### `create_github_issue` 🔒
Cria uma nova Issue no repositório GitHub configurado, contendo o
diagnóstico e a sugestão de correção de um problema de acessibilidade
encontrado.

### `nvda_speak` 🔒
Envia um comando de voz diretamente para o leitor de tela NVDA ativo (via
`nvdaControllerClient.dll`), para que ele fale um texto ao usuário — com
fallback simulado gracioso quando o NVDA/DLL não está disponível.

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
| Análise e auditoria | 8 |
| Correção (remediação) | 3 |
| Geração de entregáveis | 8 |
| Visualização | 1 |
| Pesquisa e RAG normativo | 4 |
| Integração externa e infraestrutura | 3 |
| Interação com o usuário | 1 |
| Servidor MCP (clientes externos) | 6 |
| **Total** | **34** |

Ferramentas com 🔒 (exigem aprovação explícita do usuário): 17 de 34.
