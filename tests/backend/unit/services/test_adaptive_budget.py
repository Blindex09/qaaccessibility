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


def test_selected_waves_extend_shared_budget_without_resetting_start():
    from backend.src.services.execution_scope import execution_scope

    with execution_scope(10) as parent:
        original_start = parent.started_at
        budget = create_analysis_budget(selected_agents=22, parallelism=3, per_agent_timeout=10, tradeoff=3)
        assert parent.deadline - original_start > 80
        assert budget.deadline == parent.effective_deadline()
        reserved = parent.deadline
        parent.adapt("low")
        assert parent.deadline == reserved
        assert parent.started_at == original_start
