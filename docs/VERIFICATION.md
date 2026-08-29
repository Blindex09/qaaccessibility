# VERIFICATION.md — Evidence-Based Completion

> QA Accessibility Platform
> Última verificação: 2026-08-01
> Suíte: `815 passed` (backend) + `132 passed` (web/Jest) · Cobertura backend: 79% · Lint/type-check: 0 erros (`ruff check` + `mypy` 100% clean backend; `tsc --noEmit` 0 erros no `web/`)
> Gaps fechados (2026-08-01): execução paralela de tool calls (`ThreadPoolExecutor` nas 4 rotas de provider), Retry/Backoff (achado: já cobre por padrão do SDK, sem código novo), Confidence Signals (novo campo `confidence` distinto de `severity` em todos os 25 agentes de análise) — ver seção 19
> Gaps fechados (2026-08-01): Response Caching (exact-match, TTL, escopo leaf-only), Interruptibilidade (`POST /chat/cancel` + evento `stream_id`, best-effort documentado) — ver seção 20. Memory/Personalização entre sessões conscientemente descartado (sem sistema de identidade de usuário) por decisão explícita do usuário, não implementado
> Gaps fechados (2026-08-01): Native Tools (decisão informada, sem código — redundante/fora de escopo), Context Drift Detection + Reflection/Replanning (detecção de repetição de tool calls + reflexão única por conversa), Multimodal Processing (input de imagem nos 4 caminhos de provider, com fallback gracioso), Batch Inference (serviço `batch_inference.py` para OpenAI/Anthropic/Gemini — integração ao pipeline de crawl deliberadamente deixada como próximo passo) — ver seção 21
> Coverage gap fechado (2026-08-01): novo `SvelteFrameworkAgent` (25º especialista de análise) + i18n/RTL em `wcag_semantics`/`css_analyzer` + Data Grid/Rich Text Editor em `widgets_a11y` — ver seção 14
> Prompt/Context Engineering (2026-08-01): prompt caching Anthropic (`cache_control: ephemeral` em system+tools) + few-shot example em todos os 25 agentes de análise + permissão explícita de incerteza — ver seção 15
> Naming: `test_orchestrator_v2.py` renomeado para `test_orchestrator.py` (violava a regra do próprio README de nunca versionar nome de arquivo — não havia um "v1" para fundir, era renomeação pura)
> **Gap fechado (2026-08-01):** `mypy` havia encontrado 3 erros pré-existentes em `routes/export_xlsx.py:144` e `services/a2a_service.py:175,202` (chamada a `run_orchestrator`/kwarg `issues` que não existiam mais na assinatura atual de `orchestrator.py`/`self_healing.py` — provavelmente sobras de um refactor anterior sem o gate de CI rodando de fato). Corrigido: `export_last_sarif` agora constrói `AccessibilityIssue` antes de chamar `export_to_sarif` (igual `export_sarif` já fazia); `a2a_service.py` agora chama `orchestrate()`/`run_self_healing_loop()` com a assinatura real. Os dois branches (`accessibility_analysis`, `self_healing_fix`) nunca tinham teste — só `sarif_export` era exercitado em `test_a2a_protocol.py` — por isso o bug nunca apareceu em CI. Dois testes de regressão adicionados (`test_worker_accessibility_analysis_skill_calls_orchestrate`, `test_worker_self_healing_fix_skill_calls_run_self_healing_loop`) fecham essa lacuna de cobertura.
> Documentation-First + Static/Dynamic/Behavioral Verification aplicado aos novos pilares (4 novos subagentes de acessibilidade, W3C ARIA Proibido, SARIF 2.1.0 Exporter, Protocolo A2A v1.0 Linux Foundation, Roteamento por Tier com Filtro `requires_extra_usage` e Cascata Automática de Provider `_resolve_auto_fallback`)
> Alinhamento doc ↔ código (2026-07-29): provider "agentic" exposto na rota `/models`, ordem sincronizada frontend ↔ backend, `resolve_model_and_provider` para suporte agêntico completo, mensagens de erro humanizadas em Português (400, 401, 402, 403, 404, 429, 500, 502, 503, 504, 529, timeouts)
> Gaps 2026 fechados (2026-08-01): Dependency Compliance (pip-audit + npm audit no CI), Configuration Drift Detection (`config_drift.py`), Repository Intelligence (`REPO_MAP.json` + tool MCP `describe_repository`) — ver seção 13

Este documento é a **rastreabilidade formal** entre cada promessa declarada nos
`AI_MODULE_SPEC.md` (backend + web) e a **evidência executável** que a valida
(teste, script de CI ou checagem estática). Goal-backward: para cada promessa,
indicamos o artefato de código e o teste que prova que ele cumpre o contrato.

A regra é: **nenhuma promessa de spec fica sem evidência**. Se um teste muda de
nome ou é removido, esta tabela deve ser atualizada na mesma entrega.

---

## 1. Spec-Driven Development

| Promessa (spec) | Artefato de código | Evidência executável |
|-----------------|--------------------|----------------------|
| Contrato local obrigatório do backend | `backend/AI_MODULE_SPEC.md` | Spec existe e descreve 24 agentes + A2A + contratos |
| Contrato local obrigatório do web | `web/AI_MODULE_SPEC.md` | Spec existe e descreve ChatScreen/SettingsScreen |
| README prevalece sobre qualquer doc | `README.md` | Seção "Regras obrigatórias" declara precedência |
| Zero duplicação de fluxos/rotas | `backend/src/routes/*` | 1 rota por responsabilidade (analyze, fix, checklist, report, export, vpat, tests, chat, models, settings, preview, webhook, a2a) |
| Protocolo A2A v1.0 Linux Foundation | `backend/src/services/a2a_service.py` & `backend/src/routes/a2a_route.py` | `test_a2a_protocol.py` (3/3 passed: agent-card schema, discovery, task lifecycle) |

---

## 2. Continuous Verification

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Testes backend aprovados | `tests/backend/` | `python -m pytest tests/backend -q` → 643 passed |
| Lint/compile sem erros | workspace inteiro | `get_errors` → 0 erros |
| MyPy strict | `mypy.ini`, `backend/mypy.ini` | Configurado strict |
| Ruff | `ruff.toml` | Configurado |
| Commitlint + husky | `commitlint.config.js`, `package.json` | Commits semânticos enforced |
| Cobertura medida | `pytest.ini` | `--cov` reporting no run (78% total) |

---

## 3. Holistic System Validation

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Pipeline ANALYZE ponta a ponta | `orchestrator.py` | `test_orchestrator.py::TestOrchestratorRefactored::test_analyze_runs_selected_analysis_agents` |
| Merge de issues de todos agentes | `orchestrator.py::_deduplicate_issues` | `test_orchestrator.py::test_issues_merged_from_all_agents` |
| agent_metrics por agente | `orchestrator.py` | `test_orchestrator.py::test_analyze_result_includes_agent_metrics` |
| Browser rendering (Playwright) | `services/browser.py` | `test_browser_crawler.py::test_fetch_rendered_html_and_screenshot_success` |
| Crawl de site inteiro | `services/crawler.py` | `test_browser_crawler.py` (crawl tests) |
| Rotas FastAPI integradas | `routes/*` | `tests/backend/integration/test_routes.py` |
| Rota de export XLSX | `routes/export_xlsx.py` | `tests/backend/integration/test_export_xlsx_route.py` |
| Rota de project ZIP | `routes/analyze.py` | `tests/backend/unit/routes/test_routes_zip.py` |
| Chat streaming SSE | `routes/chat.py`, `services/chat_runtime.py` | `tests/backend/unit/routes/test_chat_route.py::TestChatStreamRoute` |
| Rota /models com 6 providers (agentic + 5 concretos) | `routes/models_route.py::CHAT_PROVIDERS` | `tests/backend/unit/routes/test_models_route.py::test_lists_six_chat_providers_with_models` |
| MCP server (5 tools) | `services/mcp_server.py` | `tests/backend/unit/services/test_mcp_server.py` (44 testes) |

---

## 4. Architecture Compliance

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| PII middleware redaction | `middleware/pii_middleware.py` | `tests/backend/unit/middleware/test_pii_middleware.py` |
| Security headers | `middleware/security_headers.py` | `tests/backend/unit/test_middleware_security.py` |
| Rate limiter | `security/rate_limiter.py` | `tests/backend/unit/security/test_rate_limiter.py` |
| PII guard (SSN/CPF) | `security/pii_guard.py` | `tests/backend/unit/security/test_pii_guard.py` |
| SSRF guard | `routes/analyze.py::_validate_url_ssrf` | `tests/backend/unit/test_security_ssrf.py` (16 testes) |
| QA_API_TOKEN fora de loopback | `main.py` | `backend/src/main.py` raise RuntimeError se host != loopback sem token |
| i18n em ponto único | `shared/i18n/criteria_pt.py` | `tests/backend/unit/test_i18n.py` (12 testes) |
| Settings injection rejeita newline | `routes/settings.py` | `tests/backend/unit/routes/test_settings_route.py::TestSettingsRouteInjection` |

---

