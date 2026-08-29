# QA Accessibility

Analisador de acessibilidade com IA, seguindo WCAG 2.2, WAI-ARIA e ADA/Section 508.

## Regras obrigatórias

- Este README prevalece sobre qualquer outra documentação
- A implementação mais recente prevalece
- Toda mudança estrutural, contratual ou comportamental deve ser refletida neste README na mesma entrega
- Cada `AI_MODULE_SPEC.md` é o contrato local obrigatório do respectivo módulo
- Zero duplicação de fluxos, endpoints, helpers ou regras de negócio
- Zero código legado ou deprecado
- Imports sempre no topo do arquivo
- Zero keywords hardcoded que bloqueiem ou condicionem o comportamento da LLM
- Documentação de API é viva — nunca confie em links ou parâmetros fixos
- Zero emojis em chamadas de logger ou saída de terminal (compatibilidade cp1252)
- Qualquer alteração no código-fonte deve ser refletida nos testes na mesma entrega
- Todo início local do projeto deve manter logs persistentes ativos por padrão em `logs/`
- Logs e caches só devem ser apagados quando isso for solicitado explicitamente

## Stack

| Camada    | Tecnologia                                      |
|-----------|-------------------------------------------------|
| Agentes   | Python 3.11+ · asyncio · engine agêntica própria (`run_agent.AIAgent`) |
| Backend   | Python 3.11+ · FastAPI                          |
| Browser   | Playwright (Chromium headless) — JS rendering   |
| Web       | React Native Web · TypeScript                   |
| IA        | Engine agêntica própria · Providers nativos (OpenAI, Anthropic, Gemini, xAI, Ollama Cloud) |
| Testes    | Pytest + pytest-asyncio (backend) · Jest (web) |

## Funcionalidades

