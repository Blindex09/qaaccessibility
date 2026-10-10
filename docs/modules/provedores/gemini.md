# Ficha do provedor: Gemini

Atualizado em 09/10/2026. Provedor `gemini`, modelo Alto (roteador escolhe entre os modelos do catálogo). Testado ao vivo pela
interface com uma chave do nível gratuito.

## Como o produto fala com o Gemini

- API de Interações (`client.interactions.create`), SDK `google-genai` 2.20.0, com `store=True` (o servidor guarda a interação).
  Código: `run_agent.py`, `_run_gemini` e `_gemini_interactions_create`.
- Modelos que o catálogo oferece ao roteador: gemini-3.1-flash-lite, gemini-3.5-flash, gemini-3.6-flash, gemini-3.5-flash-lite,
  gemini-flash-latest e gemini-flash-lite-latest. Em todas as medições o roteador escolheu o gemini-3.5-flash-lite, inclusive
  para a auditoria completa.
- Formato do fluxo (gravado de uma chamada real em `tests/backend/fixtures/providers/gemini/contract.json`): `interaction.created`,
  `interaction.status_update`, `step.start`, `step.delta` (tipos `text`, `arguments_delta` e `thought_signature`), `step.stop` e
  `interaction.completed`. O evento final traz status e uso de tokens, mas não o conteúdo: a resposta e as chamadas de ferramenta
  vêm de `client.interactions.get(id=...)`, nos passos `model_output` e `function_call`. `arguments` chega como dicionário.
- Uso de tokens: `total_input_tokens`, `total_output_tokens`, `total_thought_tokens`, `total_tokens`.

## O que funciona (provado ao vivo, 09/10/2026)

| Módulo | Cenário | Resultado |
|---|---|---|
| 1 | Pergunta curta (critério 1.4.3) | 18.738 tokens, 6 chamadas, 18 s, resposta correta em duas frases |
| 1 | Fora do nicho como primeira mensagem | 1.797 tokens, 1 chamada, 3 s, recusa educada no tom descontraído da pessoa |
| 1 | Pedido vago como primeira mensagem | 1.740 tokens, 1 chamada, 3 s, pergunta específica |
| 2 | Auditoria da página com erros do W3C | 148.683 tokens, 18 chamadas, 87 s, 7 especialistas, 11 achados corretos, sem emoji nem tabela |
| 3 | ZIP da loja anexado pela interface, pedido arquivo por arquivo | 52.643 tokens, 9 chamadas, 35 s, sem especialistas; 9 dos 10 defeitos conhecidos (faltou a página sem título). Pelo script oficial: 35.463 tokens, 8 chamadas, 29 s |
| 3 | Pasta local por caminho, só teclado, com cartão de aprovação | 36.843 tokens, 5 chamadas, 32 s; apontou só os dois defeitos de teclado (botão feito de div e foco removido), dentro do escopo |
| 3 | Componente React anexado, pedindo o código corrigido | 26.228 tokens, 5 chamadas, 19 s; bloco de código com botão de copiar, sem emoji nem tabela |

## O que não foi testado ainda

Módulo 4 (documentos e imagens). Imagem anexada (o Gemini aceita imagem, não verificado). Cancelamento no Gemini. Projeto grande
(limites de 30 arquivos e 100 mil caracteres do ZIP) e correção de arquivos locais (módulo 5).

## Particularidades e defeitos já resolvidos (cada um com a causa provada)

1. O leitor do fluxo esperava `interaction.complete` e `content.delta` (formato antigo); a API envia `interaction.completed` e
   `step.delta`. Corrigido: lê os dois, busca a interação guardada para ler a resposta. Testes de contrato com a gravação real.
2. Custo aparecia zero: os nomes de uso eram outros. Corrigido.
3. O alias `gemini-flash-latest` recusa o nível de raciocínio mínimo com erro 400. O sistema aprende com a recusa do próprio
   provedor e refaz sem o parâmetro.
