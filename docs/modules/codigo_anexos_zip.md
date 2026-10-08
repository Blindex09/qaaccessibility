# Módulo 3: código, arquivos anexados, projeto compactado e projeto local

Atualizado em 08/10/2026. Provedor Ollama Cloud, modelo Alto, roteador inteligente ligado. Testado pelo
navegador, pela interface de chat, com um projeto de teste de uma loja (duas páginas, CSS e JavaScript) que tem
defeitos conhecidos, para comparar a resposta com a verdade.
Código principal: `backend/src/services/chat_runtime.py` (anexos), `backend/src/services/chat_tools.py`
(descompactar, ler projeto local, resumo dos achados), `backend/src/services/local_project_guard.py` e
`web/src/screens/ChatScreen.tsx` (exibição da resposta).

## O que este módulo entrega

1. Arquivo de código anexado. A pessoa anexa um arquivo (HTML, componente React, CSS) e pergunta se há problema.
   O conteúdo chega ao modelo como texto e a análise parte do código, não de uma página renderizada.
2. Projeto compactado em ZIP. O sistema extrai o ZIP anexado sozinho e entrega ao modelo o texto de cada arquivo
   com o seu nome. Antes o modelo recebia só uma sequência em base64 e tinha de copiá-la inteira para uma
   ferramenta de descompactar. Se algo não foi lido (tipo de arquivo não lido ou limite de tamanho), a extração
   diz o que ficou de fora, para o modelo nunca tratar um projeto parcial como completo.
3. Projeto local por caminho. A pessoa escreve o caminho de uma pasta do computador. O sistema confere que o
   caminho foi escrito por ela na conversa, mostra um cartão de aprovação com o caminho e só então lê os
   arquivos. Para corrigir, o mesmo vale, com backup antes.
4. Achados por arquivo, separando o que o código prova do que falta verificar, dentro do escopo pedido (um pedido
   só sobre teclado recebeu só o que afeta teclado, com um aviso honesto sobre o que ficou fora).
5. Código na resposta em bloco próprio, com botão que copia de verdade e anuncia que o código foi copiado.

## Números medidos ao vivo

Projeto de teste em ZIP (4 arquivos), quatro rodadas pelo navegador:
- Primeira: 315.331 tokens, 24 chamadas, 348 segundos. Faltou na resposta final o texto alternativo do logotipo, e
  a descompactação falhou ao mostrar um erro ao usuário.
- Segunda: 406.199 tokens, 33 chamadas, 1.043 segundos. Resposta completa e organizada por arquivo, mas duas
  auditorias (uma por página), o revisor em 5 chamadas e o especialista mais sobreposto.
- Terceira (depois de extrair o ZIP no sistema, resumo com todos os achados, lote do revisor sem sobra e
  orientação de custo): 297.721 tokens, 21 chamadas, 671 segundos. Uma só auditoria, 7 especialistas, revisor em
  2 chamadas, todos os defeitos conhecidos na resposta.
- Quarta (com o aviso de espera e a proteção contra chamada presa): 159.500 tokens, 20 chamadas, 818 segundos,
  6 especialistas, revisor em 2 chamadas, sem o erro de descompactação. É o menor custo das quatro rodadas. A
  resposta final não saiu porque a conta do provedor atingiu o limite semanal de uso (o sistema explicou isso com
  a mensagem de ação e guardou a análise); os achados chegaram à tela como achados preliminares.
- Uma rodada intermediária (a quinta tentativa) travou: o especialista de robustez ficou 29,7 minutos numa só
  chamada, sem erro e sem fim, até a pessoa cancelar. O cancelamento funcionou na hora e entregou o parcial (28
  achados, marcados como sem revisão). Veja o problema 11.
- O custo por especialista medido foi de 7 a 35 mil tokens conforme o modelo que o roteador escolheu, e o
  tempo varia muito com esse modelo (de 348 a 1.043 segundos para o mesmo projeto).

