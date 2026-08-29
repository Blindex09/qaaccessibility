import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services.self_healing import (
    _plan_to_instruction,
    node_plan,
    run_self_healing_loop,
    verify_html_with_axe,
)
from backend.src.shared.models import AccessibilityIssue, AgentResult, Guideline, Severity


@pytest.mark.asyncio
async def test_self_healing_loop_success_on_first_try():
    # Arrange: No remaining violations returned by verify_html_with_axe
    initial_issues = [
        AccessibilityIssue(
            id="issue-1",
            guideline=Guideline.WCAG_2_2,
            criterion="alt",
            severity=Severity.HIGH,
            element="img",
            description="Missing alt attribute",
            suggestion="Add alt attribute",
        )
    ]

    mock_run_fixer = AsyncMock(return_value=AgentResult(
        agent="fixer",
        success=True,
        data={
            "fixed_html": "<html><body><img alt='description'/></body></html>",
            "changes_summary": ["Added alt to img"],
            "enriched_issues": [{"id": "issue-1", "fixed_element_html": "<img alt='description'/>"}],
        }
    ))

    mock_verify_axe = AsyncMock(return_value=[])  # clean

    with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
         patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
         patch("backend.src.services.self_healing.node_plan", AsyncMock(return_value={"strategy": "", "ordered_groups": []})):

        html, changes, issues = await run_self_healing_loop(
            html_content="<html><body><img/></body></html>",
            initial_issues=initial_issues,
            max_retries=3
        )

    assert html == "<html><body><img alt='description'/></body></html>"
    assert changes == ["Added alt to img"]
    assert len(issues) == 1
    assert mock_run_fixer.call_count == 1
    assert mock_run_fixer.call_args_list[0][1]["model_tier"] == "fast"
    assert mock_verify_axe.call_count == 1


@pytest.mark.asyncio
async def test_self_healing_loop_runs_multiple_iterations():
    # Arrange:
    # First attempt: run_fixer fixes img, but verify_html_with_axe finds a new issue.
    # Second attempt: run_fixer fixes input, verify_html_with_axe returns nothing.
    initial_issues = [
        AccessibilityIssue(
            id="issue-1",
            guideline=Guideline.WCAG_2_2,
            criterion="alt",
            severity=Severity.HIGH,
            element="img",
            description="Missing alt attribute",
            suggestion="Add alt attribute",
        )
    ]

    run_fixer_results = [
        AgentResult(
            agent="fixer",
            success=True,
            data={
                "fixed_html": "<html><body><img alt='desc'/><input type='text'/></body></html>",
                "changes_summary": ["Added alt to img"],
                "enriched_issues": [{"id": "issue-1", "fixed_element_html": "<img alt='desc'/>"}],
            }
        ),
        AgentResult(
            agent="fixer",
            success=True,
            data={
                "fixed_html": "<html><body><img alt='desc'/><label for='name'>Name</label><input id='name' type='text'/></body></html>",
                "changes_summary": ["Added label for input"],
                "enriched_issues": [{"id": "axe-label-0", "fixed_element_html": "<input id='name'/>"}],
            }
        )
    ]

    mock_run_fixer = AsyncMock(side_effect=run_fixer_results)

    remaining_violation = AccessibilityIssue(
        id="axe-label-0",
        guideline=Guideline.WCAG_2_2,
        criterion="label",
        severity=Severity.MEDIUM,
        element="input",
        description="Missing label",
        suggestion="Add label",
    )

    verify_axe_results = [
        [remaining_violation],  # 1st verify call returns 1 remaining violation
        []                      # 2nd verify call returns 0 remaining violations
    ]
    mock_verify_axe = AsyncMock(side_effect=verify_axe_results)

    with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
         patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
         patch("backend.src.services.self_healing.node_plan", AsyncMock(return_value={"strategy": "", "ordered_groups": []})):

        html, changes, issues = await run_self_healing_loop(
            html_content="<html><body><img/><input/></body></html>",
            initial_issues=initial_issues,
            max_retries=3
        )

    assert "label for='name'" in html
    assert mock_run_fixer.call_count == 2
    assert mock_run_fixer.call_args_list[0][1]["model_tier"] == "fast"
    assert mock_run_fixer.call_args_list[1][1]["model_tier"] == "alto"
    assert mock_verify_axe.call_count == 2
    assert len(changes) == 2
    assert changes[0] == "Added alt to img"
    assert changes[1] == "[Auto-cicatrizacao T1] Added label for input"
    assert len(issues) == 2


