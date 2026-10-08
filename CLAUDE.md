Qaaccessibility — instruções operacionais para agentes

Este arquivo é lido automaticamente no início de qualquer sessão de agente
neste repositório. Não é material de estudo — são regras de processo, e todas são
obrigatórias.

## Regras mestras (obrigatórias, valem para tudo)

TODAS as regras deste arquivo são obrigatórias, sem exceção: nenhuma é sugestão, preferência ou ponto de partida
negociável, e isso inclui a parte específica de cada projeto no fim. Nenhuma é opcional nem pode ser dispensada por
conveniência, por tamanho da tarefa ou para fazer um teste passar. Se duas regras parecerem conflitar, não se escolhe
uma em silêncio: aplica-se a que protege mais e avisa-se a pessoa.

Regras obrigatórias para todo o sistema: todos os modelos e provedores, ferramentas, capacidades e
funcionalidades, e todas as interfaces. Foram ditas pelo dono do projeto ao longo de todo o trabalho e
consolidadas aqui. Nenhuma mudança está pronta se contrariar qualquer uma delas. Esta seção, a regra geral de
conclusão e a regra permanente de agente = modelo + harness são idênticas nos dois projetos (Agentic e
Qaaccessibility): o comportamento de IA é o mesmo. Ao alterar uma delas num projeto, alterar no outro na mesma
entrega. Só a parte final, específica de cada projeto, pode diferir.

Princípio central: a inteligência artificial compreende, decide, cria e se adapta; o código determinístico protege,
limita, valida e mede. Autonomia máxima da IA sem sacrificar segurança, transparência, acessibilidade e verificação.

### 1. Agente = modelo + harness

- O modelo decide o conteúdo: o significado do pedido, se há ambiguidade relevante, como decompor, qual estratégia
  seguir, o que examinar, como corrigir, quando revisar a própria abordagem e como explicar o progresso.
- O harness (o código em volta) decide só o que é permitido: identidade e escopo de credencial, ferramentas negadas por
  padrão, sandbox, validação de caminho e de comando, cancelamento, validação de schema e contrato, integridade de
  arquivo, aprovação para ações irreversíveis, registro de eventos e recuperação de falhas.
- Esses papéis nunca se invertem. A IA decide o conteúdo; o roteamento e a proteção são do código.

### 2. IA semântica, sem determinismo nem heurística para julgamento

- Nada de regex, palavra-chave, lista de sinônimos ou árvore fixa de condições para decidir intenção, se algo está
  claro, qual ferramenta usar, se uma resposta está completa ou se uma interface está boa. Isso é da IA, pelo
  significado.
- Determinismo só para fato objetivo e verificável (uma URL presente no texto, um tamanho, um schema, o código de saída
  de um processo, um processo que é da própria plataforma) e para segurança, permissões, isolamento, sintaxe e
  integridade.
- Nenhum determinismo exagerado que impeça a IA de trabalhar. Quanto menos, melhor, desde que não tire proteção.
- Um teste que obriga o código a adivinhar intenção por palavra-chave pede o tipo errado de determinismo e não é
  aceito.

### 3. Conversa corrida, humana, em tempo real

- Nunca engolir tudo e entregar só no final. Informar cada passo, em linguagem natural, como as IAs de ponta.
- Texto corrido e humanizado, nunca narração robótica. Sem saudação fixa e sem mensagem pronta; o que aparece vem do
  próprio modelo.
- Tudo chega token a token (streaming).
- Nunca mostrar protocolo, JSON bruto, nome técnico de ferramenta, stack trace ou código de controle. Nunca "cuspir"
  código: comando e código aparecem em bloco próprio, com botão de copiar.
- Sem asteriscos, marcação crua ou caracteres especiais soltos na resposta, em qualquer modelo.
- Não repetir o que já foi dito: se o agente anunciou o que vai fazer, não anuncia de novo.
- O usuário pode interromper, corrigir, complementar ou redirecionar uma execução sem perder o que já foi feito.
- Tudo no idioma do usuário (aqui, português).
- Acompanha o jeito de falar da pessoa: formal com quem é formal, descontraído com quem é descontraído, curto e
  objetivo com quem é direto. Enquanto o jeito dela não estiver claro, fica neutro e respeitoso, sem gíria, piada
  ou intimidade presumida, e se adapta assim que perceber como ela fala. Vale para toda resposta, inclusive
  quando recusa um pedido. Não existe tom fixo no código nem nos prompts.

### 4. Interface e leitor de tela

- Ações em andamento aparecem no presente e viram passado ao terminar, na mesma linha: "pensando" vira "pensou por
  Xs", "executando" vira "executou", "lendo" vira "leu", "navegando em site" vira "navegou em N sites". Nunca repetir
  "executou" ou "pensou" duas vezes: vale só a última.
- Essas mensagens curtas ficam no meio da conversa, como o modelo falando, sem cabeçalho H2 e sem URL bruta (só o nome
  do site).
- O pensamento do modelo vai para uma área recolhida, com o texto do próprio modelo em linguagem natural.
- A resposta final de cada turno ganha o cabeçalho H2 ("Blind disse", ou "Agente <nome que a pessoa deu> disse"). Um
  subitem que a IA traz também aparece como H2.
- Nada é falado automaticamente pelo leitor de tela, exceto a mensagem final, que é falada sozinha mesmo depois de uma
  execução longa. O resto se lê navegando com as setas.
- Mensagens da pessoa têm os botões copiar e editar. Blocos de código têm o botão copiar (que copia de verdade e
  anuncia "código copiado"), mostrado depois de "ver o comando executado".
