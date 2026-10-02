# Auditoria das regras mestras: fontes web × QA Accessibility

Data: 2026-09-30. Base normativa do produto: CLAUDE.md atual, AGENTS.md e
pedidos posteriores do usuário sobre progresso conversacional e interface.
Fontes técnicas primárias consultadas na web; evidências locais obtidas por
leitura de código, testes baratos e E2E real já realizado nesta conversa.
Não houve alteração de código da aplicação nesta auditoria.

## Resultado geral

**Não há evidência para declarar conformidade integral.** Há divergências
reproduzidas: autorização por agente ausente no despachante de ferramentas,
orçamentos reiniciados em retries, planejamento pesado obrigatório e silêncio
durante triagem/julgamento. Outras propriedades são parciais ou não comprovadas.
Um teste passando não aprova toda a regra que seu nome parece representar.

Legenda: **Atende no escopo** = evidência positiva restrita ao caminho testado;
**Parcial** = controle existente, mas incompleto; **Diverge** = contradição
observada; **Não comprovado** = falta verificação suficiente. Nenhuma marca
vale automaticamente para todos os providers, ferramentas ou tipos de arquivo.

## 1. Processo de engenharia

| Regra | Referência pesquisada | Evidência no QA e avaliação |
| --- | --- | --- |
| Verificação barata antes de E2E caro | [Pirâmide de testes](https://martinfowler.com/articles/practical-test-pyramid.html) | CI tem ruff, mypy e pytest; 143 testes precederam o E2E recente. **Atende no escopo**, não prova toda mudança histórica. |
| Ler/verificar a costura entre módulos | [Contract tests](https://martinfowler.com/bliki/ContractTest.html) | Há testes de integração de rota/julgamento; o despachante ainda viola a permissão da instância. **Parcial**. |
| Bug real ganha regressão | [Pirâmide de testes](https://martinfowler.com/articles/practical-test-pyramid.html) | Remoção de mensagens ganhou teste DOM. Silêncio longo e autorização por toolset ainda têm lacunas. **Parcial**. |
| Evidência antes de declarar conclusão | [Testes e avaliação de agentes](https://www.anthropic.com/engineering/building-effective-agents) | E2E documentado como não concluído; afirmações antigas de migração total não se sustentam pelos caminhos restantes. **Parcial**. |
| Avaliador conhece objetivo e decomposição | [Evaluator–optimizer](https://www.anthropic.com/engineering/building-effective-agents) | model_arbitration recebe contrato, pedido e respostas; especialista/relatório com decomposição completa não foi exercitado no E2E. **Parcial**. |

## 2. Modelo, harness, classificação e roteamento

| Regra | Referência pesquisada | Evidência no QA e avaliação |
| --- | --- | --- |
| Modelo interpreta; harness impõe limites | [Agentes versus workflows](https://www.anthropic.com/engineering/building-effective-agents) | route_advisor usa IA e valida IDs; limites operacionais e permissões não são completos. **Parcial**. |
| Não classificar intenção por keywords/regex | [Routing](https://www.anthropic.com/engineering/building-effective-agents) | Caminho contextual novo usa modelo; model_router síncrono ainda pontua mini/flash/code/coder por nome em caminhos antigos. **Parcial**, não “zero legado”. |
| Ambiguidade vaga/material pede pergunta | [Desambiguação](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/cux-disambiguate-intent) | E2E sem URL perguntou qual site. **Atende no escopo**. |
| Continuação determinada pelo histórico prossegue | [Pedidos incompletos em contexto](https://learn.microsoft.com/en-us/style-guide/chatbots-virtual-agents/structural-technical-considerations) | Clarifier recebe histórico; URL posterior virou analyze_url sem nova pergunta. Confirmação curta sem URL adicional ainda não testada. **Parcial**. |
| Não perguntar desnecessariamente | [Desambiguação proporcional](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/cux-disambiguate-intent) | Há clarifier antes da squad e perguntas condicionais; não há avaliação ampla de perguntas redundantes. **Não comprovado** globalmente. |
| Aplicação em todo provider, sem exceções | [Controles por ferramenta](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) | CLAUDE.md registra Gemini/Factory sem steer ligado; apenas Ollama foi exercitada no E2E. **Diverge** da cobertura uniforme de redirecionamento. |

A literatura não proíbe todo roteamento determinístico: Anthropic admite
classificador LLM ou algoritmo tradicional e workflows predefinidos. A exigência
de julgamento semântico sempre pela IA é um **contrato particular do QA**, que
deve ser respeitado aqui, não apresentado como lei universal da indústria.
[Fonte](https://www.anthropic.com/engineering/building-effective-agents).

## 3. Segurança e autorização

| Regra | Referência pesquisada | Evidência no QA e avaliação |
| --- | --- | --- |
| Identidade e menor escopo de credencial | [Secrets management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) | Cofre DPAPI e resolução por provider existem; não demonstram identidade/escopo mínimo por execução. Chaves estáticas não provam emissão curta ou rotação. **Parcial**. |
| Ferramentas negadas por padrão | [Autorização de ferramentas](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) | Lista exposta respeita toolsets, mas _execute_tool_calls/run_local_tool não recebem/verificam allowlist da instância. Probe inofensivo executou ferramenta não concedida. **Diverge**. |
| Isolamento/sandbox limita blast radius | [Execução com guardrails e sandbox](https://www.anthropic.com/engineering/building-effective-agents) | Há ferramentas locais e subprocessos no processo/ambiente do usuário; não foi demonstrado limite uniforme de filesystem/rede/processos. **Não comprovado**. Aprovação não equivale a sandbox. |
| Caminhos e comandos validados antes de agir | [Defesa contra command injection](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html) | _resolve_safe_project_path usa realpath e recusa saída do project_dir; subprocessos observados usam lista de argumentos. Autorização do diretório-base e todas as ferramentas não comprovadas. **Parcial**. |
| Entrada/saída respeita schema explícito | [Input validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) | Pydantic e validação de IDs no consultor; reparação em call_llm_structured. run_local_tool não valida genericamente args pelo schema do registry antes do handler. **Parcial**. |
| Gravação preserva integridade sintática | [Parsing e seus limites](https://docs.python.org/3/library/ast.html) | Fixer valida balanceamento HTML; escrita local não demonstra validação sintática universal de JS/TS/CSS/outros arquivos antes da substituição. **Parcial**. Parsing sozinho tampouco prova execução correta. |
| Irreversível exige aprovação explícita antes | [Human-in-the-loop](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) | Portão bloqueia quando enabled e sem callback; settings permite desligar e executar ferramentas marcadas sem nova confirmação. **Diverge da redação incondicional** do CLAUDE.md; pode refletir outra política do usuário, precisa resolver o contrato. |
| Evento, erro, retry auditáveis | [Monitoramento de agentes](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) | Hooks de aprovação e logs de rota, retry e provider existem. Tracing distribuído estava desativado no E2E; não há prova de auditoria completa/durável de toda decisão. **Parcial**. |
| Falha retoma sem repetir trabalho provado | [Checkpoints e retomada](https://learn.microsoft.com/en-us/agent-framework/journey/workflows) | Squad persiste estados; checkpoints de correção são por sessão e em memória. Reinício perde esses checkpoints. Retomada completa não exercitada. **Parcial**. |
| Escalonamento humano real | [Supervisão proporcional](https://learn.microsoft.com/en-us/agents/center-of-excellence/responsible-ai) | Clarify/callback e UI de aprovação existem. E2E provou pergunta, não ação destrutiva aprovada/recusada de ponta a ponta. **Parcial**. |
| Sem supervisão excessiva de baixo risco | [Supervisão proporcional](https://learn.microsoft.com/en-us/agents/center-of-excellence/responsible-ai) | read_local_project_files é marcado requires_approval mesmo sendo leitura. Justificativa pode ser confidencialidade; calibração por escopo/contexto não demonstrada. **Não comprovado**, não é automaticamente bug. |

O probe de autorização só registrou um handler que devolve PROBE_EXECUTED
em memória, em um processo Python isolado. Não leu/grava arquivos do usuário,
não usou API e não tentou explorar ferramenta perigosa. Resultado observado:
exposed_tools=[], dispatch_result={'probe': 'PROBE_EXECUTED'}.
Isso reproduz uma lacuna no dispatcher, não prova exploração remota existente.
Pontos: run_agent.py, AIAgent._execute_tool_calls e run_local_tool.

## 4. Tempo, custo, loops, julgamento e interrupção

| Regra | Referência pesquisada | Evidência no QA e avaliação |
| --- | --- | --- |
| Laços/retries dentro de teto agregado | [Budgets e retries](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.html) | call_llm cria call_deadline por chamada; call_llm_structured repete call_llm com novo prazo. Squad encadeia fases sem esse mesmo deadline. **Diverge** da proteção agregada do turno. |
| Tempo/tokens/turnos adaptativos num orçamento único | [Profundidade proporcional à tarefa](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.html) | AdaptiveExecutionBudget existe no orchestrator, mas chat usa _CHAT_MAX_ITERATIONS=12; tempo leaf vem de agent_timeout_seconds. Não há orçamento adaptativo único atravessando triagem/squad/chat. **Diverge**. |
| Economia sem perder precisão; ondas e contexto compartilhado | [Pipeline simples quando suficiente](https://learn.microsoft.com/en-us/agent-framework/journey/workflows) | Especialistas têm execução concorrente/cache, mas planejamento PO→Tech Lead→EM antecede execução. E2E fez 26 chamadas antes de análise do site. **Diverge no caso simples**. |
| Loop detection e parcial honesto | [Degradação dentro do SLO](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.html) | Detecção de repetição existe em run_agent; preserva resposta quando julgamento falha. Cancelamento não mostrou resumo final do trabalho/limitações. **Parcial**. |
| Comparar modelos só quando ganho justifica custo | [Evaluator–optimizer e valor mensurável](https://www.anthropic.com/engineering/building-effective-agents) | IA escolhe participantes/juiz, mas classificou o clarifier pela auditoria final e pediu três respostas + juiz. **Diverge da economia no E2E**; não provado ganho de qualidade. |
| Vencedor não fixo por nome/ordem | [Modelos adequados à tarefa](https://www.anthropic.com/engineering/building-effective-agents) | Novas rotas escolhem IDs via IA e filtram catálogo. Fallback técnico mantém ordem/confiabilidade e não é evidência de julgamento semântico. **Atende no caminho contextual observado**. |
| Falha do julgamento preserva melhor resultado verificável | [Degradação explícita](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.html) | Mantém primeira resposta, não avalia se é a melhor verificável. Evita perder conteúdo, mas não satisfaz literalmente toda a regra. **Parcial**. |
| Cancelar não depende do modelo | [Cancelamento asyncio](https://docs.python.org/3/library/asyncio-task.html) | Evento/endpoint e UI funcionaram; HTTP síncrono já em thread não tem aborto garantido. **Parcial**: parar a UI não comprova parar gasto em transporte. |
| Corrigir/redirecionar sem perder progresso | [Human-in-the-loop e retomada](https://learn.microsoft.com/en-us/agent-framework/journey/workflows) | Steer aceito no E2E e injetado entre iterações no código; só instalado no agente principal depois do planejamento. Aplicação durante triagem/squad não comprovada. **Parcial**. |

AWS recomenda combinar budgets com limites de iterações; não sustenta a
proibição universal de dois controles. O requisito particular do QA é não
interromper por um contador rígido antes de seu orçamento adaptativo; aqui há
um contador fixo de 12 e falta propagação do deadline do turno. Não se propõe
remover proteção contra loops, e sim compatibilizar controles com o contrato.
[Fonte](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.html).

## 5. Pedidos posteriores de conversa e interface

| Pedido | Referência pesquisada | Evidência e avaliação |
| --- | --- | --- |
| Texto natural durante o trabalho, não tudo no final | [Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) e [ritmo conversacional](https://learn.microsoft.com/en-us/style-guide/chatbots-virtual-agents/structural-technical-considerations) | Tokens podem ser transmitidos, mas triagem/route_advisor/papéis são aguardados antes do agente principal. E2E teve ~124 s só de triagem. **Diverge** da experiência pedida. |
| Não usar narração robótica ou repetir frases fixas | [Ritmo conversacional](https://learn.microsoft.com/en-us/style-guide/chatbots-virtual-agents/structural-technical-considerations) | Mensagem de contexto e título removidos; useChat ainda monta “Verificando …” e outros templates. Remoção não transforma andamento em conversa contextual. **Parcial**. |
| Andamento consultável com setas, sem fala automática | [WCAG 4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) | Feed tem foco/setas e não é aria-live; testado em DOM/Chrome, não com NVDA real. **Atende à preferência no escopo**, acessibilidade normativa precisa avaliação específica. |
| Todo erro natural, sem stack trace/JSON na UI | [Error handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) | Formatador no tool_complete e nas exceções; mensagens fixas não são explicação gerada pela IA. Não há prova de cobertura de todo erro/provider/cartão. **Parcial**. |
| Não inventar causa nem culpar site sem evidência | [Ground truth das ferramentas](https://www.anthropic.com/engineering/building-effective-agents) | Prompt proíbe atribuir CDP/rede a bloqueio sem evidência; é instrução, não prova comportamental geral. E2E não acessou site. **Parcial/não exercitado**. |
| Não exibir markdown cru, saudação e placeholders retirados | [Formato legível da conversa](https://learn.microsoft.com/en-us/style-guide/chatbots-virtual-agents/structural-technical-considerations) | Testes DOM recentes comprovam remoção/renderização; não há norma web impondo ausência de markdown internamente. **Atende nos casos testados**. |
| Preservar especialistas e não duplicá-los | [Orchestrator–workers](https://www.anthropic.com/engineering/building-effective-agents) | Especialistas permanecem. Esta auditoria não comparou semanticamente todos os prompts para provar ausência de sobreposição. **Preservação confirmada; duplicação não comprovada**. |
| Nada antigo pode continuar sendo usado | [Simplicidade e limites do workflow](https://learn.microsoft.com/en-us/agent-framework/journey/workflows) | Síncrono antigo permanece para batch, flag off, modelo manual e fallback de contratos; ranking por nomes permanece nesses módulos. **Não houve eliminação total**, como já registrado na auditoria de roteamento. |

Importante: WCAG 4.1.3 trata de status programaticamente identificável sem
receber foco e também reconhece personalização/supressão pelo usuário.
Não se deve forçar anúncios contra sua preferência, nem concluir que tabindex
sozinho garante esse critério. É preciso separar histórico consultável de
status essencial e verificar a opção silenciosa com tecnologia assistiva real.
[Fonte W3C](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

“Texto corrido” foi interpretado conforme o pedido posterior: progresso em
blocos naturais escritos durante a execução, não despejo final nem exposição
de raciocínio privado. Não há exigência de revelar cadeia de pensamento ou
inventar atualizações quando nada verificável mudou.

## Evidência executada nesta auditoria

70 testes passaram: adaptive_budget (3), route_advisor (13), chat_progress
(18), fix_checkpoint_store (12), tool_approval (7), security_ssrf (17).
Sem chamadas pagas novas. Probe de autorização em memória reproduzido.
E2E real anterior: docs/e2e-interface-ollama-2026-09-30.md; logs em
logs/backend-e2e-router.stdout.log. Remoção de mensagens: 11 testes DOM e
19 testes helpers de chat passaram no turno anterior, com lint/typecheck.

A pesquisa avalia cada regra em relação a fontes técnicas, mas não converte
recomendação em obrigação universal. Não é pentest completo, certificação
WCAG, prova de todos os providers ou execução completa de todas as ferramentas.
Falta de prova não é tratada como falha comprovada. Regras específicas do seu
produto continuam válidas mesmo quando a literatura aceita alternativas.

## Prioridades propostas, sem implementação nesta etapa

1. Impor allowlist da instância no dispatcher, antes de qualquer handler.
2. Propagar orçamento do turno por triagem, planejamento, leaf, judge e repair.
3. Fazer a IA decidir a necessidade do planejamento/comparação pela tarefa
   da etapa atual; não tratar classificação simples como auditoria inteira.
4. Entregar atualizações contextuais úteis enquanto essas etapas executam;
   retirar templates não substitui um canal de progresso conversacional.
5. Tornar cancelamento/redirecionamento eficazes desde a primeira fase e
   explicitar resultados parciais, custos em andamento e limites da interrupção.
6. Resolver contradição de aprovação desligável versus obrigação incondicional
   antes de alterar o portão; completar evidência de sandbox, sintaxe e providers.
