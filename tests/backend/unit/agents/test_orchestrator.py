from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.orchestrator.orchestrator import (
    _deduplicate_issues,
    orchestrate,
)
from backend.src.services import batch_collector
from backend.src.shared.models import (
    AccessibilityIssue,
    AgentResult,
    Guideline,
    Severity,
    TaskType,
)


def make_result(agent: str, issues: list[dict] | None = None) -> AgentResult:
    return AgentResult(
        agent=agent,
        success=True,
        data={"issues": issues or []},
    )


def make_issue(id: str, criterion: str = "1.1.1 Non-text Content", element: str = "img") -> dict:
    return {
        "id": id,
        "guideline": "WCAG 2.2",
        "criterion": criterion,
        "severity": "critical",
        "element": element,
        "description": "desc",
        "suggestion": "fix",
    }


EMPTY: dict[str, list] = {"issues": []}
CHECKLIST: dict[str, list] = {"checklist": []}
REPORT = {
    "report_id": "r1",
    "summary": "ok",
    "score": 80,
    "issues": [],
    "checklist": [],
}

EXPECTED_SAMPLE_SELECTED_AGENT_MOCKS = {
    "run_perceiver",
    "run_operability",
    "run_understandability",
    "run_robustness",
    "run_aria_specialist",
    "run_section508",
    "run_cognitive",
    "run_react_framework",
    "run_angular_framework",
    "run_vue_framework",
    "run_svelte_framework",
    "run_tailwind_css",
    "run_screen_reader",
    "run_forms_a11y",
    "run_wcag_semantics",
    "run_compliance_audit",
}

EXPECTED_SAMPLE_SKIPPED_AGENT_MOCKS = {
    "run_css_analyzer",
    "run_ajax_dynamic",
    "run_mobile_a11y",
    "run_widgets_a11y",
    "run_visual_a11y",
    "run_tables_data",
    "run_link_checker",
}


def _patch_all_analysis_agents(overrides: dict | None = None) -> dict:
    """Retorna dict de patches para todos os sub-agentes de análise com mocks vazios."""
    names = [
        "run_perceiver",
        "run_operability",
        "run_understandability",
        "run_robustness",
        "run_aria_specialist",
        "run_section508",
        "run_css_analyzer",
        "run_ajax_dynamic",
        "run_cognitive",
        "run_react_framework",
        "run_angular_framework",
        "run_vue_framework",
        "run_svelte_framework",
        "run_tailwind_css",
        "run_screen_reader",
        "run_mobile_a11y",
        "run_forms_a11y",
        "run_widgets_a11y",
        "run_tables_data",
        "run_link_checker",
        "run_wcag_semantics",
        "run_compliance_audit",
        "run_agentic_ai_ui_agent",
        "run_spatial_3d_xr_agent",
        "run_web_components_agent",
        "run_niche_domains_agent",
        "run_visual_a11y",
    ]
    patches = {n: AsyncMock(return_value=make_result(n)) for n in names}
    patches["run_classifier"] = AsyncMock(
        return_value=AgentResult(
            agent="classifier",
            success=True,
            data={"technologies": ["react", "vue", "angular", "svelte", "tailwind"]},
        )
    )
    patches["run_delegation_coordinator"] = AsyncMock(
        return_value=AgentResult(
            agent="delegation_coordinator",
            success=True,
            data={"delegations": []},
        )
    )
    if overrides:
        patches.update(overrides)
    return patches


