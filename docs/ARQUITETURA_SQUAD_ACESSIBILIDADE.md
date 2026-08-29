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

Cada solicitação de análise pode gerar um `SquadPlan` com tarefas dependentes:

1. **Product scope** — entende o objetivo e mantém o trabalho dentro de acessibilidade.
2. **A11y analysis** — delega a análise aos especialistas aplicáveis e ao orquestrador.
3. **A11y remediation** — só aparece quando a solicitação pede correção/implementação.
4. **QA validation** — valida testes, renderização, axe-core e evidências.
5. **Documentation release** — consolida checklist, relatório, links e documentação.

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

## Estado atual e limites conhecidos

Está integrado hoje: geração do plano no runtime do chat, evento SSE,
indicação de progresso na interface, dependências, portões e testes unitários
do coordenador.

Ainda não existe um quadro persistente de backlog com cerimônias, histórico de
cada tarefa e reatribuição manual por papel. Atualmente o plano é gerado por
turno de conversa e seu progresso é exposto como estado do fluxo. Um quadro
persistente pode ser adicionado depois sem alterar os contratos dos agentes.

## Referências de processo

- [Scrum Guide](https://scrumguides.org/scrum-guide.html)
- [Atlassian — Scrum roles](https://www.atlassian.com/agile/scrum/roles)
- [Microsoft — multi-agent patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns)

## Verificação

```text
python -m pytest tests/backend/unit/agents/test_squad_coordinator.py -q
python -m compileall -q backend/src/agents/squad backend/src/services/chat_runtime.py
cd web && npx expo export:web
```

