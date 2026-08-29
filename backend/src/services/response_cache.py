"""Cache de respostas dos 25 agentes de análise (leaf, single-shot, sem tools).

Escopo deliberadamente restrito: só chamadas via `llm_client.call_llm` com
`toolsets` vazio/None (o mesmo escopo do `response_schema` de Structured
Outputs — ver `AIAgent.__init__::self.response_schema`). Turnos de chat com
tools nunca são cacheados: são conversacionais por natureza (histórico,
follow-up, streaming) e cachear a resposta quebraria a interatividade.

Cache exato (hash do prompt completo), não semântico. Uma cache semântica
(similaridade de embeddings) arriscaria dar cache-hit em HTML que mudou de
forma relevante para a acessibilidade mas é "parecido" na projeção vetorial —
inaceitável numa ferramenta cujo propósito é justamente detectar essas
mudanças. Exact-match com TTL curto é a escolha correta aqui: evita custo/
latência duplicados quando a mesma página é reanalisada sem alteração dentro
da janela (ex.: usuário reabre o relatório, múltiplas abas), sem risco de
mascarar uma mudança real no HTML.
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _Entry:
    value: str
    expires_at: float


class ResponseCache:
    """Cache em memória, por processo, com expiração por TTL e tamanho máximo (LRU)."""

    def __init__(self, max_entries: int = 256) -> None:
        self._max_entries = max_entries
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                del self._store[key]
                return None
            # Reinsere para o fim (recência) -- politica LRU simples via ordem de dict.
            self._store.pop(key)
            self._store[key] = entry
            return entry.value

    def set(self, key: str, value: str, ttl_seconds: float) -> None:
        with self._lock:
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._max_entries:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


_cache = ResponseCache()


def make_cache_key(*parts: object) -> str:
    """Hash estável das partes que definem uma resposta determinística."""
    str_parts = [json.dumps(p, sort_keys=True) if not isinstance(p, str) else p for p in parts]
    joined = "\x1f".join(str_parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> str | None:
    hit = _cache.get(key)
    if hit is not None:
        logger.info("[response_cache] hit key=%s", key[:12])
    return hit


def set_cached_response(key: str, value: str, ttl_seconds: float) -> None:
    _cache.set(key, value, ttl_seconds)


def clear_cache() -> None:
    """Usado por `llm_client.refresh_settings()` e pelos testes para isolar estado."""
    _cache.clear()