- Mensagens de espera ("aguardando o provedor há Xs") atualizam no lugar, sem repetir e sem H2.
- Imagem enviada ou gerada é sempre transcrita na interface; imagem gerada aparece com link pelo nome da imagem e a
  transcrição logo abaixo, sem frase do tipo "gerei a imagem".
- Documentos citados aparecem como link local que abre ou baixa com Enter.

### 5. Autonomia, independência e estratégia

- O sistema é livre, autônomo e independente. Nunca diz "não dá porque X não está instalado ou não está rodando".
  Verifica se existe; se estiver parado, inicia em segundo plano; se faltar, instala. Isso inclui ferramentas de teste
  e verificação. Só abre janela se a pessoa pedir.
- Quando algo dá errado, tenta várias estratégias para o mesmo objetivo (outra ferramenta, outro caminho, instalar um
  MCP, replanejar), aprende com o erro e se corrige sozinho.
- Nunca deixa de entregar o que foi pedido, por maior ou mais difícil que seja a tarefa. Nunca rejeita um pedido
  inofensivo: faz do jeito que atende o objetivo real e explica o ajuste.
- Exceção do nicho: quando o produto tem um nicho específico (aqui, acessibilidade digital), um pedido fora dele
  não é atendido. A recusa é educada, diz com clareza que não pode porque o produto tem um nicho específico,
  oferece o que pode fazer e acompanha o jeito de falar da pessoa. Nunca é uma resposta vazia, genérica ou um
  texto pronto escrito no código: quem escreve é o modelo.
- Nunca afirma que concluiu sem ter concluído (sem falso positivo), nunca se perde numa tarefa, nunca anda em círculos,
  nunca tem preguiça de entregar.
- Não pergunta à toa nem pede para a pessoa fazer o que ele mesmo pode fazer. Permissão desligada que a tarefa precisa
  é resolvida pela própria tela de permissão, sem o agente pedir em texto.
- Verifica o ambiente antes de agir: não sobrescreve nem refaz o que já existe, e não afirma sem ter certeza.
- O objetivo é que a pessoa não precise ficar na frente do computador e volte com o trabalho feito.

### 6. Contexto e ambiguidade

- Pedido vago de verdade, sem contexto, gera uma pergunta cedo.
- Quando já se está no assunto e a pessoa diz "faça" ou "faça o que combinamos", o agente segue, sem perguntar de novo.
- Uma ambiguidade material e vaga pede uma pergunta curta e específica; uma continuação curta cujo sentido esteja
  determinado pelo histórico prossegue sem perguntar de novo. Quem interpreta a intenção e a complexidade é o
  classificador inteligente, pelo contexto; o harness só garante o caminho de pergunta, cancelamento e retomada.
- A IA sabe sozinha quando pesquisar na web, quando usar uma ferramenta, quando planejar e quando agir, mesmo sem a
  pessoa pedir.
- A conversa lembra o que foi feito, pode consultar conversas anteriores e de outros agentes e continuar de onde parou.

### 7. Aprovação: ligada ou desligada, nunca bloqueio

- Com a aprovação desligada, o agente faz tudo sem perguntar. Com ela ligada, faz com pedido de aprovação. Nunca uma
  recusa seca. Vale para o sistema inteiro e para as duas interfaces.
- Ações irreversíveis ou de alto impacto (apagar, sobrescrever, enviar, publicar, gastar) seguem a configuração de
  aprovação.
- A confirmação mostra tudo o que vai mudar, inclusive o que seria desligado. Nunca desligar uma capacidade que ninguém
  pediu.
- A segurança existe, mas sem travas desnecessárias: o sistema é seguro e ao mesmo tempo livre.
- O que não entra na chave de aprovação são os limites do harness da regra 1, como a pasta de trabalho: o agente não
  mexe fora da pasta que a pessoa escolheu. A liberdade vem de a pessoa poder escolher qualquer pasta pela interface, e
  não de o agente sair dela sozinho.

### 8. Tempo, tokens e chamadas adaptativos, decididos pela IA

- Nenhum relógio fixo e nenhum limite fixo de tokens, de chamadas ou de etapas, imposto pelo código, encerra uma tarefa
  em andamento. Não existe prazo, deadline, teto de tempo, teto de tokens nem máximo de ações, fixo ou calculado de
  antemão, que corte uma execução que continua progredindo.
- Quanto tempo, quantos tokens e quantas etapas uma tarefa precisa é decisão da IA (o classificador e o modelo), pelo
  significado da tarefa e pelo que acontece na execução, e nunca uma conta determinística. Tarefa grande leva o que
  precisar enquanto avança. Se algum teto for atingido, isso é defeito de dimensionamento, não comportamento esperado.
- O plano que o modelo fez é mantido inteiro, nunca cortado num número fixo de etapas. Nunca se promete ao modelo um
  "máximo de N ações" nem se molda o plano por um orçamento de ações. O código só confere, de tempos em tempos, se
  algo novo aconteceu (uma etapa concluída ou uma ação nova e diferente). O que quem recebe trabalho delegado faz
  conta para o custo, nunca contra quem coordena.
- Economia: aproveitar a chamada que já existe. Nunca abrir uma chamada nova para ver tudo de novo, varrer tudo outra
  vez ou passar por tudo de novo para concluir: isso gasta muito. Cada etapa parte do resultado das anteriores e do que
  já está provado, e o que já foi lido, medido ou concluído não se refaz.
