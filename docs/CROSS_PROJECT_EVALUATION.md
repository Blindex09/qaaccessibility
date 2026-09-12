# Avaliação cross-project do QA Accessibility

`tools/cross_project_evaluator_matrix.py` é o ponto de entrada para executar o
QA Accessibility como agente sob avaliação. Ele reutiliza as trajetórias reais
geradas pelo QA e chama os adaptadores nativos dos projetos que possuem contrato
de avaliação:

- agent-eval-harness, Agent Health, A2E, AgentFit, agentevals, AgentOps-Bench e
  HarnessFix;
- skillgate e unlazy como gates determinísticos do repositório.

O relatório é gravado em
`docs/audits/cross-project/external-evaluator-matrix.json` e sempre contém os
14 projetos encontrados em `C:\aprovacao` e `C:\confirmacao`. Projetos que são
runtime, biblioteca ou skill sem uma interface de avaliação externa recebem
`not_applicable`; seus testes próprios não são apresentados como uma auditoria
do QA.

Para repetir a execução:

```powershell
& .venv\Scripts\python.exe tools\cross_project_evaluator_matrix.py
```

O comando retorna código diferente de zero quando um adaptador disponível
falha ou não pode ser executado.
