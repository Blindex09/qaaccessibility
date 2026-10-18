# Conhecimento de bibliotecas de componentes acessíveis

Este documento é a fonte única do que o chat e os agentes especialistas sabem sobre bibliotecas de componentes. Ele tem duas partes: o método geral, que vale para qualquer plataforma, e o catálogo de uma biblioteca concreta, o accessible-astro-components. Novas bibliotecas entram como novas seções do catálogo, sem mudar o método.

## Método geral para auditar a saída de uma biblioteca de componentes

- Audite o que a biblioteca de fato renderiza, nunca o nome do componente, a classe CSS, o README ou a frase "totalmente acessível". Quando o material recebido é código-fonte de página (.astro, .mdx, .tsx, .vue, .svelte, Razor, Twig), cada componente é um contrato de entrada: descubra que HTML cada propriedade produz antes de concluir qualquer coisa.
- Nativo primeiro. details e summary, dialog aberto com showModal, popover, button, nav, fieldset e legend, label com for já expõem papel, nome e estado. Não exija aria-expanded, aria-controls, role="dialog" nem aria-modal sobre um elemento nativo que já cumpre o papel: isso é falso positivo. ARIA que contradiz o elemento nativo, ao contrário, é achado real.
- Descubra de onde vem o estado: nativo (atributo open, popover, checked), por script (aria-pressed, aria-selected e aria-expanded atualizados em runtime) ou só visual (uma classe). O HTML inicial pode mostrar aria-pressed="false" antes de o script rodar; isso é pendência de runtime, não falha.
- Propriedades extras costumam ser espalhadas no elemento depois dos atributos calculados. Um aria-label, role, tabindex ou target passado pelo consumidor sobrescreve o da biblioteca. Diga se o defeito é da biblioteca ou do uso que a página faz dela.
- Composição: o componente só está correto se as peças certas forem usadas juntas (itens dentro de lista, aba com lista de abas e painel, ids e referências casando). Confira as relações entre peças no HTML renderizado.
- A alternativa textual vem do consumidor. Imagem, avatar, cartão e mídia com alt padrão vazio viram decorativos; decida pelo contexto se a imagem é informativa. Componente sem nome padrão (avatar sem label e sem título) fica sem nome por culpa do uso.
- Texto só para leitor de tela e ícone com aria-hidden compõem o nome. Um aria-label no consumidor substitui o nome inteiro e perde o texto escondido, como o aviso de que o link abre em nova aba.
- Um botão que troca o rótulo e também o estado (aria-expanded ou aria-pressed) anuncia a mudança duas vezes. O padrão correto é rótulo fixo com estado, ou rótulo que muda sem estado.
- Menu de navegação do site com submenus é o padrão de navegação por divulgação: botões com aria-expanded que abrem uma lista de links. Não é um menu de aplicativo, então não exija role="menu", role="menuitem" nem setas entre itens; setas e Escape são um extra opcional. O que é achado real: aria-haspopup="true" num botão cujo submenu só tem links, porque ele anuncia "menu" e promete um comportamento que a lista não tem; botão de submenu sem aria-expanded; aria-current ausente no link da página atual; e dois blocos de navegação (desktop e celular) sem nomes diferentes.
- aria-haspopup="dialog" no gatilho de um diálogo é recomendação do padrão, não exigência isolada; um dialog nativo aberto por showModal não precisa dele.
- Roteadores de página sem recarga (Astro ClientRouter e View Transitions, roteadores de SPA) exigem que scripts reiniciem depois da troca, que foco e anúncio da nova página sejam tratados e que o estado salvo seja reaplicado. Isso só se confirma em runtime.
- Páginas de galeria que exibem todos os estados de um componente juntos geram ids repetidos, landmarks iguais e muitos títulos. Separe o achado da galeria do achado do componente.
- Foco desenhado só com box-shadow e outline removido pode sumir no modo de cores forçadas. Marque como pendência manual de forced-colors, não como falha confirmada.
- Classifique cada conclusão como confirmado-estatico, confirmado-runtime, declarado-na-documentacao ou pendente-manual. Comportamento de script que o HTML não prova é pendente-manual, nunca uma falha inventada. Calibrar não é suprimir: um defeito real comprovado continua sendo reportado.
- O mesmo método vale em qualquer plataforma (Astro, React, Vue, Svelte, Angular, Web Components, Blazor, WordPress). Só muda como achar o código-fonte do componente.

## Catálogo: accessible-astro-components (Incluud)

Origem: código-fonte lido em 2026-10-17 no ramo principal do repositório incluud/accessible-astro-components. O Accessible Astro Starter importa estes componentes de accessible-astro-components e de accessible-astro-launcher. O projeto de teste my-accessible-site declara a versão ^5.2.0 e não tem node_modules, então o comportamento exato da versão instalada ainda deve ser conferido no HTML renderizado. Os nomes de classe abaixo ajudam a reconhecer a biblioteca no HTML, e quem decide é a leitura do contexto, não uma lista.