@pytest.mark.asyncio
async def test_self_healing_loop_stops_at_max_retries():
    # Arrange:
    # Always returns a violation, should stop after max_retries limit.
    initial_issues = [
        AccessibilityIssue(
            id="issue-1",
            guideline=Guideline.WCAG_2_2,
            criterion="alt",
            severity=Severity.HIGH,
            element="img",
            description="Missing alt",
            suggestion="Add alt",
        )
    ]

    mock_run_fixer = AsyncMock(return_value=AgentResult(
        agent="fixer",
        success=True,
        data={
            "fixed_html": "<html><body>Still broken</body></html>",
            "changes_summary": ["Attempted fix"],
            "enriched_issues": [],
        }
    ))

    remaining_violation = AccessibilityIssue(
        id="axe-broken-0",
        guideline=Guideline.WCAG_2_2,
        criterion="alt",
        severity=Severity.HIGH,
        element="img",
        description="Still missing alt",
        suggestion="Add alt",
    )
    mock_verify_axe = AsyncMock(return_value=[remaining_violation])

    with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
         patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
         patch("backend.src.services.self_healing.node_plan", AsyncMock(return_value={"strategy": "", "ordered_groups": []})):

        html, changes, issues = await run_self_healing_loop(
            html_content="<html><body><img/></body></html>",
            initial_issues=initial_issues,
            max_retries=2
        )

    # Attempt 1: initial run
    # Attempt 2: retry 1 (loop iteration 1)
    # Attempt 3: retry 2 (loop iteration 2)
    assert mock_run_fixer.call_count == 3
    assert mock_verify_axe.call_count == 2


@pytest.mark.asyncio
async def test_self_healing_loop_detects_repeated_failure_signature_and_stops_early():
    """Se a mesma violacao (mesmo criterion+element) persiste por rodadas
    consecutivas, o loop deve parar de insistir antes de esgotar max_retries
    -- em vez de so contar tentativas, ele compara a ASSINATURA do erro entre
    auditorias consecutivas (ver docs/conceitos-ia-para-desenvolvimento-de-
    software.md, secao 7: deteccao de loop por assinatura, nao por contagem)."""
    initial_issues = [
        AccessibilityIssue(
            id="issue-1",
            guideline=Guideline.WCAG_2_2,
            criterion="alt",
            severity=Severity.HIGH,
            element="img.stuck",
            description="Missing alt",
            suggestion="Add alt",
        )
    ]

    # O fixer sempre "aplica" uma mudanca, mas nunca resolve de fato -- axe
    # continua reportando exatamente o mesmo criterion+element toda vez.
    mock_run_fixer = AsyncMock(return_value=AgentResult(
        agent="fixer",
        success=True,
        data={
            "fixed_html": "<html><body><img class='stuck'/></body></html>",
            "changes_summary": ["Tentativa que nao resolveu"],
            "enriched_issues": [],
        }
    ))

    same_violation = AccessibilityIssue(
        id="axe-alt-0",
        guideline=Guideline.WCAG_2_2,
        criterion="alt",
        severity=Severity.HIGH,
        element="img.stuck",
        description="Still missing alt",
        suggestion="Add alt",
    )
    mock_verify_axe = AsyncMock(return_value=[same_violation])

    with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
         patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
         patch("backend.src.services.self_healing.node_plan", AsyncMock(return_value={"strategy": "", "ordered_groups": []})):

        await run_self_healing_loop(
            html_content="<html><body><img class='stuck'/></body></html>",
            initial_issues=initial_issues,
            max_retries=5,  # sem deteccao de loop, chegaria a rodar bem mais tentativas
        )

    # 1 tentativa inicial + 2 retries de node_fix antes do loop detectar a
    # repeticao e parar -- bem menos que o teto de max_retries=5.
    assert mock_run_fixer.call_count == 3
    assert mock_verify_axe.call_count == 3


