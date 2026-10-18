# Leitor de tela e elementos HTML: o que a pessoa ouve, acessível e não acessível

Esta referência diz, elemento por elemento, o que cada leitor de tela expõe e fala, e o que acontece quando o elemento não é acessível. Serve para o chat e para os agentes de análise terem expectativa precisa, e não para provar conformidade.

## Como usar esta referência

Fontes: matriz de suporte de HTML da TetraLogical (NVDA, JAWS, VoiceOver no Mac e no iOS, TalkBack e Narrator), HTML-AAM da W3C (mapeamento de elementos para papéis) e a especificação Accessible Name 1.2. Consultadas em 2026-10-17.

- O que a especificação define é o papel, o nome e o estado que o navegador entrega ao leitor de tela. A frase exata falada, a ordem das palavras e os avisos extras variam por leitor, versão, navegador e configuração de verbosidade. Nunca afirme uma frase exata como regra; descreva o papel, o nome e o estado, e diga que a fala varia.
- Os resultados abaixo são de testes públicos da TetraLogical (matriz de suporte de HTML, repositório TetraLogical/screen-reader-HTML-support, atualizada em fevereiro de 2026, e a página do JAWS em maio de 2026). Versões testadas: NVDA 2024 com Chrome 129 (e Firefox em algumas linhas); JAWS 2026 com Chrome 148; VoiceOver no macOS Sequoia 15.5 com Safari 18.5 e Chrome 139; VoiceOver no iOS 18.6.2 com Safari; TalkBack de 2025 com Chrome 137; Narrator de 2025 com Edge 142 em Windows 11. As páginas do TalkBack e do Narrator se declaram trabalho em andamento. Versões mais novas podem ter mudado.
- Um achado que depende de uma dessas diferenças deve citar o leitor e o navegador, e ser marcado como pendente de verificação manual, a menos que a árvore de acessibilidade real o comprove.
- Muitas informações do Narrator exigem verbosidade 3 (todos os detalhes do controle); quem usa o padrão pode não ouvi-las.

## Estrutura de cabeçalhos e listas

Cabeçalhos h1 a h6 são falados com o texto, a palavra cabeçalho e o nível, e podem ser listados e percorridos por nível em todos os leitores testados. O atributo aria-level funciona de 1 a 6; acima de 6 é inconsistente: o JAWS e o Narrator reportam nível 2 para valores de 7 a 12 em role="heading", e o VoiceOver no Chrome só acerta até 9. O JAWS não respeita aria-level em h1 a h6 nativos. O Narrator só diz o nível com verbosidade 3 ou mais.
Listas ul e ol são faladas como lista com número de itens e a posição de cada item. Item de lista ordenada leva número ou letra. dl é tratada como lista cujo total inclui dt e dd. Falha comum: dd não é lido ao navegar por itens (NVDA, JAWS, Narrator); só com a seta para baixo. No VoiceOver do iOS, dl não é reconhecida no rotor. No TalkBack a lista em si não está na ordem de deslizar e os itens dizem "1 de N".
hr é falado como separador. br é uma quebra (no VoiceOver, uma só, qualquer que seja a quantidade). p, div, span e a maioria dos elementos de texto em linha não têm semântica própria.
Não acessível: cabeçalho usado só para o visual (a lista de cabeçalhos fica sem sentido); nível pulado; ausência de h1 (ver a calibração normativa: nem sempre é falha de critério).

## Links e botões

a com href é falado como link (ou link visitado) com o nome acessível, e aparece na lista de links. a sem href é lido como texto comum em todos os leitores testados, sem papel de link e sem atalho de link; para funcionar precisa de href ou de role e tabindex e teclado. area de mapa de imagem é falada como link gráfico, mas o NVDA não a anuncia como link quando se chega por Tab, e o JAWS repete "mapa de imagem".
button e input de tipo button, submit, reset e image são falados com o nome e a palavra botão. aria-pressed vira botão de alternância com estado marcado ou não. Botão desabilitado sai da ordem do Tab e, no JAWS, é falado como indisponível ao navegar por setas. No Narrator, aria-haspopup não é suportado; input image sem alt é falado como "Enviar". title em botão só é falado com verbosidade alta no Narrator.
Link com aria-label: o aria-label substitui o texto visível inteiro, e o JAWS nesse caso não fala nem o title. aria-describedby num link é falado só com o Tab no JAWS, não com as setas.
Não acessível: botão feito de div ou span (sem papel, sem foco, sem Enter e Espaço); link só com ícone sem nome (falado só como "link" ou "botão"); vários links com o mesmo texto e destinos diferentes (a lista de links fica ambígua); texto genérico como "clique aqui" (o critério 2.4.4 considera o contexto programático, então texto genérico sozinho não prova falha).

## Campos de formulário

