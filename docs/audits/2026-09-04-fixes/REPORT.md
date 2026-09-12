# Correções e revalidação — 2026-09-04

> Atualização posterior: os 41 testes opt-in foram executados com Factory e
> **41/41 casos distintos passaram após reexecuções**. Ver [REAL-41.md](REAL-41.md)
> e `real-41-summary.json`. A quota Ollama permanece bloqueada; os números e
> limites abaixo registram a rodada anterior a essa ampliação.

Escopo: corrigir as falhas confirmadas da auditoria anterior e repetir verificações
baratas antes das chamadas reais. O relatório anterior permanece como baseline;
seus gates e resultados não representam o estado depois destas correções.

## Correções

- Factory: preservação do histórico, system prompt, schema estruturado, imagens
  inline, streaming, contadores reais de uso, limite de chamadas e cancelamento.
  As ferramentas usam a ponte do QA e continuam passando pelo executor e pelas
  verificações de aprovação existentes. Erros conhecidos ocultam a chave.
- A execução real descobriu dois problemas que mocks não mostraram: os IDs do
  Droid são `qa___ferramenta`, e a ponte MCP exige uma resposta de permissão.
  A autorização agora aceita somente ferramentas registradas nessa ponte.
  Lista vazia de restrições é tratada como irrestrita pelo runtime; por isso o
  caminho sem ferramentas usa um identificador impossível. Comandos nativos
  ficam bloqueados. Isto é controle de ferramentas, **não sandbox de SO**.
- Análise parcial: aviso, métricas e `complete=false` chegam ao chat; o score
  é nulo, nunca 100 quando um especialista falhou.
- Revisor: schema explícito e lotes de seis itens; duração real e erro visíveis
  na orquestração, em vez de duração zero.
- Catálogo: exceção de `kimi-k3` restrita ao Factory, que expõe esse ID; a
  regra para outros providers continua sendo testada.
- Frontend: limpeza de timers e cancelamento ao desmontar; cancelamento do
  servidor encerra o streaming; conclusão antiga não limpa um turno novo.
- Dependências: SDK Factory com suporte MCP e `httpx2` para o TestClient do
  Starlette atual; removido o filtro que escondia a depreciação.

## Evidências

- Backend completo: última execução **1.577 passaram, 41 ignorados**, sem falhas
  (`backend.xml`, 296,93 s). Dois testes adicionados após a coleta dessa suíte
  também passaram na rodada focal final abaixo; não somar rodadas sobrepostas.
- Contratos Factory, análise parcial e revisor: **31 testes passaram** na rodada
  final, incluindo cancelamento, imagens, permissões e lotes (`regressions.xml`).
- Ruff: sem violações nos arquivos verificados; mypy: **185 arquivos aprovados**.
- Frontend: **200 testes / 18 suites passaram**, saída natural sem `forceExit`
  nem silenciamento; TypeScript e ESLint dos arquivos alterados passaram.
- Chromium/axe: **6 testes passaram**, incluindo contraste e botão Enviar
  inicialmente desabilitado.
- Importação do TestClient em processo novo com depreciações como erro: passou.
- `pip check`: nenhuma dependência quebrada.
- Factory real, sem substituir SDK: **4/4 golden scenarios**, cobrindo imagem
  sem alt, imagem decorativa, botão sem nome e tentativa de prompt injection.
- Factory real com ferramenta: exatamente uma execução retornou um nonce que
  não existia no prompt; streaming e uso não nulo registrados em `tools.json`.
- Trajetória real automática: `trajectory.json` registra todos os passos,
  inclusive revisor, completude e duração; `verify_evidence.py` rejeita qualquer
  passo com falha. Duas rodadas passaram com **18/18 passos**; a última levou
  299,38 s, retornou 18 issues e teve `complete=true`, sem warning.
- Skillgate: **5/5 gates passaram** com a especificação desta pasta. O gate de
  runtime verifica a amostra Factory, não certifica disponibilidade Ollama.

Comandos reproduzíveis estão em `skillgate.yaml`, `run_live.py` e no XML/log.
As chamadas reais utilizam credencial autorizada em memória; ela não integra
os artefatos. `auto` é seleção dinâmica do Factory, não versão fixa de modelo.

## Limites que continuam explícitos

- Os 41 testes reais opt-in do Ollama não contam como aprovados. A auditoria
  anterior encontrou HTTP 429 de quota; este bloqueio externo não foi corrigido
  alterando código nem substituindo respostas por mocks.
- Há avisos de `act(...)` no log de testes frontend e de compatibilidade/
  depreciação Expo/Webpack no servidor de desenvolvimento. Os processos encerram
  e os testes passam, mas não se afirma ausência de todos os warnings.
- Amostra pequena de agentes não mede taxa geral de falsos positivos, estabilidade
  em múltiplas repetições, todas as ferramentas ou todos os tipos de página.
- Não houve certificação de produção, monitoramento contínuo implantado, auditoria
  humana completa ou prova do fluxo inteiro navegador → backend → relatório.
- Esta rodada executou o Skillgate clonado; não reaplicou a skill Unlazy nem
  integrou ArgusAgent, Horizon, Zaofu, ADL ou Aga Verify Agent como novos motores.

Resultado: falhas reproduzidas corrigidas e revalidação com evidências separadas
entre testes simulados e runtime real. **Não equivale a aprovação irrestrita de
produção.**
