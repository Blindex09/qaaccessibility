"""Squad mobilization is a model selection, not a planning boolean."""

from backend.src.agents.clarifier.clarifier import _construir_classificacao


def test_small_audit_can_mobilize_roles_selected_by_model():
    data = _construir_classificacao('{"intent":"analyze_url","squad_roles":["tech_lead"],"complexity":"low"}')
    assert data["squad_roles"] == ["tech_lead"]


def test_complexity_does_not_force_all_roles():
    data = _construir_classificacao('{"intent":"analyze_code","squad_roles":["qa_lead"],"complexity":"high"}')
    assert data["squad_roles"] == ["qa_lead"]


def test_model_selection_keeps_order():
    data = _construir_classificacao('{"intent":"chat_a11y","squad_roles":["qa_lead","product_owner"]}')
    assert data["squad_roles"] == ["qa_lead", "product_owner"]


def test_absent_selection_does_not_invent_a_fixed_sequence():
    data = _construir_classificacao('{"intent":"chat_a11y"}')
    assert data["squad_roles"] == []
    assert "needs_planning" not in data
