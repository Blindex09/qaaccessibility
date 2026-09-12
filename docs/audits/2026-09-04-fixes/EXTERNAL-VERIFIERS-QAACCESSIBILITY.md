# Verificação externa do QAAccessibility

Alvo: `C:\qaaccessibility`  
Objetivo: verificar se o produto funciona de fato, sem confundir testes verdes
com excelência de software ou comportamento de agentes.

## Resultados já executados

| Verificador | Escopo | Resultado | Interpretação |
|---|---|---|---|
| Skillgate | auditoria read-only do repositório | **REPROVADO** | `instruction-sync`, ausência de TODOs proibidos e ausência de segredos passaram; o gate `tests-pass` falhou ao executar `npm test --silent` |
| Unlazy | descoberta de pipelines/gates no alvo | **NÃO AVALIADO** | não encontrou pipelines em `.unlazy/`, nem ledger reconhecível; não pode concluir aprovação |
| ArgusAgent | diagnóstico de bootstrap/ambiente | **BOOTSTRAP PASSOU** | Python, import do Argus, Git, Node, PowerShell e assets foram encontrados; isso não é avaliação de qualidade do QAAccessibility |
| Aga Verify Agent | vínculo entre alegação, snapshot e evidência | **PARCIAL** | pode verificar evidências e claims, mas não é uma suíte de execução autônoma do produto |

## Reexecução com o alvo configurado

- `skillgate drift --cwd C:\qaaccessibility`: passou; `CLAUDE.md` está sincronizado
  com `AGENTS.md`. Também revelou que não existem instruções equivalentes para
  Cursor, Copilot, Gemini CLI, Cline, Windsurf e Junie.
- `skillgate gate` sem uma especificação não executa o comando: retorna
  `no skillgate spec — nothing to enforce`. Portanto, um comando permitido por
  esse modo não é evidência de que o QAAccessibility passou.
- O `package.json` raiz do QAAccessibility possui somente o script `prepare`; não
  possui `test`. Assim, o gate default do Skillgate (`npm test --silent`) está
  mal alinhado com o projeto e falha por contrato de execução inexistente.
- Os testes Python reais precisam ser declarados em uma especificação explícita
  do Skillgate para que o verificador externo consiga bloquear/permitir com base
  neles, em vez de assumir o ecossistema Node.

## Especificação externa explícita

Foi criado `external-readiness.yaml` com backend, Ruff, mypy, frontend e
typecheck. O resultado independente foi:

- backend: passou;
- Ruff: passou;
- mypy: passou;
- frontend typecheck: passou;
- frontend Jest: **falhou no processo**, apesar de `18` suites e `200` testes
  reportados como `passed`.

O erro pós-suíte incluiu `Cannot log after tests are done` e atualizações React
fora de `act(...)`, além de warnings de APIs deprecated do React Native Web.
Isso é precisamente uma falsa sensação de aprovação: a contagem interna de
casos está verde, mas o processo externo termina com exit code 1.

## Evals reais do próprio QAAccessibility

A suíte opt-in foi executada novamente com Factory, sem cache e sem fallback,
selecionando trajetória, adversarial, online evaluation, observabilidade e
replay. Resultado: **17/17 avaliações reais passaram**:

- 5 avaliações de trajetória;
- 3 avaliações adversariais;
- 3 avaliações de scoring online/trace;
- 5 avaliações de observabilidade em runtime;
- 1 replay de trajetória sem nova chamada ao LLM.

Esse resultado confirma que os agentes e o runtime têm evidências reais de
comportamento correto nesses cenários. Ele não elimina a falha do processo de
testes frontend: prontidão exige a combinação de comportamento real saudável e
execução limpa das suítes.

## Revalidação após correção

Os testes frontend que deixavam renderers montados foram corrigidos para
desmontar os componentes e drenar a microtask pendente. A especificação externa
foi corrigida para executar os comandos dentro de `web`.

O gate consolidado passou completamente:

- backend: passou;
- Ruff: passou;
- mypy: passou;
- frontend Jest: passou com exit code 0;
- frontend typecheck: passou.

Ainda há warnings de `act(...)` em alguns testes de hook e warnings de APIs
deprecated do React Native Web. Eles permanecem evidência técnica registrada,
mas não deixam mais a execução vermelha.

## Unlazy como gate independente

Foi criado um `GATES.md` operacional para o alvo e executado pelo Unlazy com
aprovação das definições exatas. Resultado: **5/5 gates met**.

- G1 backend unit/integration: passou;
- G2 Ruff + mypy: passou;
- G3 frontend + typecheck: passou;
- G4 evals reais de trajetória, adversarial, online, observabilidade e replay:
  passou;
- G5 especificação externa do Skillgate: passou.

O Unlazy vinculou cada resultado ao comando, diretório, shell e hash da saída,
reduzindo o risco de uma aprovação baseada em transcript stale ou em execução
de outro snapshot.

## ArgusAgent em modo de plano

O `argus repair --plan` foi executado sem aplicar reparos. O diagnóstico
confirmou runtime Codex/CLI e assets, mas encontrou pendências do próprio
ambiente Argus (house rules ausentes, Electron sem binário e path memory
ausente). Essas pendências pertencem ao verificador Argus, não ao
QAAccessibility, e mostram que uma auditoria operacional precisa separar
defeitos do alvo de defeitos do harness.

## Escopo removido

O checkout `C:\zaofu` foi removido do conjunto ativo e movido de forma
reversível para `C:\zaofu.removed`, conforme solicitado. Seus resultados já
estão preservados nos relatórios anteriores; não será usado nos gates futuros.

## Significado do primeiro resultado

O QAAccessibility tinha uma suíte que aparentava estar verde em partes, mas o
Skillgate, executado externamente contra o repositório, encontrou uma falha no
comando de teste configurado para o gate. Isso já demonstra por que o projeto
precisa de verificadores independentes: o resultado depende do comando, do
ambiente e do contrato usado para declarar “passou”.

O resultado do Unlazy também é importante: ausência de um pipeline reconhecido
não equivale a aprovação. Significa que o alvo não ofereceu ao verificador um
contrato operacional que ele pudesse executar.

## O que ainda será executado

- Skillgate em modo de verificação de patch e drift de instruções;
- cenários de execução real do QAAccessibility com Factory;
- avaliações de trajetória, ferramentas, falhas, recuperação e observabilidade;
- validação dos contratos de agentes e das respostas contra casos adversariais;
- replay independente das evidências com Aga Verify Agent;
- ADL/Warden quando houver um contrato `.claude` aplicável, sem inventar um
  contrato que o QAAccessibility não declarou;
- comparação dos resultados externos com `pytest`, `ruff`, `mypy`, frontend,
  E2E e os 41 casos reais já executados.

## Regra de conclusão

O QAAccessibility só será considerado excelente se os verificadores externos
confirmarem comportamento real, não apenas compilação, testes unitários,
retornos com schema válido ou contagens de agentes concluídos.
