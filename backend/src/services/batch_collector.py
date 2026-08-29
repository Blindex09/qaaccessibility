"""Modo de coleta pra Batch Inference (ver batch_inference.py).

Problema: os 25 agentes de análise cada um constrói seu próprio prompt e
chama `llm_client.call_llm` internamente -- não há um ponto único de fora do
orchestrator pra saber "quais chamadas ELE vai fazer" sem reescrever os 25
agentes pra separar "montar prompt" de "chamar e parsear".

Solução: uma passada de COLETA. `orchestrate(..., batch_collect=True)` roda o
pipeline normal (mesma seleção de agente, mesmo prompt de cada agente), mas
com este modo ativo `call_llm` nunca liga pro provider -- em vez disso grava
(provider, model, system_prompt, user_prompt) aqui e devolve `"[]"` (sentinela
que todo agente já trata como "nenhum issue encontrado", o caminho mais comum
e testado de cada um deles). O resultado dessa passada é descartado -- só serve
pra descobrir quais chamadas seriam feitas.

Depois: as chamadas coletadas viram UM job de batch de verdade
(`batch_inference.submit_batch`). Quando o batch termina, os resultados reais
são inseridos no `response_cache` sob a MESMA chave que `call_llm` computa
normalmente, e o pipeline roda uma SEGUNDA vez (modo de coleta desligado) --
dessa vez cada `call_llm` acerta a cache com o texto real, e cada agente faz
seu próprio parsing/validação sem nenhuma alteração no código dos 25 agentes.

Duas ContextVars separadas, de proposito:

- `_pending` (a LISTA): vinculada UMA VEZ pelo chamador (a rota), antes do
  loop de páginas -- persiste através de múltiplas chamadas sequenciais a
  `orchestrate()` (uma por página), acumulando tudo num só lugar.
- `_active` (o INTERRUPTOR): ligado/desligado pelo PRÓPRIO `orchestrator.py`,
  só em torno do `asyncio.gather` dos agentes de análise -- nunca em torno da
  chamada do classificador, que decide quais agentes rodar e por isso precisa
  ser real mesmo durante a coleta.

Isolamento entre requisições concorrentes vem de graça do jeito que
`contextvars.Context` funciona: cada requisição HTTP roda na sua própria task
asyncio com seu próprio contexto: variáveis lidas por uma vêm ao herdar do pai
no momento em que a task foi criada, e um `.set()` numa task filha nunca volta
pra o pai nem pras irmãs -- mas mutar o MESMO objeto lista (`.append`) que
todas herdaram por referência SIM propaga, que é exatamente o que
`asyncio.gather` precisa aqui pra agregar as chamadas dos agentes em paralelo.
"""

import contextvars
from dataclasses import dataclass


@dataclass(frozen=True)
class CollectedRequest:
    cache_key: str
    provider: str
    model: str
    system_prompt: str
    user_prompt: str


_active: contextvars.ContextVar[bool] = contextvars.ContextVar("batch_collect_active", default=False)
_pending: contextvars.ContextVar[list[CollectedRequest] | None] = contextvars.ContextVar(
    "batch_collect_pending", default=None
)


def bind_pending_list() -> tuple[contextvars.Token, list[CollectedRequest]]:
    """Chamado UMA VEZ pela rota, antes do loop de páginas. Devolve o token
    (para `unbind_pending_list`) e a lista que vai acumular tudo."""
    pending: list[CollectedRequest] = []
    return _pending.set(pending), pending


def unbind_pending_list(token: contextvars.Token) -> None:
    _pending.reset(token)


def enable() -> contextvars.Token:
    """Chamado pelo `orchestrator.py`, só em torno do gather dos agentes."""
    return _active.set(True)


def disable(token: contextvars.Token) -> None:
    _active.reset(token)


def is_collecting() -> bool:
    return _active.get()


def record(cache_key: str, provider: str, model: str, system_prompt: str, user_prompt: str) -> None:
    """Grava uma chamada que TERIA sido feita. No-op se nenhuma lista estiver
    vinculada (defensivo -- `call_llm` já checa `is_collecting()` antes)."""
    pending = _pending.get()
    if pending is None:
        return
    pending.append(
        CollectedRequest(
            cache_key=cache_key,
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    )