- Analisa URLs externas e arquivos locais (HTML, CSS, JS, TS, TSX, Vue, Svelte)
- Analisa projetos inteiros: selecione uma pasta e todos os arquivos compatíveis são enviados
- Detecta problemas de acessibilidade (WCAG 2.2, WAI-ARIA, ADA 508)
- Detecta problemas em CSS inline e embedded (contraste, outline:none, prefers-reduced-motion)
- Detecta problemas em conteúdo dinâmico/AJAX (ARIA live regions, focus management, SPAs)
- Detecta barreiras cognitivas (CAPTCHA sem alternativa, formularios sem feedback, linguagem complexa)
- Detecta anti-padrões React/framework (div onClick, Tailwind outline-none, target=_blank sem aviso)
- Verifica compatibilidade com screen readers (headings, landmarks, link text, duplicate id)
- Verifica acessibilidade mobile web (viewport zoom, touch targets WCAG 2.5.8, reflow 1.4.10)
- Gera checklist de acessibilidade via IA
- Corrige arquivo local com auxílio da IA e disponibiliza download
- Sugere melhorias para URLs externas
- Exporta e compartilha checklist (devs, stakeholders)
- Exporta **XLSX acessível** (bilíngue, auto-filter, freeze panes, cores por severidade)
- Gera **VPAT WCAG 2.2** (conformidade para enterprise/governo/Section 508/licitações) — aceita `issues` ou `html_content`
- Gera **suíte de testes** (Playwright + axe-core) pronta para o CI da equipe auditada — aceita `issues` ou `html_content`
- **Verificação de contraste com proteção a fundos complexos**: ratio WCAG exato calculado em Python, com desvio automático e aviso de revisão manual para fundos com imagens, gradientes ou opacidade/transparência
- Funciona via web
- Chat agêntico com streaming token-a-token (assistente de acessibilidade que pensa e narra em tempo real com busca paralela via Tavily e Exa), com botão "Parar" que interrompe o turno (best-effort, `POST /chat/cancel`)
- Anexe uma imagem (screenshot de UI, PNG/JPEG/WEBP/GIF) no chat para o modelo analisar visualmente — útil pra apps nativos sem HTML ou pra confirmar visualmente um problema de contraste
- Interface chat-first: eventos de progresso dos agentes, anexos, perguntas de esclarecimento e links de download renderizados na conversa
- Análise de URL com JavaScript rendering completo via Playwright (SPAs, React, Angular, Vue, Next.js)
- Crawl de site inteiro: descobre e analisa todas as subpáginas automaticamente (limite configurável 1-50)
- **Batch Inference no crawl** (`POST /analyze/crawl/batch`): submete a análise de várias páginas como um job assíncrono no provider (OpenAI/Anthropic/Gemini, ~50% de desconto de custo), pra crawls grandes sem urgência — consulte o resultado depois via `GET /analyze/crawl/batch/{batch_id}`
- **Exportação SARIF 2.1.0**: gera relatórios em formato SARIF (`/export/sarif`) para integração direta com Pull Requests no GitHub Actions / GitLab CI
- **Servidor de Model Context Protocol (MCP)**: expõe ferramentas de análise de acessibilidade, geração de suítes de testes e links de Excel diretamente por stdio via FastMCP
- **Protocolo Agent-to-Agent (A2A v1.0 Linux Foundation)**: arquitetura Dual-Protocol que expõe a descoberta pública do Agent Card (`/.well-known/agent-card.json` e `/.well-known/agent.json`) e a API de delegação de tarefas assíncronas (`POST /a2a/v1/tasks`, `GET /a2a/v1/tasks/{id}`, `POST /a2a/v1/tasks/{id}/cancel`, `GET /a2a/v1/tasks/{id}/subscribe`) para federação par-a-par entre agentes de IA corporativos
- **Roteamento por Tier (Alto/Fast)**: no modo "Alto", o sistema seleciona automaticamente o melhor modelo recente e tool-capable do provider (tier alto, priorizando reasoning e janela de contexto) via `model_router.resolve_alto_model`; modelos que exigem créditos de uso extra em planos pagos (`requires_extra_usage=True`, como `claude-fable-5`) são preservados no catálogo para seleção explícita por ID, mas ignorados na resolução automática do modo "Alto" para evitar estourar o saldo do usuário; o classificador usa o tier rápido (`resolve_fast_model`, modelos flash/haiku/mini/lite). Provider-agnóstico, sem nomes fixos de modelos — o catálogo (dinâmico via `GET /v1/models`, fallback estático) é a fonte de verdade
- **Provider "Agentic Auto" (cascata)**: provider lógico que seleciona automaticamente o primeiro provider concreto com API key configurada (ordem: openai → anthropic → gemini → xai → ollama), resolvendo o par (provider, modelo) via `model_router.resolve_model_and_provider` e evitando configuração manual quando há mais de uma chave disponível
- **Cascata Automática de Failover (`_resolve_auto_fallback`)**: se o provedor primário falhar por falta de saldo (402), limite de requisições (429), chave expirada (401) ou indisponibilidade (500/503), o motor agêntico (`AIAgent`) aciona automaticamente a cascata para o próximo provedor configurado com API Key no ambiente, sem interromper o usuário
- **Formatador Central de Erros Humanizados (`error_formatter.py`)**: traduz 100% dos códigos de erro técnicos de LLMs e APIs (400, 401, 402, 403, 404, 429, 500, 502, 503, 504, timeouts, `RESOURCE_EXHAUSTED` do Gemini e erros de rede) em mensagens claras, empáticas e orientadas à ação em Português
- **Roteamento por Cascateamento (Model Cascading)**: otimiza custos rodando a auto-correção (Self-Healing) primeiro em modelos rápidos/baratos e escalando automaticamente para modelos de reasoning de ponta caso falhe nas validações do Axe-core no browser
- **Checklist Híbrido (Auto + Manual QA)**: combina o escaneamento automático com tarefas de QA manual guiadas e customizadas para os elementos da página (alt text, alvos de toque, ordem de foco)
- **Portões de Build no CI/CD**: script integrado de Git e workflow de GitHub Actions pronto para bloquear commits se houver violações críticas/graves de acessibilidade no código do projeto ou site de teste
- **Squad de acessibilidade**: o chat cria um `SquadPlan` por solicitação, com escopo, análise especializada, correção opcional, QA e documentação. O plano usa tarefas com dependências/estados, portões de aprovação e evidências; o evento SSE `squad_plan` atualiza o progresso na interface. A especificação completa está em [`docs/ARQUITETURA_SQUAD_ACESSIBILIDADE.md`](docs/ARQUITETURA_SQUAD_ACESSIBILIDADE.md).
- **Verificação de anúncios de leitor de tela contra a árvore de acessibilidade REAL** (`POST /analyze/screen-reader`, tool de chat `verify_screen_reader_announcements`): cruza a árvore de acessibilidade computada pelo motor real do navegador (Chromium/CDP via `page.accessibility.snapshot()` — a mesma API que NVDA/JAWS/Narrator consultam no Windows) contra regras determinísticas de nome acessível ausente ou genérico. Diferente do resto do pipeline (que estima problemas a partir do HTML bruto via LLM), aqui o achado é confirmado pelo próprio motor de acessibilidade do navegador. Se o NVDA real estiver rodando na máquina (`nvda_service.py`, DLL oficial `nvdaControllerClient.dll`), os achados podem ser lidos em voz alta para confirmação humana. Requer `BROWSERLESS_WS_URL` configurado.
- **Revisão de acessibilidade pré-desenvolvimento / shift-left** (`POST /analyze/design-review`, tool de chat `design_review`): único agente do projeto que não audita HTML/código já existente — lê um requisito, user story ou descrição de componente/fluxo em texto livre e antecipa riscos de acessibilidade (com critérios WCAG 2.2 prováveis, severidade, motivo específico e recomendação acionável) antes de qualquer linha de código ser escrita.
- **Criação automática de tickets em Jira e Azure DevOps** (`create_jira_issue`/`create_azure_devops_work_item` no chat, via `ticket_integrations.py`): abre issues/work items reais a partir de um achado de acessibilidade, com severidade mapeada para prioridade (Jira) ou `Microsoft.VSTS.Common.Severity` (Azure DevOps). Configuração via `JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`/`JIRA_PROJECT_KEY` ou `AZURE_DEVOPS_ORG`/`AZURE_DEVOPS_PROJECT`/`AZURE_DEVOPS_PAT`; sem credenciais, simula a criação (mesmo padrão de `create_github_issue`).


