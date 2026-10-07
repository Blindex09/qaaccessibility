from backend.src.services.adaptive_budget import create_analysis_budget


def test_more_specialists_never_lengthen_the_silence_window():
    """Regra 8: a janela é de silêncio entre progressos, não soma das ondas."""
    small = create_analysis_budget(selected_agents=3, parallelism=3, per_agent_timeout=90, tradeoff=9)
    large = create_analysis_budget(selected_agents=12, parallelism=3, per_agent_timeout=90, tradeoff=9)
    assert large.deadline - large.started_at == small.deadline - small.started_at


def test_standalone_phase_window_slides_with_progress():
    import time

    budget = create_analysis_budget(selected_agents=4, parallelism=2, per_agent_timeout=10, tradeoff=9)
    budget.scope.deadline = time.monotonic() + 0.05
    assert budget.remaining_seconds <= 0.06  # tolerância de relógio
    budget.note_progress()
    assert budget.remaining_seconds > 5
    assert not budget.expired


def test_quality_tradeoff_gets_more_operational_slack():
    quality = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=90, tradeoff=0)
    economy = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=90, tradeoff=10)
    assert quality.deadline - quality.started_at > economy.deadline - economy.started_at


def test_budget_remaining_is_never_negative():
    budget = create_analysis_budget(selected_agents=0, parallelism=0, per_agent_timeout=1, tradeoff=3)
    assert budget.remaining_seconds >= 0


def test_more_specialists_do_not_create_a_longer_ceiling_inside_a_turn():
    """Regra 8: dentro do turno a janela é de silêncio, não soma das ondas."""
    from backend.src.services.execution_scope import execution_scope

    with execution_scope(10) as parent:
        few = create_analysis_budget(selected_agents=3, parallelism=3, per_agent_timeout=10, tradeoff=3)
        patience_few = parent.patience
        many = create_analysis_budget(selected_agents=22, parallelism=3, per_agent_timeout=10, tradeoff=3)
        assert parent.patience == patience_few
        assert few.scope is parent and many.scope is parent
        assert parent.patience < 80  # 22 agentes em 8 ondas não viram 80+ s de teto


def test_phase_budget_is_a_live_view_of_the_turn_window():
    import time

    from backend.src.services.execution_scope import execution_scope

    with execution_scope(10) as parent:
        budget = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=10, tradeoff=3)
        parent.deadline = time.monotonic() + 0.05
        assert budget.remaining_seconds <= 0.06  # tolerância de relógio
        parent.note_progress()  # um especialista terminou: a janela desliza
        assert budget.remaining_seconds > 5
        assert not budget.expired