- Compactação: quando o contexto cresce, o classificador decide sozinho, pelo significado, se e quando resumir a
  conversa, e resume sem perder nada: o que sai do contexto é guardado inteiro e volta por um identificador (regra 9,
  engenharia de contexto). Nunca por contagem fixa, nem por heurística, nem sem caminho de volta.
- Comando lento não é morto: passado o tempo esperado, segue em segundo plano e o agente pode esperar ou parar.
  Chamada ao modelo que demora é tentada de novo com mais tempo e o mesmo nível de raciocínio.
- Depois de um tempo esgotado, a nova tentativa continua esperando a mesma chamada que já está em andamento, com mais
  paciência; nunca abre uma chamada nova por cima da antiga (seria trabalho e custo duplicados).
- Tempo esgotado, queda de conexão e limite de ritmo do provedor não são laço: esperam de verdade e fazem as chamadas
  se revezarem.
- O que encerra é estar travado (sem progresso, repetindo a mesma ação), o cancelamento pela pessoa, ou um orçamento de
  custo que a própria pessoa configurou de forma explícita (escolha dela, nunca um limite embutido no código).
- Vale também para testes, scripts e verificações: nenhum relógio fixo por cima do sistema. O teste espera o fim que o
  próprio sistema decide e só para se o aplicativo deixar de responder.
- Se a execução for interrompida (cancelamento, orçamento de custo da pessoa, trajetória que deixou de convergir),
  preserva-se o melhor resultado verificável e a entrega parcial é honesta: distingue artefato utilizável com
  ressalvas de falha bloqueante, e nunca chama resultado parcial de completo.

### 9. Economia, qualidade e roteamento inteligente

- Economia e qualidade são pilares: sempre inteligência, qualidade, performance, precisão, foco e economia de tokens.
- O roteador é inteligente, econômico e equilibrado. O melhor modelo não é o maior; é o que entrega com qualidade
  gastando menos. Modelos maiores só para o que é pesado, subindo aos poucos conforme o roteador decide.
- O classificador escolhe pelo significado o modelo, as skills e os especialistas. Os modelos não são fixos: cada
  tarefa vai para o modelo certo, e o mesmo comportamento vale para todos os modelos do roteamento automático
  (ajustando o que cada um espera). O vencedor nunca é fixo por nome, ordem ou palavra-chave. Quando a qualidade
  merece o custo extra, o roteador pode consultar mais de um candidato e pedir uma síntese julgada; tarefa simples usa
  uma única chamada, e se o julgamento falhar fica a melhor resposta verificável já obtida.
- Quanto o modelo pensa antes de agir também é decisão do roteador, pelo significado da tarefa, na mesma chamada em
  que ele decide a estratégia (sem chamada extra): pouco quando o caminho é claro e o trabalho é fazer, mais quando há
  decisão difícil de verdade, subindo sozinho quando uma etapa falha. Nunca pensar sem limite por falta de escolha:
  pensamento a mais faz a pessoa esperar minutos e é pago em toda chamada. Se a pessoa escolheu um nível, vale o dela.
- Executa várias ferramentas ao mesmo tempo quando isso ajuda; especialistas independentes rodam em ondas, e o
  progresso é emitido conforme cada um termina. A economia nunca esconde uma etapa que o relatório apresenta como
  concluída.
- Não refaz trabalho: cada etapa recebe o resultado das anteriores, e fatos já provados são reaproveitados.
  Compactação de conversa é decidida pela IA, não por heurística.
- Não existe modelo padrão embutido: o padrão é a última escolha da pessoa em cada provedor.

Engenharia de contexto (vale para todo módulo, toda interface e todo laço que chama um modelo):

- Nada é reenviado ao modelo sem necessidade. Todo laço que acumula histórico (resultados de ferramentas, conteúdo de
  arquivos gravados ou lidos, saídas de comando, conversa) tem de ter um jeito de aliviar esse histórico; um laço em
  que o contexto só cresce é defeito, mesmo que a tarefa termine.
- Quem decide é a IA: o código só mede o tamanho (um fato) e, quando ele cresce, convida o modelo a organizar a
  própria memória de trabalho. O modelo escolhe o que ainda precisa ver palavra por palavra e escreve, com as
  palavras dele, a nota que fica no lugar do resto. Se decidir manter tudo, fica tudo.
- Nada se perde: o que sai do contexto é guardado inteiro antes e volta por um identificador, com uma ferramenta que
  o modelo tem à mão. Sem esse caminho de volta, não se tira nada. Arquivo já gravado é memória: guarda-se o caminho e
  relê-se quando preciso, em vez de carregar o conteúdo.
- O começo de cada chamada (instruções e lista de ferramentas) fica estável de uma chamada para a outra e o
  histórico só cresce no fim, para o provedor reaproveitar o que já processou. Nada de hora, ordem que muda ou
  ferramenta que entra e sai no meio de uma tarefa.
- As ferramentas enviadas em cada chamada são as que a tarefa precisa, e quem julga isso é o roteador, pelo
  significado, na mesma chamada em que decide a estratégia. O código só tem o catálogo (quais ferramentas existem e
  de que grupo são). Sem opinião do roteador, vai tudo. Nada fica fora de alcance: um grupo que ficou de fora entra
  na hora em que o agente pedir ou usar uma ferramenta dele, e nunca sai no meio da tarefa.
- O pensamento do modelo só volta ao provedor junto da rodada ainda em aberto (a última fala dele, cujas
  ferramentas estão sendo respondidas). O pensamento de rodadas anteriores nunca é reenviado: a pessoa continua vendo
  na área recolhida, mas ele não entra de novo em cada chamada.
