# Capacidades de Acessibilidade — QA Accessibility

> Documentação gerada por auditoria direta do código-fonte (não por memória
> nem pelo README). Cobre tudo que o projeto **faz de verdade** em
> acessibilidade digital: funcionalidades, ferramentas e capacidades — o que
> está implementado e rodando, e onde estão os limites reais de escopo.
> Data da auditoria: 2026-08-27.

---

## 1. Padrões cobertos

- **WCAG 2.2** (Level A/AA), organizado literalmente pelos 4 princípios POUR
  (Perceptível/Operável/Compreensível/Robusto — cada princípio é um agente
  dedicado, não uma lista solta de regras).
- **WAI-ARIA 1.3** e "ARIA in HTML" (2026) — roles, estados, padrões de widget
  do W3C APG.
- **ADA / Section 508** (padrão federal dos EUA).
- **EAA / EN 301 549** (padrão europeu, citado nos agentes de compliance e de
  domínios de nicho).
- **W3C XAUR 2026** (WebXR Accessibility User Requirements) para conteúdo
  espacial/3D.
- **PDF/UA** (ISO 14289-1 e -2) para documentos PDF; normas de acessibilidade
  do Office (Word/Excel) para XLSX.

---

## 2. Os 29 especialistas de auditoria (o motor de detecção)

Cada um é um agente de IA com um `SYSTEM_PROMPT` focado — não um regex ou uma
lista de keywords. Rodam em paralelo, coordenados pelo orquestrador (seção 3).

| Grupo | Agentes | O que detectam |
|---|---|---|
| **Núcleo POUR** | `perceiver`, `operability`, `understandability`, `robustness` | Os 4 princípios WCAG 2.2 diretamente — alt text, contraste, foco/teclado, timing, labels, linguagem, ARIA name/role/value |
| **WAI-ARIA profundo** | `aria_specialist`, `widgets_a11y` | Padrões ARIA e de widget (modal, tablist, combobox, accordion) contra o W3C APG |
| **CSS e visual** | `css_analyzer`, `visual_a11y` | Contraste/outline/`prefers-reduced-motion` em CSS inline/embutido; análise visual quando há screenshot |
| **Conteúdo dinâmico** | `ajax_dynamic`, `agentic_ai_ui` | ARIA live regions, gerenciamento de foco em SPA, interfaces de chat/IA agêntica (streaming, HITL) |
| **Cognitivo** | `cognitive` | CAPTCHA sem alternativa, formulários sem feedback, linguagem complexa |
| **Frameworks front-end** | `react_framework`, `vue_framework`, `angular_framework`, `svelte_framework`, `tailwind_css`, `web_components` | Anti-padrões específicos de cada framework (`div onClick` sem teclado no React, `v-if` matando `aria-live` no Vue, binding `[aria-label]` incorreto no Angular, Custom Elements/Shadow DOM) |
| **Estruturas de conteúdo** | `forms_a11y`, `tables_data`, `link_checker`, `wcag_semantics`, `screen_reader` | Formulários, tabelas de dados, texto de link, headings/landmarks, compatibilidade real com leitor de tela |
| **Mobile** | `mobile_a11y` | Viewport/zoom (1.4.4), reflow (1.4.10), alvo de toque (2.5.8) — **só mobile web, não apps nativos** (ver seção 9) |
| **Documentos** | `pdf_accessibility`, `excel_accessibility` | PDF/UA, tabelas/células mescladas/abas do Excel |
| **Domínios emergentes** | `spatial_3d_xr`, `niche_domains` | WebXR/3D Canvas (W3C XAUR), Passkeys/WebAuthn, sonificação de dados, kiosks/POS, e-mails HTML |
| **Compliance formal** | `compliance_audit`, `section508` | Conformidade WCAG AA + Section 508 + EN 301 549 |

---

## 3. Orquestração inteligente (não é "rodar tudo sempre")

- **Roteamento estrutural**: o `orchestrator` só aciona um especialista de
  framework/domínio quando há evidência real no HTML (ex.: `mobile_a11y` só
  roda se houver `<meta name="viewport">`; agentes de framework só rodam se o
  `classifier` detectou aquela tecnologia).
