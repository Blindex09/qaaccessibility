# Arquitetura da Squad de Acessibilidade

## Objetivo

O projeto continua focado exclusivamente em acessibilidade digital. A squad é
uma camada de coordenação para organizar análise, implementação, QA e
documentação; ela não substitui os agentes especialistas de WCAG, WAI-ARIA,
Section 508, frameworks ou leitores de tela.

## Papéis

| Papel | Responsabilidade no produto |
|---|---|
| Cliente/stakeholder | Informa objetivo, contexto, restrições e aprova mudanças quando necessário. |
| Product Owner | Define escopo e prioridade do trabalho de acessibilidade. |
| Scrum Master | Remove bloqueios e mantém o fluxo rastreável. |
| Engineering Manager | Cuida de capacidade, risco e dependências técnicas. |
| Tech Lead | Define a abordagem técnica e revisa decisões de implementação. |
| Developers | Implementam correções; podem atuar como especialistas de frontend, backend, QA ou acessibilidade. |
| QA Lead | Define evidências, regressão e critérios de aceite. |
| Especialista A11y | Interpreta WCAG/ARIA e revisa falsos positivos e impacto em tecnologias assistivas. |
| Documentation/Release | Registra evidências, checklist, relatórios e entrega. |

No Scrum oficial, Product Owner, Scrum Master e Developers são as accountabilities
formais. Cliente, QA, especialista A11y, documentação, Engineering Manager e
Tech Lead são papéis operacionais do produto, não um novo nível obrigatório de
hierarquia.

## Fluxo executado pelo chat

Cada conversa tem um `SquadPlan` com tarefas dependentes, criado uma vez e
avançado ao longo dos turnos:

| # | Tarefa | Papel | Depende de |
|---|---|---|---|
| 1 | `product-scope` | Product Owner | — |
| 2 | `tech-approach` | Tech Lead | `product-scope` |
| 3 | `cycle-planning` | Engineering Manager | `tech-approach` |
| 4 | `a11y-analysis` | Especialista A11y | `cycle-planning` |
| 5 | `a11y-remediation` | Developer | `a11y-analysis` |
| 6 | `qa-validation` | QA Lead | `a11y-analysis` |
| 7 | `documentation-release` | Documentation | `qa-validation` |
| 8 | `release-readiness` | Release | `documentation-release` |

As três primeiras são o planejamento da squad e rodam **antes** da análise: é o
Engineering Manager quem fecha as dependências externas (aprovação do usuário,
credencial, browser) antes de a squad executar.

`a11y-remediation` nasce `BLOCKED` e só é liberada por aprovação explícita.
`qa-validation` depende da **análise**, não da correção: uma auditoria sem
correção aprovada continua tendo QA e entrega.

### Por que a correção é incondicional e bloqueada

Antes, o `chat_runtime` decidia por regex de palavras-chave
(`corrig|remedi|fix|implementar|aplicar`) se a etapa 3 entrava no plano. Isso
quebrava de dois jeitos:

