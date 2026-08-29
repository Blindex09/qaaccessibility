"""Testes do roteamento multi-objetivo do Ollama Cloud (score_ollama_cloud_model).

Cobre especificamente o que mudou: reliability_score e latency_score deixaram
de ser um valor fixo (0.95 hardcoded) e uma heurística de substring no nome do
modelo ("flash"/"lite") e passaram a vir de telemetria real observada -- ver
model_reliability.py.
"""
from unittest.mock import patch

from backend.src.services.ollama_cloud_adapter import OllamaCloudModelDescriptor, score_ollama_cloud_model


def _descriptor(model_id: str, **overrides) -> OllamaCloudModelDescriptor:
    defaults = dict(id=model_id, has_tools=True, has_vision=False, reasoning=True, context_window=131072)
    defaults.update(overrides)
    return OllamaCloudModelDescriptor(**defaults)


class TestEligibilityFilter:
    def test_rejects_model_without_tools_when_needed(self):
        d = _descriptor("no-tools", has_tools=False)
        assert score_ollama_cloud_model(d, needs_tools=True) == -1.0

    def test_rejects_model_without_vision_when_needed(self):
        d = _descriptor("no-vision", has_vision=False)
        assert score_ollama_cloud_model(d, needs_vision=True) == -1.0

    def test_accepts_vision_model_when_vision_needed(self):
        d = _descriptor("has-vision", has_vision=True)
        assert score_ollama_cloud_model(d, needs_vision=True) >= 0.0

    def test_rejects_model_with_context_window_too_small(self):
        d = _descriptor("tiny-context", context_window=100)
        assert score_ollama_cloud_model(d, input_tokens=2000, output_tokens=1000) == -1.0


class TestReliabilityAndLatencyUseRealTelemetry:
    def test_uses_observed_reliability_not_hardcoded_constant(self):
        d = _descriptor("telemetry-model")
        with patch(
            "backend.src.services.model_reliability.get_reliability_score", return_value=0.1
        ) as mock_reliability, patch(
            "backend.src.services.model_reliability.get_latency_score", return_value=0.75
        ):
            score_ollama_cloud_model(d, tradeoff=5)
        mock_reliability.assert_called_once_with("ollama-cloud", "telemetry-model")

    def test_unreliable_model_scores_lower_than_reliable_one(self):
        good, bad = _descriptor("good-model"), _descriptor("bad-model")

        def fake_reliability(provider, model):
            return 0.95 if model == "good-model" else 0.2

        with patch(
            "backend.src.services.model_reliability.get_reliability_score", side_effect=fake_reliability
        ), patch("backend.src.services.model_reliability.get_latency_score", return_value=0.75):
            good_score = score_ollama_cloud_model(good, tradeoff=5)
            bad_score = score_ollama_cloud_model(bad, tradeoff=5)
        assert good_score > bad_score

    def test_faster_observed_model_scores_higher_than_slower(self):
        fast, slow = _descriptor("fast-model"), _descriptor("slow-model")

        def fake_latency(provider, model):
            return 0.9 if model == "fast-model" else 0.3

        with patch("backend.src.services.model_reliability.get_reliability_score", return_value=0.75), patch(
            "backend.src.services.model_reliability.get_latency_score", side_effect=fake_latency
        ):
            fast_score = score_ollama_cloud_model(fast, tradeoff=5)
            slow_score = score_ollama_cloud_model(slow, tradeoff=5)
        assert fast_score > slow_score


class TestTradeoffDial:
    def test_low_tradeoff_favors_quality_over_cost(self):
        reasoning_model = _descriptor("reasoner", reasoning=True, cost_input=100.0, cost_output=100.0)
        cheap_model = _descriptor("cheap", reasoning=False, cost_input=0.01, cost_output=0.01)
        with patch("backend.src.services.model_reliability.get_reliability_score", return_value=0.75), patch(
            "backend.src.services.model_reliability.get_latency_score", return_value=0.75
        ):
            reasoning_score = score_ollama_cloud_model(reasoning_model, tradeoff=0)
            cheap_score = score_ollama_cloud_model(cheap_model, tradeoff=0)
        assert reasoning_score > cheap_score

    def test_high_tradeoff_favors_cost_over_quality(self):
        reasoning_model = _descriptor("reasoner", reasoning=True, cost_input=100.0, cost_output=100.0)
        cheap_model = _descriptor("cheap", reasoning=False, cost_input=0.01, cost_output=0.01)
        with patch("backend.src.services.model_reliability.get_reliability_score", return_value=0.75), patch(
            "backend.src.services.model_reliability.get_latency_score", return_value=0.75
        ):
            reasoning_score = score_ollama_cloud_model(reasoning_model, tradeoff=10)
            cheap_score = score_ollama_cloud_model(cheap_model, tradeoff=10)
        assert cheap_score > reasoning_score
