# Gates: partial analysis reaches the chat agent

OWNS: docs/audits/2026-09-04/test_partial_warning_contract.py

Scope: acceptance probe for the orchestrator to chat-tool boundary.

- [ ] P1: chat tool preserves the orchestrator partial-analysis warning
  CHECK: .venv\Scripts\python.exe -m pytest docs/audits/2026-09-04/test_partial_warning_contract.py -o addopts= -q
  EXPECT: 1 passed
  EVIDENCE: pending
