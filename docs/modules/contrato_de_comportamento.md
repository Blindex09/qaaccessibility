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
