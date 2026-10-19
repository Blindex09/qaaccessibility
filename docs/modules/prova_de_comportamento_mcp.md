# Módulo: prova de comportamento com o servidor MCP de acessibilidade

Criado em 19/10/2026. Código: `backend/src/services/chat_tools.py` (`verify_page_behavior`), `tool_groups.py` (grupo `comportamento`), regra 23 do `SYSTEM_PROMPT` em `chat_runtime.py` e, do outro lado, a ferramenta `a11y_check_page` do projeto mcp do dono.

## Por que existe

O Qaaccessibility analisa o código: especialistas com IA leem o HTML, o axe confere regras e a árvore de acessibilidade do navegador confirma nomes. Isso diz o que um componente DECLARA. Não diz o que ele FAZ quando alguém usa: se o foco entra no diálogo e volta, se a aba responde às setas, se o erro é anunciado, se a mensagem que surge sem recarregar chega a quem não vê a tela. O auditor de interação que já existia (`verify_screen_reader_announcements` com passos) roda passos que o próprio modelo escreve, no máximo 30, em um navegador novo a cada chamada.

O servidor MCP do dono (`mcp`) mede esse comportamento: sondas de contrato do padrão APG (diálogo, acordeão, menu, abas, combobox, lista, árvore, dica), de erro de formulário, de mensagem de status e de troca de tela, mais a varredura de Tab. Este módulo liga as duas coisas sem copiar conhecimento de um lado para o outro (o Qaaccessibility já tem o conhecimento, com mais rigor): o Qaaccessibility decide QUANDO provar e o MCP mede.

## Como a decisão de usar o MCP é tomada (regras 2 e 9)

Nenhum código decide por palavra. A cadeia é:

1. O roteador (um modelo, na mesma consulta em que escolhe o modelo do turno) recebe o catálogo de grupos de ferramentas e escolhe os que o pedido precisa, pelo significado. O grupo novo se chama `comportamento` e a descrição dele, escrita para o roteador, diz quando serve (a resposta depende do que acontece em execução e ler o código não decide: a pessoa quer saber se funciona de verdade, quer confirmar que uma correção resolveu, ou a análise deixou dúvida de comportamento) e quando não serve (marcação, contraste, textos alternativos, documentos, requisitos, perguntas conceituais). Conversa e pergunta conceitual recebem lista vazia, como já era.
2. Quem não foi escolhido de início continua ao alcance: o agente chama `enable_tool_group` se descobrir, com a análise na mão, que precisa provar. A concessão de segurança não muda.
3. Com a ferramenta oferecida, o modelo do chat segue a regra 23 do prompt: provar em vez de adivinhar quando o comportamento decide, dizer com clareza o que foi provado e o que só parece arriscado no código, rodar uma vez sem sondas para ver os elementos e sondar só o que importa, não afirmar nada se o servidor não está registrado, e tratar `null` como não medido.
4. A ferramenta exige aprovação (abre um navegador real e aperta teclas na página), como `verify_screen_reader_announcements`.

O harness só confere fatos: se o servidor está registrado, se as entradas têm o formato certo, e devolve o resultado como dado de terceiro, marcado, nunca instrução.

## O que foi entregue e qual teste cobre cada promessa

Em `tests/backend/unit/services/test_verify_page_behavior.py`:

- A ferramenta exige aprovação e fica num grupo só dela; o roteador só a oferece quando escolhe o grupo (não vem junto de `analise`, não vem para pergunta conceitual): `TestCatalogo`.
- A descrição do grupo e a da ferramenta dizem quando usar, quando não usar e o que não é provado; a regra 23 manda decidir pelo significado: `TestCatalogo`.
- O roteador recebe o grupo novo no catálogo e só pode responder com grupos dele (teste que já existia, `test_router_receives_the_catalog_and_must_answer_with_groups_from_it`, cobre o grupo novo porque a lista vem do catálogo).
- Entradas inválidas viram mensagem, não falha: `TestEntradas`.
- Sem o servidor registrado, diz o que fazer e que o comportamento NÃO foi provado: `TestEntradas::test_sem_o_servidor_registrado_...`.
- Repassa os argumentos e devolve o resultado como dado marcado; erros do servidor e de conexão viram mensagem sem detalhe interno: `TestChamadaAoServidor`.
- Com o servidor de verdade por stdio, uma chamada por processo: a primeira traz Tab, resumo e a lista de elementos com seletor; a segunda roda a sonda de diálogo (8 verificações cumpridas) com o seletor da primeira, em outro processo: `TestComServidorReal` (pulado se o projeto mcp não está na máquina; o caminho é `A11Y_MCP_SERVER_PATH`).

Avaliação da DECISÃO do roteador, ao vivo e opt-in: `tests/backend/real_llm/test_12_roteamento_do_comportamento_real.py`, com 8 pedidos que precisam da prova e 9 que não precisam, cada um repetido (3 vezes por padrão) para medir uma taxa. Limites iniciais: escolher o grupo em pelo menos 75 por cento das tentativas quando precisa, e em no máximo 15 por cento quando não precisa.

## Uma descoberta que moldou o desenho

O cliente MCP do Qaaccessibility sobe o servidor de novo a CADA chamada de ferramenta (`mcp_client._open` abre um processo, inicializa, chama e fecha). As ferramentas de sessão do MCP (`a11y_open`, `a11y_dossier`, `a11y_act`) perderiam o navegador entre uma chamada e outra. Por isso o MCP ganhou `a11y_check_page`, de chamada única (abre uma sessão descartável, mede, roda as sondas pedidas e fecha). Fluxos com estado entre passos continuam fora do alcance deste módulo.

## Como ligar

Registrar o servidor com o nome `accessibility` (a pessoa aprova, o servidor é revisado sem credencial antes): `mcp_register_server` com o Python e o `mcp_server.py` do projeto mcp. Sem isso a ferramenta responde `not_registered` e explica.

## O que NÃO está provado

- Nenhuma rodada ao vivo com modelo: as taxas de escolha do grupo pelo roteador não foram medidas. O teste `test_12` está escrito, passa na análise estática e fica pulado sem chave. Até a primeira medição, a boa decisão do roteador é uma expectativa, não um fato.
- A regra 23 do `SYSTEM_PROMPT` e a descrição do grupo são mudança de instrução ao modelo (regra 15). Registro: data 19/10/2026; motivo: dar ao chat o critério de quando provar comportamento; para qual modelo: texto sem ramo por modelo; testes que rodaram: os do módulo, os de grupos de ferramentas e os de numeração do prompt; portão (conjunto amplo ao vivo em tentativas repetidas, ablação e observação): NÃO cumprido, sem chave de provedor e sem crédito. Se a taxa de escolha errada ou os custos piorarem ao voltar a rodar ao vivo, desfazer: tirar a regra 23, o grupo `comportamento` e a ferramenta.
- Nenhum provedor foi testado com esta ferramenta (todos NÃO TESTADO).
- O resultado do MCP chega inteiro ao contexto do modelo. Com muitos elementos pode ser grande; não foi medido o custo em tokens.
- Leitor de tela real, dispositivo real e fluxos com estado entre passos continuam não verificados, e a ferramenta diz isso no resultado.
- O especialista de formulários, o de widgets e o revisor NÃO usam a prova de comportamento nos seus achados: hoje quem decide provar é o chat. Usar a prova para confirmar ou refutar achados do pipeline é um passo seguinte.