@pytest.mark.asyncio
class TestOrchestratorRefactored:
    async def test_analyze_runs_selected_analysis_agents(self, sample_html):
        """Somente os sub-agentes relevantes devem ser chamados no pipeline ANALYZE."""
        patches = _patch_all_analysis_agents()
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)
        assert result.success is True
        assert result.agent == "orchestrator"
        assert "issues" in result.data
        patches["run_classifier"].assert_called_once()
        for name in EXPECTED_SAMPLE_SELECTED_AGENT_MOCKS:
            patches[name].assert_called_once()
        for name in EXPECTED_SAMPLE_SKIPPED_AGENT_MOCKS:
            patches[name].assert_not_called()

    async def test_batch_collect_is_active_during_analysis_agents_but_not_classifier(self, sample_html):
        """Batch Inference (ver batch_collector.py): a coleta tem que estar
        LIGADA quando os agentes de análise rodam (dentro do gather) e
        DESLIGADA quando o classificador roda (decide quem roda, tem que ser
        real mesmo em modo de coleta)."""
        classifier_saw_collecting = []
        agent_saw_collecting = []

        async def _classifier(html):
            classifier_saw_collecting.append(batch_collector.is_collecting())
            return AgentResult(agent="classifier", success=True, data={"technologies": []})

        async def _perceiver(html):
            agent_saw_collecting.append(batch_collector.is_collecting())
            return make_result("run_perceiver")

        patches = _patch_all_analysis_agents({
            "run_classifier": _classifier,
            "run_perceiver": _perceiver,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            await orchestrate(sample_html, TaskType.ANALYZE, batch_collect=True)

        assert classifier_saw_collecting == [False]
        assert agent_saw_collecting == [True]
        assert batch_collector.is_collecting() is False  # desligado depois, nao vaza pro proximo teste

    async def test_batch_collect_false_never_touches_the_collector(self, sample_html):
        """Comportamento padrao (batch_collect=False, default): nunca liga a coleta."""
        seen = []

        async def _perceiver(html):
            seen.append(batch_collector.is_collecting())
            return make_result("run_perceiver")

        patches = _patch_all_analysis_agents({"run_perceiver": _perceiver})
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            await orchestrate(sample_html, TaskType.ANALYZE)

        assert seen == [False]

    async def test_orchestrator_runs_visual_a11y(self, sample_html):
        """O agente visual deve rodar se screenshot_base64 for fornecido."""
        patches = _patch_all_analysis_agents()
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE, screenshot_base64="fake_screenshot")
        assert result.success is True
        assert "agent_metrics" in result.data
        # 22 métricas (20 subagentes selecionados + 1 visual + 1 classificador)
        assert len(result.data["agent_metrics"]) == 22
        patches["run_visual_a11y"].assert_called_once()

    async def test_analyze_result_includes_agent_metrics(self, sample_html):
        """Resultado ANALYZE deve incluir agent_metrics dos agentes selecionados."""
        patches = _patch_all_analysis_agents()
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)
        assert "agent_metrics" in result.data
        assert len(result.data["agent_metrics"]) == 21
        for m in result.data["agent_metrics"]:
            assert "agent" in m
            assert "duration_ms" in m
            assert "issues_found" in m
            assert "success" in m

    async def test_issues_merged_from_all_agents(self, sample_html):
        """Issues dos sub-agentes devem ser mesclados."""
        issue_a = make_issue("perceiver-1", "1.1.1 Non-text Content", "img")
        issue_b = make_issue("operability-1", "2.1.1 Keyboard", "div")
        issue_c = make_issue("css-1", "2.4.7 Focus Visible", "button")
        issue_d = make_issue("react-1", "2.1.1 Keyboard", "div.btn")
        issue_e = make_issue("screen-reader-1", "1.3.1 Info and Relationships", "h3")
        issue_f = make_issue("mobile-1", "1.4.4 Resize Text", "meta[viewport]")

        reviewer_mock = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [issue_a, issue_b, issue_c, issue_d, issue_e, issue_f], "removed_false_positives": 0}
        ))
        patches = _patch_all_analysis_agents(
            {
                "run_perceiver": AsyncMock(return_value=make_result("perceiver", [issue_a])),
                "run_operability": AsyncMock(return_value=make_result("operability", [issue_b])),
                "run_css_analyzer": AsyncMock(return_value=make_result("css_analyzer", [issue_c])),
                "run_react_framework": AsyncMock(return_value=make_result("react_framework", [issue_d])),
                "run_screen_reader": AsyncMock(return_value=make_result("screen_reader", [issue_e])),
                "run_mobile_a11y": AsyncMock(return_value=make_result("mobile_a11y", [issue_f])),
                "run_a11y_expert_reviewer": reviewer_mock,
            }
        )
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        assert len(result.data["issues"]) == 6

    async def test_failed_subagent_logged_but_pipeline_continues(self, sample_html):
        """Falha de sub-agente não deve derrubar o pipeline — outros continuam."""
        patches = _patch_all_analysis_agents(
            {
                "run_css_analyzer": AsyncMock(
                    return_value=AgentResult(agent="css_analyzer", success=False, data={}, error="timeout")
                ),
            }
        )
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)
        # Pipeline deve continuar com sucesso, apenas sem issues do agente falho
        assert result.success is True
        assert "issues" in result.data

    async def test_timed_handles_exception_without_crashing_pipeline(self, sample_html):
        """Agente que lança exceção deve ser capturado por _timed; pipeline OK."""
        patches = _patch_all_analysis_agents(
            {
                "run_wcag_semantics": AsyncMock(side_effect=RuntimeError("crash")),
            }
        )
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)
        assert result.success is True
        # O agente que falhou deve aparecer como failure nas métricas
        failed = [m for m in result.data["agent_metrics"] if not m["success"]]
        assert any(m["agent"] == "wcag_semantics" for m in failed)

    async def test_deduplication_removes_same_criterion_and_element(self):
        """Issues com mesmo criterion+element devem ser removidos."""
        dup_a = AccessibilityIssue(
            id="a",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img",
            description="d",
            suggestion="s",
        )
        dup_b = AccessibilityIssue(
            id="b",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.HIGH,
            element="img",
            description="d2",
            suggestion="s2",
        )
        unique = _deduplicate_issues([dup_a, dup_b])
        assert len(unique) == 1
        assert unique[0].id == "a"

    async def test_deduplication_keeps_different_elements(self):
        issue_a = AccessibilityIssue(
            id="a",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img#logo",
            description="d",
            suggestion="s",
        )
        issue_b = AccessibilityIssue(
            id="b",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img#banner",
            description="d",
            suggestion="s",
        )
        unique = _deduplicate_issues([issue_a, issue_b])
        assert len(unique) == 2

    async def test_guardrail_truncates_at_150(self, sample_html):
        """Mais de 150 issues deve ser truncado."""
        many = [make_issue(f"i-{n}", element=f"el-{n}") for n in range(200)]
        async def reviewer_passthrough(issues, **_kwargs):
            return AgentResult(
                agent="a11y_expert_reviewer",
                success=True,
                data={
                    "issues": [i.model_dump() if hasattr(i, "model_dump") else i for i in issues],
                    "removed_false_positives": 0,
                },
            )
        patches = _patch_all_analysis_agents(
            {
                "run_perceiver": AsyncMock(return_value=make_result("perceiver", many)),
                "run_a11y_expert_reviewer": AsyncMock(side_effect=reviewer_passthrough),
            }
        )
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert len(result.data["issues"]) <= 150

    async def test_selected_agents_fail_returns_success_false(self, sample_html):
        """Quando o conjunto selecionado falha por completo, retornar success=False com error."""
        all_fail_patches = {
            name: AsyncMock(
                return_value=AgentResult(
                    agent=name, success=False, data={}, error="401 Invalid API Key"
                )
            )
            for name in _patch_all_analysis_agents()
        }
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **all_fail_patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is False
        assert result.error is not None
        assert "agentes" in result.error.lower()
        assert "agent_metrics" in result.data
        assert len(result.data["agent_metrics"]) == 16

    async def test_partial_failure_returns_success_true_with_warning(self, sample_html):
        """Quando alguns (não todos) agentes falham, success=True mas com campo 'warning'."""
        issue = make_issue("p-1")
        reviewer_mock = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=False,
            data={"issues": [issue], "fallback": True},
            error="API key missing (mocked)",
        ))
        patches = _patch_all_analysis_agents(
            {
                "run_perceiver": AsyncMock(return_value=make_result("perceiver", [issue])),
                "run_css_analyzer": AsyncMock(
                    return_value=AgentResult(agent="css_analyzer", success=False, data={}, error="timeout")
                ),
                "run_a11y_expert_reviewer": reviewer_mock,
            }
        )
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        assert "warning" in result.data
        # Pipeline agora tem 20 agentes (19 paralelos + a11y_expert_reviewer)
        # css_analyzer falha + expert_reviewer sem API key no CI = 2 falhas esperadas
        # O importante e que o warning existe e menciona o total correto de agentes
        assert "agentes falharam" in result.data["warning"]
        assert len(result.data["issues"]) >= 1

    # ── Novos testes: a11y_expert_reviewer integrado ao pipeline ──────────────

    async def test_expert_reviewer_called_when_issues_exist(self, sample_html):
        """a11y_expert_reviewer deve ser chamado quando existem issues apos merge."""
        issue = make_issue("p-1", element="img")
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [issue])),
        })
        mock_reviewer = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [issue], "removed_false_positives": 0, "reviewed_count": 1},
        ))
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches), patch(
            "backend.src.agents.orchestrator.orchestrator.run_a11y_expert_reviewer",
            new=mock_reviewer,
        ):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        mock_reviewer.assert_called_once()
        assert result.success is True

    async def test_expert_reviewer_not_called_when_no_issues(self, sample_html):
        """a11y_expert_reviewer NÃO deve ser chamado quando não ha issues."""
        patches = _patch_all_analysis_agents()  # todos retornam lista vazia
        mock_reviewer = AsyncMock()
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches), patch(
            "backend.src.agents.orchestrator.orchestrator.run_a11y_expert_reviewer",
            new=mock_reviewer,
        ):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        mock_reviewer.assert_not_called()
        assert result.success is True

    async def test_expert_reviewer_failure_fallback_preserves_issues(self, sample_html):
        """Se o expert_reviewer falhar, pipeline continua com issues originais (graceful)."""
        issue = make_issue("p-1", element="img")
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [issue])),
        })
        # Reviewer falha mas retorna fallback com issues originais
        mock_reviewer = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=False,
            data={"issues": [issue], "fallback": True},
            error="LLM timeout",
        ))
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches), patch(
            "backend.src.agents.orchestrator.orchestrator.run_a11y_expert_reviewer",
            new=mock_reviewer,
        ):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        # Pipeline não cai — issues originais preservados pelo fallback
        assert result.success is True
        assert len(result.data["issues"]) >= 1

    async def test_expert_reviewer_false_positive_reduces_issue_count(self, sample_html):
        """Issues removidos pelo reviewer devem não aparecer no resultado final."""
        issue_real = make_issue("p-1", element="img#hero")
        issue_fp = make_issue("p-2", element="svg[aria-hidden='true']")
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [issue_real, issue_fp])),
        })
        # Reviewer remove o falso positivo, retorna apenas o real
        mock_reviewer = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [issue_real], "removed_false_positives": 1, "reviewed_count": 1},
        ))
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches), patch(
            "backend.src.agents.orchestrator.orchestrator.run_a11y_expert_reviewer",
            new=mock_reviewer,
        ):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert result.data["issues"][0]["element"] == "img#hero"


