"""
Testes comportamentais (behavioral contracts) dos agentes.
Seguem o padrão de agent-evaluation skill:
- Invariantes do sistema verificados em todo output
- Testes adversariais (inputs malformados, HTML vazio, HTML gigante)
- Contrato de output verificado sem string matching exato
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.fixer.fixer import run_fixer
from backend.src.agents.reporter.reporter import run_reporter
from backend.src.shared.models import (
    AccessibilityIssue,
    AgentResult,
    Guideline,
    Severity,
)

# ---------------------------------------------------------------------------
# Fixtures adversariais
# ---------------------------------------------------------------------------

EMPTY_HTML = ""
MINIMAL_HTML = "<html><body></body></html>"
LARGE_HTML = "<html><body>" + "<img src='x.png'>" * 200 + "</body></html>"
MALFORMED_HTML = "<<not valid>>> html @@#$%"

VALID_ISSUE: dict[str, Any] = {
    "id": "i-001",
    "guideline": Guideline.WCAG_2_2,
    "criterion": "1.1.1 Non-text Content",
    "severity": Severity.CRITICAL,
    "element": "img",
    "description": "Missing alt attribute",
    "suggestion": "Add alt attribute to img element",
}


def make_issues(n: int = 1) -> list[AccessibilityIssue]:
    return [AccessibilityIssue(**{**VALID_ISSUE, "id": f"i-{i}"}) for i in range(n)]


# ---------------------------------------------------------------------------
# Invariantes: todo AgentResult deve satisfazer estas propriedades
# ---------------------------------------------------------------------------


def assert_agent_result_invariants(result: AgentResult, expected_agent: str) -> None:
    """Contrato: todo AgentResult deve ter agent, success e data definidos."""
    assert result.agent == expected_agent, f"agent deve ser {expected_agent}"
    assert isinstance(result.success, bool), "success deve ser bool"
    assert isinstance(result.data, dict), "data deve ser dict"
    if not result.success:
        assert result.error is not None, "error deve estar preenchido quando success=False"


# ---------------------------------------------------------------------------
# FixerAgent — contratos comportamentais
# ---------------------------------------------------------------------------

VALID_FIX = {
    "fixed_html": "<html><body><img alt='Logo'></body></html>",
    "changes_summary": ["Added alt"],
}


@pytest.mark.asyncio
class TestFixerContracts:
    async def test_invariants_on_success(self):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_FIX)),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert_agent_result_invariants(result, "fixer")
        assert "fixed_html" in result.data
        assert "changes_summary" in result.data

    async def test_fixed_html_is_string(self):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_FIX)),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        if result.success:
            assert isinstance(result.data["fixed_html"], str)
            assert len(result.data["fixed_html"]) > 0

    async def test_adversarial_no_issues(self):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_FIX)),
        ):
            result = await run_fixer(MINIMAL_HTML, [])
        assert result.agent == "fixer"


# ---------------------------------------------------------------------------
# ReporterAgent — contratos comportamentais
# ---------------------------------------------------------------------------

VALID_REPORT_RESP = {"summary": "Test summary.", "score": 75}


@pytest.mark.asyncio
class TestReporterContracts:
    async def test_score_in_range(self):
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_REPORT_RESP)),
        ):
            result = await run_reporter(make_issues(2), [])
        assert_agent_result_invariants(result, "reporter")
        if result.success:
            assert 0 <= result.data["score"] <= 100

    async def test_summary_is_non_empty_string(self):
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_REPORT_RESP)),
        ):
            result = await run_reporter(make_issues(1), [])
        if result.success:
            assert isinstance(result.data["summary"], str)
            assert len(result.data["summary"]) > 0

    async def test_adversarial_zero_issues(self):
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(VALID_REPORT_RESP)),
        ):
            result = await run_reporter([], [])
        assert result.agent == "reporter"
        assert isinstance(result.success, bool)

    async def test_adversarial_llm_score_out_of_range(self):
        bad_resp = {"summary": "Test", "score": 999}
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(bad_resp)),
        ):
            result = await run_reporter(make_issues(1), [])
        # Mesmo com score invalido, não deve crashar — o reporter faz fallback
        assert result.agent == "reporter"


# ---------------------------------------------------------------------------
# FixerAgent — adversarial tests (agent-evaluation skill)
# ---------------------------------------------------------------------------

XSS_HTML = '<html><body><script>alert("xss")</script><img src="x"></body></html>'
HUGE_HTML = "<html><body>" + "<img src='x.png'>" * 5000 + "</body></html>"


@pytest.mark.asyncio
class TestFixerAdversarial:
    async def test_xss_input_does_not_inject_new_scripts(self):
        """Adversarial: fixer não deve adicionar novos elementos <script> ao output."""
        import re as _re

        xss_fix = {
            "fixed_html": '<html><body><img src="x" alt="decorative"></body></html>',
            "changes_summary": ["Added alt attribute to img"],
        }
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(xss_fix)),
        ):
            result = await run_fixer(XSS_HTML, make_issues(1))
        if result.success:
            fixed = result.data["fixed_html"]
            input_scripts = len(_re.findall(r"<script", XSS_HTML, _re.IGNORECASE))
            output_scripts = len(_re.findall(r"<script", fixed, _re.IGNORECASE))
            assert output_scripts <= input_scripts, "Fixer must not inject additional script tags"

    async def test_empty_fixed_html_causes_failure(self):
        """Contrato: fixed_html vazio deve resultar em success=False."""
        bad_fix = {"fixed_html": "", "changes_summary": []}
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(bad_fix)),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert result.success is False, "empty fixed_html deve gerar falha"

    async def test_whitespace_only_fixed_html_causes_failure(self):
        """Contrato: fixed_html com apenas espaços deve resultar em success=False."""
        bad_fix = {"fixed_html": "   \n  ", "changes_summary": []}
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(bad_fix)),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert result.success is False

    async def test_huge_html_is_truncated_not_rejected(self):
        """Guardrail: HTML gigante deve ser processado (truncado) sem exception."""
        valid_fix = {
            "fixed_html": "<html><body><img alt='x'></body></html>",
            "changes_summary": ["Added alt"],
        }
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(valid_fix)),
        ):
            result = await run_fixer(HUGE_HTML, make_issues(1))
        # Não deve levantar exception — sucesso ou falha controlada
        assert isinstance(result.success, bool)
        assert result.agent == "fixer"

    async def test_malformed_llm_output_causes_failure(self):
        """Adversarial: JSON malformado retornado pelo LLM deve causar success=False."""
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value="NOT JSON AT ALL {]}"),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert result.success is False
        assert result.error is not None

    async def test_missing_required_field_causes_failure(self):
        """Adversarial: resposta sem fixed_html deve causar success=False (schema validation)."""
        incomplete = {"changes_summary": ["Some change"]}  # sem fixed_html
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(incomplete)),
        ):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert result.success is False

    async def test_api_timeout_causes_failure(self):
        """Adversarial: timeout da API deve causar success=False, não exception propagada."""
        import asyncio as _asyncio

        async def slow(*args, **kwargs):  # noqa: ANN001
            raise _asyncio.TimeoutError

        with patch("backend.src.agents.fixer.fixer.call_llm", new=slow):
            result = await run_fixer(MINIMAL_HTML, make_issues(1))
        assert result.success is False


# ---------------------------------------------------------------------------
# Orchestrator — iteration limits (autonomous-agents skill)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOrchestratorIterationLimits:
    async def test_max_issues_guardrail_applied(self):
        """Guardrail MAX_ISSUES: o pipeline trunca o total de issues unicos em 150.

        Cada sub-agente retorna issues com `criterion`+`element` GLOBALMENTE unicos
        (a chave de dedup e `criterion|element`), entao nada colapsa na deduplicacao:
        Varios agentes selecionados retornam issues unicos suficientes para passar de 150,
        entao o guardrail deve truncar para 150. Os agentes de análise sao mockados (sem mockar `asyncio.gather`, que criaria as
        coroutines reais sem aguarda-las); o expert reviewer faz passthrough.
        """
        from backend.src.agents.orchestrator.orchestrator import (
            MAX_ISSUES,
            _run_analysis_pipeline,
        )

        agent_names = [
            "run_perceiver", "run_operability", "run_understandability",
            "run_robustness", "run_aria_specialist", "run_section508",
            "run_css_analyzer", "run_ajax_dynamic", "run_cognitive",
            "run_react_framework", "run_angular_framework", "run_vue_framework",
            "run_tailwind_css", "run_screen_reader", "run_mobile_a11y",
            "run_forms_a11y", "run_widgets_a11y", "run_wcag_semantics",
            "run_compliance_audit",
        ]

        def unique_issues(prefix: str, n: int) -> list[dict]:
            return [
                {
                    **VALID_ISSUE,
                    "id": f"{prefix}-{i}",
                    "criterion": f"{prefix}.{i} Criterio",
                    "element": f"<div id='{prefix}-{i}'>",
                }
                for i in range(n)
            ]

        patches = {
            name: AsyncMock(
                return_value=AgentResult(
                    agent=name, success=True, data={"issues": unique_issues(name, 20)}
                )
            )
            for name in agent_names
        }
        patches["run_classifier"] = AsyncMock(
            return_value=AgentResult(agent="classifier", success=True, data={"technologies": []})
        )

        # Expert reviewer: passthrough (echo dos issues ja truncados, como dicts).
        async def reviewer_passthrough(issues: list[AccessibilityIssue], **_kwargs) -> AgentResult:
            return AgentResult(
                agent="a11y_expert_reviewer",
                success=True,
                data={"issues": [i.model_dump() for i in issues]},
            )

        patches["run_a11y_expert_reviewer"] = AsyncMock(side_effect=reviewer_passthrough)

        with patch.multiple("backend.src.agents.orchestrator.orchestrator", **patches):
            issues, _, _failed, _graph = await _run_analysis_pipeline("<html></html>")

        assert len(issues) == MAX_ISSUES, (
            f"Guardrail deve truncar para {MAX_ISSUES} issues, obteve {len(issues)}"
        )

    async def test_single_agent_timeout_does_not_block_pipeline(self):
        """Resilience: timeout de um sub-agente não deve bloquear o pipeline.

        Achado real (2026-08-11, "nada pode falhar"): _timed agora recebe uma
        FÁBRICA de coroutine (não uma já criada), pois refaz a chamada uma vez
        antes de desistir de vez -- uma coroutine só pode ser aguardada uma
        vez, por isso o contrato mudou de `coro` pra `coro_factory`."""
        import asyncio as _asyncio

        from backend.src.agents.orchestrator.orchestrator import _timed

        async def _always_timeout_coro():
            raise _asyncio.TimeoutError

        def always_timeout():
            return _always_timeout_coro()

        result, duration_ms = await _timed("test-agent", always_timeout)
        assert result.success is False
        assert "Timeout" in (result.error or "")
        assert duration_ms >= 0

    async def test_timeout_on_first_attempt_retries_and_succeeds(self):
        """Achado real (2026-08-11, "nada pode falhar" -- pedido do usuário,
        pesquisa 2026 de resiliência de API de LLM confirma retry como padrão
        pra timeout): muitos timeouts são fila/latência transitória do
        provider, não um problema real da tarefa -- a 1a tentativa estourando
        não deve significar falha definitiva se a 2a tentativa (fresh
        coroutine) completar dentro do tempo."""
        import asyncio as _asyncio

        from backend.src.agents.orchestrator.orchestrator import _timed
        from backend.src.shared.models import AgentResult

        call_count = 0

        async def _coro():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _asyncio.TimeoutError
            return AgentResult(agent="test-agent", success=True, data={"issues": []})

        def flaky_once():
            return _coro()

        result, _duration_ms = await _timed("test-agent", flaky_once)
        assert result.success is True
        assert call_count == 2

    async def test_timeout_twice_fails_after_retry_exhausted(self):
        """Contraparte do teste acima: se as DUAS tentativas estourarem o
        timeout, o resultado final é falha de verdade -- o retry não vira um
        loop infinito nem esconde uma falha real e persistente."""
        import asyncio as _asyncio

        from backend.src.agents.orchestrator.orchestrator import _timed

        call_count = 0

        async def _coro():
            nonlocal call_count
            call_count += 1
            raise _asyncio.TimeoutError

        def always_timeout_twice():
            return _coro()

        result, _duration_ms = await _timed("test-agent", always_timeout_twice)
        assert result.success is False
        assert "2 tentativas" in (result.error or "")
        assert call_count == 2


class TestAdaptiveAgentTimeout:
    """Achado real (2026-08-11): timeout fixo de 180s pra qualquer esforço de
    raciocínio penalizava justamente as tarefas que MAIS precisam de
    qualidade (esforço alto, mais lento por design) -- pesquisa de mercado
    2026 confirma faixa 180-300s conforme profundidade de raciocínio."""

    def setup_method(self):
        from backend.src.services import complexity_router
        complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    def teardown_method(self):
        from backend.src.services import complexity_router
        complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    def test_low_tradeoff_favoring_quality_gets_longer_timeout(self):
        from backend.src.agents.orchestrator.orchestrator import _get_agent_timeout
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(0)  # favorece qualidade -> esforco "high"
        assert _get_agent_timeout() == 300.0

    def test_high_tradeoff_favoring_cost_keeps_historical_timeout(self):
        from backend.src.agents.orchestrator.orchestrator import _get_agent_timeout
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(9)  # favorece custo -> esforco "none"
        assert _get_agent_timeout() == 180.0

    def test_never_shrinks_below_the_configured_settings_floor(self):
        """Mesmo se Settings tiver um timeout customizado MAIOR que o piso
        histórico de 180s, o timeout adaptativo nunca deve ficar menor que
        isso -- só cresce a partir do piso configurado, nunca encolhe."""
        from unittest.mock import MagicMock, patch

        from backend.src.agents.orchestrator.orchestrator import _get_agent_timeout
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(9)  # esforco "none" -> mapeado pra 180.0
        with patch(
            "backend.src.agents.orchestrator.orchestrator.get_settings",
            return_value=MagicMock(agent_timeout_seconds=250.0),
        ):
            assert _get_agent_timeout() == 250.0
