"""O limite de tokens da pessoa vale também fora do chat (CI, scripts, outras IAs).

Como as APIs de IA fazem (Anthropic: stop_reason "max_tokens"; OpenAI: finish_reason "length"),
atingir o limite devolve o que já foi feito como resposta normal, com um aviso de que foi
cortado, e não como erro.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.agents.orchestrator.orchestrator import _mark_token_limit
from backend.src.main import app as main_app
from backend.src.middleware.request_budget import RequestBudgetMiddleware
from backend.src.services import execution_scope
from backend.src.services.execution_scope import TokenBudgetReachedError, add_tokens
from backend.src.shared.models import AgentResult


def test_every_http_request_runs_inside_a_budget_with_the_persons_limit(monkeypatch):
    monkeypatch.setattr(execution_scope, "_configured_token_limit", lambda: 4321)
    probe = FastAPI()
    probe.add_middleware(RequestBudgetMiddleware)

    @probe.get("/limite")
    async def limite():
        budget = execution_scope.current_budget()
        return {"has_budget": budget is not None, "limit": budget.token_limit if budget else None}

    body = TestClient(probe).get("/limite").json()
    assert body == {"has_budget": True, "limit": 4321}


def test_no_limit_chosen_means_no_limit_over_http(monkeypatch):
    monkeypatch.setattr(execution_scope, "_configured_token_limit", lambda: None)
    probe = FastAPI()
    probe.add_middleware(RequestBudgetMiddleware)

    @probe.get("/limite")
    async def limite():
        return {"limit": execution_scope.current_budget().token_limit}

    assert TestClient(probe).get("/limite").json() == {"limit": None}


def test_two_requests_never_share_the_spent_tokens(monkeypatch):
    monkeypatch.setattr(execution_scope, "_configured_token_limit", lambda: 100)
    probe = FastAPI()
    probe.add_middleware(RequestBudgetMiddleware)

    @probe.get("/gasta")
    async def gasta():
        add_tokens(60)
        return {"used": execution_scope.current_budget().tokens_used}

    http = TestClient(probe)
    assert http.get("/gasta").json() == {"used": 60}
    assert http.get("/gasta").json() == {"used": 60}  # cada pedido tem o seu próprio gasto


def test_partial_analysis_is_returned_flagged_not_failed():
    @_mark_token_limit
    async def fake_pipeline():
        add_tokens(900)
        return AgentResult(agent="orchestrator", success=True, data={"issues": [{"id": "a"}]})

    import asyncio

    async def run():
        with execution_scope.execution_scope(10, token_limit=800):
            return await fake_pipeline()

    result = asyncio.run(run())
    assert result.success is True  # parcial, não falha
    assert result.data["issues"] == [{"id": "a"}]  # o que foi feito volta
    assert result.data["complete"] is False
    assert result.data["token_limit"] == {"reached": True, "used": 900, "limit": 800}
    assert "1 achados devolvidos são parciais" in result.data["warning"]


def test_analysis_inside_the_limit_is_not_flagged():
    @_mark_token_limit
    async def fake_pipeline():
        add_tokens(10)
        return AgentResult(agent="orchestrator", success=True, data={"issues": []})

    import asyncio

    async def run():
        with execution_scope.execution_scope(10, token_limit=800):
            return await fake_pipeline()

    data = asyncio.run(run()).data
    assert "token_limit" not in data and "complete" not in data


def test_a_route_that_hits_the_limit_before_producing_anything_answers_200_with_the_flag():
    @main_app.get("/__teste_limite_de_tokens")
    async def boom():
        raise TokenBudgetReachedError(5399, 3000)

    try:
        response = TestClient(main_app).get("/__teste_limite_de_tokens")
    finally:
        main_app.router.routes[:] = [r for r in main_app.router.routes if getattr(r, "path", "") != "/__teste_limite_de_tokens"]
    assert response.status_code == 200  # igual às APIs de IA: não é erro
    assert response.headers["X-Token-Limit-Reached"] == "true"
    body = response.json()
    assert body["complete"] is False
    assert body["token_limit"] == {"reached": True, "used": 5399, "limit": 3000}
    assert "3000" in body["message"]


@pytest.mark.parametrize("configured, expected", [(0, None), (2500, 2500)])
def test_the_limit_comes_from_the_persons_settings(monkeypatch, configured, expected):
    class FakeSettings:
        turn_token_budget = configured

    monkeypatch.setattr("backend.src.config.settings.get_settings", lambda: FakeSettings())
    assert execution_scope._configured_token_limit() == expected


def test_unreadable_settings_never_break_a_request(monkeypatch):
    """Regressão: o teste de cabeçalhos de segurança usa um Settings falso (AsyncMock); o
    middleware não pode derrubar o pedido por causa disso."""
    from unittest.mock import AsyncMock

    from backend.src.middleware import request_budget

    monkeypatch.setattr("backend.src.config.settings.get_settings", lambda: AsyncMock())
    assert request_budget._window_seconds() > 0  # não levanta, mesmo com um Settings falso

    class Broken:
        @property
        def agent_timeout_seconds(self):
            raise RuntimeError("configuração ilegível")

    monkeypatch.setattr("backend.src.config.settings.get_settings", lambda: Broken())
    assert request_budget._window_seconds() == request_budget._DEFAULT_WINDOW_SECONDS


def test_warning_does_not_call_zero_findings_partial_findings():
    @_mark_token_limit
    async def nothing_found():
        add_tokens(900)
        return AgentResult(agent="orchestrator", success=False, data={"issues": []})

    import asyncio

    async def run():
        with execution_scope.execution_scope(10, token_limit=800):
            return await nothing_found()

    warning = asyncio.run(run()).data["warning"]
    assert "não houve como apurar achados" in warning
    assert "parciais" not in warning
