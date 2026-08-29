# AI_MODULE_SPEC — Backend

## Responsabilidade
Servidor FastAPI que expõe a API REST do QA Accessibility e orquestra o pipeline
de sub-agentes especializados para análise, correção e geração de checklists.

## Modelo de IA
- Engine: própria do projeto (`run_agent.AIAgent`, raiz do repositório) — engine agêntica nativa com conversation loop, tool-calling e compressão de histórico. Não depende de nenhuma biblioteca externa instalada fora deste repositório.
- Providers suportados: `agentic` (lógico), `openai`, `anthropic`, `gemini`, `xai`, `ollama-cloud`
  - **`agentic` (Agentic Auto)** é um provider **lógico**, não conecta a um endpoint próprio: resolve para o primeiro provider concreto com API key configurada, em cascata (ordem: openai → anthropic → gemini → xai → ollama-cloud/ollama). Implementado em `model_router.resolve_model_and_provider` (sentinela `"agentic"`/`"auto"`), devolvendo o par `(concrete_provider, resolved_model)` para garantir roteamento perfeito. Exposto em primeiro lugar na rota `/models` (`CHAT_PROVIDERS`) e na UI como opção recomendada/default. Sem API key em nenhum provider → cai no default vigente do `AIAgent`.
  - **Providers concretos** (`openai`, `anthropic`, `gemini`, `xai`, `ollama-cloud`): cada um conecta ao seu endpoint oficial. A ordem em `CHAT_PROVIDERS` (`backend/src/routes/models_route.py`) é a fonte de verdade que a UI espelha (`web/src/screens/SettingsScreen.tsx`).
- Model default: `alto` (seleção automática do melhor modelo agêntico do provider)
- Provider default: vazio — nenhum provider é assumido sem configuração explícita (UI/Configurações ou `LLM_PROVIDER`)
- Configuração via env: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` (`LLM_BASE_URL` é override avançado opcional do endpoint)
- Failover e Cascata Automática (`_resolve_auto_fallback` no `AIAgent`): quando o provedor primário falhar (por saldo esgotado/402, rate limit/429 ou erro de servidor/500/503), o motor agêntico calcula dinamicamente o próximo provedor ativo com chave de API e re-executa a requisição transparente e automaticamente.
- Formatador Central de Erros (`backend/src/shared/error_formatter.py`): centraliza a tradução humanizada de todos os erros de IA (400, 401, 402, 403, 404, 429, 500, 502, 503, 504, 529, timeouts, `RESOURCE_EXHAUSTED` e falhas de rede) em mensagens amigáveis em Português.
- Modelo "Alto" (`LLM_MODEL=alto`, padrão da UI): seleção automática do melhor modelo recente e **com suporte a ferramentas** do provider. Resolvido em `backend/src/services/model_router.py` (`resolve_alto_model`/`resolve_model`) a partir de `agent.models_dev.list_agentic_models` (tool_call=True, sem ruído), ranqueado por (reasoning, janela de contexto, menor custo). Cacheado por processo (`clear_cache()` no `refresh_settings`). Sentinela `"alto"` (ou vazio em `chat_runtime`) dispara a resolução; valor concreto passa direto. Sem catálogo (offline) → cai no default vigente. Aplica-se a `call_llm` (sub-agentes) e `chat_runtime` (chat). A rota `/models` oferece `"alto"` como primeira opção por provider. O classificador usa o tier rápido (`resolve_fast_model`) e os demais especialistas usam o tier alto, sem nomes fixos de modelos por provider.
  - **Catálogo dinâmico (2026-07-28):** `agent/models_dev.py` agora consulta as APIs reais dos providers via `fetch_live_models(provider, api_key, base_url)` — `GET /v1/models` (OpenAI, Anthropic, xAI, Ollama) e `GET /v1beta/models` (Gemini). A metadata retornada (capabilities, token limits, thinking) enriquece o `ModelInfo` em runtime. O catálogo estático `_CATALOG` permanece como **fallback gracioso offline** (padrão 2026: live-first, static-fallback). `resolve_alto_model`/`resolve_fast_model` usam `list_agentic_models` que prefere o catálogo live quando disponível, caindo para o estático sem quebrar. A "Limitação conhecida" do catálogo fixo está **resolvida**.
- Service: `backend/src/services/llm_client.py` — wrapper `call_llm()` com `asyncio.to_thread(agent.run_conversation)`
- Contrato do `call_llm`: `temperature` é repassada ao modelo via `request_overrides={"temperature": ...}` (canal mesclado no payload pelo `AIAgent`); `max_tokens` via construtor do `AIAgent`
- **Self-heal de temperatura:** modelos de reasoning estritos (ex.: OpenAI gpt-5/o-series) rejeitam `temperature` com HTTP 400. O `call_llm` detecta a rejeição via `_provider_rejected_temperature` (`llm_client.py`) — um detector técnico local, baseado no nome do parâmetro + marcador de "não suportado" na mensagem de erro do provider, sem vocabulário de domínio — e **refaz a chamada UMA vez sem `temperature`**, deixando o provider aplicar seu próprio default. Provider-agnóstico, sem lista de modelos hardcoded; relevante porque o "Alto" prioriza modelos com reasoning.
- Sub-agentes rodam como **filhos isolados de `AIAgent`**: cada chamada cria um `AIAgent` filho com contexto isolado (`task_id` próprio `a11y-<label>-<uuid>`), prompt focado via `ephemeral_system_prompt`, `log_prefix` por especialista, `quiet_mode=True`
- `enabled_toolsets=[]` (default) — leaf **sem tools**: o schema de ferramentas não é enviado ao modelo (economia de tokens) e o subagente não emite tool-calls espúrias no lugar do JSON
- `max_iterations=1` (default) — classificador single-shot (single response por especialista)
- `call_llm(toolsets=[...], max_iterations=N)` — opt-in para subagente com tools de domínio (loop tool→resposta)
- Chat agentico (`backend/src/services/chat_runtime.py`): usa somente os toolsets controlados `[a11y_chat, clarify]`. O toolset genérico `web` fica desabilitado para evitar `web_extract` repetido depois de uma auditoria já concluída. Buscas ficam nas tools próprias `tavily_search` e `exa_search`, registradas dentro de `a11y_chat`.
- Apresentação acessível no cliente: streaming visual silencioso, um anúncio “Digitando...” e a resposta final completa uma vez; ferramentas equivalentes agrupadas durante todo o turno; duração única do turno; conectores/MCP identificados; mídia condicionada à capacidade e apresentada diretamente, sem confirmação redundante.
- Toolset `clarify` (`chat_tools.py`): expõe a tool `clarify(question, options)`, que as regras 12 (plano/aprovação) e 13 (checkpoint de remediação) do system prompt exigem. Registrada com `needs_clarify_callback=true`: o `run_local_tool` entrega a ela o mesmo callback de clarify do agente, que emite o evento SSE e bloqueia até `POST /chat/clarify`. Sem callback, a tool devolve erro explícito em vez de responder sozinha.
- Interruptibilidade (`chat_progress.py` + `POST /chat/cancel`): cada turno recebe um token de cancelamento (evento SSE `stream_id`, primeiro evento do stream). `POST /chat/cancel {stream_id}` sinaliza um `asyncio.Event` que `stream_chat` aguarda em paralelo com a fila de eventos (`asyncio.wait`); ao ser sinalizado, o servidor para de entregar eventos ao cliente e cancela a task best-effort (não aborta uma chamada HTTP síncrona já em andamento no provider — limitação do SDK, não do projeto). Frontend (`useChat.ts::stop()`) já fechava a conexão via `abort()`; agora também dispara `sendCancel` sem bloquear a UI.
- Squad de acessibilidade (`backend/src/agents/squad/` + `chat_runtime.py`): cada turno gera um `SquadPlan` com tarefas de escopo, análise, correção opcional, QA e documentação. O plano usa dependências, estados e quality gates e é emitido como evento SSE `squad_plan`. A squad coordena o fluxo; não escolhe provider/modelo e não substitui o `OrchestratorAgent` nem a delegação A2A.
- Response Caching (`response_cache.py`): cache exato (hash do prompt completo, não semântico) para os leaf subagents single-shot sem tools — mesmo escopo do `response_schema`. TTL configurável (`A11Y_RESPONSE_CACHE_TTL_SECONDS`, default 300s), desativável (`A11Y_RESPONSE_CACHE_ENABLED=false`). Nunca aplicado a chat/tools. Deliberadamente exact-match (não por similaridade de embeddings): uma cache semântica arriscaria confundir HTML "parecido" com HTML que mudou de forma relevante para acessibilidade.
- Context Drift Detection + Reflection/Replanning (`run_agent.py::AIAgent._check_context_drift`): nenhum provider expõe sinal nativo de "o modelo perdeu o fio" (só `finish_reason`/`stop_reason` por limite de tokens). Detecção por repetição (mesma tool+args+resultado 3x numa janela de 6) dispara UMA reflexão anexada ao resultado da tool que volta pro modelo — funciona nos 4 caminhos de provider sem tocar na lógica de mensagens de cada um, porque toda tool call passa por `_execute_tool_calls`. `context_drift_callback` dá transparência ao chat.
- Multimodal Processing (`run_agent.py::_*_user_content`/`_gemini_user_parts`, `chat_runtime.py::extract_message_with_images`): imagens (PNG/JPEG/WEBP/GIF) do turno atual do chat viram content block nativo de imagem no provider (shape confirmado por pesquisa: `input_image` OpenAI/xAI, `image`+`source` Anthropic, `inlineData` Gemini, `image_url` Ollama), não mais texto extraído. Histórico nunca reenvia imagens de turnos passados. Fallback gracioso: se o provider rejeitar a imagem, `run_conversation` refaz UMA vez sem ela (nota explicativa) antes de cair pro provider de reserva — nenhum provider documenta como saber de antemão se o modelo aceita imagem.
- Batch Inference (`batch_inference.py` + `batch_collector.py` + `batch_job_store.py`): `submit_batch`/`poll_batch`/`fetch_batch_results` para OpenAI, Anthropic e Gemini (os 3 com desconto de ~50% documentado; xAI/Ollama sem Batch API com desconto claro, levantam `BatchNotSupportedError`). Integrado ao crawl via `POST /analyze/crawl/batch` + `GET /analyze/crawl/batch/{batch_id}`: uma passada de coleta (`orchestrate(..., batch_collect=True)`) roda o pipeline normal, mas `call_llm` grava a chamada em vez de ligar pro provider; os resultados reais do batch são inseridos no `response_cache` sob a mesma chave e o pipeline roda de novo — cada um dos 25 agentes faz seu próprio parsing sem nenhuma alteração de código. Ver VERIFICATION.md §21 para o racional completo.
- Cada turno devolve `result["usage"] = {input_tokens, output_tokens, total_tokens}`, normalizado a partir do shape de cada provider (Responses `input/output_tokens`, Chat Completions `prompt/completion_tokens`, Gemini `*_token_count`) e somado ao longo das iterações de tool-calling.
- `reasoning_effort` é encaminhado nos quatro caminhos de provider. No Anthropic não existe esse campo: o valor vira `thinking` (`{"type": "disabled"}` para `none`, ou um orçamento proporcional a `max_tokens`), só em modelos marcados como `reasoning` no catálogo, e `temperature` é omitida quando o thinking fica ligado porque a API a rejeita nesse modo.
- Triagem do clarifier no chat: `out_of_scope` responde a recusa de escopo e `needs_clarification` devolve ao usuário a pergunta gerada pelo próprio clarifier (com fallback quando ele não gera nenhuma). Ambos encerram o turno sem chamar o modelo agentico.
- Cache da última análise (`last_analysis_store.py`): um slot em memória **por conversa** (`conversation_id`) e um arquivo por conversa em `%TEMP%`, com o id sanitizado no nome. A sessão corrente viaja por ContextVar (definida em `stream_chat`), então `generate_vpat`/`generate_test_suite`/`fix_and_zip_files` leem sempre a análise da própria conversa. Fora do chat vale a sessão `default`.
- Base de conhecimento do chat (`a11y_knowledge.py`): RAG híbrido (BM25 + embeddings + fusão RRF + rerank) sobre o corpus `_CORPUS_FILES` — `a11y_reference.md` (guia de referência escrito à mão: AccName, APG, i18n/RTL, data grids, guia de teste por leitor de tela) e `agent_knowledge.md` (**gerado** por `scripts/generate_agent_knowledge.py` a partir do `SYSTEM_PROMPT` dos 25 agentes de análise — nunca editar à mão). `build_reference_block(message)` injeta o trecho relevante no turno do chat. Resolve a divergência entre "o que os agentes de análise sabem" e "o que o chat sabe": qualquer mudança num `SYSTEM_PROMPT` de agente flui para o chat rodando o gerador de novo. `tests/backend/unit/test_agent_knowledge_sync.py` falha se `agent_knowledge.md` divergir do que o gerador produziria agora.
- Regra 18 do system prompt do chat (`chat_runtime.py`): antes de dar passo a passo de teste com leitor de tela, o chat deve saber SO/dispositivo/navegador/leitor de tela do usuário (perguntar se não souber) e usar o pareamento correto (ex.: VoiceOver só é confiável com Safari) em vez de instrução genérica — guia completo em `a11y_reference.md` §11.
- Observabilidade: `telemetry.agent_span()` embrulha o turno de chat (`agent.chat_turn`, com provider/modelo/conversa e tokens) e cada execução de tool (`agent.tool`). Sem `OTEL_EXPORTER_OTLP_ENDPOINT` os spans são no-op.  - **Online scoring de traces (2026-07-28):** `telemetry.score_trace(trace_text, criteria)` pontua spans de produção com LLM-as-judge (rubric: factual accuracy, completeness, tool efficiency). Padrão Braintrust/DeepEval 2026: o scorer é assíncrono, não impacta latência, e usa o mesmo `call_llm` do projeto. Resultado anotado no span como atributo `eval.score`. Sem provider configurado → no-op. Permite detectar regressões em produção que os evals offline não cobrem.
  - **End-state evals (2026-07-28):** `tests/backend/unit/test_end_state_evals.py` valida o **estado final** de fluxos multi-turn (análise → fix → re-audit), não cada step isolado. Padrão Anthropic 2026 ("evaluate final state, not every step"): o agente pode tomar caminhos diferentes, mas o estado final deve satisfazer invariantes (issues corrigidas, score melhorou, sem regressões). Casos: `EC001` (fix endereça issue reportada), `EC002` (re-audit não regressa), `EC003` (VPAT gerado reflete issues resolvidas).- Superfícies oficiais por provider:
  - OpenAI e xAI usam Responses (`input`, `max_output_tokens`, tools planas e `function_call_output`). O loop é stateless (`store=false`) e reenvia os items nativos; reasoning/thought não é enviado à UI.
  - Gemini usa Interactions, preserva `previous_interaction_id` no loop de ferramentas e entre turnos por conversa (cache local com TTL de uma hora), reenvia tools/config em cada continuação e expõe somente deltas de texto.
  - Anthropic usa Messages com blocos `tool_use`/`tool_result`.
  - Ollama Cloud mantém Chat Completions porque é a superfície compatível documentada por esse endpoint.
- Ferramentas com gravação ou efeito externo possuem `requires_approval=true`. A pergunta apresenta os argumentos exatos com segredos redigidos e um digest SHA-256; sem callback ou sem aprovação explícita, o handler não é executado.
- Credenciais são persistidas no cofre local `backend/.secrets.json`, protegido por DPAPI do usuário atual no Windows. `.env` contém somente configuração não secreta; instalações antigas migram automaticamente ambos os arquivos `.env`.
- A API liga em loopback por padrão. Bind fora de loopback exige `QA_API_TOKEN`; quando configurado, o frontend envia `X-QA-Accessibility-Token` e todas as rotas privadas o validam. `/health` e o webhook com autenticação própria permanecem públicos nesse middleware.

### Configuration Drift Detection (`backend/src/services/config_drift.py`)
- `log_config_drift()` roda no startup do backend (`main.py`) e loga um WARNING por divergencia encontrada; nunca levanta excecao (check informativo, nao um gate)
- Cobre a classe de bug encontrada em 2026-08-01: uma var de override de endpoint (`OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `GEMINI_BASE_URL`, `XAI_BASE_URL`, `OLLAMA_BASE_URL`, `OLLAMA_CLOUD_BASE_URL`) ativa no ambiente do processo mas ausente de `backend/.env` -- o endpoint resolvido por `agent/models_dev.py::_resolve_endpoint` diverge silenciosamente do que o `.env` do projeto documenta
- Tambem acusa chaves com prefixo do projeto (`LLM_`, `CHAT_LLM_`, `QA_`, `A11Y_`, `AGENT_TIMEOUT_`) presentes em `backend/.env` mas nao documentadas em `.env.example` -- configuracao obsoleta ou nunca documentada

