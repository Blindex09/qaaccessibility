# Módulo 1: conversa, triagem e roteamento Alto

Atualizado em 07/10/2026. Provedor Ollama Cloud, modelo Alto, roteador inteligente ligado.
Código principal: `backend/src/services/chat_runtime.py`, `route_advisor.py`, `tool_groups.py`,
`llm_client.py`, `execution_scope.py` e `backend/src/agents/clarifier/clarifier.py`.

## O que este módulo entrega

1. Triagem. Antes de qualquer trabalho, o clarificador lê o pedido e decide pelo significado: se é uma
   pergunta de acessibilidade, uma análise, uma correção, um pedido fora do foco ou um pedido vago demais.
   Pedido fora do foco e pedido vago terminam ali, com uma resposta escrita pelo próprio modelo, em uma
   única chamada barata.
2. Roteamento Alto. Em cada etapa o roteador de rotas recebe a lista de modelos elegíveis e decide, pelo
   significado da etapa, qual modelo usar, quanto ele deve pensar e quais grupos de ferramentas o pedido
   precisa. O código só valida: candidatos existentes, credenciais e contrato do JSON.
3. Ferramentas por pedido. O chat tem 33 ferramentas, em seis grupos (análise, correção, documentos, testes,
   pesquisa, integrações) mais três sempre presentes (perguntar à pessoa, consultar a squad e habilitar outro
   grupo). O roteador escolhe os grupos pelo significado do pedido. Se o agente descobrir que precisa de
   outro grupo, chama `enable_tool_group` e ele entra na próxima chamada, sem sair no meio da tarefa. A
   concessão de segurança não muda: continua sendo definida ao nascer e o agente só amplia o que já tem.
4. Squad contextual. A IA escolhe quais papéis da squad convocar, em que ordem e quando. Cada papel agora
   sabe quanto custa (de 6 a 10 mil tokens), então pesa o ganho antes de chamar.
5. Registro de custo. Cada pedido grava no log uma linha `[Custo]` com tokens de entrada e saída por tipo de
   chamada e por modelo. Sem isso nenhuma afirmação de economia era verificável.

## Números medidos ao vivo

Pergunta conceitual curta (Em duas frases, o que é o critério 1.4.3):
- Antes: 37.704 tokens em 6 chamadas. O roteador gastou 15.119 (40 por cento) e o chat 16.725, porque
  mandava as 33 ferramentas, cerca de 11.900 tokens de schema, em toda chamada.
- Depois: 25.335 tokens na primeira vez (cache frio) e entre 17.590 e 18.533 nas seguintes, em 4 chamadas.
  O roteador caiu para 21 por cento do total e o chat para 9.100 a 9.800 tokens de entrada, porque o roteador
  escolheu nenhum grupo e foram oferecidas 3 de 33 ferramentas. Redução de cerca de 53 por cento.

Pedido fora do foco (receita de bolo): 1 chamada, cerca de 2.000 tokens quando é a primeira mensagem.
Pedido vago ("analisa isso"): 1 chamada, cerca de 2.000 tokens, devolve uma pergunta específica.

Revisão focada de um campo de formulário:
- Antes: de 54 mil a 135 mil tokens. O revisor sênior gastou 23 mil, 26 mil e 45 mil tokens de saída para
  devolver cerca de 900, quase tudo raciocínio escondido.
- Depois: o revisor gastou entre 6.600 e 12.200 tokens no total.
- Pelo navegador, revisão de um botão de menu: 31.772 tokens em 114 segundos, 3 consultas ao roteador,
  1 papel da squad, nenhuma ferramenta oferecida, resposta correta e precisa (quatro falhas WCAG com
  correção). Antes da orientação de custo o clarificador convocava 2 papéis para o mesmo tipo de pedido.

Seleção de especialistas. Nas revisões focadas o orquestrador escolheu de 1 a 3 especialistas entre 29
(formulários; formulários e móvel; semântica, formulários e cognitivo), nunca todos. Em uma análise ampla de
página estática foram 8. A decisão é do modelo: o código não escolhe especialista por palavra-chave.

