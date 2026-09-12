# Gates: QAAccessibility independent verification

OWNS: backend/**, web/**, run_agent.py, tests/**, docs/audits/**

Scope: independent finish-line verification of backend, frontend and real agent behavior

- [x] G1: backend unit and integration suite passes
  CHECK: .venv\Scripts\python.exe -m pytest tests/backend -q
  EXPECT: /passed/
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=1a2efe961e22898192d2acd2cd62fd305e1ceeac33ea598a9dbbdddfb1de7633; exit=0; EXPECT=matched; output-sha256=16b0ed1bdae49d6b96fcba57cea259435eab0e420c576f90b99e105b09779619; output-bytes=35644; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G2: backend lint and typecheck pass
  CHECK: .venv\Scripts\ruff.exe check backend tests/backend && .venv\Scripts\python.exe -m mypy backend/src
  EXPECT: /Success: no issues found/
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=89e4e851833bcabe361dbb4f78cc4624bf8b1758edc04e31f3b2f77e11552322; exit=0; EXPECT=matched; output-sha256=4f2c20270ccd054d46f474db4b1c32024809ab4738c757aad74a50653490568c; output-bytes=362; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G3: frontend tests and typecheck pass
  CHECK: cd web && npm test -- --runInBand && npm run typecheck
  EXPECT: /Tests:.*passed/
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=1d2cdd217bced7a0b9994cd15338aea85aa8600f6c3f9538dcf6265e4e8883c4; exit=0; EXPECT=matched; output-sha256=0e34cbf69e65dbaba0614b246d1c266c35c739d2e1b5b5f20e28902b4c615a5a; output-bytes=47109; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G4: real trajectory, adversarial, online, observability and replay evals pass
  CHECK: .venv\Scripts\python.exe docs\audits\2026-09-04-fixes\run_41.py -k "trajectory or adversarial or online_eval or production_observability or trace_replay"
  EXPECT: /REAL_SUITE_EXIT=0/
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=a337cdbf933ed454d4aff691368b3e81dc9dab68de13fa0e7fe6db71189c8908; exit=0; EXPECT=matched; output-sha256=d9e47c3eb07ec1a30a32948d3077619d993e34be61647f88c88df6cb209e3fa5; output-bytes=2060; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G5: external readiness specification passes through Skillgate
  CHECK: node C:\skillgate\dist\src\cli.js check docs\audits\2026-09-04-fixes\external-readiness.yaml --json
  EXPECT: /"passed": true/
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=c2cb1e4cc5b6468e650a43f2ed5dc6dcc2d638049e4ee78f5310c805f69e65d6; exit=0; EXPECT=matched; output-sha256=12e4f3f682d8740fcae27e48d0b50af9c6931225de64a0acf02c742c06adbad5; output-bytes=851; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries
