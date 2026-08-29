import pytest

from backend.src.services.eval_stats import (
    MultiRunEvalResult,
    confidence_interval_95,
    pass_at_k,
    run_multi_trial,
    sample_variance,
    success_rate,
)


class TestSuccessRate:
    def test_empty_list_is_zero(self):
        assert success_rate([]) == 0.0

    def test_all_success(self):
        assert success_rate([True, True, True]) == 1.0

    def test_all_failure(self):
        assert success_rate([False, False]) == 0.0

    def test_mixed(self):
        assert success_rate([True, False, True, False]) == 0.5


class TestSampleVariance:
    def test_fewer_than_two_results_is_zero(self):
        assert sample_variance([]) == 0.0
        assert sample_variance([True]) == 0.0

    def test_constant_results_have_zero_variance(self):
        assert sample_variance([True, True, True, True]) == 0.0
        assert sample_variance([False, False, False]) == 0.0

    def test_mixed_results_have_positive_variance(self):
        assert sample_variance([True, False, True, False]) > 0.0


class TestPassAtK:
    def test_empty_results_is_zero(self):
        assert pass_at_k([], 1) == 0.0

    def test_k_zero_or_negative_is_zero(self):
        assert pass_at_k([True, False], 0) == 0.0
        assert pass_at_k([True, False], -1) == 0.0

    def test_all_success_pass_at_1_is_1(self):
        assert pass_at_k([True, True, True], 1) == 1.0

    def test_all_failure_pass_at_1_is_0(self):
        assert pass_at_k([False, False, False], 1) == 0.0

    def test_partial_success_pass_at_1_matches_success_rate(self):
        # 1 sucesso em 4: Pass@1 == taxa de sucesso simples
        results = [True, False, False, False]
        assert pass_at_k(results, 1) == pytest.approx(0.25)

    def test_k_larger_than_n_is_clamped(self):
        results = [True, False]
        assert pass_at_k(results, 10) == pass_at_k(results, 2)

    def test_more_successes_than_k_needs_is_certain(self):
        # 3 sucessos em 5, k=2: garantido pegar pelo menos 1 sucesso amostrando 2
        # de 5 quando so 2 sao falha (n-c=2 >= k=2 ainda possivel falhar as 2,
        # mas com c=4 sucessos e apenas 1 falha, k=2 forca pelo menos 1 sucesso)
        results = [True, True, True, True, False]
        assert pass_at_k(results, 2) == 1.0


class TestConfidenceInterval95:
    def test_empty_results(self):
        assert confidence_interval_95([]) == (0.0, 0.0)

    def test_single_result_is_maximally_wide(self):
        assert confidence_interval_95([True]) == (0.0, 1.0)

    def test_interval_contains_the_point_estimate(self):
        results = [True, True, True, False, False]
        lo, hi = confidence_interval_95(results)
        p = success_rate(results)
        assert lo <= p <= hi

    def test_interval_bounds_are_clamped_to_0_1(self):
        lo, hi = confidence_interval_95([True] * 20)
        assert 0.0 <= lo <= hi <= 1.0


class TestRunMultiTrial:
    @pytest.mark.asyncio
    async def test_all_trials_succeed(self):
        async def always_true() -> bool:
            return True

        result = await run_multi_trial(always_true, n_runs=5)
        assert isinstance(result, MultiRunEvalResult)
        assert result.n_runs == 5
        assert result.successes == 5
        assert result.success_rate == 1.0
        assert result.variance == 0.0
        assert not result.is_flaky
        assert result.trial_errors == []

    @pytest.mark.asyncio
    async def test_all_trials_fail(self):
        async def always_false() -> bool:
            return False

        result = await run_multi_trial(always_false, n_runs=4)
        assert result.successes == 0
        assert result.success_rate == 0.0
        assert not result.is_flaky

    @pytest.mark.asyncio
    async def test_mixed_trials_are_flaky(self):
        calls = {"n": 0}

        async def alternate() -> bool:
            calls["n"] += 1
            return calls["n"] % 2 == 0

        result = await run_multi_trial(alternate, n_runs=4)
        assert result.n_runs == 4
        assert result.successes == 2
        assert result.is_flaky

    @pytest.mark.asyncio
    async def test_exception_in_one_trial_counts_as_failure_without_crashing(self):
        calls = {"n": 0}

        async def flaky_raiser() -> bool:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("transient provider error")
            return True

        result = await run_multi_trial(flaky_raiser, n_runs=3)
        assert result.n_runs == 3
        assert result.successes == 2
        assert len(result.trial_errors) == 1
        assert "transient provider error" in result.trial_errors[0]

    @pytest.mark.asyncio
    async def test_pass_at_k_values_computed_for_requested_k(self):
        async def always_true() -> bool:
            return True

        result = await run_multi_trial(always_true, n_runs=5, k_values=(1, 3, 5))
        assert set(result.pass_at_k.keys()) == {1, 3, 5}
        assert all(v == 1.0 for v in result.pass_at_k.values())