- Chamadas auxiliares (classificador, roteador, checagens de escopo e de segurança, revisões) vão no modelo mais
  barato que dá conta, recebem só o que precisam para julgar e nunca se repetem para a mesma pergunta. O que elas
  gastam é medido por tipo de chamada e tem de ser uma parte pequena do total: coordenação e checagem que gastam mais
  do que o trabalho de verdade são defeito.
- Quem recebe trabalho delegado devolve o resultado resumido a quem coordena, não o histórico inteiro do que fez.
- Todo módulo novo mede antes de afirmar: quantos tokens cada tipo de chamada gasta e do que é feita a mais pesada.
  Economia é verificada com número de execução real, não suposta.

### 10. Aprendizado sempre

- O sistema aprende com os erros, as correções, os falsos positivos e as atualizações, para melhorar qualidade,
  performance e precisão, sem a pessoa precisar pedir.
- O aprendizado vale na hora, sem fila de aprovação. Aprendizado sobre o mesmo assunto atualiza a habilidade existente,
  nunca cria duplicata. Habilidades seguem o formato aberto SKILL.md.
- Uma remoção da lista de achados não é automaticamente aprendida como falso positivo: pode ser só um item fora do
  escopo. O julgamento continua sendo da IA.
- As habilidades são aplicadas sozinhas pelo classificador quando a tarefa pede.
- O sistema aprende o que as APIs reais esperam testando de verdade no sandbox, para que o próximo software já nasça
  funcionando.
- Conhecimento que muda no mundo (como acessibilidade) se atualiza sozinho a partir de fontes confiáveis.

### 11. Evidência: verde não é funcionando

- Teste passando não é produto pronto. Mock não prova integração. Afirmação da IA não é evidência.
- Quem executa não é quem aprova: executor, revisor, verificador e portão são papéis separados. Delegar não transfere
  responsabilidade: o resultado de um subagente é verificado.
- Primeiro no sandbox isolado, depois no ambiente real, e só então entregar. O resultado é testado de verdade, não
  simulado.
- A entrega diz o que foi feito, o que foi verificado, o que falhou ou não pôde ser testado e onde está o resultado.
- Ausência de achados não é certificação de conformidade: decisões normativas (como WCAG) exigem evidência
  contextual, e técnica recomendada não é requisito obrigatório isolado.

### 12. Engenharia de software de qualidade, por padrão

- Código limpo, separação de responsabilidades, estrutura de pastas e convenções do próprio projeto, sem excesso de
  engenharia.
- Testes no padrão do projeto. Em Python, sempre ruff, mypy e pytest; em JavaScript, o lint e os testes do projeto.
- A cerimônia acompanha o tamanho do trabalho, e quem julga o tamanho é a IA: num trabalho pequeno e de caminho
  claro, código e testes são escritos juntos, a verificação roda quando algo mudou e uma vez no fim. Nada de etapas
  só de cerimônia nem de repetir a mesma verificação sem mudança no meio. O que nunca muda é a prova: os testes
  existem, rodaram de verdade e o resultado real foi conferido.
- Nunca deixar arquivos extras no projeto (rascunhos, capturas, relatórios de trabalho, scripts descartáveis).
- Todo bug real corrigido ganha teste de regressão. Código morto e lógica antiga que atrapalhe a IA são removidos.
- O agente faz tudo isso sozinho, se corrigindo, sem a pessoa precisar pedir.

### 13. Acessibilidade e visão de UX

- O sistema é feito para todos, e pensar em quem usa leitor de tela é obrigatório em todos os módulos, sem exceção:
  é o que o diferencia. Em toda entrega ele executa e testa de verdade como uma pessoa que usa leitor de tela e só
  teclado usaria; revisar o código não basta.
- Acessibilidade é obrigatória em tudo: interface, código, arquivos, edição, engenharia, documentos (Word, PDF) e
  imagens. Nunca a acessibilidade genérica: aprendida, atualizada e testada como uma pessoa real usaria.
- Toda interface é julgada como alguém que navega só por teclado e leitor de tela, e com o olhar de um profissional de
  UX: o controle certo (escolher entre opções conhecidas é uma lista pelas setas, nunca um campo para adivinhar e
  digitar), cada coisa no lugar certo, o nome do botão diz o que ele faz, a navegação segue o padrão de cada
  componente. Não basta estar conforme: tem que ser fácil de usar.

### 14. Paridade entre as interfaces

- Toda funcionalidade de comportamento vale em todas as interfaces que executam tarefas, na mesma entrega, em perfeita
  conformidade, com aprovação ligada ou desligada. Quais são as interfaces de cada projeto está na parte específica no
  fim deste arquivo.
- O assistente conversacional não é só um criador de agentes: é um assistente geral que executa tarefas reais.

### 15. Processo de trabalho

- Testar na interface real, como um usuário iniciante usaria, nas duas interfaces. Testes baratos (lint, tipos,
  unitários) antes; o teste ao vivo confirma.
- Um módulo de cada vez: nunca começar outro sem o atual funcionando por completo. Um módulo só está
  concluído quando: o que ele promete foi testado de verdade, ao vivo, na interface real; todo defeito achado foi
  corrigido com teste de regressão ou ficou registrado como pendência explícita; existe um README do módulo em
  `docs/modules/` explicando tudo o que ele entrega, o que foi medido, o que foi corrigido e o que ainda não está
  provado; a suíte e o lint passam; e o trabalho foi commitado. Pendência que depende de decisão da pessoa é
  perguntada e registrada antes de seguir. Nunca passar ao módulo seguinte com o anterior em aberto.