# ── Novos entregaveis de QA/agile ligados ao pipeline: VPAT e TESTS ───────────


@pytest.mark.asyncio
async def test_orchestrate_vpat_invokes_vpat_reporter(sample_html):
    """TaskType.VPAT roda a análise e delega ao vpat_reporter com target/product_name."""
    patches = _patch_all_analysis_agents({
        "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("perceiver-1")])),
    })
    reviewer = AsyncMock(return_value=AgentResult(
        agent="a11y_expert_reviewer",
        success=True,
        data={"issues": [make_issue("perceiver-1")], "removed_false_positives": 0},
    ))
    vpat_mock = AsyncMock(return_value=AgentResult(agent="vpat_reporter", success=True, data={"vpat": {}}))
    with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches,
                        run_a11y_expert_reviewer=reviewer, run_vpat_reporter=vpat_mock):
        result = await orchestrate(sample_html, TaskType.VPAT, target="https://x.com", product_name="App")

    assert result.success is True
    assert result.agent == "vpat_reporter"
    vpat_mock.assert_called_once()
    kwargs = vpat_mock.call_args.kwargs
    assert kwargs["target"] == "https://x.com"
    assert kwargs["product_name"] == "App"


@pytest.mark.asyncio
async def test_orchestrate_tests_invokes_test_generator(sample_html):
    """TaskType.TESTS roda a análise e delega ao test_generator com target."""
    patches = _patch_all_analysis_agents({
        "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("perceiver-1")])),
    })
    reviewer = AsyncMock(return_value=AgentResult(
        agent="a11y_expert_reviewer",
        success=True,
        data={"issues": [make_issue("perceiver-1")], "removed_false_positives": 0},
    ))
    tg_mock = AsyncMock(return_value=AgentResult(agent="test_generator", success=True, data={"suite": {}}))
    with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches,
                        run_a11y_expert_reviewer=reviewer, run_test_generator=tg_mock):
        result = await orchestrate(sample_html, TaskType.TESTS, target="file.html")

    assert result.success is True
    assert result.agent == "test_generator"
    tg_mock.assert_called_once()
    assert tg_mock.call_args.kwargs["target"] == "file.html"


