# Contratos de componentes acessíveis

Este catálogo traduz padrões comuns de bibliotecas de componentes acessíveis em
contratos que podem ser verificados em uma aplicação concreta. Ele é inspirado
nos componentes demonstrados pelo Accessible Astro Starter, mas não depende de
Astro: o mesmo contrato vale para HTML nativo, React, Vue, Svelte, Angular ou
Web Components.

## Como avaliar uma biblioteca de componentes

Uma biblioteca pode declarar que oferece acessibilidade sem que a aplicação a
use corretamente. Separe sempre três perguntas:

1. O componente escolhido é semanticamente adequado ao comportamento real?
2. O HTML renderizado expõe nome, papel, estado e relação corretos?
3. O comportamento em runtime mantém foco, teclado, anúncios e atualização de
   estado quando o usuário interage?

Não transforme o nome de um componente, uma classe CSS ou uma documentação em
prova de conformidade. Quando o HTML não permite confirmar o comportamento em
runtime, reporte como verificação pendente, com confiança média, e diga qual
teste manual ou automatizado falta.

## Disclosure, acordeão e mostrar mais

- O gatilho deve ser um `button` ou o `summary` de um `details` nativo, não um `div`
  clicável. `details` e `summary` expõem o estado sozinhos: nesse caso `aria-expanded` e
  `aria-controls` não são exigidos.
- Quando o gatilho é um `button`, ele deve expor `aria-expanded="true|false"` e `aria-controls`
  apontando para o painel correspondente.
- O painel deve ter um `id` estável; quando recolhido, deve estar realmente
  oculto para tecnologia assistiva (`hidden`, `display:none` ou equivalente
  comprovado).
- A mudança visual precisa ocorrer junto com a mudança do estado ARIA.
- Se o conteúdo revelado receber foco ou inserir novos controles, o foco e a
  ordem de leitura precisam continuar previsíveis.

## Modal e drawer

- Use `<dialog>` com `showModal()` ou um padrão equivalente comprovável; um
  `role="dialog"` isolado não cria gerenciamento de foco.
- O diálogo precisa de nome acessível, foco inicial dentro, retorno do foco ao
  gatilho e fechamento por `Escape`.
- Enquanto estiver aberto, o conteúdo de fundo não pode continuar navegável;
  prefira `inert` e confirme que não há uma segunda rota de foco.
- Clique no backdrop não pode ser a única forma de fechar.
- Se o foco for preso por JavaScript, teste também Tab, Shift+Tab, leitor de
  tela e desmontagem/re-renderização do componente.

## Tabs

- O contêiner deve ser `role="tablist"`, cada aba `role="tab"` e cada painel
  `role="tabpanel"`.
- Cada aba precisa de `aria-selected`, `aria-controls` e `id`; cada painel deve
  referenciar sua aba com `aria-labelledby`.
- Use setas para mover entre abas, Home/End quando suportado pelo padrão, e Tab
  para entrar ou sair do conjunto — não exija Tab entre todas as abas.
- Painéis inativos precisam estar ocultos ou fora da árvore de acessibilidade.
- O modo automático ou manual de ativação deve ser consistente e anunciado.

## Tooltip, toast e notification

- Tooltip complementa um controle; nunca deve ser o único nome de um botão de
  ícone. Deve aparecer em foco e hover, permanecer enquanto o ponteiro estiver
  sobre ele e poder ser dispensado sem mover o foco, inclusive com Escape. Um toggletip, que
  só abre por ativação (clique, Enter, Espaço), é outro padrão: a regra de hover e foco não se
  aplica a ele, mas ele precisa fechar com Escape ou ao clicar fora.
- Mensagens de sucesso ou estado normal devem usar um container persistente com
  `role="status"` ou `aria-live="polite"`; não crie a região live somente no
  instante da mensagem.
- Erros urgentes podem usar `role="alert"`, mas não use assertividade máxima
  para cada mudança de interface.
- Mensagens não devem roubar o foco de quem está trabalhando. O foco só deve
  ser movido quando o usuário precisa corrigir um erro ou responder a uma ação.
- Ofereça tempo suficiente, pausa ou dispensação quando a mensagem desaparece
  automaticamente.

## Skip link, alto contraste e movimento reduzido

- O skip link deve ser o primeiro elemento focável e apontar para o conteúdo
  principal; o alvo precisa receber foco de forma observável quando necessário.
- Alto contraste não pode depender somente de inverter cores. Verifique texto,
  bordas, ícones, foco, estados hover/focus e conteúdo em imagens.
- `prefers-reduced-motion: reduce` deve reduzir ou remover animações e
  transições não essenciais. Uma chave manual de movimento reduzido deve
  produzir o mesmo efeito da preferência do sistema.
- Não aceite a existência de um botão “alto contraste” ou “reduzir movimento”
  como prova: confira o CSS e o estado aplicado ao documento.

## Formulário, tabela e paginação compostos

- Cada campo deve ter nome visível associado, instrução e erro ligado por
  `aria-describedby`; estado inválido deve ser refletido por `aria-invalid`.
- Um formulário com erro precisa anunciar o resumo e levar o usuário ao local
  de correção sem perder contexto.
- DataTable precisa preservar cabeçalhos, relação célula-cabeçalho, ordenação,
  paginação e posição real quando houver virtualização.
- A paginação deve indicar a página atual com `aria-current="page"` quando houver lista de
  páginas numeradas (ou por texto de progresso, como "Página 3 de 12", quando não houver), ter
  nomes distintos para anterior/próxima e manter foco depois de trocar o conteúdo.

## Regra de evidência do componente

Classifique cada conclusão como uma destas evidências:

- `confirmado-estatico`: comprovado pelo HTML/CSS/atributos presentes;
- `confirmado-runtime`: comprovado por interação ou teste de navegador;
- `declarado-na-documentacao`: apenas afirmado pela biblioteca ou projeto;
- `pendente-manual`: depende de leitor de tela, navegador ou comportamento que
  não foi observável na execução.

Uma declaração de acessibilidade nunca deve substituir a evidência real. Se a
documentação diz que contraste atende AA, mas a medição encontra contraste
insuficiente, o achado deve apontar a divergência explicitamente.