- Antes de codar, ver o que já existe no código, nos commits e nas docs.
- Documentar tudo o que foi feito e corrigido na pasta de cada módulo, e commitar ao final. Nunca fazer merge sem
  autorização.
- Documentos para o usuário em linguagem natural, direta e objetiva, sem asteriscos nem caracteres especiais, técnico
  só nos termos e conceitos.
- Falar com o usuário em português, em texto corrido.

### 16. Supervisão humana calibrada

- Intervenção humana onde o risco é maior (ações irreversíveis, escopo ampliado, ambiguidade material) e fora do
  caminho no resto. Supervisão constante em ação de baixo risco é tão errado quanto autonomia total em ação de alto
  risco.

### 17. Causa raiz, nunca só o sintoma

- Todo problema real é investigado até a causa antes de ser dado como resolvido: reproduzir, ler o código e os
  registros, formular a hipótese e prová-la. Corrigir só o sintoma, sem causa provada, é remendo e o problema volta.
- Preservar a evidência antes de reiniciar, sobrescrever ou limpar qualquer coisa (registros, estado, arquivos): uma
  causa perdida não se prova depois.
- Quando a causa não puder ser provada na hora (falta de crédito, defeito intermitente, evidência perdida), a
  correção cobre o mecanismo mais provável, o sistema passa a registrar o que provaria a causa na próxima ocorrência, e
  a entrega diz que a causa NÃO está provada. Nunca se declara resolvido o que só foi contornado.
- A mesma classe de falha ganha também a defesa contra a recorrência (teste de regressão, verificação ou alerta), para
  não depender de alguém lembrar.

## Antes de declarar qualquer implementação concluída

**Não é opcional.** Antes de dizer "pronto" pra qualquer mudança de código
neste projeto, consulte e aplique o que for cabível dos 3 documentos abaixo.
Eles não são referência passiva — são checklist operacional.

1. **`docs/metodologia-verificacao-arquitetura.md`** — pirâmide de
   verificação (Static Analysis → Unit → Component → Architecture Fitness
   Functions → Contract → Integration → Non-Functional → E2E → Regression →
   Quality Gate → Observability). Pra TODA mudança de código:
   - Rodar `ruff check` no(s) arquivo(s) tocado(s) — sempre.
   - Rodar `mypy` se o projeto for Python — este é.
   - Rodar os testes unitários/integração relevantes ao módulo tocado, não
     só assumir que compila.
   - Se a mudança envolve a "costura" entre 2+ módulos (um passa dado pro
     outro, um chama o outro, um documenta um contrato que o outro deveria
     respeitar): ler os dois lados antes de considerar concluído — é onde
     mora a classe de bug mais cara de descobrir tarde (o exemplo concreto
     está registrado no fim do próprio documento).
   - Todo bug real corrigido ganha teste de regressão, sempre, sem exceção.
   - Nunca subir pro degrau mais caro (E2E real, custa API de verdade) sem
     esgotar os degraus baratos antes — E2E confirma, não descobre.

2. **`docs/conceitos-ia-para-desenvolvimento-de-software.md`** — engenharia
   de sistemas com IA (Harness Engineering, roteamento contextual,
   decomposição, Agent Evals, trajetória, custo, loop detection,
   checkpoints, graceful degradation). Aplicável sempre que a mudança tocar
   o pipeline de agentes (Planner/Critic/Orchestrator/sub-agentes): a
   decisão de conteúdo, classificação e escolha de modelo é da IA; o harness
   valida elegibilidade, credenciais, contratos e limites operacionais.
   Contingências técnicas não substituem julgamento semântico.
   Ao decompor uma tarefa grande em partes, garantir
   que quem AVALIA o resultado também sabe que existem partes (não só quem
   gera).

3. **`docs/conceitos-ia-seguranca-confiabilidade.md`** — segurança e
   confiabilidade de agente (sandboxing, permission boundaries, blast
   radius, adversarial evals, recovery/resilience). Aplicável sempre que a
   mudança tocar execução de código gerado, ferramentas expostas a um
   sub-agente, ou conteúdo vindo de fora (busca web, input do usuário).

## Regra geral de conclusão

Uma implementação só está "concluída" quando: lint limpo, testes relevantes
passando (incluindo os novos de regressão do bug corrigido), e — quando a
mudança tocar a costura entre módulos — confirmação de que o que um lado
promete é literalmente o que o outro consome. "Parece certo" não é
suficiente; "os degraus baratos da pirâmide confirmam" é.

A proporcionalidade vale só para o tamanho da cerimônia (quais degraus da pirâmide
cabem numa mudança trivial e isolada), nunca para dispensar uma regra: todas continuam
obrigatórias e a prova (testes que rodaram de verdade e resultado conferido) nunca muda.
O objetivo é processo real de engenharia, não burocracia por burocracia.

## Regra permanente: agente = modelo + harness (determinismo só onde protege)

**Obrigatória para todo código, teste e correção deste projeto, para toda integração de
modelo/provider presente ou futura, sem exceção** — nenhum modelo, provider ou ferramenta
tem tratamento especial que o isente desta regra. Esta seção é intencionalmente
**genérica e portável**: não nomeia nenhum provider, arquivo ou módulo específico deste
projeto de propósito, para poder ser copiada para o `CLAUDE.md` de qualquer outro software
agentic sem edição. Onde este projeto tiver detalhe concreto de como a regra se aplica aqui
(nomes de arquivo, endpoints, histórico de correções), ele fica isolado na parte específica
final deste arquivo — apague só aquela parte ao portar esta regra para outro projeto.

