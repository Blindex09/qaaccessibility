"""Testes da compactação real do histórico de conversa (resumo por LLM).

Feature real: `_compress_history_if_needed` mandava o texto do chat para o
`context_compressor`, que é um compressor de HTML -- em texto puro ele caía no
`content[:max_chars]`, ou seja, recortava a conversa no meio e descartava o resto
em silêncio. Agora o bloco antigo é resumido por um LLM e as mensagens recentes
ficam verbatim (padrão de compaction da Anthropic, 2026). Além disso, os caminhos
`_run_openai` e `_run_gemini` nunca chamavam compactação nenhuma.
"""

import pytest

from backend.src.services import history_summarizer
from run_agent import _KEEP_RECENT_MESSAGES, AIAgent


def _agent(max_context_chars: int = 500) -> AIAgent:
    return AIAgent(
        model="modelo-x",
        provider="openai",
        api_key="k",
        max_context_chars=max_context_chars,
        log_prefix="[teste]",
    )


def _history(turns: int, filler: int = 200) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": "prompt de sistema"}]
    for index in range(turns):
        role = "user" if index % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"turno {index} " + "x" * filler})
    return messages


@pytest.fixture
def fake_summary(monkeypatch):
    calls: list[list[dict]] = []

    def _summarize(messages, provider, model, api_key=None, base_url=None):
        calls.append(list(messages))
        return "RESUMO: o usuário pediu auditoria de acessibilidade da home."

    monkeypatch.setattr(history_summarizer, "summarize_messages", _summarize)
    return calls


class TestSummarizationTrigger:
    def test_history_below_the_budget_is_left_untouched(self, fake_summary):
        agent = _agent(max_context_chars=100_000)
        messages = _history(10)

        assert agent._compress_history_if_needed(messages) == messages
        assert fake_summary == []

    def test_above_the_budget_history_is_summarized_and_gets_materially_shorter(self, fake_summary):
        agent = _agent(max_context_chars=500)
        messages = _history(12)
        original_chars = sum(len(m["content"]) for m in messages)

        result = agent._compress_history_if_needed(messages)
        new_chars = sum(len(m["content"]) for m in result)

        assert fake_summary, "o resumo tinha de ter sido chamado"
        assert new_chars < original_chars / 2
        assert any("RESUMO:" in m["content"] for m in result)

    def test_recent_turns_survive_verbatim(self, fake_summary):
        agent = _agent(max_context_chars=500)
        messages = _history(12)
        expected_tail = messages[-_KEEP_RECENT_MESSAGES:]

        result = agent._compress_history_if_needed(messages)

        assert result[-_KEEP_RECENT_MESSAGES:] == expected_tail
        assert result[0] == messages[0]  # o system prompt também fica intacto

    def test_only_the_old_block_is_folded_not_the_recent_one(self, fake_summary):
        agent = _agent(max_context_chars=500)
        messages = _history(12)

        agent._compress_history_if_needed(messages)

        summarized = fake_summary[0]
        assert summarized == messages[1:-_KEEP_RECENT_MESSAGES]


class TestSummarizationFailureFallback:
    def test_summary_failure_falls_back_to_truncation_without_crashing(self, monkeypatch, caplog):
        def _broken(messages, provider, model, api_key=None, base_url=None):
            raise RuntimeError("provider 503")

        monkeypatch.setattr(history_summarizer, "summarize_messages", _broken)
        agent = _agent(max_context_chars=500)
        messages = _history(12, filler=3000)
        original_chars = sum(len(m["content"]) for m in messages)

        with caplog.at_level("ERROR"):
            result = agent._compress_history_if_needed(messages)

        assert "Resumo do historico falhou" in caplog.text
        assert "provider 503" in caplog.text
        # Degradou para o truncamento antigo: ainda encurta, e o turno não morre.
        assert sum(len(m["content"]) for m in result) < original_chars
        assert result[-_KEEP_RECENT_MESSAGES:] == messages[-_KEEP_RECENT_MESSAGES:]


class TestToolPairsAreNeverBroken:
    def test_tool_call_and_tool_result_are_not_folded_into_the_summary(self, fake_summary):
        """Resumir metade de um par tool_call/tool_result gera 400 no provider."""
        agent = _agent(max_context_chars=500)
        messages = [
            {"role": "system", "content": "sistema"},
            {"role": "user", "content": "oi " + "x" * 400},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "resultado " + "y" * 400},
            {"role": "assistant", "content": "pronto " + "z" * 400},
            {"role": "user", "content": "e agora? " + "w" * 400},
            {"role": "assistant", "content": "vamos lá"},
            {"role": "user", "content": "ok"},
        ]

        result = agent._compress_history_if_needed(messages)

        assert fake_summary[0] == [messages[1]]  # só o turno de texto puro foi dobrado
        roles = [m["role"] for m in result]
        assert roles.count("tool") == 1
        assert any(m.get("tool_calls") for m in result)