## Estrutura do projeto

```
qaaccessibility/
├── backend/
│   ├── src/
│   │   ├── agents/
│   │   │   ├── orchestrator/        # Coordena pipeline em paralelo
│   │   │   ├── perceiver/           # WCAG 1.x — alt text, contraste, cor
│   │   │   ├── operability/         # WCAG 2.x — teclado, foco, timing
│   │   │   ├── understandability/   # WCAG 3.x — linguagem, labels, erros
│   │   │   ├── robustness/          # WCAG 4.x — ARIA, name/role/value
│   │   │   ├── aria_specialist/     # WAI-ARIA — roles, estados, widgets, aria-prohibited-attr
│   │   │   ├── section508/          # ADA/Section 508 — requisitos US federais
│   │   │   ├── css_analyzer/        # CSS inline/embedded — outline, contraste, motion
│   │   │   ├── ajax_dynamic/        # Conteúdo dinâmico — ARIA live, focus management, SPA
│   │   │   ├── cognitive/           # Acessibilidade cognitiva — CAPTCHA, formularios, linguagem
│   │   │   ├── react_framework/     # React/JS — div onClick, Tailwind, target=_blank
│   │   │   ├── screen_reader/       # Screen readers — headings, landmarks, link text, IDs
│   │   │   ├── mobile_a11y/         # Mobile web — viewport, touch targets, reflow
│   │   │   ├── forms_a11y/          # Formularios — labels, required, aria-invalid, autocomplete
│   │   │   ├── widgets_a11y/        # ARIA widgets — dialog, tabs, accordion, combobox, carousel
│   │   │   ├── a11y_expert_reviewer/ # Remove falsos positivos, re-score por impacto AT real
│   │   │   ├── fixer/               # Corrige HTML com AST codemods e CSS @layer
│   │   │   ├── checklist/           # Gera checklist por princípio POUR
│   │   │   ├── reporter/            # Score 0-100 + resumo executivo
│   │   │   ├── vpat_reporter/       # VPAT WCAG 2.2 (conformidade enterprise/Section 508)
│   │   │   ├── test_generator/      # Suíte Playwright + axe-core para o CI
│   │   │   ├── wcag_semantics/      # Semântica HTML profunda — landmarks, headings, links, tabelas
│   │   │   ├── compliance_audit/    # Conformidade WCAG AA + Section 508 + EN 301 549
│   │   │   ├── agentic_ai_ui/       # Agentic AI — streaming, tool logs role="log", HITL alertdialog
│   │   │   ├── spatial_3d_xr/       # WebXR XAUR — 3D Canvas, spatial audio, gaze dwell, PAT DOM
│   │   │   ├── web_components/      # Web Components — FACE ElementInternals, shadowrootreferencetarget
│   │   │   ├── niche_domains/       # Niche domains — Passkeys SC 3.3.8/3.3.9, D3 sonification, Kiosks
│   │   │   ├── angular_framework/   # Angular — anti-padrões condicionais
│   │   │   ├── vue_framework/       # Vue — anti-padrões condicionais
│   │   │   ├── svelte_framework/    # Svelte 5/SvelteKit — anti-padrões condicionais
│   │   │   ├── tailwind_css/        # Tailwind CSS — anti-padrões condicionais
│   │   │   ├── visual_a11y/         # Análise visual quando há screenshot
│   │   │   ├── classifier/          # Classifica framework/stack do conteúdo analisado (tier rápido)
│   │   │   ├── clarifier/           # Detecta pedidos fora de escopo no chat e pede esclarecimento
│   │   │   ├── deep_research/       # Pesquisa aprofundada sob demanda (ferramenta do chat)
│   │   │   └── design_review/       # Shift-left: antecipa risco de acessibilidade em requisito/user story, antes do código existir
│   │   ├── routes/                  # FastAPI: analyze, fix, checklist, report, export/xlsx, export/sarif,
│   │   │                            # analyze/vpat, analyze/tests, analyze/screen-reader, analyze/design-review,
│   │   │                            # chat/stream (SSE), models
│   │   ├── services/                # llm_client (engine propria + retry estruturado),
│   │   │                            # chat_runtime (chat streaming) + chat_tools,
│   │   │                            # model_router (resolucao do modelo "Alto"),
│   │   │                            # mcp_server (6 tools, inclui describe_repository),
│   │   │                            # config_drift (Configuration Drift Detection), contrast_verifier,
│   │   │                            # xlsx_exporter, sarif_exporter, browser (Playwright), crawler
│   │   ├── middleware/              # Logging middleware
│   │   ├── config/                  # Settings + logging_config
│   │   ├── shared/                  # Modelos Pydantic compartilhados
│   │   │   └── i18n/                # Camada de tradução PT-BR (criteria_pt.py)
│   │   └── security/                # pii_guard, rate_limiter, dependencies
│   ├── AI_MODULE_SPEC.md
│   ├── setup.cfg
│   └── requirements.txt
├── web/                            # Chat-first (o assistente faz tudo)
│   ├── src/
│   │   ├── screens/                 # ChatScreen, SettingsScreen
│   │   ├── services/                # api.ts (settings) + chat.ts (streaming SSE + getModels)
│   │   ├── hooks/                   # useChat
│   │   └── design/                  # tokens + helpers
│   ├── App.tsx
│   ├── package.json
│   └── AI_MODULE_SPEC.md
├── tests/                          # Todos os testes em um lugar só
│   ├── backend/                    # pytest — agentes, services, rotas
│   │   ├── unit/                   #   (agents, services, routes, security)
│   │   └── integration/            #   rotas via TestClient
│   └── web/                        # Jest + Playwright (e2e + axe-core)
├── pytest.ini                      # config pytest (testpaths=tests/backend)
├── README.md
└── .env.example
```