- **Delegação agente-a-agente real**: o `delegation_coordinator` lê os
  achados da 1ª rodada e decide, via LLM (nunca por mapeamento fixo
  issue→agente), se algum especialista pulado deveria olhar a página mesmo
  assim — porque o que os outros encontraram sugere uma lacuna que só ele
  cobre. No máximo 2 delegações por rodada.
- **Segunda opinião**: `a11y_expert_reviewer` remove falsos positivos e
  re-pontua por impacto real de tecnologia assistiva.
- **Memória de falso positivo** (`lessons_store.py`): padrões generalizáveis
  (critério + assinatura estrutural do elemento) confirmados como falso
  positivo em análises passadas são injetados de volta como contexto —
  convergência sem re-treino, só depois de se repetir múltiplas vezes.
- **Pesquisa sob demanda** (`deep_research`/`gap_research`): quando um
  especialista não tem certeza se um achado é real, uma pesquisa normativa
  (WCAG/APG) é acionada automaticamente antes de descartar ou confirmar.
- **Dedup e classificador**: `classifier` identifica a stack (React/Vue/
  Angular/Svelte/Tailwind) antes de rotear; o resultado final é deduplicado
  entre especialistas que podem ter encontrado o mesmo problema por ângulos
  diferentes.

---

## 4. Verificação com tecnologia assistiva real

- **Árvore de acessibilidade REAL do navegador**
  (`POST /analyze/screen-reader`, tool de chat
  `verify_screen_reader_announcements`): cruza a árvore computada de verdade
  pelo Chromium (`page.accessibility.snapshot()` — a mesma API que
  NVDA/JAWS/Narrator consultam no Windows) contra regras determinísticas de
  nome acessível ausente ou genérico. Diferente do resto do pipeline (que
  estima a partir do HTML bruto via LLM), aqui o achado é confirmado pelo
  próprio motor de acessibilidade do navegador — zero inferência de IA nessa
  etapa específica.
- **Integração real com NVDA** (`nvda_service.py`, DLL oficial
  `nvdaControllerClient.dll` via ctypes): o chat pode mandar o NVDA falar um
  texto real (`nvda_speak`), e a verificação acima pode ler os achados em voz
  alta para confirmação humana quando o NVDA estiver rodando. Windows-only;
  fallback simulado gracioso em qualquer outro SO ou sem o NVDA ativo.
- **Limite honesto**: não existe captura oficial de "o que o NVDA realmente
  falou" (exigiria um add-on rodando dentro do processo do NVDA) — por isso a
  fonte de verdade é a árvore de acessibilidade real, não uma gravação de
  fala. JAWS, VoiceOver e TalkBack não têm nenhuma automação neste projeto,
  apenas conhecimento de referência (seção 6).

---

## 5. Revisão pré-desenvolvimento (shift-left)

- **`design_review`** (`POST /analyze/design-review`, tool de chat
  `design_review`): único agente do projeto que **não audita HTML/código já
  existente**. Recebe um requisito, user story ou descrição de componente em
  texto livre e antecipa riscos de acessibilidade — com critérios WCAG 2.2
  prováveis, severidade, motivo específico (preso ao texto real do
  requisito, não genérico) e recomendação acionável — antes de qualquer
  linha de código ser escrita. Requisito sem risco real → lista vazia,
  resposta válida, não uma falha.

---

## 6. QA híbrido (automático + manual)

- **Checklist híbrido** (`checklist` agent, `generate_checklist`): combina o
  "fail" automático com verificações manuais guiadas para o que scanners
  não cobrem sozinhos — qualidade real do `alt text`, nomes de botões-ícone,
  associação de labels, alvo de toque, fluxo de foco com leitor de tela,
  armadilhas de teclado em widgets customizados. Reconhece explicitamente
  que scanners automáticos só pegam 30–40% dos problemas reais.
- **Base de conhecimento de referência** (`a11y_reference.md`, RAG híbrido —
  ver documento de comportamento de IA): cobre AccName, padrões de teclado
  APG, JSX-A11y, PDF/UA, i18n/RTL, data grids virtualizados, editores
  colaborativos, guia de leitor de tela por navegador/dispositivo, árvore de
  decisão de `alt` do W3C, acessibilidade mobile nativa (referência, não
  automação), e o benchmark WebAIM Million para priorização.

---

