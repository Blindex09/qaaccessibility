# Pendências do Qaaccessibility

## Decisões do dono de 20/out/2026 que ainda não estão no código

As regras estão em `.claude/rules/projeto-qaaccessibility.md` e `.claude/rules/aprendizado.md`. Falta o código, cada item com teste de regressão (regra 12) e prova ao vivo (regra 15):

1. Remover o painel de memória do chat (`web/src/screens/MemoryPanel.tsx` e o que o liga); memória só por conversa.
2. Rodar a suíte de testes gerada no computador da pessoa (`backend/src/services/remote_runners.py`, `local_exec_consent_store.py`) seguindo a chave de aprovação, com a lista do que vai instalar e rodar.
3. Conferir que analisar uma pasta inteira e exportar VPAT/relatórios continuam como decidido (sem aviso antes do envio e sem faixa no documento).
4. A mesma regra de aprendizado sem aviso e sem tela vale aqui; conferir o que a interface mostra do aprendizado hoje.