## Squad de acessibilidade

A squad é a camada de coordenação do trabalho, mantendo o produto restrito à
acessibilidade digital. Product Owner, Scrum Master e Developers são as
accountabilities centrais; cliente, QA, especialista A11y, documentação,
Engineering Manager e Tech Lead apoiam o fluxo conforme a necessidade.

O runtime gera o plano no início do streaming, informa as etapas ao frontend e
aplica os portões antes de correção, validação e entrega. A execução dos
agentes especialistas continua no orquestrador, com paralelismo quando as
dependências permitem. O roteamento de provider/modelo continua no
`model_router`, separado da coordenação da squad.

O plano por turno já está integrado. Um quadro persistente de backlog,
reatribuição manual e histórico de cerimônias ainda não faz parte do produto;
essa limitação está registrada na especificação da arquitetura.

## Pipeline de agentes

```
OrchestratorAgent
├── [PARALELO — timeout 25s cada] PerceiverAgent         WCAG 1.x
├── [PARALELO] OperabilityAgent       WCAG 2.x
├── [PARALELO] UnderstandabilityAgent WCAG 3.x
├── [PARALELO] RobustnessAgent        WCAG 4.x
├── [PARALELO] ARIASpecialistAgent    WAI-ARIA (inclui aria-prohibited-attr)
├── [PARALELO] Section508Agent        ADA/Section 508
├── [PARALELO] CSSAnalyzerAgent       CSS inline/embedded
├── [PARALELO] AJAXDynamicAgent       Conteúdo dinâmico/AJAX
├── [PARALELO] CognitiveAgent         Acessibilidade cognitiva
├── [PARALELO] ScreenReaderAgent      Compatibilidade screen readers
├── [PARALELO] MobileA11yAgent        Acessibilidade mobile/touch
├── [PARALELO] FormsA11yAgent         Formulários e campos de dados
├── [PARALELO] WidgetsA11yAgent       ARIA widgets interativos
├── [PARALELO] WCAGSemanticsAgent     Semântica HTML profunda (landmarks, heading, links, tabelas, iframes)
├── [PARALELO] ComplianceAuditAgent   Conformidade WCAG AA + Section 508 + EN 301 549
├── [PARALELO] AgenticAIUIAgent       Interfaces de IA agêntica, live regions e modais HITL
├── [PARALELO] Spatial3D_XR_Agent     WebXR XAUR 2026, Canvas Three.js/Babylon.js PAT DOM
├── [PARALELO] WebComponentsAgent     Custom Elements FACE ElementInternals e shadowrootreferencetarget
├── [PARALELO] NicheDomainsAgent      Passkeys SC 3.3.8/3.3.9, Sonificação D3 e Kiosks ADA/EAA
├── [CONDICIONAL] ReactFrameworkAgent React/framework anti-patterns
├── [CONDICIONAL] AngularFrameworkAgent Angular framework anti-patterns
├── [CONDICIONAL] VueFrameworkAgent   Vue framework anti-patterns
├── [CONDICIONAL] SvelteFrameworkAgent Svelte 5/SvelteKit anti-patterns
├── [CONDICIONAL] TailwindCSSAgent    Tailwind CSS anti-patterns
├── [CONDICIONAL] VisualA11yAgent     Análise visual quando há screenshot
├── merge + deduplicate + guardrail(150 issues) + AgentMetrics
├── [SEQ] FixerAgent
├── [SEQ] ChecklistAgent
└── [SEQ] ReporterAgent
```

