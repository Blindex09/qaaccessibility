from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.services.a2a_service import (
    _a2a_tasks_store,
    _execute_a2a_task_worker,
    generate_agent_card,
    get_a2a_task_status,
)
from backend.src.shared.models import AccessibilityIssue, AgentResult, Guideline, Severity

client = TestClient(app)


def _seed_task(task_id: str) -> None:
    # _execute_a2a_task_worker atualiza um registro existente (normalmente
    # criado por submit_a2a_task) -- nao cria a entrada, entao os testes que
    # chamam o worker diretamente precisam semear o registro minimo antes.
    _a2a_tasks_store[task_id] = {
        "task_id": task_id,
        "status": "working",
        "progress": 0.1,
        "output": None,
        "error": None,
        "metrics": {"execution_time_ms": 0.0},
    }


def test_generate_agent_card_schema():
    """Valida se o Agent Card gerado cumpre o esquema oficial A2A v1.0 (2026 Standard)."""
    card = generate_agent_card("http://localhost:8000")
    assert card["$schema"] == "https://a2a-protocol.org/schemas/v1.0/agent-card.json"
    assert card["name"] == "QAAccessibilityAgent"
    assert card["version"] == "1.0.0"
    assert card["capabilities"]["streaming"] is True
    assert card["capabilities"]["stateful"] is True
    assert len(card["skills"]) >= 5
    skill_ids = [s["id"] for s in card["skills"]]
    assert "accessibility_analysis" in skill_ids
    assert "self_healing_fix" in skill_ids
    assert "sarif_export" in skill_ids


def test_agent_card_endpoints():
    """Valida as rotas de descoberta de Agent Card /.well-known/agent-card.json e /.well-known/agent.json."""
    res1 = client.get("/.well-known/agent-card.json")
    assert res1.status_code == 200
    card = res1.json()
    assert card["name"] == "QAAccessibilityAgent"

    res2 = client.get("/.well-known/agent.json")
    assert res2.status_code == 200
    assert res2.json()["name"] == "QAAccessibilityAgent"


@pytest.mark.asyncio
async def test_a2a_task_lifecycle():
    """Valida o ciclo de vida de criacao, consulta e cancelamento de tarefas A2A."""
    payload = {
        "skill_id": "sarif_export",
        "input": {
            "issues": [
                {
                    "id": "aria-1",
                    "guideline": "WAI-ARIA",
                    "criterion": "4.1.2 Name, Role, Value",
                    "severity": "high",
                    "level": "A",
                    "element": "<button>",
                    "description": "Missing accessible name",
                    "suggestion": "Add aria-label",
                }
            ],
            "url": "http://localhost/test",
        },
        "parameters": {},
        "stream": False,
    }

    # 1. Criar Tarefa A2A
    create_res = client.post("/a2a/v1/tasks", json=payload)
    assert create_res.status_code == 200
    task_info = create_res.json()
    task_id = task_info["task_id"]
    assert task_id.startswith("task_a2a_")
    assert task_info["status"] in ["working", "completed"]

    # 2. Consultar Status da Tarefa A2A
    status_res = client.get(f"/a2a/v1/tasks/{task_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["task_id"] == task_id
    assert status_data["status"] in ["working", "completed"]

    # 3. Cancelar Tarefa A2A
    cancel_res = client.post(f"/a2a/v1/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "canceled"


@pytest.mark.asyncio
async def test_worker_accessibility_analysis_skill_calls_orchestrate():
    """Regressao: o worker chamava `run_orchestrator` (inexistente em
    orchestrator.py, que expoe `orchestrate`) -- nenhum teste exercitava esse
    branch, entao o mypy so pegou isso meses depois. Mocka `orchestrate` e
    verifica que o output do task store bate com o contrato real de AgentResult."""
    task_id = "task_a2a_test_analysis"
    _seed_task(task_id)
    fake_result = AgentResult(
        agent="orchestrator",
        success=True,
        data={
            "issues": [
                AccessibilityIssue(
                    id="aria-1",
                    guideline=Guideline.WAI_ARIA,
                    criterion="4.1.2 Name, Role, Value",
                    severity=Severity.HIGH,
                    element="<button>",
                    description="Missing accessible name",
                    suggestion="Add aria-label",
                ).model_dump()
            ],
        },
    )
    with patch(
        "backend.src.agents.orchestrator.orchestrator.orchestrate",
        new=AsyncMock(return_value=fake_result),
    ):
        await _execute_a2a_task_worker(
            task_id, "accessibility_analysis", {"html_content": "<button></button>"}, {}
        )

    status = get_a2a_task_status(task_id)
    assert status["status"] == "completed"
    assert status["output"]["total_issues"] == 1
    assert status["output"]["score"] == 90  # 100 - 10 (high)


@pytest.mark.asyncio
async def test_worker_self_healing_fix_skill_calls_run_self_healing_loop():
    """Regressao: o worker chamava `run_self_healing_loop(issues=...)` (kwarg
    inexistente -- o parametro real e posicional `initial_issues`) e tratava o
    retorno (uma tupla de 3) como se fosse so a string de HTML corrigido."""
    task_id = "task_a2a_test_healing"
    _seed_task(task_id)
    with patch(
        "backend.src.services.self_healing.run_self_healing_loop",
        new=AsyncMock(return_value=("<button>Fixed</button>", ["added aria-label"], [])),
    ):
        await _execute_a2a_task_worker(
            task_id,
            "self_healing_fix",
            {
                "html_content": "<button></button>",
                "issues": [
                    {
                        "id": "aria-1",
                        "guideline": "WAI-ARIA",
                        "criterion": "4.1.2 Name, Role, Value",
                        "severity": "high",
                        "element": "<button>",
                        "description": "Missing accessible name",
                        "suggestion": "Add aria-label",
                    }
                ],
            },
            {},
        )

    status = get_a2a_task_status(task_id)
    assert status["status"] == "completed"
    assert status["output"]["fixed_html"] == "<button>Fixed</button>"
    assert status["output"]["changes_summary"] == ["added aria-label"]