Medição do raciocínio no modelo deepseek-v4.1-flash, mesma revisão curta de 2 achados:
sem pensar 169 tokens em 1,5 segundo; nível baixo 6.372 tokens em 31 segundos; médio 1.593 tokens; alto 916.
O consumo não cresce com o nível. Só "não pensar" é previsível, por isso complexidade baixa do roteador agora
significa nenhum raciocínio extra.

## Problemas encontrados e corrigidos neste módulo

1. O roteador era consultado 3 vezes por pergunta simples, cada uma com 5 mil tokens. A entrada agora é
   compacta: começo e fim do texto mais o tamanho total, fatos dos modelos sem repetição (provedor e nome já
   estão no id) e pedido de só os 5 melhores candidatos, porque o restante da ordem o código completa pela
   confiabilidade observada.
2. O cache das decisões do roteador para etapas internas nunca acertava, porque a chave incluía a telemetria
   viva dos modelos, que muda a cada chamada. A chave agora usa quais modelos existem. O reranqueamento da base
   de conhecimento passou a ser etapa barata, e os papéis da squad compartilham uma família de rota.
3. O chat mandava todas as ferramentas sempre. Agora o roteador escolhe os grupos, com validação de que os
   nomes existem no catálogo, um teste que obriga classificar toda ferramenta nova e uma ferramenta para
   habilitar um grupo sob demanda.
4. A resposta de recusa para pedido fora do foco era um texto fixo no código, contra a regra 3. Agora é o
   clarificador, o próprio modelo, quem escreve.
5. O sub-agente da pesquisa profunda recebia as 33 ferramentas do chat. Agora recebe só as de busca (menor
   privilégio) e a ferramenta pede aprovação, porque gastou 570 mil tokens em um único pedido para revisar um
   campo de CPF. A descrição dela avisa o custo e o roteador também.
6. O revisor sênior pensava de 22 mil a 45 mil tokens. Complexidade baixa agora é "não pensar", e o roteador
   foi informado de que o raciocínio é o maior custo escondido.
7. Uma conexão do Ollama Cloud respondeu 200 e ficou muda por mais de 10 minutos, travando o turno. O timeout
   de leitura dos clientes passou a ser a janela de silêncio do turno, que se adapta à complexidade: uma
   geração que continua enviando dados nunca é cortada, uma conexão sem nenhum byte é.

## Testes e verificação

- Testes novos: `test_tool_groups.py` (23), `test_squad_route_family.py` (2), mais casos novos em
  `test_route_advisor.py`, `test_chat.py`, `test_token_budget.py` e `test_rule8_limits.py`.
- Suíte completa do backend: 1.834 passados e 41 pulados. Ruff e mypy sem erros.
- Ao vivo, pelo navegador e pela rota de streaming que o navegador usa, com Ollama Cloud em modo Alto.

## O que ainda não está provado ou ainda pode piorar

- A pesquisa profunda com aprovação e com as 3 ferramentas de busca foi coberta por testes, mas não foi
  repetida ao vivo depois da correção.
- O nível médio de raciocínio ainda pode gastar dezenas de milhares de tokens em uma chamada. O único freio
  contra isso é o limite de tokens que a pessoa pode escolher nas Configurações; por padrão ele não existe.
- O chat ainda custa cerca de 9 mil tokens de entrada só de instruções e conhecimento, e o histórico é
  reenviado a cada rodada de ferramentas. Não verifiquei se o Ollama Cloud reaproveita esse prefixo.
- O cache de respostas por prompt idêntico faz um segundo pedido igual parecer mais barato do que é.
- A análise de sites com muitas páginas (`analyze_site`) também gasta muito e não pede aprovação. Fica para o
  módulo de rastreamento.

## Decisão que depende da pessoa dona do projeto

Pedido inofensivo fora do foco, como receita de bolo, hoje é recusado com educação pelo modelo. A regra 5 diz
que nunca se rejeita pedido inofensivo. O produto se apresenta como especialista em acessibilidade. É preciso
decidir qual das duas vale.
