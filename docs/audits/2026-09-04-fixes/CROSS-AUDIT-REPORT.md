# Cruzamento de prontidão: testes nativos × QAAccessibility

## Regra do veredito

Um projeto só pode ser considerado pronto quando possui evidência suficiente
em todas as dimensões relevantes. Uma suíte verde não neutraliza falha de
coleta, incompatibilidade de plataforma, falha de integração, achados de
acessibilidade ou comportamento de agente não verificado.

## Matriz consolidada

| Projeto | Testes nativos | Execução/ambiente | Auditoria QAAccessibility | Veredito atual |
|---|---|---|---|---|
| Unlazy | Passou nos blocos da suíte local | Fluxos reais do agente ainda não comprovados | Sem superfície web compatível; nenhuma conclusão de prontidão | **Não verificado** |
| Skillgate | Falhou em Git, comandos, Trivy e E2E | Integração do CLI não confiável nesta máquina | 0 achados web, mas resultado de cache | **Reprovado** |
| ArgusAgent | Não coleta a suíte completa | Colisão de módulos impede a execução | 60 achados; 21/21 agentes de acessibilidade OK | **Reprovado** |
| Horizon | 7/25 falharam | Execução de código e repair loop incompatíveis no Windows | Sem superfície web compatível | **Reprovado** |
| ZaoFu | 666 erros de coleta após instalação | Dependência POSIX `fcntl` impede execução no Windows | 11 achados; 19/20 agentes OK; análise incompleta | **Reprovado/incompleto** |
| ADL | Sem suíte executada nesta rodada | Ferramenta orientada a Claude Code/arquivos de contrato | Sem superfície web compatível | **Não verificado** |
| Aga Verify Agent | Skill/documentação, não aplicação executável | Requer contexto de tarefa e evidência de um agente | Sem superfície web compatível | **Não verificado** |

## O que esta auditoria prova

- Há projetos com resultados locais aparentemente positivos que não têm
  evidência suficiente de comportamento de agente ou prontidão.
- Há projetos que não chegam sequer à execução da suíte por problemas de
  coleta ou portabilidade; isso é uma falha operacional relevante.
- No ArgusAgent, a análise de acessibilidade encontrou 60 problemas mesmo
  com a etapa de agentes do QAAccessibility concluindo sem erro.
- No ZaoFu, a análise produziu achados, mas o próprio pipeline reportou uma
  falha de agente; portanto, o resultado não pode ser tratado como completo.

## O que ainda não é possível afirmar

Esta rodada ainda não certifica segurança, qualidade geral do produto,
comportamento autônomo em tarefas abertas ou produção. Para isso, cada projeto
precisa de cenários comportamentais específicos: tarefa, estado inicial,
ferramentas permitidas, resultado esperado, invariantes, falhas injetadas e
critério de parada. O QAAccessibility deve avaliar esse pacote, não apenas o
arquivo fonte.

## Próximo gate

Executar cenários reais por projeto, capturando trajetória, chamadas de
ferramenta, efeitos no filesystem, recuperação, timeouts e estado final; em
seguida aplicar avaliação adversarial e revisão de evidência independente.
