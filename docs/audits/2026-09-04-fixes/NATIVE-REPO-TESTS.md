# Evidência nativa dos repositórios clonados

Esta evidência é separada da análise WCAG do QAAccessibility. Um teste verde
prova somente o comportamento coberto por aquele comando; não prova prontidão
integral, comportamento correto de agentes ou funcionamento em produção.

## Resultados observados

| Projeto | Comando | Resultado | Evidência principal |
|---|---|---|---|
| Unlazy | `npm test` | Passou nos blocos executados | Os blocos terminaram com 34/34, 51/51, 24/24, 29/29, 8/8 e self-check 15/15 |
| Skillgate | `npm test` | Falhou | Falhas em Git plumbing, comando, Trivy e vários testes E2E; o build TypeScript passou antes da suíte |
| ArgusAgent | `python -m pytest -q` | Não coletou | Mesmo após instalação editável no `.venv`, colisão de módulos `test_build_release.py` entre `tests/release_tools` e `tests/scripts` |
| Horizon | `python -m pytest -q` | Falhou | 7 falhas e 18 aprovados; equivalência, dual execution, stdin/call mode e repair loop |
| ZaoFu | `python -m pytest -q` | Não coletou | Após instalação editável no `.venv`, 666 erros de coleta por `ModuleNotFoundError: fcntl`; 5 testes foram deselecionados |

## Interpretação

- Unlazy tem uma suíte forte para seus contratos locais, mas ainda precisa de
  avaliação comportamental do agente e de cenários reais para sustentar uma
  afirmação de prontidão.
- Skillgate não deve ser tratado como aprovado: a suíte oficial atual falha,
  mesmo que uma checagem isolada de gates tenha passado anteriormente.
- ArgusAgent e ZaoFu não chegaram à execução funcional completa porque o
  ambiente não conseguiu sequer coletar os testes. Isso é uma falha de
  reprodutibilidade/integração, não um sucesso neutro.
- Horizon possui falhas funcionais concretas em ambiente Windows, inclusive
  dependência de `resource`, que não existe no Python padrão para Windows.

## Próxima camada

Esses resultados serão cruzados com avaliações independentes do QAAccessibility:
componentes, agentes, trajetórias, ferramentas, E2E, adversarial, acessibilidade
e runtime. O veredito final só será positivo quando houver evidência suficiente
nas duas dimensões: execução do software e comportamento do agente.