**Resiliência do pipeline:** cada agente é executado com `asyncio.wait_for(...)` e timeout configurável (`AGENT_TIMEOUT_SECONDS`, padrão 180s), com captura de exceções via `_timed()`. Uma falha isolada não afeta os demais agentes. O resultado `ANALYZE` inclui `agent_metrics: []` com `duration_ms`, `issues_found` e `success` por agente.

**Análise de projetos:** `/analyze/project` aceita múltiplos arquivos (HTML, CSS, JS, TS, TSX, Vue, Svelte). Monta contexto unificado anotado com limite de 400 KB. Ignora node_modules, .git, dist, build, .next. Retornado no mesmo contrato `AgentResult`.

## JavaScript Rendering com Playwright

A rota `/analyze/url` usa Playwright (Chromium headless) em vez de um simples fetch HTTP.
O browser abre a página, executa todo o JavaScript, aguarda `networkidle` e captura o HTML
completo do DOM. Garante que SPAs (React, Angular, Vue, Next.js) sejam analisados com
o conteúdo real renderizado, não com o HTML vazio do primeiro load.

Serviço: `backend/src/services/browser.py` — `fetch_rendered_html_and_screenshot(url)`

## Crawl de Site Inteiro

A rota `/analyze/crawl` recebe uma URL raiz e um limite de páginas (1-50, padrão 10).
O crawler visita cada página com Playwright, descobre links internos automaticamente,
e roda o pipeline de análise em cada página. O resultado consolida score global, total de issues
e detalhes por página com URL de origem anotada em cada issue.

