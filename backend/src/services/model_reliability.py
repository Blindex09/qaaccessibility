"""
model_reliability.py
Telemetria de confiabilidade e latência OBSERVADA por modelo real, consumida pelo
roteamento "Alto" (ver ollama_cloud_adapter.score_ollama_cloud_model) para substituir
valores fixos por dados de verdade.

Antes desta telemetria, `reliability_score` no roteador Ollama Cloud era uma
constante hardcoded (0.95, sempre) e `latency_score` vinha de uma heurística de
substring no nome do modelo (`"flash" in id`, `"lite" in id`) -- nenhum dos dois
refletia o comportamento real observado. Padrão de gateways de produção 2026
(Bifrost/LiteLLM, OpenRouter Auto Router): o roteador aprende com o histórico
real de chamadas -- um modelo que está falhando ou lento cai no ranking
automaticamente, sem intervenção manual e sem lista fixa de "modelo bom".

Confiança gradual via shrinkage bayesiano (achado real 2026-08-26, auditoria
`docs/auditoria-portado-de-agentic-2026-08-26.md`, item 3 -- mesma constante
K=20 de `C:\\agentic`): antes, o corte era binário (< 5 tentativas = 100%
prior neutro; >= 5 = 100% taxa observada). A tentativa #5 pesava 0->100% de
repente -- uma falha isolada de infra (503, timeout) bem na 5a tentativa
derrubava o modelo inteiro do ranking. Agora:

    confidence = tentativas / (tentativas + K)
    score = (1 - confidence) * prior_neutro + confidence * taxa_observada

Com 1 tentativa, confiança ~4,8% (quase todo prior ainda). Com 20 tentativas,
confiança exatamente 50%. Com volume grande, aproxima da taxa observada mas
nunca chega a 100% -- o prior nunca é totalmente descartado.

Persistido em disco (mesmo padrão de last_analysis_store.py: memória + espelho
em arquivo) para sobreviver a reinícios do processo -- sem isso, o roteador
"esquece" tudo a cada deploy e nunca converge.
"""

import json
import logging
import math
import os
import tempfile
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

RELIABILITY_SHRINKAGE_K = 20
NEUTRAL_RELIABILITY = 0.75
NEUTRAL_LATENCY_SCORE = 0.75
_MAX_TRACKED_MODELS = 512
_EWMA_ALPHA = 0.3  # peso da amostra mais recente na média móvel de latência


def _shrinkage_confidence(attempts: int) -> float:
    """Confiança gradual (0..1) na taxa observada, crescente com o volume de
    amostras, sem nunca chegar a 100% -- ver nota do módulo."""
    return attempts / (attempts + RELIABILITY_SHRINKAGE_K)


def _store_path() -> str:
    return os.path.join(tempfile.gettempdir(), "qa_accessibility_model_reliability.json")


@dataclass
class _ModelStats:
    attempts: int = 0
    successes: int = 0
    latency_ewma_ms: float = 0.0


class ModelReliabilityStore:
    """Em memória por processo, espelhado em disco. Thread-safe (record() é
    chamado de volta na event loop após `asyncio.to_thread`, mas mantemos o
    lock pelo mesmo motivo de response_cache.py: seguranca sob qualquer
    topologia de execução, não só a atual)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, _ModelStats] = {}
        self._load()

    @staticmethod
    def _key(provider: str, model: str) -> str:
        return f"{provider.strip().lower()}::{model.strip().lower()}"

    def record(self, provider: str, model: str, success: bool, duration_ms: float) -> None:
        if not provider or not model or duration_ms < 0:
            return
        key = self._key(provider, model)
        with self._lock:
            if key not in self._stats and len(self._stats) >= _MAX_TRACKED_MODELS:
                oldest_key = min(self._stats, key=lambda k: self._stats[k].attempts)
                del self._stats[oldest_key]
            stats = self._stats.setdefault(key, _ModelStats())
            stats.attempts += 1
            if success:
                stats.successes += 1
            stats.latency_ewma_ms = (
                duration_ms
                if stats.latency_ewma_ms == 0.0
                else _EWMA_ALPHA * duration_ms + (1 - _EWMA_ALPHA) * stats.latency_ewma_ms
            )
        self._save()

    def reliability_score(self, provider: str, model: str) -> float:
        stats = self._get(provider, model)
        if stats is None or stats.attempts == 0:
            return NEUTRAL_RELIABILITY
        observed = stats.successes / stats.attempts
        confidence = _shrinkage_confidence(stats.attempts)
        return (1 - confidence) * NEUTRAL_RELIABILITY + confidence * observed

    def latency_score(self, provider: str, model: str) -> float:
        stats = self._get(provider, model)
        if stats is None or stats.attempts == 0 or stats.latency_ewma_ms <= 0:
            return NEUTRAL_LATENCY_SCORE
        # Mesma forma da funcao de custo em score_ollama_cloud_model: decaimento
        # logaritmico, nunca deixa um outlier de latencia dominar a formula.
        observed = 1.0 / (1.0 + math.log1p(stats.latency_ewma_ms / 1000.0))
        confidence = _shrinkage_confidence(stats.attempts)
        return (1 - confidence) * NEUTRAL_LATENCY_SCORE + confidence * observed

    def attempts(self, provider: str, model: str) -> int:
        stats = self._get(provider, model)
        return stats.attempts if stats else 0

    def _get(self, provider: str, model: str) -> _ModelStats | None:
        with self._lock:
            return self._stats.get(self._key(provider, model))

    def _load(self) -> None:
        path = _store_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            for key, entry in raw.items():
                self._stats[key] = _ModelStats(
                    attempts=int(entry.get("attempts", 0)),
                    successes=int(entry.get("successes", 0)),
                    latency_ewma_ms=float(entry.get("latency_ewma_ms", 0.0)),
                )
        except Exception as exc:
            logger.warning("[ModelReliability] Falha ao carregar telemetria persistida: %s", exc)

    def _save(self) -> None:
        path = _store_path()
        try:
            with self._lock:
                raw = {
                    k: {"attempts": v.attempts, "successes": v.successes, "latency_ewma_ms": v.latency_ewma_ms}
                    for k, v in self._stats.items()
                }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f)
        except Exception as exc:
            logger.warning("[ModelReliability] Falha ao persistir telemetria: %s", exc)


_store = ModelReliabilityStore()


def record_call_outcome(provider: str, model: str, success: bool, duration_ms: float) -> None:
    """Registra o resultado de UMA chamada real ao provider (sucesso final apos
    retries internos, duracao total incluindo-os) -- chamado por llm_client.call_llm."""
    _store.record(provider, model, success, duration_ms)


def get_reliability_score(provider: str, model: str) -> float:
    return _store.reliability_score(provider, model)


def get_latency_score(provider: str, model: str) -> float:
    return _store.latency_score(provider, model)


def get_attempts(provider: str, model: str) -> int:
    return _store.attempts(provider, model)


def reset_for_tests() -> None:
    """Uso exclusivo de testes -- recria o store (relê o arquivo em disco corrente,
    útil tanto para isolar testes entre si quanto para simular reinício do processo)."""
    global _store
    _store = ModelReliabilityStore()
