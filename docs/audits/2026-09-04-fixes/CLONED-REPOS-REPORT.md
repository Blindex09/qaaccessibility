# Auditoria QAAccessibility dos repositórios clonados

Data: 2026-09-05  
Provider: Factory (`auto`)  
Endpoint: `POST /analyze/project/zip`

## Resultado executivo

Esta execução verificou os sete repositórios clonados usando o analisador de projeto do QAAccessibility. O resultado não é uma certificação de qualidade geral do software: ele mede a superfície web enviada ao analisador e a execução dos agentes de acessibilidade. Testes funcionais, segurança, comportamento dos agentes do projeto e prontidão de produção continuam sendo dimensões separadas.

| Projeto | Arquivos web enviados | Resultado | Achados | Observação |
|---|---:|---|---:|---|
| unlazy | 0 | Não aplicável | — | Nenhum arquivo web compatível encontrado |
| skillgate | 25 | Passou no endpoint | 0 | Resultado retornado do cache; não é uma análise fresca nesta execução |
| ArgusAgent | 80 | Reprovado | 60 | 21/21 agentes concluídos; 69 candidatos, 9 falsos positivos removidos |
| horizon | 0 | Não aplicável | — | Nenhum arquivo web compatível encontrado |
| zaofu | 80 | Incompleto / reprovado | 11 | 19/20 agentes concluídos; `gap_research` falhou por erro de loop assíncrono |
| adl | 0 | Não aplicável | — | Nenhum arquivo web compatível encontrado |
| aga-verify-agent | 0 | Não aplicável | — | Nenhum arquivo web compatível encontrado |

## Leitura correta

- `ArgusAgent` não passou: o revisor especialista manteve 60 problemas, incluindo semântica, contraste, foco, títulos, labels, status e teclado.
- `ZaoFu` não deve ser tratado como aprovado: há 11 problemas e a execução ficou parcial. O log registrou `asyncio.run() cannot be called from a running event loop` no caminho de pesquisa de lacunas.
- `Skillgate` retornou zero achados, mas o endpoint informou resultado de cache. Portanto, é apenas um resultado de análise previamente armazenado, não evidência suficiente de uma nova auditoria completa.
- `unlazy`, `horizon`, `adl` e `aga-verify-agent` não tinham arquivos com extensões web suportadas pelo endpoint. Isso significa “fora do escopo desta análise”, não “software aprovado”.

## Limitações observadas

1. O endpoint limitou o contexto quando recebeu 80 arquivos. O próprio log registrou truncamento de arquivos; a cobertura deve ser considerada parcial para os projetos grandes.
2. A auditoria é de acessibilidade de código web. Ela não substitui testes unitários, integração, E2E, validação de sistema, avaliações de agentes, segurança, performance ou observabilidade em produção.
3. Para uma segunda rodada mais rigorosa, é necessário desabilitar o cache e enviar um subconjunto priorizado por entrada web, componentes interativos e CSS, ou analisar os arquivos em lotes menores.

## Evidências

- Dados brutos: `cloned-repos-results.json`
- Executor: `audit_cloned_repos.py`
- Auditoria do próprio QAAccessibility: `REPORT.md`, `REAL-41.md` e `AGA-VERIFY-REPORT.md`