Projeto local por caminho: 218.634 tokens e 22 chamadas, cerca de 220 segundos de trabalho ativo mais a espera
pela aprovação. Pedido só sobre teclado: o revisor removeu 11 e 11 achados fora do escopo, ficaram 5.

Arquivo de código anexado (componente React com uma div clicável e uma imagem sem texto alternativo): 214.960
tokens, 17 chamadas, 313 segundos. Os dois defeitos foram achados, mais o foco, e a correção sugerida foi boa.
Desses tokens, 69.831 foram de uma pesquisa na web automática (veja as pendências).

Defeitos conhecidos do projeto de teste e o que a resposta final trouxe: idioma ausente, página sem título, imagem
sem texto alternativo, pulo de nível de título, campo sem rótulo, botão feito de div, link com texto genérico,
tabela sem cabeçalhos, foco removido pelo CSS e contraste baixo. Todos apareceram na terceira rodada do ZIP.

## Problemas encontrados e corrigidos neste módulo

1. O ZIP anexado chegava como base64 e o modelo tinha de copiá-lo para a ferramenta. Falhava com "File is not a
   zip file" e, num projeto real, a cópia nem caberia. Agora o sistema extrai (fato objetivo, como já fazia com PDF
   e Word) e a descrição da ferramenta manda não usá-la para anexo do chat. O formato de leitura também deixou de
   engolir o final do base64.
2. A leitura do ZIP ignorava em silêncio arquivos de tipo não lido e cortava no limite de 30 arquivos ou 100 mil
   caracteres sem avisar. Agora devolve avisos do que ficou de fora e a extração os repassa ao modelo.
3. O chat só via os 10 primeiros achados de cada análise. Com 16 achados, um defeito alto (imagem sem texto
   alternativo) sumiu da resposta. O resumo agora traz todos, com um aviso se passar de 80.
4. O revisor sênior gastava uma chamada inteira (reenviando o documento) para sobra de 1 achado. A sobra pequena
   entra no lote anterior.
5. O assistente escolhia especialistas sobrepostos e fazia uma auditoria por arquivo. A descrição da ferramenta
   agora traz o custo medido, a sobreposição observada e a orientação de enviar o projeto numa chamada só, com o
   nome de cada arquivo marcado.
6. Um guarda decidia por palavra-chave no nome da pasta se um projeto local podia ser lido. A pasta lojasol_local foi
   recusada e o assistente pediu para renomear a pasta, contra as regras 2 e 5. Por decisão do dono do projeto em
   08/10/2026: para ler e corrigir arquivos locais vale o caminho escrito pela pessoa mais a aprovação no cartão.
   A regra do nome da pasta continua só para executar comandos locais (Cypress, Selenium), que são mais arriscados.
7. A tela apagava todo sublinhado do texto, e a pasta lojasol_local aparecia como lojasollocal na mensagem da
   pessoa e nas respostas. Agora só se remove o sublinhado de ênfase, e o que está no meio de uma palavra fica.
8. A tela não tinha bloco de código nem botão de copiar: o código saía em linhas soltas e a limpeza apagava as
   crases do próprio código (um template literal ficava quebrado). Agora o código vai em bloco próprio, com
   botão Copiar código, que copia de verdade, tem reserva para navegadores que negam a área de transferência e
   anuncia código copiado. Provado ao vivo com clique real.
9. Na terceira rodada o modelo ainda chamou a ferramenta de descompactar sem precisar e o erro apareceu ao usuário. A
   descrição da ferramenta agora manda não usá-la para anexo do chat. Na rodada seguinte o erro não apareceu, mas
   foi uma rodada só.
10. Quando um especialista demora, a tela só dizia "Processando". Agora o orquestrador avisa a cada 20 segundos
    quem ainda falta, e a tela mostra uma única linha ("Ainda aguardando Estrutura e Tags ARIA há 40s") que se
    atualiza no lugar e some quando chega o próximo evento (regra 4). O aviso só informa: não encerra nada.
