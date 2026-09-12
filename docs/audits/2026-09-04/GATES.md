# Gates: auditoria de prontidao dos agentes

OWNS: docs/audits/2026-09-04/**

Scope: medir contratos Factory, disponibilidade real e resultados sem confundir mocks com producao.

- [ ] G1: contratos Factory preservam contexto, ferramentas, schema e uso
  CHECK: .venv\Scripts\python.exe docs/audits/2026-09-04/check_contracts.py
  EXPECT: FACTORY_CONTRACTS_MET
  EVIDENCE: pending

- [x] G2: lint do backend e harness sem violacoes
  CHECK: .venv\Scripts\python.exe -m ruff check backend/src agent run_agent.py docs/audits/2026-09-04
  EXPECT: All checks passed!
  EVIDENCE: automatic-evidence=v1; definition-sha256=28dd56efac4c4e0e2b22ac47167dda5ee573032cb53aa84af9be26343444ae34; exit=0; EXPECT=matched; output-sha256=82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18; output-bytes=19; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G3: tipagem do backend aceita
  CHECK: .venv\Scripts\python.exe -m mypy backend/src
  EXPECT: Success: no issues found
  EVIDENCE: automatic-evidence=v1; definition-sha256=52d5060d3d421987a02c7ff3aa6a095f919577db36b03bd4f69da4e000116196; exit=0; EXPECT=matched; output-sha256=fe94ad20c5f6b835db571c007e464da70f754a3e93facd7c6e7d5c69b0681653; output-bytes=343; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [ ] G4: avaliacao real dos agentes aprovada
  CHECK: .venv\Scripts\python.exe docs/audits/2026-09-04/live_probe.py --verify
  EXPECT: LIVE_AGENT_GATES_MET
  EVIDENCE: pending

- [ ] G5: suite backend termina sem falhas (skips reais separados no XML)
  CHECK: .venv\Scripts\python.exe -m pytest tests/backend -o addopts= -q --tb=short --junitxml=docs/audits/2026-09-04/backend.xml
  EXPECT: passed
  EVIDENCE: pending

- [ ] G6: testes frontend terminam naturalmente sem recursos pendentes
  CHECK: npm run test:ci -- --runInBand
  EXPECT: Test Suites:
  CWD: web
  EVIDENCE: pending

- [x] G7: seis verificacoes de acessibilidade da interface passam em Chromium
  CHECK: npx --no-install playwright test accessibility.spec.ts --reporter=line
  EXPECT: 6 passed
  CWD: tests/web/e2e
  EVIDENCE: automatic-evidence=v1; definition-sha256=52b756d6edb322fe723f5545dbaedb87f91c63c51aaad54ac66970b936dc103c; exit=0; EXPECT=matched; output-sha256=e22b612c813bea0c0594a629956bd07b22da9a9298ec7f617b783d520618dc08; output-bytes=2468; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility\tests\web\e2e; path=022c3eda4836/39 entries