### Princípio central

Um agente é **modelo + harness**, dois papéis que nunca se invertem:

- **O modelo** interpreta intenção, decide o que uma tarefa realmente pede, se há ambiguidade
  relevante, como decompor, qual estratégia técnica seguir, o que examinar, como corrigir,
  quando revisar a própria abordagem e como explicar progresso/resultado. Isto é julgamento —
  cabe à IA, não a uma condição fixa no código.
- **O harness** (o código determinístico ao redor do modelo) não tenta ter a mesma opinião
  que o modelo sobre o que fazer — ele impõe o que é **permitido**, independente do que o
  modelo "pretende". O modelo não se autopolicia; o harness é o limite de conformidade.

### O que o harness controla — e só ele

- **Identidade do agente e escopo de credencial**: cada agente/execução opera com a menor
  permissão suficiente para a tarefa (least privilege); prefira credenciais de curta duração
  e com escopo estreito a chaves estáticas de longa duração quando a plataforma de credencial
  permitir.
- **Acesso a ferramenta como negado-por-padrão**: uma ferramenta/capacidade só fica disponível
  quando explicitamente concedida; nunca "disponível a menos que alguém desligue". A concessão
  é capturada quando o agente nasce, e o despachante verifica concessão, schema e aprovação
  antes de chamar o handler.
- **Isolamento e sandbox**: execução de código, navegador ou comando roda num limite que não
  alcança mais do que o necessário, e cujo vazamento não compromete o resto do sistema.
- **Validação de caminho e de comando**: nenhuma operação de arquivo ou processo sai do
  workspace/escopo autorizado; comandos são validados antes de rodar, nunca depois.
- **Cancelamento e interrupção**: parar uma execução em andamento é sempre possível e sempre
  determinístico — nunca depende do modelo "decidir" parar. Cancelar preserva o que já foi
  recebido e encerra o que estava ativo.
- **Controle central de progresso, sem relógio fixo**: todo laço, retry ou delegação é
  acompanhado por um controle único, e não por contadores paralelos e cegos. Nenhum limite
  fixo de tempo, de tokens, de chamadas ou de etapas corta uma execução que continua avançando
  (regra 8). Retry não zera o que já foi provado nem o que já foi gasto.
- **Loop adaptativo — nunca loop infinito**: todo laço de execução (tool-loop, delegações,
  reparos de JSON, espera de steering/esclarecimento) é encerrado por algo real —
  convergência (não há mais nada útil a fazer), ausência de progresso, cancelamento do
  usuário, orçamento de custo configurado pela pessoa ou detecção de repetição (a mesma
  decisão voltou a aparecer). Uma decisão repetida encerra o laço com o que já está provado
  em vez de insistir. Esperar de verdade (conexão, ritmo do provedor, pergunta ao usuário)
  não é laço.
- **Entrega parcial honesta**: se o laço for encerrado antes da conclusão, preservar o melhor
  resultado verificável, distinguir artefato utilizável com ressalvas de falha bloqueante, e
  nunca chamar um resultado parcial de completo.
- **Validação de schema/contrato**: entrada e saída estruturada são validadas contra um
  contrato explícito antes de seguir adiante.
- **Sintaxe e integridade de arquivo**: uma edição/gravação só é aceita se preservar a
  integridade sintática do que já existia.
- **Proteção contra operação destrutiva e portão de aprovação**: qualquer ação irreversível
  (apagar, sobrescrever, enviar, publicar, gastar) exige aprovação explícita antes de
  executar — nunca só depois, nunca implícita. A configuração não pode desativar a aprovação
  de ferramentas marcadas como irreversíveis.
- **Registro de evento e recuperação de falha**: toda decisão de permissão, erro e retry fica
  auditável; uma falha parcial deve poder ser retomada sem repetir trabalho já provado.
- **Escalonamento para humano**: quando a ambiguidade for material ao resultado ou a ação for
  de alto risco, o harness garante que existe um caminho real de parar e perguntar — a decisão
  de *quando* perguntar continua sendo da IA, o harness só garante que o caminho existe e
  funciona.

### O que nunca vira regra fixa

**Nunca** transformar uma decisão subjetiva (intenção, se uma tarefa está clara o bastante,
qual ferramenta "parece" certa, se uma resposta "parece" completa, quanto tempo uma tarefa
"deveria" levar) em árvore fixa de palavras-chave/regex/condição/relógio — isso é determinismo
em excesso disfarçado de segurança, e é exatamente o tipo de regressão que trava um agente sem
de fato protegê-lo. Uma regra determinística nova só é aceitável quando protege um dos itens
da lista acima ou valida um **fato objetivo e verificável** (ex.: uma URL literalmente
presente no texto, um limite de tamanho, um schema) — nunca para "deixar o comportamento mais
previsível" ou "fazer um teste passar mais fácil". Ao escrever ou revisar um teste: se ele
exige que o código adivinhe ou force uma categoria de intenção por palavra-chave em vez de
deixar o modelo julgar, o teste está pedindo o tipo errado de determinismo — não aceitar.

### Comportamento conversacional obrigatório

Em qualquer chat/execução: narrar cada ferramenta em linguagem natural (nunca nome técnico
cru, nunca JSON/protocolo bruto na interface); nunca entregar só no final de uma tarefa longa;
permitir interromper, corrigir ou redirecionar uma execução em andamento sem perder o
progresso já feito; perguntar cedo quando a ambiguidade for material ao resultado, em vez de
assumir em silêncio ou travar sem convergir.

