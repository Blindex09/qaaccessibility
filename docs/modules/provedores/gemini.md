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
7. Módulo 3: em um projeto pequeno o Gemini decide analisar direto no chat, sem convocar especialistas (52 mil tokens contra 160 a
   400 mil no Ollama). É mais barato, mas sem revisão sênior ele deixou passar a página sem `<title>` e, no componente, não avisou
   que um `<h3>` dentro de um `<button>` é HTML inválido (o Ollama avisou). Quem decide convocar especialistas é a IA, e esta
   diferença de rigor entre modelos fica registrada como observação, não como defeito do produto.

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
| 2 Auditoria de URL e especialistas | PARCIAL | 09/10/2026 | um cenário (página com erros do W3C): 148,7 mil tokens e 87 segundos, achados corretos |
| 3 Código, anexos, ZIP e projeto local | PROVADO | 09/10/2026 | ZIP, pasta local com aprovação e componente anexado ao vivo, com bloco de código e botão de copiar; ressalvas: um defeito conhecido não apontado (página sem título) e sem revisão sênior (o modelo analisou sem especialistas) |
| 4 Documentos e imagens | NÃO TESTADO | - | - |

Números de referência dos cenários ao vivo (base do script `verify_live_modules_1_to_3.py` para este provedor):

- m1-pergunta-curta: 18738 tokens (medido em 09/10/2026)
- m1-fora-do-nicho: 1797 tokens (medido em 09/10/2026)
- m1-pedido-vago: 1740 tokens (medido em 09/10/2026)
- m2-url-com-erros: 148683 tokens (medido em 09/10/2026)
- m3-zip-anexado: 35463 tokens (medido em 09/10/2026)
- m3-projeto-local: 36843 tokens (medido em 09/10/2026)
- m3-componente-anexado: 26228 tokens (medido em 09/10/2026)

Contrato real gravado: `tests/backend/fixtures/providers/gemini/contract.json`.
<!-- PROTECOES:ESTADO:FIM -->
