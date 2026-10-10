# Módulo 4: documentos (Word, PowerPoint, PDF, Excel, EPUB) e imagens

STATUS: EM ANDAMENTO, NÃO CONCLUÍDO. Atualizado em 08/10/2026. Preparado sem chamar o modelo, porque o limite semanal
de uso da conta do Ollama Cloud está atingido (uma chamada mínima recebeu erro 429). Por decisão do dono do projeto, o
módulo foi preparado por leitura, testes e arquivos de teste, e o teste ao vivo fica para quando o limite voltar. Pela
regra 15 do CLAUDE.md ele só será dado como concluído depois desse teste.

Código principal: `backend/src/services/document_facts.py` (novo), `backend/src/services/chat_tools.py` (leitores
`_read_docx_text`, `_read_pptx_text`, `_read_pdf_text`, `_read_epub_text`, `_read_xlsx_structure` e a ferramenta
`analyze_document`) e `backend/src/services/chat_runtime.py` (pré-processamento dos anexos).

## O que o módulo promete

1. A pessoa anexa um documento e pergunta se é acessível. O sistema extrai o conteúdo e a IA julga.
2. Word, PowerPoint e EPUB são analisados pelo próprio modelo do chat a partir do texto extraído. PDF e Excel passam por
   especialistas próprios (`analyze_document`). Imagem anexada é vista pelo modelo, quando ele aceita imagem.
3. A resposta diz o que foi verificado e o que não pôde ser (regra 11): ausência de achados não é conformidade.

## O que foi encontrado lendo o código e rodando a extração (sem modelo)

Com arquivos de teste de defeito conhecido (um Word, um PowerPoint, uma planilha e um PDF), mostrei exatamente o texto
que o modelo recebia:
- Word: as imagens nem apareciam no texto, e faltavam o título e o idioma do documento e a marcação de cabeçalho da
  tabela. Uma imagem sem texto alternativo era invisível para o modelo.
- PowerPoint: não aparecia que o slide não tinha título, nem a existência ou o texto alternativo das imagens, nem a
  ordem dos objetos (a ordem de leitura).
- PDF: só o texto. Não se sabia se o arquivo era marcado (tagged), nem o idioma, o título, se o título aparece na barra
  da janela, nem se as figuras tinham texto alternativo. A conferência do veraPDF só entra se ele estiver instalado.
- EPUB: toda marcação era apagada. Sumiam títulos, texto alternativo, idioma da página e navegação.
- Excel: já trazia os fatos e avisava a incerteza sobre o texto alternativo. Estava certo.

Sem esses fatos o modelo só enxerga texto e não tem como julgar a acessibilidade do arquivo, o que arrisca uma resposta
falsa de que está tudo bem.

## O que foi corrigido (provado por teste, não ao vivo)

Novo módulo `document_facts.py`: lê a estrutura e relata fatos objetivos, sem nenhum julgamento (a IA continua
decidindo o que significam, regra 2). Entra no começo do texto que o modelo recebe.
- Word: título e idioma das propriedades, parágrafos com estilo de título, parágrafos que parecem título mas não têm
  estilo, sequências de parágrafos vazios usadas como espaçamento, imagens com e sem texto alternativo (com o texto de
  cada uma), tabelas com a marcação da linha de cabeçalho e células mescladas, hiperlinks e seus textos.
- PowerPoint: título e idioma das propriedades, por slide o layout, o título, as imagens com o texto alternativo de cada
  uma (a biblioteca preenche o nome do arquivo como texto alternativo, e isso agora fica visível), tabelas com
  cabeçalho, a ordem dos objetos e as notas.
- PDF: marcado ou não, árvore de estrutura, idioma, título, exibição do título, páginas sem texto extraível (podem ser
  digitalizadas), figuras da estrutura com e sem texto alternativo.
- EPUB: título, idioma, metadados de acessibilidade, documento de navegação e, por capítulo, idioma da página, títulos,
  imagens com e sem alt, tabelas com e sem células de cabeçalho.
- Quando algo não pode ser lido, o texto diz isso. Nunca fica em silêncio.
- Cada bloco termina com os limites do que a leitura não verifica (ordem de leitura real, contraste, o que um leitor de
  tela anuncia).

Testes novos: `tests/backend/unit/services/test_document_facts.py` (14 testes: defeitos reportados, texto alternativo
existente reportado, leitores com o bloco no começo, arquivo ilegível dito em voz alta, contagem de figuras do PDF com e
sem texto alternativo).

Defeito achado no próprio trabalho: a primeira versão do percurso pela árvore de estrutura do PDF não terminava quando o
leitor era um objeto de mentira, e a suíte inteira passou de 13 GB de memória. A causa provada: o percurso aceitava
qualquer objeto com o método get e nunca chegava ao fim. Agora só segue dicionários de PDF de verdade, cada um uma vez
(proteção contra referência circular de um PDF malformado) e diz quando a árvore é grande demais e a contagem é parcial.
Dois testes de regressão cobrem isso (o leitor de mentira e a árvore com ciclo).

## O que falta para concluir o módulo (precisa do modelo)

- Rodar pela interface um Word, um PowerPoint, um PDF, um EPUB e uma planilha com defeitos conhecidos e comparar a
  resposta com a verdade, medindo tokens por tipo de chamada.
- Confirmar que PDF e Excel chamam o especialista certo e que Word, PowerPoint e EPUB não chamam especialista à toa.
- Imagem anexada: ver se o modelo descreve, se a interface transcreve a imagem (regra 4) e o custo.
- Um arquivo corrompido e um arquivo protegido por senha, para a falha honesta e barata.
- Medir o custo do bloco de fatos: ele cresce o texto enviado ao modelo.

## Verificação feita até aqui: suíte completa do backend com 1.886 testes passando e 41 pulados, ruff e mypy limpos.

## Pendências já conhecidas

- O especialista de PDF e o de Excel recebem o texto com o bloco de fatos no começo, mas seus prompts não foram
  revisados para citar esses fatos. Não se sabe ainda se isso melhora a precisão.
- Não existe revisão de Word, PowerPoint ou EPUB feita por especialista: só o modelo do chat. É uma decisão de produto a
  conferir com o dono do projeto antes de mudar.
- A correção de documentos (gerar o arquivo corrigido) é do módulo 5.


## Provedores

<!-- PROTECOES:PROVEDORES:INICIO -->
Este módulo vale para todos os provedores (todas as regras do CLAUDE.md valem para todos). Estado de cada um, gerado de
`provedores/evidencias.json` por `scripts/update_protections.py` (não editar a mão):

- Ollama Cloud (Alto): PARCIAL em 08/10/2026. preparado sem o modelo; testes ao vivo pendentes por falta de cota. Ficha: `provedores/ollama-cloud.md`.
- Gemini (Alto): NÃO TESTADO.
- OpenAI: NÃO TESTADO.
- Anthropic: NÃO TESTADO.
- xAI (Grok): NÃO TESTADO.
- Factory AI: NÃO TESTADO.
- OpenCode Go: NÃO TESTADO.

O roteiro para testar um provedor novo, sem retrabalho, está em `provedores/_roteiro_para_novo_provedor.md`.
<!-- PROTECOES:PROVEDORES:FIM -->
