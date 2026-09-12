# Gates: QAAccessibility com Factory e validação dos agentes

OWNS: backend/**, tests/backend/**, docs/audits/2026-09-04-fixes/**, docs/real_llm_testing.md, pytest.ini

Scope: verificar o estado atual do QAAccessibility com testes baratos, evidência Factory real e controles de prontidão agêntica

- [x] G1: regressões e contratos passam
  CHECK: .venv\Scripts\python.exe -m pytest tests/backend/unit/services/test_factory_adapter.py tests/backend/unit/test_real_eval_configuration.py docs/audits/2026-09-04/test_factory_contracts.py docs/audits/2026-09-04/test_partial_warning_contract.py -o addopts= -q
  EXPECT: 24 passed
  CWD: ../../..
  EVIDENCE: automatic-evidence=v1; definition-sha256=f4ca9e5aad64a92bbd4dfc73597de2e2edf9605624ac692f99aa3b08bdb90687; exit=0; EXPECT=matched; output-sha256=5540af701d2c0e68f2ed9a234f767b655cb502528c2ce8c3e10feae7291dc20f; output-bytes=101; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G2: type-check e lint do escopo agêntico passam
  CHECK: powershell -NoProfile -Command "& { .venv\Scripts\python.exe -m ruff check backend/src run_agent.py tests/backend/real_llm tests/backend/unit/test_real_eval_configuration.py docs/audits/2026-09-04-fixes; .venv\Scripts\python.exe -m mypy backend/src run_agent.py tests/backend/real_llm/conftest.py tests/backend/unit/test_real_eval_configuration.py }"
  EXPECT: Success: no issues found
  CWD: ../../..
  EVIDENCE: automatic-evidence=v1; definition-sha256=10de756e97b13fa50606a5f2c4d38cd8eb11d4b6067a8b51bc179f9de2b57e03; exit=0; EXPECT=matched; output-sha256=e0ea225fd89114ed96ca5618c9aad99cdb1094b574abe4bf1159588b85e027d3; output-bytes=362; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G3: os 41 casos reais distintos passam com Factory
  CHECK: .venv\Scripts\python.exe docs/audits/2026-09-04-fixes/summarize_41.py
  EXPECT: "passed": 41
  CWD: ../../..
  EVIDENCE: automatic-evidence=v1; definition-sha256=569f992af69b8c2887f81a0c65c0edba41b549e96584d239736aa61d948c52c2; exit=0; EXPECT=matched; output-sha256=d17e689491dc39946a3f5fc2b944b6f9b37b9f547043c4f8b9258e1661f8dcb0; output-bytes=121; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G4: frontend e browser passam
  CHECK: powershell -NoProfile -Command "Set-Location web; npm test -- --runInBand; npm run typecheck"
  EXPECT: Test Suites: 18 passed
  CWD: ../../..
  EVIDENCE: automatic-evidence=v1; definition-sha256=40c9c3b16874a7389b4883dacc5bf8a8edcbdf91c067e40a9608b455c3a28337; exit=0; EXPECT=matched; output-sha256=d832b93f2cd16021925682c4b51fb72d15fa844aa64c00a749a0483560b6e806; output-bytes=53976; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries

- [x] G5: evidence gate confirma ferramenta real, streaming e trajetória completa
  CHECK: .venv\Scripts\python.exe docs/audits/2026-09-04-fixes/verify_evidence.py
  EXPECT: FACTORY_LIVE_SAMPLE_MET
  CWD: ../../..
  EVIDENCE: automatic-evidence=v1; definition-sha256=95e9c4d0b0f6ebf93c880ab0085f2753ed3ede227a7d0fb17674de0e83429163; exit=0; EXPECT=matched; output-sha256=fa1fa0d6f001bc2739e0ea097d1d5bcbaf961f42a7c2620d27ca54193e31e9c8; output-bytes=25; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\qaaccessibility; path=022c3eda4836/39 entries