### Servidor MCP (`backend/src/services/mcp_server.py`)
- 6 ferramentas via stdio: `get_rendered_page`, `run_axe_audit`, `export_xlsx`, `analyze_page_full`, `analyze_site_full`, `describe_repository`
- **`describe_repository` (Repository Intelligence):** devolve `docs/REPO_MAP.json` -- indice estruturado dos ~34 sub-agentes (nome, arquivo, entry-point `run_*`/`orchestrate`, prefixo de ID de issue, diretriz) gerado por `scripts/generate_repo_map.py` a partir do proprio codigo-fonte (regex sobre `def run_*`, `"id": "prefixo-<n>"`, docstring/SYSTEM_PROMPT). Permite a um agente cliente (Claude Desktop, VS Code Copilot, outra sessao de Claude Code) descobrir "quem cobre ARIA?" sem ler os 34 modulos. `docs/REPO_MAP.json` e artefato gerado (nunca editado a mao); `tests/backend/unit/test_repo_map.py::test_committed_repo_map_matches_generator_output` falha se o JSON commitado divergir do que o gerador produziria agora -- previne que o indice fique obsoleto em silencio

### Protocolo Agent-to-Agent (A2A v1.0 Linux Foundation) (`backend/src/services/a2a_service.py` & `backend/src/routes/a2a_route.py`)
- **Arquitetura Dual-Protocol:** o projeto expõe o protocolo vertical MCP (servidor FastMCP `mcp_server.py` para ferramentas Agent-to-Tool) e o protocolo horizontal A2A (Linux Foundation v1.0 para descoberta e delegação Agent-to-Agent).
- **Agent Card Discovery:** endpoints públicos `GET /.well-known/agent-card.json` e `GET /.well-known/agent.json` retornando o esquema JSON estrito A2A de descoberta de agente, descrevendo as skills da plataforma (`accessibility_analysis`, `self_healing_fix`, `vpat_generation`, `playwright_test_generation`, `sarif_export`), endpoints, suporte a streaming, modos de input/output e rate limits.
- **Delegação de Tarefas A2A (`/a2a/v1/tasks`):**
  - `POST /a2a/v1/tasks`: aceita requisições de delegação de tarefas de agentes pares externos com `skill_id`, `input`, `parameters` e `stream`. Retorna `202 Accepted` / `200 OK` com `task_id` e estado inicial `working`.
  - `GET /a2a/v1/tasks/{id}`: retorna o estado (`submitted`, `working`, `completed`, `failed`, `canceled`), progresso (0.0 a 1.0), payload de saída (`output`) e métricas.
  - `POST /a2a/v1/tasks/{id}/cancel`: cancela graciosamente uma tarefa em andamento.
  - `GET /a2a/v1/tasks/{id}/subscribe`: streaming em tempo real via Server-Sent Events (SSE) dos eventos de progresso da tarefa (`TaskStatusUpdateEvent`, `TaskOutputChunkEvent`).

### Toolset de domínio `a11y_tools` (`backend/src/services/a11y_domain_tools.py`)
- Registrado no `tools/registry.py` deste projeto via `registry.register()` (import-time, side-effect)
- `compute_contrast(foreground, background)` — cálculo determinístico do ratio de contraste WCAG (1.4.3 / 1.4.11) em Python puro; retorna ratio exato + veredicto AA/AAA normal/large. Tira a alucinação do LLM em contraste
- **Estado atual:** registrada e testada. Ativável via os params opt-in acima (`call_llm(toolsets=["a11y_tools"], max_iterations>1)`) nos providers que suportam o round-trip multi-turn de tool-calling. No caminho single-shot (default) o toolset fica dormente — o cálculo determinístico de contraste roda no Orchestrator (abaixo)

### Verificação determinística de contraste (`backend/src/services/contrast_verifier.py`)
- `verify_contrast_issues(issues)` roda no Orchestrator após o expert review, **sem depender de tool-call** (cálculo em Python puro, robusto em qualquer provider)
- Para cada issue 1.4.3 / 1.4.11, extrai cores (hex e rgb/rgba) do texto do issue. Como o ratio é simétrico, a ordem fg/bg é irrelevante
- **Conservador:** só age com EXATAMENTE 2 cores parseáveis. Com 0/1/3+ cores deixa o issue intacto (nunca dropa por ambiguidade)
- Ratio ≥ limite → remove falso positivo; ratio < limite → mantém e anota `[Contraste verificado: X:1 (limite Y:1)]` em `why_technical`
- Limites: 1.4.11 = 3.0; 1.4.3 = 4.5 (AA) / 7.0 (AAA)
- **Caminho CSS-fonte (recall):** quando o texto do issue não tem 2 cores, o verifier recebe o `source_html` e extrai o par cor+fundo da regra CSS cujo seletor casa o `element` do issue. Modo **anotação-apenas** (`[Contraste verificado (CSS): X:1 ...]`) — **nunca remove** (matching de seletor é best-effort; drop seria arriscado). Só age quando EXATAMENTE uma regra casa (guarda de ambiguidade)
- Resumo dos modos: texto com 2 cores → pode **remover** falso positivo; CSS-fonte → só **anota**. Em ambiguidade ou sem match, no-op seguro
- Regra: nunca chamar API diretamente — sempre via `run_agent.AIAgent`

---

## Pipeline de Sub-Agentes (Especialistas por Domínio)

O Orchestrator executa sub-agentes de análise em **paralelo controlado**,
com timeout individual configurável via `_timed()` e limite de concorrência por
`A11Y_MAX_CONCURRENT_AGENTS`. O roteamento é seletivo: agentes base WCAG rodam
sempre; especialistas condicionais entram apenas por evidência estrutural do
HTML (formulários, CSS, scripts, widgets ARIA, responsividade); agentes de
framework (`react_framework`, `angular_framework`, `vue_framework`, `svelte_framework`,
`tailwind_css`) entram somente conforme o classificador; e `visual_a11y` entra
quando há screenshot. Se o classificador falhar, frameworks são pulados em vez
de serem chamados no escuro. Os logs registram idioma, agentes selecionados,
agentes pulados e o motivo de cada decisão. Exceções isoladas não interrompem o
pipeline. O resultado ANALYZE inclui `agent_metrics` com `duration_ms`,
`issues_found` e `success` por agente.

