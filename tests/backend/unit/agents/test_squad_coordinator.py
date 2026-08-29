from backend.src.agents.squad import SquadRole, build_squad_plan


def test_squad_plan_is_accessibility_only_and_has_quality_gates():
    plan = build_squad_plan("Corrigir o conteúdo principal de uma página")

    assert plan.domain == "digital_accessibility"
    assert plan.tasks[0].role is SquadRole.PRODUCT_OWNER
    assert "não implementar sem aprovação explícita" in plan.quality_gates


def test_squad_plan_orders_analysis_fix_qa_and_documentation():
    plan = build_squad_plan("Auditar e corrigir uma URL")
    by_id = {task.id: task for task in plan.tasks}

    assert by_id["a11y-analysis"].depends_on == ["product-scope"]
    assert by_id["a11y-remediation"].depends_on == ["a11y-analysis"]
    assert by_id["qa-validation"].depends_on == ["a11y-remediation"]
    assert by_id["documentation-release"].depends_on == ["qa-validation"]
    assert "live_preview_evidence" in by_id["qa-validation"].artifacts
