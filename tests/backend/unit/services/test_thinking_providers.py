from unittest.mock import MagicMock, patch

from run_agent import AIAgent


def test_openai_chat_completions_reasoning_content_streaming_callback():
    """Valida a captura de delta.reasoning_content na Chat Completions API (xAI, Ollama Cloud, DeepSeek, Kimi)."""
    thinking_chunks = []
    reasoning_chunks = []
    text_chunks = []

    def on_thinking(t: str) -> None:
        thinking_chunks.append(t)

    def on_reasoning(r: str) -> None:
        reasoning_chunks.append(r)

    def on_text(d: str) -> None:
        text_chunks.append(d)

    chunk1 = MagicMock()
    chunk1.usage = None
    delta1 = MagicMock()
    delta1.reasoning_content = "Pensando sobre a estrutura..."
    delta1.reasoning = None
    delta1.thinking = None
    delta1.content = None
    delta1.tool_calls = None
    chunk1.choices = [MagicMock(delta=delta1)]

    chunk2 = MagicMock()
    chunk2.usage = None
    delta2 = MagicMock()
    delta2.reasoning_content = None
    delta2.reasoning = None
    delta2.thinking = None
    delta2.content = " Resposta final de acessibilidade."
    delta2.tool_calls = None
    chunk2.choices = [MagicMock(delta=delta2)]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = [chunk1, chunk2]

    agent = AIAgent(
        model="deepseek-r1",
        provider="ollama",
        api_key="test-key",
        stream_delta_callback=on_text,
        thinking_callback=on_thinking,
        reasoning_callback=on_reasoning,
    )

    with patch("openai.OpenAI", return_value=mock_client):
        res = agent.run_conversation("Teste de acessibilidade")

    assert res["failed"] is False
    assert thinking_chunks == ["Pensando sobre a estrutura..."]
    assert reasoning_chunks == ["Pensando sobre a estrutura..."]
    assert text_chunks == [" Resposta final de acessibilidade."]


def test_openai_responses_reasoning_streaming_callback():
    """Valida a captura de eventos de raciocínio no streaming da Responses API (OpenAI gpt-5.2 / o-series)."""
    thinking_chunks = []
    reasoning_chunks = []
    text_chunks = []

    def on_thinking(t: str) -> None:
        thinking_chunks.append(t)

    def on_reasoning(r: str) -> None:
        reasoning_chunks.append(r)

    def on_text(d: str) -> None:
        text_chunks.append(d)

    event_reasoning = MagicMock()
    event_reasoning.type = "response.reasoning_text.delta"
    event_reasoning.delta = "Análise de raciocínio o3..."

    event_text = MagicMock()
    event_text.type = "response.output_text.delta"
    event_text.delta = " Resposta pública final."

    final_resp = MagicMock()
    final_resp.status = "completed"
    final_resp.output_text = " Resposta pública final."
    final_resp.output = []
    final_resp.usage = None

    class FakeStream:
        def __iter__(self):
            return iter([event_reasoning, event_text])

        def get_final_response(self):
            return final_resp

    class FakeStreamContext:
        def __enter__(self):
            return FakeStream()

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = MagicMock()
    mock_client.responses.stream.return_value = FakeStreamContext()

    agent = AIAgent(
        model="gpt-5.2",
        provider="openai",
        api_key="test-key",
        stream_delta_callback=on_text,
        thinking_callback=on_thinking,
        reasoning_callback=on_reasoning,
    )

    with patch("openai.OpenAI", return_value=mock_client):
        res = agent.run_conversation("Teste de acessibilidade")

    assert res["failed"] is False
    assert thinking_chunks == ["Análise de raciocínio o3..."]
    assert reasoning_chunks == ["Análise de raciocínio o3..."]
    assert text_chunks == [" Resposta pública final."]