4. Cota: o `gemini-3.6-flash` estourou a cota do projeto gratuito ("Your project has exceeded a quota") enquanto os modelos lite
   funcionaram. O SDK tenta de novo a cada 30 segundos, 8 vezes (cerca de 4 minutos) antes de desistir. A contingência do roteador
   agora lê a telemetria atual e deixa de repetir o modelo que acabou de falhar, e a tela mostra "Aguardando o provedor há Xs".
5. Chave bloqueada por vazamento: erro 403 "Your API key was reported as leaked". Agora a mensagem mostra o que o provedor disse.
   Uma chave que passou pelo chat ou por um repositório público deve ser trocada.
6. O alias `gemini-flash-latest` respondeu 503 de alta demanda em uma chamada direta (transitório).
7. Módulo 3, auditoria de projeto anexado sem especialistas. O Gemini auditava o ZIP sozinho (52 mil tokens), deixou passar a página
   sem `<title>`, errou um número de contraste (disse 1,45:1; o correto é 2,3:1) e, mesmo quando a pessoa pediu especialistas e
   revisão sênior, respondeu "com base na análise especializada" sem ter chamado nenhuma ferramenta. Causa provada: a regra 5 do
   prompt mandava "auditar imediatamente neste turno" sem citar a ferramenta, e os modelos do Ollama chamavam `analyze_page` por
   conta própria. Correções, iguais para todo provedor: (a) a regra 5 agora manda usar `analyze_page` (uma chamada para o projeto,
   com `--- caminho ---` antes de cada arquivo), proíbe dizer ou insinuar que houve especialistas sem chamar a ferramenta e proíbe
   número não medido; (b) verificação do harness: se o classificador decidiu que é auditoria e o turno termina sem ferramenta de
   análise, a resposta é retida, a análise é pedida uma vez, e só se nenhuma ferramenta servir (Word, PowerPoint, EPUB) o modelo
   diz com clareza que os especialistas não foram usados. Resultado ao vivo depois das correções: 10 de 10 defeitos conhecidos,
   contraste certo, 121.305 tokens, 20 chamadas, 117 s no pedido comum, e 136.642 tokens no pedido explícito de especialistas.
8. O Gemini às vezes responde com formatação crua (títulos e negrito); a tela remove a marcação, o texto bruto do fluxo não.

## Como repetir e conferir

- Chave: Configurações, provedor Gemini, modelo Alto (a chave fica no cofre, uma por provedor).
- Conferir o formato da API: `scripts/record_provider_contract.py --provider gemini --check` (acusa se a API mudou).
- Regravar depois de uma mudança de formato: o mesmo comando sem `--check`, atualizar o leitor e rodar
  `tests/backend/unit/providers/test_gemini_contract.py`.
- Cenários dos módulos 1 a 3: `scripts/verify_live_modules_1_to_3.py --provider gemini`.

## Pendências

Módulos 3 e 4 no Gemini; rodar o script ao vivo completo; medir o Gemini com um nível pago (a cota gratuita limita rodadas longas).

<!-- PROTECOES:ESTADO:INICIO -->
Estado por módulo (gerado de `evidencias.json` por `scripts/update_protections.py`, não editar a mão):

| Módulo | Estado | Data | Nota |
|---|---|---|---|
| 1 Conversa, triagem e roteamento | PROVADO | 09/10/2026 | pergunta curta, fora do nicho e pedido vago ao vivo, com custo igual ao do Ollama |
| 2 Auditoria de URL e especialistas | PROVADO | 09/10/2026 | pela tela: auditoria da página com erros do W3C em 137 s e 127.556 tokens, 18 chamadas, achados corretos sem emoji nem tabela. Pelo script mais 3 cenários (pedido estreito, página acessível, URL inexistente). Pendências: a contagem de achados da resposta não bateu com a lista (disse 8 e listou 7) e a abertura 'Olha,' é casual para uma pergunta neutra |
| 3 Código, anexos, ZIP e projeto local | PROVADO | 09/10/2026 | ZIP, pasta local com aprovação e componente anexado ao vivo; auditoria de projeto passa pelos especialistas e pela revisão sênior depois da verificação comum a todos os provedores (antes o Gemini auditava sozinho) |
| 4 Documentos e imagens | PARCIAL | 09/10/2026 | pela tela, o Word anexado expôs um defeito real (o anexo chegava como base64 cru ao classificador, ao reranqueador e à squad, 45 a 71 mil tokens de entrada cada), corrigido com teste de regressão. O Word corrigido foi reenviado pela tela, mas a cota diária gratuita do Gemini esgotou (429, volta em cerca de 21 horas) antes de terminar. Faltam pela tela: Word corrigido, PDF, Excel, PowerPoint, EPUB, imagem e arquivo corrompido |

