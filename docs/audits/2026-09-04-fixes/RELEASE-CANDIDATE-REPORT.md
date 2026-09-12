# QAAccessibility — Release Candidate Verification

Data: 2026-09-05  
Provider real: Factory (`auto`), sem cache e sem fallback

## Veredito

**RELEASE CANDIDATE — fortemente verificado, com warnings não bloqueantes
documentados.**

O produto não foi declarado perfeito ou provado para todos os cenários
possíveis. O veredito significa que os principais claims operacionais têm
evidência independente, reproduzível e ligada ao código executado.

## Evidências finais

- Unlazy: 5/5 gates externos passaram.
- Skillgate: especificação externa completa passou.
- Backend: suíte completa passou.
- Ruff: passou.
- mypy: passou.
- Frontend: 18 suites e 200 testes passaram com exit code 0.
- Frontend typecheck: passou.
- Frontend lint: passou.
- Browser E2E: 12/12 passaram, incluindo axe-core na interface do QAAccessibility
  e auditoria real/manual de uma página externa.
- Evals reais: 41/41 passaram.
- Trajetória, adversarial, E2E, acessibilidade, regressão, online scoring,
  observabilidade, planejamento e replay passaram com Factory.

## Warnings restantes

- React Native Web ainda emite warning para `shadow*` e `pointerEvents`.
- Alguns testes de hook emitem warning de atualização fora de `act(...)`, embora
  a suíte aguarde e termine com exit code 0.
- Esses warnings não foram suprimidos nem tratados como aprovação silenciosa;
  permanecem dívida técnica para a próxima iteração.

## Limites do veredito

- Não é uma prova matemática de ausência de bugs.
- Não substitui operação prolongada em produção com usuários reais.
- A quota do Ollama Cloud continua separada; os resultados reais usados aqui
  foram Factory.
- A auditoria externa comprova os cenários definidos, não qualquer tarefa
  arbitrária futura.

## Artefatos relacionados

- `EXTERNAL-VERIFIERS-QAACCESSIBILITY.md`
- `NATIVE-REPO-TESTS.md`
- `GATES.md`
- `real-41-summary.json`
- `external-readiness.yaml`

## Cobertura adicional

O E2E de navegador foi executado com Chromium real. Os testes do próprio
QAAccessibility passaram sem violações axe-core. A auditoria da página externa
também completou, reportando achados reais do site auditado (contraste, links,
labels e hierarquia de headings), demonstrando que o pipeline não retorna
sucesso vazio.