11. Uma chamada ao provedor ficou 29,7 minutos presa, sem erro e sem fim, e só o cancelamento a encerrou. Duas coisas
    seguravam o turno: o orçamento tratava qualquer chamada em andamento como progresso, e o limite de leitura do
    HTTP não a encerrou. Investigação da causa:
    - A chamada nunca registrou custo, então nunca terminou. A mesma análise isolada (mesmo modelo, mesmo projeto,
      mesmo caminho do produto) terminou em 31 segundos, então o defeito é intermitente. O registro da rodada presa
      foi sobrescrito quando reiniciei o servidor, e o limite semanal de uso da conta impediu repetir a medição.
    - Hipótese mais forte, pelo código: a saída do especialista é restrita por esquema JSON, e esse tipo de geração
      pode degenerar em espaços e quebras de linha sem fim. Os dados continuam chegando, então não é silêncio, e a
      chamada nunca termina e nunca registra custo. Esta hipótese NÃO está provada.
    Defesas feitas (todas com teste): (a) uma chamada em andamento só conta como progresso enquanto chega dado dentro
    da janela de paciência (cobre a chamada muda); (b) um fluxo degenerado, mil pedaços seguidos vazios, só de espaço
    ou repetidos, é encerrado como falha de provedor e o orquestrador segue com o parcial, sem refazer a mesma
    geração por outro endpoint (cobre a hipótese); (c) uma chamada longa deixa no log, a cada 2 minutos, quantos
    pedaços recebeu, quantos caracteres e o final do texto, para que a causa de uma nova ocorrência fique provada em
    vez de adivinhada. A regra de buscar a causa raiz entrou no CLAUDE.md (regra 17) por causa deste caso.

## Testes e verificação

- Testes novos: extração do ZIP anexado, aviso de extração parcial, ZIP corrompido sem derrubar o turno, resumo
  com todos os achados, sobra do revisor, orientação de custo, caminho local escrito pela pessoa e regra nova do
  guarda, sublinhado no meio de palavra, bloco de código e cerca ainda aberta.
- Suíte completa no fim do módulo: backend 1.872 passados e 41 pulados, web 266 passados, ruff, mypy e tsc sem erros.
- Ao vivo pelo navegador: ZIP em quatro rodadas, projeto local com aprovação, arquivo de código anexado.

## O que ainda não está provado ou ainda pode piorar

- O limite semanal de uso da conta do Ollama Cloud foi atingido durante os testes deste módulo e continuava
  atingido na verificação seguinte (uma chamada mínima recebeu o erro 429). Novas rodadas ao vivo ficam bloqueadas
  até o limite renovar ou entrar crédito, o que é decisão da pessoa. As três defesas contra chamada presa (silêncio,
  fluxo degenerado e diagnóstico no log) e o aviso de espera estão cobertos por testes, mas nenhum foi visto ao
  vivo, e a causa da chamada presa continua sendo hipótese (problema 11).
- A pesquisa automática do pipeline (etapa de verificação de lacuna) roda sem cartão de aprovação quando um
  especialista marca um achado como baixa confiança, e custou 69.831 tokens no componente React. É do módulo de
  pesquisa (14): decidir se continua automática, se pede aprovação ou se o revisor basta.
- Os botões de copiar e editar nas mensagens da pessoa (regra 4) não existem na interface. Fica para o módulo de
  interface (15).
- Projeto grande. Os limites de 30 arquivos e 100 mil caracteres do ZIP continuam. Agora são avisados, mas um
  projeto real maior fica parcial. Não foi testado com um projeto de centenas de arquivos.
- O roteador não escolheu nenhum grupo de ferramentas para o pedido do projeto local, e o modelo teve de habilitar
  o grupo de análise depois (uma rodada a mais). A escolha é do roteador e não foi alterada.
- O custo e o tempo variam com o modelo escolhido pelo roteador: o mesmo projeto custou de 297 mil a 406 mil
  tokens e levou de 348 a 1.043 segundos.
- A resposta final de um modelo trouxe uma palavra estranha (e-mailikinetic) numa rodada. É erro do modelo e não
  há como o sistema consertar.
- Apagar ou alterar arquivos do projeto local pela correção não foi testado neste módulo (é do módulo 5).
