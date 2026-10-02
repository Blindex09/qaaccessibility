# E2E real da interface — Ollama Cloud

Data: 2026-09-30. Interface no Chrome: http://localhost:19006/.
Backend reiniciado com o código atual em 127.0.0.1:8001, sem abrir janela
de terminal. Provider Ollama Cloud, modelo Alto, aprovação ligada; chave já
salva reutilizada, sem revelar ou alterar seu conteúdo. Interações pela UI,
sem mocks e sem invocar diretamente a API de auditoria.

## Cenários executados

1. Pedido: “Quero avaliar a acessibilidade de um site.”
   Resposta em aproximadamente 27 s: “Claro! Qual é a URL do site que você
   gostaria que eu avaliasse quanto à acessibilidade?”
2. Continuação: https://example.com/, somente homepage desktop, WCAG 2.2,
   sem mudanças, distinguindo evidências de limitações.
3. Durante a execução: enviado redirecionamento para manter somente aquela
   URL e distinguir o que realmente foi verificado. A UI mostrou Redirecionar
   e o servidor respondeu 200 a POST /chat/steer. Aplicação da instrução pelo
   agente principal não comprovada, pois ele não chegou à auditoria.
4. Navegação por setas: ArrowUp no item atual de Product Owner moveu o foco
   ao item anterior da mesma lista da squad. Itens de progresso tinham
   role=listitem, tabindex=0 e não tinham aria-live. Não foi usado NVDA real;
   isso comprova DOM/foco, não comportamento completo de leitor de tela.
5. Após cerca de cinco minutos sem análise do site, cancelamento pela UI.
   Tempo final exibido: 308 s. POST /chat/cancel retornou 200, controles do
   chat foram restabelecidos, mensagens e planejamento parcial permaneceram.

## Resultado contra CLAUDE.md

| Regra | Evidência | Resultado |
| --- | --- | --- |
| Ambiguidade material pede esclarecimento | Perguntou a URL, sem inventar site | Passou neste cenário |
| Continuação em contexto prossegue | Segunda mensagem classificada analyze_url; squad iniciou | Parcial: não chegou à auditoria |
| IA escolhe modelos no Alto | Logs RouteAdvisor source=ia, modelos diferentes por etapa | Passou no caminho observado; não prova ausência de regras fixas em todo o sistema |
| Economia proporcional | Três candidatos e juiz para o clarifier, repetidos após JSON truncado; julgamento também no planejamento | Problema: muito trabalho antes de acessar uma página simples |
| Progresso sem silêncio longo | Durante triagem, apenas mensagem inicial até cerca de 124 s; PO/Tech Lead depois emitiram início e conclusão | Falhou no trecho de triagem/julgamento |
| Progresso em linguagem natural | Texto contextual de PO/Tech Lead, sem JSON ou stack trace nessas etapas | Passou no trecho observado |
| Setas sem anúncios automáticos do progresso | Lista da squad navegável; itens sem aria-live | Passou no DOM/foco; NVDA não testado |
| Redirecionamento sem perder progresso | UI alterou botão, endpoint aceitou e conteúdo permaneceu | Parcial: consumo da instrução não comprovado |
| Cancelamento determinístico | UI voltou a aceitar entrada; cancel aceito; nenhuma nova etapa observada após cancel | Passou para interface; encerramento de HTTP já em thread não comprovado |
| Entrega parcial honesta | Não afirmou auditoria concluída; mas não mostrou resumo final de cancelamento/limitações | Lacuna de comunicação no cancelamento |
| Deadline único adaptativo | Duas tentativas de clarifier e múltiplas fases somaram vários minutos | Não demonstrado no turno completo; requer verificação do orçamento agregado |
| Evidências WCAG e erros de acesso em linguagem natural | Nenhuma ferramenta de análise de site executada | Não coberto |
| Sandbox, credenciais mínimas, comandos/caminhos e aprovação destrutiva | Nenhuma ação destrutiva ou execução de código solicitada | Não coberto por este teste |

## Evidências e limites

Logs desta execução: `logs/backend-e2e-router.stdout.log` e
`logs/backend-e2e-router.stderr.log`. Contagem até a interrupção: 26 registros
de POST https://ollama.com/api/chat nos dois cenários; sete registros de
RouteAdvisor; zero registros de analyze_page/analyze_site. Isto é contagem de
chamadas observadas, não medição de tokens, cobrança ou execução do provedor.

O clarifier usou comparação e julgamento duas vezes após saída truncada.
Julgamentos de Product Owner e Tech Lead ficaram indisponíveis e preservaram
a primeira resposta. PO concluiu escopo somente leitura da homepage; Tech
Lead concluiu abordagem; Engineering Manager começou ao cancelar.
Não houve relatório de auditoria. O alvo é uma URL pública real, mas sua
acessibilidade não foi efetivamente avaliada nesta execução.

Capturas em `artifacts/e2e-ollama-2026-09-30/`: `progresso.jpg`,
`espera-5min.jpg`, `cancelado.jpg`. A primeira resposta exibiu 27 s, mas depois
passou a exibir 1 s ao iniciar o turno seguinte; inconsistência visual registrada.

Conclusão: **teste de auditoria não concluído; cobertura parcial das regras**.
Interrupção foi do avaliador, para limitar gasto após cinco minutos de
planejamento — não foi um timeout natural comprovado do sistema. Não houve
mudança no código da aplicação neste teste. A conversa de teste ficou aberta.