def test_anthropic_thinking_delta_streaming_callback():
    """Valida a captura de eventos thinking_delta na API Anthropic."""
    thinking_chunks = []
    reasoning_chunks = []
    text_chunks = []

    def on_thinking(t: str) -> None:
        thinking_chunks.append(t)

    def on_reasoning(r: str) -> None:
        reasoning_chunks.append(r)

    def on_text(d: str) -> None:
        text_chunks.append(d)

    event_start = MagicMock()
    event_start.type = "content_block_start"
    block = MagicMock()
    block.type = "thinking"
    block.thinking = "Iniciando raciocínio..."
    event_start.content_block = block

    event_delta = MagicMock()
    event_delta.type = "content_block_delta"
    delta_think = MagicMock()
    delta_think.type = "thinking_delta"
    delta_think.thinking = " Detalhando critérios WCAG."
    event_delta.delta = delta_think

    event_text = MagicMock()
    event_text.type = "content_block_delta"
    delta_text = MagicMock()
    delta_text.type = "text_delta"
    delta_text.text = "Conclusão técnica."
    event_text.delta = delta_text

    mock_client = MagicMock()
    mock_client.messages.create.return_value = [event_start, event_delta, event_text]

    agent = AIAgent(
        model="claude-opus-4-6",
        provider="anthropic",
        api_key="test-key",
        stream_delta_callback=on_text,
        thinking_callback=on_thinking,
        reasoning_callback=on_reasoning,
    )

    with patch("anthropic.Anthropic", return_value=mock_client):
        res = agent.run_conversation("Teste Anthropic")

    assert res["failed"] is False
    assert thinking_chunks == ["Iniciando raciocínio...", " Detalhando critérios WCAG."]
    assert reasoning_chunks == ["Iniciando raciocínio...", " Detalhando critérios WCAG."]
    assert text_chunks == ["Conclusão técnica."]


def test_gemini_thought_streaming_callback():
    """Valida a captura de deltas do tipo thought/thinking no provedor Gemini."""
    thinking_chunks = []
    reasoning_chunks = []
    text_chunks = []

    def on_thinking(t: str) -> None:
        thinking_chunks.append(t)

    def on_reasoning(r: str) -> None:
        reasoning_chunks.append(r)

    def on_text(d: str) -> None:
        text_chunks.append(d)

    event_thought = MagicMock()
    event_thought.event_type = "content.delta"
    delta_thought = MagicMock()
    delta_thought.type = "thought"
    delta_thought.thought = "Raciocínio interno do Gemini."
    delta_thought.text = ""
    event_thought.delta = delta_thought
    event_thought.candidates = None

    event_text = MagicMock()
    event_text.event_type = "content.delta"
    delta_text = MagicMock()
    delta_text.type = "text"
    delta_text.text = " Resposta pública final."
    event_text.delta = delta_text
    event_text.candidates = None

    event_complete = MagicMock()
    event_complete.event_type = "interaction.complete"
    interaction_obj = MagicMock()
    interaction_obj.status = "completed"
    step_model = MagicMock()
    step_model.type = "model_output"
    content_item = MagicMock()
    content_item.text = " Resposta pública final."
    step_model.content = [content_item]
    interaction_obj.steps = [step_model]
    event_complete.interaction = interaction_obj

    mock_client = MagicMock()
    mock_client.interactions.create.return_value = [event_thought, event_text, event_complete]

    agent = AIAgent(
        model="gemini-3-flash",
        provider="gemini",
        api_key="test-key",
        stream_delta_callback=on_text,
        thinking_callback=on_thinking,
        reasoning_callback=on_reasoning,
    )

    with patch("google.genai.Client", return_value=mock_client):
        res = agent.run_conversation("Teste Gemini")

    assert res["failed"] is False
    assert thinking_chunks == ["Raciocínio interno do Gemini."]
    assert reasoning_chunks == ["Raciocínio interno do Gemini."]
    assert text_chunks == [" Resposta pública final."]