### Accordion e AccordionItem

HTML: ul.accordion com li.item, dentro details.wrapper, summary.title contendo um Heading (headingLevel padrão h3, tamanho visual h6) e div.content. O atributo name agrupa itens com abertura exclusiva.
Não é falha: não existir button, aria-expanded, aria-controls nem id. details e summary são o padrão nativo de divulgação e expõem o estado sozinhos.
Achados reais ou pendências: o segundo SVG do ícone de mais não tem aria-hidden; list-style none no ul pode remover a semântica de lista no Safari com VoiceOver (pendente-manual); heading dentro de summary entra na navegação por títulos, o que é permitido, mas o nível precisa caber na hierarquia da página.

### Modal e Drawer

HTML: dialog nativo aberto por showModal, com aria-labelledby apontando para o título (id do gatilho mais -title). No Modal o título é h3, no Drawer é sempre h2, com tabindex="-1" e autofocus. Botão de fechar real, com texto escondido (padrão "Close").
Não é falha: ausência de inert e de aria-modal, porque showModal já torna o fundo inerte. Escape é o cancelamento nativo do dialog. Clique no fundo fecha, e existe o botão de fechar, então não é a única forma.
Achados reais ou pendências: o gatilho não tem aria-haspopup nem aria-expanded (recomendação, não obrigação); o componente não guarda o gatilho para devolver o foco, então confirmar em runtime que o foco volta ao gatilho; a armadilha de Tab por script só age quando o foco já está no primeiro ou no último item; sem aria-describedby, o que é opcional; id do gatilho precisa ser único.

### Tabs, TabsList, TabsTab e TabsPanel

HTML: a marcação vem das peças. TabsList com role="tablist", TabsTab é button com role="tab", id, aria-controls, aria-selected e tabindex 0 na aba ativa e -1 nas demais, TabsPanel com role="tabpanel". O componente Tabs só acrescenta o script.
Comportamento do script: setas esquerda e direita com volta ao início e ao fim, ativação automática ao focar, sem Home e End. Home e End são recomendação do padrão, não exigência isolada.
Achados reais ou pendências: painéis inativos recebem aria-hidden="true" mas não hidden nem display; se o CSS da página não os remove do fluxo, controles focáveis dentro de painel inativo continuam alcançáveis pelo Tab (confirmar em runtime); conferir no HTML renderizado o aria-labelledby de cada painel apontando para sua aba.

### Tooltip

HTML: button.tooltip-trigger com popovertarget, aria-describedby, aria-controls e aria-expanded sincronizado, e span com role="tooltip" e atributo popover. O nome vem do conteúdo do botão ou do triggerLabel escondido; sem nenhum dos dois o componente lança erro.
Comportamento: abre por ativação (clique, Enter, Espaço), não por hover nem por foco. Isso é um toggletip, um padrão de informação sob demanda, e não um tooltip clássico. A regra 1.4.13 trata de conteúdo que aparece em hover ou foco; um toggletip que só abre por ativação não falha por não abrir em hover.
Pendências: Escape e clique fora vêm do comportamento nativo do popover automático (confirmar em runtime).

### Notification e Toast

Notification: div ou aside, com role padrão none; role opcional (status, alert, log, timer, marquee, region). Não define aria-live, não tem botão de dispensar nem tempo. Uma notificação estática e permanente sem role é correta; só é falha se a mensagem aparece dinamicamente e a região viva não existia antes. O Form da biblioteca usa Notification com ariaLive polite, escondida, que ganha tabindex -1 e foco depois de erro de envio.
Toast: div.toast sem role nem aria-live; o anúncio depende do contêiner do ToastProvider (conferir que ele é persistente e tem role="status" ou aria-live polite). Texto escondido com o tipo ("error:"), botão de dispensar real com nome escondido. O componente não tem temporizador.

### Form, Input, Textarea, Checkbox, Radio e Fieldset

Form: form.js-validate sempre com novalidate; o script da biblioteca valida. Em erro, mostra um resumo (Notification de erro, aria-live polite) que recebe foco, com links por id para cada campo inválido. Marca aria-invalid nos campos obrigatórios por script. Não liga aria-describedby da mensagem inline ao campo.
Input: div.input-group com label for (id padrão input mais o nome), input e small com id terminado em -validation, apontado por aria-describedby e escondido até aria-invalid="true". Obrigatório usa o atributo nativo required e o texto visível "(required)" no rótulo; aria-required seria redundante. A mensagem inline não é região viva; o anúncio vem do resumo. autocomplete padrão é "on"; o consumidor precisa passar o token certo (name, email) para 1.3.5.
Checkbox: div.checkbox-group com input type checkbox e label for; id padrão checkbox mais o nome, o que gera ids repetidos se vários checkboxes dividem o mesmo name sem id (achado real de uso).
Fieldset: fieldset e legend, com "(required)" dentro da legenda e aria-describedby para o small de validação.
Textarea e Radio seguem o mesmo padrão do Input e do Checkbox, mas a fonte deles não foi lida: confirmar no HTML renderizado.