## 7. Entregáveis e exportação

| Formato | Rota/tool | O que gera |
|---|---|---|
| **XLSX acessível** | `export_xlsx` | Planilha bilíngue, auto-filter, freeze panes, cores por severidade, organizada por princípio POUR |
| **SARIF 2.1.0** | `POST /export/sarif` | Integração direta com Pull Requests (GitHub Actions / GitLab CI) |
| **VPAT 2.4 (WCAG 2.2 Edition)** | `POST /analyze/vpat`, `generate_vpat` | Conformidade por critério (Supports/Partially/Does Not/N-A/Not Evaluated) para procurement/governo/Section 508 |
| **Checklist em PDF** | `export_checklist_pdf` | PDF/UA real via WeasyPrint a partir do checklist híbrido |
| **Declaração de Acessibilidade** | `generate_accessibility_statement` / PDF | Documento de conformidade pública — **nunca inventado por LLM**: só relata o que a análise real encontrou, usa placeholders visíveis quando dados da organização não são informados |
| **Suíte de testes Playwright + axe-core** | `POST /analyze/tests`, `generate_test_suite` | Testes executáveis prontos para CI, incluindo verificação de foco em SPA e elementos dinâmicos |

---

## 8. Automação de teste real (não simulada)

- **Selenium**: `location="local"` roda WebDriver + `chromedriver` de
  verdade, axe-core injetado via `execute_script`; `location="cloud"` roda
  via infraestrutura remota. Decisão de local/cloud é sempre do usuário,
  nunca escolhida silenciosamente pelo modelo.
- **Cypress**: mesmo contrato de duas camadas (local real / cloud real).
- **Postman/Newman**: contrato de API real, não mais reimplementação de 3
  checks fixos em Python (achado e corrigido em auditoria de 2026-08-10).
- **Auditoria cross-browser real**: roda axe-core em Chromium, Firefox e
  Webkit de verdade via Playwright, e faz diff das violações que aparecem só
  em alguns motores.
- **Portões de build em CI/CD**: workflow de GitHub Actions + script Git
  prontos para bloquear commits com violações críticas/graves.
- **Lighthouse CI** (`.lighthouserc.json`): gate de score de acessibilidade
  mínimo 0.9.

---

## 9. Escopo — limites honestos

- **Mobile**: só mobile **web** (HTML/CSS em navegador mobile). Não audita
  apps nativos iOS/Android compilados — a seção 13 do próprio
  `a11y_reference.md` documenta isso explicitamente como conhecimento de
  referência para o chat explicar, não como capacidade de automação.
- **Leitores de tela**: automação real só para NVDA (Windows). JAWS,
  VoiceOver e TalkBack são conhecimento de referência, não automação.
- **WAVE / Accessibility Insights / Axe DevTools** (a extensão): não
  integrados — são ferramentas de uso manual humano no navegador, não têm
  API de automação. O motor `axe-core` em si é usado de verdade (vendorizado,
  rodado via Chromium/CDP).
- **Gestão de defeitos externa**: Jira e Azure DevOps têm criação real de
  ticket (`create_jira_issue`/`create_azure_devops_work_item`); não há
  integração com Xray/Zephyr especificamente.

---

## 10. Integrações e protocolos

- **Criação de ticket**: GitHub, Jira e Azure DevOps (`create_github_issue`,
  `create_jira_issue`, `create_azure_devops_work_item`) — severidade mapeada
  para prioridade/campo de severidade de cada sistema; sem credenciais,
  simula a criação em vez de falhar.
- **Model Context Protocol (MCP)**: 6 tools expostos via stdio/FastMCP
  (`get_rendered_page`, `run_axe_audit`, `export_xlsx`, `analyze_page_full`,
  `analyze_site_full`, `describe_repository`) para uso por outros agentes/
  clientes MCP.
- **Agent-to-Agent (A2A v1.0, Linux Foundation)**: Agent Card público
  (`/.well-known/agent-card.json`) e API de delegação assíncrona de tarefas
  (`POST /a2a/v1/tasks` + subscribe/cancel) para federação com outros
  agentes de IA corporativos.
- **Webhook assíncrono**: `POST /webhook/analyze` + `GET /webhook/result/{job_id}`
  para integração server-to-server sem manter conexão aberta.