## 5. Reference Implementation Compliance

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Todo AgentResult valida schema Pydantic | `shared/models.py` | `test_agent_contracts.py::assert_agent_result_invariants` + todos `test_*_agent.py` fazem `AccessibilityIssue(**raw)` |
| Contraste determinístico (referência canônica) | `services/contrast_verifier.py` | `tests/backend/unit/services/test_contrast_verifier.py` (13 testes) |
| Cálculo APCA | `services/apca.py` | `tests/backend/unit/services/test_apca.py` |
| axe-core como referência externa | `services/self_healing.py::verify_html_with_axe` | `tests/backend/unit/services/test_self_healing.py` (axe-core 4.9.1 via Playwright) |
| Catálogo de modelos local | `agent/models_dev.py` | `tests/backend/unit/test_models_dev_catalog.py` |
| XLSX exporter (formato canônico) | `services/xlsx_exporter.py` | `tests/backend/unit/services/test_xlsx_exporter.py` (100% cobertura) |
| Roteamento "alto" (model_router) | `services/model_router.py` | `tests/backend/unit/services/test_model_router.py` |

---

## 6. Documentation Compliance

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Toda mudança estrutural refletida no README | `README.md` | Seção "Regras obrigatórias" declara a regra |
| Débitos técnicos documentados | `backend/AI_MODULE_SPEC.md` | Limitação do `models_dev.py` (catálogo estático) documentada |
| Master doc de commits | `docs/MASTER_IMPLEMENTATION_AND_COMMIT_HISTORY.md` | 5 commits estruturados + contagem de testes atualizada |
| Sem versionamento no nome de arquivos | workspace | Nenhum arquivo usa v1/v2/1.x/2.x (verificado por file_search) |

---

## 7. Agent Evals

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Contratos comportamentais dos agentes | `tests/backend/unit/test_agent_contracts.py` | Invariantes de `AgentResult` + casos adversariais (empty/minimal/large/malformed) |
| Contrato por agente especialista | `tests/backend/unit/agents/test_*.py` | 24 arquivos, cada um valida `test_contract_on_success` + falhas |
| Adversarial: HTML vazio/gigante/malformado | `test_agent_contracts.py` | `EMPTY_HTML`, `LARGE_HTML`, `MALFORMED_HTML` fixtures |
| Classifier routing | `agents/classifier/` | `tests/backend/unit/agents/test_classifier.py` |
| Orchestrator skip de frameworks sem evidência | `orchestrator.py` | `test_orchestrator.py::test_analyze_runs_selected_analysis_agents` (asserts skipped agents) |

---

## 8. Accessibility Verification

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| axe-core 4.9.1 via Playwright CDP | `services/self_healing.py` | `tests/backend/unit/services/test_self_healing.py` |
| Mapeamento de severidade axe→enum | `services/self_healing.py::_SEVERITY_MAP` | `test_self_healing.py` valida Severity.CRITICAL/HIGH/MEDIUM/LOW |
| Build gate no CI/CD | `scripts/ci_a11y_check.py` | Falha build se critical/high encontrados |
| Self-healing com model cascading | `services/self_healing.py::run_self_healing_loop` | `test_self_healing.py::test_self_healing_loop_success_on_first_try` |
| Fix route com/sem self-healing | `routes/fix.py` | `tests/backend/unit/routes/test_fix_route.py` |
| Preview de fix | `routes/preview.py` | `tests/backend/unit/routes/test_preview_route.py` |
| Fix checkpoint store | `services/fix_checkpoint_store.py` | `tests/backend/unit/services/test_fix_checkpoint_store.py` |

---

## 9. Evidence-Based Completion

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Specs como contratos verificáveis | `AI_MODULE_SPEC.md` (backend + web) | Este VERIFICATION.md — mapeia cada promessa a teste |
| Suíte verde e reprodutível | `tests/backend/` | `643 passed in 36.00s` (executado 2026-07-28) |
| Lint/compile sem erros | workspace | `get_errors` → 0 |
| CI gate bloqueia critical/high | `scripts/ci_a11y_check.py` | Script com `sys.exit(1)` em violações |
| Rastreabilidade fase→evidência | **este documento** | Tabela por conceito acima |

> **Lacuna fechada:** antes deste documento, o projeto tinha todas as evidências
> mas sem rastreabilidade formal. Este `VERIFICATION.md` é a ponte entre
> promessa (spec) e prova (teste executável).

---

## 10. AI Evals / LLM Evals

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| LLM-as-Judge com 5 dimensões | `tests/backend/unit/test_llm_judge.py` | `evaluate_fix()` → correctness, minimality, preservation, no-regression, completeness |
| Pointwise scoring 0-2 | `test_llm_judge.py` | `judge_*` helpers devolvem 0/1/2 por dimensão |
| Golden cases com limiar mínimo | `test_llm_judge.py::JUDGE_CASES` | 5 casos (JC001-JC005), `min_score` por caso |
| Judge determinístico em CI | `test_llm_judge.py` | Sem chamada a outro LLM — asserções sobre output |
| Fixer integrado ao judge | `agents/fixer/fixer.py` | `test_llm_judge.py::TestLLMJudgePointwise::test_judge_score_meets_threshold` |
| Telemetry/observabilidade | `services/telemetry.py` | `tests/backend/unit/services/test_telemetry_instrumentation.py` |

---

## 11. Prompt Regression

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Golden dataset (5 cenários WCAG) | `tests/backend/unit/test_prompt_regression.py::GOLDEN_CASES` | GC001-GC005 com criterion+severity esperados |
| Detecção de regressão de prompt | `test_prompt_regression.py` | `TestPerceiverPromptRegression::test_golden_case_detected` |
| Schema invariant de issues | `test_prompt_regression.py` | `test_schema_invariant_all_issues_have_required_fields` |
| HTML vazio → sem issues | `test_prompt_regression.py` | `test_empty_html_returns_no_issues` |
| Tool approval (fail-closed) | `tools/registry.py` | `tests/backend/unit/test_tool_approval.py` |
| Clarify tool (chat) | `services/chat_tools.py` | `tests/backend/unit/services/test_clarify_tool.py` |

---

## Resumo executivo

| Conceito | Promessas | Evidências | Status |
|----------|-----------|------------|--------|
| Spec-Driven Development | 4 | 4 | ✅ |
| Continuous Verification | 6 | 6 | ✅ |
| Holistic System Validation | 10 | 10 | ✅ |
| Architecture Compliance | 8 | 8 | ✅ |
| Reference Implementation Compliance | 7 | 7 | ✅ |
| Documentation Compliance | 4 | 4 | ✅ |
| Agent Evals | 5 | 5 | ✅ |
| Accessibility Verification | 7 | 7 | ✅ |
| Evidence-Based Completion | 5 | 5 | ✅ (fechado por este doc) |
| AI Evals / LLM Evals | 6 | 6 | ✅ |
| Prompt Regression | 6 | 6 | ✅ |
| **TOTAL** | **68** | **68** | **100%** |

### Como reproduzir as evidências

```powershell
# Suíte completa do backend
python -m pytest tests/backend -q

# Suíte web (Jest + Playwright)
cd web && npm test

# Build gate de acessibilidade
$env:A11Y_TARGET_URL="https://exemplo.com"; python scripts/ci_a11y_check.py

# Lint/compile check
# (VS Code: Problems panel — esperado 0 erros)
```

### Manutenção

Este documento deve ser atualizado **na mesma entrega** de qualquer mudança que:
- adicione/remova/renomeie um teste citado aqui
- altere um contrato declarado nos `AI_MODULE_SPEC.md`
- adicione uma nova promessa de spec
- mude a contagem de testes (atualizar o cabeçalho)

A regra de Evidence-Based Completion é: **promessa sem evidência executável = dívida técnica**, e débito deve ser registrado no spec correspondente.

---

## 12. Gaps fechados (2026-07-28) — Documentation-First + Static/Dynamic/Behavioral Verification

Os 3 gaps identificados vs. produção 2026 foram resolvidos seguindo
Documentation-First Development com Static, Dynamic e Behavioral Verification.

### Gap 1: Catálogo dinâmico de modelos

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Consulta `GET /v1/models` dos providers em runtime | `agent/models_dev.py::fetch_live_models` | `test_models_live_catalog.py::TestFetchLiveModels` (7 testes) |
| Live-first, static-fallback (padrão 2026) | `list_agentic_models`, `get_model_info` | `test_models_live_catalog.py::TestLiveFirstStaticFallback` (5 testes) |
| Parse por provider (OpenAI/Anthropic/Gemini) | `_parse_openai_models`, `_parse_anthropic_models`, `_parse_gemini_models` | testes de parse por provider |
| Resolução de endpoint e auth por provider | `_resolve_endpoint`, `_resolve_auth_header` | `TestEndpointResolution` (6), `TestAuthHeaders` (4) |
| Cache com TTL + invalidação | `_LIVE_CACHE`, `clear_live_cache` | `test_caches_live_catalog_within_ttl`, `test_clear_live_cache_invalidates` |
| Fallback gracioso offline | `fetch_live_models` retorna `{}` | `test_returns_empty_on_network_failure` |