Números de referência dos cenários ao vivo (base do script `verify_live_modules_1_to_3.py` para este provedor):

- m1-pergunta-curta: 22469 tokens (medido em 09/10/2026)
- m1-fora-do-nicho: 1790 tokens (medido em 09/10/2026)
- m1-pedido-vago: 1802 tokens (medido em 09/10/2026)
- m2-url-com-erros: 133522 tokens (medido em 09/10/2026)
- m3-zip-anexado: 133221 tokens (medido em 09/10/2026)
- m3-projeto-local: 36843 tokens (medido em 09/10/2026)
- m3-componente-anexado: 26228 tokens (medido em 09/10/2026)
- m3-zip-pede-especialistas: 159900 tokens (medido em 09/10/2026)
- m1-tom-descontraido: 17867 tokens (medido em 09/10/2026)
- m1-tom-formal: 17693 tokens (medido em 09/10/2026)

Contrato real gravado: `tests/backend/fixtures/providers/gemini/contract.json`.
<!-- PROTECOES:ESTADO:FIM -->

## Rodada pela tela do navegador (09/10/2026, noite)

Feita no navegador, na interface de chat, com o provedor Gemini no modo Alto, anexando arquivos pelo mesmo campo do botão "Anexar arquivos".

- Módulo 2, auditoria de URL: 137 s, 127.556 tokens, 18 chamadas, achados corretos, cabeçalho "qaaccessibility disse", sem asteriscos nem
  emoji nem tabela. Defeitos da resposta: a contagem não bateu (disse 8 problemas e listou 7) e a abertura "Olha," é casual para uma
  pergunta neutra.
- Módulo 3, ZIP da loja anexado: 7 dos 10 defeitos conhecidos (faltaram idioma, título da página e o salto de h1 para h4), sem número de
  contraste inventado. A resposta terminou com três ofertas e uma pergunta, quando a regra 19 pede uma só sugestão.
- Módulo 4, Word anexado: defeito real encontrado e corrigido. Pelo caminho da tela o anexo entra como anexo estruturado, e a extração do
  texto rodava antes de ele entrar na mensagem. O arquivo seguia como base64 cru (49.885 caracteres para um Word de 37 KB) para o
  classificador (70.861 tokens de entrada), o reranqueador (71.043) e cada papel da squad (cerca de 45 mil), e uma imagem anexada nunca
  chegava ao modelo. Depois da correção o classificador recebe 2.261 tokens. O script ao vivo não via isso porque embute o anexo no
  texto (outro caminho), o que prova que só a tela pega esse tipo de defeito. Teste de regressão: `TestStructuredAttachmentsAreExtracted`.
- A cota diária gratuita do Gemini (500 pedidos por dia para este modelo) esgotou antes de o Word corrigido terminar. O erro 429 traz
  "retry in 21h14m"; a tela ficou em "Processando" por mais de 3 minutos sem a linha de espera do provedor e sem explicar o limite. É
  pendência a tratar: um limite diário de horas não é limite de ritmo, e a pessoa precisa saber disso logo.
- Achado de interface fora do chat: a tela de Configurações mostra "**Hermes Agent**" com asteriscos crus e um nome antigo do produto.