- **Violava a regra do README** ("zero keywords hardcoded que bloqueiem ou
  condicionem o comportamento da LLM"): o plano é injetado no prompt como
  contrato de execução, então a regex condicionava o modelo.
- **Errava em pedidos comuns.** "melhore o contraste", "ajuste os rótulos",
  "deixe acessível" não casam com nenhuma daquelas raízes — o plano chegava ao
  modelo sem etapa de correção justamente quando o usuário pediu correção.

Hoje a etapa existe sempre, visível e explicitamente inalcançável sem
aprovação. A autorização real nunca esteve no plano: está no
`requires_approval` das ferramentas de mutação e na regra 13 do prompt do chat
(checkpoint de remediação). Regressão coberta em
`tests/backend/unit/agents/test_squad_coordinator.py`.

As tarefas usam estados `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, `REVIEW` e
`DONE`. O plano também informa dependências, critérios de aceite e portões de
qualidade. O chat recebe o evento SSE `squad_plan` e mostra o progresso da
squad na conversa.

## Portões de qualidade

- Não implementar sem aprovação quando a ação exigir confirmação.
- Não aceitar correção que resulte em página vazia, renderização inválida ou
  ausência de evidência.
- Executar validação automatizada e, quando aplicável, revisão manual de
  teclado, foco, leitor de tela e conteúdo visual.
- Manter rastreabilidade entre problema, correção, teste, evidência e entrega.
- Não misturar sessões: iniciar uma nova auditoria encerra o preview anterior e
  cria o contexto de trabalho da nova página.

## Agentes, ferramentas e paralelismo

O `OrchestratorAgent` coordena especialistas de acessibilidade em paralelo,
faz merge/deduplicação e aplica limites e métricas. O fluxo sequencial de
correção, checklist e relatório ocorre depois da análise. A delegação A2A e o
MCP continuam sendo interfaces de integração; o `SquadPlan` organiza o fluxo
interno do chat e não cria um provedor de IA novo.

As ferramentas existentes permanecem as executoras do trabalho, incluindo
análise de página, correção, teste remoto, checklist, XLSX, VPAT, suíte de
testes, SARIF e live preview. A escolha de provider/modelo continua sob
responsabilidade do `model_router`; os papéis da squad descrevem a tarefa e
seu critério de qualidade, não forçam nomes de modelos.

## Cada papel é um agente

Seis papéis são agentes com prompt e responsabilidade próprios, em
`backend/src/agents/squad/role_agents/`. Um módulo por papel, sem sobreposição
— é a separação de responsabilidades que distingue uma squad de um agente só
com muitos prompts. A execução é compartilhada em `_runner.py`, para que a
separação seja de responsabilidade e não de código duplicado.

| Papel | Agente | Decide |
|---|---|---|
| Product Owner | `product_owner.py` | Escopo, público, prioridade, critérios de aceite |
| Tech Lead | `tech_lead.py` | Abordagem técnica, áreas de expertise, riscos técnicos |
| Engineering Manager | `engineering_manager.py` | Sequenciamento, dependências externas, risco de entrega |
| QA Lead | `qa_lead.py` | Evidência, verificação manual, regressão, veredito |
| Scrum Master | `scrum_master.py` | Triagem de bloqueios, rastreabilidade, saúde do fluxo |
| Release | `release_manager.py` | Prontidão, artefatos, risco residual |

Papéis que **já eram** agentes do pipeline não foram reimplementados (regra de
zero duplicação): Developer é o `fixer`, A11y Specialist é o
`a11y_expert_reviewer`, Documentation é `checklist`/`reporter`/`vpat_reporter`,
e Cliente é o próprio usuário. O coordenador **registra** o que esses já fazem,
em vez de duplicá-los.

### O handoff é o que torna a squad real

Cada papel devolve um `RoleDecision` com `summary`, `decisions`, `blockers` e
`handoff`. O `handoff` de um papel é **literalmente a entrada do próximo**: o
Tech Lead decide em cima do escopo que o PO fixou, o Engineering Manager
sequencia em cima daquela abordagem, o QA Lead define evidência em cima do que
foi realmente encontrado, o Release decide em cima do veredito do QA. Sem esse
encadeamento seriam opiniões independentes, não uma squad — e é isso que o
teste `test_o_proximo_papel_recebe_o_handoff_do_anterior` fixa.

O planejamento (PO → Tech Lead → EM) é sequencial de propósito. Rodar em
paralelo devolveria três pareceres que não se conhecem.

## Estado atual

- **Quadro persistente por conversa** (`squad_plan_store.py`): o ciclo é
  planejado **uma vez** e avança ao longo dos turnos, sobrevivendo inclusive a
  reinício do backend. Nenhuma squad real replaneja a sprint a cada frase dita.
- **Estados transicionam de verdade**: `READY → IN_PROGRESS → DONE/BLOCKED`,
  disparados por execução real. Tarefas executadas pelo pipeline existente
  (análise, correção, documentação) são registradas via `record_started` /
  `record_done` / `record_blocked` quando o trabalho de fato acontece.
- **Portões bloqueiam**: `SquadPlan.dependencies_met` impede uma tarefa de
  começar antes de as dependências fecharem. Entrega não fecha sem
  documentação, que não fecha sem QA. O agente do papel **nem chega a ser
  chamado** quando o portão está fechado.
- **A interface mostra o quadro**: o `useChat` mantém `squadPlan` com tarefas,
  papéis, estados e decisões, atualizado pelos eventos `squad_task` e
  `squad_decision`. O resumo de cada papel é anunciado como linha de status,
  então quem usa leitor de tela acompanha a squad trabalhando. Antes disso a
  interface recebia o plano e imprimia apenas a contagem de etapas.

### Bloqueio não é falha

Levantar um impedimento **não** marca a tarefa como `BLOCKED`. Numa squad
real, apontar o bloqueio *é* o trabalho: o papel entregou sua decisão e
registrou uma ressalva.

`BLOCKED` fica para quem de fato não entregou — o papel falhou (provider fora
do ar) ou não produziu decisão nenhuma. Os bloqueios continuam visíveis no
quadro e vão para a triagem do Scrum Master.

Isto veio de uma execução real (2026-08-30): o Product Owner quase sempre
registra alguma ressalva (público não informado, URL ausente). Tratar isso
como `BLOCKED` travava `tech-approach` e `cycle-planning` **para sempre** — o
portão de dependência nunca abria — e, como `planning_done` exige as três
`DONE`, o planejamento reexecutava a cada turno, anulando o quadro
persistente e gastando três chamadas de LLM por mensagem.

### Degradação

Um papel que falha nunca derruba o turno: devolve `succeeded=False` com um
bloqueio legível, e o Scrum Master tria. O Scrum Master só é acionado quando há
bloqueio de verdade — um papel falando sem impedimento é chamada de LLM
desperdiçada.

### O que ainda não existe

Não há cerimônias com histórico por tarefa nem reatribuição manual de papel
pela interface. O quadro é observável e persistente, mas não editável pelo
usuário.

## Referências de processo

- [Scrum Guide](https://scrumguides.org/scrum-guide.html)
- [Atlassian — Scrum roles](https://www.atlassian.com/agile/scrum/roles)
- [Microsoft — multi-agent patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns)

## Verificação

```text
python -m pytest tests/backend/unit/agents/test_squad_coordinator.py                  tests/backend/unit/agents/test_squad_coordinator_state.py                  tests/backend/unit/services/test_squad_plan_store.py -q
python -m ruff check backend/src/agents/squad backend/src/services/chat_runtime.py
python -m mypy --config-file mypy.ini backend/src
cd web && npm run typecheck && npm run test:ci
```

