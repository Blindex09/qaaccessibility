# Roteiro para colocar um provedor novo à prova (qualquer provedor)

Vale para OpenAI, Anthropic, xAI, Factory, OpenCode Go e qualquer outro. Todas as regras mestras do CLAUDE.md valem para todos os
provedores, sem tratamento especial. O objetivo é quase nenhum retrabalho: cada passo abaixo existe porque um defeito real já
custou retrabalho em um provedor.

## Antes de testar

1. Chave nova e limpa. Uma chave que passou por repositório público ou por qualquer lugar exposto pode já estar bloqueada
   (o Google bloqueou uma). Ela vai para o cofre pela tela de Configurações, que guarda uma chave por provedor. Trocar de
   provedor nunca apaga a chave de outro.
2. Copiar o cofre e os registros antes de reiniciar qualquer coisa (regra 17: evidência perdida não se prova depois).
3. Gravar o contrato real do provedor: `scripts/record_provider_contract.py --provider <provedor>` (texto, fluxo e chamada de
   ferramenta). Se o provedor ainda não tem gravador, escrever um no mesmo molde (`RECORDERS` no script). Nunca escrever o leitor
   do fluxo de cabeça: o do Gemini foi escrito para um formato que a API já não enviava, e os testes usavam esse formato
   inventado.
4. Escrever os testes de contrato em cima da gravação (modelo: `tests/backend/unit/providers/test_gemini_contract.py`): texto em
   fluxo chega ao usuário, custo medido (nunca zero), ciclo completo de ferramenta, fluxo cortado é falha e não resposta vazia,
   tipos de evento novos acusam mudança.

## Testar ao vivo, pela interface, um módulo de cada vez

5. Rodar os cenários do módulo (`scripts/verify_live_modules_1_to_3.py --provider <provedor> --only m1`) e também conferir pela
   interface como uma pessoa usaria. Medir tokens por tipo de chamada (linha `[Custo]` do log).
6. Para cada defeito: provar a causa (regra 17), corrigir, escrever o teste de regressão e dizer o que NÃO está provado. Defeito
   que só aparece em um provedor se corrige dentro do caminho daquele provedor em `run_agent.py`. Defeito em arquivo
   compartilhado exige a suíte completa e, havendo cota, o script ao vivo no Ollama Cloud.
7. Cota ou limite de ritmo: parar no primeiro 429, registrar o ponto exato e não insistir.

## Registrar (sempre, no mesmo commit)

8. Ficha do provedor em `docs/modules/provedores/<provedor>.md`: como o produto fala com ele, o que funciona (com números), o que
   não foi testado, particularidades e defeitos com a causa de cada um, como repetir e pendências.
9. Matriz `docs/modules/paridade_provedores.md`: PROVADO, PARCIAL ou NÃO TESTADO por módulo e por provedor.
10. Seção "Provedores" no README do módulo testado, apontando para a ficha.
11. Commit com mensagem que diga o que funcionou, o que foi corrigido e o que ficou pendente. Nada de merge sem autorização.

## Antes de dar por pronto

12. Suíte completa (backend e front), ruff, mypy e tsc verdes, e o `--check` do gravador sem mudança de formato.
13. Conferir que o provedor anterior continua intacto: trocar de volta pela API e ver que a chave dele segue ativa; rodar o
    script ao vivo nele quando houver cota.
