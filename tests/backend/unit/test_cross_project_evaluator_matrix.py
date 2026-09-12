import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[3] / "tools" / "cross_project_evaluator_matrix.py"
SPEC = spec_from_file_location("cross_project_evaluator_matrix", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matrix_declares_exactly_the_fourteen_in_scope_projects() -> None:
    assert len(MODULE.EXPECTED_PROJECTS) == 14
    assert len({item.project for item in MODULE._not_applicable_results()}) == 5
    assert not {item.project for item in MODULE._not_applicable_results()} & {
        "A2E",
        "agent-eval-harness",
        "agent-health",
        "agentevals",
        "agentfit",
        "AgentOps-Bench",
        "HarnessFix",
        "skillgate",
        "unlazy",
    }


def test_matrix_marks_non_evaluator_projects_honestly() -> None:
    results = MODULE._not_applicable_results()

    assert all(item.status == "not_applicable" for item in results)
    assert all("no" in item.evidence or "requires" in item.evidence for item in results)
