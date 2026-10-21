# Correção das orientações de conformidade

20 de outubro de 2026

A criação do módulo de documentos no MCP revelou que os dois prompts de vpat_reporter aprovavam automaticamente ausência de achados e violações de baixa gravidade. A correção foi aplicada aqui, como fonte dos playbooks, e no guia specialist-vpat-reporter do MCP.

O modelo deve julgar o critério pela evidência e pela cobertura. Gravidade é prioridade de correção, não prova de conformidade. Avaliação incompleta permanece não avaliada e preserva nas observações as falhas já conhecidas. Uma conclusão positiva exige avaliação completa do escopo e evidências positivas. Inaplicabilidade exige justificativa própria.

Verificações locais: ruff do arquivo, mypy do arquivo e os oito testes de tests/backend/unit/agents/test_vpat_reporter.py passaram. Esses testes usam respostas simuladas e não provam comportamento de provedores reais.

O guia equivalente foi avaliado no cliente Codex em oito casos sintéticos, repetidos três vezes: 24 de 24 decisões esperadas. Removendo a seção corrigida, o resultado foi 18 de 24, com aprovação indevida de violação leve e conclusão sobre avaliação incompleta. As justificativas foram lidas. O procedimento reproduzível e os limites estão no MCP, em scripts/eval_document_guidance.py e docs/modules/documentos_acessiveis.md.

Não houve avaliação ao vivo dos provedores do Qaaccessibility nesta entrega. A observação em uso real e o portão completo por provedor continuam pendentes. Esta correção de orientação não conclui um novo módulo funcional nem certifica relatórios anteriores.