Serviço: `backend/src/services/crawler.py` — `crawl_site(url, max_pages)`

Na UI atual, o usuário pede a análise pelo chat; o agente escolhe a ferramenta apropriada
(`/analyze/url`, `/analyze/crawl` ou tools do chat) conforme o pedido.

## Camada de i18n

O módulo `backend/src/shared/i18n/criteria_pt.py` é o único ponto de tradução de campos de acessibilidade.
Chamado pelo Orchestrator em ponto único, após deduplicação e guardrail.
Preenche `criterion_pt` (critério em PT-BR) e `severity_pt` (severidade em PT-BR) em todos os issues.
Os campos EN originais (`criterion`, `severity`) não são alterados — backward compatibility garantida.
Critérios sem tradução fazem fallback para o valor EN original.

## Interface Web — chat-first

O frontend atual concentra o fluxo em `ChatScreen`: o usuário envia URL, HTML, ZIP ou documentos,
e o assistente agêntico chama as ferramentas do backend durante a conversa. A UI mostra tokens da
resposta, fases do orchestrator, início/fim dos agentes, perguntas de esclarecimento e links de download.

`SettingsScreen` configura provider, chave de API, modelo (`alto` por padrão) e Base URL opcional.
`web/App.tsx` mantém navegação simples entre chat e configurações, skip link, landmark principal e
anúncios de mudança de tela.

As chaves salvas pela interface não são escritas em `.env`: no Windows, ficam
protegidas por DPAPI em `backend/.secrets.json`. Para expor o backend fora de
`127.0.0.1`, configure também `QA_API_TOKEN` e forneça o mesmo valor ao build web
como `EXPO_PUBLIC_QA_API_TOKEN`. Sem token, um bind não local falha ao iniciar.

O proxy local deve encaminhar todos os prefixos de API usados pela UI:
`/analyze`, `/fix`, `/report`, `/checklist`, `/health`, `/export`, `/settings`,
`/chat`, `/models`, `/preview` e `/webhook`.

## Artefatos gerados

Arquivos de cache, build e execução local não fazem parte da arquitetura-fonte do projeto:
`.expo/`, `web-build/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`,
`*.pid`, `node_modules/` e ambientes virtuais devem permanecer fora de versionamento.
O código-fonte fica em `backend/src`, `web/src`, `agent`, `tools` e os testes canônicos em `tests/`.

## Variáveis de ambiente

Ver `.env.example` para todas as variáveis necessárias.

### Modelo "Alto" (seleção automática)

`LLM_MODEL=alto` (padrão da tela de Configurações) ativa o roteamento automático:
o usuário só escolhe o **provedor** e a **chave de API**, e o backend resolve o
**melhor modelo recente e com suporte a ferramentas** daquele provedor. O catálogo
é live-first: consulta a API de modelos do provider e usa o catálogo estático local
(`agent/models_dev.py`) apenas como fallback offline. O ranking considera reasoning,
janela de contexto e custo. Modelos concretos continuam disponíveis como override
manual na UI.

## Mapa de contratos locais

Cada pasta de primeiro nível possui um `AI_MODULE_SPEC.md` obrigatório:
- `backend/AI_MODULE_SPEC.md`
- `web/AI_MODULE_SPEC.md`

## Executando o projeto

