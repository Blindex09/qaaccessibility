---
paths:
  - "backend/**"
  - "web/src/**"
  - "scripts/**"
  - "docs/modules/**"
---

# Regras específicas do Qaaccessibility

> Carrega quando se mexe no backend, na interface web, nos scripts ou nos módulos. Texto integral da parte específica deste projeto, sem mudança.

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
Cobre os providers OpenAI (Responses e Chat Completions), xAI, Ollama e Anthropic; o Gemini tem steer ligado em `run_agent.py::_run_gemini` (verificado em 2026-10-08, sem prova ao vivo registrada) e o Factory ainda não tem (só `cancel_check` em `factory_adapter.py`; o cancelamento best-effort continua disponível).

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
é encerrada pelo limite de leitura do HTTP, pelo cancelamento da pessoa ou pelo sistema operacional; o limite de tokens não cobre o servidor MCP por stdio, que não passa pelo middleware HTTP, e no protocolo A2A a requisição passa pelo middleware e o trabalho em segundo plano herda o orçamento, mas ao atingi-lo a tarefa vira falha em vez de entrega parcial (verificado por leitura do código em 2026-10-08), e uma rota que faz várias chamadas isoladas divide um único orçamento por pedido; o padrão de 32000 da
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

### Revisão de relógios fixos de 2026-10-18

Varredura do backend, dos scripts e dos testes ao vivo contra a regra 8. O que cortava trabalho em andamento saiu:
- `routes/fix.py`: o teto de 420 s do corretor (`_FIX_TIMEOUT_SECONDS`) virou `run_until_stalled`; o 504 agora diz que o corretor parou de avançar.
- `services/remote_runners.py`: Selenium (60/180 s), Newman (90 s), Cypress (120 s), instalação do Cypress (300 s) e a checagem de versão do Cypress (15 s) usam `run_until_stalled`; o processo só é morto se travar ou se a pessoa cancelar. As chamadas ao Postman limitam só a conexão (tupla com leitura sem limite).
- `services/self_healing.py`: acabou o contador `max_retries`. O laço termina por sucesso, falha do corretor, assinatura de violações já vista antes (inclui oscilação entre dois estados), cancelamento ou parada de avanço; cada volta chama `check_execution`.
- `services/chat_tools.py` e `services/browser.py`: instalação do Playwright (600 s) e veraPDF (30 s) sem prazo; Tavily, Exa e Firecrawl limitam só a conexão. `services/crawler.py` (mapa do Firecrawl), `github_service.py` e `ticket_integrations.py` também.
- `agents/deep_research`: `max_iterations=8` removido (era inerte, o laço com ferramentas não tem contador).
- Scripts e testes ao vivo: clientes httpx e `urlopen` sem prazo de resposta (só a conexão), esperas de fim de turno do navegador com `timeout=0`.

Continua, de propósito: a janela de silêncio do orçamento do turno (`agent_timeout_seconds`, que desliza a cada progresso); os timeouts de navegação e de rede ociosa do Playwright, que têm saída graciosa e seguem com o que já carregou; as consultas ao catálogo do Ollama Cloud (metadado); as esperas curtas que só avisam progresso e não cancelam nada; as pausas de acomodação de tela (`wait_for_timeout`) dos scripts.

Defesa contra a volta: `tests/backend/unit/test_sem_relogio_fixo.py` varre o backend e reprova `asyncio.wait_for` com prazo, `subprocess` com `timeout` e chamada de rede com número fixo de segundos, fora de uma lista pequena e justificada.

Não provado: nenhum teste ao vivo foi rodado depois desta mudança (Selenium, Newman e Cypress reais, nem o `/fix` com self-healing contra um modelo real). A cobertura é de testes unitários e de integração com processos simulados.

### Registro de mudança de instrução ao modelo (regra 15), 2026-10-18

Mudança: o SYSTEM_PROMPT do chat ganhou as regras 21 (narração durante o trabalho) e 22 (autonomia e entrega honesta), que são as regras 3 e 5 do CLAUDE.md e tinham ficado sem texto: as regras 15 e 17 do prompt apontavam para uma "regra 5 de explicação falada" que já não existia. As referências agora apontam para a 21, e a regra duplicada 20 virou 20b. Vale para todos os provedores (texto sem ramo por modelo).
Testes que rodaram: tests/backend/unit/services/test_prompt_regras_de_comportamento.py (numeração única, referências existentes, conteúdo das duas regras) e a suíte unitária do backend.
Portão NÃO cumprido: conjunto amplo de avaliações ao vivo em tentativas repetidas, ablação (ligar e desligar as duas regras e comparar a taxa) e período de observação. Motivo: não há chave de provedor no ambiente desta sessão e a cota do Ollama Cloud estava esgotada. A mudança entra por ordem do dono e fica marcada como pendente de avaliação; se a taxa dos fluxos de narração ou de custo piorar ao voltar a rodar ao vivo, desfazer.