**Ajuste de `A11Y_MAX_CONCURRENT_AGENTS` por plano do provider** (pesquisa 2026-08-10,
motivada por uma análise real via Ollama Cloud levando ~17min): o default (3) é
conservador para caber no plano Free do Ollama Cloud (1 modelo concorrente por
conta). Contas Pro suportam até 3 concorrentes e Max até 10 (limites por nível de
peso do modelo, resetados a cada 5h/7 dias — não é um teto fixo de requests/tokens).
Subir esse valor SEM confirmar o tier da conta é arriscado: em vez de acelerar,
pode causar 429/fila em contas Free. Quem tiver plano Pro/Max e quiser análises
mais rápidas pode elevar a env var (`A11Y_MAX_CONCURRENT_AGENTS=6` ou mais) e
observar os logs de `agent_metrics`/erros de rate limit antes de manter o valor.

Importante: não existe escalada automática para o conjunto completo quando o
classificador falha. Nessa situação o Orchestrator continua com os agentes base
e os condicionais detectados por estrutura do HTML, mas pula frameworks sem
evidência.

```
OrchestratorAgent
├── [PARALELO — 25s timeout] PerceiverAgent         WCAG 1.x
├── [PARALELO] OperabilityAgent       WCAG 2.x
├── [PARALELO] UnderstandabilityAgent WCAG 3.x
├── [PARALELO] RobustnessAgent        WCAG 4.x
├── [PARALELO] ARIASpecialistAgent    WAI-ARIA
├── [PARALELO] Section508Agent        ADA/Section 508
├── [PARALELO] CSSAnalyzerAgent       CSS inline/embedded
├── [PARALELO] AJAXDynamicAgent       Conteúdo dinâmico/AJAX
├── [PARALELO] CognitiveAgent         Acessibilidade cognitiva
├── [PARALELO] ScreenReaderAgent      Compatibilidade screen readers
├── [PARALELO] MobileA11yAgent        Acessibilidade mobile/touch
├── [PARALELO] FormsA11yAgent         Formulários e campos de dados
├── [PARALELO] WidgetsA11yAgent       ARIA widgets interativos
├── [PARALELO] WCAGSemanticsAgent     Semântica HTML profunda (landmarks, headings, tabelas, iframes)
├── [PARALELO] ComplianceAuditAgent   Conformidade WCAG AA + Section 508 + EN 301 549
├── [CONDICIONAL] ReactFrameworkAgent React/framework anti-patterns
├── [CONDICIONAL] AngularFrameworkAgent Angular framework anti-patterns
├── [CONDICIONAL] VueFrameworkAgent   Vue framework anti-patterns
├── [CONDICIONAL] SvelteFrameworkAgent Svelte 5/SvelteKit anti-patterns
├── [CONDICIONAL] TailwindCSSAgent    Tailwind CSS anti-patterns
├── [CONDICIONAL] VisualA11yAgent     Análise visual quando há screenshot
│
├── [MERGE] _deduplicate_issues()     Remove duplicatas por criterion+element
├── [LOOP, ≤2 rodadas] DelegationCoordinatorAgent  Decide via LLM se agente pulado deve ser chamado
│    └── (se sim) roda o agente delegado, mescla issues, repete até convergir/backstop
├── [OPCIONAL] GapResearchAgent       Verifica issues de baixa confiança via deep_research (fontes normativas reais)
├── [GUARDRAIL] MAX_ISSUES = 150
├── [METRICS] AgentMetrics por agente (duration_ms, issues_found, success, delegated_by)
├── [OBSERVÁVEL] pipeline_graph        nós+arestas explícitos da topologia real desta análise
│
├── [SEQUENCIAL] a11y_expert_reviewer  Revisão holística + memória de lições (lessons_store.py)
├── [SEQUENCIAL] FixerAgent
├── [SEQUENCIAL] ChecklistAgent
└── [SEQUENCIAL] ReporterAgent
```

### Delegação dinâmica agente-a-agente (`delegation_coordinator.py`) e grafo explícito

Após a rodada 1 (fan-out estático por evidência estrutural), um `DelegationCoordinatorAgent`
lê os achados reais e a lista de agentes pulados, e decide via LLM (nunca regra fixa) se algum
agente pulado deveria ser chamado mesmo assim. Roda em loop limitado por
`MAX_DELEGATION_ROUNDS=2` (backstop real, nunca aberto) — para quando o coordenador converge
(nada mais a delegar) ou o limite é atingido. Cada delegação vira uma aresta explícita no
`pipeline_graph` retornado em `AgentResult.data["pipeline_graph"]` (`{"nodes": [...],
"edges": [...]}`), com o estado de cada agente (`selected`/`skipped`/`delegated`) e o motivo —
dado observável, não só efeito colateral em log (ver `_build_pipeline_graph`).

### Verificação automática de lacuna (`gap_research.py`) e memória de lições (`lessons_store.py`)

Achados com `confidence=low` disparam automaticamente uma pesquisa normativa real via
`deep_research` (bounded, `MAX_GAP_RESEARCH_ISSUES=3` por análise, uma única chamada cobrindo
todos), anexando a resposta em `why_technical` — reforço aditivo, nunca sobrescreve
severidade/confiança sozinho. Separadamente, `lessons_store.py` persiste em disco (mesmo
padrão de `url_scan_history_store.py`) os padrões (`criterion` + assinatura estrutural do
elemento) que o `a11y_expert_reviewer` já confirmou como falso positivo em análises PASSADAS
de páginas diferentes — quando um padrão se repete `MIN_COUNT_TO_SURFACE=3`+ vezes, é injetado
como dica no prompt do próximo review (`known_false_positive_patterns`). Memória cumulativa
entre análises, sem re-treino de peso — mesmo espírito da "skill memory" do Hermes Agent.

### Busca web nativa por provider (`run_agent.py::AIAgent(enable_native_web_search=True)`)

Opt-in por agente (usado por `deep_research`): quando ativo, adiciona a busca nativa do
provider — `{"type": "web_search"}` (OpenAI/xAI, Responses API) ou
`{"type": "web_search_20260209", "name": "web_search"}` (Anthropic, server tool) — em
**paralelo** com `tavily_search`/`exa_search`, nunca substituindo. Ollama/Ollama Cloud não
recebem (sem busca nativa própria boa). **Gemini nunca recebe, mesmo com a flag ativa**: a API
do Gemini não suporta combinar `googleSearch` com function tools na mesma chamada (doc oficial
2026) — misturar quebraria o tool-calling normal do agente inteiro, não só a busca.

---

## Contratos por Sub-Agente

### PerceiverAgent
- Responsabilidade: WCAG 1.x (Perceivable)
- Critérios: 1.1.1 a 1.4.13 (inclui 1.4.5 Images of Text; lê [PAGE CONTEXT], [STYLES], [ELEMENTS])
- ID prefix: "perceiver-<n>"
- Guideline: "WCAG 2.2"

### OperabilityAgent
- Responsabilidade: WCAG 2.x (Operable)
- Critérios: 2.1.1 a 2.5.8 (inclui 2.4.5 Multiple Ways AA; lê [PAGE CONTEXT], [STYLES], [ELEMENTS])
- ID prefix: "operability-<n>"
- Guideline: "WCAG 2.2"

### UnderstandabilityAgent
- Responsabilidade: WCAG 3.x (Understandable)
- Critérios: 3.1.1 a 3.3.8
- ID prefix: "understandability-<n>"
- Guideline: "WCAG 2.2"

### RobustnessAgent
- Responsabilidade: WCAG 4.x (Robust)
- Critérios: 4.1.2 e 4.1.3 (4.1.1 Parsing removido em WCAG 2.2 — não reportar)
- ID prefix: "robustness-<n>"
- Guideline: "WCAG 2.2"

### ARIASpecialistAgent
- Responsabilidade: WAI-ARIA 1.2/1.3 — roles, estados, propriedades obrigatórias, widget ownership rules, e atributos ARIA proibidos (`aria-prohibited-attr`)
- Verifica: 6 ARIA Rules, propriedades obrigatórias por role (slider, progressbar,
  combobox, checkbox, radio, switch, scrollbar, treeitem), computed accessible name (AccName 1.2),
  aria-current, aria-busy, aria-roledescription, landmark duplicados sem aria-label, e proibições W3C
  (ex.: aria-label em divs sem role, aria-sort em botões, aria-checked em listbox options)
