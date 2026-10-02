Qaaccessibility— instruções operacionais para agentes

Este arquivo é lido automaticamente no início de qualquer sessão de agente
neste repositório. Não é material de estudo — são regras de processo.

## Mobilização contextual da squad

O chat atua como coordenador da squad de acessibilidade. O classificador escolhe
`squad_roles` e sua ordem pelo contexto, sem uma sequência obrigatória de gestão
e sem uma regra que dispense a squad em auditorias pequenas. Os especialistas
das ferramentas de análise são membros da mesma squad. Durante o trabalho, o
agente pode usar `consult_squad` para consultar outros papéis ou rever a abordagem
com os resultados reais. Não converter essa seleção em palavras-chave, regex ou
heurística de intenção. Uma consulta de QA define/revisa evidências; não significa
que testes foram executados. Handoffs não concedem aprovação para mutações.
O harness valida IDs, contratos, permissões, cancelamento e orçamento agregado.
As rotinas batch de planejamento não são a política de seleção do chat.

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

Isso não substitui julgamento — para mudanças triviais e isoladas, aplicar
o bom senso sobre qual subconjunto do checklist é proporcional. O objetivo é
processo real de engenharia, não burocracia por burocracia.

## Regra permanente: agente = modelo + harness (determinismo só onde protege)

**Obrigatória para todo código, teste e correção deste projeto, para toda integração de
modelo/provider presente ou futura, sem exceção** — nenhum modelo, provider ou ferramenta
tem tratamento especial que o isente desta regra. Esta seção é intencionalmente
**genérica e portável**: não nomeia nenhum provider, arquivo ou módulo específico deste
projeto de propósito, para poder ser copiada para o `CLAUDE.md` de qualquer outro software
agentic sem edição. Onde este projeto tiver detalhe concreto de como a regra se aplica aqui
(nomes de arquivo, endpoints, histórico de correções), ele fica isolado na nota final desta
seção — apague só aquela nota ao portar esta regra para outro projeto.

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
  quando explicitamente concedida; nunca "disponível a menos que alguém desligue".
- **Isolamento e sandbox**: execução de código, navegador ou comando roda num limite que não
  alcança mais do que o necessário, e cujo vazamento não compromete o resto do sistema.
- **Validação de caminho e de comando**: nenhuma operação de arquivo ou processo sai do
  workspace/escopo autorizado; comandos são validados antes de rodar, nunca depois.
- **Cancelamento e interrupção**: parar uma execução em andamento é sempre possível e sempre
  determinístico — nunca depende do modelo "decidir" parar.
- **Timeouts e limites operacionais**: todo laço, retry ou orçamento de execução tem um teto
  agregado imposto pelo código, não apenas a soma de laços independentes sem controle central.
- **Orçamento adaptativo único — o tempo se adapta e nunca deve esbarrar no teto**: tempo,
  tokens e turnos partem da complexidade que o classificador inteligente atribuiu e dos
  recursos realmente selecionados, e o prazo se adapta conforme as tarefas executam — a
  adaptação recalcula o deadline a partir do início original (retry não reinicia o relógio).
  O teto é dimensionado pela complexidade declarada e pelas ondas de trabalho selecionadas
  para que a execução normal convirja com folga: atingir o teto de tempo é sinal de
  orçamento mal dimensionado, não o comportamento esperado. Não criar um segundo contador
  de rodadas que interrompa antes do orçamento agregado; o deadline central é o único teto
  operacional da fase. Se mesmo assim o teto for alcançado, vale a entrega parcial honesta
  descrita abaixo.
- **Economia sem sacrificar precisão**: compartilhar contexto, cachear fatos já provados,
  executar especialistas independentes em ondas controladas e emitir progresso conforme
  cada papel termina. A economia nunca pode ocultar uma etapa que o relatório apresenta como
  concluída.
- **Loop adaptativo — nunca loop infinito**: todo laço de execução (tool-loop, delegações,
  reparos de JSON, espera de steering/esclarecimento) é encerrado por algo real — convergência
  (não há mais nada útil a fazer), deadline agregado, cancelamento do usuário ou detecção de
  repetição (a mesma decisão voltou a aparecer). O teto que encerra o laço vem do orçamento
  central, nunca de um contador paralelo cego, e nenhum laço pode girar indefinidamente;
  uma decisão repetida encerra o laço com o que já está provado em vez de insistir.
