"""Testes da verificacao de anuncios de leitor de tela.

Feature real (2026-08-27): cruza a arvore de acessibilidade REAL do Chromium
(a mesma API que NVDA/JAWS/Narrator consultam) contra regras deterministicas
de nome acessivel ausente/generico -- nao e mais uma estimativa de LLM sobre
HTML bruto, e o NVDA real e usado so pra ler os achados em voz alta (canal de
fala ja existente em nvda_service.py, sem add-on nenhum)."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services.browser import AccessibilityTreeNode
from backend.src.services.screen_reader_verification import (
    ScreenReaderFinding,
    detect_screen_reader_findings,
    finding_to_issue_dict,
    verify_screen_reader_announcements,
)


def _node(role: str, name: str, path: str | None = None, interactive: bool = True) -> AccessibilityTreeNode:
    return AccessibilityTreeNode(role=role, name=name, path=path or role, is_interactive=interactive)


class TestDetectScreenReaderFindings:
    def test_flags_interactive_node_with_no_accessible_name(self):
        nodes = [_node("button", "")]
        findings = detect_screen_reader_findings(nodes)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].announcement_preview == "button"

    def test_flags_generic_accessible_name(self):
        nodes = [_node("link", "clique aqui")]
        findings = detect_screen_reader_findings(nodes)
        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert "clique aqui" in findings[0].problem

    def test_generic_name_check_is_case_insensitive(self):
        nodes = [_node("button", "CLIQUE AQUI")]
        findings = detect_screen_reader_findings(nodes)
        assert len(findings) == 1

    def test_does_not_flag_a_real_descriptive_name(self):
        nodes = [_node("button", "Enviar formulario de contato")]
        assert detect_screen_reader_findings(nodes) == []

    def test_ignores_non_interactive_nodes_even_without_a_name(self):
        """Um <div> ou heading sem nome nao e problema de anuncio de AT --
        so controles com os quais o usuario interage precisam de nome."""
        nodes = [_node("heading", "", interactive=False)]
        assert detect_screen_reader_findings(nodes) == []

    def test_multiple_nodes_each_evaluated_independently(self):
        nodes = [
            _node("button", "Fechar"),
            _node("link", "", path="nav > link"),
            _node("checkbox", "ok"),
        ]
        findings = detect_screen_reader_findings(nodes)
        assert len(findings) == 2
        assert {f.role for f in findings} == {"link", "checkbox"}


class TestVerifyScreenReaderAnnouncements:
    @pytest.mark.asyncio
    async def test_empty_when_browserless_not_configured(self):
        with (
            patch(
                "backend.src.services.screen_reader_verification.fetch_accessibility_tree_nodes",
                new=AsyncMock(return_value=[]),
            ),
            patch("backend.src.services.nvda_service.is_nvda_running", return_value=False),
        ):
            result = await verify_screen_reader_announcements("https://example.com")

        assert result.findings == []
        assert result.total_interactive_nodes == 0
        assert result.nvda_running is False
        assert result.spoken_findings == 0

    @pytest.mark.asyncio
    async def test_counts_only_interactive_nodes_in_total(self):
        nodes = [_node("heading", "Titulo", interactive=False), _node("button", "Enviar formulario de contato")]
        with (
            patch(
                "backend.src.services.screen_reader_verification.fetch_accessibility_tree_nodes",
                new=AsyncMock(return_value=nodes),
            ),
            patch("backend.src.services.nvda_service.is_nvda_running", return_value=False),
        ):
            result = await verify_screen_reader_announcements("https://example.com")

        assert result.total_interactive_nodes == 1
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_speaks_findings_via_nvda_when_requested_and_running(self):
        nodes = [_node("button", ""), _node("link", "")]
        with (
            patch(
                "backend.src.services.screen_reader_verification.fetch_accessibility_tree_nodes",
                new=AsyncMock(return_value=nodes),
            ),
            patch("backend.src.services.nvda_service.is_nvda_running", return_value=True),
            patch(
                "backend.src.services.nvda_service.speak_text",
                return_value={"status": "ok", "spoken": True},
            ) as mock_speak,
        ):
            result = await verify_screen_reader_announcements("https://example.com", speak_via_nvda=True)

        assert result.nvda_running is True
        assert result.spoken_findings == 2
        assert mock_speak.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_speak_when_nvda_not_running_even_if_requested(self):
        nodes = [_node("button", "")]
        with (
            patch(
                "backend.src.services.screen_reader_verification.fetch_accessibility_tree_nodes",
                new=AsyncMock(return_value=nodes),
            ),
            patch("backend.src.services.nvda_service.is_nvda_running", return_value=False),
            patch("backend.src.services.nvda_service.speak_text") as mock_speak,
        ):
            result = await verify_screen_reader_announcements("https://example.com", speak_via_nvda=True)

        assert result.spoken_findings == 0
        mock_speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_max_spoken_cap(self):
        nodes = [_node("button", "") for _ in range(10)]
        with (
            patch(
                "backend.src.services.screen_reader_verification.fetch_accessibility_tree_nodes",
                new=AsyncMock(return_value=nodes),
            ),
            patch("backend.src.services.nvda_service.is_nvda_running", return_value=True),
            patch(
                "backend.src.services.nvda_service.speak_text",
                return_value={"status": "ok", "spoken": True},
            ) as mock_speak,
        ):
            result = await verify_screen_reader_announcements(
                "https://example.com", speak_via_nvda=True, max_spoken=3
            )

        assert result.spoken_findings == 3
        assert mock_speak.call_count == 3


class TestFindingToIssueDict:
    def test_maps_to_the_accessibility_issue_shape(self):
        finding = ScreenReaderFinding(
            role="button", path="main > button", severity="critical",
            problem="Sem nome acessivel", announcement_preview="button",
        )
        issue = finding_to_issue_dict(finding, "https://example.com", 0)

        from backend.src.shared.models import AccessibilityIssue

        built = AccessibilityIssue(**issue)  # levanta se o shape estiver errado
        assert built.severity.value == "critical"
        assert built.guideline.value == "WAI-ARIA"
        assert built.url == "https://example.com"
