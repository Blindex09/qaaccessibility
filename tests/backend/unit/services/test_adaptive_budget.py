from backend.src.services.adaptive_budget import create_analysis_budget


def test_budget_scales_with_selected_agents_and_parallelism():
    small = create_analysis_budget(selected_agents=3, parallelism=3, per_agent_timeout=90, tradeoff=9)
    large = create_analysis_budget(selected_agents=12, parallelism=3, per_agent_timeout=90, tradeoff=9)
    assert large.deadline - large.started_at > small.deadline - small.started_at


def test_quality_tradeoff_gets_more_operational_slack():
    quality = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=90, tradeoff=0)
    economy = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=90, tradeoff=10)
    assert quality.deadline - quality.started_at > economy.deadline - economy.started_at


def test_budget_remaining_is_never_negative():
    budget = create_analysis_budget(selected_agents=0, parallelism=0, per_agent_timeout=1, tradeoff=3)
    assert budget.remaining_seconds >= 0
