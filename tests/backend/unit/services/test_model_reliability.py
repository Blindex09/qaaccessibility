"""Testes da telemetria de confiabilidade/latência observada por modelo real.

Substitui, no roteamento "Alto" do Ollama Cloud, os antigos valores fixos
(reliability_score=0.95 hardcoded, latência por heurística de substring no
nome do modelo) por dados observados de verdade -- ver ollama_cloud_adapter.py.

Confiança gradual via shrinkage bayesiano (achado real 2026-08-26, auditoria
`docs/auditoria-portado-de-agentic-2026-08-26.md`, item 3): o corte binário
anterior (< 5 tentativas = 100% prior neutro; >= 5 = 100% taxa observada)
fazia a 5a tentativa pesar 0->100% de repente -- uma sequência de falha
isolada de infra bem nessa amostra derrubava o modelo inteiro do ranking.
Estes testes verificam a curva suave que substituiu o corte.
"""
import math
from unittest.mock import patch

import pytest

from backend.src.services import model_reliability


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path):
    """Cada teste usa seu proprio arquivo de persistencia e store em memoria limpo."""
    store_file = tmp_path / "model_reliability_test.json"
    with patch.object(model_reliability, "_store_path", return_value=str(store_file)):
        model_reliability.reset_for_tests()
        yield
        model_reliability.reset_for_tests()


def _expected_score(successes: int, attempts: int, neutral: float) -> float:
    observed = successes / attempts
    confidence = attempts / (attempts + model_reliability.RELIABILITY_SHRINKAGE_K)
    return (1 - confidence) * neutral + confidence * observed


class TestNeutralPriorBeforeEnoughSamples:
    def test_no_data_returns_neutral_reliability(self):
        assert model_reliability.get_reliability_score("ollama-cloud", "some-model") == (
            model_reliability.NEUTRAL_RELIABILITY
        )

    def test_no_data_returns_neutral_latency(self):
        assert model_reliability.get_latency_score("ollama-cloud", "some-model") == (
            model_reliability.NEUTRAL_LATENCY_SCORE
        )

    def test_single_attempt_stays_close_to_neutral(self):
        """Com 1 amostra, a confiança na taxa observada é baixa (~4,8% com K=20)
        -- um unico erro isolado (ex.: timeout de rede transitorio) nao pode
        dominar a pontuacao de um modelo."""
        model_reliability.record_call_outcome("ollama-cloud", "flaky-model", False, 500.0)
        score = model_reliability.get_reliability_score("ollama-cloud", "flaky-model")
        assert score == pytest.approx(_expected_score(0, 1, model_reliability.NEUTRAL_RELIABILITY))
        # Ainda muito perto do prior neutro (0.75), longe da taxa observada (0.0).
        assert score > model_reliability.NEUTRAL_RELIABILITY - 0.05


class TestObservedScoreAfterEnoughSamples:
    def test_reliability_leans_toward_real_success_rate(self):
        model = "test-model"
        for _ in range(8):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 1000.0)
        for _ in range(2):
            model_reliability.record_call_outcome("ollama-cloud", model, False, 1000.0)
        score = model_reliability.get_reliability_score("ollama-cloud", model)
        assert score == pytest.approx(_expected_score(8, 10, model_reliability.NEUTRAL_RELIABILITY))
        # Com apenas 10 amostras, a curva ainda nao chega na taxa bruta (0.8) --
        # esse e o ponto do shrinkage: nunca converge de golpe.
        assert score < 0.8

    def test_unreliable_model_scores_low(self):
        model = "unreliable-model"
        for _ in range(2):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 1000.0)
        for _ in range(8):
            model_reliability.record_call_outcome("ollama-cloud", model, False, 1000.0)
        score = model_reliability.get_reliability_score("ollama-cloud", model)
        assert score == pytest.approx(_expected_score(2, 10, model_reliability.NEUTRAL_RELIABILITY))
        assert score < model_reliability.NEUTRAL_RELIABILITY

    def test_large_volume_approaches_raw_rate_but_never_reaches_it(self):
        model = "high-volume-model"
        for _ in range(998):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 1000.0)
        for _ in range(2):
            model_reliability.record_call_outcome("ollama-cloud", model, False, 1000.0)
        score = model_reliability.get_reliability_score("ollama-cloud", model)
        raw_rate = 998 / 1000
        assert score == pytest.approx(_expected_score(998, 1000, model_reliability.NEUTRAL_RELIABILITY))
        assert score < raw_rate  # prior nunca e totalmente descartado, nem com volume grande

    def test_faster_model_scores_higher_latency(self):
        fast, slow = "fast-model", "slow-model"
        for _ in range(6):
            model_reliability.record_call_outcome("ollama-cloud", fast, True, 500.0)
            model_reliability.record_call_outcome("ollama-cloud", slow, True, 20000.0)
        assert model_reliability.get_latency_score("ollama-cloud", fast) > (
            model_reliability.get_latency_score("ollama-cloud", slow)
        )

    def test_attempts_counts_all_records(self):
        model = "counted-model"
        for _ in range(4):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 100.0)
        assert model_reliability.get_attempts("ollama-cloud", model) == 4


