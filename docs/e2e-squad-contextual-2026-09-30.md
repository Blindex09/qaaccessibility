# E2E real da mobilização contextual da squad — 2026-09-30

Resultado: execução real concluída; aprovação comportamental apenas parcial.

## Ambiente e escopo

- Chrome, interface em `http://localhost:19006/`, backend na porta 8001.
- Configuração confirmada na interface: Ollama Cloud, Alto (seleção dinâmica).
- Conversa de teste: `69ce12bb-7d48-42a7-8800-f2a11d3f93d4`.
- Alvo público: `https://example.com/`, página inicial desktop.
- Pedido inicial restrito a idioma e títulos, WCAG 2.2, sem modificações.
- Nenhum papel, especialista ou modelo individual foi fixado no pedido.
- Continuação: revisar escopo/evidências com a squad, sem nova inspeção.

## Evidências observadas

1. Primeiro turno: 54 segundos indicados pela interface. Executou Product Owner,
   Tech Lead e QA Lead, sem a sequência obrigatória incluindo Engineering Manager.
2. Inspeção real via Firecrawl/Browserless e execução de dois especialistas:
   understandability e wcag_semantics, seguida de a11y_expert_reviewer.
3. Resultados intermediários chegaram antes da resposta final: especialistas em
   execução, achados preliminares e revisão. Não entregou somente ao final.
4. Segundo turno: 32 segundos. A ferramenta consult_squad foi executada na
   interface, consultando novamente Product Owner, Tech Lead e QA Lead.
5. Os logs contêm somente um pipeline ANALYZE concluído nesta conversa. A revisão
   reutilizou os achados anteriores e não repetiu a captura/inspeção.
6. O roteador registrou decisões `source=ia`. Neste teste as escolhas registradas
   convergiram para gemma4:31b; isso não demonstra alternância entre modelos nem
   julgamento entre modelos, pois comparison permaneceu vazio.
7. ArrowDown moveu o foco de uma atualização para a seguinte. O elemento focado
   não estava dentro de aria-live. Não houve teste auditivo com NVDA real.
8. O cabeçalho das respostas foi qaaccessibility. Não foram observadas ferramentas
   de mutação nesta execução.

## Limitações e reprovações

- Várias atualizações repetiram a mesma intenção com outras palavras. A deduplicação
  literal anterior não resolve repetição semântica. Ainda apareceu linguagem interna
  sobre classificar/reranking, inadequada para o progresso solicitado pelo usuário.
- O QA Lead foi consultado inicialmente antes de existirem achados e respondeu que
  aguardava a análise. A seleção é da IA, mas a trajetória ainda desperdiçou consulta.
- wcag_semantics/reviewer mantiveram um achado sobre o link Learn more, fora do
  escopo explícito de idioma/títulos. A revisão posterior excluiu esse item do escopo.
- O QA Lead chamou a ausência de títulos de falha, enquanto a primeira resposta
  ressalvou que a ausência não constitui automaticamente falha WCAG. O veredito
  normativo não ficou consistentemente calibrado entre todos os papéis.
- Ao iniciar o segundo turno, o tempo exibido no primeiro mudou de 54s para 1s.
  O registro de duração por turno precisa de revisão.
- A abertura independente do alvo no Chrome retornou lang=pt e título Domínio de
  exemplo, com zero headings; a auditoria relatou lang=en na captura de seu pipeline.
  As representações/localização de captura não são intercambiáveis. Não tratar a
  diferença, isoladamente, como prova de invenção do modelo.

## Artefatos

- Screenshot: `artifacts/qaa-squad-e2e-real-2026-09-30.png`.
- Logs: `logs/backend-squad-contextual-2026-09-30.v2.stdout.log`.

Este teste comprova a ligação real da squad e da consulta contextual no chat.
Não comprova todas as regras mestras, todos os provedores ou precisão normativa
completa. Não foram feitas correções de código durante esta rodada de E2E.
