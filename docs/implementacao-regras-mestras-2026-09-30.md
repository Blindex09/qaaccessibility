# Correções das regras mestras — 2026-09-30

Complementa, sem apagar seu diagnóstico histórico, a
[auditoria com fontes primárias em inglês](auditoria-regras-mestras-web-2026-09-30.md).
Nenhum especialista de acessibilidade foi removido.

## Implementado e verificado em testes baratos

- Concessão imutável por agente no despacho, negada por padrão; schema validado
  antes do handler. Aprovação de capacidades marcadas obrigatória mesmo se uma
  configuração antiga tentar desligá-la. Regressões cobrem execução não concedida.
- Orçamento agregado herdado por triagem, roteamento, chamadas, reparação,
  ferramentas e especialistas. IA declara complexidade; harness converte o enum
  em teto contado desde o início, sem reset por retry. Factory também herda prazo.
- Planejamento gerencial decidido pela IA, sem inferência fixa por intenção ou
  anexos; pergunta ambígua acontece antes da escolha do agente executor principal.
- Contrato do consultor distingue o passo atual do objetivo futuro da auditoria.
  Passos de controle de resposta única não abrem competição entre modelos.
- Atualizações públicas do modelo podem chegar durante a produção do JSON da
  triagem, consultor e squad; decodificador só publica strings completas do campo
  público inicial. Não exibe o resto do protocolo nem raciocínio privado.
- Removidos pulsos repetitivos da squad por temporizador. Achados preliminares
  reais dos especialistas são publicados antes da revisão, identificados como
  provisórios. Interface conserva feed silencioso e navegável pelas setas.
- Cancelamento cobre também preparação do turno e preserva texto parcial.
  Cartões da interface são encerrados; anúncio pendente de digitação é limpo.
- Erro de conexão do navegador não é prova de bloqueio do site. Exceções
  desconhecidas de conexão no cliente não são interpoladas na interface.
  Identificadores técnicos desconhecidos de ferramentas/especialistas não são
  usados como seus nomes visíveis.
- Extração exige HTML original completo (`rawHtml`, `onlyMainContent=false`),
  sem fallback silencioso para artigo limpo. Código HTTP de erro do alvo impede
  auditar a página de erro como se fosse a página solicitada.

