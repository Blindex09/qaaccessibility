# Comportamento, Capacidades e Conceitos de IA — QA Accessibility

> Documentação gerada por auditoria direta do código-fonte. Cobre o **motor
> agêntico em si**: como a IA decide, se recupera de falha, aprende com o
> tempo, se protege, e quais conceitos de engenharia de IA (2026) o
> justificam — funcionalidades, ferramentas e capacidades do harness, não do
> produto de acessibilidade em si (ver `CAPACIDADES_ACESSIBILIDADE.md`).
> Data da auditoria: 2026-08-27.

---

## 1. O motor agêntico (`AIAgent`, `run_agent.py`)

Engine própria (não um wrapper fino de um único SDK) que fala com 7
providers/caminhos diferentes, cada um com o formato de API correto:

| Provider | Caminho real | Observação |
|---|---|---|
| OpenAI | Responses API | Compaction nativa, structured outputs, reasoning effort |
| Anthropic | API nativa | Prompt caching, extended thinking |
| Gemini | API nativa | Function calling, thinking |
| xAI | Responses API | Cache por-servidor via header `x-grok-conv-id` |
| Ollama (local) | API nativa `/api/chat` | `format`/structured outputs locais reais |
| Ollama Cloud | API nativa `/api/chat` (fallback OpenAI-compat) | **Sem prompt caching nem structured outputs reais** (verificado ao vivo, não suposição — ver seção 4) |
| OpenCode Go | Responses API (só `gpt-5.6-luna`) ou Chat Completions (demais modelos) | Roteamento por MODELO, não só por provider — achado real de auditoria |

Cada caminho suporta: streaming token-a-token, chamada de ferramentas (tool
loop com resultado real de execução), multimodal (imagem, com fallback
gracioso "refaz sem a imagem" se o modelo não suportar), compressão de
histórico longo, e narração de raciocínio (`thinking`/`reasoning`) quando o
provider expõe.

---

## 2. Roteamento de modelo — provider-agnóstico, sem lista fixa

- **"Alto"** (padrão): resolve o melhor modelo agêntico recente e
  tool-capable do catálogo (`agent/models_dev.py`), rankeado por reasoning →
  janela de contexto → custo. Nunca um nome de modelo fixo no código.
- **Tiers**: "Alto" (qualidade), "Fast" (classificador — barato/rápido),
  "Code" (fixer — modelos especializados em código quando existem).
- **"Agentic Auto"**: cascata que escolhe o primeiro provider concreto com
  API key configurada; em `tradeoff` alto, compara **custo real estimado**
  entre TODOS os providers disponíveis (não só a ordem de prioridade fixa) e
  escolhe o mais barato capaz da tarefa.
- **Cadeia de fallback verificada para Structured Outputs**: quando o
  provider ativo não garante JSON estruturado (ex.: Ollama Cloud), a chamada
  é roteada para uma cadeia de modelos **testados ao vivo** via OpenCode Go
  (`gpt-5.6-luna → kimi-k2.6 → glm-5.1 → deepseek-v4-flash → qwen3.8-max`) —
  se um modelo da cadeia falhar, o próximo é tentado automaticamente antes de
  desistir.
- **Confiabilidade com shrinkage bayesiano**: o roteamento aprende com o
  histórico real de chamadas (`model_reliability.py`) — `confidence =
  tentativas/(tentativas+20)`, nunca um corte binário abrupto. Uma falha
  isolada de infra não derruba um modelo bom do ranking do zero.

---

## 3. Esforço de raciocínio adaptativo

O classificador de complexidade (`complexity_router.py`) lê o **conteúdo
real** sendo analisado e decide um dial `tradeoff` (0–10, custo↔qualidade) —
nunca uma heurística fixa (`if len(html) > 50000`), porque tamanho de HTML
não é proxy confiável de complexidade real de acessibilidade. Esse mesmo dial
decide tanto QUAL modelo (seção 2) quanto QUANTO esforço de raciocínio
(`reasoning_effort`) aplicar naquela chamada específica — antes desta função,
o projeto desligava raciocínio incondicionalmente em toda chamada, mesmo em
tarefas que precisavam de mais cuidado.

---

## 4. Confiabilidade e recuperação de falha

- **Retry/backoff**: delegado ao SDK oficial de cada provider por padrão —
  decisão deliberada de **não duplicar** essa lógica (regra do projeto).
- **Cascata automática de failover**: se o provider primário falhar por
  saldo (402), rate limit (429), chave expirada (401) ou indisponibilidade
  (500/503), o próximo provider configurado é acionado sem interromper o
  usuário.
- **Self-heal de parâmetro**: se o provider recusar `temperature` ou
  `reasoning_effort` (modelo de reasoning que não aceita), a chamada é
  refeita uma vez sem o parâmetro rejeitado, em vez de falhar.
- **Recuperação de resposta vazia**: refaz com instrução JSON estrita antes
  de desistir.
- **JSON truncado**: detecta truncamento por limite de tokens, dobra
  `max_tokens` e continua o array a partir de onde parou.