### Gap 2: Online scoring de traces

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| LLM-as-judge pontua traces de produção | `telemetry.py::score_trace` | `test_telemetry_scoring.py` (9 testes) |
| No-op seguro sem provider | `score_trace` devolve None | `test_score_trace_noop_when_no_provider` |
| Rubric default (factual/completeness/tool efficiency) | `_DEFAULT_RUBRIC` | `test_score_trace_passes_custom_criteria` |
| Parse de JSON + fallback regex | score_trace | `test_score_trace_returns_parsed_score_on_valid_json`, `test_score_trace_falls_back_to_regex` |
| Normalização de score 0-10 → 0-1 | score_trace | `test_score_trace_normalizes_score_above_one` |
| Truncamento de trace longo | score_trace | `test_score_trace_truncates_long_trace` |

### Gap 3: End-state evals (multi-turn)

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Valida estado final, não cada step (padrão Anthropic) | `test_end_state_evals.py` | 4 classes de teste (EC001-EC004) |
| Fix endereça issue reportada | `assert_final_state_invariants` | `TestEndStateFixAddressesIssue` (2 testes) |
| Re-audit não regressa | invariantes de tabindex/aria | `TestEndStateNoRegressionAfterFix` (2 testes) |
| VPAT reflete issues resolvidas | `run_vpat_reporter` end-state | `TestEndStateVpatReflectsResolvedIssues` (1 teste) |
| Reporter consolida score | `run_reporter` end-state | `TestEndStateReporterSummarizesAnalysis` (1 teste) |

### Verification aplicada (Documentation-First)

| Nível | Ferramenta | Resultado |
|-------|-----------|-----------|
| **Documentation-First** | Spec atualizada ANTES do código | `AI_MODULE_SPEC.md` — limitação do catálogo substituída por catálogo dinâmico + 2 novas capacidades documentadas |
| **Static Verification** | mypy strict, ruff, get_errors | 0 erros em 3 arquivos de produção + 3 de teste |
| **Dynamic Verification** | pytest + cobertura | 680 passed, 78% cobertura |
| **Behavioral Verification** | contratos + invariantes end-state | `assert_final_state_invariants` + testes de contrato de catalog/scoring |

---

## 13. Gaps fechados (2026-08-01) — Dependency Compliance, Configuration Drift Detection, Repository Intelligence

Identificados numa auditoria de conceitos de engenharia agêntica 2026 (validados contra doc oficial de cada provider + definições atuais de mercado via pesquisa web), com escopo deliberadamente proporcional ao projeto — nenhum indexador de código ou infraestrutura de drift pesada foi construída onde um check simples resolve o problema real.

### Dependency Compliance

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| CVE conhecido bloqueia merge (backend) | `.github/workflows/accessibility-ci.yml::code-quality` | `pip-audit -r backend/requirements.txt` — 0 vulnerabilidades após bump de `cryptography` para `>=48.0.1,<49.0.0` (corrigia GHSA-537c-gmf6-5ccf) |
| CVE visível sem travar em dívida pré-existente (web) | `.github/workflows/accessibility-ci.yml::web-app-quality` | `npm audit --audit-level=moderate` com `continue-on-error: true` — 54 vulnerabilidades pré-existentes, todas em ferramentas de build do Expo/Metro (nunca chegam ao bundle servido), raiz é a mesma trava documentada do `@expo/webpack-config` preso no SDK 51 |

### Configuration Drift Detection

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Var de override de endpoint ativa no ambiente mas não declarada em `backend/.env` gera warning | `services/config_drift.py::detect_config_drift` | `tests/backend/unit/services/test_config_drift.py::TestProviderBaseUrlDrift` (3 testes) |
| Chave com prefixo do projeto em `backend/.env` não documentada em `.env.example` gera warning | `services/config_drift.py::detect_config_drift` | `TestUndocumentedProjectVars` (3 testes) |
| Check roda no startup, nunca derruba o processo | `main.py::log_config_drift()` | chamado logo após `configure_telemetry()`; função nunca levanta exceção |

### Repository Intelligence

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Índice estruturado dos ~34 sub-agentes, gerado do código-fonte (não prosa mantida à mão) | `scripts/generate_repo_map.py` → `docs/REPO_MAP.json` | `tests/backend/unit/test_repo_map.py::test_every_agent_file_exists`, `test_every_agent_has_at_least_one_entry_point` |
| Índice nunca fica dessincronizado em silêncio | `test_repo_map.py::test_committed_repo_map_matches_generator_output` | Compara `docs/REPO_MAP.json` commitado contra a saída do gerador rodado agora — falha se divergir |
| Prefixos de ID de issue não colidem entre agentes | `test_repo_map.py::test_id_prefixes_are_unique_across_agents` | Passou nos 34 agentes atuais |
| Consultável por agente externo via MCP | `services/mcp_server.py::describe_repository` | `tests/backend/unit/services/test_mcp_server.py::test_describe_repository_returns_valid_repo_map_json`, `test_mcp_server_registers_six_tools` |

---

## 14. Gaps fechados (2026-08-01) — Cobertura de acessibilidade cruzada com `C:\test\web-accessibility` (skill de referência 2026) + validação de Prompt/Context Engineering

Cruzamento sistemático entre os 34 prompts de agente existentes e o skill de referência `web-accessibility` (W3C WCAG 2.2 AA, WCAG 3.0 draft, ARIA in HTML Rec. 15 Apr 2026, WAI-ARIA 1.3). Achados reais (não hipotéticos — confirmados por grep/leitura direta do código antes de qualquer mudança).

### Gap 1: Classificador nunca detectava Svelte (código morto inalcançável)

`react_framework.py` já continha uma seção "SVELTE-SPECIFIC PATTERNS" completa, mas `SUPPORTED_FRAMEWORKS`/`classifier.py` só reconheciam react/vue/angular/tailwind — apesar do projeto aceitar `.svelte` como extensão de entrada em `/analyze/project`. A seção nunca podia disparar.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Svelte 5 (runes) e Svelte 4 (legado) detectados e auditados | `agents/svelte_framework/svelte_framework.py` (25º especialista) | `tests/backend/unit/agents/test_svelte_framework.py` (6 testes) |
| Classificador reconhece "svelte" como tecnologia | `shared/models.py::SUPPORTED_FRAMEWORKS`, `agents/classifier/classifier.py` | `tests/backend/unit/agents/test_classifier.py::test_classifier_detects_svelte` |
| Orchestrator roteia "svelte" → `svelte_framework` | `orchestrator.py::FRAMEWORK_AGENT_BY_TECH` | `tests/backend/unit/agents/test_orchestrator.py` (contagens de `agent_metrics` atualizadas 21→22, 20→21) |
| Sem duplicação: seção Svelte obsoleta removida de `react_framework.py` | `agents/react_framework/react_framework.py` | `tests/backend/unit/agents/test_react_framework.py` (6 testes, sem regressão) |

### Gap 2: Internacionalização / RTL não coberta por nenhum agente

Nenhum agente verificava `dir`, `<bdi>`/`<bdo>`, ou propriedades CSS lógicas vs físicas sob RTL — confirmado por grep vazio em todo `backend/src/agents/` antes da mudança.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| `dir` ausente em idioma RTL, `<bdi>`/`<bdo>` mal utilizados (WCAG 1.3.2/3.1.2) | `agents/wcag_semantics/wcag_semantics.py` — seção "INTERNATIONALIZATION & BIDIRECTIONAL TEXT" | `tests/backend/unit/agents/test_wcag_semantics.py` (contrato existente, sem regressão) |
| Propriedades físicas (margin-left etc.) em página `dir="rtl"` (WCAG 1.3.2) | `agents/css_analyzer/css_analyzer.py` — seção "INTERNATIONALIZATION — LOGICAL VS PHYSICAL PROPERTIES" | `tests/backend/unit/agents/test_css_analyzer.py` (contrato existente, sem regressão) |

### Gap 3: Componentes ultra-complexos — Data Grid virtualizado e Rich Text Editor colaborativo

`aria_specialist.py` só verificava relação de posse estrutural básica (`grid` → `row` → `gridcell`); nenhum agente cobria `aria-rowindex`/`aria-colindex` dinâmicos em grids virtualizados nem os papéis colaborativos ARIA 1.3 (`suggestion`/`insertion`/`deletion`/`comment`/`mark`).

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Data Grid/TreeGrid virtualizado: índices dinâmicos, roving tabindex vs aria-activedescendant, seleção multi-célula | `agents/widgets_a11y/widgets_a11y.py` — seção "DATA GRID / TREEGRID — VIRTUALIZED" | `tests/backend/unit/agents/test_widgets_a11y.py` (contrato existente, sem regressão) |
| Rich Text Editor colaborativo: papéis ARIA 1.3, throttling de anúncios de co-autoria | `agents/widgets_a11y/widgets_a11y.py` — seção "COLLABORATIVE RICH TEXT EDITOR" | idem |

### Fora de escopo (correto, não é gap)

`documents-media-a11y.md` (PDF/UA-2, EPUB 3.3, WebVTT AD, HLS/DASH) e `electron-desktop-a11y.md`: o projeto audita HTML/CSS/JS renderizado via Playwright, não arquivos de documento binários nem apps desktop Electron — mesma fronteira de escopo que já exclui iOS/Android nativos. Não fechado porque não deveria ser.

