# Módulo: aprovação e execução de ferramentas

Atualizado em 2026-09-25. O cadastro das ferramentas fica em `tools/registry.py`;
o portão de execução fica em `run_agent.py::run_local_tool`. A configuração
vem de `backend/src/config/settings.py` e da rota `/settings`. O chat usa
`backend/src/services/chat_runtime.py` e `web/src/screens/ClarifyPanel.tsx`.

## O que faz

Cada ferramenta registrada declara `requires_approval`. Quando a configuração
`approval_enabled` está ligada, `run_local_tool` mostra o nome, os argumentos
visíveis e um identificador SHA-256 da ação; só executa após resposta explícita
de aprovação. Sem canal de resposta, bloqueia. Com a configuração desligada,
executa sem confirmação adicional. A ferramenta `clarify` usa o mesmo canal
para perguntas, mas não é uma aprovação de efeito externo.

O executor emite uma decisão estruturada por chamada (`approved`, `cancelled`,
`blocked`, `disabled`, `not_required` ou `unknown_tool`). O registro de
observabilidade associa essa decisão ao `tool_id`, inclusive para chamadas
paralelas, em vez de deduzi-la do texto retornado pela ferramenta.

## Contratos conferidos

| Origem | Consumidor | Contrato |
| --- | --- | --- |
| `tools.registry` | `run_local_tool` | `requires_approval` controla o portão; a ausência do campo significa falso. |
| `/settings` | `get_settings()` | `approval_enabled` é booleano e a alteração vale sem reiniciar o servidor. |
| `run_local_tool` | `chat_runtime.on_clarify` | Pergunta com opções `Aprovar` e `Cancelar`; aguarda a resposta antes do handler. |
| `run_local_tool` | `agent_hooks` / `audit_observability` | Decisão estruturada emitida antes do evento de conclusão, ligada ao mesmo `tool_id`. |
| `chat_runtime` | `ClarifyPanel` | Evento `clarify` contém `request_id`, pergunta e escolhas; o cartão responde pelo chat. |

## Achados e correções

1. A auditoria lia palavras como “cancelada” no resultado para determinar a
   aprovação. Um handler aprovado que devolvia essa palavra era registrado
   falsamente como cancelado. A decisão agora vem do portão de execução.
2. A confirmação redigia segredos apenas no primeiro nível dos argumentos.
   Valores sob objetos e listas aninhados podiam aparecer no cartão. A redação
   agora percorre toda a estrutura.
3. Enquanto o sistema esperava a confirmação, os argumentos originais podiam
   mudar; o handler receberia um alvo diferente daquele mostrado. O portão
   congela uma cópia dos argumentos antes de apresentar a ação e usa a mesma
   cópia para executar.
4. O teste de navegador recebia o manifesto do Expo ao acessar `localhost`
   neste ambiente, em vez da página web. A configuração do Playwright agora
   usa `127.0.0.1`; a execução no Chromium passou após a correção.

## Verificação

- Testes do portão, hooks, auditoria, motor do agente, rota de configuração e
  integração: 141 passaram.
- Integração com a ferramenta registrada `read_local_project_files`, lendo um
  arquivo HTML de um projeto temporário real: bloqueio sem canal, cancelamento,
  aprovação e execução com a configuração desligada passaram. O conteúdo do
  arquivo foi lido somente nas duas execuções autorizadas pela configuração.
- Testes do cartão de aprovação, inclusive navegação acessível: 26 passaram.
- Testes da chave de aprovação por teclado e troca de provedor na interface
  real (Chromium): 2 passaram.
- `ruff` dos arquivos Python tocados e `mypy` dos três arquivos de produção:
  passaram.

## Limites

O teste integrado usa um projeto temporário e uma ferramenta de leitura local;
nenhum serviço externo ou provedor de IA foi acionado. O teste da interface
verifica a chave de configuração e o cartão separadamente. Um fluxo completo
com modelo real e publicação externa não foi executado nesta rodada.
