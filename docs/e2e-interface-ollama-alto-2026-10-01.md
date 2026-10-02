# E2E real via interface — Ollama Cloud no modo Alto (2026-10-01)

## O que foi rodado

Teste E2E real, ao vivo, pelo navegador (interface web em `http://127.0.0.1:3000`,
proxy local encaminhando ao backend `127.0.0.1:8001`). Configuração feita pelas
telas do produto, não por variáveis de ambiente:

- Provider: **Ollama Cloud** (`ollama-cloud`)
- Modelo: **Alto — seleção dinâmica para cada tarefa** (roteamento automático,
  nenhum modelo concreto fixado)
- Chave do provider informada pela UI e guardada via
  `POST /settings/` (log: `Provider=ollama-cloud, Model=alto`)
- Chave Tavily também registrada pela UI para pesquisa no chat

## Passo a passo executado

1. `python start_backend.py` — backend na porta 8001 (PID 8688). `/health` 200.
2. `python start_frontend.py` — gerou `web/web-build` (Expo export:web) e subiu
   `web/proxy-server.js` na porta 3000.
3. Interface aberta no navegador: `QA Accessibility — Assistente`.
4. Tela **Configurações**: provider trocado para Ollama Cloud, chave colada,
   modelo `Alto` selecionado no dropdown, `Salvar Configurações de IA`.
   O dropdown de modelos listou o catálogo dinâmico em tempo real
   (`GET /models` — 9s, catálogo descoberto ao vivo: 16 modelos).
5. No chat, mensagem em linguagem natural:
   "Faça uma auditoria de acessibilidade completa da página
   https://example.com. Informe o score, os problemas encontrados com
   severidade e as recomendações principais."
6. O assistente rodou o turno completo em 130 s e respondeu na conversa.

## Resultado observado na interface (linguagem natural, não um JSON seco)

- **Andamento da squad** no feed: Tech Lead definiu a estratégia técnica;
  QA Lead definiu o plano de evidências e a régua de aceite. Depois:
  a11y-analysis (a11y_specialist) -> done.
- Feed de progresso estruturado: 19 especialistas de acessibilidade
  (`19 de 19 análises recebidas`), achados preliminares anunciados com
  "ainda sujeito à revisão", revisão especializada
  (`removendo falsos positivos e repontuando`), verificação
  determinística de contraste e `Auditoria concluída`.
- Resposta final: **score 73**, resumo de severidade (0 críticos, 0 altos,
  5 médios, 1 baixo), problemas principais (ausência de H1, falta de
  landmarks/skip link, link genérico "Learn more", opacidade de ícones SVG)
  com critérios WCAG e recomendações de correção. Oferta de correção +
  download no final.

## Evidência de roteamento do modo Alto (logs do backend)

- RouteAdvisor (decisão da IA, source=ia) tomou **29 decisões** no turno;
  **28 delas** escolheram `gemma4:31b` e **1** escolheu
  `deepseek-v4.1-flash` (análise AJAX em página simples). Nenhum modelo
  concreto foi imposto — todas as escolhas partiram do classificador com
  justificativa registrada (ex.: `reason=A tarefa exige ... O modelo
  gemma4:31b apresenta a maior confiabilidade observada...`).
- `[Effort]` mapeou tradeoff por papel: `squad_tech_lead`/`squad_qa_lead`
  `tradeoff=3 -> reasoning_effort=medium`; `clarifier`/`classifier`
  `tradeoff=9 -> reasoning_effort=none` (tarefas rápidas, sem raciocínio
  longo — economia sem perder precisão).
- **Julgamento entre modelos**: em todas as 29 decisões a IA registrou
  `comparison=[]` — nenhuma comparou candidatos nesta rodada
  (`a11y_model_arbitration_enabled=True` por padrão; a IA julgou que o custo
  extra não valia para estes turnos; com `comparison=[]`, não há judge).
  Comportamento esperado e permitido pela regra "o roteador pode consultar
  candidatos ... pedir uma síntese julgada" — é decisão de custo da IA, não
  um gate automático. Limitação desta rodada de evidência: nenhuma
  arbitragem real foi exercitada aqui (o E2E de 2026-09-30 registrou o
  mesmo `comparison` vazio).
- Orçamento único: nenhum segundo contador de rodadas interrompeu o turno;
  retry não reiniciou o relógio (nenhum retry foi necessário).

## Pipeline real executado (log `logs/backend.log`, 04:55:20–04:57:28)

- Clarifier classificou `analyze_url` (sem perguntar — pedido era claro).
- Tool do chat acionada: scrape do Firecrawl + screenshot via CDP
  Browserless; HTML 22336 -> 5793 chars (25.9%), 3 elementos a11y.
- Orchestrator: roteamento seletivo ativou **19 especialistas** com
  justificativas por agente (ex.: `link_checker -- HTML contem links`,
  `visual_a11y -- screenshot fornecido`) e pulou
  angular/react/svelte/tailwind (classificador não detectou framework).
- A11yExpertReviewer: batch review 9 issues em 2 lotes; **removeu 3 falsos
  positivos (9 -> 6 issues)**; revisor recebeu HTML original da captura em
  cada lote.