### Validação de Prompt Engineering / Context Engineering (pesquisa web, 2026)

Pesquisa nas fontes oficiais (Anthropic `claude.com/blog/best-practices-for-prompt-engineering`, guias de context engineering 2026) cruzada com os 35 prompts de agente:

| Prática 2026 | Status no projeto | Fonte |
|---|---|---|
| Role específico + single responsibility ("You are a X specialist. Your ONLY job is...") | ✅ Todos os 35 agentes | best-practices-for-prompt-engineering |
| Schema JSON explícito no prompt + validação Pydantic real no parse (dupla camada) | ✅ Todos os agentes — mais forte que só instrução de prompt | structured-output guides |
| Seções demarcadas ([PAGE CONTEXT]/[STYLES]/[ELEMENTS]) para escaneabilidade | ✅ Presente na maioria dos agentes de análise | Anthropic context engineering |
| Static-first, variable-last (system prompt fixo + HTML variável por último) | ✅ Arquitetura já separa `system_prompt` de `user_prompt` | prompt caching guidance |
| **Few-shot example (1 issue completo de exemplo) no prompt** | ❌ **Gap** — todos os agentes só têm o schema abstrato com placeholders (`<code> <name>`), nenhum exemplo preenchido | "one-shot para extração/classificação reduz inconsistência" |
| **Permissão explícita de incerteza ("se ambíguo, não reporte")** | ⚠️ Parcial — só `classifier.py` tem ("If evidence is ambiguous, omit... instead of guessing"); os 34 agentes de análise não têm instrução equivalente | "permitir incerteza reduz alucinação" |
| **Prompt caching (`cache_control: ephemeral`) no path Anthropic** | ❌ **Gap real de custo/latência** — `run_agent.py::_run_anthropic` envia `system` como string simples, sem cache breakpoint, apesar do system prompt ser 100% estático a cada uma das ~25 chamadas por auditoria | Anthropic: "cache pode cortar custo em até 90% e latência em até 85%" |

Os dois primeiros gaps (few-shot, permissão de incerteza) são mudanças de prompt de baixo risco mas em escala (35 arquivos) — não aplicadas nesta entrega, reportadas para decisão. O terceiro (prompt caching) é uma mudança arquitetural no engine (`run_agent.py`, `_run_anthropic`), com implicação direta de custo/billing — reportado e não implementado sem confirmação explícita.

---

## 15. Gaps fechados (2026-08-01) — Prompt Caching + Few-shot Examples (confirmado pelo usuário)

### Prompt Caching (Anthropic)

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| System prompt marcado com `cache_control: ephemeral` (bloco, não string simples) | `run_agent.py::_run_anthropic` | `tests/backend/unit/test_run_agent.py::TestAnthropicWirePayload::test_system_prompt_marked_for_ephemeral_caching` — valida o JSON real enviado à API |
| Sem system prompt, comportamento inalterado (string vazia, não bloco vazio) | idem | `test_empty_system_prompt_sent_as_plain_string` |
| Schema de tools também marcado no último bloco (mesmo prefixo estático por toolset) | `run_agent.py::_run_anthropic` (`tools[-1]["cache_control"]`) | Cobertura indireta via `TestAnthropicWirePayload` (payload real capturado) |

### Few-shot Examples + Permissão de Incerteza (25 agentes de análise)

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Cada agente de análise tem 1 exemplo de issue completo e preenchido (não só schema abstrato) | Todos os 25 `agents/*/[nome].py` que retornam `AccessibilityIssue[]` (perceiver, operability, understandability, robustness, aria_specialist, section508, css_analyzer, ajax_dynamic, cognitive, react_framework, screen_reader, mobile_a11y, forms_a11y, widgets_a11y, wcag_semantics, compliance_audit, agentic_ai_ui, spatial_3d_xr, web_components, niche_domains, angular_framework, vue_framework, svelte_framework, tailwind_css, visual_a11y) | `ruff`/`mypy` limpos + suíte completa (719 passed) — exemplo é apenas conteúdo de prompt, sem mudança de schema/contrato, então os testes de contrato existentes continuam validando sem alteração |
| Permissão explícita de incerteza ("If you are not confident... omit it — do not guess") | Mesmos 25 arquivos, adicionada junto ao exemplo | idem |

### Renomeação `test_orchestrator_v2.py` → `test_orchestrator.py`

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Nenhum arquivo de teste usa versionamento no nome (regra do README) | `git mv tests/backend/unit/agents/test_orchestrator_v2.py test_orchestrator.py` | `python -m pytest tests/backend/unit/agents/test_orchestrator.py` — 19 passed; suíte completa 719 passed |

---

## 16. Gaps fechados (2026-08-01) — Compaction API nativa, sincronização da base de conhecimento do chat, guia de teste por leitor de tela

### Compaction API nativa (Anthropic + OpenAI) — rede de segurança server-side

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Anthropic: `context_management`/beta `compact-2026-01-12` enviado via `extra_headers`/`extra_body` | `run_agent.py::_anthropic_messages_create` | `tests/backend/unit/test_run_agent.py::TestAnthropicWirePayload::test_compaction_api_beta_sent_as_safety_net` — valida header + corpo reais |
| Degrada sem quebrar se a conta/SDK não suportar (fallback automático) | idem | `test_compaction_api_falls_back_gracefully_when_unsupported` — simula 400 real via `httpx.MockTransport`, confirma 2ª chamada sem o campo |
| OpenAI: `context_management` via `extra_body` (kwarg direto é descartado em silêncio pelo SDK instalado — achado real durante a implementação) | `run_agent.py::_run_openai` | `tests/backend/unit/test_run_agent.py::TestRunOpenAIResponsesShape::test_compaction_sent_as_safety_net` |
| Degrada sem quebrar (OpenAI) | idem | `test_compaction_falls_back_gracefully_when_unsupported` — mesmo padrão de simulação de rejeição real |
| Threshold nativo (50k tokens Anthropic / 150k OpenAI) fica acima do teto client-side (80k chars ≈ 20k tokens) — raramente dispara, é só rede de segurança | `run_agent.py::_ANTHROPIC_COMPACTION_MIN_TRIGGER_TOKENS`, `_OPENAI_COMPACTION_THRESHOLD_TOKENS` | Documentado no comentário do módulo |

### Sincronização da base de conhecimento do chat (`a11y_reference.md`)

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Svelte 5 (runes) + Svelte 4 (legado) sincronizados com `svelte_framework.py` | `resources/a11y_reference.md` §5.D | Leitura manual — RAG do chat (`a11y_knowledge.py`) lê o arquivo em runtime, sem índice pré-computado a regenerar |
| i18n/RTL sincronizado com `wcag_semantics.py`/`css_analyzer.py` | `resources/a11y_reference.md` §9 | idem |
| Data Grid/Rich Text Editor sincronizado com `widgets_a11y.py` | `resources/a11y_reference.md` §10 | idem |

### Sincronização estrutural e permanente: `agent_knowledge.md` (gerado)

A sincronização manual acima resolve o estado de hoje; sem automação, a próxima mudança num prompt de agente voltaria a divergir do chat. Fechado com o mesmo padrão de `REPO_MAP.json` (gerador + teste de sincronia):

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Todo `SYSTEM_PROMPT` dos 25 agentes de análise entra no corpus do RAG do chat, sem boilerplate de schema JSON/exemplo | `scripts/generate_agent_knowledge.py` → `resources/agent_knowledge.md` | `tests/backend/unit/test_agent_knowledge_sync.py::test_covers_every_analysis_agent_prompt` |
| Arquivo gerado nunca fica dessincronizado em silêncio | `test_agent_knowledge_sync.py::test_committed_file_matches_generator_output` | Compara `agent_knowledge.md` commitado contra a saída do gerador rodado agora — falha se divergir |
| Registrado no corpus do RAG (`_CORPUS_FILES`) | `services/a11y_knowledge.py` | `test_agent_knowledge_sync.py::test_registered_in_chat_rag_corpus` |
| Chunks por agente ficam no tamanho esperado pelo design de chunking existente (< 6000 chars) | `generate_agent_knowledge.py::_split_into_subsections` — quebra por bloco em branco em `###` sub-headings, reaproveitando a estrutura que os prompts já tinham | `tests/backend/unit/services/test_a11y_knowledge.py::TestChunking::test_chunks_are_materially_smaller_than_the_whole_document` — maior chunk cai de 8248 para 2918 chars |
| Fluxo permanente: qualquer edição futura de `SYSTEM_PROMPT` propaga para o chat | Rodar `python scripts/generate_agent_knowledge.py` após editar um agente | Mesmo fluxo de manutenção de `scripts/generate_repo_map.py` |

### Guia de teste por leitor de tela + navegador + dispositivo

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Matriz de pareamento leitor de tela × navegador × SO (NVDA+Firefox, JAWS+Chrome/Edge, VoiceOver+Safari-only, TalkBack+Chrome-Android) disponível para o RAG do chat | `resources/a11y_reference.md` §11 | Fonte: WebAIM Screen Reader Survey 2026 (pesquisa web) |
| Chat pergunta SO/navegador/dispositivo/leitor de tela antes de dar passo a passo, em vez de instrução genérica | `services/chat_runtime.py::SYSTEM_PROMPT` regra 18 | `ruff`/`mypy` limpos; sem teste de conteúdo de prompt (comportamento conversacional, não determinístico) |

