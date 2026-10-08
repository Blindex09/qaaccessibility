"""Protege contra geração degenerada em fluxo e deixa diagnóstico de chamadas longas.

Caso real (e2e de 2026-10-08): uma chamada de especialista ficou 29,7 minutos sem erro e sem fim, e nenhum custo foi
registrado para ela. Saída restrita por esquema JSON pode degenerar em espaços e quebras de linha sem parar: os dados
continuam chegando (então não é silêncio) e a chamada nunca termina. Isto detecta esse padrão por um fato objetivo
(uma longa corrida de pedaços vazios, só de espaço ou idênticos), que nenhuma resposta legítima produz, e encerra a
chamada como falha de provedor, para o orquestrador seguir com o parcial. Não é limite de tempo nem de tamanho do
trabalho: uma resposta longa e variada nunca é cortada.

Também registra, de tempos em tempos, o que a chamada longa está recebendo, para que a causa de uma nova chamada
presa fique provada no log em vez de adivinhada.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Quantos pedaços seguidos vazios, só de espaço ou iguais ao anterior caracterizam um fluxo degenerado. Um texto legítimo
# varia; mil pedaços assim em sequência são segundos de geração perdida, nunca uma resposta.
DEGENERATE_RUN = 1000
# De quanto em quanto tempo uma chamada que continua em fluxo deixa uma linha de diagnóstico no log.
DIAGNOSTIC_INTERVAL = 120.0


class DegenerateStreamError(RuntimeError):
    """A geração entrou num laço sem conteúdo (espaços, quebras de linha ou o mesmo pedaço repetido)."""


class StreamGuard:
    def __init__(self, label: str = "", run_limit: int = DEGENERATE_RUN, interval: float = DIAGNOSTIC_INTERVAL) -> None:
        self.label = label
        self.run_limit = run_limit
        self.interval = interval
        self.started = time.monotonic()
        self._last_log = self.started
        self.chunks = 0
        self.chars = 0
        self._run = 0
        self._previous: str | None = None
        self._tail = ""

    def observe(self, text: str) -> None:
        """Registra um pedaço recebido. Levanta DegenerateStreamError num fluxo degenerado."""
        self.chunks += 1
        self.chars += len(text)
        self._tail = (self._tail + text)[-80:]
        if not text.strip() or text == self._previous:
            self._run += 1
        else:
            self._run = 0
        self._previous = text
        if self._run >= self.run_limit:
            logger.error(
                "[Stream]%s fluxo degenerado: %d pedaços seguidos vazios ou repetidos (total %d pedaços, %d caracteres, "
                "%.0fs). Final recebido: %r",
                self._label(), self._run, self.chunks, self.chars, time.monotonic() - self.started, self._tail,
            )
            raise DegenerateStreamError(
                "A geração entrou num laço sem conteúdo (só espaços ou o mesmo trecho repetido) e foi encerrada."
            )
        now = time.monotonic()
        if now - self._last_log >= self.interval:
            self._last_log = now
            logger.warning(
                "[Stream]%s chamada longa em andamento há %.0fs: %d pedaços, %d caracteres, corrida de vazios/repetidos=%d. "
                "Final recebido: %r",
                self._label(), now - self.started, self.chunks, self.chars, self._run, self._tail,
            )

    def _label(self) -> str:
        return f" {self.label}" if self.label else ""
