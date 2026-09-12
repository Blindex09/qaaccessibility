# Aga Verify Agent — revisão independente

Modo: High-Risk. O trabalho altera provider, chamadas de IA, ferramentas,
permissões, limites, fallback e evidência de agentes.

## Task contract

- Required: usar os repositórios clonados aplicáveis para verificar o
  QAAccessibility com Factory e não tratar alegações de teste como prova.
- Acceptance: gates reexecutáveis, 41 casos reais consolidados, regressões,
  frontend/browser, ferramentas Factory e trajetória completa.
- Out of scope: deploy, merge, produção e recuperação da quota Ollama.
- Authority: instrução explícita do usuário nesta conversa; o estado do
  repositório é um worktree sujo preexistente, não um commit limpo.

## Evidence identity

- Repository: `C:\qaaccessibility`
- HEAD observado: `59149fb2a59e8f19c8548d2104cd8082c150912c`
- Worktree: dirty, com mudanças anteriores e desta auditoria; portanto a
  evidência é vinculada ao snapshot de trabalho, não ao commit HEAD.
- Evidence source: execução independente do verificador, XMLs e JSONs locais.
- Provider: Factory, modelo dinâmico `auto`; segredo não persistido.

## Claim vs evidence

| Claim | Evidence | Status |
|---|---|---|
| 41 casos reais passaram | `real-41-summary.json`, exatamente 41 casos, 41 pass | supported |
| ferramentas Factory realmente executaram | `tools.json`, uma execução, streaming e uso não nulo | supported |
| trajetória completa dos agentes | `trajectory.json`, `complete=true`, métricas com sucesso | supported |
| gates determinísticos passaram | Unlazy GATES.md: 5/5; Skillgate: 5/5 | supported |
| frontend/browser passaram | gate G4 passou; rodada anterior registra 200 testes e 6 Chromium | supported |
| Ollama passou | HTTP 429 por limite semanal | contradicted / not available |
| produção está certificada | nenhum deploy/ambiente produtivo foi inspecionado | cannot verify |

## Repositórios usados e adequação

- `C:\unlazy`: usado como ledger executável; 5/5 gates passaram.
- `C:\skillgate`: usado como gate determinístico; 5/5 passaram.
- `C:\aga-verify-agent`: usado como protocolo desta revisão independente;
  o relatório é a aplicação do protocolo ao snapshot atual.
- `C:\adl`: inspecionado como contrato Warden/proof; não possui um runtime
  aplicável ao QAAccessibility sem instalar hooks/manifestos específicos.
- `C:\ArgusAgent` e `C:\zaofu`: são runtimes/control planes de entrega de
  agentes, não suites de acessibilidade; executar seu fluxo alteraria a
  arquitetura de execução e não provaria o produto.
- `C:\horizon`: seus verificadores são para código/matemática gerados em
  sandbox, não para auditoria WCAG ou trajetória do backend; não foi usado como
  falso proxy de qualidade.

## Cannot verify

- Produção real, monitoramento implantado, estabilidade estatística geral e
  quota Ollama permanecem fora desta evidência. Isso bloqueia qualquer decisão
  de release, mas não bloqueia a constatação de que os 41 casos Factory
  passaram.
- Atribuição por commit não pode ser confirmada porque o worktree já estava
  sujo. O conteúdo e os comandos estão registrados, mas não há clean checkout.

## Verdict

**PARTIALLY_VERIFIED** para a tarefa ampla de auditoria multi-repositório:
os gates e casos Factory estão comprovados, mas produção/Ollama/commit limpo
não estão comprovados. Para o subconjunto “executar os 41 casos com Factory e
passar pelos gates”, a evidência é suportada.

## Next Action

- Verification verdict: PARTIALLY_VERIFIED para a auditoria ampla.
- Workflow action: PROCEED TO CODE REVIEW para as mudanças; HOLD para release.
- Code review status: required on the dirty snapshot.
- Human next action: revisar `factory_adapter.py`, `run_41.py` e os gates.
- Agent next instruction: após um commit/checkout limpo, repetir apenas os
  gates vinculados ao commit se a decisão de merge exigir proveniência por SHA.
- Do not: afirmar que Ollama ou produção foram aprovados.
