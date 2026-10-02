# Comparação e migração do roteamento contextual

Escopo: roteador, classificação conversacional e aplicação das regras mestras
nesses caminhos. Não é certificação de todo o sistema nem de qualidade de
auditorias. NVDA Studio foi inspecionado sem alterações.

## Evidências locais

Referência: `C:/nvdastudio/addon/globalPlugins/nvdastudio/ai/route_advisor.py`,
`ai/model_router.py`, `gui/studio_dialog.py`, `C:/nvdastudio/AGENTS.md` e
`C:/nvdastudio/CLAUDE.md`. Destino: `backend/src/services/route_advisor.py`,
`llm_client.py`, `chat_runtime.py`, `model_arbitration.py` e clarifier.

| Aspecto | Studio inspecionado | QA após alteração |
| --- | --- | --- |
| Escolha automática | IA ordena candidatos com fatos e hints | IA classifica contexto e ordena candidatos; caminho normal não chama pontuação antiga |
| Classificação | Intenção, complexidade, preferência e capacidades no diálogo | Triagem recebe histórico e pedido; consultor retorna complexidade, preferência e plano de modelos |
| Capacidades | Caminho de provider fixo pode relaxar requisitos | Novo consultor não relaxa ferramentas/visão; capacidades Ollama declaradas, não inferidas pelo nome |
| Cache de conselho | Chave usa IDs/hints/tarefa; sucesso sem expiração | Chave inclui contexto completo e fatos/telemetria, TTL de cinco minutos; configuração invalida |
| Julgamento de respostas | Não encontrado nesse consultor | IA decide participantes e julgador; chamadas limitadas, resposta julgada entra no cache |
| Falha do consultor | Contingência por confiabilidade | Contingência explícita, uma reparação de contrato dentro do mesmo prazo |

O Studio estava mais alinhado que o QA anterior na escolha semântica de modelos.
O novo QA acrescenta validações e invalidação de cache mais estritas. Isso não
prova superioridade geral: capacidade disponível e qualidade do plano continuam
dependendo do catálogo e da IA. O catálogo genérico não documenta visão para
todos os providers; capacidade desconhecida não é concedida por suposição.

## Regras mestras

Corrigida contradição de AGENTS.md/CLAUDE.md e documento de engenharia:
escolha semântica de modelo é da IA, elegibilidade e limites são do harness.
Credenciais e endpoints são resolvidos por provider e nunca transferidos de um
provider para outro. O consultor roda sem ferramentas, sem fallback implícito,
com bootstrap explícito e sem chamar o próprio roteador. Dados remotos não
alteram lista de modelos permitidos ou permissões. Sem mudanças de leitura
automática, navegação por setas ou remoção de especialistas.

Limites de escopo: funções síncronas anteriores permanecem para modelo manual,
batch, flag desativada e fallback de contrato estruturado. Não é correto dizer
que todo código antigo foi removido. Cancelamento de transporte em thread é
best-effort; prazo limita espera, não encerra à força uma requisição de rede.
Não foi auditado aqui todo o permissionamento, sandbox e steer de cada provider.

## Verificação

Testes de contrato do consultor cobrem IDs inválidos, duplicatas, timeout,
credenciais, contexto completo, catálogo atualizado, capacidades sem inferência
pelo nome e reparação. Integração de leaf confirma seleção, comparação e juiz,
cache da resposta julgada e ausência de chamada ao roteador de pontuação antigo.
Regressão cobre transporte, router síncrono, complexidade, clarifier e helpers
de chat. Ruff e mypy são executados nos módulos tocados.

Validação real: `python -m tools.validate_route_advisor --live`, com a chave
protegida já configurada, sem exibi-la. Nas tentativas iniciais houve planos
com IDs inválidos, corretamente rejeitados. Na última execução: saudação
classificada como low/cost, deepseek-v4.1-flash, sem comparação; caso combobox
classificado high/quality, gemma4:31b e deepseek-v4.1-flash como participantes,
kimi-k2.7-code como juiz. Estes são resultados observados, não modelos fixados
nem prova estatística de qualidade. O teste real executa o consultor, não uma
auditoria completa nem E2E da interface.

Backend já aberto não foi reiniciado nesta alteração. A ativação desse código
na interface exige recarregar/reiniciar o processo que não usa hot reload.