@pytest.mark.asyncio
async def test_orchestrator_filters_framework_agents_when_only_react_detected(sample_html):
    """Orquestrador deve executar apenas o ReactFrameworkAgent se apenas 'react' for detectado."""
    patches = _patch_all_analysis_agents()
    # Mock do classificador retornando apenas React
    patches["run_classifier"] = AsyncMock(
        return_value=AgentResult(
            agent="classifier",
            success=True,
            data={"technologies": ["react"]},
        )
    )
    with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
        result = await orchestrate(sample_html, TaskType.ANALYZE)

    assert result.success is True
    # React deve ter sido chamado, mas vue, angular, svelte e tailwind não
    patches["run_react_framework"].assert_called_once()
    patches["run_vue_framework"].assert_not_called()
    patches["run_angular_framework"].assert_not_called()
    patches["run_svelte_framework"].assert_not_called()
    patches["run_tailwind_css"].assert_not_called()

    # Outros agentes universais devem ter sido chamados
    patches["run_perceiver"].assert_called_once()
    patches["run_screen_reader"].assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_skips_framework_agents_on_classifier_failure(sample_html):
    """Orquestrador deve continuar sem chamar frameworks no escuro."""
    patches = _patch_all_analysis_agents()
    # Mock do classificador falhando
    patches["run_classifier"] = AsyncMock(
        return_value=AgentResult(
            agent="classifier",
            success=False,
            data={"technologies": []},
            error="API key missing",
        )
    )
    with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
        result = await orchestrate(sample_html, TaskType.ANALYZE)

    assert result.success is True
    # Frameworks não devem rodar sem evidencia confiavel do classificador.
    patches["run_react_framework"].assert_not_called()
    patches["run_vue_framework"].assert_not_called()
    patches["run_angular_framework"].assert_not_called()
    patches["run_svelte_framework"].assert_not_called()
    patches["run_tailwind_css"].assert_not_called()
    # Agentes base e condicionais por estrutura continuam protegendo a análise.
    patches["run_perceiver"].assert_called_once()
    patches["run_forms_a11y"].assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_routes_tables_data_and_link_checker_by_structural_evidence():
    """tables_data/link_checker sao condicionais como os demais (ver
    _conditional_agent_reasons) -- so rodam se o HTML tiver <table>/<a href>,
    nao no sample_html padrao (sem nenhum dos dois)."""
    html_with_table_and_link = "<html><body><table><tr><td>x</td></tr></table><a href='/x'>link</a></body></html>"
    patches = _patch_all_analysis_agents()
    with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
        result = await orchestrate(html_with_table_and_link, TaskType.ANALYZE)

    assert result.success is True
    patches["run_tables_data"].assert_called_once()
    patches["run_link_checker"].assert_called_once()