- **Formatador humanizado de erro** (`error_formatter.py`): traduz 100% dos
  códigos técnicos (400–504, timeouts, `RESOURCE_EXHAUSTED` do Gemini) em
  mensagens claras e acionáveis em português — nunca expõe stack trace bruto
  ao usuário final.
- **Achados reais verificados ao vivo (não suposição)**: Ollama Cloud não
  tem prompt caching nem structured outputs reais em nenhum modelo da conta
  (confirmado por chamada de API real + issue pública do repositório
  `ollama/ollama`); xAI e Ollama/Ollama Cloud não expõem endpoint de
  embeddings — o roteador trata esses casos como conhecido-não-suportado
  ANTES de tentar a rede, em vez de descobrir isso a cada chamada.

---

## 5. Gestão de contexto e custo

- **Compressão de histórico** (`context_compressor.py`): remove comentários
  HTML, esvazia `<script>`/`<style>` volumosos, simplifica SVG complexo sem
  atributo de acessibilidade, substitui base64 longo por placeholder.
- **Batch Inference**: submissão assíncrona (OpenAI/Anthropic/Gemini, ~50% de
  desconto, SLA até 24h) para crawls grandes sem urgência — nunca no fluxo
  principal interativo. xAI e Ollama Cloud deliberadamente fora de escopo
  (sem desconto documentado / sem Batch API).
- **Cache de resposta exato** (`response_cache.py`): só para chamadas
  leaf single-shot sem tools (mesmo escopo de Structured Outputs) — hash
  exato, TTL curto, nunca cache semântico (arriscaria dar hit em HTML que
  mudou de forma relevante mas é "parecido" na projeção vetorial).

---

## 6. Auto-correção (Self-Healing)

Um agente estrategista (`self_healing.py`) decide a ORDEM e o AGRUPAMENTO de
correções — nunca uma lista de prioridade fixa: algumas correções têm efeito
cascata (corrigir headings pode resolver landmarks encontrados
separadamente), algumas são seguras de agrupar, outras arriscadas de
combinar. Verificação dinâmica real com axe-core depois de cada correção
(não confiança cega no que o LLM disse que corrigiu). Roteamento por
cascateamento: tenta modelos rápidos/baratos primeiro, escala pra modelos de
reasoning de ponta só se falhar na validação real.

---

## 7. Base de conhecimento (RAG híbrido)

- **Chunking por heading** de `a11y_reference.md` + `agent_knowledge.md`
  (este último **gerado automaticamente** do `SYSTEM_PROMPT` real dos 29
  especialistas de auditoria — muda um prompt, o conhecimento do chat
  atualiza sozinho no próximo `generate_agent_knowledge.py`).
- **Retrieval em 2 pernas + fusão**: BM25 (SQLite FTS5) e embeddings
  (cosine), fundidos por Reciprocal Rank Fusion (funciona em ranks, não
  scores — evita normalizar escalas incompatíveis).
- **Rerank por LLM**: reordena os candidatos fundidos por relevância real à
  pergunta antes de virar contexto — com fallback gracioso pra ordem da
  fusão se o rerank falhar.
- **Degradação graciosa sem embeddings**: sem API key de embeddings (ou com
  provider sem suporte — xAI/Ollama/Ollama Cloud), cai pra busca só por
  palavra-chave, nunca falha o turno.
- **Guarda-corpo de qualidade**: agentes de coordenação/pipeline (orchestrator,
  classifier, clarifier, `delegation_coordinator`, `squad`, `design_review`
  etc.) são explicitamente EXCLUÍDOS deste corpus — seu `SYSTEM_PROMPT` é
  instrução de roteamento, não conhecimento de domínio, e um bug real (2
  agentes vazando pro corpus) já foi encontrado e corrigido nesta auditoria.

---

## 8. Observabilidade e verificação

- **OpenTelemetry** (`telemetry.py`): no-op silencioso sem
  `OTEL_EXPORTER_OTLP_ENDPOINT` configurado — zero custo/risco em ambiente
  sem observabilidade.
- **Trace replay** (`trace_replay.py`): grava input+contexto+output de cada
  passo (chamada de LLM, tool, decisão de roteamento); permite reproduzir o
  cenário exato de um bug sem gastar de novo o custo de rodar tudo do zero.
- **Agent Evals estatísticos** (`eval_stats.py`): Pass@k, taxa de sucesso,
  variância amostral, intervalo de confiança — 1 execução de um agente de IA
  é evidência fraca (mesmo input pode dar A, B ou C em temperatura 0); este
  módulo agrega N execuções independentes em estatística honesta.
- **Hooks plugáveis** (`agent_hooks.py`): pontos de extensão do ciclo de vida
  (pré/pós-chamada de LLM, erro) que código externo registra/desregistra em
  runtime — N observadores por evento, sem editar o construtor do `AIAgent`.