---

## 17. Matriz de conceitos agênticos 2026 por provider (validação cruzada, 2026-08-01)

Pesquisa nas docs oficiais dos 5 providers suportados para confirmar que Prompt Caching, Context Compaction e Tool Calling funcionam corretamente em qualquer um deles (via `agentic` auto ou escolha manual), não só nos dois cobertos nas seções 15-16.

| Provider | Prompt Caching | Context Compaction/Management | Tool Calling |
|---|---|---|---|
| **Anthropic** | ✅ Explícito, implementado — `cache_control: ephemeral` (seção 15) | ✅ Explícito, implementado — beta `compact-2026-01-12` com fallback (seção 15) | ✅ `tool_use`/`tool_result` — validado contra doc oficial (turno anterior) |
| **OpenAI** | ✅ Automático no servidor (prefixo repetido) — nenhuma ação do cliente necessária | ✅ Explícito, implementado — `context_management`/`compact_threshold` via `extra_body` com fallback (seção 15) | ✅ Responses API `function_call`/`function_call_output` — validado |
| **Gemini** | ✅ **Automático desde Gemini 2.5+, já funciona sem código** — implicit caching nativo da Interactions API, inclusive com `previous_interaction_id` (que o projeto já usa em `_run_gemini`). "There is nothing you need to do to enable this" (doc oficial) | ✅ Coberto pelo próprio modo stateful (`previous_interaction_id`) — o servidor guarda o histórico | ✅ Interactions API `function_call`/`function_result` — validado |
| **xAI** | ✅ Automático + **otimização implementada nesta entrega**: header `x-grok-conv-id` (doc oficial "Maximizing Cache Hits") roteia chamadas da mesma conversa/especialista para o mesmo servidor, maximizando o hit rate — `run_agent.py::_run_openai` (Responses API; xAI **não** usa `_run_chat_completions`, achado corrigido nesta entrega) | N/A — xAI não documenta uma API de compaction própria; contexto grande é absorvido pela janela de 2M tokens do Grok 4.1 Fast | ✅ Responses API, mesmo formato do OpenAI — validado |
| **Ollama Cloud** | ⚠️ Automático localmente (reuso de KV-cache), mas a API `/v1` **não reporta** `cached_tokens` nas stats de uso (limitação documentada do lado da Ollama, não do projeto) | N/A — sem API de compaction própria; usa Chat Completions (`_run_chat_completions`) | ✅ Chat Completions `tool_calls` — validado |

**Conclusão:** com qualquer provider selecionado (`agentic` auto ou manual), os 3 conceitos funcionam — automaticamente nos providers que já os embutem no servidor (Gemini, OpenAI caching, xAI caching), explicitamente onde o projeto precisa declarar (Anthropic caching+compaction, OpenAI compaction), e com uma otimização adicional específica do xAI implementada nesta entrega (`x-grok-conv-id`). O único ponto sem controle do lado do projeto é a Ollama Cloud não reportar métricas de cache — não afeta o funcionamento, só a observabilidade.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| xAI: header `x-grok-conv-id` enviado via Responses API (`_run_openai`, não `_run_chat_completions`) | `run_agent.py::_run_openai` | `tests/backend/unit/test_run_agent.py::test_xai_sends_conv_id_header_for_cache_routing` |
| Header nunca vai para OpenAI (é específico do xAI) | idem | `test_openai_provider_never_sends_xai_conv_id_header` |
| `conv_id` agrupa por especialista (leaf, via `log_prefix`) ou por conversa real (chat, via `conversation_id`) | `run_agent.py::AIAgent.__init__`, `chat_runtime.py` | Suíte completa sem regressão |

---

## 18. Structured Outputs nativo — os 5 providers (2026-08-01)

Pesquisa doc oficial de cada provider antes de implementar (mesmo rigor das seções 15-17). Gap real fechado: os 25 agentes de análise dependiam só de instrução de prompt ("Return ONLY valid JSON...") + validação Pydantic *depois* — nenhum provider restringia a decodificação do modelo de verdade. Shape exato por provider, confirmado nas docs:

| Provider | Parâmetro nativo | Onde no código |
|---|---|---|
| OpenAI (Responses API) | `text: {format: {type: "json_schema", name, schema, strict: true}}` | `run_agent.py::_run_openai` |
| xAI (mesmo endpoint Responses-compat) | idem OpenAI | `run_agent.py::_run_openai` |
| Anthropic (GA desde Claude 4.5+, sem beta header) | `output_config: {format: {type: "json_schema", schema}}` — mesclado com `output_config.effort` do adaptive thinking, nunca sobrescrito | `run_agent.py::_anthropic_messages_create` |
| Gemini (Interactions API) | `response_format: {type: "text", mime_type: "application/json", schema}` | `run_agent.py::_gemini_interactions_create` |
| Ollama / Ollama Cloud (endpoint OpenAI-compat) | `response_format: {type: "json_schema", json_schema: {name, schema, strict: true}}` — **achado real**: Ollama Cloud documentadamente não suporta ainda (só a instalação local, via outro parâmetro nativo `format`); tentativa é inofensiva porque cai no fallback | `run_agent.py::_chat_completions_create` |

Schema compartilhado pelos 25 agentes (`llm_client.py::ISSUES_RESPONSE_SCHEMA`): raiz `object` (exigência da OpenAI — schema raiz não pode ser `array`), campo `issues` como array de `AccessibilityIssue` (só os 13 campos que o *modelo* preenche — exclui `criterion_pt`/`severity_pt`/`fixed_element_html`/`url`, populados por estágios posteriores do pipeline), `additionalProperties: false` e todo campo em `required` (opcionais viram tipo nullable) — dialeto "strict mode" exigido pela OpenAI/Anthropic.

Escopo deliberado: só os 25 agentes de análise (`enabled_toolsets=[]`, resposta single-shot). Nunca aplicado em turnos com tools (`self.response_schema = None` quando `enabled_toolsets` não está vazio) — a maioria dos providers não combina "chame uma tool" com "responda só nesse schema" no mesmo turno; chat/classifier/clarifier ficam de fora.

Fallback automático testado ponta a ponta em todos os 5, mesmo padrão das seções 15-17 (tentativa nativa → se a API rejeitar, HTTP real simulado, refaz sem nenhum extra):

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| OpenAI: `text.format` enviado + fallback real via `httpx.MockTransport` (simula 400) | `test_run_agent.py::test_response_schema_sent_as_text_format`, `test_response_schema_falls_back_gracefully_when_rejected` (classe `TestRunOpenAIResponsesShape`) | 400 real, 2 chamadas HTTP, 2ª sem `text` |
| Anthropic: `output_config.format` mesclado com `effort`, sem sobrescrever + fallback real | `TestAnthropicWirePayload::test_response_schema_merged_into_output_config`, `test_response_schema_merges_with_output_config_effort`, `test_response_schema_falls_back_gracefully_when_rejected` | idem, `output_config` no `kwargs` original nunca herda o schema rejeitado |
| Gemini: `response_format` enviado + fallback (mock client) | `TestRunGeminiInteractions::test_response_schema_sent_as_response_format`, `test_response_schema_falls_back_gracefully_when_unsupported` | 2 chamadas, 2ª sem `response_format` |
| Ollama/Ollama Cloud: `response_format` enviado + fallback (mock client) | `TestChatCompletionsStructuredOutputs` (2 testes) | idem |
| Nunca aplicado em turnos com tools (chat) | `AIAgent.__init__::self.response_schema = response_schema if not self.enabled_toolsets else None` | Cobertura indireta — nenhum teste de chat quebrou |
| Schema idêntico injetado nos 25 agentes de análise | `backend/src/agents/*/[nome].py::call_llm(response_schema=ISSUES_RESPONSE_SCHEMA, ...)` | `ruff`/`mypy` limpos em 137 arquivos + suíte completa sem regressão de contrato (schema Pydantic inalterado, só mais restrito na decodificação) |

---

## 19. Execução paralela de tool calls, Retry/Backoff (achado: já resolvido pelo SDK) e Confidence Signals (2026-08-01)

Continuação do checklist de conceitos agênticos 2026 (seção 17), 3 itens fechados nesta entrega.

### Execução paralela de chamadas de tool

**Gap real:** quando o modelo pede 2+ tool calls no mesmo turno (comum em `agentic`/tool-use multi-step), as 4 rotas de provider (`_run_openai`, `_run_chat_completions`, `_run_anthropic`, `_run_gemini`) executavam cada chamada sequencialmente em um `for` loop — 6 loops sequenciais no total (streaming e não-streaming onde aplicável). Nenhum provider exige isso; é puramente uma limitação da implementação cliente. Como `run_local_tool` é síncrono e as tools são I/O-bound (chamadas de rede, leitura de arquivo), rodar em série desperdiça o paralelismo que o próprio modelo já expôs ao pedir múltiplas tools de uma vez.