- Loop de delegação convergiu na rodada 1 (sem rodar em círculos).
- Pipeline concluído: **6 issues, 21/21 agentes OK**. Cache atualizado para
  a sessão `91602c57-54f1-445b-b6f8-367431730efd`.
- Chamadas reais ao Ollama Cloud no período: **59** (`POST
  https://ollama.com/api/chat 200`). **0 ERROR** no backend no turno. Os 8
  warnings de `models_dev` são do bootstrap de catálogo dos *outros*
  providers (sem chaves) — nenhum do Ollama Cloud.

## Conformação com as regras (CLAUDE.md) — tabela

| Regra | Evidência desta execução | Resultado |
| --- | --- | --- |
| Classificador mobiliza a squad pelo contexto | tech_lead -> qa_lead -> a11y_specialist, na ordem do problema (estratégia, régua de aceite, análise), sem sequência de gestão obrigatória | Passou |
| Nada de keywords/regex/eurística decidindo intenção | `ClarifierAgent` classificou `analyze_url` por julgamento; RouteAdvisor com `source=ia` em todas as 29 rotas; logs de seleção com justificativa textual, não match de string | Passou no caminho observado; não prova ausência de keywords em todo o resto do sistema |
| Roteamento do Alto sem modelo fixo | 28 rotas -> `gemma4:31b`, 1 rota -> `deepseek-v4.1-flash`, catálogo descoberto ao vivo; nenhuma constante de modelo usada como rota | Passou |
| Economia sem perder precisão | `clarifier`/`classifier` rodaram com `reasoning_effort=none`; especialistas com `medium`; 19 especialistas em paralelo com timeout por agente | Passou |
| Entrega completa, sem rodar em círculos | Loop de delegação convergiu na rodada 1; pipeline 21/21 OK; revisão removeu 3 falsos positivos antes de narrar | Passou |
| Progresso estruturado, sem silêncio longo | Feed mostrou contador `N de 19` enquanto especialistas terminavam, achados marcados como preliminares até a revisão | Passou |
| Narrativa em linguagem natural | Resposta final sem JSON cru; cards com status de ferramenta (` Buscando e renderizando …`) | Passou |
| Orçamento adaptativo único | Turno único de 130 s sem segundo contador; nenhum retry para reiniciar relógio | Passou |
| Julgamento entre modelos (Alto) | Permitido pela regra, mas a IA retornou `comparison=[]` nas 29 rotas e não houve arbitragem; judge vazio | Não exercitado nesta rodada (decisão de custo da IA) |
| Redirecionamento em tempo real | Não testado nesta rodada (sem steer durante o streaming) | Fora do escopo desta execução |
| Cancelamento determinístico | Não testado nesta rodada (nenhum cancelamento pedido) | Fora do escopo desta execução |

## Comparação com a rodada de 2026-09-30

A execução anterior (`docs/e2e-interface-ollama-2026-09-30.md`)
**não chegou a auditar** — interrompida manualmente após 5 min de
planejamento, com economia inadequada (três candidatos + juiz para o
clarifier) e silêncio longo na triagem. Nesta rodada de 2026-10-01:

- O turno completo foi auditado de ponta a ponta (130 s), sem
  interrupção manual 
- A economia melhorou de forma mensurável: clarifier/classifier com
  `reasoning_effort=none`, sem comparação de modelos em rotas simples
- Os mesmos cardápios de regras foram exercitados com resultado distinto:
  entrega completa em vez de parcial interrompida, progresso contínuo em
  vez de silêncio de 124 s
- O gap anterior de "não chegou à auditoria" foi fechado: 19
  especialistas rodaram com evidência real de HTML capturado

Ambas as rodadas documentam o mesmo ponto em aberto: nenhuna execução
até esta data confirmou a arbitragem real do modo Alto com
`comparison` preenchido e judge rodando (`model_arbitration.py`).

## Conclusão

Auditoria completa de ponta a ponta, com roteamento dinâmico do modo
Alto real no Ollama Cloud e classificação semântica sem determinismo.
A arbitragem entre modelos não foi exercitada nesta rodada — não é
caminho bloqueado, é decisão de custo da IA registrada; para o
contrato de aceitação completo do modo Alto, falta uma execução cujo
RouteAdvisor retorne candidatos suficientes para o julgamento.

A configuração do provider e do modelo ficou persistida pelo produto
(DPAPI em `backend/.secrets.json`) e a conversa de teste permanece
recuperável pela UI.

## Limitações desta rodada

- A arbitragem/julgamento entre candidatos não foi exercitada (a IA decidiu
  não comparar em todas as 29 rotas do turno). Para forçar o caminho, seria
  necessário um turno cujo RouteAdvisor retorne `compare_models` com >= 2
  candidatos.
- Provider configurado só Ollama Cloud: cascata de failover não exercitada.
- NVDA real não foi acionado (o ambiente não tem o serviço rodando); as
  verificações de leitor de tela rodaram pelo motor de acessibilidade do
  Chromium (CDP), conforme README, sem as vozes.