- **Configuration Drift Detection** (`config_drift.py`): acusa quando uma
  variável de override de endpoint está ativa no ambiente do processo mas
  não declarada no `.env` do projeto — comportamento em runtime divergindo
  silenciosamente do que está documentado.

---

## 9. Segurança e confiabilidade do próprio agente

- **PII Guard + Middleware de redação**: escaneia todo corpo de resposta
  JSON e substitui PII detectada (SSN, CPF, e-mail, número de cartão) por
  `[REDACTED]` antes de sair ao cliente — padrões técnicos mínimos, sem
  vocabulário de domínio.
- **Rate limiting por IP**: janela de 60s, máximo 30 requisições.
- **Proteção SSRF**: bloqueia IPs privados/internos e `localhost` antes de
  buscar uma URL fornecida pelo usuário.
- **Secret store com DPAPI** (Windows): persistência de segredo local
  criptografada, migração automática de segredo em texto plano no `.env`.
- **Guarda de escopo de projeto local**: a IA só pode ler/corrigir/executar
  teste em um diretório local se houver evidência estrutural (nome do
  diretório) de que é um projeto de acessibilidade — fronteira sobre ONDE no
  disco a IA pode agir, não uma blacklist de conteúdo/intenção (proibida
  pelas regras do projeto).
- **Aprovação obrigatória de ferramenta com efeito real**: criar issue/ticket
  externo, falar via NVDA, ler arquivo local fora do sandbox — todos exigem
  confirmação explícita antes de executar (`requires_approval=True` no
  registry de tools).
- **Sanitização de prompt injection**: todo `SYSTEM_PROMPT` de agente de
  auditoria trata o HTML analisado como DADO não confiável, nunca instrução —
  texto dentro do HTML que parece comando ("ignore instruções anteriores")
  é tratado como evidência de conteúdo malicioso da própria página, não como
  comando real.

---

## 10. Interação de chat

- **Streaming SSE** com narração de raciocínio em tempo real, busca paralela
  (Tavily + Exa) durante o turno, e botão "Parar" best-effort
  (`POST /chat/cancel`).
- **Clarifier**: triagem semântica do primeiro turno (dentro ou fora do
  escopo de acessibilidade) antes de qualquer ferramenta ser chamada.
- **Squad de acessibilidade** (`squad/`): monta um `SquadPlan` por
  solicitação complexa — escopo, análise, correção opcional, QA,
  documentação — com tarefas dependentes/estados e portões de aprovação
  (evento SSE `squad_plan` atualiza a interface em tempo real).
- **Anexo de imagem**: o modelo analisa visualmente screenshots de UI
  anexados no chat (útil pra apps nativos sem HTML, ou confirmar visualmente
  um problema de contraste).

---

## 11. Conceitos de engenharia de IA que fundamentam o projeto

Três documentos de referência conceitual (`docs/*.md`) guiam toda decisão de
arquitetura de IA deste projeto — não são leitura passiva, são checklist
operacional consultado antes de qualquer entrega:

1. **`conceitos-ia-para-desenvolvimento-de-software.md`** — Harness
   Engineering, roteamento determinístico vs. decisão de conteúdo pela IA,
   decomposição de tarefa, Agent Evals, trajetória, custo, detecção de loop,
   checkpoints, graceful degradation. Regra central aplicada em todo o
   projeto: **a decisão de CONTEÚDO é da IA; a decisão de ROTEAMENTO é
   determinística** — nunca invertido.
2. **`metodologia-verificacao-arquitetura.md`** — a pirâmide de verificação
   (Static Analysis → Unit → Component → Architecture Fitness Functions →
   Contract → Integration → Non-Functional → E2E → Regression → Quality Gate
   → Observability). Regra aplicada: nunca subir pro degrau mais caro sem
   esgotar os baratos antes; todo bug real corrigido ganha teste de
   regressão, sempre.
3. **`conceitos-ia-seguranca-confiabilidade.md`** — sandboxing, permission
   boundaries, blast radius, adversarial evals, recovery/resilience.
   Aplicado sempre que a mudança toca execução de código gerado, ferramentas
   expostas a um sub-agente, ou conteúdo vindo de fora (busca web, input do
   usuário) — ver seção 9.

---

## 12. Limites honestos (o que a IA aqui deliberadamente NÃO faz)

- **Sem memória/personalização entre sessões** (decisão explícita do
  usuário) — sem sistema de identidade cross-sessão.
- **Sem classificador de complexidade por LLM barato** (ao contrário de
  outros projetos do mesmo autor) — roteamento 100% determinístico por
  design; só o CONTEÚDO da decisão vem do modelo.
- **Sem captura de fala real do NVDA** — exigiria add-on rodando dentro do
  processo do leitor de tela; a fonte de verdade é a árvore de acessibilidade
  real do navegador (ver `CAPACIDADES_ACESSIBILIDADE.md`, seção 4).
- **Nunca inventa dado de conformidade/organização** em documentos formais
  (VPAT, Declaração de Acessibilidade) — usa placeholder visível em vez de
  fabricar.