@pytest.mark.asyncio
class TestDynamicDelegation:
    """Delegacao dinamica agente-a-agente (ver delegation_coordinator.py):
    apos a rodada 1, um coordenador (LLM) pode decidir chamar um agente que
    tinha sido pulado, com base no que a rodada 1 encontrou."""

    async def test_no_delegation_when_coordinator_returns_empty(self, sample_html):
        """Resposta padrao (sem delegacoes) nao deve acionar nenhum agente extra."""
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        patches["run_delegation_coordinator"].assert_called_once()
        patches["run_widgets_a11y"].assert_not_called()

    async def test_delegated_agent_is_invoked_and_its_issues_merged(self, sample_html):
        """Quando o coordenador delega para um agente pulado, o orchestrator
        deve chama-lo de verdade e mesclar os issues dele no resultado final."""
        delegated_issue = make_issue("widgets-1", "4.1.2 Name, Role, Value", "div[role=tab]")
        reviewer_mock = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [make_issue("p-1"), delegated_issue], "removed_false_positives": 0},
        ))
        coordinator_mock = AsyncMock(side_effect=[
            AgentResult(
                agent="delegation_coordinator",
                success=True,
                data={"delegations": [{"target_agent": "widgets_a11y", "reason": "achados sugerem widget custom"}]},
            ),
            AgentResult(agent="delegation_coordinator", success=True, data={"delegations": []}),
        ])
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
            "run_widgets_a11y": AsyncMock(return_value=make_result("widgets_a11y", [delegated_issue])),
            "run_delegation_coordinator": coordinator_mock,
            "run_a11y_expert_reviewer": reviewer_mock,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        patches["run_widgets_a11y"].assert_called_once()
        issue_ids = {i["id"] for i in result.data["issues"]}
        assert "widgets-1" in issue_ids
        delegated_metric = next(m for m in result.data["agent_metrics"] if m["agent"] == "widgets_a11y")
        assert delegated_metric["delegated_by"] == "delegation_coordinator"

    async def test_delegation_not_attempted_when_no_issues_found(self, sample_html):
        """Sem nenhum issue na rodada 1, nao ha o que embasar uma delegacao --
        o coordenador nao deve ser chamado (economiza uma chamada de LLM)."""
        patches = _patch_all_analysis_agents()
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        patches["run_delegation_coordinator"].assert_not_called()

    async def test_delegation_loop_stops_when_coordinator_converges(self, sample_html):
        """Loop engineering: a rodada de delegacao para assim que o coordenador
        nao tem mais nada a delegar (convergencia), nao espera o limite de
        rodadas -- coordenador so deve ser chamado 2x (delega, depois convergencia vazia)."""
        delegated_issue = make_issue("widgets-1", "4.1.2 Name, Role, Value", "div[role=tab]")
        reviewer_mock = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [make_issue("p-1"), delegated_issue], "removed_false_positives": 0},
        ))
        coordinator_mock = AsyncMock(side_effect=[
            AgentResult(
                agent="delegation_coordinator",
                success=True,
                data={"delegations": [{"target_agent": "widgets_a11y", "reason": "achados sugerem widget custom"}]},
            ),
            AgentResult(agent="delegation_coordinator", success=True, data={"delegations": []}),
        ])
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
            "run_widgets_a11y": AsyncMock(return_value=make_result("widgets_a11y", [delegated_issue])),
            "run_delegation_coordinator": coordinator_mock,
            "run_a11y_expert_reviewer": reviewer_mock,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        assert coordinator_mock.call_count == 2

    async def test_delegation_loop_respects_max_rounds_backstop(self, sample_html):
        """Backstop real (sem loop aberto): mesmo que o coordenador SEMPRE
        delegue algo, o loop para no limite de MAX_DELEGATION_ROUNDS."""
        from backend.src.agents.orchestrator.orchestrator import MAX_DELEGATION_ROUNDS

        delegated_issue = make_issue("widgets-1", "4.1.2 Name, Role, Value", "div[role=tab]")
        reviewer_mock = AsyncMock(return_value=AgentResult(
            agent="a11y_expert_reviewer",
            success=True,
            data={"issues": [make_issue("p-1"), delegated_issue], "removed_false_positives": 0},
        ))
        # Coordenador "teimoso": delega widgets_a11y toda vez (simula um LLM
        # que ignora a lista de candidatos ja delegados) -- o loop tem que
        # parar sozinho pelo backstop, nunca rodar infinitamente.
        coordinator_mock = AsyncMock(return_value=AgentResult(
            agent="delegation_coordinator",
            success=True,
            data={"delegations": [{"target_agent": "widgets_a11y", "reason": "achados sugerem widget custom"}]},
        ))
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
            "run_widgets_a11y": AsyncMock(return_value=make_result("widgets_a11y", [delegated_issue])),
            "run_delegation_coordinator": coordinator_mock,
            "run_a11y_expert_reviewer": reviewer_mock,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        assert coordinator_mock.call_count == MAX_DELEGATION_ROUNDS

    async def test_pipeline_graph_is_explicit_and_observable(self, sample_html):
        """Graph engineering: o resultado da analise deve trazer um grafo
        explicito (nos + arestas), nao so o efeito colateral implicito de
        rodar os agentes -- inspecionavel sem ler logs."""
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        graph = result.data["pipeline_graph"]
        assert "nodes" in graph and "edges" in graph
        node_names = {n["agent"] for n in graph["nodes"]}
        assert "perceiver" in node_names
        assert "widgets_a11y" in node_names  # pulado, mas ainda um no do grafo
        perceiver_node = next(n for n in graph["nodes"] if n["agent"] == "perceiver")
        assert perceiver_node["state"] == "selected"
        classifier_edges = [e for e in graph["edges"] if e["from"] == "classifier"]
        assert any(e["to"] == "perceiver" for e in classifier_edges)

    async def test_delegation_not_attempted_with_only_agents(self, sample_html):
        """only_agents pula a classificacao/routing estrutural inteiramente --
        nao ha lista de 'agentes pulados' pra delegar, entao o coordenador nao roda."""
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE, only_agents=["perceiver"])

        assert result.success is True
        patches["run_delegation_coordinator"].assert_not_called()


