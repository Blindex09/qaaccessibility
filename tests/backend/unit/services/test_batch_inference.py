"""Testes do serviço de Batch Inference (2026): submit/poll/fetch pros 3
providers com Batch API documentada (OpenAI, Anthropic, Gemini). Mocks no
nível do client do SDK, mesmo padrão dos outros testes de provider."""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.batch_inference import (
    BatchNotSupportedError,
    BatchRequest,
    BatchStatus,
    fetch_batch_results,
    poll_batch,
    submit_batch,
)

_REQ = [
    BatchRequest(custom_id="page-1", system_prompt="s1", user_prompt="u1", model="gpt-5.6"),
    BatchRequest(custom_id="page-2", system_prompt="s2", user_prompt="u2", model="gpt-5.6"),
]


class TestUnsupportedProviders:
    @pytest.mark.parametrize("provider", ["xai", "ollama", "ollama-cloud", "agentic"])
    def test_submit_raises_for_unsupported_provider(self, provider):
        with pytest.raises(BatchNotSupportedError):
            submit_batch(_REQ, provider, "test-key")

    def test_submit_raises_for_empty_requests(self):
        with pytest.raises(ValueError):
            submit_batch([], "openai", "test-key")


class TestOpenAIBatch:
    def test_submit_uploads_jsonl_and_creates_batch(self):
        mock_client = MagicMock()
        mock_client.files.create.return_value = MagicMock(id="file-123")
        mock_client.batches.create.return_value = MagicMock(id="batch-abc")

        with patch("openai.OpenAI", return_value=mock_client):
            batch_id = submit_batch(_REQ, "openai", "test-key")

        assert batch_id == "batch-abc"
        upload_kwargs = mock_client.files.create.call_args.kwargs
        assert upload_kwargs["purpose"] == "batch"
        filename, jsonl_bytes = upload_kwargs["file"]
        lines = [json.loads(line) for line in jsonl_bytes.decode().strip().splitlines()]
        assert len(lines) == 2
        assert lines[0]["custom_id"] == "page-1"
        assert lines[0]["url"] == "/v1/responses"
        assert lines[0]["body"]["instructions"] == "s1"
        assert lines[0]["body"]["input"] == [{"role": "user", "content": "u1"}]

        create_kwargs = mock_client.batches.create.call_args.kwargs
        assert create_kwargs["input_file_id"] == "file-123"
        assert create_kwargs["completion_window"] == "24h"

    def test_poll_maps_status_to_enum(self):
        mock_client = MagicMock()
        mock_client.batches.retrieve.return_value = MagicMock(status="completed")
        with patch("openai.OpenAI", return_value=mock_client):
            assert poll_batch("batch-abc", "openai", "test-key") == BatchStatus.COMPLETED

        mock_client.batches.retrieve.return_value = MagicMock(status="in_progress")
        with patch("openai.OpenAI", return_value=mock_client):
            assert poll_batch("batch-abc", "openai", "test-key") == BatchStatus.RUNNING

    def test_fetch_results_parses_jsonl_output_file(self):
        mock_client = MagicMock()
        mock_client.batches.retrieve.return_value = MagicMock(output_file_id="out-file")
        output_jsonl = "\n".join([
            json.dumps({
                "custom_id": "page-1",
                "response": {"body": {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "issues: []"}
                ]}]}},
            }),
            json.dumps({
                "custom_id": "page-2",
                "response": {"body": {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "issues: [1]"}
                ]}]}},
            }),
        ])
        mock_client.files.content.return_value = MagicMock(text=output_jsonl)

        with patch("openai.OpenAI", return_value=mock_client):
            results = fetch_batch_results("batch-abc", "openai", "test-key")

        assert results == {"page-1": "issues: []", "page-2": "issues: [1]"}

    def test_fetch_results_empty_when_no_output_file_yet(self):
        mock_client = MagicMock()
        mock_client.batches.retrieve.return_value = MagicMock(output_file_id=None)
        with patch("openai.OpenAI", return_value=mock_client):
            assert fetch_batch_results("batch-abc", "openai", "test-key") == {}