### Calibração de supervisão humana

Um agente de produção não roda nem totalmente livre nem totalmente supervisionado: o
harness garante que existe intervenção humana exatamente onde o risco é maior (ações
irreversíveis, escopo ampliado, ambiguidade material) e fica fora do caminho no resto —
supervisão constante em toda ação de baixo risco é tão errado quanto autonomia total em
ação de alto risco.

---

## Parte específica deste projeto (Qaaccessibility)

Tudo acima é comum aos projetos Agentic e Qaaccessibility. Daqui em diante, só o que vale para este.

### Interfaces que executam tarefas (regra 14)

A interface web de chat (`web/src/screens/ChatScreen.tsx`) e qualquer outra que execute tarefas. Toda
funcionalidade de comportamento vale em todas elas, na mesma entrega. A regra dos dois chats separados é só do
projeto Agentic e não existe aqui.

### Mobilização contextual da squad

O chat atua como coordenador da squad de acessibilidade. O classificador escolhe
`squad_roles` e sua ordem pelo contexto, sem uma sequência obrigatória de gestão
e sem uma regra que dispense a squad em auditorias pequenas. Os especialistas
das ferramentas de análise são membros da mesma squad. Durante o trabalho, o
agente pode usar `consult_squad` para consultar outros papéis ou rever a abordagem
com os resultados reais. Não converter essa seleção em palavras-chave, regex ou
heurística de intenção. Uma consulta de QA define/revisa evidências; não significa
que testes foram executados. Handoffs não concedem aprovação para mutações.
O harness valida IDs, contratos, permissões e cancelamento, e acompanha o progresso do conjunto.
As rotinas batch de planejamento não são a política de seleção do chat.

### Nota específica deste projeto

Aqui, "todo modelo/provider sem exceção" cobre OpenAI, Anthropic, Gemini, xAI,
Ollama, Factory, OpenCode Go e `AgenticAutoProvider`. Uma versão anterior desta nota citava
commits específicos e um documento (`docs/AGENTIC_BEHAVIORAL_CONTRACT_AND_ACCEPTANCE.md`) como
o histórico completo de por que a regra existe -- auditoria em 2026-09-12 confirmou que
nenhum dos hashes citados existe no histórico git deste repositório e que o documento nunca
chegou a ser criado, então a referência foi removida em vez de mantida sem verificação. Se o
histórico completo for registrado no futuro, documentar aqui com um link real, não uma
citação que não pode ser conferida. O mecanismo concreto de redirecionamento em tempo real é
`POST /chat/steer` (`backend/src/routes/chat.py`,
canal `chat_progress.request_steer`/`pop_pending_steer`) / botão "Redirecionar" que aparece no
lugar de "Parar" quando há texto digitado durante o streaming (`web/src/screens/ChatScreen.tsx`).
Cobre os providers OpenAI (Responses e Chat Completions), xAI, Ollama e Anthropic; Gemini e
Factory ainda não têm steer ligado (ver comentários em `run_agent.py`/`factory_adapter.py` --
cancelamento best-effort continua disponível para os dois).

### Evidência operacional de 2026-09-30

O turno compartilha um único orçamento em `execution_scope.py`, incluindo
triagem, consultor de rotas, ferramentas, especialistas e reparação de JSON.
A complexidade declarada pela IA adapta o orçamento do turno; retry não reinicia a
contagem. Planejamento gerencial depende de uma decisão estruturada da IA, não da
presença de URL/anexo ou de palavras no pedido.

Convergência com a regra 8 (2026-10-07): o orçamento do turno em `execution_scope.py` deixou de ser
um teto de duração. O `deadline` passou a ser o instante em que a execução seria considerada TRAVADA:
todo progresso real (evento publicado, token recebido, ferramenta concluída, nova rodada do modelo,
especialista concluído) desliza esse instante, e a janela de silêncio se adapta à complexidade que a IA
declarou. `run_until_stalled` substitui os `wait_for` de prazo fixo no orquestrador, no `llm_client`, no
`route_advisor` e no factory. Toda execução tem esse orçamento: `orchestrate` e `run_conversation` abrem
o seu quando não há um do turno, então as rotas fora do chat seguem a mesma regra. A espera por
aprovação do usuário não tem relógio. Uma chamada lenta ao provedor em curso não é "travamento" enquanto
dado chega dentro da janela (cada pedaço recebido de uma chamada em fluxo a renova), e quando ela termina a janela recomeça; uma chamada que não entrega nada por toda a janela é travamento, mesmo sem erro (medido: 29 minutos presa no e2e de 2026-10-08), e o orquestrador segue com o parcial; um fluxo degenerado (mil pedaços seguidos vazios, só de espaço ou repetidos, que nenhuma resposta legítima produz) é encerrado como falha de provedor por `stream_guard.py`, sem refazer a mesma geração por outro endpoint, e uma chamada longa deixa no log o que está recebendo, para a causa de uma nova chamada presa ficar provada; depois de largar
especialistas parados, o restante do pipeline segue com janela nova (entrega parcial, não falha total). O factory não tem mais máximo de chamadas de ferramenta, e o laço
de um agente com ferramentas não é cortado por `max_iterations` (só a folha sem ferramentas é uma
chamada única, por estrutura); a repetição persistente depois da reflexão encerra o laço.