class TestSummarizerLeafCall:
    def test_summarizer_runs_as_a_cheap_toolless_leaf_agent(self, monkeypatch):
        captured: dict = {}

        class _FakeAgent:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run_conversation(self, user_message, **_k):
                captured["user_message"] = user_message
                return {"failed": False, "final_response": "resumo compacto"}

        monkeypatch.setattr("run_agent.AIAgent", _FakeAgent)

        summary = history_summarizer.summarize_messages(
            [{"role": "user", "content": "auditar https://exemplo.com"}],
            provider="openai",
            model="modelo-x",
            api_key="k",
        )

        assert summary == "resumo compacto"
        assert captured["enabled_toolsets"] == []
        assert captured["max_iterations"] == 1
        assert captured["request_overrides"]["reasoning_effort"] == "low"
        assert "auditar https://exemplo.com" in captured["user_message"]

    def test_provider_failure_is_raised_not_swallowed(self, monkeypatch):
        class _FailingAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message, **_k):
                return {"failed": True, "error": "429 rate limit"}

        monkeypatch.setattr("run_agent.AIAgent", _FailingAgent)

        with pytest.raises(RuntimeError, match="429 rate limit"):
            history_summarizer.summarize_messages(
                [{"role": "user", "content": "oi"}], provider="openai", model="m"
            )

    def test_empty_summary_is_raised_not_returned(self, monkeypatch):
        class _SilentAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message, **_k):
                return {"failed": False, "final_response": "   "}

        monkeypatch.setattr("run_agent.AIAgent", _SilentAgent)

        with pytest.raises(RuntimeError, match="resumo vazio"):
            history_summarizer.summarize_messages(
                [{"role": "user", "content": "oi"}], provider="openai", model="m"
            )


class TestCompactionIsWiredInEveryProviderPath:
    """Antes, só `_run_chat_completions` e `_run_anthropic` compactavam."""

    def test_openai_responses_path_compacts_the_prefill_history(self, monkeypatch):
        agent = _agent(max_context_chars=500)
        agent.prefill_messages = [
            {"role": m["role"], "content": m["content"]} for m in _history(12)[1:]
        ]
        seen: dict = {}

        def _spy(messages):
            seen["called_with"] = list(messages)
            return messages[:2]

        monkeypatch.setattr(agent, "_compress_history_if_needed", _spy)
        monkeypatch.setattr(
            "openai.OpenAI", lambda **kwargs: _StubOpenAI(seen)
        )

        agent._run_openai("última pergunta")

        assert seen["called_with"][-1]["content"] == "última pergunta"
        assert len(seen["sent_input"]) == 2

    def test_gemini_path_compacts_the_prefill_history(self, monkeypatch):
        agent = _agent(max_context_chars=500)
        agent.provider = "gemini"
        agent.prefill_messages = [
            {"role": m["role"], "content": m["content"]} for m in _history(12)[1:]
        ]
        seen: dict = {}

        def _spy(messages):
            seen["called_with"] = list(messages)
            return [{"role": "user", "content": "compactado"}]

        monkeypatch.setattr(agent, "_compress_history_if_needed", _spy)
        monkeypatch.setattr("google.genai.Client", lambda **kwargs: _StubGenAI(seen))

        agent._run_gemini("última pergunta")

        assert seen["called_with"][-1]["content"] == "última pergunta"
        assert seen["sent_input"] == "user: compactado"


class _StubResponse:
    status = "completed"
    output_text = "ok"
    output: list = []
    usage = None


class _StubOpenAI:
    def __init__(self, seen):
        self.responses = self
        self._seen = seen

    def create(self, **kwargs):
        self._seen["sent_input"] = kwargs["input"]
        return _StubResponse()


class _StubInteraction:
    status = "completed"
    steps = None
    outputs: list = []
    id = "int-1"
    usage_metadata = None
    usage = None


class _StubGenAI:
    def __init__(self, seen):
        self.interactions = self
        self._seen = seen

    def create(self, **kwargs):
        self._seen["sent_input"] = kwargs["input"]
        return _StubInteraction()
