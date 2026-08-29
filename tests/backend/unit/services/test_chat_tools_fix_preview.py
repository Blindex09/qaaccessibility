"""Testes de regressao para o live preview em fix_and_zip_files.

Bug real corrigido: fix_and_zip_files, quando usava o fallback de HTML/URL da
ultima analise, re-auditava o HTML dentro de _run_fixes_and_generate_zip. A
re-auditoria frequentemente nao encontrava os mesmos issues (especialmente em
HTML semantico reduzido), entao o run_fixer nao era chamado, nenhuma pagina de
preview era salva em last_fix_store, e open_live_preview falhava silenciosamente.

A correcao faz com que o fallback reutilize os issues ja detectados pela
analise anterior, garantindo que o fixer rode e que o live preview tenha
paginas para exibir.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.src.services import chat_tools, session_context
from backend.src.services.chat_tools import fix_and_zip_files
from backend.src.services.last_fix_store import get_last_fix

HTML_SAMPLE = """<!DOCTYPE html>
<html>
<head><title>Example</title></head>
<body>
<a href="#">Learn more</a>
</body>
</html>"""


class AccessibilityIssueMock:
    """Objeto leve que substitui AccessibilityIssue para o fixer."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "issue-1")
        self.criterion = kwargs.get("criterion", "2.4.4")
        self.severity = kwargs.get("severity", "medium")
        self.description = kwargs.get("description", "Link sem texto descritivo")
        self.element = kwargs.get("element", '<a href="#">Learn more</a>')
        self.url = kwargs.get("url", "")

    def model_dump(self, **_):
        return {
            "id": self.id,
            "criterion": self.criterion,
            "severity": self.severity,
            "description": self.description,
            "element": self.element,
            "url": self.url,
        }

    def model_copy(self, *, update):
        updated = {**self.model_dump(), **update}
        return AccessibilityIssueMock(**updated)


@pytest.fixture
def session_context_fixture():
    session_id = "fix-preview-test-session"
    token = session_context.set_current_session(session_id)
    yield session_id
    session_context.reset_current_session(token)


