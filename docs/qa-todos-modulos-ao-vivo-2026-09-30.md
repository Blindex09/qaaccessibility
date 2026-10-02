# Bateria ampla do QA Accessibility — em andamento

Pedido: testar todos os módulos e funcionalidades ao vivo pelo chat. Este arquivo
é um controle de cobertura, não uma declaração de aprovação do projeto.

## Regras da execução

- Interface real no Chrome, localhost:19006, backend localhost:8001.
- Provider salvo: Ollama Cloud, modo Alto, escolhas de modelo pelo roteador.
- Cenários fictícios e alvos públicos sem dados pessoais.
- Nenhum ticket externo, instalação ou alteração de projeto real sem autorização específica.
- Exportações/correções/execuções locais de teste aguardam autorização do usuário.
- Uma resposta convincente não prova execução: conferir ferramentas, logs e artefatos.
- Especialista relevante não acionado é cobertura pendente, não aprovação automática.

## Bateria local ampla

Backend: 1698 testes executados; 1690 passaram e 8 falharam (78,14s).
XML: `artifacts/qa-all-modules-offline-2026-09-30.xml`.

Frontend: 220 testes; 214 passaram e 6 falharam, 18 suítes aprovadas/1 reprovada.
JSON: `artifacts/qa-all-web-offline-2026-09-30.json`.

As suites locais não são cobertura ao vivo. Duas verificações de Browserless
acabaram capturando conteúdo real quando o teste esperava ausência de configuração:
o isolamento destas verificações não é hermético no ambiente configurado.

Falhas a investigar, sem correção nesta rodada:

| Área | Resultado observado |
|---|---|
| Observabilidade de aprovação | Teste espera approved, execução registra denied |
| Integração do portão | Teste tenta monkeypatch em run_agent.get_settings inexistente |
| Agent Card A2A | Anuncia 27 especialistas; catálogo possui 29 |
| Conhecimento gerado | Documento não corresponde à saída atual do gerador |
| Repo map | Mapa gerado não sincronizado |
| Browserless (2 testes) | Retorna árvore real, apesar de cenário esperar vazio |
| Detector de segredo | Sinaliza fixture textual `conteudo-privado-da-pagina`, não prova de chave real |
| Autoauditoria UI (6 testes) | Exige placeholder/rótulos removidos a pedido do usuário; inclui validação de disabled a conferir no DOM |

## Inventário de ferramentas do chat

Origem: registros reais em `backend/src/services/chat_tools.py` — 31 capacidades,
incluindo clarify em seu toolset próprio. Resultado de testes locais não substitui
a coluna de execução real abaixo.

| Capacidade | Cobertura ao vivo nesta rodada |
|---|---|
| consult_squad | Em teste no cenário HTML |
| analyze_page | Em teste no cenário HTML |
| analyze_site | Pendente |
| unzip_and_list_files | Pendente; fixture ZIP |
| read_local_project_files | Aguarda autorização para fixture local |
| fix_local_project_files | Aguarda autorização; somente cópia fictícia |
| analyze_document | Pendente; PDF/Word/Excel fictícios |
| fix_and_zip_files | Aguarda autorização; somente fixture |
| undo_last_fix | Aguarda autorização; somente resultado de fixture |
| export_xlsx | Aguarda autorização |
| generate_checklist | Aguarda autorização |
| export_checklist_pdf | Aguarda autorização |
| generate_accessibility_statement | Aguarda autorização |
| export_accessibility_statement_pdf | Aguarda autorização |
| generate_vpat | Aguarda autorização |
| generate_test_suite | Aguarda autorização |
| open_live_preview | Pendente; depende de resultado corrigido |
| tavily_search | Pendente |
| exa_search | Pendente |
| evaluate_research | Pendente |
| create_github_issue | Pendente de destino de teste e aprovação específica; não publicar em projeto real |
| create_jira_issue | Pendente de destino de teste e aprovação específica |
| create_azure_devops_work_item | Pendente de destino de teste e aprovação específica |
| verify_screen_reader_announcements | Aguarda autorização; não equivale a teste auditivo humano com NVDA |
| design_review | Pendente; captura visual |
| generate_automation_script | Aguarda autorização |
| run_remote_test | Aguarda autorização e runtime disponível |
| run_cross_browser_test | Aguarda autorização e motores disponíveis |
| install_playwright_browsers | Pendente de necessidade constatada e aprovação específica de instalação |
| run_deep_research | Pendente |
| clarify | Em teste de pedido sem alvo |

## Cobertura de UI e pipeline

| Fluxo | Estado |
|---|---|
| Nova conversa | Executado para isolar cenários |
| Histórico/restauração | Histórico anterior restaurado; seleção de outra conversa pendente |
| Mensagem fixa Processamento concluído | Não aparece no histórico restaurado observado |
| Campos/botões e teclado | Inspeção parcial; teste completo pendente |
| Streaming e progresso navegável | Em observação |
| Parar/cancelar | Pendente |
| Redirecionar | Enviado durante triagem; verificar escopo final |
| Pergunta material | Em execução |
| Roteamento/classificação/squad | Em execução; não inferir julgamento cruzado sem comparação nos logs |
| Configurações/catalogo/modelos | Pendente; sem exibir credenciais |
| 29 especialistas | Unitários exercitados; execução real por especialista ainda pendente |
| A2A/webhooks/telemetria/batch | Cobertura local parcial; testes reais específicos pendentes |
| Outros providers | Não exercitados ao vivo; não extrapolar Ollama para todos |

## Cenários iniciados

1. HTML com imagem sem alt, campo email sem rótulo, botão vazio e div clicável.
   Redirecionamento enviado durante streaming restringindo a primeira etapa a nomes
   acessíveis do campo/botão, sem modificação. Resultado final ainda em observação.
2. Pedido “Audite a acessibilidade para mim.” sem alvo. Esperado: perguntar cedo,
   sem inventar site nem iniciar auditoria arbitrária. Em observação.