**Correção:** novo `AIAgent._execute_tool_calls(calls)` — dispara todos os `tool_start_callback` antecipadamente, executa sequencialmente se houver ≤1 chamada (sem overhead de thread pool), ou via `concurrent.futures.ThreadPoolExecutor` se houver 2+, disparando `tool_complete_callback` dentro de cada worker conforme cada uma termina (progressivo, não em lote ao final). Substituiu os 6 loops sequenciais nas 4 rotas de provider.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| 2+ tool calls no mesmo turno executam concorrentemente, não em série | `run_agent.py::AIAgent._execute_tool_calls` | `TestParallelToolExecution` — prova real de concorrência via `time.sleep()` em tools mockadas: tempo total ≈ tempo da mais lenta, não soma de todas |
| `tool_start_callback` dispara para todas as chamadas antes de qualquer execução começar | idem | Teste de ordenação de callbacks |
| `tool_complete_callback` dispara progressivamente (conforme cada tool termina), não em lote | idem | Teste verifica ordem de conclusão não-determinística mas sempre antes do próximo turno do LLM |
| 1 chamada só não paga overhead de thread pool | idem (`if len(calls) <= 1: sequencial`) | Cobertura indireta — todos os testes de tool-use single-call continuam passando sem regressão de latência |

### Retry/Backoff (achado: nenhum código novo necessário)

Pesquisa nas docs oficiais dos SDKs Python: OpenAI (`max_retries=2` padrão, backoff exponencial em erros de conexão/timeout/429/5xx), Anthropic (idem, mesmo padrão), Google Gemini SDK (retry automático nativo, ~4-5 tentativas). **Nenhum dos 3 SDKs usados pelo projeto desativa isso** — `AIAgent` nunca passa `max_retries=0` nem constrói um `httpx.Client` customizado sem retry. Empilhar uma camada de retry própria por cima do retry do SDK é um anti-padrão documentado (multiplica o tempo de espera em cascata e pode mascarar timeouts reais como travamentos silenciosos) — por isso a decisão correta aqui foi **não** implementar retry customizado.

Achado colateral: dois comentários no código diziam o oposto do que é verdade ("sem retry/backoff próprio hoje", sugerindo que fosse um gap) — ambos corrigidos para documentar que os SDKs já cobrem isso por padrão e por que o projeto não duplica essa lógica.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Nenhum cliente de provider desativa o retry padrão do SDK | `run_agent.py::AIAgent` (todas as 4 rotas) | `TestSdkDefaultRetriesNeverDisabled` — grep estrutural garantindo que `max_retries=0` nunca é passado |
| Comentários enganosos corrigidos | `backend/src/services/llm_client.py`, `backend/src/config/settings.py` | Revisão manual — não é comportamento, é documentação |

### Confidence Signals

**Gap real:** `Severity` mede impacto *se* a violação for real, mas nenhum campo capturava a confiança do próprio agente de que a detecção é correta. Um issue `critical` com baixa confiança de detecção (ex.: heurística de HTML estático não pode confirmar que um atributo ARIA foi de fato preenchido corretamente via JS) e um issue `critical` com alta confiança eram indistinguíveis no schema — perdendo um sinal que ajuda o time humano a priorizar triagem.