- ID prefix: "aria-<n>"
- Guideline: "WAI-ARIA"

### Section508Agent
- Responsabilidade: ADA/Section 508 (36 CFR 1194.21 Software + 1194.22 Web Content)
- Mapeamento: cada subseção (a)–(p) mapeada ao critério WCAG correspondente
- Cobre: EN 301 549 (WCAG 2.1 AA), CVAA, PDF sem versão acessível, CAPTCHA sem áudio
- ID prefix: "s508-<n>"
- Guideline: "ADA/Section 508"

### AgenticAIUIAgent
- Responsabilidade: Acessibilidade de Interfaces de IA Agêntica e Chatbots de LLM
- Verifica: streaming visual de tokens fora de regiões vivas, anúncio inicial/final limitado, manutenção de foco
  no prompt textarea durante geração, atividade de ferramentas como texto comum navegável e silencioso com `aria-busy="true"`,
  modais HITL de permissão de alto risco (`role="alertdialog"`, focus trap e retorno de foco), e suporte a MathML / diffs
- ID prefix: "agentic-ai-<n>"
- Guideline: "WCAG 2.2 / WAI-ARIA"

### Spatial3D_XR_Agent
- Responsabilidade: Acessibilidade em WebXR (VR/AR), 3D Canvas (Three.js/Babylon.js) e Games
- Verifica: W3C XAUR 2026 (interação independente de 6DoF, Fitts' law 3D bounding box hit scaling),
  sinalizadores acústicos 3D, legendas 3D direcionais, dwell selection em gaze-tracking (200-2000ms com trava magnética),
  e espelhamento da cena 3D para Árvore DOM Paralela (PAT / DOM Overlay)
- ID prefix: "spatial-3d-<n>"
- Guideline: "W3C XAUR 2026"

### WebComponents_ElementInternals_Agent
- Responsabilidade: Web Components, Form-Associated Custom Elements (FACE) e Shadow DOM
- Verifica: uso de `ElementInternals.setFormValue()`, obrigatoriedade do 3º argumento `anchor`
  em `ElementInternals.setValidity(flags, message, anchor)` para foco em Shadow DOM, atributos `shadowrootreferencetarget`,
  e suporte a AOM Fase 1/2
- ID prefix: "web-comp-<n>"
- Guideline: "W3C Custom Elements / ARIA"

### NicheDomains_Auth_Passkeys_Agent
- Responsabilidade: Autenticação Acessível (WCAG 2.2 SC 3.3.7/3.3.8/3.3.9), Kiosks POS e Sonificação de Dados
- Verifica: ausência de testes cognitivos de memória em logins (bloqueio de cola de senha `onpaste="return false"`),
  suporte a Passkeys / WebAuthn `autocomplete="username webauthn"`, sonificação Web Audio API em gráficos SVG (D3.js),
  roteamento de áudio P2/USB em Kiosks de autoatendimento via `navigator.mediaDevices.ondevicechange`, e tabelas `role="presentation"` em e-mails HTML
- ID prefix: "niche-auth-<n>"
- Guideline: "WCAG 2.2 / ADA / EAA"

### CSSAnalyzerAgent
- Responsabilidade: Problemas de acessibilidade causados por CSS inline e embedded
- Verifica: outline:none/0 em elementos interativos, contraste via CSS, animações
  sem prefers-reduced-motion, display:none em focáveis, opacity:0, pointer-events:none,
  font-size abaixo de 11px, line-height abaixo de 1.2
- ID prefix: "css-<n>"
- Guideline: "WCAG 2.2"

### AJAXDynamicAgent
- Responsabilidade: Problemas em conteúdo dinâmico e AJAX
- Verifica: containers atualizados sem aria-live, role="status"/"alert" ausentes,
  SPA route changes sem title update + focus management, modais sem focus trap,
  loading spinners sem aria-busy, session timeout sem aviso, auto-refresh sem pause
- ID prefix: "dynamic-<n>"
- Guideline: "WCAG 2.2"

### CognitiveAgent
- Responsabilidade: Barreiras cognitivas (WCAG 3.x + COGA guidance)
- Verifica: CAPTCHA sem alternativa (3.3.8), formulários sem indicador de progresso,
  erros sem sugestão de correção, jargão sem explicação, carrossel sem pause,
  redundant entry, timeouts sem aviso
- ID prefix: "cognitive-<n>"
- Guideline: "WCAG 2.2"

### ReactFrameworkAgent
- Responsabilidade: Anti-padrões de acessibilidade específicos de React e frameworks JS
- Verifica: `<div onClick>` sem role/tabIndex/onKeyDown, `dangerouslySetInnerHTML` com
  markup inerte, portais sem focus trap, links `target="_blank"` sem aviso sr-only,
  links com texto genérico ("clique aqui", "aqui"), Tailwind `outline-none` sem
  `focus-visible:ring-*`, `text-gray-300/400` em fundos claros
- ID prefix: "react-<n>"
- Guideline: "WCAG 2.2"

### ScreenReaderAgent
- Responsabilidade: Padrões que causam falha ou confusão em leitores de tela (NVDA, JAWS, VoiceOver, TalkBack, Narrator)
- Verifica: anúncio no carregamento (title, lang 3.1.1), skip links (2.4.1), hierarquia
  de headings, landmarks + aria-label em múltiplos nav, link text genérico, IDs duplicados,
  input sem label, iframe sem title, tabelas sem th, aria-hidden em focáveis, role=application
  misuse, modo Browse/Forms/Application, SVG sem aria-hidden, links em nova aba sem aviso
- ID prefix: "screen-reader-<n>"
- Guideline: "WCAG 2.2"

### MobileA11yAgent
- Responsabilidade: Acessibilidade web em dispositivos móveis e touch
- Verifica: `<meta viewport>` com `user-scalable=no` ou `maximum-scale < 2` (1.4.4),
  contêineres de largura fixa forçando scroll horizontal (1.4.10 Reflow),
  alvos touch abaixo de 24x24 CSS px (WCAG 2.5.8 — novo em WCAG 2.2),
  input sem type mobile adequado (email, tel, number, date), orientação bloqueada (1.3.4),
  prefers-reduced-motion ausente, Motion Actuation (2.5.4), iOS VoiceOver/TalkBack compat.
- ID prefix: "mobile-<n>"
- Guideline: "WCAG 2.2"

### FormsA11yAgent
- Responsabilidade: Acessibilidade de formulários HTML
- Verifica: placeholder como único label, input/select/textarea sem label associado,
  radio/checkbox sem fieldset+legend, campos obrigatórios sem required/aria-required,
  mensagens de erro não ligadas via aria-describedby, campos inválidos sem aria-invalid,
  campos de dados pessoais sem autocomplete (1.3.5), ausência de error summary,
  context change on focus/change sem aviso (3.2.1)
- ID prefix: "forms-<n>"
- Guideline: "WCAG 2.2"

### WidgetsA11yAgent
- Responsabilidade: Padrões WAI-ARIA de widgets interativos (APG + widget-patterns)
- Verifica: dialog (aria-labelledby, inert vs aria-modal, alertdialog misuse), tabs
  (Arrow-key navigation, inactive panels hidden), accordion (aria-expanded dinâmico),
  combobox (aria-expanded/controls/activedescendant), listbox (aria-selected obrigatório),
  radiogroup (aria-checked obrigatório), switch (aria-checked required),
  slider (aria-valuenow/min/max, multi-thumb), carousel (pause, aria-hidden slides),
  progressbar (valuenow/max), tooltip (focus trigger, Escape, aria-describedby),
  menu (Arrow nav, aria-haspopup), tree (Arrow nav, aria-expanded)
- ID prefix: "widget-<n>"
- Guideline: "WAI-ARIA"

### WCAGSemanticsAgent
- Responsabilidade: Semântica HTML profunda para tecnologias assistivas
- Verifica: page title (2.4.2), lang (3.1.1), landmarks (1.3.6, 2.4.1), skip nav,
  heading hierarchy (1.3.1, 2.4.6), link semantics (2.4.4, 4.1.2), listas (1.3.1),
  tabelas com scope/caption (1.3.1), iframes com title (4.1.2), imagens com alt ou role (1.1.1)
- ID prefix: "semantics-<n>"
- Guideline: "WCAG 2.2"
- NÃO cobre: widgets interativos, formulários, AJAX (cobertos por agentes dedicados)

### ComplianceAuditAgent
- Responsabilidade: Auditoria de conformidade regulatória WCAG 2.2 AA + Section 508 + EN 301 549
- Verifica: todos os critérios de maior risco de não-conformidade legal incluindo
  novos WCAG 2.2 (2.4.11, 2.5.7, 2.5.8, 3.3.7, 3.3.8), padrões sistêmicos,
  mapeamento cruzado 508/EN301549/CVAA, nota 4.1.1 removido em 2.2
- Saídas adicionais: `data.wcag_level` estimado, `data.systemic_patterns`
- ID prefix: "compliance-<n>"
- Guideline: "WCAG 2.2"
- Prioridade: critical = BLOCKER legal, high = 30 dias, medium = 90 dias, low = backlog

### FixerAgent
- Entradas: html_content (str), issues (list[AccessibilityIssue])
- Saídas: fixed_html (str), changes_summary (list[str])

### ChecklistAgent
- Entradas: issues consolidados (list[AccessibilityIssue])
- Saídas: checklist (list[ChecklistItem]) agrupado por princípio POUR

### ReporterAgent
- Entradas: issues, checklist, fixed_html (opcional)
- Saídas: ReportOutput — summary, score (0-100), issues, checklist, download_url
- Score: 100 - deduções (critical=-20, high=-10, medium=-5, low=-2), mín 0

### /export/xlsx — Exportação XLSX Acessível
- Entradas: `url` (str), `issues` (list[AccessibilityIssue])
- Descrição: Gera planilha Excel (.xlsx) formatada para acessibilidade com headers descritivos, auto-filter, freeze panes, cores por severidade (vermelho=critical/high, laranja=medium, amarelo=low) e largura de colunas otimizada para leitores de tela
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename="qa-accessibility-<url>.xlsx"`
- Injetta `url` em cada issue que não tiver o campo preenchido
- Retorna 400 se `issues` for vazio
- Retorna 500 se o gerador XLSX falhar

---

## Rotas expostas

| Método | Rota             | Descrição                         | Rate limit |
|--------|------------------|-----------------------------------|------------|
| POST   | /analyze/url     | Analisa URL externa (Playwright JS rendering)                | Sim        |
| POST   | /analyze/file    | Analisa arquivo único (HTML, CSS, JS, TS, TSX, Vue, Svelte) | Sim   |
| POST   | /analyze/project | Analisa projeto inteiro — multiplos arquivos (List[UploadFile]) | Sim |
| POST   | /analyze/crawl   | Crawlea site inteiro com JS rendering — limite configuravel  | Sim        |
| POST   | /fix             | Corrige HTML                                                 | Sim        |
| POST   | /checklist       | Gera checklist                                               | Sim        |
| POST   | /report          | Relatório completo                                           | Sim        |
| POST   | /export/xlsx     | Exporta issues para planilha Excel (XLSX) acessivel          | Sim        |
| POST   | /analyze/vpat    | Gera VPAT (WCAG 2.2). Aceita `issues` OU `html_content`      | Sim        |
| POST   | /analyze/tests   | Gera suite de testes (Playwright+axe). Aceita `issues` OU `html_content` | Sim |
| GET    | /health          | Health check                                                 | Não        |

### /analyze/vpat e /analyze/tests — entregaveis de QA/agile (ligados ao pipeline)
- Agentes: `vpat_reporter` (VPAT WCAG 2.2 Edition, exigido por enterprise/governo/Section 508) e `test_generator` (Playwright + axe-core prontos para colar no CI do projeto auditado)
- Dois modos de entrada:
  - `issues` (de `/analyze/*`) → chama o agente diretamente (issues→entregavel)
  - `html_content` → roda o pipeline completo via `orchestrate(html, TaskType.VPAT|TESTS)` (HTML→entregavel em uma chamada, util apos crawl/url)
- `TaskType.VPAT` / `TaskType.TESTS` no Orchestrator: rodam o pipeline de análise + expert review + verificação de contraste e então delegam ao agente de entrega (não precisam do checklist)
- VPAT aceita `product_name` e `target`; TESTS aceita `target`
- Retorna 422 se nem `issues` nem `html_content` forem fornecidos; 500 se o agente falhar

### /analyze/url — Playwright JS rendering
- Usa Playwright (Chromium headless) em vez de httpx para capturar o HTML
- Aguarda `networkidle` para garantir que o JavaScript terminou de renderizar
- Timeout total: 30s de navegacao + 20s de networkidle
- Fallback: se networkidle exceder timeout, usa o HTML disponivel ate entao
- Cobre SPAs (React, Angular, Vue, Next.js) que entregam HTML vazio no primeiro load

### /analyze/crawl — detalhes
- Aceita: `url` (URL raiz) + `max_pages` (1-50, padrão 10)
- Usa Playwright para cada página — JS rendering completo
- Descobre links internos automaticamente via `<a href>` na página atual
- Ignora: links externos, fragmentos (#), extensoes de arquivo não-HTML
- Deduplicacao de URLs via normalizacao (remove trailing slash e fragmento)
- Retorna `CrawlResult` com score global, issues consolidados e detalhes por página
- Score calculado com mesmo algoritmo do ReporterAgent (100 - deducoes por severidade)
- Elemento de cada issue anotado com URL de origem: `[https://página.com] <elemento>`
- Aceita: .html, .htm, .css, .js, .jsx, .ts, .tsx, .vue, .svelte
- Monta contexto anotado (`=== FILE: nome.ext ===`) — HTML primeiro, depois CSS, depois JS/TS
- Limite por arquivo: 60 KB; limite total do contexto: 400 KB
- Ignora automaticamente: node_modules, .git, dist, build, .next, coverage, .cache, out
- Retorna 422 se nenhum arquivo compativel for enviado

---

## Invariantes obrigatórias
- Zero emojis em logger (compatibilidade cp1252) — apenas ASCII
- Inicializacao local deve manter logs persistentes ativos por padrão em `logs/`
- Limpeza de logs/cache ocorre somente sob pedido explicito
- Imports sempre no topo do arquivo
- Zero keywords hardcoded que condicionem comportamento da LLM
- Rate limit: 30 req/60s por IP via security/dependencies.py
- PII guard em security/pii_guard.py
- Todo agente retorna AgentResult com success, agent, data, error
- Todo agente usa `extract_json_array(raw)` ou `extract_json_object(raw)` de `llm_client` para parsing robusto -- nunca `json.loads(raw)` direto
- `_extract_issues()` no Orchestrator loga WARNING ao detectar `result.success=False`,
  distinguindo falha de agente de "nenhum issue encontrado" -- pipeline nunca interrompe
- `_timed()` no Orchestrator: todo agente tem timeout configurável via `AGENT_TIMEOUT_SECONDS` (default 180s), exceções capturadas -> AgentResult de falha
- `AgentMetrics` retornado no `data["agent_metrics"]` de todo resultado ANALYZE

## Schema de AccessibilityIssue

Todos os agentes de análise retornam issues com o seguinte contrato:

| Campo                  | Tipo         | Obrigatório | Descrição                                              |
|------------------------|--------------|-------------|--------------------------------------------------------|
| id                     | str          | sim         | Prefixo do agente + número sequencial                  |
| guideline              | Guideline    | sim         | "WCAG 2.2", "WAI-ARIA" ou "ADA/Section 508"          |
| criterion              | str          | sim         | Código + nome do critério em inglês (ex: "1.1.1 Non-text Content")|
| severity               | Severity     | sim         | critical / high / medium / low — impacto SE a violação for real |
| confidence             | Confidence   | não         | high / medium / low — confiança de detecção (eixo distinto de severity: um issue critical com confidence low significa "grave se for real, mas não tenho certeza") |
| level                  | str          | não         | Nível WCAG: A / AA / AAA                               |
| element                | str          | sim         | Seletor HTML ou contexto                               |
| description            | str          | sim         | Linguagem simples -- para PMs e designers              |
| description_technical  | str          | não         | Regra técnica violada -- para devs                     |
| why_simple             | str          | não         | Impacto humano em linguagem simples                    |
| why_technical          | str          | não         | Justificativa WCAG e modo de falha AT -- técnico       |
| suggestion             | str          | sim         | Correção em linguagem simples                          |
| suggestion_technical   | str          | não         | Correção em nível de código                            |
| wcag_url               | str          | não         | URL Understanding da diretriz                          |
| criterion_pt           | str          | não         | Critério traduzido PT-BR — preenchido pela camada i18n |
| severity_pt            | str          | não         | Severidade traduzida PT-BR — preenchida pela camada i18n |
| fixed_element_html     | str          | não         | Snippet HTML do elemento corrigido — preenchido pelo FixerAgent |

### Camada i18n

O módulo `backend/src/shared/i18n/criteria_pt.py` é o único ponto de tradução.
Chamado pelo Orchestrator após deduplicação e guardrail, antes de retornar o resultado.
Preenche `criterion_pt` e `severity_pt` em todos os issues.
Não altera os campos EN originais — backward compatibility garantida.
`translate_issues(issues)` é a única função de entrada pública.

### Campo fixed_element_html

Preenchido pelo `FixerAgent` via `_enrich_issues_with_fixed_element()`.
Contém o snippet HTML do elemento **após** a correção, extraído do `fixed_html`.
Usado por fluxos de correção e exportação para preservar o snippet corrigido do elemento.
Limitado a 500 caracteres por issue.

---

## CI/CD

Pipeline GitHub Actions em `.github/workflows/accessibility-ci.yml`:

| Job                 | Trigger         | O que verifica                                    |
|---------------------|-----------------|---------------------------------------------------|
| code-quality        | push/PR         | Quality gate: proibições README + mypy (config `backend/mypy.ini`, plugin `pydantic.mypy`) |
| backend-tests       | push/PR         | pytest, coverage ≥ 80% (`--cov-fail-under=80`), `--ignore=integration` |
| web-unit-tests      | push/PR         | Jest unit tests (web)                             |
| web-e2e-tests       | push/PR         | Playwright + axe-core (teclado, ARIA live, contraste) |
| lighthouse-audit    | PRs only        | Accessibility score ≥ 0.90, Best Practices ≥ 0.85 |
| github-a11y-scanner | PRs → main only | github/accessibility-scanner@v2 nas rotas da app  |

Lighthouse CI configurado em `.lighthouserc.json`.

---

## Pendências de arquitetura (decisões adiadas deliberadamente)

Registradas aqui para não se perderem entre sessões. Nenhuma delas deve ser
implementada sem confirmação explícita do usuário -- são adiamentos
propositais, não esquecimentos.

### 1. Compaction nativo Anthropic/OpenAI como camada adicional ao client-side

Hoje a compactação de histórico (`history_summarizer.py` /
`_compress_history_if_needed`) é 100% client-side: resume o bloco mais antigo
via uma chamada de LLM extra, preserva o system message + últimas
`_KEEP_RECENT_MESSAGES` mensagens verbatim, sempre reincorpora o bloco médio
completo (nunca encadeia resumos de resumos). É a única opção real pro Ollama
(sem compaction nativa confirmada via pesquisa 2026). Anthropic
(`compact-2026-01-12`) e OpenAI (`responses/compact`) têm compaction nativa,
mas a decisão foi NÃO integrar isso agora, pelo motivo explícito dado pelo
usuário: sem crédito de API disponível pra validar a mudança com segurança.
Retomar quando houver crédito para testar de verdade -- ver Task #18.

### 2. Roteamento de custo entre providers (multi-provider cost-aware routing)

Hoje o custo é otimizado em três frentes reais, todas já implementadas:
- `complexity_router.py` -- classificador (o próprio modelo, nunca heurística
  fixa) decide um tradeoff custo/qualidade (0-10) por análise, usado por
  `model_router.resolve_alto_model` ao rankear candidatos do Ollama Cloud
  (`ollama_cloud_adapter.rank_ollama_cloud_candidates`).
- `response_cache.py` -- cache exato (não semântico, por design: risco de
  cache-hit em HTML "parecido" mas diferente no ponto relevante pra
  acessibilidade é inaceitável neste domínio).
- `batch_collector.py` / `batch_inference.py` -- padrão Batch API (desconto de
  lote).

O que falta, confirmado por pesquisa de mercado 2026 (RouteLLM: rotear ~14%
das queries pro modelo caro mantém ~95% da qualidade com ~85% de economia):
um roteador que compare **preço real entre providers** (OpenAI vs. Anthropic
vs. Gemini vs. xAI vs. Ollama-cloud) e escolha objetivamente o mais barato
capaz de resolver a tarefa. Hoje "Alto" rankeia modelo por
(reasoning, contexto, custo como desempate) **dentro** de um provider já
escolhido; o modo "agentic/auto" escolhe o provider pela API key disponível no
ambiente, não por preço. Adiado a pedido do usuário em 2026-08-11 -- ver
Task #19. Não é bom momento pra validar mudança de custo com a conta Ollama
Cloud sem saldo de extra usage.

**Implementado e validado em 2026-08-11** (Task #19 concluída):
`model_router.py::_resolve_agentic_auto` compara custo real
(`cost_input`/`cost_output` do catálogo `models.dev`, ponderado 4:1 a favor
do input) entre todos os providers com API key disponível, respeitando o
tradeoff de `complexity_router`. Testado por unidade (8 testes reais em
`test_model_router.py`, tradeoff baixo/médio/alto/muito alto, sem provider
disponível, tier fast, modelo concreto pulando o roteamento) e por um E2E
real (`tests/backend/real_llm/live_runs/run_cost_routing_e2e.py`, provider
`agentic`, cadeia completa sem mock: classificador de complexidade real ->
roteador de custo real -> chamada real ao provider/modelo escolhido -> issues
de acessibilidade reais entregues).

Resultado do E2E real: página simples (sem widget/ARIA) classificou
tradeoff=10 e resolveu pro modelo `glm-5.1` (Ollama Cloud), 4.3s, 1 issue
real correto. Página complexa (combobox, tablist, dialog, div clicável sem
role) classificou tradeoff=2 e resolveu pro modelo `minimax-m3` (diferente
do caso simples), 22.5s, **7 issues reais e sofisticados** (teclado, nome
acessível de dialog, `aria-live` faltando, `tabpanel` ausente, roving
tabindex) -- confirma que o caminho mais barato não degrada qualidade no
caso simples, e que o caso complexo escala esforço de verdade sem
intervenção manual.

Duas ressalvas reais encontradas durante essa validação, não fabricadas:
1. A `OPENAI_API_KEY` armazenada está inválida/expirada (401 direto da API
   da OpenAI) -- bloqueou a comparação real de custo entre OpenAI e Ollama
   Cloud nesta rodada; o E2E precisou ser restrito a um único provider
   (Ollama Cloud, confirmado funcionando) pra completar. Ver Task #22 --
   ação do usuário (renovar/trocar a chave), não é bug de código.
2. Com o catálogo real disponível hoje, os candidatos de OpenAI (fallback
   estático, já que a busca ao vivo deu timeout) e Ollama Cloud empataram no
   custo estimado (0.24 $/Mtok ambos) -- essa rodada real específica não
   demonstra economia em $ mensurável entre providers por falta de dados de
   preço diferenciados no momento, não por falha do mecanismo (que já está
   provado nos testes unitários com custos genuinamente diferentes).

**Correção final em 2026-08-11** (a pedido do usuário, "pesquise individual
em cada provedor"): a Ollama Cloud não publica $/token próprio (confirmado
em duas buscas independentes -- cobra por assinatura/GPU-time, billing por
token "em breve"), mas os ~18 modelos que ela hospeda são pesos de
laboratórios terceiros que TÊM preço oficial publicado (Moonshot/Kimi,
Zhipu/GLM, MiniMax, DeepSeek, Alibaba/Qwen, NVIDIA/Nemotron, Google/Gemma).
Pesquisado o preço real de cada modelo do catálogo `ollama-cloud`
(`agent/models_dev.py`) direto na fonte original, substituindo o default
genérico de `ModelInfo` (0.15/0.6) que estava mascarado como se fosse dado
real. Achado colateral corrigido no mesmo lote: `get_model_info` preferia o
catálogo *live* (buscado direto no `/v1/models` da Ollama), que não traz
preço nenhum -- sem mesclar o custo estático sobre o live, os valores
pesquisados eram silenciosamente sobrescritos pelo default sempre que o
catálogo live estava acessível. Testado por unidade
(`test_ollama_cloud_costs_sao_precos_reais_pesquisados_no_laboratorio_original`
em `test_models_dev_catalog.py`) e revalidado com o mesmo E2E real: página
simples -> `minimax-m3` (0.48 $/Mtok), página complexa -> `glm-5.2`
(2.00 $/Mtok) -- ~4,2x de diferença real de custo entre os dois casos,
com a página complexa entregando ainda mais issues reais (11, incluindo
gestão de foco em modal, suporte a teclado no combobox, live region) que a
rodada anterior (7) -- confirma economia real mensurável sem perda de
qualidade. Suíte unitária completa: 1024/1024, zero regressão.

### 3. Validação real (E2E contra o modelo) de fix_local_project_files/read_local_project_files

Implementados em 2026-08-11 (`chat_tools.py`): permitem apontar um caminho
local no disco do backend (ex.: `C:\meuprojeto`) e a IA ler
(`read_local_project_files`) e corrigir/escrever de volta
(`fix_local_project_files`) os arquivos reais nesse caminho, sem exigir
round-trip de ZIP -- reaproveita o mesmo pipeline de correção de
`fix_and_zip_files` (`_run_fixes_and_generate_zip`), com proteção de path
traversal (`_resolve_safe_project_path`) e backup automático do conteúdo
original antes de sobrescrever (`tempfile.gettempdir()/qa_accessibility_local_backups/<uuid>`).
Ambas as ferramentas exigem aprovação explícita via `clarify`
(`requires_approval=True`), mesmo padrão de `fix_and_zip_files`.

Validado: sintaxe, lint (ruff limpo), smoke test de filesystem (leitura real
de diretório, `node_modules`/`.git` pulados corretamente, path traversal
`../../etc/passwd` bloqueado), suíte unitária existente (75/75, sem
regressão) e, em 2026-08-11 (após o usuário confirmar crédito reposto na
conta Ollama Cloud), **teste real de ponta a ponta contra o modelo**: HTML
com `<img>` sem alt, sem `<title>`, sem `lang`, sem `<main>`/`<h1>` foi
corrigido de verdade (5 mudanças reais: `lang="pt-BR"`, `<title>`,
`alt="Acme Corp"`, `<h1>`, landmark `<main>`) e **reescrito no disco no
caminho original** -- confirmado lendo o arquivo de volta do disco após a
chamada, com backup automático criado e o ZIP de segurança também gerado.
Task #20 concluída.

Achado real durante essa validação (não é bug da ferramenta nova, é do
pipeline de correção geral): `_verify_layout_visually` (verificação visual
pós-fix) envia conteúdo multimodal (texto + imagem) e falha na API nativa do
Ollama (`_run_ollama_native`) com erro de validação Pydantic ("content
deveria ser string, veio lista") -- a chamada cai automaticamente pro
fallback OpenAI-compat e o resultado final continua correto, mas isso
significa que **toda chamada multimodal (verificação visual, gerador de
alt-text de imagem) nunca aproveita a API nativa**, sempre cai no fallback.
**Corrigido em 2026-08-11** (Task #21): `_ollama_native_user_content`
(`run_agent.py`) agora normaliza os dois formatos -- detecta quando
`user_message` é uma lista estilo content-array OpenAI, extrai os blocos
`text` e `image_url` (decodificando o base64 do data URI), e junta com
qualquer imagem já vinda por `self.images` (a convenção usada pelos outros
provedores). Testado por unidade
(`TestOllamaNativeApiIsTheDefaultPath::test_multimodal_content_array_reaches_native_client_as_images_field`,
reproduz o payload real de `_verify_layout_visually` contra um
`ollama.Client` mockado e confirma `content` como string + `images` como
lista) e revalidado com um novo `fix_local_project_files` real contra o
modelo (78/78 testes de `run_agent.py` passando, zero regressão).

### 4. Captura real da fala do NVDA (validação cruzada com a árvore de acessibilidade real)

Investigação de viabilidade concluída em 2026-08-11 (a pedido do usuário --
Task #26, não implementada ainda). Contexto: `nvda_service.py` usa a DLL
oficial `nvdaControllerClient.dll` (`nvdaController_speakText`,
`nvdaController_cancelSpeech`, `nvdaController_brailleMessage`,
`nvdaController_testIfRunning`) -- via de MÃO ÚNICA, feita pra ENVIAR texto
pro NVDA falar (usada hoje pela tool `nvda_speak`). A API oficial da NV
Access nunca expôs uma função pra "escutar"/capturar o que o NVDA realmente
anuncia em tempo real durante uma navegação de verdade -- isso não existe
hoje no projeto nem na API oficial.

Achado real da pesquisa: existe um add-on NVDA open-source mantido,
`speechLogger` (https://github.com/opensourcesys/speechLogger), que grava
cada frase falada pelo NVDA num arquivo de texto em tempo real, com
diretório configurável (`%temp%`, `%userprofile%`, etc.). Isso resolve o
problema sem precisar escrever/manter um add-on NVDA próprio.

Caminho de implementação proposto (pendente, não iniciado):
1. Usuário instala e configura o add-on `speechLogger` no NVDA dele --
   passo manual, único, fora do código (não dá pra instalar add-on de
   terceiro no software do usuário programaticamente).
2. Nosso lado acompanha esse arquivo de log em tempo real (file watching --
   ler linhas novas conforme são escritas).
3. Cruza o texto real capturado contra a árvore de acessibilidade real já
   implementada (item 3 acima / `fetch_accessibility_tree_snapshot` em
   `browser.py`, Task #25) -- permite confirmar automaticamente se o que o
   NVDA realmente anunciou bate com o que deveria ter sido anunciado,
   inclusive capturando SILÊNCIO em elementos que deveriam ter sido
   anunciados e não foram (achado que ferramentas automatizadas comuns não
   pegam).

Mudança prática pro usuário, se implementado: hoje o usuário precisa ouvir o
NVDA e DESCREVER pra IA em texto o que ouviu, pra ela poder avaliar. Depois
do setup único do add-on, o usuário só precisa navegar normalmente com o
NVDA ligado -- a IA lê o transcript real do arquivo de log sozinha, sem o
usuário precisar anotar ou descrever nada, e aponta divergências com o
transcript real como prova, não como suposição.
