# Proteção contra regressão: o que foi provado ao vivo no Ollama Cloud (módulos 1 a 3)

Atualizado em 09/10/2026. Objetivo: toda correção feita depois, inclusive as que nascem de testes com outro provedor
(Gemini, por exemplo), não pode estragar o que já foi provado ao vivo no Ollama Cloud em modo Alto. Este arquivo liga cada
comportamento provado ao teste automático que o guarda e ao cenário ao vivo que o repete.

## Como a proteção funciona, em três camadas

1. Testes automáticos (rodam em segundos, sem gastar cota). A suíte completa deve estar verde antes de qualquer commit:
   backend `pytest tests/backend`, ruff e mypy; front `jest` e `tsc`. Último resultado completo em 09/10/2026: 1.896 testes
   do backend passando (41 pulados) e 267 do front.
2. Script ao vivo: `scripts/verify_live_ollama_modules_1_to_3.py`. Repete no Ollama Cloud (Alto), pela mesma rota do
   navegador, os cenários dos três módulos e compara com os números medidos (custo com margem de 60 por cento, número de
   chamadas, sem erro, sem emoji, sem tabela, ZIP extraído sem erro). Troca o provedor para o Ollama e devolve a configuração
   anterior ao terminar. Sem cota, avisa e sai sem marcar nada como quebrado. Opção `--only m1`, `m2` ou `m3`.
3. Regra de mudança. Mexer em arquivo compartilhado por todos os provedores exige a suíte completa e, quando houver cota,
   o script ao vivo antes de dar por pronto. Arquivos compartilhados: `run_agent.py`, `backend/src/services/execution_scope.py`,
   `llm_client.py`, `route_advisor.py`, `chat_runtime.py`, `chat_tools.py`, `backend/src/config/settings.py`,
   `backend/src/routes/settings.py`, `backend/src/security/secret_store.py` e `web/src/hooks/useChat.ts`. Mudança que vale só
   para um provedor fica dentro do código daquele provedor.

Limite honesto: um teste automático prova a lógica, não o comportamento de um modelo real. O script ao vivo é o que fecha
essa lacuna, e só roda quando o Ollama Cloud tiver cota. Enquanto isso o que está provado é por teste, mais a troca de
provedor conferida pela API (a chave do Ollama continua guardada e ativa ao voltar para ele).

## Módulo 1 (conversa, triagem e roteamento Alto)

| Provado ao vivo | Guardado por | Repetir com |
|---|---|---|
| Pergunta curta custa por volta de 17 a 25 mil tokens, roteador pequeno | `test_route_advisor.py`, `test_squad_route_family.py`, `test_tool_groups.py` | m1-pergunta-curta |
| O roteador escolhe os grupos de ferramentas e o chat só recebe as necessárias | `test_tool_groups.py`, `test_route_advisor.py` | m1-pergunta-curta |
| Pedido fora do nicho recebe recusa educada em uma chamada barata, no tom da pessoa | `test_clarifier.py`, `test_chat.py` | m1-fora-do-nicho |
| Pedido vago recebe uma pergunta específica em uma chamada | `test_clarifier.py` | m1-pedido-vago |
| Limite de tokens da pessoa devolve o parcial com HTTP 200, no chat e na API | `test_token_budget.py`, `test_rest_token_limit.py`, `test_rule8_limits.py` | (configuração, sem cenário) |
| Pesquisa profunda custosa pede aprovação e avisa o custo | `toolMeta.costly.test.ts`, `test_chat.py` | (cartão, conferido na tela) |
| Fim normal de turno não mostra "Execução interrompida" | `useChat.toolCardsOnDone.test.tsx` | m1-pergunta-curta |

## Módulo 2 (auditoria de página por URL e seleção de especialistas)

| Provado ao vivo | Guardado por | Repetir com |
|---|---|---|
| Auditoria da página com erros do W3C: cerca de 150 a 210 mil tokens e 80 a 260 segundos (antes 594 mil e 28 minutos) | `test_a11y_expert_reviewer.py`, `test_orchestrator.py`, `test_progress_window.py` | m2-url-com-erros |
| Caminho de disco só é lido se a pessoa o escreveu, antes de qualquer aprovação | `test_request_context.py`, `test_local_project_scope.py` | (conferir na tela) |
| Erro de ferramenta não vira "modelo não encontrado" | `test_chat.py` | (URL inexistente, conferir na tela) |
| Sem emoji, sem tabela, sem HTML cru, sem afirmar verificação não feita | `test_chat.py` (prompt e filtro), `cleanAssistantMarkup.test.ts` | m2-url-com-erros |
| Achados com nível de evidência, separando confirmado de a verificar | `test_chat.py`, `test_a11y_expert_reviewer.py` | m2-url-com-erros |

## Módulo 3 (código, anexos, ZIP e projeto local)

| Provado ao vivo | Guardado por | Repetir com |
|---|---|---|
| ZIP anexado é extraído pelo sistema, sem erro de descompactar | `test_chat.py` | m3-zip-anexado |
| Resumo traz todos os achados, não só 10 | `test_chat.py` | m3-zip-anexado |
| Leitura de projeto local por caminho, com aprovação, sem regra de nome de pasta | `test_local_project_scope.py` | (cartão, conferir na tela) |
| Bloco de código com botão de copiar, sublinhado preservado | `cleanAssistantMarkup.test.ts` | (conferir na tela) |
| Chamada em andamento só conta como progresso enquanto chega dado; fluxo degenerado é encerrado | `test_progress_window.py`, `test_stream_guard.py` | m3-zip-anexado |
| Aviso de espera do provedor e dos especialistas, uma linha que se atualiza no lugar | `test_orchestrator.py`, `test_chat.py`, `useChat.toolCardsOnDone.test.tsx` | (só aparece quando algo demora) |

## O que ainda não está coberto

- Tom da pessoa, conferido ao vivo com três pedidos no módulo 1, está coberto por teste só no prompt, não na resposta de um
  modelo real. Fica para a primeira rodada com cota.
- Os cenários de cartão de aprovação e de tela são conferidos por quem olha a interface, não pelo script.
- O custo varia com o modelo que o roteador escolhe: a margem de 60 por cento absorve a variação normal, mas uma rodada
  fora dela pede olhar a saída antes de concluir que algo quebrou.

## Outros provedores

A matriz do que está provado em cada provedor, os números do Gemini e os defeitos que só apareceram nele estão em
`paridade_provedores.md`. O mesmo script, com `--provider <provedor>`, repete os cenários em outro provedor.