class TestFixAndZipFilesPreviewFallback:
    def test_reuses_cached_issues_and_generates_preview_pages(self, session_context_fixture):
        """Quando nenhum 'files' e passado, usa issues do cache e gera preview."""
        session_id = session_context_fixture

        issues = [
            {
                "id": "issue-1",
                "criterion": "2.4.4",
                "severity": "medium",
                "description": "Link sem texto descritivo",
                "element": '<a href="#">Learn more</a>',
                "guideline": "WCAG 2.4.4",
                "suggestion": "Use texto descritivo no link",
            }
        ]

        fixed_html = HTML_SAMPLE.replace("Learn more", "Learn more about accessibility")

        with patch(
            "backend.src.services.chat_tools._render_html_to_screenshot",
            return_value="fake-screenshot",
        ), patch(
            "backend.src.services.chat_tools._verify_layout_visually",
            return_value={"layout_ok": True},
        ), patch(
            "backend.src.services.chat_tools._sanitize_accessible_links_and_labels",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.chat_tools._strip_injected_script_vectors",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.last_analysis_store.get_last_analysis",
            return_value=(issues, "https://example.org"),
        ), patch(
            "backend.src.services.last_analyzed_content_store.get_last_analyzed_content",
            return_value=(HTML_SAMPLE, "https://example.org"),
        ), patch(
            "backend.src.agents.fixer.fixer.run_fixer",
            return_value=MagicMock(
                success=True,
                data={
                    "fixed_html": fixed_html,
                    "changes_summary": ["Adicionado texto descritivo ao link"],
                    "enriched_issues": [],
                },
            ),
        ) as mock_fixer, patch(
            "backend.src.agents.orchestrator.orchestrator.orchestrate",
        ) as mock_orchestrate:
            result_json = fix_and_zip_files({"pre_exec_msg": "Corrigindo..."})

        # Deve chamar o fixer com os issues do cache
        assert mock_fixer.called, "run_fixer deveria ser chamado"
        passed_issues = mock_fixer.call_args.args[1]
        assert len(passed_issues) == 1
        assert passed_issues[0].id == "issue-1"

        # Nao deve re-auditar o HTML (orchestrate nao e chamado para fallback)
        assert not mock_orchestrate.called, "orchestrate nao deve ser re-chamado no fallback"

        # O resultado deve conter o download e as mudancas
        result = chat_tools.json.loads(result_json)
        assert "download_url" in result
        assert result["total_files"] == 1
        assert any("descritivo" in s for s in result["changes_summary"])

        # E o mais importante: as paginas de preview devem estar salvas na sessao
        preview = get_last_fix(session_id)
        assert len(preview) == 1
        # O path fallback sem extensao HTML conhecida e normalizado para index.html
        assert preview[0]["title"] == "index.html"
        assert preview[0]["original_html"] == HTML_SAMPLE
        assert preview[0]["fixed_html"] == fixed_html

    def test_re_audit_when_files_are_provided(self, session_context_fixture):
        """Quando 'files' e fornecido explicitamente, re-audita o HTML."""
        session_id = session_context_fixture

        fixed_html = HTML_SAMPLE.replace("Learn more", "Learn more about accessibility")
        issues = [
            {
                "id": "issue-2",
                "criterion": "2.4.4",
                "severity": "medium",
                "description": "Link generico",
                "element": '<a href="#">Learn more</a>',
                "guideline": "WCAG 2.4.4",
                "suggestion": "Use texto descritivo no link",
            }
        ]

        with patch(
            "backend.src.services.chat_tools._render_html_to_screenshot",
            return_value="fake-screenshot",
        ), patch(
            "backend.src.services.chat_tools._verify_layout_visually",
            return_value={"layout_ok": True},
        ), patch(
            "backend.src.services.chat_tools._sanitize_accessible_links_and_labels",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.chat_tools._strip_injected_script_vectors",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.last_analysis_store.get_last_analysis",
            return_value=([], ""),
        ), patch(
            "backend.src.services.last_analyzed_content_store.get_last_analyzed_content",
            return_value=("", ""),
        ), patch(
            "backend.src.agents.orchestrator.orchestrator.orchestrate",
            return_value=MagicMock(success=True, data={"issues": issues}),
        ) as mock_orchestrate, patch(
            "backend.src.agents.fixer.fixer.run_fixer",
            return_value=MagicMock(
                success=True,
                data={
                    "fixed_html": fixed_html,
                    "changes_summary": ["Corrigido link"],
                    "enriched_issues": [],
                },
            ),
        ) as mock_fixer:
            result_json = fix_and_zip_files({
                "pre_exec_msg": "Corrigindo...",
                "files": [{"path": "index.html", "content": HTML_SAMPLE}],
            })

        assert mock_orchestrate.called, "orchestrate deve ser chamado para uploads de arquivo"
        assert mock_fixer.called

        result = chat_tools.json.loads(result_json)
        assert result["total_files"] == 1

        preview = get_last_fix(session_id)
        assert len(preview) == 1
        assert preview[0]["title"] == "index.html"

    def test_skips_visual_validation_for_small_fallback(self, session_context_fixture):
        """HTML pequeno e sem imagens, vindo do cache, pula o loop de validacao visual.

        Bug real corrigido: a validacao visual envolve renderizacao Playwright e uma
        chamada multimodal de LLM, que era executada ate para fallbacks de URL simples.
        Isso fazia o fix_and_zip_files exceder o tempo disponivel no chat e falhar
        antes de abrir o live preview.
        """
        session_id = session_context_fixture

        issues = [
            {
                "id": "issue-1",
                "criterion": "2.4.4",
                "severity": "medium",
                "description": "Link sem texto descritivo",
                "element": '<a href="#">Learn more</a>',
                "guideline": "WCAG 2.4.4",
                "suggestion": "Use texto descritivo no link",
            }
        ]

        fixed_html = HTML_SAMPLE.replace("Learn more", "Learn more about accessibility")

        with patch(
            "backend.src.services.chat_tools._render_html_to_screenshot",
        ) as mock_render, patch(
            "backend.src.services.chat_tools._verify_layout_visually",
        ) as mock_verify, patch(
            "backend.src.services.chat_tools._sanitize_accessible_links_and_labels",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.chat_tools._strip_injected_script_vectors",
            return_value=(fixed_html, []),
        ), patch(
            "backend.src.services.last_analysis_store.get_last_analysis",
            return_value=(issues, "https://example.org"),
        ), patch(
            "backend.src.services.last_analyzed_content_store.get_last_analyzed_content",
            return_value=(HTML_SAMPLE, "https://example.org"),
        ), patch(
            "backend.src.agents.fixer.fixer.run_fixer",
            return_value=MagicMock(
                success=True,
                data={
                    "fixed_html": fixed_html,
                    "changes_summary": ["Adicionado texto descritivo ao link"],
                    "enriched_issues": [],
                },
            ),
        ) as mock_fixer:
            result_json = fix_and_zip_files({"pre_exec_msg": "Corrigindo..."})

        assert mock_fixer.called
        assert mock_fixer.call_args.kwargs.get("model_tier") == "fast"
        assert not mock_render.called, "renderizacao visual nao deve ser chamada para fallback pequeno"
        assert not mock_verify.called, "verificacao visual nao deve ser chamada para fallback pequeno"

        result = chat_tools.json.loads(result_json)
        assert result["total_files"] == 1

        preview = get_last_fix(session_id)
        assert len(preview) == 1
        assert preview[0]["title"] == "index.html"