@pytest.mark.asyncio
class TestGapResearchGate:
    """Verificacao automatica de lacuna (ver gap_research.py): achados de
    baixa confianca disparam uma pesquisa normativa real via Deep Research."""

    async def test_low_confidence_issue_triggers_gap_research_and_gets_enriched(self, sample_html):
        low_conf_issue = {**make_issue("p-1"), "confidence": "low"}

        async def reviewer_passthrough(issues, **_kwargs):
            return AgentResult(
                agent="a11y_expert_reviewer",
                success=True,
                data={"issues": [i.model_dump() for i in issues], "removed_false_positives": 0},
            )

        reviewer_mock = AsyncMock(side_effect=reviewer_passthrough)
        gap_research_mock = AsyncMock(return_value=AgentResult(
            agent="gap_research",
            success=True,
            data={"answer": "WCAG 1.1.1 confirms this is a genuine violation.", "issue_ids": ["p-1"]},
        ))
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [low_conf_issue])),
            "run_a11y_expert_reviewer": reviewer_mock,
            "run_gap_research_check": gap_research_mock,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        gap_research_mock.assert_called_once()
        issue = next(i for i in result.data["issues"] if i["id"] == "p-1")
        assert "WCAG 1.1.1 confirms" in (issue.get("why_technical") or "")

    async def test_no_low_confidence_issues_skips_gap_research(self, sample_html):
        gap_research_mock = AsyncMock(side_effect=AssertionError("nao deveria rodar"))
        patches = _patch_all_analysis_agents({
            "run_perceiver": AsyncMock(return_value=make_result("perceiver", [make_issue("p-1")])),
            "run_gap_research_check": gap_research_mock,
        })
        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            result = await orchestrate(sample_html, TaskType.ANALYZE)

        assert result.success is True
        gap_research_mock.assert_not_called()