Segunda mudança de instrução do dia (2026-10-18): o prompt do especialista de formulários ganhou a orientação "não reportar marcador visual de obrigatório quando já há required ou aria-required", que antes era imposta por um filtro de expressões regulares no código (removido, regra 2). Mesmo portão da mudança anterior: o conjunto amplo ao vivo, a ablação e a observação continuam pendentes; os testes unitários provam só que o código não descarta mais achados e que o prompt traz as duas orientações.

### Nicho (regra 5)

Acessibilidade digital. Um pedido fora dela é recusado com educação, como descreve a regra 5.

### Proteções por provedor e por módulo (regra 15)

Fonte única: `docs/modules/provedores/evidencias.json` (estado, data, nota e números de referência de cada módulo em cada
provedor). Tudo o que depende dela é gerado por `scripts/update_protections.py`: a matriz `docs/modules/paridade_provedores.md`,
a seção "Provedores" do README de cada módulo e a tabela de estado da ficha de cada provedor (`docs/modules/provedores/`).
Depois de testar um provedor em um módulo, na mesma entrega:

1. `scripts/record_provider_contract.py --provider <provedor>` grava o contrato real (texto, fluxo e ferramenta) e
   `--check` acusa mudança de formato da API; os testes de contrato (`tests/backend/unit/providers/`) partem da gravação.
2. `scripts/verify_live_modules_1_to_3.py --provider <provedor> --register` confere os cenários ao vivo contra os números do
   próprio provedor e registra os novos números quando tudo passa.
3. `scripts/update_protections.py set <provedor> <m1..m4> <PROVADO|PARCIAL|NÃO TESTADO> --nota "o que funcionou e o que falta"`.
4. A ficha do provedor é completada à mão (a de um provedor novo nasce com trechos "A PREENCHER" que reprovam a verificação).
5. `scripts/verify_all.py [--formats]` fica verde (suítes, lint, tipos, proteções em dia e formato da API) e o commit é feito.

O passo a passo para um provedor novo está em `docs/modules/provedores/_roteiro_para_novo_provedor.md`.

### Contrato de comportamento entre provedores (regras 2, 9 e 15)

O mesmo texto de regra pode ser lido de um jeito por um modelo e de outro por outro (caso real de 09/10/2026: pedida uma auditoria de
projeto, o Ollama chamava `analyze_page` e o Gemini auditava sozinho e escrevia "com base na análise especializada" sem ter
chamado ferramenta nenhuma). Divergência assim se trata em quatro camadas, nunca com texto ou ramo por nome de modelo; o detalhe
está em `docs/modules/contrato_de_comportamento.md`:

1. Regra escrita sem ambiguidade no `SYSTEM_PROMPT` (`backend/src/services/chat_runtime.py`): qual ferramenta, por quê e o que nunca fazer.
2. Contrato observável no `scripts/verify_live_modules_1_to_3.py`: cada cenário declara as ferramentas que devem e as que não devem ser
   chamadas (`must_call`, `must_not_call`), conferidas pelo fluxo de eventos, em qualquer provedor.
3. Verificação do harness para o que não pode depender do modelo (portão da auditoria em `chat_runtime.py`): se o classificador (IA)
   decidiu "auditoria" e o turno termina sem ferramenta de análise, a resposta é retida, a análise é pedida uma vez, e só se nenhuma
   ferramenta servir o próprio modelo diz que não houve especialistas. O harness confere um fato; o conteúdo continua sendo do modelo.
4. Ajuste específico de provedor somente no caminho daquele provedor em `run_agent.py` (formato do fluxo, nomes de uso, parâmetros
   recusados), e o contrato real dele gravado e conferido por `scripts/record_provider_contract.py`.

Regra para todo defeito que aparecer só em um provedor ou modelo: provar a causa (regra 17), corrigir na camada certa, escrever o teste
e acrescentar o cenário ao contrato.

## Decisões do dono de 20/out/2026 para este projeto

- Analisar uma pasta inteira envia os arquivos compatíveis ao provedor de IA sem aviso antes: a pessoa escolheu a pasta, então sabe (decisão do dono).
- O VPAT e os relatórios exportados saem sem faixa de aviso no documento (decisão do dono); o aviso de que nenhum achado não é certificação continua valendo na conversa.
- Rodar no computador da pessoa a suíte de testes gerada (Cypress, Selenium, Newman) segue a chave de aprovação: ligada mostra o que vai instalar e rodar e pede; desligada instala e roda sozinho.
- O painel de memória do chat sai (ver rules/aprendizado.md).