### Heading

O level escolhe o elemento (h1 a h6) e o size muda só o visual. Não há ARIA extra. Pular níveis é decisão do consumidor, e não prova de falha por si só.

### Link e Button

Link: sempre a. isButton só muda o estilo e continua sendo link, o que é correto para navegação; só é problema se o controle executa ação sem navegar. isExternal acrescenta target="_blank", rel="noopener noreferrer", SVG com aria-hidden e texto escondido "Opens in a new tab"; hideIcon remove os dois. ariaLabel substitui o nome inteiro e perde o aviso de nova aba. aria-current não é tratado pelo componente.
Button: button com type="button" por padrão (htmlType muda para submit ou reset); a propriedade type é só a cor. Botão só com ícone depende do ariaLabel do consumidor. disabled é o atributo nativo.

### Badge, Avatar, AvatarGroup e Card

Badge: span sem papel, ou button quando isButton. O botão não tem atributo type, então dentro de um formulário envia o formulário; o label vira texto escondido. Animação de hover e de pulso não respeita prefers-reduced-motion no componente (pendente-manual para 2.3.3 e 2.2.2).
Avatar e AvatarGroup (o grupo só agrupa avatares, e a fonte dele não foi lida; cada avatar precisa do próprio nome): div com img de alt vindo de label, depois título, depois vazio; ou span role="img" com aria-label. Sem label e sem título fica sem nome (defeito de uso). Título e subtítulo são parágrafos, não títulos. Alt igual ao título visível gera leitura repetida.
Card: article.card com Heading (padrão h3, tamanho h6) contendo um link; o link cobre o cartão inteiro por pseudo-elemento, e controles interativos nos slots ficam sob essa camada. Alt padrão da imagem é vazio. O foco aparece por box-shadow no :focus-within.

### Breadcrumbs, BreadcrumbsItem e Pagination

Breadcrumbs: nav com aria-label "Breadcrumbs" e lista ordenada. O item (aria-current e separadores) vem de BreadcrumbsItem, cuja fonte não foi lida: confirmar no HTML renderizado.
Pagination: nav com aria-label "Pagination" e ul com cinco li: primeira, anterior, progresso textual "Page X of Y", próxima, última. Links levam aria-label sem o número da página. Controle indisponível vira span.disabled, sem link e sem aria-disabled, o que é correto porque deixa de ser controle. Não existe lista de números nem aria-current: a página atual é o texto de progresso. Exigir aria-current="page" aqui não se aplica ao padrão. O anel de foco usa box-shadow e remove o outline (pendente-manual em cores forçadas).

### DarkMode, HighContrast e ReducedMotion

HTML: button com aria-pressed e aria-label fixo ("Toggle Dark Mode", "Toggle High Contrast", "Toggle Reduced Motion"), ícones com aria-hidden, rótulo constante e estado em aria-pressed (padrão correto). O estado inicial aria-pressed="false" muda quando o script roda.
Comportamento: o estado é salvo em localStorage (darkMode, highContrast, reducedMotion). DarkMode usa prefers-color-scheme só quando não há valor salvo e não acompanha mudanças depois. HighContrast só acrescenta a classe high-contrast ao html (contornos de 3px, links sublinhados) e não lê a preferência do sistema. ReducedMotion acrescenta reduce-motion ao html (durações de 0,01 ms, rolagem sem suavização) e lê prefers-reduced-motion só na carga. Só é achado se o CSS da página não reage a essas classes ou não cobre texto, bordas, ícones e foco.

### SkipLink

Usado no Header do starter. A fonte não foi lida: conferir no HTML renderizado que é o primeiro elemento focável, que o destino existe (no starter, main com id main-content) e que o link aparece quando recebe foco.

### Media e Video

Media: div.media-wrapper com img, alt padrão vazio, sem figure nem figcaption; propriedades extras vão para a div, não para a imagem.
Video: div.video-wrapper com iframe do YouTube (youtube-nocookie), com title. Não há elemento video, trilha de legendas nem transcrição; as legendas dependem do player do YouTube e disablekb desliga os atalhos dele. Legendas, audiodescrição e alternativa (1.2.x) precisam de verificação humana.

### Pendentes de leitura

DataTable, Drawer em uso real, Textarea, Radio, BreadcrumbsItem, TabsPanel, SkipLink e o accessible-astro-launcher (paleta de comandos) existem na biblioteca ou no starter e ainda não tiveram a fonte lida.
