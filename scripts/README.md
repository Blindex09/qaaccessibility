# `scripts/` — utilitários operacionais

Nada aqui faz parte do gate de CI. `pytest.ini` define
`testpaths = tests/backend`, então o pytest **não coleta** este diretório.

## Convenção de nomes

| Prefixo | O que é | Precisa de quê |
|---|---|---|
| `run_*.py` | Execução manual ao vivo (E2E real, provider pago, UI no browser) | Backend rodando e/ou chave real de provider |
| `generate_*.py` | Geração de artefato versionado (`agent_knowledge.md`, `REPO_MAP.json`, entregáveis) | Só o repo |
| `inspect_*.py` | Inspeção de saída já gerada | Artefato já produzido |
| `ci_a11y_check.py` | Portão de acessibilidade para pipelines externos | Backend rodando |

**Não** nomeie nada aqui como `test_*.py`. Esse prefixo é o padrão de coleta do
pytest (`python_files = test_*.py`): um arquivo assim neste diretório aparenta
ser parte da suíte, mas nunca roda — foi exatamente esse drift que fez
asserções reais de acessibilidade viverem fora do gate por vários commits
(hoje em `tests/backend/unit/services/test_chat_tools_link_sanitizer.py`).

A mesma convenção `run_*.py` já é usada em
`tests/backend/real_llm/live_runs/`, para execuções ao vivo que também não
entram na coleta.

## Credenciais

Nenhum script embute chave. Os que falam com provider real leem
`OLLAMA_CLOUD_API_KEY` / `OLLAMA_API_KEY` do ambiente e abortam com mensagem
clara se estiverem ausentes.

```bash
export OLLAMA_CLOUD_API_KEY=...
python scripts/run_full_accessibility_pipeline_e2e.py
```

## `ci_a11y_check.py` — portão de acessibilidade externo

Aponta para uma instância do backend e falha o build se houver achado
`critical` ou `high`. Consome `POST /analyze/url`, que responde
`AgentResult{success, data.issues, error}`.

```bash
A11Y_API_URL=http://localhost:8001 A11Y_TARGET_URL=https://exemplo.com python scripts/ci_a11y_check.py
```

Não está ligado ao CI deste repositório: ele precisa de um backend de pé e de
um provider LLM real, o que o gate de PR não tem. Serve para o pipeline de
quem **usa** o produto. O gate de acessibilidade do próprio app está em
`.github/workflows/ci.yml`, job `web`.