@pytest.mark.asyncio
async def test_self_healing_first_attempt_fails():
    initial_issues = [
        AccessibilityIssue(
            id="issue-1",
            guideline=Guideline.WCAG_2_2,
            criterion="alt",
            severity=Severity.HIGH,
            element="img",
            description="Missing alt",
            suggestion="Add alt",
        )
    ]

    mock_run_fixer = AsyncMock(return_value=AgentResult(
        agent="fixer",
        success=False,
        data={},
        error="LLM failed",
    ))

    with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
         patch("backend.src.services.self_healing.node_plan", AsyncMock(return_value={"strategy": "", "ordered_groups": []})), \
         pytest.raises(RuntimeError) as exc_info:
        await run_self_healing_loop(
            html_content="<html><body><img/></body></html>",
            initial_issues=initial_issues,
        )

    assert "Primeira tentativa de" in str(exc_info.value)
    assert "LLM failed" in str(exc_info.value)


@pytest.mark.asyncio
@patch("backend.src.config.settings.get_settings")
async def test_verify_html_with_axe_success(mock_get_settings):
    # O endpoint CDP vem da configuração, não do .env da máquina que roda a
    # suíte -- sem este mock o teste só passava em quem tivesse BROWSERLESS_WS_URL
    # configurado localmente.
    mock_settings = AsyncMock()
    mock_settings.browserless_ws_url = "ws://browserless.test/cdp"
    mock_get_settings.return_value = mock_settings

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={
        "violations": [
            {
                "id": "color-contrast",
                "description": "Ensures the contrast between foreground and background colors meets WCAG 2 AA contrast ratio thresholds",
                "help": "Elements must have sufficient color contrast",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.9/color-contrast",
                "impact": "serious",
                "nodes": [
                    {
                        "target": ["div.bad-contrast"],
                        "failureSummary": "Fix any of the following: Element has insufficient color contrast of 2.3",
                    }
                ]
            }
        ]
    })

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_chromium = AsyncMock()
    mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    mock_playwright = AsyncMock()
    mock_playwright.chromium = mock_chromium

    class MockAsyncContextManager:
        async def __aenter__(self):
            return mock_playwright
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("backend.src.services.self_healing.async_playwright", return_value=MockAsyncContextManager()):
        issues = await verify_html_with_axe("<html><body><div class='bad-contrast'>text</div></body></html>")

    assert len(issues) == 1
    assert issues[0].criterion == "color-contrast"
    assert issues[0].severity == Severity.HIGH
    assert issues[0].element == "div.bad-contrast"
    assert "insufficient color contrast" in issues[0].description

    mock_page.set_content.assert_called_once_with("<html><body><div class='bad-contrast'>text</div></body></html>")
    mock_page.add_script_tag.assert_called_once()
    mock_page.evaluate.assert_called_once_with("() => axe.run()")


@pytest.mark.asyncio
@patch("backend.src.config.settings.get_settings")
async def test_verify_html_with_axe_raises_on_missing_ws_url(mock_get_settings):
    # Mock settings so browserless_ws_url is None
    mock_settings = AsyncMock()
    mock_settings.browserless_ws_url = None
    mock_get_settings.return_value = mock_settings

    with pytest.raises(ValueError, match="Configuração ausente: BROWSERLESS_WS_URL"):
        await verify_html_with_axe("<html><body>OK</body></html>")



def _issue(id_: str, criterion: str = "alt") -> AccessibilityIssue:
    return AccessibilityIssue(
        id=id_,
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=Severity.HIGH,
        element="img",
        description="Missing alt attribute",
        suggestion="Add alt attribute",
    )