- **Loops protegidos e entrega parcial honesta**: se o orçamento acabar, houver cancelamento
  ou a trajetória deixar de convergir, preservar o melhor resultado verificável. Distinguir
  artefato utilizável com ressalvas de falha bloqueante; nunca chamar um resultado parcial de
  completo.
- **Julgamento entre modelos no Alto**: quando o classificador indicar que a qualidade merece
  o custo adicional, o roteador pode consultar candidatos atuais do catálogo e pedir uma
  síntese julgada. O vencedor nunca é fixo por nome, ordem ou keyword; tarefas simples usam
  uma única chamada, e uma falha do julgamento preserva a melhor resposta verificável já obtida.
- **Validação de schema/contrato**: entrada e saída estruturada são validadas contra um
  contrato explícito antes de seguir adiante.
- **Sintaxe e integridade de arquivo**: uma edição/gravação só é aceita se preservar a
  integridade sintática do que já existia.
- **Proteção contra operação destrutiva e portão de aprovação**: qualquer ação irreversível
  (apagar, sobrescrever, enviar, publicar, gastar) exige aprovação explícita antes de
  executar — nunca só depois, nunca implícita.
- **Registro de evento e recuperação de falha**: toda decisão de permissão, erro e retry fica
  auditável; uma falha parcial deve poder ser retomada sem repetir trabalho já provado.
- **Escalonamento para humano**: quando a ambiguidade for material ao resultado ou a ação for
  de alto risco, o harness garante que existe um caminho real de parar e perguntar — a decisão
  de *quando* perguntar continua sendo da IA, o harness só garante que o caminho existe e
  funciona.

### O que nunca vira regra fixa

**Nunca** transformar uma decisão subjetiva (intenção, se uma tarefa está clara o bastante,
qual ferramenta "parece" certa, se uma resposta "parece" completa) em árvore fixa de
palavras-chave/regex/condição — isso é determinismo em excesso disfarçado de segurança, e
é exatamente o tipo de regressão que trava um agente sem de fato protegê-lo. Uma regra
determinística nova só é aceitável quando protege um dos itens da lista acima ou valida um
**fato objetivo e verificável** (ex.: uma URL literalmente presente no texto, um limite de
tamanho, um schema) — nunca para "deixar o comportamento mais previsível" ou "fazer um teste
passar mais fácil". Ao escrever ou revisar um teste: se ele exige que o código adivinhe ou
force uma categoria de intenção por palavra-chave em vez de deixar o modelo julgar, o teste
está pedindo o tipo errado de determinismo — não aceitar.

O classificador inteligente deve interpretar a intenção e a complexidade no contexto. Uma
ambiguidade material e vaga pede uma pergunta curta e específica; uma continuação curta cujo
sentido esteja determinado pelo histórico deve prosseguir sem perguntar de novo. O harness
garante apenas o caminho de pergunta, cancelamento e retomada; não decide a intenção por
keywords, regex ou heurística fixa.

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

**Nota específica deste projeto** (apagar esta nota ao portar a regra acima para outro
`CLAUDE.md`): aqui, "todo modelo/provider sem exceção" cobre OpenAI, Anthropic, Gemini, xAI,
Ollama, Factory, OpenCode Go e `AgenticAutoProvider`. Uma versão anterior desta nota citava
commits específicos e um documento (`docs/AGENTIC_BEHAVIORAL_CONTRACT_AND_ACCEPTANCE.md`) como
o histórico completo de por que esta regra existe -- auditoria em 2026-09-12 confirmou que
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
A complexidade declarada pela IA adapta o prazo a partir do início original;
retry não reinicia o relógio. Planejamento gerencial depende de uma decisão
estruturada da IA, não da presença de URL/anexo ou de palavras no pedido.

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
Uma remoção da lista de achados não é automaticamente aprendida como falso positivo:
pode ser apenas um item fora do escopo. O julgamento continua sendo da IA.
Eventos de quadro/roteamento são estado interno, não narração pública. Cada resposta
guarda sua própria duração; histórico sem esse dado não exibe um tempo inventado
nem a mensagem fixa “Processamento concluído”.

Isso não é uma declaração de conformidade integral: sandbox uniforme,
credenciais curtas por execução, recuperação durável de todos os módulos,
latência de primeira atualização e comportamento de todos os providers ainda
exigem evidência adicional. Consulte
`docs/implementacao-regras-mestras-2026-09-30.md` para testes e limitações reais.
