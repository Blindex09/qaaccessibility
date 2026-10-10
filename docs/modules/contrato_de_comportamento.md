# Contrato de comportamento: o mesmo resultado em qualquer provedor

Atualizado em 09/10/2026. Problema real: o mesmo texto de regra foi lido de um jeito pelos modelos do Ollama Cloud e de outro
pelo Gemini. Pedida uma auditoria de projeto, os modelos do Ollama chamavam a ferramenta de análise (com os especialistas e a
revisão sênior) e o Gemini auditava sozinho, e ainda escreveu "com base na análise especializada" sem ter chamado nada. Nenhum
dos dois estava "errado" segundo o texto antigo: o texto era ambíguo. Como isso não deve gerar retrabalho a cada provedor ou
modelo novo, o comportamento é tratado em camadas, da mais barata à mais firme.

## As quatro camadas

1. Regra escrita sem ambiguidade (`SYSTEM_PROMPT` em `chat_runtime.py`). Cada regra diz qual ferramenta, por que, o que nunca
   fazer e o que fazer na exceção. Sem nome de modelo e sem ramo por provedor: o mesmo texto para todos. Isto reduz a chance de
   o modelo divergir, mas não a elimina (o Gemini ignorou a frase "nunca diga que houve especialistas" uma vez).
2. Contrato observável, verificado por fatos (`scripts/verify_live_modules_1_to_3.py`). Cada cenário declara quais ferramentas
   devem ou não ser chamadas (`must_call`, `must_not_call`), além de custo, emoji, tabela e erro. Os fatos vêm do fluxo de
   eventos, não da opinião de ninguém. Rodar o mesmo script em outro provedor mostra na hora onde ele diverge.
3. Verificação do harness para o que não pode depender do modelo (regra 1: a IA decide, o código confere fatos). Exemplo: o portão
   da auditoria. Se o classificador (IA) decidiu "auditoria" e o turno termina sem ferramenta de análise, a resposta é retida, a
   análise é pedida uma vez e, só se nenhuma ferramenta servir, o próprio modelo diz que não houve especialistas. Foi a única
   forma de garantir que uma afirmação falsa nunca chegue à tela, em qualquer modelo.
4. Ajuste específico de provedor só na camada do provedor (`run_agent.py`, no caminho daquele provedor): formato do fluxo, nomes de
   uso de tokens, parâmetros que o provedor recusa. Nunca no texto compartilhado, e nunca por nome de modelo.

## Contrato atual dos cenários (módulos 1 a 3)

| Cenário | Deve chamar | Não deve chamar |
|---|---|---|
| m1 pergunta curta | nada | analyze_page, analyze_site, run_deep_research |
| m1 fora do nicho, m1 pedido vago | nada (resposta em 1 chamada) | ferramentas de análise |
| m2 auditoria de URL | analyze_page | |
| m3 ZIP anexado | analyze_page | unzip_and_list_files |
| m3 ZIP pedindo especialistas e revisão sênior | analyze_page | |

## Quando um modelo ou provedor divergir

1. Rodar o script no provedor e ler qual item do contrato reprovou.
2. Provar a causa (regra 17): o texto da regra é ambíguo? O modelo ignorou uma regra clara? É formato do provedor?
3. Corrigir na camada certa: texto ambíguo vira texto claro para todos; regra clara ignorada pede verificação do harness;
   formato do provedor fica no adaptador dele. Escrever o teste de regressão e acrescentar o cenário ao contrato.
4. Registrar na ficha do provedor (`provedores/<provedor>.md`) o que divergiu, a causa e a camada da correção.

Um contrato novo nunca é uma lista de palavras proibidas nem uma decisão fixa sobre intenção: ele só confere fatos observáveis do
turno (ferramenta chamada ou não, evento, custo), e o que o modelo escolhe dizer continua sendo dele.

## O que o contrato de fatos não vê, e como passa a ser conferido (09/10/2026)

O contrato de fatos (ferramentas, custo, emoji, tabela, erro de extração, fim da resposta) não via quatro coisas. Cada uma agora tem
uma conferência, e a regra 2 manda separar fato de julgamento:

1. Ausência de repetição: é um fato (o mesmo trecho de pelo menos 8 palavras aparece duas vezes). Conferido pelo código
   (`repeated_passages` em `scripts/behavior_judge.py`), em todo cenário.
2. Cabeçalho da resposta: é da interface, não do modelo. O H2 de cada resposta é "qaaccessibility disse" (neste projeto o nome do
   produto, como "Blind disse" no Agentic). Conferido pelo teste do front `ChatScreen.liveRegion.test.tsx`, que antes aceitava só
   "qaaccessibility" (sem o "disse"); a tela e o teste foram corrigidos.
3. Tom da pessoa: é julgamento. Quem confere é um juiz de IA separado de quem respondeu (de outro provedor quando houver chave; só se
   nenhum outro responder usa o mesmo, e o script avisa que a independência é menor). O juiz recebe o pedido e a resposta, devolve
   um veredito em JSON validado por contrato (se o formato falha, uma nova tentativa, e depois "juiz falhou", nunca aprovado em
   silêncio). Registro, e não comprimento ou estrutura de um relatório pedido, é o critério. Há cenários com pessoa descontraída e
   pessoa formal.
4. Qualidade dos achados: o projeto de teste (ZIP da loja) tem 10 defeitos conhecidos (`KNOWN_DEFECTS`). O juiz diz quais a resposta
   trouxe, quais faltaram e se há afirmação falsa. Afirmação falsa reprova. Cobertura é comparada com a cobertura medida antes DESTE
   provedor (registrada com `--register`); sem referência, só é informada, porque não existe número certo embutido no código.

Medido no Gemini (gemini-3.5-flash-lite, juiz no mesmo provedor porque a cota do Ollama Cloud está esgotada): tom conferido em
todos os cenários, 8 de 10 e 9 de 10 defeitos conhecidos cobertos nos dois cenários do ZIP. O defeito heading-skip (h1 para h4)
faltou em todas as execuções do ZIP, o que indica uma lacuna real a investigar no que chega à resposta final (não está provado se
a falha é do especialista ou do resumo).

Achados reais desta rodada, com a camada em que foram tratados:

- Resposta vazia (Gemini devolveu "concluído" com zero tokens de saída, e a pessoa recebia nada). Causa NÃO provada: o log não
  guardava status nem passos. Agora o log registra os dois quando a resposta vem vazia, e o chat repete o turno uma vez quando não há
  texto nem ferramenta (fato objetivo), somando o custo. Teste de regressão: `TestEmptyProviderAnswer`.
- "Em duas frases": o modelo acrescentava uma terceira frase de sugestão (regra 19 do prompt). A regra agora diz que um limite de
  tamanho pedido pela pessoa é rígido e que a sugestão não vale para resposta conceitual.

Limites honestos: o juiz também é um modelo e varia (o mesmo cenário foi reprovado e aprovado em execuções diferentes antes de o
critério de registro ser esclarecido); por isso falha de tom é lida, não decidida às cegas. A independência do juiz depende de ter
chave de outro provedor com cota. Não foi rodado no Ollama Cloud (cota semanal esgotada).