Campos de texto (text, email, tel, url, search): falados como campo de edição com o nome. O NVDA e o JAWS não dizem o tipo email; o Narrator nunca diz o tipo e não tem papel searchbox; o VoiceOver do Mac diz "campo de texto" ou o tipo específico (como campo de URL). password: o NVDA fala "edição protegida" e cada tecla como "estrela"; o JAWS também diz estrela; o VoiceOver do iOS fala as teclas digitadas em voz alta (problema de segurança relatado), o do Mac não fala os caracteres; o TalkBack diz o dígito e "bullet substituído"; o Narrator fala "oculto". number: botão giratório com valor, setas mudam e falam o valor (no TalkBack o novo valor não é falado de novo). range: controle deslizante com valor e setas; no NVDA, Home, End, PageUp e PageDown não funcionam. date, time e color: inconsistentes. No Chrome o NVDA fala números soltos sem contexto para date e o campo color sem nome; no Firefox há contexto. No iOS abrem seletores e a dica de ativar nem sempre é falada; date e time vazios podem ficar mudos.
file: botão com o nome do arquivo ou "nenhum arquivo escolhido"; o Narrator não anuncia o atributo multiple; o VoiceOver do Mac pode continuar dizendo "nenhum arquivo" depois da escolha. hidden não tem interface.
textarea: campo de edição com o nome e o valor (no JAWS o conteúdo não é falado na entrada, só "contém texto"). label: o conteúdo é falado quando o controle recebe foco; a associação por for e id, por envolver o controle, ou por aria-labelledby dá o nome.
checkbox: nome, marcado ou não (VoiceOver diz "tickbox"). radio: nome, estado e posição no grupo; o nome do grupo só é falado se houver fieldset com legend ou radiogroup nomeado.
select: caixa de combinação (NVDA e Narrator) ou botão de menu (VoiceOver e TalkBack). option: conteúdo, posição e selecionada; no iOS as opções são faladas como "botão". optgroup: o NVDA só fala o rótulo do grupo com a lista expandida; o Narrator não fala o papel do grupo; o TalkBack fala o rótulo sem contexto de grupo. datalist: o NVDA fala "caixa de combinação com preenchimento automático", o JAWS "caixa de lista de preenchimento automático", e no iOS com VoiceOver ligado a lista não aparece como caixa de lista; no TalkBack não há aviso de que existem sugestões.
fieldset e legend: o grupo só é exposto se tiver nome acessível (legend, aria-label ou aria-labelledby). O NVDA fala "agrupamento" com a legenda; o JAWS tem diferença de ordem quando a legenda tem cabeçalho dentro; o VoiceOver do iOS só fala o grupo ao chegar por navegação virtual; no TalkBack a legenda não é falada quando o primeiro controle recebe foco.
Não acessível: campo sem rótulo (falado só como "edição"); placeholder ou title como único rótulo (o Narrator só fala o placeholder com verbosidade 3); erro sem ligação com o campo; grupo de rádios sem fieldset e legend.

## Tabelas

table é falada como tabela com N linhas e M colunas, e a legenda (caption) é falada ao chegar. Células navegam por Ctrl+Alt e setas no NVDA e no JAWS; o VoiceOver e o TalkBack têm navegação por célula própria. A célula fala os cabeçalhos associados quando a ligação existe por th, scope, headers ou aria-labelledby. Sem ligação programática, o leitor não inventa o cabeçalho. thead, tbody, tfoot, tr, colgroup e col não transmitem semântica. O Narrator só fala cabeçalhos de coluna e de linha com verbosidade 3 e trata tabela complexa como "tabela não uniforme". No iOS, colgroup é falado de modo estranho ("cabeçalho de coluna, ocupa X colunas").
Não acessível: layout feito com tabela sem role presentation; tabela de dados feita de div; célula de dados sem cabeçalho associado; tabela sem legenda quando precisa de nome.

## Imagens e gráficos

img com alt: falada como gráfico ou imagem mais o alt. alt vazio (alt="") é marca deliberada de imagem decorativa: o NVDA, o JAWS e o VoiceOver a ignoram, e é válido. Sem o atributo alt: o JAWS fala "sem rótulo", o VoiceOver fala o nome do arquivo, o TalkBack diz "esta imagem não tem rótulo", e o Edge abre um aviso no Narrator. Ordem do nome: aria-label, depois alt, depois title.
svg: ignorado sem nome; com role="img" e nome é falado como gráfico. O Firefox ignora o svg sem role="img" e rótulo; o Narrator só fala title ou aria-label, e desc não é falado. canvas: transparente; o conteúdo de reserva interno é navegável; role presentation evita repetição; no VoiceOver do iOS precisa de role="img" e rótulo para ser identificado.
figure: só é falado como figura se tiver nome acessível ou figcaption; figcaption é falado como legenda da figura (NVDA) ou como conteúdo comum (VoiceOver). No TalkBack o papel de figura não é transmitido.
Não acessível: imagem informativa sem alt; decorativa com alt descritivo; imagem de gráfico sem alternativa dos dados; svg com informação sem nome; input image sem alt.

## Áreas de página e pontos de referência

