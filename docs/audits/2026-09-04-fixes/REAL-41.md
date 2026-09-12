# Revalidação dos 41 testes opt-in

**Resultado: 41/41 casos distintos aprovados com Factory**, após as reexecuções.
Rodada principal: 40 passaram e um foi ignorado pelo antigo comportamento de
drift (18min37s). Reexecução final: quatro passaram (8min53s), incluindo esse
caso e as três verificações reforçadas. O resultado combinado tem zero falhas,
erros ou skips; os XMLs individuais permanecem intactos para auditoria.

## Causa dos skips e correções

Os 41 não eram 41 defeitos conhecidos do produto: a suíte exigia opt-in e
credencial Ollama. O preflight autenticado desta rodada retornou HTTP 429,
explicitamente por limite semanal. Não se alterou quota, assinatura ou conta.

Foi adicionado suporte explícito a Factory na configuração dos mesmos testes,
com chave em memória, cache desligado, failover automático desligado e
restauração da configuração ao terminar. O padrão sem opt-in continua ignorando
os testes pagos, deliberadamente: não transformar todo CI em consumo de API.

Correções no harness:

- Escolha e isolamento de provider, modelo e chave; regressões unitárias.
- O controle de endpoint inacessível continua usando HTTP real em loopback,
  com chave fictícia. Não tenta aplicar URL HTTP ao SDK CLI do Factory.
- Os evals de traces usam o provider configurado, não uma indicação fixa Ollama.
- O teste de mudança de modelo registra baseline, modelo atual e drift em JUnit;
  não se ignora mais quando o modelo muda. O baseline não foi regenerado.
- Trajetória, upload E2E e pipeline de acessibilidade exigem `complete=true`
  e sucesso de todos os especialistas, não somente sucesso do transporte.
  Uma regressão unitária confirma rejeição de resultado parcial.

## Como interpretar as evidências

`real-41.xml` é a rodada completa. Quatro testes ajustados durante a execução
foram reexecutados com o código final em `real-41-3344a087.xml`; esse arquivo
inclui o antigo skip de drift e as exigências reforçadas de completude.
`summarize_41.py` combina os resultados por identidade de teste, exige exatamente
41 casos distintos e reprova qualquer falha, erro ou skip restante. Não soma
reexecuções como se fossem testes adicionais. Saída: `real-41-summary.json`.

Os três controles de falha/no-op também passaram separadamente em
`real-41-ad53b8ea.xml`. Essa suíte contém controles sem chamada paga, além de
agentes reais: seus 41 casos não significam 41 chamadas independentes ao modelo.

A suíte comum foi reexecutada: **1.582 passaram, 41 ignorados por opt-in**, sem
falhas (`backend-after41.xml`). Ruff passou; mypy aprovou 187 arquivos no escopo
verificado. O conjunto focal de configuração e adapter teve 16 aprovações.

## Limites

Factory usa seleção dinâmica `auto`. Os resultados não certificam Ollama,
cuja quota continua bloqueada, nem produção inteira. O teste estatístico usa
cinco tentativas e o limiar já existente de 60%; passar esse teste não demonstra
100% de confiabilidade. Os controles de replay e drift não são chamadas reais.

Comando desta rodada: `.venv\Scripts\python.exe docs/audits/2026-09-04-fixes/run_41.py`.
Para uso geral, consultar `docs/real_llm_testing.md`; o runner de auditoria lê o
arquivo local autorizado, sem incluir suas chaves nos artefatos persistidos.