class TestAnthropicBatch:
    def test_submit_sends_requests_inline_no_file_upload(self):
        mock_client = MagicMock()
        mock_client.messages.batches.create.return_value = MagicMock(id="msgbatch-123")

        with patch("anthropic.Anthropic", return_value=mock_client):
            batch_id = submit_batch(_REQ, "anthropic", "test-key")

        assert batch_id == "msgbatch-123"
        sent = mock_client.messages.batches.create.call_args.kwargs["requests"]
        assert sent[0]["custom_id"] == "page-1"
        assert sent[0]["params"]["system"] == "s1"
        assert sent[0]["params"]["messages"] == [{"role": "user", "content": "u1"}]

    def test_poll_maps_processing_status_to_enum(self):
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = MagicMock(processing_status="ended")
        with patch("anthropic.Anthropic", return_value=mock_client):
            assert poll_batch("msgbatch-123", "anthropic", "test-key") == BatchStatus.COMPLETED

        mock_client.messages.batches.retrieve.return_value = MagicMock(processing_status="in_progress")
        with patch("anthropic.Anthropic", return_value=mock_client):
            assert poll_batch("msgbatch-123", "anthropic", "test-key") == BatchStatus.RUNNING

    def test_fetch_results_extracts_text_blocks_per_custom_id(self):
        text_block = MagicMock(type="text")
        text_block.text = "ok anthropic"
        succeeded = MagicMock(type="succeeded")
        succeeded.message = MagicMock(content=[text_block])
        entry = MagicMock(custom_id="page-1", result=succeeded)

        mock_client = MagicMock()
        mock_client.messages.batches.results.return_value = [entry]

        with patch("anthropic.Anthropic", return_value=mock_client):
            results = fetch_batch_results("msgbatch-123", "anthropic", "test-key")

        assert results == {"page-1": "ok anthropic"}

    def test_fetch_results_errored_entry_returns_empty_string(self):
        errored = MagicMock(type="errored")
        entry = MagicMock(custom_id="page-2", result=errored)
        mock_client = MagicMock()
        mock_client.messages.batches.results.return_value = [entry]

        with patch("anthropic.Anthropic", return_value=mock_client):
            results = fetch_batch_results("msgbatch-123", "anthropic", "test-key")

        assert results == {"page-2": ""}


class TestGeminiBatch:
    def test_submit_builds_inlined_requests_with_custom_id_metadata(self):
        mock_client = MagicMock()
        job = MagicMock()
        job.name = "batches/xyz"  # "name" e kwarg reservado do MagicMock(); precisa ser setado depois
        mock_client.batches.create.return_value = job

        with patch("google.genai.Client", return_value=mock_client):
            batch_id = submit_batch(_REQ, "gemini", "test-key")

        assert batch_id == "batches/xyz"
        create_kwargs = mock_client.batches.create.call_args.kwargs
        assert create_kwargs["model"] == "gpt-5.6"
        src = create_kwargs["src"]
        assert len(src) == 2
        assert src[0].metadata == {"custom_id": "page-1"}
        assert src[0].contents == "u1"
        assert src[0].config.system_instruction == "s1"

    def test_poll_maps_job_state_to_enum(self):
        mock_client = MagicMock()
        mock_client.batches.get.return_value = MagicMock(state="JOB_STATE_SUCCEEDED")
        with patch("google.genai.Client", return_value=mock_client):
            assert poll_batch("batches/xyz", "gemini", "test-key") == BatchStatus.COMPLETED

        mock_client.batches.get.return_value = MagicMock(state="JOB_STATE_RUNNING")
        with patch("google.genai.Client", return_value=mock_client):
            assert poll_batch("batches/xyz", "gemini", "test-key") == BatchStatus.RUNNING

        mock_client.batches.get.return_value = MagicMock(state="JOB_STATE_FAILED")
        with patch("google.genai.Client", return_value=mock_client):
            assert poll_batch("batches/xyz", "gemini", "test-key") == BatchStatus.FAILED

    def test_fetch_results_reads_inlined_responses_by_metadata_custom_id(self):
        item1 = MagicMock(metadata={"custom_id": "page-1"}, response=MagicMock(text="ok gemini 1"))
        item2 = MagicMock(metadata={"custom_id": "page-2"}, response=MagicMock(text="ok gemini 2"))
        job = MagicMock(dest=MagicMock(inlined_responses=[item1, item2]))
        mock_client = MagicMock()
        mock_client.batches.get.return_value = job

        with patch("google.genai.Client", return_value=mock_client):
            results = fetch_batch_results("batches/xyz", "gemini", "test-key")

        assert results == {"page-1": "ok gemini 1", "page-2": "ok gemini 2"}