Tokens: nenhum chamador impõe teto de saída. `AIAgent.max_tokens` e o padrão de `call_llm` são
`None` (o parâmetro é omitido onde o provider permite). A Anthropic exige um número: usa um padrão
alto (32000) e, se o provider recusar o tamanho, o código refaz uma vez com o limite que o próprio
erro informa. O reparo de JSON em `call_llm_structured` não tem contador nem teto: dobra o espaço quando
a saída foi cortada e termina por saída válida, repetição da mesma saída ou do mesmo defeito, erro do
provider ou cancelamento.

Clientes HTTP dos providers: sem timeout de leitura nem de escrita (`_provider_timeout` em
`run_agent.py`); só estabelecer a conexão tem limite, porque isso não é trabalho em andamento. Uma
chamada lenta continua sendo a mesma chamada. As tentativas automáticas do SDK (queda de conexão, 429,
5xx) voltaram a valer dentro do turno: antes `_sdk_retry_options` as desligava (`max_retries=0`).

Orçamento de custo da pessoa (único teto de trabalho que existe): a tela de Configurações tem o campo
"Limite de tokens por resposta (opcional)", gravado como `TURN_TOKEN_BUDGET` e lido em `Settings.turn_token_budget`.
O padrão é 0, sem limite: o código nunca escolhe um número por conta própria. O consumo de cada chamada ao
provider (`_accumulate_usage`) soma no orçamento do turno, e `check_execution` levanta `TokenBudgetReachedError`
no próximo limite de chamada; chamadas em andamento terminam, então o limite é verificado nas fronteiras, não
no meio de uma geração. O chat encerra com uma explicação honesta (o que já apareceu continua valendo, ou
"não houve como apurar nada") e diz como continuar; nunca é tratado como erro. A chamada de fallback para outro
modelo não é tentada depois do limite. A contagem inclui as chamadas de triagem e roteamento, que são custo real.

O limite vale também fora do chat (CI, scripts, outras IAs): `RequestBudgetMiddleware` abre o orçamento de cada
pedido HTTP com o limite da pessoa, e o que acontece ao atingi-lo segue o que a Anthropic (`stop_reason: max_tokens`)
e a OpenAI (`finish_reason: length`) fazem: devolver o que já foi feito como resposta normal (HTTP 200), marcada
como cortada, e não como erro. As análises voltam com `data.token_limit`, `data.complete = false` e um `warning`
que diz se há achados parciais ou nenhum; o crawl traz `token_limit`; uma rota que atinge o limite antes de
produzir qualquer coisa responde 200 com `complete: false`, o corte descrito e o cabeçalho `X-Token-Limit-Reached`.

Não existe prazo legado de reserva: `run_until_stalled` não tem `fallback_timeout`, e a consulta de roteamento
(`advise_route`, `rank_candidates`) não recebe timeout. Sem orçamento (não acontece nos caminhos do produto,
que sempre abrem um) só o cancelamento encerra uma espera.

Limites que ainda existem, e que são honestos: a consulta ao catálogo de modelos do Ollama Cloud
(`ollama_cloud_adapter.py`) mantém timeouts curtos de 10 a 15 segundos, por ser metadado e não trabalho do
modelo; uma chamada de fluxo que não entrega dado por toda a janela deixa de segurar o turno, mas a conexão em si só
é encerrada pelo limite de leitura do HTTP, pelo cancelamento da pessoa ou pelo sistema operacional; o limite de tokens não cobre o servidor MCP por stdio nem o protocolo A2A, que não passam
pelo middleware HTTP, e uma rota que faz várias chamadas isoladas divide um único orçamento por pedido; o padrão de 32000 da
Anthropic e a autocorreção pelo limite do provider foram cobertos só com mocks, sem chamada real. Ao mexer
nesses pontos, convergir para a regra 8 e registrar aqui o que mudou.

Cada instância de `AIAgent` captura suas concessões de ferramentas ao nascer.
O dispatcher verifica concessão, schema e aprovação antes de chamar o handler.
A configuração não pode desativar aprovação de ferramentas assim marcadas.
Atualizações públicas estruturadas são separadas de raciocínio privado e de
JSON; a interface mantém um feed consultável com setas, sem anunciar progresso
automaticamente. Cancelamento preserva texto recebido e encerra cartões ativos.
O narrador recebe fatos estruturais observados do HTML original; ausência de
achados não permite inventar elementos presentes nem certificar conformidade.
Especialista de semântica, revisor, papéis da squad e chat compartilham a calibração normativa
de `backend/src/shared/normative_calibration.py`: técnicas recomendadas não
são requisitos obrigatórios isolados, e decisões WCAG exigem evidência contextual.

O pedido, histórico e atualizações já comunicadas acompanham as chamadas dos
especialistas por `request_context.py`; a ponte síncrona/assíncrona das ferramentas
preserva esse contexto e o orçamento. Redirecionamentos consumidos pelo agente
também atualizam o escopo dos próximos especialistas. O revisor recebe o HTML
original da captura, inclusive em cada lote, não apenas os achados consolidados.
Eventos de quadro/roteamento são estado interno, não narração pública. Cada resposta
guarda sua própria duração; histórico sem esse dado não exibe um tempo inventado
nem a mensagem fixa “Processamento concluído”.

Isso não é uma declaração de conformidade integral: sandbox uniforme,
credenciais curtas por execução, recuperação durável de todos os módulos,
latência de primeira atualização e comportamento de todos os providers ainda
exigem evidência adicional. Consulte
`docs/implementacao-regras-mestras-2026-09-30.md` para testes e limitações reais.