class TestNodePlan:
    """Planning explícito (node_plan): decide ordem/agrupamento a partir dos
    issues reais, nunca de uma lista de prioridade fixa -- ver docstring."""

    @pytest.mark.asyncio
    async def test_empty_issues_returns_empty_plan_without_calling_llm(self):
        mock_call = AsyncMock()
        with patch("backend.src.services.llm_client.call_llm", mock_call):
            plan = await node_plan([])
        assert plan == {"strategy": "", "ordered_groups": []}
        mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_model_decides_grouping_from_real_issues(self):
        plan_json = json.dumps({
            "strategy": "Fix heading structure first, it resolves the landmark issue too.",
            "ordered_groups": [
                {"issue_ids": ["issue-1", "issue-2"], "rationale": "same structural change"},
            ],
        })
        with patch("backend.src.services.llm_client.call_llm", AsyncMock(return_value=plan_json)):
            plan = await node_plan([_issue("issue-1"), _issue("issue-2", "heading-order")])
        assert plan["ordered_groups"][0]["issue_ids"] == ["issue-1", "issue-2"]
        assert "heading structure" in plan["strategy"]

    @pytest.mark.asyncio
    async def test_planner_uses_fast_tier(self):
        mock_call = AsyncMock(return_value=json.dumps({"strategy": "x", "ordered_groups": []}))
        with patch("backend.src.services.llm_client.call_llm", mock_call):
            await node_plan([_issue("issue-1")])
        _, kwargs = mock_call.call_args
        assert kwargs.get("model_tier") == "fast"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_empty_plan_without_crashing(self):
        with patch(
            "backend.src.services.llm_client.call_llm", AsyncMock(side_effect=Exception("provider down"))
        ):
            plan = await node_plan([_issue("issue-1")])
        assert plan == {"strategy": "", "ordered_groups": []}

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_empty_plan(self):
        with patch("backend.src.services.llm_client.call_llm", AsyncMock(return_value="not json")):
            plan = await node_plan([_issue("issue-1")])
        assert plan == {"strategy": "", "ordered_groups": []}


class TestPlanToInstruction:
    def test_empty_plan_yields_empty_instruction(self):
        assert _plan_to_instruction({"strategy": "", "ordered_groups": []}) == ""

    def test_plan_renders_strategy_and_groups(self):
        plan = {
            "strategy": "Fix in dependency order.",
            "ordered_groups": [{"issue_ids": ["a", "b"], "rationale": "same element"}],
        }
        instruction = _plan_to_instruction(plan)
        assert "Fix in dependency order." in instruction
        assert "a, b" in instruction
        assert "same element" in instruction


class TestPlanningIntegratesIntoFixerInstruction:
    @pytest.mark.asyncio
    async def test_plan_is_forwarded_to_first_fixer_call(self):
        plan_json = json.dumps({
            "strategy": "Fix accessible names before keyboard access.",
            "ordered_groups": [{"issue_ids": ["issue-1"], "rationale": "isolated fix"}],
        })
        mock_run_fixer = AsyncMock(return_value=AgentResult(
            agent="fixer",
            success=True,
            data={"fixed_html": "<html></html>", "changes_summary": [], "enriched_issues": []},
        ))
        mock_verify_axe = AsyncMock(return_value=[])

        with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
             patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
             patch("backend.src.services.llm_client.call_llm", AsyncMock(return_value=plan_json)):
            await run_self_healing_loop(
                html_content="<html><body><img/></body></html>",
                initial_issues=[_issue("issue-1")],
                max_retries=1,
            )

        forwarded_instruction = mock_run_fixer.call_args_list[0][1]["custom_instruction"]
        assert "Fix accessible names before keyboard access." in forwarded_instruction

    @pytest.mark.asyncio
    async def test_plan_failure_does_not_block_fixer_from_running(self):
        """Planejamento é uma otimização -- sua falha nunca pode impedir o fix real."""
        mock_run_fixer = AsyncMock(return_value=AgentResult(
            agent="fixer",
            success=True,
            data={"fixed_html": "<html></html>", "changes_summary": [], "enriched_issues": []},
        ))
        mock_verify_axe = AsyncMock(return_value=[])

        with patch("backend.src.agents.fixer.fixer.run_fixer", mock_run_fixer), \
             patch("backend.src.services.self_healing.verify_html_with_axe", mock_verify_axe), \
             patch("backend.src.services.llm_client.call_llm", AsyncMock(side_effect=Exception("planner down"))):
            html, changes, issues = await run_self_healing_loop(
                html_content="<html><body><img/></body></html>",
                initial_issues=[_issue("issue-1")],
                max_retries=1,
            )

        assert mock_run_fixer.call_count == 1
        assert html == "<html></html>"
