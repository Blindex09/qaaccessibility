# Correções após E2E real da squad

## Implementação

- Contexto por execução: pedido, histórico e progresso público chegam ao transporte
  de todos os especialistas, incluindo entradas multimodais. Não há classificação de
  intenção por regex, palavras-chave ou filtro fixo de critérios.
- A ponte de ferramentas síncronas para corrotinas preserva ContextVars. Redirecionamentos
  atualizam o pedido consumido pelas próximas chamadas.
- HTML original da captura chega ao revisor, inclusive em cada lote. A interpretação
  do escopo e a exclusão de achados sem evidência são decisões do modelo.
- Papéis da squad recebem a mesma calibração normativa de especialistas/revisor/chat.
  QA anterior à inspeção deve entregar um plano concreto, não apenas aguardar resultados.
- Omitir um achado não o transforma automaticamente em falso positivo aprendido.
- Roteador não publica seu JSON/progresso interno. Eventos de quadro atualizam estado,
  sem títulos genéricos no feed. Atualizações públicas continuam navegáveis por setas.
- A duração é vinculada à mensagem da resposta. Um novo turno não altera o anterior;
  histórico sem duração conhecida mostra “Processamento concluído”.

## Verificação barata

- Ruff nos Python alterados: passou.
- Mypy em 12 fontes alteradas, configuração do backend: passou.
- 240 testes backend relevantes/regressões: passaram.
- 51 testes frontend em quatro suítes: passaram.
- TypeScript e ESLint dos arquivos frontend alterados: passaram.
- Regressões incluem isolamento concorrente de contexto, ponte assíncrona, conteúdo
  multimodal, encaminhamento do documento a todos os lotes, ausência de aprendizado
  indevido por omissão, calibração dos papéis e duração preservada entre turnos.

## E2E real: primeira tentativa não aprovada

Conversa `01152949-e76a-4a08-8dd7-ea6e26d838fc`, Chrome, UI em localhost:19006,
Ollama Cloud/Alto salvo, sem modelo fixado no pedido. Inspeção de example.com restrita
a idioma e títulos, somente leitura. Duração exibida: 60s.

A separação do escopo eliminou o achado anterior sobre links, mas QA ainda esperou
os resultados e o revisor manteve uma falha baseada apenas na ausência de títulos.
A resposta final a chamou de violação. Esta tentativa NÃO aprovou a precisão normativa.
Foram reforçados os contratos de contribuição de QA e de evidência de 1.3.1;
nenhum filtro determinístico de descrições ou de intenção foi adicionado.

## E2E real: repetição após correções

Conversa `b5eb9b73-222a-42bd-aa4c-7f3781225e96`, mesmo pedido/alvo/provedor e modo.
Primeiro turno: 70s exibidos. QA entregou plano de aceitação em vez de apenas aguardar.
O especialista ainda propôs um achado de títulos, identificado como preliminar no feed,
mas o revisor o descartou: resultado final do pipeline zero achados, 3/3 agentes OK.
A resposta separou o fato de zero headings da recomendação, sem afirmar que h1 é
obrigatório. Não houve achado de links fora do escopo ou mensagem interna de roteamento.

Limitação: a redação “Conforme” para idioma e “não há violação crítica” para títulos
é menos cautelosa que “nenhuma violação confirmada neste escopo”; esta amostra não
comprova conformidade integral, precisão em todos os sites ou ausência de repetição
semântica em qualquer execução. Não demonstra redução de latência: 70s foi maior
que os 54s do E2E anterior. Os papéis ainda podem produzir resumos genéricos; o
contrato foi ajustado para exigir a decisão concreta e não repetir a própria atualização.

Logs: `logs/backend-squad-correcoes-2026-09-30.stdout.log`, `.v2.stdout.log` e
`.v3.stdout.log`.

## Revisão no segundo turno e navegação

Na mesma conversa, a revisão levou 32s e mobilizou Product Owner e QA Lead via
`consult_squad`. Nenhuma nova inspeção foi executada; as decisões usaram o resultado
armazenado. Na interface, o primeiro turno continuou em 70s durante/depois do segundo.
ArrowUp mudou o foco entre contribuições reais da squad, com ancestral aria-live
ausente. Não foi realizado teste auditivo com NVDA real.

A revisão ainda traduziu o status da tarefa como “Conforme com ressalvas”, excessivo
para comprovação parcial. Foi acrescentada uma orientação normativa compartilhada:
veredito de conclusão da tarefa não é certificação da página; comunicar “nenhuma
violação confirmada no escopo avaliado” e evitar “não é uma violação crítica” para
um achado sem sustentação. Backend recarregado com esse contrato; logs em
`logs/backend-squad-correcoes-2026-09-30.v4.stdout.log`.

## Terceiro turno: calibração de certeza reprovada

O pedido de encerramento/revisão de certeza levou 30s, reutilizando a evidência
armazenada com Product Owner e QA Lead; nenhum novo pipeline de inspeção foi executado.
Apesar da orientação compartilhada, os papéis e o narrador ainda afirmaram certeza
total/100% e traduziram o veredito como “Conforme com ressalvas”. Portanto esta parte
do comportamento NÃO está aprovada. Não confundir testes de contrato passando com
garantia de precisão semântica do modelo. É necessária investigação adicional do
efeito de histórico/handoffs e avaliação de qualidade das respostas dos modelos.

O roteador permaneceu `source=ia`, mas convergiu para gemma4:31b, sem comparação
entre modelos; este E2E não comprova julgamento cruzado nem cobertura dos demais
provedores. Backend carregado e saudável ao término, processo de servidor 17604.
As durações dos três turnos permaneceram independentes: 70s, 32s e 30s.

Screenshot: `artifacts/qaa-squad-correcoes-e2e-2026-09-30.png`.
