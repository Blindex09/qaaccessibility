# Módulo: observabilidade do agente

Atualizado em 2026-09-25. Código: `backend/src/services/audit_observability.py`.

## O que faz

`audit_scope()` cria um registro por execução, identificado por `run_id`, e o
propaga por `ContextVar`. Hooks de ferramenta e de chamada ao modelo acrescentam
eventos de início, conclusão, falha, duração e aprovação. `snapshot()` devolve
eventos e contadores; `audited_orchestrator` anexa esse snapshot ao resultado do
orquestrador. O registro mantém nomes de argumentos, mas não seus valores, e
não persiste o texto bruto de exceções. O log do servidor continua sendo a
fonte para diagnóstico detalhado de falhas.

## Contratos entre módulos

| Origem | Contrato consumido aqui | Verificação |
| --- | --- | --- |
| `agent_hooks` | Registra callbacks por evento, uma vez por identidade; após `clear_all_hooks()`, o próximo `audit_scope()` os instala novamente. | Testes de registro, limpeza e segundo turno. |
| `AIAgent._execute_tool_calls` | Dispara PRE e POST para cada ferramenta; threads paralelas recebem uma cópia do contexto do turno. | Teste de ferramenta real e regressão com duas chamadas paralelas. |
| `tools.registry` e `Settings` | Informam se a ferramenta exige aprovação e se o portão está ligado. | Teste de aprovação desligada. |
| Orquestrador | Recebe `audit` no `AgentResult.data` sem alterar a resposta dos especialistas. | Teste do decorador. |

## Achados e correções desta rodada

1. A suíte completa encontrava quatro falhas deste módulo. Uma flag local dizia
   que os hooks ainda estavam registrados depois de outro teste os limpar.
   Substituí a flag por `agent_hooks.ensure_hook`, cuja consulta e inserção são
   atômicas e usam o registro real como fonte de verdade.
2. Um teste com duas ferramentas reais em paralelo mostrou duas execuções e
   zero conclusões na auditoria. `ThreadPoolExecutor` não propagava o
   `ContextVar`. Agora cada chamada recebe sua própria cópia do contexto.
3. Os eventos de ferramenta antes guardavam valores de argumentos, inclusive
   texto de página sob nomes como `html` e arquivos em `zip_base64`; eventos
   de erro podiam guardar o texto bruto da exceção. Agora os valores são
   redigidos e o evento de erro registra apenas sua ocorrência. Um teste
   adicional mostrou que `AuditRun.add()` redigia valores sem observar o nome
   do campo; a sanitização passou a receber o mapa completo do evento.

## Evidência de verificação

- `ruff check` dos arquivos tocados: passou.
- `mypy` dos três arquivos Python de produção tocados: passou.
- Testes de `agent_hooks` e `audit_observability`: 19 passaram.
- Testes do motor do agente e do portão de aprovação junto desses módulos:
  114 passaram.
- Execução real, sem provedor de IA nem mocks: `AIAgent` extraiu um ZIP em
  memória pela ferramenta `unzip_and_list_files`. No primeiro turno houve
  1 pedido e 1 conclusão. Após limpar os hooks, duas extrações paralelas
  devolveram 2 resultados, 2 pedidos e 2 conclusões na auditoria. O conteúdo
  base64 do ZIP não apareceu no snapshot.

## Revisão do contrato de aprovação (2026-09-25)

O portão de execução agora publica uma decisão estruturada por `tool_id`.
A auditoria usa essa decisão no evento de conclusão, sem interpretar o texto
da resposta. A integração real e os testes de regressão estão documentados em
[`tools/APPROVAL_EXECUTION.md`](../../tools/APPROVAL_EXECUTION.md).
