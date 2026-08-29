"""Testes das rotas de Batch Inference no crawl (POST/GET /analyze/crawl/batch).

Batch Inference (ver batch_inference.py, VERIFICATION.md §21): submeter a
análise de várias páginas como UM job assíncrono no provider, com desconto de
custo, em vez de rodar em tempo real. Estes testes exercitam as rotas de
ponta a ponta, mockando só o crawl e as chamadas reais ao provider de batch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.src.services import batch_job_store
from backend.src.services.batch_inference import BatchStatus
from backend.src.services.crawler import CrawlPageResult
from backend.src.shared.models import AgentResult


def _fake_settings(provider="openai", model="gpt-5.6"):
    settings = MagicMock()
    settings.llm_provider = provider
    settings.llm_model = model
    settings.llm_api_key = "test-key"
    return settings


class TestCrawlBatchSubmit:
    def test_rejects_provider_without_batch_support(self, client):
        with patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()), patch(
            "backend.src.services.model_router.resolve_model_and_provider",
            return_value=("ollama-cloud", "deepseek-v4-pro"),
        ):
            resp = client.post("/analyze/crawl/batch", json={"url": "https://example.com"})

        assert resp.status_code == 400
        assert "Batch mode" in resp.json()["detail"]

    def test_submits_batch_and_returns_id(self, client):
        """`orchestrate` roda DE VERDADE aqui (não mockado): é o único jeito
        de exercitar a passada de coleta (batch_collect=True -> call_llm ->
        batch_collector) sem reescrever a seleção de agentes na mão. O que se
        mocka é o nível abaixo -- `AIAgent` -- pra nenhuma chamada real de
        rede acontecer (a classificação, que não entra em modo de coleta,
        passaria por aqui de verdade)."""
        pages = [CrawlPageResult(url="https://example.com/a", html="<html><body><img src=x></body></html>")]
        fake_agent = MagicMock()
        fake_agent.run_conversation.return_value = {"final_response": "[]", "failed": False}

        with (
            patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()),
            patch("backend.src.services.model_router.resolve_model_and_provider", return_value=("openai", "gpt-5.6")),
            patch("backend.src.routes.analyze.crawl_site", new=AsyncMock(return_value=pages)),
            patch("backend.src.services.llm_client.AIAgent", return_value=fake_agent),
            patch("backend.src.routes.analyze.submit_batch", return_value="batch-abc123") as mock_submit,
        ):
            resp = client.post("/analyze/crawl/batch", json={"url": "https://example.com", "max_pages": 5})

        assert resp.status_code == 200
        body = resp.json()
        assert body["batch_id"] == "batch-abc123"
        assert body["provider"] == "openai"
        assert body["pages_submitted"] == 1
        assert body["pages_failed_at_crawl"] == 0
        mock_submit.assert_called_once()

        # O job precisa estar persistido pro polling funcionar depois.
        job = batch_job_store.load("batch-abc123")
        assert job is not None
        assert job.provider == "openai"
        assert "https://example.com/a" in job.page_htmls
        batch_job_store.delete("batch-abc123")

    def test_no_pages_crawled_returns_400(self, client):
        with (
            patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()),
            patch("backend.src.services.model_router.resolve_model_and_provider", return_value=("openai", "gpt-5.6")),
            patch("backend.src.routes.analyze.crawl_site", new=AsyncMock(return_value=[])),
        ):
            resp = client.post("/analyze/crawl/batch", json={"url": "https://example.com"})

        assert resp.status_code == 400

    def test_failed_pages_are_counted_and_not_submitted(self, client):
        pages = [
            CrawlPageResult(url="https://example.com/a", html="<html><body><img src=x></body></html>"),
            CrawlPageResult(url="https://example.com/b", html="", error="timeout"),
        ]
        fake_agent = MagicMock()
        fake_agent.run_conversation.return_value = {"final_response": "[]", "failed": False}

        with (
            patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()),
            patch("backend.src.services.model_router.resolve_model_and_provider", return_value=("openai", "gpt-5.6")),
            patch("backend.src.routes.analyze.crawl_site", new=AsyncMock(return_value=pages)),
            patch("backend.src.services.llm_client.AIAgent", return_value=fake_agent),
            patch("backend.src.routes.analyze.submit_batch", return_value="batch-xyz") as mock_submit,
        ):
            resp = client.post("/analyze/crawl/batch", json={"url": "https://example.com", "max_pages": 5})

        assert resp.status_code == 200
        body = resp.json()
        assert body["pages_submitted"] == 1
        assert body["pages_failed_at_crawl"] == 1
        mock_submit.assert_called_once()

        job = batch_job_store.load("batch-xyz")
        assert job.failed_pages == [{"url": "https://example.com/b", "error": "timeout"}]
        batch_job_store.delete("batch-xyz")


class TestCrawlBatchStatus:
    def test_unknown_batch_id_returns_404(self, client):
        resp = client.get("/analyze/crawl/batch/does-not-exist")
        assert resp.status_code == 404

    def test_running_status_returns_no_result(self, client):
        batch_job_store.save(batch_job_store.BatchJob(
            batch_id="batch-running", provider="openai", model="gpt-5.6",
            root_url="https://example.com", page_htmls={"https://example.com/a": "<html></html>"},
        ))
        try:
            with (
                patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()),
                patch("backend.src.routes.analyze.poll_batch", return_value=BatchStatus.RUNNING),
            ):
                resp = client.get("/analyze/crawl/batch/batch-running")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "running"
            assert body["result"] is None
        finally:
            batch_job_store.delete("batch-running")

    def test_completed_status_builds_full_crawl_result(self, client):
        batch_job_store.save(batch_job_store.BatchJob(
            batch_id="batch-done", provider="openai", model="gpt-5.6",
            root_url="https://example.com",
            page_htmls={"https://example.com/a": "<html></html>"},
            failed_pages=[{"url": "https://example.com/b", "error": "timeout"}],
        ))
        issue = {
            "id": "p-1", "guideline": "WCAG 2.2", "criterion": "1.1.1 Non-text Content",
            "severity": "high", "element": "img", "description": "sem alt", "suggestion": "adicionar alt",
        }
        try:
            with (
                patch("backend.src.routes.analyze.get_settings", return_value=_fake_settings()),
                patch("backend.src.routes.analyze.poll_batch", return_value=BatchStatus.COMPLETED),
                patch("backend.src.routes.analyze.fetch_batch_results", return_value={"key1": "[]"}),
                patch(
                    "backend.src.routes.analyze.orchestrate",
                    new=AsyncMock(return_value=AgentResult(agent="orchestrator", success=True, data={"issues": [issue]})),
                ),
            ):
                resp = client.get("/analyze/crawl/batch/batch-done")

            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "completed"
            result = body["result"]
            assert result["total_pages"] == 2  # 1 pagina batched + 1 falha de crawl
            assert result["pages_ok"] == 1
            assert result["pages_failed"] == 1
            assert result["total_issues"] == 1
            assert result["all_issues"][0]["element"] == "[https://example.com/a] img"

            # Job consumido -- nao pode ser consultado de novo.
            assert batch_job_store.load("batch-done") is None
        finally:
            batch_job_store.delete("batch-done")