header e footer viram banner e informação do conteúdo só quando são filhos diretos do corpo; dentro de article ou section deixam de ser pontos de referência (NVDA, JAWS, VoiceOver). main, nav e aside são expostos (aside como informação complementar). form e section só viram ponto de referência com nome acessível; sem nome são ignorados. article não tem navegação por padrão no NVDA e no Narrator. address só é falado como grupo se tiver nome. No TalkBack, main, header, footer, form e section não transmitem semântica nem o nome. No iOS, os pontos de referência precisam estar ligados no rotor.
Vários nav ou aside na mesma página precisam de nomes diferentes (sem a palavra do papel no rótulo).
Não acessível: conteúdo fora de qualquer ponto de referência em página com blocos repetidos; vários nav sem nome distinto; dois main.

## Divulgação, diálogo e progresso

details e summary: o summary é falado como botão com estado expandido ou recolhido (NVDA, VoiceOver, TalkBack falam "triângulo de divulgação"); o details em si só é falado se tiver nome (Narrator, JAWS). O estado é atualizado ao ativar. O texto é válido sem aria-expanded.
dialog aberto com showModal: falado como diálogo com o nome e a descrição; o foco vai para o primeiro elemento focável ou para o próprio diálogo, fica contido enquanto está aberto, Escape fecha, e o foco volta ao gatilho. O navegador mantém a barra de endereços na ordem do foco. No iOS, o foco só volta ao gatilho se o fechamento foi pelo teclado, e não por toque ou voz. O JAWS com tabindex="-1" no diálogo fala só o conteúdo, sem papel nem nome. O diálogo não modal não fecha com Escape por padrão. Com mais de um diálogo modal, Escape fecha só o último.
progress: falado com nome, valor e "indicador de progresso" (o NVDA toca bips com tom crescente); não recebe foco sem tabindex="0"; no VoiceOver mudanças de valor não são faladas; no TalkBack só são faladas com foco. meter: falado como barra de progresso (NVDA), indicador de nível (VoiceOver) ou medidor; o conteúdo de reserva e o aria-labelledby mudam o resultado, e o NVDA e o VoiceOver no Chrome suprimem o valor quando há aria-labelledby. output: o valor é lido, sem semântica.

## Texto em linha

abbr: o título não é acessível a quem usa só o teclado, e vários leitores não leem a expansão; não dependa de title para informação essencial. mark: falado como destacado (NVDA, VoiceOver, TalkBack) ou "realce" só se nomeado (Narrator); aria-label é ignorado no iOS. del e ins: falados como excluído e inserido no NVDA, JAWS e TalkBack, com comportamento inconsistente no VoiceOver, e sem indicação alguma no Narrator. s: falado como excluído em alguns leitores, embora signifique texto que não é mais exato. q e blockquote: o blockquote é falado como citação no NVDA e tem tecla Q; o Narrator não fala o papel. time, em, strong, b, i, u, small, sub, sup, code, kbd, samp, var, cite, dfn, data, bdi, bdo, pre, span: sem semântica falada na maior parte dos leitores; não use esses elementos para transmitir informação que só o significado dá (ênfase, destaque) sem texto equivalente, e lembre que o leitor pode ou não mudar a entonação. i é um item separado ao deslizar no TalkBack, a menos que font-style seja normal.

## Mídia e conteúdo incorporado

audio: o controle aparece como botões navegáveis quando há controls; o NVDA anuncia o nome mas não o áudio; o TalkBack não anuncia o audio ao receber foco. video: no Narrator o elemento não é falado sem tabindex="0", só o botão de reprodução; no VoiceOver do Mac é ignorado sem nome; no iOS fala duração e tempo decorrido. track: expõe o controle de legenda (NVDA) ou o texto da legenda atual (TalkBack). iframe: o NVDA e o JAWS falam o título e "quadro" (tecla M); o Narrator fala o título ou o título do documento mais "documento"; o iOS não anuncia o contêiner e o title nunca é falado; no TalkBack, sem title o iframe nem entra na ordem de deslizar. embed e object: inconsistentes; prefira img, video, audio ou iframe. noscript: lido só quando o JavaScript está desligado.
Não acessível: vídeo sem legendas nem alternativa; iframe sem title; áudio sem transcrição (critério 1.2.x exige verificação humana, e um leitor de tela não prova isso).

## Elementos sem interface

base, head, html, link, meta, param, picture, script, source, style, template e wbr não têm interface nem semântica. title é lido ao carregar a página e pelo atalho de título (NVDA+T); ele identifica a página e é o primeiro texto falado.

## Resumo dos pontos mais cobrados por quem testa

- Elemento sem nome acessível costuma ser ignorado ou falado de forma pobre: form, section, fieldset, figure, details, header e footer fora do corpo.
- Nada substitui ouvir o leitor real: dialog, date, time, color, meter, progress e embed variam por navegador e leitor.
- O que um teste automático pode afirmar é a árvore de acessibilidade; a fala exata é pendente manual.