Esta última correção se fundamenta nos contratos oficiais de
[scrape](https://docs.firecrawl.dev/features/scrape) e
[extração avançada](https://docs.firecrawl.dev/advanced-scraping-guide).
HTML reconstruído não substitui teste interativo completo do site original.

## Verificação

- Ruff limpo nos módulos alterados e testes novos.
- Mypy: 21 arquivos-fonte verificados sem erros; notas existentes sobre funções sem tipos no registry.
- Jest: 9 suítes, 101 testes relevantes aprovados, incluindo cancelamento,
  apresentação de ferramentas, histórico, redirecionamento e live regions.
- TypeScript e ESLint dos arquivos da interface alterados: sem erros.
- Python: 426 testes na bateria consolidada; 3 testes adicionais do contrato
  de análise parcial/fatos observados passaram depois da última mudança.

## Limites da evidência

Não prova conformidade integral. Permanecem sem cobertura uniforme comprovada:
sandbox de filesystem/rede/processos, credenciais curtas por execução,
validação sintática de toda linguagem, recuperação durável de todos os stores,
redirecionamento Factory e todos os providers. Requisição síncrona já iniciada
pode continuar no transporte até seu timeout mesmo após cancelamento da UI;
as barreiras impedem iniciar novas ferramentas/chamadas no turno cancelado.

O roteador antigo ainda possui caminhos de contingência por catálogo e nomes;
não se declara remoção integral de legado. Uma escolha de contingência não deve
ser apresentada como julgamento inteligente comprovado.

## Execuções reais

As duas primeiras avaliações de example.com foram interrompidas: a primeira
por recarga durante alteração da interface; a segunda manualmente, após descobrir
extração de HTML incompleto. Seus achados não certificam a página real.

A repetição final usa conversa nova no Chrome, Ollama Cloud e seleção Alto,
com escopo inicial restrito ao idioma e títulos da página. A primeira atualização
observada levou aproximadamente um minuto: a latência de triagem/consultoria
continua sendo uma limitação real, mesmo com publicação incremental implementada.
O consultor da triagem usou contingência após resposta inválida; isso foi
registrado no log, não contado como sucesso de roteamento inteligente.

Essa execução revelou falta de telemetria do bootstrap: repetia consultor sem
JSON válido por ordem de catálogo. Agora seu resultado contratual é registrado;
empates de preço usam confiabilidade e latência observadas, atualizadas antes de
uma reparação. Não há escolha por substring nem modelo fixado manualmente.
Uma regressão verifica que a reparação pode usar outro consultor após falha.

Na nova repetição do mesmo pedido, o consultor respondeu com contrato válido
em cerca de oito segundos e a auditoria iniciou em aproximadamente 22 segundos.
A IA limitou a execução a dois especialistas de idioma/semântica, em vez de
expandir para as 19 especialidades da tentativa anterior. Ambas as decisões
foram reais, com `source=ia` registrado, não respostas simuladas.

## Correção de precisão descoberta no E2E

O resultado de 55 segundos reportava ausência de h1 como falha WCAG isolada.
A [explicação oficial de 2.4.6](https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html)
não exige que headings existam; [1.3.1](https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html)
exige preservação de informação/relações efetivamente transmitidas.
A ausência isolada de main também não comprova violação de
[2.4.1](https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks.html).

Foi removida a instrução rígida incorreta de h1 obrigatório. Especialista,
revisor e narrador agora compartilham calibração normativa explícita, com
precedência sobre listas de padrões. Julgamento permanece com a IA; não existe
filtro de achados por keywords/regex.

A repetição seguinte terminou em 47 segundos e deixou de acusar ausência de h1,
mas o narrador passou a inventar que existia h1. Isso **não foi aprovado**.
O resumo da ferramenta só continha achados, não fatos negativos/positivos do
documento. A última correção inclui `observed_structure` calculado antes da
extração semântica: idioma, título, quantidade e níveis/textos de headings,
limites de truncamento e ressalva de que não certifica conformidade.
O teste de contrato verifica o percurso original → resultado → resumo consumido
pelo narrador. Não transforma contagem de headings em julgamento WCAG.

Nesse E2E o consultor selecionou `gpt-oss:20b` na triagem e `gemma4:31b` na
execução, ambos com `source=ia`: há evidência de seleção dinâmica real, não apenas
nomes variados em testes simulados. Isso não prova qualidade global de toda rota.

Também foi corrigido o rótulo acessível do balão: usa a mesma limpeza de markup
da resposta visível. A regressão verifica o aria-label, além do textContent.

## Resultado da última execução

Conversa `7071972f-6156-4651-b043-e4301da6b44e`, logs
`logs/backend-rules-evidence-2026-09-30.stdout.log`, Chrome em
`http://localhost:19006/`, backend na porta 8001.

- Concluiu em **61 segundos**, com análise real da URL e dois especialistas,
  sem PO/Tech Lead/EM antecedendo o pedido simples.
- A resposta relatou corretamente `lang=en` e ausência de h1–h6, sem inventar
  h1 presente. Distinguiu ausência de headings de falha automática em 2.4.6.
- A leitura direta independente da URL também encontrou lang=en e zero h1.
  Isso verifica fatos estruturais, não toda a conclusão normativa.
- Publicou andamento e achado provisório antes do final. Atualizações reais
  foram consultadas com ArrowDown: foco avançou ao segundo item. Seus elementos
  têm tabindex=0, sem aria-live; não se realizou teste auditivo com NVDA nesta etapa.
- Balão e nome acessível sem os marcadores crus de Markdown anteriormente vistos.
- Evidência visual: `artifacts/qaa-regras-mestras-2026-09-30.png`.
- Backend ficou em execução após reinício com as mudanças finais.

**Aprovação limitada, não global.** A resposta ainda afirma falha do link
“Learn more” fora do escopo solicitado; o propósito precisa ser julgado com seu
contexto antes de certificar essa conclusão. O revisor atual recebe achados,
mas não recebe o HTML original como argumento — portanto não equivale a
verificação independente da evidência de cada achado. Existem ainda mensagens
padronizadas de início/fim e achados preliminares em inglês no feed. Não afirmar
que toda a comunicação já está natural/localizada ou que falsos positivos foram
eliminados. A redução de espera observada não é SLA garantido.
