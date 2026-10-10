# Ficha do provedor: Ollama Cloud

Atualizado em 09/10/2026. Provedor `ollama-cloud`, modelo Alto com roteador inteligente. É o provedor em que os módulos 1, 2 e 3
foram provados ao vivo (07 e 08/10/2026).

## Como o produto fala com o Ollama Cloud

- API nativa `/api/chat` pela biblioteca `ollama` (`run_agent.py`, `_run_ollama_native`), com fluxo, `think` (nível de raciocínio)
  e saída restrita por esquema JSON. O endpoint compatível com OpenAI (`/v1`) fica só como reserva: tem defeito conhecido de
  chamada de ferramenta.
- Catálogo descoberto pelo adaptador `ollama_cloud_adapter.py` (17 modelos em 08/10/2026), com telemetria de confiabilidade e
  latência observadas (`model_reliability.py`).
- Uso de tokens: `prompt_eval_count` e `eval_count`, no último pedaço do fluxo.

## O que funciona (provado ao vivo)

| Módulo | Resultado resumido | Documento |
|---|---|---|
| 1 Conversa, triagem e roteamento | pergunta curta de 25 para cerca de 17,6 mil tokens; fora do nicho e pedido vago em 1 chamada de cerca de 2 mil tokens; pesquisa profunda de 790 mil para 63 mil tokens; tom acompanha a pessoa | `chat_triagem_roteamento.md` |
| 2 Auditoria de URL | página com erros do W3C de 594 mil tokens e 28 minutos para cerca de 150 a 210 mil tokens e 80 a 260 segundos | `auditoria_url_especialistas.md` |
| 3 Código, anexos, ZIP | ZIP extraído pelo sistema, projeto local por caminho com aprovação, bloco de código com botão de copiar; custo de 159 a 406 mil tokens conforme o modelo escolhido | `codigo_anexos_zip.md` |
| 4 Documentos e imagens | preparado sem o modelo; testes ao vivo pendentes | `documentos_imagens.md` |

## Particularidades e defeitos já resolvidos

1. Limite semanal de uso: depois de muitos testes, a conta responde 429 "you have reached your weekly usage limit". Atingido em
   08/10/2026 e ainda atingido em 09/10 às 19h. Bloqueia testes ao vivo até renovar ou entrar crédito.
2. Raciocínio no nível médio é imprevisível (de 1,1 mil a 4,2 mil tokens na mesma revisão curta, chegando a dezenas de milhares em
   revisões grandes); só "não pensar" é previsível. Complexidade baixa do roteador significa nenhum raciocínio extra.
3. Uma conexão respondeu 200 e ficou muda por mais de 10 minutos; o limite de leitura agora é a janela de silêncio do turno.
4. Uma chamada de especialista ficou 29,7 minutos presa sem erro. Hipótese: geração sem fim em espaços sob saída restrita por
   esquema JSON. Proteções: só conta como progresso enquanto chega dado, fluxo degenerado é encerrado, e a chamada longa deixa
   diagnóstico no log. A causa continua sendo hipótese (regra 17).
5. O modelo kimi-k2.6 é lento (100 a 230 s por chamada) e gasta muito em saída; o roteador passou a escolher por custo observado.
6. O Ollama reaproveita um pouco do início do prompt de forma automática (primeira palavra em 0,66 a 1,08 s contra 1,03 a 1,25 s),
   sem opção para forçar; o provedor sempre informa o tamanho total do prompt.
7. Erro de ferramenta aparecia como "modelo não encontrado"; resolvido (vale para todo provedor).

## Como repetir e conferir

- Conferir cota: uma chamada mínima (`credit_probe`) devolve 429 enquanto o limite estiver atingido.
- Cenários dos módulos 1 a 3: `scripts/verify_live_modules_1_to_3.py` (padrão é este provedor; troca sozinho e restaura).
- Mapa de proteção: `docs/modules/regressao_ollama_modulos_1_a_3.md`.

## Pendências

- Gravar o contrato real do provedor: `scripts/record_provider_contract.py --provider ollama-cloud` (precisa de cota). Os testes
  atuais do Ollama usam objetos que imitam o formato nativo, que já foi usado em produção nos módulos 1 a 3.
- Rodada de conferência dos módulos 1 a 3 depois das mudanças de 09/10, quando a cota voltar.
- Módulo 4 ao vivo.
