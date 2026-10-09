# Paridade entre provedores

Atualizado em 09/10/2026. Todas as regras do CLAUDE.md valem para todos os provedores (OpenAI, Anthropic, Gemini, xAI,
Ollama, Factory, OpenCode Go e o modo automático). Um módulo só está pronto para um provedor quando o que ele promete foi
provado ao vivo naquele provedor. Este arquivo mostra o que está provado em cada um e o que falta, para ninguém precisar
adivinhar nem refazer trabalho.

## Matriz

Legenda: PROVADO = testado ao vivo pela interface e documentado. PARCIAL = feito em parte. NÃO TESTADO = ainda não.

| Módulo | Ollama Cloud (Alto) | Gemini (Alto) | OpenAI | Anthropic | xAI | Factory |
|---|---|---|---|---|---|---|
| 1 Conversa, triagem e roteamento | PROVADO (07 e 08/10) | PROVADO (09/10) | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO |
| 2 Auditoria de URL e especialistas | PROVADO (08/10) | PROVADO em um cenário (09/10) | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO |
| 3 Código, anexos, ZIP, projeto local | PROVADO (08/10) | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO |
| 4 Documentos e imagens | PARCIAL (preparado sem modelo) | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO | NÃO TESTADO |

O Ollama Cloud está sem cota (limite semanal) desde 08/10, então depois das mudanças feitas em 09/10 ele só foi conferido por
teste automático e pela troca de provedor, não por uma resposta real. Veja `regressao_ollama_modulos_1_a_3.md`.

## Números medidos no Gemini (09/10/2026, gratuito, tudo no gemini-3.5-flash-lite escolhido pelo roteador)

| Cenário | Gemini | Ollama Cloud (medido antes) |
|---|---|---|
| Pergunta curta sobre o critério 1.4.3 | 18.738 tokens, 6 chamadas, 18 s | de 17.590 a 25.335 tokens |
| Pedido fora do nicho, como primeira mensagem (tom descontraído acompanhado) | 1.797 tokens, 1 chamada, 3 s | cerca de 2.000 tokens, 1 chamada |
| Pedido vago, como primeira mensagem | 1.740 tokens, 1 chamada, 3 s | cerca de 2.000 tokens, 1 chamada |
| Auditoria da página com erros do W3C | 148.683 tokens, 18 chamadas, 87 s, 7 especialistas | de 151.771 a 211.063 tokens, de 80 a 259 s |

Observações do Gemini: o fora do nicho como segunda mensagem da conversa custou 14.623 tokens em 4 chamadas, porque o atalho
barato só vale na primeira mensagem (desenho do módulo 1, igual para qualquer provedor). Alguns especialistas escreveram a
descrição em inglês (já acontecia no Ollama Cloud) e a resposta final não trouxe o rótulo de nível de evidência nesta rodada.

## Defeitos que só apareceram no Gemini, e a causa de cada um (regra 17)

1. Todo fluxo falhava com "Gemini encerrou o stream sem interaction.complete". Causa provada por chamada real: a API atual
   envia `interaction.completed` (com d), os trechos de texto vêm em `step.delta` e o evento final não traz o conteúdo da
   resposta. O leitor foi escrito para o formato antigo (`interaction.complete`, `content.delta`) e os testes antigos usavam esse
   mesmo formato inventado, então passavam. Correção: lê os dois formatos, e depois do fluxo busca a interação guardada
   (`store=True`) para ler a resposta e as chamadas de ferramenta. Testes novos usam os eventos gravados de uma chamada real.
2. O custo do Gemini aparecia como zero. Os nomes de uso da API atual são `total_input_tokens` e `total_output_tokens`. Agora
   são lidos (o custo é medido por tipo de chamada, regra 9).
3. Um modelo (o alias gemini-flash-latest) recusou o nível de raciocínio mínimo com erro 400. Agora o sistema aprende com a
   recusa do próprio provedor e refaz a chamada sem esse parâmetro, sem lista fixa de modelos.
4. A contingência do roteador repetia o modelo que acabara de estourar a cota, esperando mais 3 minutos (corrigido, vale para
   todo provedor).
5. A tela não mostrava que o provedor estava limitando o ritmo (corrigido, vale para todo provedor).
6. O erro 403 de chave bloqueada por vazamento aparecia como "verifique as permissões" (corrigido, vale para todo provedor).
7. O cofre guardava uma só chave de IA e trocar de provedor apagava a anterior (corrigido: uma chave por provedor).

## Como evitar retrabalho com os próximos provedores

1. Antes de testar um provedor, gravar uma chamada real dele (texto, fluxo e ferramenta) e escrever os testes em cima do que
   ele de fato devolve. Mock inventado não prova integração (regra 11): foi exatamente o que escondeu o defeito 1.
2. Código específico de um provedor fica dentro do caminho daquele provedor em `run_agent.py`. Mudança em arquivo
   compartilhado exige a suíte completa e, havendo cota, o script ao vivo no Ollama Cloud.
3. Conferir o provedor com `scripts/verify_live_ollama_modules_1_to_3.py --provider <provedor>` (os fatos objetivos reprovam,
   o custo é só informado ao lado do medido no Ollama) e registrar o resultado na matriz acima.
4. Um provedor só entra na matriz como PROVADO depois da interface real, não só do script.

## Pendências

- Módulo 3 e módulo 4 no Gemini, e os quatro módulos nos outros provedores: faltam chaves e cota.
- Rodada de conferência no Ollama Cloud assim que a cota voltar.
- Descrições dos especialistas em inglês: vale para todos os provedores, pertence ao módulo 2.