> **Pré-requisito:** crie `backend/.env` a partir de `.env.example`. Não há provider
> assumido por padrão — escolha um dos providers suportados (OpenAI, Anthropic,
> Gemini, xAI ou Ollama Cloud) e informe a chave de API na tela de **Configurações**
> (ou direto em `LLM_PROVIDER`/`LLM_API_KEY`). O modelo padrão é `alto` (seleção automática).

### Backend

Execute **a partir da raiz do repositório** (o módulo usa `backend.src.*`):

```powershell
# instalar dependências (uma vez)
pip install -r backend/requirements.txt

# subir o servidor (hot-reload)
$env:PYTHONPATH="C:\qaaccessibility"
python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8001 --reload --env-file backend/.env --access-log
```

O backend fica disponível em `http://localhost:8001`.
Em inicialização padrão via `python start_backend.py`, os logs persistentes ficam em `logs/backend.log` e `logs/backend.err.log`.

### Web

O frontend local usa o proxy estático em `web/proxy-server.js`, que serve `web/web-build`
e encaminha chamadas de API para o backend:

```bash
# instalar dependências (uma vez)
cd web
npm install

# voltar para a raiz e iniciar o proxy em http://localhost:3000
cd ..
python start_frontend.py
```

Em inicialização padrão via `python start_frontend.py`, os logs persistentes ficam em `logs/frontend.log` e `logs/frontend.err.log`.

Para desenvolvimento com hot-reload:

```bash
cd web
npx expo start --web
```

O chat usa `EXPO_PUBLIC_API_URL` quando definido; sem essa variável, aponta para o backend
no mesmo host com porta `8001`.

### Solução de Problemas (Troubleshooting)

#### 1. Erro `ModuleNotFoundError: No module named 'run_agent'`
`run_agent.py` (engine agêntica própria do projeto) fica na raiz do repositório. Se você rodar o uvicorn diretamente e encontrar esse erro, configure `PYTHONPATH` para incluir a raiz do projeto:

* **No Windows (PowerShell):**
  ```powershell
  $env:PYTHONPATH="C:\qaaccessibility"
  python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8001 --env-file backend/.env
  ```
* **No Windows (CMD):**
  ```cmd
  set PYTHONPATH=C:\qaaccessibility
  python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8001 --env-file backend/.env
  ```
* **No Linux/macOS:**
  ```bash
  export PYTHONPATH="/caminho/para/qaaccessibility"
  python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8001 --env-file backend/.env
  ```

#### 2. Erro `ERR_CONNECTION_REFUSED` ao tentar acessar http://localhost:3000
Este erro indica que o backend ou o servidor de proxy do frontend não estão em execução.
* Certifique-se de que ambos os servidores foram iniciados.
* Você pode usar os scripts de automação inclusos na raiz do projeto:
  1. Inicie o backend: `python start_backend.py` (roda na porta `8001`).
  2. Inicie o frontend/proxy: `python start_frontend.py` (roda na porta `3000` e gerencia o proxy para a porta `8001`).
  3. Consulte `logs/` para reconstruir interações mesmo após fechar e reabrir o software.
* **Nota sobre Ambientes Sandbox/Agentes:** Em ambientes sandbox, processos de segundo plano criados de forma independente podem ser finalizados automaticamente após a conclusão do turno do agente. Se isso ocorrer, inicie-os como tarefas de background gerenciadas (usando o runner do sistema) ou mantenha os processos rodando no terminal ativo.

#### 3. Mudança de Provedores e Salvamento de API Key nas Configurações
Se você trocar de provedor de IA na tela de Configurações, a chave do provedor anterior (representada pela máscara `••••••••••••••••••••••••`) será automaticamente limpa. Isso força a inserção de uma nova chave de API válida para o novo provedor selecionado.
* **Por que isso ocorre?** O sistema utiliza uma única variável global `LLM_API_KEY` por vez no backend. A máscara do provedor anterior é limpa ao alternar de provedor para evitar que o frontend envie a máscara como a chave de API real ou que o backend mantenha uma chave inválida de outro provedor.
* **Nota sobre URLs de API:** A URL base das requisições de configuração é resolvida de forma dinâmica a partir da porta em execução (ex: porta `8001`), evitando falhas em ambientes de desenvolvimento (Expo) ou de produção.

