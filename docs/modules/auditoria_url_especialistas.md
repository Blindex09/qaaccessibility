# Módulo 2: auditoria de página por URL e seleção de especialistas

Atualizado em 08/10/2026. Provedor Ollama Cloud, modelo Alto, roteador inteligente ligado. Testado pelo
navegador, pela interface de chat, com a página de exemplo do W3C (Before and After Demonstration).
Código principal: `backend/src/agents/orchestrator/orchestrator.py`, `a11y_expert_reviewer.py`,
`backend/src/services/chat_tools.py` (ferramenta de análise de página), `route_advisor.py`,
`execution_scope.py` e `run_agent.py`.

## O que este módulo entrega

1. A pessoa cola uma URL e pede uma auditoria. O chat busca e renderiza a página, escolhe os especialistas que
   o pedido realmente precisa, roda esses especialistas em ondas, passa o resultado por um revisor sênior que
   remove falsos positivos e devolve uma resposta em texto corrido.
2. A escolha dos especialistas é da IA, pelo significado do pedido e da página. O código só confere que os
   nomes existem. Um pedido amplo convocou 6 a 8 especialistas. Um pedido estreito ("só idioma e texto
   alternativo") convocou 2.
3. O progresso aparece conforme cada especialista termina, com o achado preliminar marcado como sujeito à
   revisão. Nada é apresentado como concluído antes da revisão.
4. Cada achado sai com um nível de evidência. O revisor marca como alta confiança o que o próprio código da
   página prova, e como média ou baixa o que depende de algo que o código não mostra (tamanho real na tela,
   contraste visual, se uma imagem com alt vazio é decorativa, padrões que costumam ser válidos). A resposta
   final separa o confirmado do que precisa ser verificado e não fecha com veredito geral da página.
5. Falha honesta e barata. Para uma URL que não existe, o assistente explica que o endereço não foi
   encontrado, sugere conferir a URL ou enviar o HTML, e não inventa resultado. Levou 29 segundos.

## Números medidos ao vivo

Página com erros (W3C Before, home), mesmo tipo de pedido:
- Antes das correções: 594.163 tokens em 43 chamadas e cerca de 28 minutos de trabalho ativo, mais 12 minutos
  esperando uma aprovação. O revisor sênior gastou 254.095 tokens em 11 lotes, o roteador 74.154 em 17 chamadas
  e cada especialista de 7 mil a 30 mil.
- Depois: 191.223 tokens em 22 chamadas e 80 segundos. Redução de cerca de 68 por cento nos tokens e de mais de
  95 por cento no tempo. O revisor gastou 44.294 em 2 lotes, o roteador 40.544 em 9 chamadas, o chat 28.033.

Página acessível (W3C After, home):
- Primeira rodada: 175.681 tokens em 21 chamadas, 71 segundos, 13 achados.
- Rodada depois da calibração de evidência: 173.931 tokens em 21 chamadas, 74 segundos, 10 achados, 3 falsos
  positivos removidos pelo revisor.

Repetições finais na página com erros, depois de todas as correções (o roteador escolheu modelos diferentes a
cada vez, e isso muda a qualidade da resposta final):
- 211.063 tokens em 23 chamadas, 259 segundos, 7 especialistas. Sem emoji, mas a resposta final do modelo escolhido
  veio com tabelas quebradas, o mesmo achado em três severidades e a frase falsa de que tudo foi verificado na
  árvore de acessibilidade. Isso levou ao reforço do prompt descrito no problema 9.
- Depois do reforço: 151.771 tokens em 16 chamadas, 206 segundos, 4 especialistas. Sem tabela, sem emoji, achados
  separados por gravidade, cada um com a evidência (alta ou média) e a afirmação de que foi verificado no código da
  página, que é o que de fato aconteceu.

Pedido estreito (idioma e texto alternativo, página com erros): 106.058 tokens em 14 chamadas, 53 segundos,
2 especialistas (percepção e semântica). A resposta ficou dentro do que foi perguntado.

URL inexistente: resposta final honesta em 29 segundos. O custo desse cenário não foi registrado, porque o
registro do servidor foi reiniciado em seguida.

Do que é feita a chamada mais pesada: o revisor sênior, porque reenvia o HTML capturado inteiro (cerca de 8 mil
tokens) em cada lote, mais o raciocínio escondido. Antes eram lotes de 6 achados (11 lotes, 166 mil tokens só de
entrada). Agora são lotes de 15.

## Problemas encontrados e corrigidos neste módulo

1. O roteador era consultado uma vez por especialista, cerca de 3,7 mil tokens cada. Os especialistas de uma
   auditoria agora formam uma família de rota: o primeiro decide e os outros reaproveitam. O revisor e os papéis
   da squad também.
2. O roteador comparava modelos quase a cada etapa, e a auditoria passava de 40 minutos. Ele agora recebe o custo
   de comparar e fatos observados de execuções anteriores.
3. O revisor processava lotes de 6 achados por causa de um teto de saída que já não existe, reenviando o HTML
   11 vezes. O lote passou a 15.
4. O cartão de aprovação chamava de "altera algo e não dá para desfazer" uma ferramenta que só lê. O cartão agora
   descreve cada ferramenta pelo que ela faz de verdade.
5. O assistente inventou um caminho de disco que a pessoa nunca informou (a pasta temporária do computador) e pediu
   para lê-lo, em vez de analisar a URL. Agora um caminho local só é lido ou corrigido se estiver escrito na
   conversa, e a checagem acontece antes do cartão de aprovação, para a pessoa não ser chamada a aprovar algo que
   seria negado. É uma checagem de fato (o texto está ou não está na conversa), não de intenção.
6. Um erro de ferramenta (endereço que não existe) aparecia como "o modelo solicitado não foi encontrado, selecione
   o modo Alto". O formatador de erros de provedor de IA, que decide por palavra-chave, estava sendo aplicado a erros
   de ferramenta. Agora um erro de ferramenta mostra uma frase neutra e quem explica a causa é o próprio modelo.
7. O prompt do chat dizia que emojis eram opcionais, contra a regra 3. Mudou para proibido. Como um modelo ainda
   usou emojis mesmo assim, o texto em fluxo e o texto final removem pictogramas por faixa de Unicode (fato
   objetivo, não julgamento), porque o leitor de tela os lê em voz alta como ruído.
8. A página acessível recebia 13 achados, vários discutíveis, e uma conclusão geral categórica. O revisor passou a
   marcar o nível de evidência de cada achado, o resumo do chat leva essa marcação e o prompt do chat manda separar
   o confirmado do a verificar, sem veredito geral.

9. Com outro modelo narrando a resposta final, apareceram tabelas que a interface não renderiza, HTML cru, o mesmo
   achado repetido em três severidades e a afirmação de uma verificação que ninguém fez. O prompt do chat agora
   proíbe tabelas, HTML cru fora de bloco de código e repetição de achado, e só deixa afirmar uma checagem que o
   resultado da ferramenta relata. O comportamento tem que valer para qualquer modelo do roteamento.

## Testes e verificação

- Testes novos: caminho local escrito pela pessoa (2), erro de ferramenta não confundido com erro de provedor,
  emojis proibidos no prompt e removidos do fluxo e do texto final, nível de evidência no resumo e nos prompts,
  família de rota dos especialistas, lote do revisor, cartões de ferramenta no web.
- Suíte completa do backend: 1.852 passados e 41 pulados. Suíte do web: 260 passados. Ruff e mypy sem erros.
  Depois da última mudança de prompt rodei de novo os testes do chat, com ruff e mypy do arquivo.
- Ao vivo pelo navegador: quatro cenários (página com erros, página acessível, pedido estreito, URL inexistente),
  mais uma repetição depois de cada correção que mudou comportamento.

## O que ainda não está provado ou ainda pode piorar

- Precisão em página acessível. Conferido contra o HTML real: o link do logotipo sem href e o elemento obsoleto
  acronym existem de fato. Mas um link da página atual sem href é um padrão válido e continua sendo apontado com
  severidade alta. O nível de evidência ajuda a pessoa a pesar, mas a severidade ainda pode exagerar.
- Recall. Na página com erros, tabelas usadas para layout não foram apontadas, e um achado incoerente sobre o link
  de pular conteúdo foi mantido pelo revisor na primeira medição. Não foi reavaliado depois das correções.
- Contraste e leitor de tela real não são medidos neste caminho. Os especialistas visuais estimam contraste pela
  imagem e a resposta marca isso como requer validação visual. A verificação com leitor de tela de verdade é de
  outro módulo.
- O roteador escolheu modelos diferentes em cada rodada (gemma4:31b, gpt-oss:120b e outros), e a qualidade da
  resposta final varia com o modelo. O prompt reforçado melhorou isso, mas foi provado em uma rodada só.
- O chat gasta cerca de 27 mil tokens de entrada em uma auditoria, só com instruções e resultados das ferramentas.
- O cache de respostas por prompt idêntico distorce a medição de um segundo pedido igual. As medições usaram
  textos diferentes.
- A análise de sites com várias páginas ainda gasta muito e não pede aprovação. Fica para o módulo de
  rastreamento.


## Provedores

<!-- PROTECOES:PROVEDORES:INICIO -->
Este módulo vale para todos os provedores (todas as regras do CLAUDE.md valem para todos). Estado de cada um, gerado de
`provedores/evidencias.json` por `scripts/update_protections.py` (não editar a mão):

- Ollama Cloud (Alto): PROVADO em 08/10/2026. página com erros do W3C de 594 mil tokens e 28 minutos para cerca de 150 a 210 mil e 80 a 260 segundos. Ficha: `provedores/ollama-cloud.md`.
- Gemini (Alto): PROVADO em 09/10/2026. pela tela: auditoria da página com erros do W3C em 137 s e 127.556 tokens, 18 chamadas, achados corretos sem emoji nem tabela. Pelo script mais 3 cenários (pedido estreito, página acessível, URL inexistente). Pendências: a contagem de achados da resposta não bateu com a lista (disse 8 e listou 7) e a abertura 'Olha,' é casual para uma pergunta neutra. Ficha: `provedores/gemini.md`.
- OpenAI: NÃO TESTADO.
- Anthropic: NÃO TESTADO.
- xAI (Grok): NÃO TESTADO.
- Factory AI: NÃO TESTADO.
- OpenCode Go: NÃO TESTADO.

O roteiro para testar um provedor novo, sem retrabalho, está em `provedores/_roteiro_para_novo_provedor.md`.
<!-- PROTECOES:PROVEDORES:FIM -->