## Decisão do dono de 21/out/2026: o agente é autônomo (a mesma do Agentic)

- O agente de IA deste projeto é livre quanto à estratégia: se ajusta sozinho, aprende com os erros e se corrige, resolve os laços e os erros por dentro e fica cada vez mais estratégico e independente. O dono já repetiu isto muitas vezes: está escrito aqui e no `CLAUDE.md`.
- Ordem diante de um laço ou de um erro, sempre nesta ordem: (1) o harness informa ao modelo apenas o fato (o que se repetiu e que nada de novo veio), sem dizer o que fazer; (2) o raciocínio sobe e o roteador leva a chamada para outro modelo, não o que travou; (3) o modelo muda de caminho por conta própria e aprende com o erro; (4) só se nada mudou depois disso, a rede de segurança da regra 8 encerra com entrega parcial honesta. O encerramento é o último recurso, deve ser muito raro, e cada vez que acontece é um sintoma a investigar.
- Nenhum determinismo dita estratégia (regras 1 e 2): nem texto pronto dizendo ao modelo o que fazer, nem lista de passos. Todo laço novo nasce com um teste em que o laço se resolve sozinho antes de ser encerrado e outro em que a IA diz sempre "siga" e ele ainda assim termina.
- O código deste projeto ainda não obedece em tudo: conferir o que cada laço faz hoje e registrar a diferença como pendência com o item nomeado, em `docs/PENDENCIAS.md`.
- Respostas do dono às perguntas de cenário sobre a autonomia (21/out/2026): (1) antes de a rede de segurança encerrar, o agente replaneja uma vez, descarta o plano atual e monta outro com o que já aprendeu; só se o segundo plano também não sair do lugar a rede encerra; (2) o outro modelo que a repetição chamou fica na tarefa só enquanto o trabalho estiver travado, e o roteador volta a escolher pela evidência e pela dificuldade assim que o trabalho volta a andar; (3) numa chamada ao modelo que demora muito, a pessoa ouve uma frase curta e calma, uma vez só ("o modelo está demorando para responder, continuo esperando"), a espera segue como a regra 8 manda e nenhuma chamada nova é aberta por cima; (4) quando o agente sai sozinho de uma repetição, a lição é guardada em silêncio, por dentro, como o resto do aprendizado (sem aviso e sem tela).
- Chamada ao modelo travada (resposta do dono, 21/out/2026, depois da pesquisa de recuperação de laços): a regra de esperar a mesma chamada vale para a conexão VIVA e lenta (chegam dados, ou o provedor está processando). Para a conexão MORTA (aberta, mas nenhum dado chega há muito tempo, enquanto o mesmo provedor responde rápido a outras chamadas), o agente detecta a falta de sinal da conexão, descarta aquela chamada e refaz a mesma pergunta em outro modelo do mesmo provedor pelo Auto, e a pessoa ouve uma frase calma ("o modelo não respondeu, troquei de modelo"). O que se mede é a inatividade da conexão (primeiro dado, intervalo entre pedaços), nunca o tempo da tarefa (regra 8). Isto ajusta a resposta anterior do mesmo dia, de só esperar.

## Como o dono usa e prova o Agentic (resposta do dono, 21/out/2026)

- Hoje só o Ollama funciona. O dono usa o Auto do Ollama para testar todos os modelos ao mesmo tempo, ver o que cada um entrega (thinking e demais capacidades) e corrigir direto e ao vivo. Toda prova ao vivo roda no Auto do Ollama; o que é de outro provedor fica pronto e testado em unidade, e é provado quando o crédito voltar.
- Thinking automático no roteador: mínimo, médio, alto ou máximo conforme a tarefa e conforme o que cada modelo oferece; o mesmo vale para as outras capacidades. A escolha da pessoa, quando existe, vale. Conferir ao vivo que cada modelo recebe só o nível que ele oferece.

## O agente checa, testa e corrige a si mesmo para tudo (decisão do dono, 21/out/2026)

- Achar a causa de uma falha na própria execução, mudar de caminho e corrigir o resultado é trabalho do agente, e não de quem desenvolve: o harness informa o fato, o raciocínio sobe, o roteador tenta outro modelo, o agente recomeça uma vez e aprende com o erro, em silêncio.
- Quem desenvolve, diante de qualquer falha, pergunta que mecanismo faltou para o agente ter achado e corrigido aquilo sozinho, e constrói esse mecanismo. O conserto à mão é só o passo para provar o mecanismo, e a entrega diz o que o agente já faz sozinho e o que ainda falta.