### Testes
```bash
# Backend (a partir da raiz do repo)
python -m pytest

# Web
cd tests/web
npm test

# E2E Web (Playwright + axe-core)
cd tests/web/e2e && npx playwright test
```

### Verificação estática + dinâmica (rodar antes de qualquer entrega)

Três ferramentas com pontos cegos diferentes — nenhuma sozinha basta:

| Ferramenta | Tipo | O que pega | O que NÃO pega |
|---|---|---|---|
| `ruff` (Python) / `eslint` (web) | Lint (análise de padrão de texto) | Import nunca usado, nome referenciado sem import (`NameError` real), `except: pass` engolindo erro, código morto | Lógica errada, comportamento em runtime |
| `mypy` (Python) / `tsc` (web) | Tipagem estática (análise sem executar) | `None` inesperado, argumento/atributo incompatível, dois tipos diferentes na mesma variável | Se o código roda mas devolve resultado errado; qualquer coisa escondida atrás de `Any`/`# type: ignore` |
| `pytest` (Python) / `jest` (web) | Teste automatizado (análise dinâmica — executa de verdade) | Bugs reais de runtime, comportamento de SDK que a tipagem não modela | Só cobre o que foi escrito; não escala pra 100% do código sozinho |

Comandos (a partir da raiz do repo, backend Python):
```bash
python -m ruff check backend run_agent.py agent tests
python -m mypy backend run_agent.py agent   # usa mypy.ini na raiz
python -m pytest
```

Comandos (dentro de `web/`):
```bash
npx tsc --noEmit -p .
npm run lint
npm test
```

Fluxo ao achar um apontamento do ruff/mypy/eslint/tsc: **não é pra suprimir de cara**.
1. Ler o código ao redor do apontamento e decidir: é um bug real, ou o verificador está sendo raso (ex.: SDK externo com stub mais rígido que o comportamento real)?
2. Se for bug real, corrigir na causa raiz (não só na linha apontada) e escrever um teste que executa o código de verdade e prova o bug antes/depois da correção.
3. Se for falso positivo confirmado, `# type: ignore[código-específico]` ou `# noqa: CÓDIGO` com um comentário explicando o porquê — nunca uma supressão em branco.

`mypy.ini` na raiz configura `explicit_package_bases`, o plugin do pydantic e os módulos sem stub (`docx`, `headroom`, `opentelemetry.instrumentation.fastapi`) como ignorados. `ruff.toml` na raiz seleciona `E, W, F, I, N, UP, B, SIM`. `web/.eslintrc.js` estende `eslint-config-expo@sdk-51` (a única versão publicada compatível com Expo SDK 51) mais `env: { browser: true }`, já que o app roda condicionalmente no navegador nos mesmos arquivos `.tsx` do nativo.

## CI/CD

Pipeline GitHub Actions em `.github/workflows/accessibility-ci.yml`:

| Job                    | Trigger          | O que executa                                      |
|------------------------|------------------|-----------------------------------------------------|
| code-quality           | push/PR          | Quality gate: proibições README + ruff + mypy type-check (usando `mypy.ini` da raiz) + `pip-audit` (Dependency Compliance, bloqueante) |
| backend-tests          | push/PR          | pytest do pipeline seletivo de agentes + coverage ≥70% (`--ignore=integration`) |
| web-unit-tests         | push/PR          | Jest unit tests (`tests/web/`)                     |
| web-app-quality        | push/PR          | tsc + eslint no app (`web/`) + `npm audit` (Dependency Compliance, não-bloqueante — dívida pré-existente do toolchain Expo/Metro) |
| web-e2e-tests          | push/PR          | Playwright — teclado, ARIA live, contraste, axe    |
| lighthouse-audit       | PRs only         | Accessibility ≥ 0.90, Best-Practices ≥ 0.85       |
| github-a11y-scanner    | PRs → main only  | github/accessibility-scanner@v2 nas rotas da app   |

Threshold Lighthouse configurado em `.lighthouserc.json`.