**Correção:** novo enum `Confidence` (`high`/`medium`/`low`), eixo distinto de `Severity`, campo opcional `confidence: Confidence | None` em `AccessibilityIssue` (compatível com respostas antigas sem o campo). Propagado em 3 pontos: schema Pydantic (`shared/models.py`), schema JSON strict-mode compartilhado pelos 25 agentes de análise (`llm_client.py::_ISSUE_SCHEMA_PROPERTIES`, campo nullable no `enum`), e prompt de cada um dos 25 agentes (linha `"confidence": "high|medium|low"` no schema abstrato + valor concreto no few-shot example + extensão da frase de incerteza já existente explicando a semântica: `high` = padrão inequívoco no HTML, `medium` = leitura plausível mas pode ter explicação benigna que o agente não consegue inspecionar (ex.: atributo ARIA setado corretamente por JS fora do HTML estático), `low` = reportado mesmo assim por severidade alta apesar da incerteza.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| `Confidence` é eixo distinto de `Severity`, nunca confundido no schema | `backend/src/shared/models.py::Confidence`, `AccessibilityIssue.confidence` | `ruff`/`mypy` limpos + suíte completa (743 passed) sem regressão de contrato (campo opcional, backward-compatible) |
| Schema JSON strict-mode dos 25 agentes aceita `confidence` nullable | `llm_client.py::_ISSUE_SCHEMA_PROPERTIES` | Mesmo schema compartilhado da seção 18 — cobertura indireta via testes de Structured Outputs |
| Todos os 25 agentes de análise pedem `confidence` no prompt (schema abstrato + few-shot) | `backend/src/agents/*/[nome].py` | Script mecânico reportou `Changed 25/25`, sem skips; `ruff`/`mypy` limpos |

---

## 20. Response Caching e Interruptibilidade (2026-08-01)

Últimos 2 itens do checklist de conceitos agênticos 2026 (seção 17) endereçados nesta entrega; Memory/Personalization entre sessões foi conscientemente descartado (ver nota abaixo) em vez de forçado numa arquitetura que não tem sistema de identidade de usuário.

### Response Caching (exact-match, não semântico)

**Gap real:** os 25 agentes de análise (single-shot, sem tools) refaziam a chamada completa ao provider mesmo quando o MESMO HTML era reanalisado sem alteração dentro de uma janela curta (reabertura do relatório, múltiplas abas, retries do usuário) — custo e latência duplicados sem nenhum benefício.

**Decisão deliberada — exact-match, não semântico:** uma cache por similaridade de embeddings arriscaria dar cache-hit num HTML que mudou de forma relevante para acessibilidade mas ficou "parecido" na projeção vetorial — inaceitável numa ferramenta cujo propósito é justamente detectar essas mudanças. Hash exato do prompt completo (provider+model+system+user+temperature+presença de schema) com TTL curto (`A11Y_RESPONSE_CACHE_TTL_SECONDS`, default 300s) é a escolha correta: sem risco de mascarar uma mudança real.

**Escopo:** só leaf single-shot sem tools — mesmo escopo do `response_schema` de Structured Outputs (seção 18). Chat/tools nunca cacheia (são conversacionais por natureza).

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Cache em memória por processo, TTL configurável, LRU quando cheio | `backend/src/services/response_cache.py::ResponseCache` | `tests/backend/unit/services/test_response_cache.py` (6 testes: chave estável, hit/miss, expiração por TTL, LRU) |
| `call_llm` consulta a chave ANTES de chamar o AIAgent; grava o resultado após sucesso | `llm_client.py::call_llm` | `test_llm_client.py::test_call_llm_second_identical_call_hits_cache_no_second_agent_call` — 2ª chamada não instancia `AIAgent` |
| Chave usa o provider/model JÁ RESOLVIDO (não a tier bruta) — evita devolver resposta de outro modelo após um fallback automático | `llm_client.py::call_llm` (chave computada depois de `resolve_model_and_provider`) | Revisão de código — comentário explica o motivo |
| Nunca cacheia turnos com tools (chat) | `cacheable = ... and not enabled_toolsets` | `test_call_llm_never_caches_when_toolsets_present` |
| Desativável via settings (`A11Y_RESPONSE_CACHE_ENABLED=false`) | `config/settings.py::a11y_response_cache_enabled` | `test_call_llm_cache_disabled_calls_agent_every_time` |
| `is True` (não truthy simples) na leitura do flag | `llm_client.py::call_llm` | Comentário explica: a suíte inteira usa `settings=MagicMock()` sem configurar este campo; truthy simples ativaria cache em quase todo teste existente e causaria contaminação entre testes que reusam o mesmo prompt |
| `refresh_settings()` limpa a cache junto com o cache de provider/model | `llm_client.py::refresh_settings` | Revisão de código — mesma função que já limpava `model_router.clear_cache()` |

### Interruptibilidade (cancelar um turno de chat em andamento)

**Gap real:** o chat não tinha nenhum canal explícito para interromper um turno em andamento no lado do servidor — só existia o `abort()` do lado do cliente (fecha a conexão HTTP, mas não avisa o backend a parar de trabalhar).

**Limitação honesta, documentada no código:** best-effort por natureza. Uma chamada HTTP síncrona do provider já em andamento numa thread worker (`asyncio.to_thread`) não pode ser abortada de fora — não é uma limitação do projeto, é como `concurrent.futures.Future.cancel()` funciona (retorna `False` se o trabalho já começou a rodar). O que É garantido: o servidor para de entregar mais eventos ao stream imediatamente e cancela a task assim que possível.

**Implementação:** `chat_progress.py` ganha um 3º mecanismo (além do sink de progresso e do registro de clarify) — `new_cancel_token()`/`cancel_event()`/`request_cancel()`/`clear_cancel_token()`, usando `asyncio.Event` (não `threading.Event` como o clarify) porque o cancelamento é sinalizado de dentro do mesmo loop de evento (outra requisição HTTP), não de uma thread worker. `stream_chat` cria o token no início do turno, entrega via evento `stream_id`, e espera na fila E nesse evento simultaneamente via `asyncio.wait`. Nova rota `POST /chat/cancel {stream_id}`. Frontend: `useChat.ts::stop()` já fazia `abort()`; agora também dispara `sendCancel(streamId)` (best-effort, sem bloquear o `abort()` que continua sendo o que garante a UI parar na hora).

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Evento `stream_id` é o primeiro evento de cada turno | `chat_runtime.py::stream_chat` | `test_stream_chat_emits_event_sequence` — `types[0] == "stream_id"` |
| Cancelamento para de entregar eventos ao stream sem esperar a task em andamento terminar (não bloqueia o cliente) | `chat_runtime.py::stream_chat` (branch `cancelled=True`, sem `await task` síncrono) | `test_stream_chat_cancel_stops_the_stream_before_agent_finishes` — agente mockado fica bloqueado numa `threading.Event`; o teste recebe o evento `cancelled` sem esperar o agente "terminar" |
| `POST /chat/cancel` entrega ao registro; `False` se o token já não existe | `routes/chat.py::chat_cancel`, `chat_progress.request_cancel` | `test_chat_cancel_route_delivers_to_the_progress_registry`, `test_chat_cancel_route_unknown_stream_id_returns_false` |
| Registro de cancelamento usa `asyncio.Event` (mesmo loop), não `threading.Event` (thread cruzada, como o clarify) | `chat_progress.py::new_cancel_token` | `test_cancel_event_is_awaitable_asyncio_event`; comentário do módulo explica a diferença |
| Token é limpo em TODO caminho de saída do turno (sucesso, erro, out-of-scope, needs-clarification, cancelamento) | `chat_runtime.py::stream_chat` (`finally` + 2 `return` antecipados) | Cobertura indireta — nenhum teste de chat existente quebrou (42+ testes de `stream_chat`) |
| Frontend: `stop()` dispara `sendCancel` além do `abort()` já existente, sem bloquear a UI | `web/src/hooks/useChat.ts::stop`, `web/src/services/chat.ts::sendCancel` | `web/src/hooks/__tests__/useChat.cancel.test.tsx` (4 testes: abort sem stream_id, cancel com stream_id, novo turno esquece o id antigo, evento `cancelled` não lança erro) |

### Memory (episódica/semântica) e Personalização entre sessões — descartado, não implementado

Perguntado ao usuário explicitamente antes de agir: o projeto não tem sistema de identidade de usuário — cada conversa é isolada por `conversation_id`, sem storage persistente entre sessões (nem contas, nem autenticação). Implementar memória/personalização de verdade exigiria criar esse sistema primeiro, uma mudança estrutural fora do escopo dos gaps anteriores. Decisão do usuário: pular por agora em vez de forçar uma versão simplificada que não reflete o conceito real (2026-08-01).

### Regressão pré-existente encontrada e corrigida durante a verificação (não é desta entrega)

Ao rodar a suíte completa do `web/` como parte da verificação desta entrega, `ChatScreen.liveRegion.test.tsx` falhava e `tsc --noEmit` apontava 2 erros de tipo em `ChatScreen.tsx` (`accessibilityRole="listitem"` não é um `AccessibilityRole` válido do React Native) — ambos de uma feature de renderização de markdown-lite (listas/links no balão) de um turno anterior desta sessão, não desta entrega. Corrigidos por serem regressões reais capturadas pelo próprio gate de verificação: o teste agora aceita `<p>` além de `<div>` (o novo renderer usa `<p>` para parágrafos, mais semântico), e os 2 `accessibilityRole="listitem"` ganharam `as any` — mesmo padrão já usado 3x em `SettingsScreen.tsx` para roles ARIA que o RN não tipa mas o `react-native-web` aceita.

---

## 21. Gaps finais do checklist agêntico 2026 — Native Tools, Context Drift + Reflection/Replanning, Multimodal, Batch Inference (2026-08-01)

Auditoria termo-a-termo do checklist completo (Core LLM, Context Engineering, Agent Engineering, Production AI, UX, Infraestrutura) cruzada contra o código real (grep, não memória) identificou 5 gaps novos. Todos pesquisados nas docs oficiais dos 5 providers antes de qualquer implementação, mesmo rigor das seções 15-20.

### Native Tools — decisão informada, sem código novo

Pesquisa confirmou que os 5 providers oferecem tools nativas/built-in: `web_search`/`web_fetch` (OpenAI, Anthropic, Gemini, xAI — shape `{"type": "web_search"}` no array `tools`), `code_execution`/`code_interpreter`, `computer_use`/`bash`/`text_editor` (client-side, Anthropic/OpenAI). Ollama Cloud não tem tool nativa nenhuma — seu "web search" é um endpoint REST separado que você mesmo orquestra, exatamente como o projeto já faz.

**Decisão:** `web_search`/`web_fetch` nativos seriam **redundantes** com `tavily_search`/`exa_search` já implementados — adicionar violaria a regra do próprio projeto contra duplicação de fluxos. `code_execution`/`computer_use`/`bash` seriam capacidades **novas**, mas não atendem nenhum caso de uso real do produto (um auditor de acessibilidade não precisa executar código arbitrário) — implementar aumentaria a superfície de segurança sem justificativa, contrariando a regra de não adicionar funcionalidade além do que a tarefa exige. Mesmo padrão de decisão da seção 19 (Retry/Backoff): pesquisa levou à conclusão de que a ação correta é **não** codificar nada, e documentar o porquê.

### Context Drift Detection + Reflection/Replanning (fechados juntos: causa → ação)

**Gap real:** nenhum dos 5 providers expõe um sinal nativo de "o modelo perdeu o fio" — pesquisa 2026 confirmou que só existe `finish_reason`/`stop_reason` por limite de tokens, nunca por qualidade (é um efeito emergente, invisível na API). A técnica prática e barata (sem chamada extra a LLM) é detectar **repetição**: mesma tool+args+resultado repetida na janela recente = o agente girando em falso.

**Correção:** `AIAgent._check_context_drift` (run_agent.py) registra a assinatura de cada tool call executada em `_execute_tool_calls` (janela deslizante de 6, limiar de repetição = 3). Ao detectar, anexa **uma única** reflexão (`[SYSTEM REFLECTION]`) ao resultado da tool que volta pro modelo, pedindo para reconsiderar a abordagem — essa é a ação de "Replanning" em resposta ao "Reflection": o modelo sempre lê o resultado da tool de volta, então a reflexão chega garantidamente, sem precisar tocar na lógica de mensagens específica de cada um dos 4 caminhos de provider. Novo `context_drift_callback` (mesmo padrão dos outros callbacks) dá transparência ao chat (`chat_runtime.py` emite `{"type": "phase", "text": "Reconsiderando a abordagem..."}`).

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Repetição exata (tool+args+resultado) 3x na janela dispara a reflexão | `run_agent.py::_check_context_drift` | `TestContextDriftDetection::test_repeated_identical_call_triggers_reflection_note` |
| Resultado diferente a cada chamada nunca dispara (progresso real, não loop) | idem | `test_varying_results_never_trigger_reflection` |
| Dispara só UMA vez por conversa (não fica implicando a cada repetição) | idem | `test_reflection_fires_only_once_per_conversation` |
| Callback de transparência recebe o motivo; erro no callback nunca quebra o loop | idem | `test_context_drift_callback_fires_with_a_reason`, `test_callback_error_never_breaks_the_tool_loop` |
| Detecção funciona também no caminho de 2+ tool calls paralelas | idem | `test_drift_detected_across_parallel_calls_too` |

### Multimodal Processing (gap real fechado — visão nos 4 caminhos de provider)

**Gap real:** anexos do chat só extraíam TEXTO de PDF/DOCX/PPTX/EPUB; nunca havia caminho de enviar uma IMAGEM (screenshot de UI) para o modelo interpretar visualmente — relevante pro caso de auditar apps sem HTML (nativo mobile) ou confirmar visualmente um problema de contraste.

**Correção, com shape confirmado nas docs oficiais de cada provider:**

| Provider | Shape do content block de imagem | Onde no código |
|---|---|---|
| OpenAI/xAI (Responses API) | `{"type": "input_image", "image_url": "data:<media_type>;base64,<data>"}` misturado com `input_text` | `run_agent.py::_openai_user_content` |
| Anthropic (Messages API) | `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}` misturado com `text` | `run_agent.py::_anthropic_user_content` |
| Gemini (Interactions API) | `{"inlineData": {"mimeType": ..., "data": ...}}` misturado com parts de texto | `run_agent.py::_gemini_user_parts` |
| Ollama/Ollama Cloud (Chat Completions) | `{"type": "image_url", "image_url": {"url": "data:..."}}` misturado com `text` | `run_agent.py::_chat_completions_user_content` |

**Fallback gracioso (achado real da pesquisa: nenhum provider documenta como saber ANTES da chamada se o modelo aceita imagem, e o catálogo do projeto (`agent/models_dev.py`) não tem esse metadado):** `AIAgent.run_conversation` tenta com a imagem; se falhar, refaz UMA vez sem ela (nota explicando o porquê anexada ao prompt) antes de cair pra outro provider inteiro — degradação mais leve primeiro. Especialmente relevante pra Ollama Cloud, cujo catálogo é majoritariamente texto-only e tem bug documentado de 500 no endpoint OpenAI-compat com alguns modelos de visão.

Extração de imagem no chat (`chat_runtime.py`): `extract_message_with_images` (turno atual) remove a imagem do texto e devolve separadamente; `preprocess_base64_attachments` (histórico) nunca reenvia imagens de turnos passados — reenviar base64 a cada turno infla custo/contexto sem benefício. **Bug real encontrado e corrigido durante a implementação:** o padding base64 (`=` final) era cortado pelo regex de delimitação e nunca restaurado no caminho de imagem (o caminho de documento já fazia essa correção) — corrigido antes de qualquer teste rodar, via revisão de código.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Shape correto por provider (4 caminhos) | `run_agent.py::_*_user_content`/`_gemini_user_parts` | `TestMultimodalImageInput` (7 testes) — 1 por provider + histórico Gemini + fallback |
| Sem imagem, contrato antigo intacto (string simples) | idem | `test_openai_without_images_keeps_plain_string_content` |
| Falha com imagem → refaz sem ela, nota explicativa, nunca propaga erro | `run_agent.py::run_conversation` | `test_run_conversation_retries_without_image_when_provider_rejects_it` |
| Imagem do turno atual extraída e removida do texto; histórico nunca reenvia | `chat_runtime.py::extract_message_with_images`/`preprocess_base64_attachments` | `tests/backend/unit/services/test_chat_attachments.py` (9 testes) |
| Padding base64 restaurado no caminho de imagem (bug real) | idem | `test_extract_message_with_images_removes_image_and_returns_it_separately` (falhava antes da correção) |

### Batch Inference — serviço + integração real no crawl (2026-08-01, 2 entregas)

**Gap real:** os 25 agentes de análise sempre rodam em tempo real; nenhuma chamada usa a Batch API de nenhum provider, mesmo em crawls grandes (até 50 páginas × 25 agentes = 1250 chamadas) onde o usuário não precisaria do resultado na hora.

**Pesquisa confirmou, por provider:**

| Provider | Batch API | Desconto | SLA | Formato |
|---|---|---|---|---|
| OpenAI | `POST /v1/batches` (referencia `input_file_id` de um upload JSONL) | 50% | até 24h | JSONL, até 50k requests/200MB |
| Anthropic | `POST /v1/messages/batches` (`requests[]` inline, sem upload) | 50% (empilha com prompt caching) | maioria <1h, máx 24h | inline, até 100k requests/256MB |
| Gemini | `client.batches.create(src=[...])` (`InlinedRequest[]` inline) | 50% | alvo 24h, geralmente mais rápido | inline (até 20MB) ou arquivo (até 2GB) |
| xAI | `POST /v1/batches` existe, mas **sem percentual de desconto documentado** | não especificado | "most complete within 24h" | JSONL, até 200MB/50k requests |
| Ollama Cloud | **Não existe** — só `/api/generate`/`/api/chat` síncronos | N/A | N/A | N/A |

**Camada de serviço:** `backend/src/services/batch_inference.py` — `submit_batch`/`poll_batch`/`fetch_batch_results` para os 3 providers com desconto claramente documentado (OpenAI, Anthropic, Gemini). `BatchNotSupportedError` para os demais (xAI, Ollama, Ollama Cloud, agentic) — o chamador deve cair pro pipeline síncrono existente, nunca falhar o fluxo por causa disso.

**Integração ao crawl (pedida pelo usuário logo em seguida — resolvido o problema que tinha ficado em aberto):** o obstáculo real era que os 25 agentes cada um constrói seu próprio prompt e chama `call_llm` internamente — não havia como saber de fora quais chamadas um `orchestrate()` faria sem reescrever os 25 agentes pra separar "montar prompt" de "chamar e parsear". Resolvido com uma **passada de coleta**: `orchestrate(html, TaskType.ANALYZE, batch_collect=True)` roda o pipeline normal (mesma seleção de agente via classificador, mesmo prompt de cada agente), mas com o modo ligado `call_llm` nunca liga pro provider — grava a chamada em `batch_collector.py` e devolve o sentinel `"[]"` (que todo agente já trata como "nenhum issue", o caminho mais comum e testado de cada um). O resultado dessa passada é descartado; só a lista de chamadas coletadas importa.

Depois de submeter as chamadas coletadas como UM batch e o job terminar, os resultados reais são inseridos no `response_cache.py` sob a MESMA chave que `call_llm` computa normalmente, e o pipeline roda uma SEGUNDA vez (coleta desligada) — cada `call_llm` acerta a cache com o texto real e cada agente faz seu próprio parsing/validação **sem nenhuma alteração nos 25 agentes**. Reutiliza 100% da infraestrutura de Response Caching já implementada (seção 20).

O `_active` (interruptor da coleta) é ligado pelo `orchestrator.py` só em torno do `asyncio.gather` dos agentes de análise — nunca em torno da chamada do classificador, que decide quais agentes rodar e por isso precisa continuar real mesmo durante a coleta. O `_pending` (lista que acumula) é vinculado UMA VEZ pela rota antes do loop de páginas, então chamadas de várias páginas caem no mesmo batch.

Novas rotas: `POST /analyze/crawl/batch` (crawlea + roda a passada de coleta + submete o batch, devolve `batch_id` imediatamente — 400 se o provider ativo não suportar) e `GET /analyze/crawl/batch/{batch_id}` (consulta o status; quando `completed`, popula a cache com os resultados reais, roda o pipeline de novo, e devolve o mesmo shape `CrawlResult` do `/analyze/crawl` síncrono). Persistência em disco (`batch_job_store.py`, mesmo padrão de `last_analysis_store.py`) porque submissão e consulta são requisições HTTP separadas, possivelmente horas depois.

| Promessa | Artefato | Evidência executável |
|----------|----------|----------------------|
| Submit/poll/fetch funcionam pros 3 providers documentados, shape exato confirmado na doc oficial | `batch_inference.py` | `tests/backend/unit/services/test_batch_inference.py` (16 testes: 1 classe por provider + providers não suportados) |
| Provider sem Batch API documentada levanta erro explícito, nunca falha silenciosamente | `batch_inference.py::BatchNotSupportedError` | `TestUnsupportedProviders` (xai, ollama, ollama-cloud, agentic) |
| OpenAI: upload JSONL real antes do batch (não é inline como os outros 2) | `_submit_openai_batch` | `test_submit_uploads_jsonl_and_creates_batch` — valida o conteúdo exato do JSONL enviado |
| Anthropic/Gemini: requests inline, sem upload de arquivo | `_submit_anthropic_batch`, `_submit_gemini_batch` | `test_submit_sends_requests_inline_no_file_upload`, `test_submit_builds_inlined_requests_with_custom_id_metadata` |
| Coleta ligada durante os agentes de análise, desligada durante o classificador | `orchestrator.py` (gather-scoped `batch_collector.enable/disable`) | `test_batch_collect_is_active_during_analysis_agents_but_not_classifier` |
| `call_llm` em modo de coleta nunca liga pro provider; devolve sentinel e grava a chamada | `llm_client.py::call_llm` | `test_call_llm_records_request_and_returns_sentinel_when_collecting` |
| Coleta nunca se aplica a chat/tools (mesmo escopo do response_schema/response_cache) | idem | `test_call_llm_collection_mode_never_applies_to_tools_turns` |
| Lista de coleta persiste através de múltiplas páginas (loop sequencial) | `batch_collector.py` | `test_pending_list_persists_across_multiple_enable_disable_cycles` |
| `POST /analyze/crawl/batch` rejeita provider sem Batch API, submete e persiste o job | `routes/analyze.py::analyze_crawl_batch_submit` | `tests/backend/unit/routes/test_analyze_crawl_batch.py::TestCrawlBatchSubmit` (4 testes) |
| `GET /analyze/crawl/batch/{id}` 404 se não existe, `running` sem resultado, `completed` com `CrawlResult` completo (incluindo páginas que já tinham falhado no crawl) | `routes/analyze.py::analyze_crawl_batch_status` | `TestCrawlBatchStatus` (3 testes) |

## Squad de acessibilidade — integração verificada

| Promessa | Artefato | Evidência |
|---|---|---|
| Plano com escopo, análise, correção opcional, QA e documentação | `backend/src/agents/squad/coordinator.py` | `tests/backend/unit/agents/test_squad_coordinator.py` (2 testes) |
| O plano é emitido no streaming e chega ao frontend | `chat_runtime.py`, `chat.ts`, `useChat.ts` | smoke runtime em `POST /chat/stream` com evento `squad_plan`; build web concluído |
| Portões e dependências ficam documentados | `contracts.py`, `docs/ARQUITETURA_SQUAD_ACESSIBILIDADE.md` | contrato `SquadTask`/`SquadPlan` e testes unitários |
| Aprovação não é diálogo e live preview não é diálogo | `ClarifyPanel.tsx`, `LivePreviewModal.tsx` | validação visual/e2e: `dialog=0`, `complementary` presente, iframe com DOM da página |

Limitação conhecida: o produto ainda não possui quadro persistente de backlog,
reatribuição manual ou histórico de cerimônias. O plano é gerado por turno e o
progresso é apresentado na conversa; isso não deve ser descrito como Scrum
persistente até essa camada ser implementada.

---
