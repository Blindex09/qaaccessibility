"""Testes do remote_runners — execução remota de Selenium, Postman e Cypress.

Validam contratos e tratamento de erro sem acionar rede real
(browser/requests/subprocess mockados).

Achado real corrigido (auditoria 2026-08-10): selenium/cypress não rodavam
Selenium/Cypress nenhum -- só reexecutavam o orquestrador de IA do projeto e
devolviam o resultado relabeled. Agora os dois rodam axe-core real via
`browser.run_axe_core_audit` (mockado aqui, real de verdade só na suíte
real_llm/E2E) -- estes testes fixam o CONTRATO (shape do resultado, tratamento
de erro), não o comportamento do axe-core em si.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services import remote_runners


def _fake_axe_results(violations=None, incomplete=None):
    return {
        "violations": violations or [],
        "incomplete": incomplete or [],
        "testEngine": {"name": "axe-core", "version": "4.13.0"},
    }


_SAMPLE_VIOLATIONS = [
    {
        "id": "image-alt",
        "impact": "critical",
        "description": "Images must have alternate text",
        "help": "Images must have alternate text",
        "helpUrl": "https://dequeuniversity.com/rules/axe/4.13/image-alt",
        "tags": ["wcag2a", "wcag111"],
        "nodes": [{"target": ["img.hero"], "html": "<img class=hero>"}],
    },
    {
        "id": "color-contrast",
        "impact": "serious",
        "description": "Elements must meet minimum color contrast ratio",
        "help": "Elements must meet minimum color contrast ratio",
        "helpUrl": "https://dequeuniversity.com/rules/axe/4.13/color-contrast",
        "tags": ["wcag2aa", "wcag143"],
        "nodes": [{"target": ["p.muted"], "html": "<p class=muted>x</p>"}],
    },
]


# --------------------------------------------------------------------------- #
# run_remote_selenium (axe-core real)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_selenium_returns_real_axe_violations_on_success():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results(_SAMPLE_VIOLATIONS)),
    ):
        result = await remote_runners.run_remote_selenium("https://example.com")

    assert result["status"] == "ok"
    assert result["runner"] == "selenium_remote"
    assert result["engine"] == "axe-core"
    assert result["total_violations"] == 2
    assert result["violations_by_impact"] == {"critical": 1, "serious": 1}
    assert result["passed"] is False
    assert result["critical_issues"][0]["id"] == "image-alt"


@pytest.mark.asyncio
async def test_run_remote_selenium_passes_when_no_violations():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ):
        result = await remote_runners.run_remote_selenium("https://example.com")

    assert result["total_violations"] == 0
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_run_remote_selenium_returns_error_on_exception():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result = await remote_runners.run_remote_selenium("https://example.com")

    assert result["status"] == "error"
    assert "network down" in result["error"]


# --------------------------------------------------------------------------- #
# run_remote_selenium -- decisão explícita local vs. nuvem (sem fallback silencioso)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_selenium_local_runs_real_webdriver_when_available():
    with patch(
        "backend.src.services.remote_runners._try_run_local_selenium",
        new=AsyncMock(return_value=_fake_axe_results(_SAMPLE_VIOLATIONS)),
    ):
        result = await remote_runners.run_remote_selenium("https://example.com", location="local")

    assert result["status"] == "ok"
    assert result["runner"] == "selenium_local"
    assert result["total_violations"] == 2


@pytest.mark.asyncio
async def test_run_remote_selenium_local_never_falls_back_silently_to_cloud():
    with patch(
        "backend.src.services.remote_runners._try_run_local_selenium",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ) as mock_cloud:
        result = await remote_runners.run_remote_selenium("https://example.com", location="local")

    assert result["status"] == "error"
    assert "local" in result["error"].lower()
    mock_cloud.assert_not_called()  # nunca deve ter chamado o motor via nuvem sozinho


@pytest.mark.asyncio
async def test_run_remote_selenium_local_probe_returns_none_without_chromedriver(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = await remote_runners._try_run_local_selenium("https://example.com")
    assert result is None


def _fake_newman_report(assertions_total=3, assertions_failed=0, http_code=200):
    assertions = []
    names = ["Status code e 200 OK", "Resposta e um JSON valido", "Contrato contem atributos de acessibilidade"]
    for i in range(assertions_total):
        entry = {"assertion": names[i % len(names)]}
        if i < assertions_failed:
            entry["error"] = {"message": "falhou"}
        assertions.append(entry)
    return {
        "run": {
            "stats": {"assertions": {"total": assertions_total, "failed": assertions_failed}},
            "executions": [{"response": {"code": http_code}, "assertions": assertions}],
        }
    }


# --------------------------------------------------------------------------- #
# run_remote_postman_contract -- caminho real (Newman)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_postman_contract_runs_real_newman_when_available():
    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners._run_newman",
        new=AsyncMock(return_value=_fake_newman_report(assertions_total=3, assertions_failed=0)),
    ):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["status"] == "ok"
    assert result["runner"] == "postman_remote"
    assert result["engine"] == "newman"
    assert result["newman_ran"] is True
    assert result["score"] == 100
    assert result["passed"] is True
    assert len(result["tests"]) == 3


@pytest.mark.asyncio
async def test_run_remote_postman_contract_newman_partial_failure():
    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners._run_newman",
        new=AsyncMock(return_value=_fake_newman_report(assertions_total=3, assertions_failed=1)),
    ):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["score"] == 66
    assert result["passed"] is False
    assert sum(1 for t in result["tests"] if not t["passed"]) == 1


@pytest.mark.asyncio
async def test_run_remote_postman_contract_fetches_real_collection_when_configured(monkeypatch):
    monkeypatch.setenv("POSTMAN_API_KEY", "fake-key")
    monkeypatch.setenv("POSTMAN_COLLECTION_ID", "coll-123")
    fake_me = type("FakeMe", (), {"status_code": 200, "json": staticmethod(lambda: {"user": {"username": "qa"}})})
    fake_collection_res = type(
        "FakeCollectionRes",
        (),
        {"status_code": 200, "json": staticmethod(lambda: {"collection": {"info": {"name": "Real"}}})},
    )
    captured_collection = {}

    async def _fake_run_newman(collection, **kwargs):
        captured_collection.update(collection)
        return _fake_newman_report()

    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners.requests.get",
        side_effect=[fake_me, fake_collection_res],
    ), patch("backend.src.services.remote_runners._run_newman", side_effect=_fake_run_newman):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["postman_cloud_synced"] is True
    assert captured_collection["info"]["name"] == "Real"


# --------------------------------------------------------------------------- #
# run_remote_postman_contract -- fallback honesto (newman indisponível)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_postman_contract_falls_back_honestly_when_newman_unavailable():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 200,
            "json": staticmethod(lambda: {"title": "ok", "score": 90}),
        },
    )
    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners._run_newman", new=AsyncMock(return_value=None)
    ), patch("backend.src.services.remote_runners.requests.get", return_value=fake_response):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["status"] == "ok"
    assert result["runner"] == "postman_remote"
    assert result["engine"] == "lightweight_contract_check"
    assert result["newman_ran"] is False
    assert result["http_status"] == 200
    assert result["score"] == 100
    assert result["passed"] is True
    assert all(t["passed"] for t in result["tests"])


@pytest.mark.asyncio
async def test_run_remote_postman_contract_calls_ssrf_guard():
    with patch(
        "backend.src.routes.analyze._validate_url_ssrf"
    ) as mock_ssrf, patch(
        "backend.src.services.remote_runners._run_newman",
        new=AsyncMock(return_value=_fake_newman_report()),
    ):
        await remote_runners.run_remote_postman_contract("https://api.example.com")

    mock_ssrf.assert_called_once_with("https://api.example.com")


@pytest.mark.asyncio
async def test_run_remote_postman_contract_syncs_postman_cloud_when_key_set(monkeypatch):
    monkeypatch.setenv("POSTMAN_API_KEY", "fake-key")
    fake_me = type("FakeMe", (), {"status_code": 200, "json": staticmethod(lambda: {"user": {"username": "qa"}})})
    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners.requests.get",
        return_value=fake_me,
    ), patch(
        "backend.src.services.remote_runners._run_newman",
        new=AsyncMock(return_value=_fake_newman_report()),
    ):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["postman_cloud_synced"] is True


@pytest.mark.asyncio
async def test_run_remote_postman_contract_returns_error_on_exception():
    # O guard SSRF passa (mockado); newman indisponível cai no fallback leve,
    # cuja exceção do requests.get é capturada pelo try/except, devolvendo status=error.
    with patch("backend.src.routes.analyze._validate_url_ssrf"), patch(
        "backend.src.services.remote_runners._run_newman", new=AsyncMock(return_value=None)
    ), patch(
        "backend.src.services.remote_runners.requests.get",
        side_effect=ConnectionError("network down"),
    ):
        result = await remote_runners.run_remote_postman_contract("https://api.example.com")

    assert result["status"] == "error"
    assert "network down" in result["error"]


# --------------------------------------------------------------------------- #
# run_remote_cypress_simulation (axe-core real)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_returns_real_axe_violations_on_success():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results(_SAMPLE_VIOLATIONS)),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com")

    assert result["status"] == "ok"
    assert result["runner"] == "cypress_remote"
    assert result["engine"] == "axe-core"
    assert result["total_violations"] == 2
    assert result["passed"] is False
    assert result["scope"] == "global"


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_passes_when_no_violations():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com")

    assert result["total_violations"] == 0
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_returns_error_on_exception():
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com")

    assert result["status"] == "error"
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_uses_scope_selector_to_filter_violations():
    violations = _SAMPLE_VIOLATIONS  # image-alt em img.hero, color-contrast em p.muted
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results(violations)),
    ):
        result = await remote_runners.run_remote_cypress_simulation(
            "https://example.com", scope_selector="img.hero"
        )

    assert result["scope"] == "img.hero"
    assert result["total_violations"] == 1
    assert result["critical_issues"][0]["id"] == "image-alt"


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_reports_cloud_sync_status(monkeypatch):
    monkeypatch.setenv("CYPRESS_PROJECT_ID", "proj-123")
    monkeypatch.setenv("CYPRESS_RECORD_KEY", "rec-key")
    with patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com")

    assert result["cypress_cloud_synced"] is True
    assert result["cypress_project_id"] == "proj-123"


# --------------------------------------------------------------------------- #
# run_remote_cypress_simulation -- decisão explícita local vs. nuvem (sem fallback silencioso)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_local_runs_real_binary_when_available():
    """Achado real (2026-08-11, validação E2E com Cypress local recém
    instalado): _try_run_local_cypress passou a devolver o formato axe-core
    real (violations/incomplete/testEngine, via o callback de cy.checkA11y
    escrito em arquivo) em vez do relatório mocha (que não expunha as
    violações de verdade quando skipFailures=true) -- reaproveita
    _summarize_axe_results, o mesmo caminho já usado pela nuvem."""
    with patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(return_value=_fake_axe_results(_SAMPLE_VIOLATIONS)),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com", location="local")

    assert result["status"] == "ok"
    assert result["runner"] == "cypress_local"
    assert result["engine"] == "axe-core"
    assert result["total_violations"] == len(_SAMPLE_VIOLATIONS)
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_local_never_falls_back_silently_to_cloud():
    with patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ) as mock_cloud:
        result = await remote_runners.run_remote_cypress_simulation("https://example.com", location="local")

    assert result["status"] == "error"
    assert "local" in result["error"].lower()
    mock_cloud.assert_not_called()


@pytest.mark.asyncio
async def test_try_run_local_cypress_returns_none_without_project_dir(monkeypatch):
    monkeypatch.delenv("CYPRESS_LOCAL_PROJECT_DIR", raising=False)
    with patch(
        "backend.src.services.remote_runners._search_for_local_cypress_installations",
        return_value=[],
    ):
        result = await remote_runners._try_run_local_cypress("https://example.com")
    assert result is None


# --------------------------------------------------------------------------- #
# Busca real por Cypress instalado localmente (sem CYPRESS_LOCAL_PROJECT_DIR)
# --------------------------------------------------------------------------- #
def test_search_for_local_cypress_installations_finds_a_real_marker(tmp_path, monkeypatch):
    """Achado real (pedido do usuário, 2026-08-10): usuários sem nuvem querem
    que a IA ache o Cypress já instalado num projeto seu, sem precisar
    informar o caminho manualmente. Busca por node_modules/cypress/package.json
    de verdade, não só pelo nome da pasta."""
    monkeypatch.setattr(remote_runners.Path, "home", classmethod(lambda cls: tmp_path))
    project = tmp_path / "projects" / "meu-projeto-com-cypress"
    marker_dir = project / "node_modules" / "cypress"
    marker_dir.mkdir(parents=True)
    (marker_dir / "package.json").write_text("{}", encoding="utf-8")

    found = remote_runners._search_for_local_cypress_installations()
    assert found == [str(project)]


def test_search_for_local_cypress_installations_returns_empty_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_runners.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "projects" / "projeto-sem-cypress").mkdir(parents=True)

    found = remote_runners._search_for_local_cypress_installations()
    assert found == []


def test_search_for_local_cypress_installations_finds_all_not_just_first(tmp_path, monkeypatch):
    """Achado real (pedido do usuário, 2026-08-11): um usuário pode ter mais
    de um projeto com Cypress instalado -- a busca não deve parar na primeira
    ocorrência, senão a IA nunca saberia que há outras opções pra oferecer."""
    monkeypatch.setattr(remote_runners.Path, "home", classmethod(lambda cls: tmp_path))
    project_a = tmp_path / "projects" / "projeto-a"
    project_b = tmp_path / "dev" / "projeto-b"
    for project in (project_a, project_b):
        marker_dir = project / "node_modules" / "cypress"
        marker_dir.mkdir(parents=True)
        (marker_dir / "package.json").write_text("{}", encoding="utf-8")

    found = remote_runners._search_for_local_cypress_installations()
    assert set(found) == {str(project_a), str(project_b)}


@pytest.mark.asyncio
async def test_try_run_local_cypress_uses_search_result_and_persists_it_when_exactly_one(monkeypatch):
    monkeypatch.delenv("CYPRESS_LOCAL_PROJECT_DIR", raising=False)
    with patch(
        "backend.src.services.remote_runners._search_for_local_cypress_installations",
        return_value=["/found/via/search-acessibilidade"],
    ), patch("backend.src.security.secret_store.save_secret") as mock_save, patch(
        "shutil.which", return_value=None,  # sem npx -- só validamos que o caminho foi resolvido/persistido
    ):
        await remote_runners._try_run_local_cypress("https://example.com")

    assert os.environ.get("CYPRESS_LOCAL_PROJECT_DIR") == "/found/via/search-acessibilidade"
    mock_save.assert_called_once_with("CYPRESS_LOCAL_PROJECT_DIR", "/found/via/search-acessibilidade")
    monkeypatch.delenv("CYPRESS_LOCAL_PROJECT_DIR", raising=False)


@pytest.mark.asyncio
async def test_try_run_local_cypress_raises_when_multiple_found_without_override(monkeypatch):
    """Achado real (pedido do usuário, 2026-08-11): com mais de uma instalação
    encontrada e nenhuma escolha explícita do usuário, a função NUNCA decide
    sozinha qual usar -- levanta uma exceção específica que o chamador (chat)
    transforma numa pergunta real pro usuário via `clarify`."""
    monkeypatch.delenv("CYPRESS_LOCAL_PROJECT_DIR", raising=False)
    candidates = ["/found/project-a", "/found/project-b"]
    with patch(
        "backend.src.services.remote_runners._search_for_local_cypress_installations",
        return_value=candidates,
    ), pytest.raises(remote_runners.CypressMultipleInstallationsFoundError) as exc_info:
        await remote_runners._try_run_local_cypress("https://example.com")

    assert exc_info.value.candidates == candidates


@pytest.mark.asyncio
async def test_try_run_local_cypress_uses_override_even_with_multiple_found(monkeypatch, tmp_path):
    """Quando o usuário já escolheu (project_dir_override), a busca nem
    precisa rodar de novo -- usa a escolha diretamente."""
    monkeypatch.delenv("CYPRESS_LOCAL_PROJECT_DIR", raising=False)
    chosen = tmp_path / "chosen-project-acessibilidade"
    chosen.mkdir()
    with patch(
        "backend.src.services.remote_runners._search_for_local_cypress_installations",
    ) as mock_search, patch("shutil.which", return_value=None):
        await remote_runners._try_run_local_cypress(
            "https://example.com", project_dir_override=str(chosen),
        )

    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_returns_needs_selection_with_real_candidates():
    """Achado real (pedido do usuário, 2026-08-11): o resultado propagado pro
    chat deve conter os caminhos REAIS encontrados (não um erro genérico),
    pra IA conseguir apresentar as opções de verdade ao usuário."""
    candidates = ["/found/project-a", "/found/project-b"]
    with patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(side_effect=remote_runners.CypressMultipleInstallationsFoundError(candidates)),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com", location="local")

    assert result["status"] == "needs_selection"
    assert result["candidates"] == candidates
    assert "/found/project-a" in result["error"]
    assert "/found/project-b" in result["error"]


# --------------------------------------------------------------------------- #
# location="install_local" -- instalação real (mockada aqui), só com consentimento explícito
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_install_local_installs_then_runs():
    with patch(
        "backend.src.services.remote_runners._install_local_cypress",
        new=AsyncMock(return_value="/fake/project/dir"),
    ) as mock_install, patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ):
        result = await remote_runners.run_remote_cypress_simulation("https://example.com", location="install_local")

    mock_install.assert_called_once()
    assert result["status"] == "ok"
    assert result["runner"] == "cypress_local"


@pytest.mark.asyncio
async def test_run_remote_cypress_simulation_install_local_failure_returns_clear_error():
    with patch(
        "backend.src.services.remote_runners._install_local_cypress",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.src.services.browser.run_axe_core_audit",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ) as mock_cloud:
        result = await remote_runners.run_remote_cypress_simulation("https://example.com", location="install_local")

    assert result["status"] == "error"
    mock_cloud.assert_not_called()  # instalação falhou -- não some sozinho pra nuvem


@pytest.mark.asyncio
async def test_run_remote_selenium_install_local_lets_selenium_manager_resolve_driver():
    with patch(
        "backend.src.services.remote_runners._try_run_local_selenium",
        new=AsyncMock(return_value=_fake_axe_results([])),
    ) as mock_local:
        result = await remote_runners.run_remote_selenium("https://example.com", location="install_local")

    assert result["status"] == "ok"
    assert result["runner"] == "selenium_local"
    _, kwargs = mock_local.call_args
    assert kwargs.get("allow_driver_auto_install") is True


@pytest.mark.asyncio
async def test_try_run_local_selenium_without_chromedriver_and_without_install_flag_returns_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = await remote_runners._try_run_local_selenium("https://example.com", allow_driver_auto_install=False)
    assert result is None
