Resposta ao usuário: o que a plataforma é, todos os módulos e a auditoria. Data: 02/10/2026.

Uso real de hoje, feito por mim na interface http://127.0.0.1:3000 como um usuário comum.

Primeiro pedi, em linguagem natural: analise a acessibilidade de https://example.com e me diga a nota e os problemas. Em 106 segundos respondeu: nota 60, oito problemas de severidade média, cada um explicado em linguagem de gente (exemplo: a falta de marcas de navegação é como entrar numa sala sem portas nem etiquetas para quem usa leitor de tela). A equipe interna (Tech Lead e QA Lead) narrou o plano no feed de progresso.

Depois pedi, na mesma conversa: gere o checklist de acessibilidade em PDF para baixar. O cartão de aprovação apareceu em 8 segundos. Fiquei 20 segundos pensando e o turno não morreu, porque a espera do usuário não consome o orçamento (correção de ontem funcionando). Aprovei. No meio apareceu um aviso amarelo honesto de que a primeira tentativa não concluiu, a ferramenta tentou de novo e concluiu: PDF do checklist pronto. Baixei o arquivo e conferi: 92.451 bytes, assinatura %PDF-1.7, PDF acessível com 10 itens.

Serviços de pé agora: backend na porta 8001 respondendo 200, frontend na porta 3000 respondendo 200, provedor Ollama Cloud no modo Alto.



O QUE A PLATAFORMA É

Um assistente de acessibilidade com o qual você conversa em português. Você digita um pedido ou anexa um arquivo ou imagem, ela examina a página, o site, o projeto ou o screenshot como um usuário com deficiência olharia, encontra os problemas, explica o que cada um significa na vida real e conserta o código quando você pede, entregando o arquivo pronto para baixar. Segue as normas oficiais: WCAG 2.2, WAI-ARIA, ADA/Section 508 e EN 301 549.

TODOS OS MÓDULOS

1. Os trinta especialistas de auditoria (os olhos). Rodam em paralelo, cada um com um foco: os quatro princípios do WCAG (percebível, operável, compreensível, robusto), ARIA e widgets (modais, abas, acordeões), CSS e contraste, conteúdo dinâmico e SPAs, barreiras cognitivas e CAPTCHA, os frameworks React, Vue, Angular, Svelte, Tailwind e Web Components, formulários, tabelas, texto de links, títulos e landmarks, leitor de tela, escolha de padrão de interação, mobile web, PDF, Excel, domínios de nicho (3D, passkeys, quiosques, e-mails) e compliance formal. Depois de todos ouvirem, um revisor sênior remove os falsos positivos antes de te contar (na rodada real, nove achados viraram seis). Também existe memória de falsos positivos e pesquisa da norma oficial quando um especialista tem dúvida.

2. Quatro portas de entrada. O chat na interface web (a principal, para qualquer pessoa), a API REST (para times de desenvolvimento), o servidor MCP (para outras IAs usarem as ferramentas) e o protocolo A2A (para federação de agentes entre empresas).

3. O que o chat sabe fazer. Analisar qualquer URL, inclusive páginas com JavaScript; analisar arquivo HTML, CSS e JS; analisar um projeto inteiro por anexo; analisar imagem e screenshot; rastrear um site inteiro com as subpáginas; corrigir o código com prévia do antes e depois e arquivo ZIP para baixar, sempre pedindo sua aprovação antes; gerar checklist e o PDF dele; gerar planilha XLSX colorida por severidade; gerar o VPAT, o documento formal de conformidade; gerar uma suíte de testes Playwright pronta para o CI; gerar relatório SARIF que aparece direto no Pull Request no GitHub ou GitLab; gerar a declaração de acessibilidade em PDF; abrir ticket no Jira ou Azure DevOps a partir de um achado; revisar um requisito antes de qualquer código existir; verificar os achados contra a árvore de acessibilidade real do navegador, a mesma API que os leitores de tela consultam.

4. A squad. Seis papéis com responsabilidade real: Product Owner (escopo e critérios de aceite), Tech Lead (abordagem técnica), Engineering Manager (sequenciamento), QA Lead (evidência e veredito), Scrum Master (desbloqueio) e Release (prontidão e risco). O quadro é visível e persiste por conversa, e os portões são de verdade: a entrega não fecha sem documentação, que não fecha sem QA.

5. As proteções. A inteligência decide o que fazer e o código determinístico decide o que é permitido; nenhuma ação crítica executa sem aprovação humana (a configuração não desliga esse portão); esperar por você não consome o orçamento do turno; há botão de parar e de redirecionar no meio do turno sem perder o progresso; existe um único orçamento de tempo por turno que se adapta à complexidade; se o teto chega, entrega o que provou e diz o que falta, sem fingir; o roteador escolhe o melhor modelo de IA para cada tarefa no modo Alto; se um provedor cai, tenta o próximo automaticamente.

AUDITORIA: ESTÁ TUDO TESTADO?

Testado e funcionando, com evidência:
- Análise por URL com squad e especialistas: feito há minutos por mim na interface. Nota 60, oito problemas.
- Checklist em PDF com aprovação humana no meio: feito há minutos por mim. Cartão, pausa de 20 segundos sem terminar o turno, PDF baixado e verificado (92 KB, %PDF-1.7).
- Correção de código com ZIP e preview ao vivo: ontem e hoje na interface, ZIP baixado com as correções.
- Espera do usuário não gasta orçamento: provado hoje com log do backend (restante 167 segundos antes e depois de uma espera de 76,6 segundos).
- Correção depois de rastrear um site sem re-analisar a página: provado hoje na interface e no log, nenhum novo scrape.
- Suíte completa de testes do backend: hoje, 1716 testes passando, zero falhas, 41 pulos justificados.
- Suíte de testes da interface (Jest): 225 de 225.
- Lint e tipagem (ruff, mypy, tsc): zero erros nas entregas.
- Doze módulos testados de ponta a ponta na interface real: rodada de 01/10/2026 (análise por URL, análise por anexo, correção com ZIP, checklist com PDF, XLSX, quatro frameworks, crawl, SARIF, VPAT, suíte de testes, preview ao vivo, declaração de acessibilidade).
- Cada bug de produto encontrado ganhou teste de regressão: seis bugs, todos com teste dedicado.

Não testado ou em aberto, dito sem rodeio:
- A arbitragem entre modelos de IA nunca foi acionada de verdade (o roteador nunca precisou comparar candidatos).
- A cascata de failover não foi exercitada com um provedor real caindo.
- O NVDA com voz real não rodou nos testes (sem serviço na máquina); a verificação de leitor de tela usou o motor do Chromium.
- O preview ao vivo aponta para localhost; em acesso de outro computador da rede o link de download resolve, mas o painel do preview continua fixo (única limitação de produto aberta).
- O rastreamento de sites com muitas páginas não guarda o HTML para correção posterior, só o de página única (decisão deliberada).
- 41 testes ficam pulados por dependência de ambiente, justificados.

VEREDITO

Sim. Um usuário pode usar a plataforma hoje pela interface, em linguagem natural, e ela entrega o que promete nos fluxos auditados: analisar, explicar, corrigir com sua aprovação e entregar os documentos (ZIP, PDF, XLSX, VPAT, SARIF, suíte de testes, declaração). O comprovante é o uso real de hoje mais as suítes verdes (1716 e 225 testes, zero falhas) mais os doze módulos validados ao vivo mais seis bugs corrigidos com regressão. Seguindo as regras do CLAUDE.md: lint limpo, testes verdes, contratos conferidos dos dois lados e honestidade sobre o que ainda não está provado.