class TestBayesianShrinkageCurve:
    """Cobre a curva em si (K=20), incluindo o cenario exato do bug corrigido."""

    def test_confidence_at_k_attempts_is_exactly_half(self):
        assert model_reliability.RELIABILITY_SHRINKAGE_K == 20
        assert model_reliability._shrinkage_confidence(20) == pytest.approx(0.5)

    def test_confidence_grows_monotonically_with_attempts(self):
        confidences = [model_reliability._shrinkage_confidence(n) for n in (1, 5, 20, 100, 10_000)]
        assert confidences == sorted(confidences)
        assert confidences[-1] < 1.0

    def test_isolated_failure_streak_at_fifth_attempt_does_not_crash_score_to_zero(self):
        """Regressao direta do bug: no corte binario antigo, 4 falhas seguidas por
        acaso (ex.: durante uma instabilidade transitoria de infra) faziam o score
        cair para 0.0 exato assim que attempts atingia 5 -- o modelo era descartado
        do ranking por uma sequencia de azar isolada. A curva suave amortece isso."""
        for _ in range(5):
            model_reliability.record_call_outcome("ollama-cloud", "unlucky-model", False, 500.0)
        score = model_reliability.get_reliability_score("ollama-cloud", "unlucky-model")
        assert score > 0.0
        assert score == pytest.approx(_expected_score(0, 5, model_reliability.NEUTRAL_RELIABILITY))

    def test_score_is_never_exactly_the_raw_observed_rate(self):
        model = "any-model"
        for _ in range(7):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 100.0)
        for _ in range(3):
            model_reliability.record_call_outcome("ollama-cloud", model, False, 100.0)
        score = model_reliability.get_reliability_score("ollama-cloud", model)
        assert score != pytest.approx(0.7)

    def test_latency_score_uses_same_shrinkage_curve(self):
        model = "latency-model"
        for _ in range(6):
            model_reliability.record_call_outcome("ollama-cloud", model, True, 500.0)
        score = model_reliability.get_latency_score("ollama-cloud", model)
        observed = 1.0 / (1.0 + math.log1p(500.0 / 1000.0))
        confidence = model_reliability._shrinkage_confidence(6)
        expected = (1 - confidence) * model_reliability.NEUTRAL_LATENCY_SCORE + confidence * observed
        assert score == pytest.approx(expected)


class TestProviderModelIsolation:
    def test_different_providers_tracked_independently(self):
        model_reliability.record_call_outcome("ollama-cloud", "shared-name", False, 100.0)
        for _ in range(5):
            model_reliability.record_call_outcome("openai", "shared-name", True, 100.0)
        # openai/shared-name tem 5 sucessos seguidos; ollama-cloud/shared-name tem
        # 1 falha isolada -- devem divergir (o segundo pesa bem mais perto do
        # prior neutro), provando isolamento por provider.
        openai_score = model_reliability.get_reliability_score("openai", "shared-name")
        ollama_score = model_reliability.get_reliability_score("ollama-cloud", "shared-name")
        assert openai_score > model_reliability.NEUTRAL_RELIABILITY
        assert ollama_score < model_reliability.NEUTRAL_RELIABILITY
        assert openai_score > ollama_score

    def test_case_insensitive_key(self):
        model_reliability.record_call_outcome("Ollama-Cloud", "Deepseek-V4", True, 100.0)
        assert model_reliability.get_attempts("ollama-cloud", "deepseek-v4") == 1


class TestPersistence:
    def test_survives_store_recreation(self, tmp_path):
        store_file = tmp_path / "persisted.json"
        with patch.object(model_reliability, "_store_path", return_value=str(store_file)):
            model_reliability.reset_for_tests()
            for _ in range(6):
                model_reliability.record_call_outcome("ollama-cloud", "persisted-model", True, 1000.0)
            assert store_file.exists()
            score_before = model_reliability.get_reliability_score("ollama-cloud", "persisted-model")

            # Simula reinicio do processo: novo store, mesmo arquivo em disco.
            model_reliability.reset_for_tests()
            assert model_reliability.get_attempts("ollama-cloud", "persisted-model") == 6
            assert model_reliability.get_reliability_score("ollama-cloud", "persisted-model") == pytest.approx(
                score_before
            )

    def test_corrupted_file_does_not_crash(self, tmp_path):
        store_file = tmp_path / "corrupted.json"
        store_file.write_text("{not valid json", encoding="utf-8")
        with patch.object(model_reliability, "_store_path", return_value=str(store_file)):
            model_reliability.reset_for_tests()  # não deve levantar exceção
            assert model_reliability.get_attempts("ollama-cloud", "anything") == 0


class TestRecordCallOutcomeGuards:
    def test_ignores_empty_provider_or_model(self):
        model_reliability.record_call_outcome("", "model", True, 100.0)
        model_reliability.record_call_outcome("provider", "", True, 100.0)
        assert model_reliability.get_attempts("", "model") == 0
        assert model_reliability.get_attempts("provider", "") == 0

    def test_ignores_negative_duration(self):
        model_reliability.record_call_outcome("ollama-cloud", "model", True, -5.0)
        assert model_reliability.get_attempts("ollama-cloud", "model") == 0
