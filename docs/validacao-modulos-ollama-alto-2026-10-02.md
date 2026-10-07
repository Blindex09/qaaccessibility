# Validação por módulo — Ollama Cloud Alto — 02/10/2026

Rodada em andamento. Este documento registra evidência desta execução, não
transforma relatos anteriores nem testes com mocks em validação ao vivo.

## Ambiente e escopo

- Backend em 8001; interface em 3000. Interface inicialmente desligada, iniciada nesta rodada.
- Configuração consultada: `ollama-cloud`, `alto`, credencial presente; sem divulgar a chave.
- Alvo público: https://www.w3.org/WAI/demos/bad/before/home.html.
- Referência independente: https://www.w3.org/WAI/demos/bad/ (demonstração W3C com relatórios de barreiras conhecidas, baseada em WCAG 2.0; não é cobertura integral de WCAG 2.2).
- GitHub, Jira e Azure DevOps explicitamente adiados pelo usuário.
- Não modificar o site remoto; correções apenas em cópias/artefatos de teste.

## Correções desta rodada

1. `API_TOKEeEN` impedia compilar/carregar o cliente do chat: corrigido para `API_TOKEN`.
2. Removida instrução fixa do botão Enviar; preservados nome acessível e estado disabled.
3. Supervisão SSE reavalia o deadline após timeout capturado antes da pausa humana ou adaptação. Regressão atravessa o prazo anterior durante aprovação.
4. Placeholders internos de URLs usam caracteres de uso privado, evitando erro de lint sem alterar as URLs restauradas.
5. Teste E2E antigo passa a procurar o cabeçalho `qaaccessibility` em vez de `IA ASSISTENTE`.
6. A árvore de acessibilidade usa o mesmo HTML capturado, evitando combinar o HTML do alvo com uma página de bloqueio capturada em outra navegação.
7. Cache de correções passa a guardar HTML original, não apenas o resumo semântico; resumo inclui fatos de existência dos destinos de fragmentos.
8. Ferramentas de auditoria no chat exigem que o modelo selecione explicitamente os especialistas. Os 29 especialistas foram preservados. Isso não comprova migração dos demais caminhos REST/batch.
9. Reserva adaptativa considera ondas da análise e não encolhe ao classificar chamadas auxiliares simples.
10. XLSX, EPUB e imagens passaram a ser enviados como binário/base64, não lidos como texto UTF-8. Regressões locais passaram; upload ao vivo desses formatos ainda pendente.
11. Ferramentas com aprovação no mesmo lote executam na ordem do modelo, sem disputar o único painel de perguntas. Digest de segurança continua interno, sem ocupar o cartão.
12. Checklist deixa de usar ausência de achados como prova de aprovação. Exportador remove alegações fixas de auditoria completa, axe-core e fala com NVDA/JAWS/VoiceOver; não infere localização por keywords nem idioma da página como português. Nível WCAG não define automaticamente a prioridade.
13. Ferramenta que retorna link de PDF declara geração sob demanda, não arquivo já produzido ou conformidade PDF/UA comprovada.

## Verificações locais

- Interface: 243 testes passaram; TypeScript passou; exportação web compilou.
- ESLint dos arquivos de interface alterados: passou após corrigir o delimitador de URLs.
- Ruff e mypy de `chat_runtime.py`: passaram.
- Backend completo: primeira rodada após mudanças teve 1724 passados, 41 omitidos e 1 falha no teste que ainda esperava redução da reserva. Contrato atualizado para preservar trabalho reservado; regressão passou. Omissões incluem suítes opt-in de provedores, não são cobertura ao vivo.
- Regressões de aprovação, execução, checklist e PDF: 35 passaram; última verificação do exportador e contratos: 30 passaram. Ruff e mypy dos módulos alterados passaram.
- Nova rodada unitária global em execução; registrar resultado final depois.

## Matriz ao vivo

| Módulo/capacidade | Estado nesta rodada | Evidência necessária |
|---|---|---|
| Chat, classificação e squad | Observado ao vivo, parcial | Seleção contextual e feed progressivo; revisão de precisão ainda tem ressalvas |
| Roteamento Alto | Observado nos logs | `RouteAdvisor source=ia`; registrar seleções reais |
| Auditoria URL | Executada com ressalvas | Rodada ampla expirou em 360s. Rodada focada com 4 especialistas terminou em 91s e 18 achados; escopos diferentes, não comparação direta de desempenho |
| Crawl de múltiplas páginas | Duas URLs explícitas executadas | 150s; 26 achados, por URL. Descoberta automática de links ainda não validada |
| Código/anexos/projeto ZIP | Pendente | Arquivos reais recebidos e achados contextualizados |
| Documentos e imagens | Pendente | Evidência específica de cada formato |
| Correção ZIP e preview | Pendente | Aprovação, download, conteúdo, antes/depois |
| Desfazer correção | Pendente | Estado restaurado na conversa |
| Checklist e PDF | Falha encontrada, regressão ao vivo em curso | Duas aprovações simultâneas ocultaram um portão. PDF baixado tinha 18 páginas, tags e pt-BR, mas metadados e aprovação de contraste sem sustentação. Não aprovado como relatório confiável; correções aplicadas e repetição em curso |
| XLSX | Pendente | Planilha válida e coerência com achados |
| VPAT | Pendente | Critérios e níveis sustentados por evidências |
| Declaração e PDF | Pendente | Sem certificação inventada; campos desconhecidos explícitos |
| SARIF | Pendente | Link no chat, arquivo válido e resultados reais |
| Geração de testes/scripts | Pendente | Código gerado verificável; geração ≠ execução |
| Execução remota/cross-browser | Pendente | Navegadores executados, falhas e resultados |
| Árvore de acessibilidade | Pendente | Inspeção real; não equivale a testar voz NVDA |
| Revisão de requisito/design | Pendente | Decisões sobre requisito sintético explícito |
| Pesquisa e avaliação de fontes | Pendente | Fontes retornadas e justificativa |
| Aprovação/cancelamento/redirecionamento | Pendente | Transições reais e preservação do progresso |
| Histórico e isolamento de conversas | Retomada observada | Conversa original reaberta após reinício; isolamento completo ainda não validado |
| Julgamento entre modelos | Pendente | Decisão IA, candidatos e julgamento realmente executados |
| Failover | Pendente | Falha controlada e recuperação; distinguir de queda real do provedor |
| Publicação GitHub/Jira/Azure | Adiado pelo usuário | Destino e autorização específicos |

Não há veredito de cobertura completa enquanto houver itens pendentes.

## Precisão ainda não encerrada

- Auditoria estática afirmou link de salto inoperante sem teste de teclado registrado. O destino existe; distinguir existência, efetividade e teste de interação.
- Multi-URL incluiu 3.3.2 apesar de escopo estrito 3.1.1/4.1.2; não considerar precisão e aderência completas.
- Primeiro PDF inventou aprovação de contraste apesar de rodada sem medição. Prompt e exportador corrigidos; é necessário confirmar o conteúdo da repetição.
- Cache HTML é em memória e não sobrevive ao reinício; issues e histórico persistem. Correção posterior ao reinício não deve prometer usar captura original disponível.
