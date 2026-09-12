# Adaptação dos verificadores externos ao QAAccessibility

## ADL / Warden

O protocolo ADL foi aplicado como modelo de contrato: goal explícito,
acceptance checks executáveis, non-goals, budget e prova vinculada ao manifest.
O QAAccessibility já possui gates equivalentes em `GATES.md` e os cinco gates
foram verificados pelo Unlazy.

O Warden não foi executado como processo porque o ambiente atual não possui
Claude Code/Stop hook operacional. Criar um `.claude` fictício produziria uma
prova falsa; portanto, o resultado é `protocol-aligned`, não `warden-executed`.

## ArgusAgent

O diagnóstico e `repair --plan` foram executados sem alterações no alvo. O
setup headless revelou uma falha real: `--setup --non-interactive` ainda chamava
`input()` para escolher o modo de autenticação e terminava com `EOFError`.

O Argus foi corrigido para usar `subscription_cli` como default não interativo
quando o backend é Codex. O teste de regressão e Ruff passaram; em seguida o
setup real completou e o smoke test de uma resposta de agente passou.

Resultado: `runtime-diagnosed` e `setup-smoke-verified`. A missão real foi
iniciada pelo cockpit contra `C:\qaaccessibility`, mas não chegou ao executor:
o Manager classificou a tarefa e o Planner terminou com `planner backend exit 1`.
O log registra `External interrupt: daemon stop requested` e também o aviso de
que o snapshot de shell ainda não é suportado no PowerShell. Portanto, não há
relatório Argus nem evidência de trajetória produzida; o resultado desta
execução é `planner-blocked`, não aprovação do comportamento dos agentes.

Após permitir a execução e repetir a missão, o Engineer e o Reviewer do Argus
chegaram a executar a auditoria somente leitura. A entrega, contudo, falhou no
próprio Argus com `planner missing key-value completion marker`: o Planner
produziu uma decisão estruturada que não foi aceita pelo parser de conclusão,
e a rotina de recuperação não tratou esse erro como recuperável. O próprio
Argus registrou como correção necessária adicionar retry no mesmo thread e um
teste de regressão. Como não houve pacote final rastreável de artefatos, esta
execução permanece `audit-executed-delivery-blocked`, não uma aprovação
independente do QAAccessibility.

## Horizon

O Horizon é aplicável a execução/verificação/repair de código gerado, não ao
fluxo completo do QAAccessibility. A tentativa de usar seu harness diretamente
como auditor geral não seria metodologicamente válida: o domínio do Horizon é
code execution/eval e exige um cliente/modelo próprio. Ele permanece como
referência para uma futura avaliação isolada do fixer/executor, não como gate de
release do produto inteiro.

## Ganho efetivo

As adaptações aumentaram a cobertura de confiança em quatro dimensões:

1. gates independentes e evidência vinculada (Unlazy/Skillgate);
2. contrato de conclusão separado da autoavaliação (ADL, aplicado ao nível de
   protocolo);
3. diagnóstico operacional e detecção de falha do próprio harness (Argus);
4. separação explícita de ferramentas que são realmente aplicáveis das que
   produziriam uma conclusão artificial (Horizon).
