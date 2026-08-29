"""Testes do histórico de análise por URL ("shift-right" sob demanda).

Achado real (2026-08-11, pedido do usuário): decisão de rodar sob demanda
(quando a mesma URL é reanalisada), não agendado -- sem infraestrutura de
scheduler nova. Regressão real (issues novos) e melhoria real (issues
resolvidos) são detectadas comparando o snapshot anterior contra o atual.
"""

import pytest

from backend.src.services import url_scan_history_store as store


@pytest.fixture(autouse=True)
def isolated_history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_HISTORY_DIR", str(tmp_path / "url_history"))
    yield


def _issue(criterion: str, element: str, severity: str = "high") -> dict[str, str]:
    return {"criterion": criterion, "element": element, "severity": severity, "description": f"{criterion} em {element}"}


class TestGetPreviousScan:
    def test_returns_none_when_url_never_scanned(self):
        assert store.get_previous_scan("https://example.com/nunca-visto") is None

    def test_returns_none_for_empty_url(self):
        assert store.get_previous_scan("") is None

    def test_returns_saved_snapshot(self):
        url = "https://example.com/page"
        issues = [_issue("1.1.1", "img.logo")]
        store.save_scan(url, issues)

        previous = store.get_previous_scan(url)
        assert previous is not None
        assert previous["url"] == url
        assert previous["issues"] == issues
        assert "scanned_at" in previous


class TestSaveScanOverwritesPrevious:
    def test_second_save_replaces_first(self):
        url = "https://example.com/page"
        store.save_scan(url, [_issue("1.1.1", "img.a")])
        store.save_scan(url, [_issue("2.4.4", "a.link")])

        previous = store.get_previous_scan(url)
        assert len(previous["issues"]) == 1
        assert previous["issues"][0]["criterion"] == "2.4.4"

    def test_different_urls_stay_independent(self):
        store.save_scan("https://a.com", [_issue("1.1.1", "img.a")])
        store.save_scan("https://b.com", [_issue("2.4.4", "a.link")])

        assert store.get_previous_scan("https://a.com")["issues"][0]["criterion"] == "1.1.1"
        assert store.get_previous_scan("https://b.com")["issues"][0]["criterion"] == "2.4.4"


class TestDiffScans:
    def test_no_changes_when_issues_identical(self):
        issues = [_issue("1.1.1", "img.a"), _issue("2.4.4", "a.link")]
        diff = store.diff_scans(issues, issues)
        assert diff["new_issues_count"] == 0
        assert diff["resolved_issues_count"] == 0

    def test_detects_real_new_regression(self):
        previous = [_issue("1.1.1", "img.a")]
        current = [_issue("1.1.1", "img.a"), _issue("2.4.4", "a.link")]
        diff = store.diff_scans(previous, current)
        assert diff["new_issues_count"] == 1
        assert diff["new_issues"][0]["criterion"] == "2.4.4"
        assert diff["resolved_issues_count"] == 0

    def test_detects_real_resolved_issue(self):
        previous = [_issue("1.1.1", "img.a"), _issue("2.4.4", "a.link")]
        current = [_issue("1.1.1", "img.a")]
        diff = store.diff_scans(previous, current)
        assert diff["resolved_issues_count"] == 1
        assert diff["resolved_issues"][0]["criterion"] == "2.4.4"
        assert diff["new_issues_count"] == 0

    def test_matching_ignores_severity_and_description_differences(self):
        """Achado real: severidade/descrição podem variar levemente na
        redação entre chamadas de LLM mesmo pro MESMO problema real -- o
        diff não deve tratar isso como issue novo, só criterion+element
        importam pro pareamento."""
        previous = [_issue("1.1.1", "img.a", severity="medium")]
        current = [_issue("1.1.1", "img.a", severity="critical")]
        diff = store.diff_scans(previous, current)
        assert diff["new_issues_count"] == 0
        assert diff["resolved_issues_count"] == 0

    def test_matching_is_case_insensitive(self):
        previous = [_issue("1.1.1", "IMG.logo")]
        current = [_issue("1.1.1", "img.logo")]
        diff = store.diff_scans(previous, current)
        assert diff["new_issues_count"] == 0
        assert diff["resolved_issues_count"] == 0
