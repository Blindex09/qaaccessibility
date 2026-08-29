import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import OpenAI

from run_agent import AIAgent


def _build_agent(provider, model, **overrides):
    return AIAgent(
        model=model,
        provider=provider,
        api_key="test-key",
        max_tokens=512,
        request_overrides=overrides,
    )


def _mock_openai_client(captured):
    mock_client = MagicMock()

    def _create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.status = "completed"
        resp.output_text = "ok"
        resp.output = []
        return resp

    mock_client.responses.create.side_effect = _create
    return mock_client


def _mock_anthropic_client(usage=None):
    mock_client = MagicMock()
    text_block = MagicMock(type="text")
    text_block.text = "ok"
    mock_client.messages.create.return_value = MagicMock(content=[text_block], usage=usage)
    return mock_client


def _ollama_chunk(content=None, tool_calls=None, thinking=None, done=False, prompt_eval_count=None, eval_count=None):
    """Chunk no formato da API nativa do Ollama (biblioteca oficial `ollama`,
    ChatResponse) -- usado por _run_ollama_native. Diferente do shape OpenAI:
    tool_calls vem completo num unico chunk (arguments ja e dict, nao string
    JSON fragmentada por indice), e as contagens de token vem no ultimo
    chunk (done=True), nao num objeto usage separado."""
    chunk = MagicMock()
    chunk.message.content = content
    chunk.message.thinking = thinking
    chunk.message.tool_calls = tool_calls
    chunk.done = done
    chunk.prompt_eval_count = prompt_eval_count
    chunk.eval_count = eval_count
    return chunk


def _ollama_tool_call(name, arguments):
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _mock_ollama_client(chat_side_effect):
    """Mock de `ollama.Client` -- chat_side_effect(**kwargs) deve devolver uma
    lista de chunks (ver _ollama_chunk), simulando stream=True."""
    mock_client = MagicMock()
    mock_client.chat.side_effect = chat_side_effect
    return mock_client


class TestRunOpenAIResponsesShape:
    def test_reasoning_model_uses_max_output_tokens(self):
        agent = _build_agent("openai", "gpt-5.6")  # reasoning=True in agent/models_dev.py
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            result = agent._run_openai("hello")

        assert result["failed"] is False
        assert captured["max_output_tokens"] == 512
        assert "max_tokens" not in captured
        assert "max_completion_tokens" not in captured
        assert "messages" not in captured
        assert captured["store"] is False

    def test_non_reasoning_openai_model_also_uses_responses(self):
        agent = _build_agent("openai", "gpt-5.4")  # reasoning=False in agent/models_dev.py
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["max_output_tokens"] == 512
        assert "messages" not in captured

    def test_xai_uses_responses_shape(self):
        agent = _build_agent("xai", "grok-4.5")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["max_output_tokens"] == 512
        assert "messages" not in captured

    def test_xai_sends_conv_id_header_for_cache_routing(self):
        """Docs xAI 2026 ("Maximizing Cache Hits"): x-grok-conv-id roteia
        chamadas para o mesmo servidor, maximizando o hit rate do cache de
        prompt (que e por-servidor). xAI usa _run_openai (Responses API), nao
        _run_chat_completions -- ver nota no proprio metodo."""
        agent = AIAgent(
            model="grok-4.5",
            provider="xai",
            api_key="test-key",
            max_tokens=512,
            conv_id="perceiver",
        )
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["extra_headers"] == {"x-grok-conv-id": "perceiver"}

    def test_openai_provider_never_sends_xai_conv_id_header(self):
        """O header e especifico do xAI -- nao deve ir para chamadas OpenAI
        mesmo quando conv_id esta setado (ex.: herdado do log_prefix)."""
        agent = AIAgent(
            model="gpt-5.6",
            provider="openai",
            api_key="test-key",
            max_tokens=512,
            conv_id="perceiver",
        )
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert "extra_headers" not in captured

    def test_real_sdk_serializes_responses_endpoint_and_flat_tools(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={
                "id": "resp_contract",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-5.6",
                "output": [{
                    "id": "msg_1",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok", "annotations": []}],
                }],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            })

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        real_client = OpenAI(
            api_key="test-key",
            base_url="https://provider.example/v1",
            http_client=http_client,
        )
        agent = _build_agent("openai", "gpt-5.6")
        agent.enabled_toolsets = ["contract"]
        from tools.registry import registry
        registry.register(
            "contract_tool",
            "contract",
            {
                "description": "Contract tool",
                "parameters": {"type": "object", "properties": {}},
            },
            lambda _args: "ok",
        )
        try:
            with patch("openai.OpenAI", return_value=real_client):
                result = agent._run_openai("hello")
        finally:
            real_client.close()

        payload = json.loads(requests[0].content)
        assert result["final_response"] == "ok"
        assert requests[0].url.path == "/v1/responses"
        assert payload["tools"][0]["name"] == "contract_tool"
        assert "function" not in payload["tools"][0]
        assert "messages" not in payload

    def test_compaction_sent_as_safety_net(self):
        """Compaction API nativa da OpenAI (2026): rede de seguranca server-side
        complementar a compactacao client-side (ver _ANTHROPIC_COMPACTION_BETA
        para a mesma logica do lado Anthropic)."""
        agent = _build_agent("openai", "gpt-5.6")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            result = agent._run_openai("hello")

        assert result["failed"] is False
        assert captured["extra_body"] == {
            "context_management": [{"type": "compaction", "compact_threshold": 150_000}]
        }

    def test_response_schema_sent_as_text_format(self):
        """Structured Outputs (Responses API): text.format com type
        json_schema, name, strict=True -- doc oficial 2026. Mesmo shape usado
        por xAI via o endpoint Responses-compativel."""
        schema = {"type": "object", "properties": {"issues": {"type": "array"}}}
        agent = _build_agent("openai", "gpt-5.6")
        agent.response_schema = schema
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            result = agent._run_openai("hello")

        assert result["failed"] is False
        assert captured["text"] == {
            "format": {
                "type": "json_schema",
                "name": "accessibility_issues",
                "schema": schema,
                "strict": True,
            }
        }

    def test_compaction_falls_back_gracefully_when_unsupported(self):
        """Se a conta/SDK ainda nao suportar o parametro, a API rejeita a
        chamada (ex.: 400) e o engine deve refazer sem context_management."""
        call_log: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            call_log.append(body)
            if "context_management" in body:
                return httpx.Response(
                    400,
                    json={"error": {"message": "Unknown parameter: 'context_management'.", "type": "invalid_request_error"}},
                )
            return httpx.Response(200, json={
                "id": "resp_fallback",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-5.6",
                "output": [{
                    "id": "msg_1",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok", "annotations": []}],
                }],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            })

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        real_client = OpenAI(api_key="test-key", http_client=http_client)
        agent = _build_agent("openai", "gpt-5.6")
        try:
            with patch("openai.OpenAI", return_value=real_client):
                result = agent._run_openai("hello")
        finally:
            real_client.close()

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        assert len(call_log) == 2
        assert "context_management" in call_log[0]
        assert "context_management" not in call_log[1]

    def test_response_schema_falls_back_gracefully_when_rejected(self):
        """Se o modelo/conta nao suportar text.format (ex.: modelo antigo),
        refaz sem schema E sem compaction (mesma tentativa combinada) --
        nunca perde a resposta."""
        call_log: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            call_log.append(body)
            if "text" in body:
                return httpx.Response(400, json={"error": {"message": "Unknown parameter: 'text.format'.", "type": "invalid_request_error"}})
            return httpx.Response(200, json={
                "id": "resp_fallback", "object": "response", "created_at": 0, "status": "completed", "model": "gpt-5.6",
                "output": [{"id": "msg_1", "type": "message", "status": "completed", "role": "assistant",
                            "content": [{"type": "output_text", "text": "ok", "annotations": []}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                          "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
            })

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        real_client = OpenAI(api_key="test-key", http_client=http_client)
        agent = _build_agent("openai", "gpt-5.6")
        agent.response_schema = {"type": "object"}
        try:
            with patch("openai.OpenAI", return_value=real_client):
                result = agent._run_openai("hello")
        finally:
            real_client.close()

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        assert len(call_log) == 2
        assert "text" in call_log[0]
        assert "text" not in call_log[1]


class TestRunOpenAIReasoningEffortForwarding:
    def test_reasoning_effort_is_forwarded_for_openai(self):
        # Regression test: llm_client.py computes request_overrides["reasoning_effort"]
        # (e.g. "none" to disable reasoning for leaf subagents) but _run_openai used to
        # only ever read "temperature" out of request_overrides -- the value went
        # nowhere, silently making the "disable reasoning" feature a no-op.
        agent = _build_agent("openai", "gpt-5.6", reasoning_effort="none")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["reasoning"] == {"effort": "none"}
        assert captured["include"] == ["reasoning.encrypted_content"]

    def test_reasoning_effort_is_forwarded_for_xai(self):
        agent = _build_agent("xai", "grok-4.5", reasoning_effort="low")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["reasoning"] == {"effort": "low"}

    def test_reasoning_effort_e_forwarded_para_ollama_cloud(self):
        """
        Bug real de auditoria (historico): reasoning_effort precisa chegar ao
        modelo real hospedado no Ollama Cloud, senao sub-agentes folha que
        pedem reasoning_effort="none" (desligar raciocinio) nunca conseguem
        isso. Corrigido em 2026-08-10 pra usar a API nativa /api/chat (ver
        _run_ollama_native) -- o campo nativo pra isso e `think`
        ('low'/'medium'/'high'/False), passado via ollama.Client().chat(),
        nao mais o `reasoning_effort` do endpoint OpenAI-compat /v1 (que tem
        bug documentado de tool-calling, ver docstring de _run_ollama_native).
        """
        agent = _build_agent("ollama-cloud", "deepseek-v4-pro:cloud", reasoning_effort="low")
        mock_client = _mock_ollama_client(lambda **_kwargs: [_ollama_chunk(content="ok", done=True)])
        with patch("ollama.Client", return_value=mock_client):
            agent._run_openai("hello")

        kwargs = mock_client.chat.call_args.kwargs
        assert kwargs["think"] == "low"
        assert kwargs["options"]["num_predict"] == 512


class TestParallelToolExecution:
    """Quando o modelo pede 2+ tools no mesmo turno, run_local_tool nao pode
    mais ser chamado sequencialmente (soma o tempo de cada tool I/O-bound) --
    _execute_tool_calls roda via ThreadPoolExecutor. Prova por tempo real: 2
    tools de 0.2s cada devem terminar em ~0.2s no total, nao ~0.4s."""

    def test_two_slow_tools_run_concurrently_not_sequentially(self):
        import time

        from tools.registry import registry

        def _slow_tool(_args):
            time.sleep(0.2)
            return "done"

        registry.register("slow_tool_a", "test_parallel", {"description": "", "parameters": {}}, _slow_tool)
        registry.register("slow_tool_b", "test_parallel", {"description": "", "parameters": {}}, _slow_tool)

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        start = time.monotonic()
        results = agent._execute_tool_calls([
            ("call-1", "slow_tool_a", {}),
            ("call-2", "slow_tool_b", {}),
        ])
        elapsed = time.monotonic() - start

        assert results["call-1"] == "done"
        assert results["call-2"] == "done"
        assert elapsed < 0.35, f"esperava execucao paralela (~0.2s), levou {elapsed:.2f}s (parece sequencial)"

    def test_single_tool_call_still_works(self):
        from tools.registry import registry

        registry.register("single_tool", "test_parallel", {"description": "", "parameters": {}}, lambda _args: "ok")

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        results = agent._execute_tool_calls([("call-1", "single_tool", {})])

        assert results == {"call-1": "ok"}

    def test_callbacks_fire_for_every_call_in_parallel_mode(self):
        from tools.registry import registry

        registry.register("cb_tool_a", "test_parallel", {"description": "", "parameters": {}}, lambda _args: "a")
        registry.register("cb_tool_b", "test_parallel", {"description": "", "parameters": {}}, lambda _args: "b")

        started, completed = [], []
        agent = AIAgent(
            model="gpt-5.6", provider="openai", api_key="test-key",
            tool_start_callback=lambda tid, name, args: started.append((tid, name)),
            tool_complete_callback=lambda tid, name, args, result: completed.append((tid, name, result)),
        )
        agent._execute_tool_calls([("call-1", "cb_tool_a", {}), ("call-2", "cb_tool_b", {})])

        assert set(started) == {("call-1", "cb_tool_a"), ("call-2", "cb_tool_b")}
        assert set(completed) == {("call-1", "cb_tool_a", "a"), ("call-2", "cb_tool_b", "b")}


class TestContextDriftDetection:
    """Nenhum provider expoe um sinal nativo de 'o agente esta travado' (achado
    de pesquisa 2026: so ha finish_reason/stop_reason por limite de tokens,
    nunca por qualidade). A tecnica pratica e barata e detectar REPETICAO: a
    mesma tool+args+resultado repetida na janela recente. Ao detectar, uma
    reflexao e anexada ao resultado da tool que volta pro modelo -- a acao de
    'Replanning' em resposta ao 'Reflection'."""

    def test_repeated_identical_call_triggers_reflection_note(self):
        from tools.registry import registry

        registry.register("stuck_tool", "test_drift", {"description": "", "parameters": {}}, lambda _args: "mesmo resultado sempre")

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        results = None
        for _ in range(3):
            results = agent._execute_tool_calls([("call-1", "stuck_tool", {"x": 1})])

        assert "[SYSTEM REFLECTION]" in results["call-1"]
        assert results["call-1"].startswith("mesmo resultado sempre")

    def test_varying_results_never_trigger_reflection(self):
        """Resultado diferente a cada chamada -- nao e um loop travado, e progresso real."""
        from tools.registry import registry

        counter = {"n": 0}

        def _tool(_args):
            counter["n"] += 1
            return f"resultado {counter['n']}"

        registry.register("progressing_tool", "test_drift", {"description": "", "parameters": {}}, _tool)

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        results = None
        for _ in range(5):
            results = agent._execute_tool_calls([("call-1", "progressing_tool", {})])

        assert "[SYSTEM REFLECTION]" not in results["call-1"]

    def test_reflection_fires_only_once_per_conversation(self):
        from tools.registry import registry

        registry.register("stuck_tool_2", "test_drift", {"description": "", "parameters": {}}, lambda _args: "travado")

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        reflection_count = 0
        for _ in range(6):
            r = agent._execute_tool_calls([("call-1", "stuck_tool_2", {})])
            if "[SYSTEM REFLECTION]" in r["call-1"]:
                reflection_count += 1

        assert reflection_count == 1

    def test_context_drift_callback_fires_with_a_reason(self):
        from tools.registry import registry

        registry.register("stuck_tool_3", "test_drift", {"description": "", "parameters": {}}, lambda _args: "parado")

        reasons = []
        agent = AIAgent(
            model="gpt-5.6", provider="openai", api_key="test-key",
            context_drift_callback=lambda reason: reasons.append(reason),
        )
        for _ in range(3):
            agent._execute_tool_calls([("call-1", "stuck_tool_3", {})])

        assert len(reasons) == 1
        assert "stuck_tool_3" in reasons[0]

    def test_callback_error_never_breaks_the_tool_loop(self):
        from tools.registry import registry

        registry.register("stuck_tool_4", "test_drift", {"description": "", "parameters": {}}, lambda _args: "erro no callback nao deve propagar")

        def _boom(_reason):
            raise RuntimeError("callback quebrado")

        agent = AIAgent(
            model="gpt-5.6", provider="openai", api_key="test-key",
            context_drift_callback=_boom,
        )
        results = None
        for _ in range(3):
            results = agent._execute_tool_calls([("call-1", "stuck_tool_4", {})])

        assert "[SYSTEM REFLECTION]" in results["call-1"]

    def test_drift_detected_across_parallel_calls_too(self):
        """A deteccao roda tambem no caminho de 2+ chamadas paralelas (nao so
        no caminho sequencial de 1 chamada)."""
        from tools.registry import registry

        registry.register("stuck_tool_5", "test_drift", {"description": "", "parameters": {}}, lambda _args: "sempre igual")
        registry.register("other_tool", "test_drift", {"description": "", "parameters": {}}, lambda _args: "outra coisa")

        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key")
        results = None
        for _ in range(3):
            results = agent._execute_tool_calls([
                ("call-1", "stuck_tool_5", {}),
                ("call-2", "other_tool", {}),
            ])

        assert "[SYSTEM REFLECTION]" in results["call-1"]
        assert "[SYSTEM REFLECTION]" not in results["call-2"]


class TestMultimodalImageInput:
    """Input de imagem (2026): pesquisa por provider confirmou shape exato do
    content block de imagem, todos no MESMO endpoint de texto/multi-turno
    (nenhum provider exige endpoint separado). Ollama Cloud e o unico com
    catalogo majoritariamente texto-only e bug documentado de 500 no endpoint
    OpenAI-compat com alguns modelos de visao -- por isso o fallback
    sem-imagem (run_conversation) e testado à parte, provider-agnostico."""

    _IMG = {"media_type": "image/png", "data": "aGVsbG8="}

    def test_openai_sends_input_image_content_block(self):
        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key", max_tokens=512, images=[self._IMG])
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("olhe esta imagem")

        user_content = captured["input"][-1]["content"]
        assert user_content == [
            {"type": "input_text", "text": "olhe esta imagem"},
            {"type": "input_image", "image_url": "data:image/png;base64,aGVsbG8="},
        ]

    def test_openai_without_images_keeps_plain_string_content(self):
        """Sem imagem, o content continua string simples -- sem mudanca de
        contrato para o caminho ja existente (25 agentes de analise, chat)."""
        agent = _build_agent("openai", "gpt-5.6")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")

        assert captured["input"][-1]["content"] == "hello"

    def test_anthropic_sends_image_content_block(self):
        agent = AIAgent(
            model="claude-opus-5", provider="anthropic", api_key="test-key",
            max_tokens=512, images=[self._IMG],
        )
        captured: dict = {}
        with patch("anthropic.Anthropic", TestAnthropicWirePayload._capturing_anthropic(captured)):
            agent._run_anthropic("olhe esta imagem")

        user_content = captured["messages"][-1]["content"]
        assert user_content == [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}},
            {"type": "text", "text": "olhe esta imagem"},
        ]

    def test_gemini_sends_inline_data_part_stateful(self):
        """Turno com previous_interaction_id (conversa em andamento) -- caso
        simples, input vira direto a lista de parts."""
        agent = AIAgent(
            model="gemini-3.6-flash", provider="gemini", api_key="test-key",
            images=[self._IMG], previous_provider_response_id="interaction-0",
        )
        resp = MagicMock(status="completed", steps=[
            MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])
        ])
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = resp

        with patch("google.genai.Client", return_value=mock_client):
            agent._run_gemini("olhe esta imagem")

        call_kwargs = mock_client.interactions.create.call_args.kwargs
        assert call_kwargs["input"] == [
            {"inlineData": {"mimeType": "image/png", "data": "aGVsbG8="}},
            {"text": "olhe esta imagem"},
        ]

    def test_gemini_sends_inline_data_part_with_history(self):
        """Primeiro turno (sem previous_interaction_id) -- historico anterior
        vira 1 part de texto, current turn vira parts de imagem+texto."""
        agent = AIAgent(
            model="gemini-3.6-flash", provider="gemini", api_key="test-key",
            images=[self._IMG],
            prefill_messages=[{"role": "user", "content": "oi"}, {"role": "assistant", "content": "ola"}],
        )
        resp = MagicMock(status="completed", steps=[
            MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])
        ])
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = resp

        with patch("google.genai.Client", return_value=mock_client):
            agent._run_gemini("olhe esta imagem")

        call_kwargs = mock_client.interactions.create.call_args.kwargs
        assert call_kwargs["input"][0] == {"text": "user: oi\nassistant: ola"}
        assert call_kwargs["input"][1] == {"inlineData": {"mimeType": "image/png", "data": "aGVsbG8="}}
        assert call_kwargs["input"][2] == {"text": "olhe esta imagem"}

    def test_chat_completions_sends_image_url_content_block(self):
        agent = AIAgent(
            model="gemma4:31b", provider="ollama-cloud", api_key="test-key",
            images=[self._IMG],
        )
        captured: dict = {}
        client = TestChatCompletionsStructuredOutputs._mock_chat_completions_client(captured)
        with patch("openai.OpenAI", return_value=client):
            agent._run_chat_completions("olhe esta imagem")

        user_content = captured["messages"][-1]["content"]
        assert user_content == [
            {"type": "text", "text": "olhe esta imagem"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
        ]

    def test_run_conversation_retries_without_image_when_provider_rejects_it(self):
        """Nenhum provider documenta um jeito de saber ANTES da chamada se o
        modelo aceita imagem -- o fallback e reativo: falha com imagem -> refaz
        sem ela (nota explicando o porque) -- degradacao mais leve antes de
        cair pra outro provider inteiro."""
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            images=[self._IMG],
        )
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
            if len(calls) == 1:
                raise RuntimeError("500 internal server error (vision not supported)")
            return [_ollama_chunk(content="ok sem imagem", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("olhe esta imagem")

        assert result["failed"] is False
        assert result["final_response"] == "ok sem imagem"
        assert len(calls) == 2
        # 1a tentativa: imagem incluida (campo `images` nativo, nao content-array)
        assert calls[0]["messages"][-1]["images"] == ["aGVsbG8="]
        # 2a tentativa: texto puro, com a nota explicando a degradacao
        assert calls[1]["messages"][-1]["content"] == "olhe esta imagem" + AIAgent._IMAGE_UNSUPPORTED_NOTE
        assert "images" not in calls[1]["messages"][-1]
        assert agent.images == []


class TestNoToolCallAnnouncementRetry:
    """Achado real (teste E2E de chat completo, ollama-cloud, 2026-08-10): em
    turnos de follow-up o modelo às vezes só anuncia a ação ('Vou gerar a
    planilha...') e encerra o turno sem nunca chamar a tool correspondente.
    Retentativa estrutural (resposta curta + zero tool_calls + tools
    disponíveis + 1a chamada do turno), sem keyword/blacklist de conteúdo --
    ver _NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS em run_agent.py."""

    def _register_tool(self, name: str):
        from tools.registry import registry
        registry.register(
            name, "test_nudge",
            {"description": "", "parameters": {"type": "object", "properties": {}}},
            lambda _args: "tool ran",
        )

    def test_short_no_tool_response_triggers_one_retry_that_then_calls_the_tool(self):
        self._register_tool("nudge_tool_a")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        calls: list[dict] = []

        def _create(**kwargs):
            # messages e a MESMA lista mutada a cada iteracao do loop -- precisa
            # copiar aqui, senao todas as entradas de `calls` acabam apontando
            # pro estado FINAL da lista em vez do estado no momento da chamada.
            calls.append({**kwargs, "messages": list(kwargs["messages"])})
            if len(calls) == 1:
                return [_ollama_chunk(content="Vou gerar a planilha agora.", done=True)]
            if len(calls) == 2:
                tc = _ollama_tool_call("nudge_tool_a", {})
                return [_ollama_chunk(tool_calls=[tc], done=True)]
            return [_ollama_chunk(content="Aqui está a planilha.", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("gera a planilha")

        assert result["failed"] is False
        assert result["final_response"] == "Aqui está a planilha."
        assert len(calls) == 3
        # A 2a chamada deve conter a mensagem de anuncio do modelo + a nota de sistema pedindo pra agir
        nudge_messages = calls[1]["messages"]
        assert nudge_messages[-2]["content"] == "Vou gerar a planilha agora."
        assert "nenhuma ferramenta foi chamada" in nudge_messages[-1]["content"]

    def test_only_one_retry_per_turn_even_if_model_stalls_again(self):
        """A retentativa só dispara na 1a chamada do turno (_iteration == 0):
        se o modelo travar de novo depois, o loop encerra em vez de repetir
        pra sempre."""
        self._register_tool("nudge_tool_b")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append(kwargs)
            return [_ollama_chunk(content="Vou fazer isso.", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("faz algo")

        assert result["failed"] is False
        assert len(calls) == 2  # 1 original + 1 retentativa, depois encerra

    def test_long_final_answer_without_tool_calls_is_never_retried(self):
        """Resposta longa (relatório/resumo final legítimo) sem tool_calls não
        deve disparar retentativa -- só respostas curtas (proxy estrutural de
        'anúncio de ação', ver limiar _NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS)."""
        self._register_tool("nudge_tool_c")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        long_answer = "Relatório completo de acessibilidade. " * 20
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append(kwargs)
            return [_ollama_chunk(content=long_answer, done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("resuma a análise")

        assert result["failed"] is False
        assert result["final_response"] == long_answer
        assert len(calls) == 1

    def test_empty_response_after_a_tool_call_retries_even_past_iteration_zero(self):
        """Achado real (validação E2E completa, 2026-08-10): um turno real
        chamou clarify -> analyze_page -> clarify de novo (tudo aprovado) e
        terminou com resposta final TOTALMENTE VAZIA na 4a chamada -- a
        retentativa original só disparava na 1a chamada do turno
        (_iteration == 0), então não pegava esse caso. Resposta vazia sem
        tool_call nunca é um fim de turno válido, então agora dispara em
        QUALQUER iteração (diferente de resposta curta-mas-não-vazia, que
        continua restrita à 1a chamada -- ver teste acima)."""
        self._register_tool("nudge_tool_d")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=6,
        )
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                # 1a chamada: já chama a tool direto (simula o clarify/analyze
                # já resolvidos antes deste ponto do teste)
                tc = _ollama_tool_call("nudge_tool_d", {})
                return [_ollama_chunk(tool_calls=[tc], done=True)]
            if len(calls) == 2:
                # 2a chamada (depois do resultado da tool): resposta VAZIA,
                # sem tool_call -- o bug real observado.
                return [_ollama_chunk(content="", done=True)]
            # 3a chamada (depois da retentativa): resposta final de verdade.
            return [_ollama_chunk(content="Pronto, conferido.", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("confere isso pra mim")

        assert result["failed"] is False
        assert result["final_response"] == "Pronto, conferido."
        assert len(calls) == 3  # tool-call + resposta vazia + retentativa bem-sucedida

    def test_empty_response_even_after_retry_never_returns_silent_final_response(self):
        """Achado real (E2E completa, 2026-08-10, 3a rodada): um turno pedindo
        correção direta ("Corrige os problemas... gera o zip") não chamou
        NENHUMA ferramenta e voltou com final_response="" mesmo depois da
        retentativa de nudge -- o loop só fazia `break` e devolvia string
        vazia, deixando o usuário sem resposta e sem a ação ter ocorrido.
        Agora, se o turno inteiro nunca chamou uma tool E a resposta final
        continua vazia após a retentativa, final_response vira uma mensagem
        honesta em vez de silêncio."""
        self._register_tool("nudge_tool_e")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append(kwargs)
            # Toda chamada (original + retentativa) volta vazia, sem tool_call.
            return [_ollama_chunk(content="", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("corrige os problemas e gera o zip")

        assert result["failed"] is False
        assert result["final_response"].strip() != ""
        assert "reformular" in result["final_response"].lower() or "tentar" in result["final_response"].lower()
        assert len(calls) == 2  # 1 original + 1 retentativa, depois encerra com fallback

    def test_tool_call_hallucinated_as_text_json_triggers_nudge_and_real_call(self):
        """Achado real (E2E completa, 2026-08-10, 3a rodada): um turno pedindo
        generate_accessibility_statement voltou com o texto
        '{"name": "generate_accessibility_statement", "arguments": {...}}'
        escrito como conteúdo normal, sem NUNCA usar o mecanismo real de
        tool_calls -- o modelo alucinou a chamada em vez de executá-la. Como o
        texto não é vazio nem curto o bastante pro gatilho normal de anúncio
        (_NO_TOOL_CALL_ANNOUNCEMENT_MAX_CHARS), o nudge não disparava e a
        ferramenta nunca rodava de verdade. Agora, texto no formato
        {"name": str, "arguments": dict} força o nudge independente de
        tamanho/iteração, e a retentativa consegue produzir uma tool_call real.
        A correção definitiva de verdade e a API nativa (_run_ollama_native)
        nao ter esse problema por construcao -- este teste continua existindo
        como rede de seguranca adicional caso o comportamento reapareca."""
        self._register_tool("nudge_tool_f")
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        fake_call_text = (
            '{"name": "nudge_tool_f", "arguments": {"pre_exec_msg": "Gerando...", '
            '"organization_name": "MarsCommuter Inc", "product_name": "MarsCommuter Web", '
            '"contact_email": "a11y@marscommuter.example.com", "contact_phone": "+1 555-0142"}}'
        )
        assert len(fake_call_text) > 220  # garante que não seria pego pelo gatilho de tamanho
        calls: list[dict] = []

        def _create(**kwargs):
            # messages e a MESMA lista mutada a cada iteracao do loop -- precisa
            # copiar aqui, senao todas as entradas de `calls` acabam apontando
            # pro estado FINAL da lista em vez do estado no momento da chamada.
            calls.append({**kwargs, "messages": list(kwargs["messages"])})
            if len(calls) == 1:
                # 1a chamada: o modelo "alucina" a tool call como texto puro.
                return [_ollama_chunk(content=fake_call_text, done=True)]
            if len(calls) == 2:
                # 2a chamada (depois do nudge): tool_call real de verdade.
                tc = _ollama_tool_call("nudge_tool_f", {})
                return [_ollama_chunk(tool_calls=[tc], done=True)]
            # 3a chamada (depois do resultado da tool): resposta final normal.
            return [_ollama_chunk(content="Declaração gerada.", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("gera a declaração de acessibilidade")

        assert result["failed"] is False
        assert len(calls) == 3  # texto-alucinado + tool_call real + resposta final
        nudge_messages = calls[1]["messages"]
        assert "não foi executada de verdade" in nudge_messages[-1]["content"]

    def test_tool_arguments_hallucinated_as_text_without_name_wrapper_triggers_nudge(self):
        """Achado real (E2E completa, 2026-08-10, verificação da API nativa do
        Ollama): variante mais sutil do bug acima -- o modelo às vezes escreve
        só os ARGUMENTOS de uma tool (ex.: {"question": "...", "options": [...]}
        pros parâmetros de `clarify`) sem sequer o wrapper {"name",...}. O
        detector original só reconhecia {"name": str, "arguments": dict};
        agora também reconhece um JSON cujas chaves batem com os `properties`
        de alguma tool disponível no turno (ver tools_arg em
        _looks_like_fake_tool_call_json)."""
        from tools.registry import registry
        registry.register(
            "clarify_like_tool", "test_nudge",
            {
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array"},
                    },
                },
            },
            lambda _args: "clarify respondida",
        )
        agent = AIAgent(
            model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key",
            enabled_toolsets=["test_nudge"], max_iterations=5,
        )
        # Sem o wrapper "name"/"arguments" -- só os parâmetros crus, como
        # observado ao vivo contra o modelo real.
        fake_args_only_text = (
            '{"question": "Plano de auditoria do site:\\n1. [ ] Definir escopo\\n'
            '2. [ ] Executar varredura", "options": ["Aprovar Plano", "Cancelar"]}'
        )
        calls: list[dict] = []

        def _create(**kwargs):
            calls.append({**kwargs, "messages": list(kwargs["messages"])})
            if len(calls) == 1:
                return [_ollama_chunk(content=fake_args_only_text, done=True)]
            if len(calls) == 2:
                tc = _ollama_tool_call("clarify_like_tool", {"question": "Aprovar?", "options": ["Sim"]})
                return [_ollama_chunk(tool_calls=[tc], done=True)]
            return [_ollama_chunk(content="Combinado.", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("audita o site inteiro")

        assert result["failed"] is False
        assert len(calls) == 3
        nudge_messages = calls[1]["messages"]
        assert "não foi executada de verdade" in nudge_messages[-1]["content"]

    def test_empty_response_without_tools_available_stays_empty_not_a_chat_message(self):
        """Achado real (validação E2E 2026-08-10, rodada da API nativa): a
        mensagem de fallback humanizada ("Não consegui processar esse
        pedido...") vazou pro ClassifierAgent/ClarifierAgent -- agentes
        especialistas que chamam o modelo SEM ferramentas e esperam JSON cru,
        nunca texto de chat. O fallback quebrou o parser JSON deles com uma
        frase humana em vez de string vazia -- pior que o problema original
        pra esses chamadores. O fallback só deve substituir final_response
        quando o turno tinha ferramentas disponíveis (tools_arg truthy) --
        chamadas sem tools (sem enabled_toolsets) devem continuar devolvendo
        "" numa resposta vazia, não uma frase de chat."""
        agent = AIAgent(model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key")
        assert agent.enabled_toolsets == []  # sem ferramentas -- shape de chamada de agente especialista

        def _create(**_kwargs):
            return [_ollama_chunk(content="", done=True)]

        with patch("ollama.Client", return_value=_mock_ollama_client(_create)):
            result = agent.run_conversation("classifique este HTML")

        assert result["failed"] is False
        assert result["final_response"] == ""


class TestSdkDefaultRetriesNeverDisabled:
    """Retry/backoff em erro transitorio (conexao, timeout, 429, 5xx) vem de
    graca dos SDKs oficiais (default 2-5x conforme o SDK) -- run_agent.py NAO
    deve construir nenhum client com max_retries=0 nem qualquer override que
    desative isso, e nao deve implementar retry proprio por cima (bug real
    documentado: stackar os dois multiplica o tempo de espera em travamentos
    silenciosos). Este teste trava que nenhum construtor de client passe
    max_retries explicitamente."""

    def test_openai_client_never_overrides_max_retries(self):
        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = _mock_openai_client({})
            _build_agent("openai", "gpt-5.6")._run_openai("hello")
        assert "max_retries" not in mock_cls.call_args.kwargs

    def test_anthropic_client_never_overrides_max_retries(self):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = _mock_anthropic_client()
            AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key")._run_anthropic("hello")
        assert "max_retries" not in mock_cls.call_args.kwargs

    def test_gemini_client_never_overrides_max_retries(self):
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = MagicMock(
            status="completed",
            steps=[MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])],
        )
        with patch("google.genai.Client") as mock_cls:
            mock_cls.return_value = mock_client
            AIAgent(model="gemini-3.6-flash", provider="gemini", api_key="test-key")._run_gemini("hello")
        assert "max_retries" not in mock_cls.call_args.kwargs


class TestOllamaNativeApiIsTheDefaultPath:
    """Achado real (2026-08-10, pesquisa confirmada via docs oficiais Ollama +
    openclaw): o endpoint OpenAI-compat /v1 do Ollama Cloud tem bug
    DOCUMENTADO de tool-calling -- o modelo pode emitir o JSON da chamada
    como texto puro em vez de uma tool_call estruturada. A API nativa
    /api/chat (biblioteca oficial `ollama`) nao tem esse problema. Estes
    testes travam que ollama/ollama-cloud usem a API nativa por padrao, e
    caiam pro endpoint OpenAI-compat apenas se a nativa genuinamente falhar."""

    def test_ollama_cloud_uses_native_client_not_openai_compat_v1(self):
        agent = _build_agent("ollama-cloud", "deepseek-v4-pro")
        mock_client = _mock_ollama_client(lambda **_kwargs: [_ollama_chunk(content="ok", done=True)])
        with patch("ollama.Client", return_value=mock_client) as constructor, patch("openai.OpenAI") as openai_ctor:
            result = agent._run_openai("hello")

        assert result["final_response"] == "ok"
        constructor.assert_called_once()
        assert constructor.call_args.kwargs["host"] == "https://ollama.com"
        openai_ctor.assert_not_called()

    def test_ollama_cloud_falls_back_to_openai_compat_if_native_client_fails(self):
        """Rede de seguranca: se a biblioteca `ollama` nao estiver disponivel
        ou a chamada nativa falhar por qualquer motivo, o agente ainda
        responde via o endpoint OpenAI-compat em vez de quebrar o turno."""
        agent = _build_agent("ollama-cloud", "deepseek-v4-pro")
        captured: dict = {}

        def _create(**kwargs):
            captured.update(kwargs)
            message = MagicMock(content="ok via fallback", tool_calls=None)
            return MagicMock(choices=[MagicMock(message=message)], usage=None)

        openai_mock_client = MagicMock()
        openai_mock_client.chat.completions.create.side_effect = _create

        with patch("ollama.Client", side_effect=RuntimeError("ollama package indisponivel")), \
             patch("openai.OpenAI", return_value=openai_mock_client):
            result = agent._run_openai("hello")

        assert result["failed"] is False
        assert result["final_response"] == "ok via fallback"

    def test_multimodal_content_array_reaches_native_client_as_images_field(self):
        """Achado real (2026-08-11, validando fix_local_project_files ao vivo):
        chamadores como _verify_layout_visually (chat_tools.py) montam o proprio
        content-array estilo OpenAI ([{"type": "text", ...},
        {"type": "image_url", ...}]) em vez de usar self.images. Isso batia
        num erro de validacao Pydantic na API nativa do Ollama ("content
        deveria ser string, veio lista"), fazendo TODA chamada multimodal
        cair sempre pro fallback OpenAI-compat, nunca usando a API nativa de
        verdade. Trava que o content-array e' normalizado corretamente."""
        agent = _build_agent("ollama-cloud", "deepseek-v4-pro")
        captured: dict = {}

        def _capture_chat(**kwargs):
            captured.update(kwargs)
            return iter([_ollama_chunk(content="layout ok", done=True)])

        mock_client = _mock_ollama_client(_capture_chat)
        multimodal_prompt = [
            {"type": "text", "text": "Check this screenshot."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmFrZQ=="}},
        ]

        with patch("ollama.Client", return_value=mock_client):
            result = agent._run_openai(multimodal_prompt)

        assert result["final_response"] == "layout ok"
        user_msg = captured["messages"][-1]
        assert isinstance(user_msg["content"], str)
        assert user_msg["content"] == "Check this screenshot."
        assert user_msg["images"] == ["ZmFrZQ=="]


class TestProviderRoutingAndFailover:
    def test_xai_uses_official_base_url_by_default(self):
        agent = _build_agent("xai", "grok-4.5")
        captured = {}
        mock_client = _mock_openai_client(captured)
        with patch("openai.OpenAI", return_value=mock_client) as constructor:
            agent._run_openai("hello")

        assert constructor.call_args.kwargs["base_url"] == "https://api.x.ai/v1"

    def test_configured_fallback_runs_after_primary_failure(self):
        agent = AIAgent(
            model="primary-model",
            provider="openai",
            api_key="primary-key",
            fallback_model={
                "provider": "anthropic",
                "model": "fallback-model",
                "api_key": "fallback-key",
            },
        )
        with patch.object(agent, "_run_openai", side_effect=RuntimeError("primary down")), patch.object(
            AIAgent,
            "_run_anthropic",
            return_value={"failed": False, "final_response": "fallback ok"},
        ):
            result = agent.run_conversation("hello")

        assert result["failed"] is False
        assert result["used_fallback"] is True
        assert result["final_response"] == "fallback ok"

    def test_auto_fallback_restricted_to_same_provider_for_individual_provider(self):
        agent = AIAgent(
            model="gpt-5.6",
            provider="openai",
            api_key="openai-key",
        )
        with patch("agent.models_dev.list_agentic_models", return_value=["gpt-5.6", "gpt-5.4", "o1"]):
            fb = agent._resolve_auto_fallback()

        assert fb is not None
        assert fb["provider"] == "openai"
        assert fb["model"] == "gpt-5.4"
        assert fb["api_key"] == "openai-key"

    def test_auto_fallback_returns_none_when_no_alternative_in_same_provider(self):
        agent = AIAgent(
            model="gpt-5.6",
            provider="openai",
            api_key="openai-key",
        )
        with patch("agent.models_dev.list_agentic_models", return_value=["gpt-5.6"]):
            fb = agent._resolve_auto_fallback()

        assert fb is None

    def test_auto_fallback_cross_provider_for_agentic_auto(self):
        agent = AIAgent(
            model="auto",
            provider="agentic",
        )
        with patch("os.getenv", side_effect=lambda k: "anthropic-key" if k == "ANTHROPIC_API_KEY" else None), \
             patch("backend.src.services.model_router.resolve_alto_model", return_value="claude-opus-5"):
            fb = agent._resolve_auto_fallback()

        assert fb is not None
        assert fb["provider"] == "anthropic"
        assert fb["model"] == "claude-opus-5"

    def test_run_conversation_formats_429_friendly_error(self):
        agent = AIAgent(
            model="gpt-5.6",
            provider="openai",
            api_key="openai-key",
        )
        with patch.object(agent, "_run_openai", side_effect=RuntimeError("HTTP 429: You have reached your weekly usage limit")), \
             patch.object(agent, "_resolve_auto_fallback", return_value=None):
            result = agent.run_conversation("hello")

        assert result["failed"] is True
        assert "Desculpe, ocorreu um erro: O limite de requisições por minuto (Rate Limit) ou cota semanal foi atingido no provedor de IA." in result["error"]


class TestOpenCodeGoEndpointRoutingByModel:
    """Achado real (auditoria docs/auditoria-prompt-caching-structured-output-
    2026-08-26.md): OpenCode Go so expoe a Responses API (_run_openai) para o
    unico modelo OpenAI-family do catalogo (gpt-5.6-luna). Os demais modelos
    verificados da cadeia de Structured Outputs (Kimi, GLM, DeepSeek, Qwen)
    usam o endpoint Chat Completions padrao (_run_chat_completions), como o
    restante do catalogo do provider -- roteamento por MODELO, nao so por
    provider."""

    def test_gpt_luna_uses_responses_api(self):
        agent = _build_agent("opencode-go", "gpt-5.6-luna")
        with (
            patch.object(agent, "_run_openai", return_value={"failed": False, "final_response": "ok"}) as mock_responses,
            patch.object(agent, "_run_chat_completions") as mock_chat,
        ):
            result = agent.run_conversation("hello")

        mock_responses.assert_called_once()
        mock_chat.assert_not_called()
        assert result["final_response"] == "ok"

    def test_other_opencode_go_models_use_chat_completions(self):
        for model in ("kimi-k2.6", "glm-5.1", "deepseek-v4-flash", "qwen3.8-max"):
            agent = _build_agent("opencode-go", model)
            with (
                patch.object(agent, "_run_chat_completions", return_value={"failed": False, "final_response": "ok"}) as mock_chat,
                patch.object(agent, "_run_openai") as mock_responses,
            ):
                result = agent.run_conversation("hello")

            mock_chat.assert_called_once()
            mock_responses.assert_not_called()
            assert result["final_response"] == "ok"


class TestRunGeminiInteractions:

    def test_function_call_round_trip_does_not_raise(self):
        """
        A prévia de Interactions também pode devolver `steps` com
        `model_output`; o SDK 2.14 tipa `outputs`. O adaptador aceita ambos sem
        perder function calls nem texto.
        """
        agent = AIAgent(model="gemini-3.6-flash", provider="gemini", api_key="test-key", max_tokens=512, max_iterations=2)

        first_resp = MagicMock()
        first_resp.id = "interaction-1"
        first_resp.status = "requires_action"
        first_resp.steps = [
            MagicMock(type="function_call", id="call-1", name="some_tool", arguments={"a": 1})
        ]

        second_resp = MagicMock()
        second_resp.id = "interaction-2"
        second_resp.status = "completed"
        second_resp.steps = [
            MagicMock(type="model_output", content=[MagicMock(type="text", text="final answer")])
        ]

        mock_client = MagicMock()
        mock_client.interactions.create.side_effect = [first_resp, second_resp]

        with patch("google.genai.Client", return_value=mock_client):
            result = agent._run_gemini("hello")

        assert result["failed"] is False
        assert result["final_response"] == "final answer"
        assert mock_client.interactions.create.call_count == 2
        second = mock_client.interactions.create.call_args_list[1].kwargs
        assert second["previous_interaction_id"] == "interaction-1"
        assert second["input"][0]["call_id"] == "call-1"
        assert mock_client.models.generate_content.call_count == 0

    def test_response_schema_sent_as_response_format(self):
        """Structured Outputs (Interactions API): response_format com
        mime_type application/json + schema -- doc oficial 2026."""
        schema = {"type": "object", "properties": {"issues": {"type": "array"}}}
        agent = AIAgent(
            model="gemini-3.6-flash", provider="gemini", api_key="test-key",
            response_schema=schema,
        )
        resp = MagicMock(status="completed", steps=[
            MagicMock(type="model_output", content=[MagicMock(type="text", text="{}")])
        ])
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = resp

        with patch("google.genai.Client", return_value=mock_client):
            result = agent._run_gemini("hello")

        assert result["failed"] is False
        call_kwargs = mock_client.interactions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        }

    def test_response_schema_falls_back_gracefully_when_unsupported(self):
        """Se response_format nao for aceito, refaz sem ele -- sem propagar erro."""
        schema = {"type": "object"}
        agent = AIAgent(
            model="gemini-3.6-flash", provider="gemini", api_key="test-key",
            response_schema=schema,
        )
        resp = MagicMock(status="completed", steps=[
            MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])
        ])
        mock_client = MagicMock()
        mock_client.interactions.create.side_effect = [RuntimeError("response_format not supported"), resp]

        with patch("google.genai.Client", return_value=mock_client):
            result = agent._run_gemini("hello")

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        assert mock_client.interactions.create.call_count == 2
        first_call = mock_client.interactions.create.call_args_list[0].kwargs
        second_call = mock_client.interactions.create.call_args_list[1].kwargs
        assert "response_format" in first_call
        assert "response_format" not in second_call


class TestAnthropicReasoningEffortForwarding:
    def test_reasoning_effort_is_forwarded_for_anthropic(self):
        """
        Bug real de auditoria: _run_anthropic só encaminhava "temperature" de
        request_overrides. Os outros três caminhos de provider (_run_openai,
        _run_chat_completions, _run_gemini) já encaminhavam reasoning_effort, e
        aqui ele era descartado em silêncio -- subagentes folha que pedem
        reasoning_effort="none" (desligar raciocínio) nunca conseguiam isso no
        Anthropic. A API não tem o campo `reasoning_effort`: a profundidade é o
        extended thinking, então o valor é traduzido para `thinking`.
        """
        agent = _build_agent("anthropic", "claude-opus-5", reasoning_effort="none")
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "disabled"}

    def test_reasoning_effort_becomes_adaptive_thinking_plus_effort(self):
        """
        Claude 4.6+ removeu o extended thinking por orçamento de tokens: enviar
        `thinking: {"type": "enabled", "budget_tokens": N}` devolve 400 nos
        modelos flagship. A profundidade agora é adaptive thinking somada a
        `output_config.effort`.
        """
        agent = AIAgent(
            model="claude-opus-5",
            provider="anthropic",
            api_key="test-key",
            max_tokens=8192,
            request_overrides={"reasoning_effort": "high", "temperature": 0.2},
        )
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "high"}
        assert "budget_tokens" not in kwargs["thinking"]
        # Claude 4.6+ removeu temperature/top_p/top_k: enviar devolve 400.
        assert "temperature" not in kwargs

    @pytest.mark.parametrize(
        "model",
        ["claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-fable-5"],
    )
    def test_flagship_models_never_receive_budget_tokens(self, model):
        agent = AIAgent(
            model=model,
            provider="anthropic",
            api_key="test-key",
            max_tokens=8192,
            request_overrides={"reasoning_effort": "xhigh"},
        )
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "xhigh"}

    def test_legacy_model_still_uses_the_token_budget_format(self):
        """Modelos anteriores ao 4.6 continuam no extended thinking legado."""
        agent = AIAgent(
            model="claude-haiku-4-5",
            provider="anthropic",
            api_key="test-key",
            max_tokens=8192,
            request_overrides={"reasoning_effort": "high"},
        )
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 6553}
        assert "output_config" not in kwargs

    def test_always_thinking_model_omits_thinking_instead_of_disabling(self):
        """Fable 5 devolve 400 para `thinking: {"type": "disabled"}`."""
        agent = _build_agent("anthropic", "claude-fable-5", reasoning_effort="none")
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert "thinking" not in kwargs
        assert "output_config" not in kwargs

    def test_non_reasoning_model_never_receives_thinking(self):
        agent = _build_agent("anthropic", "claude-3-5-sonnet-legacy", reasoning_effort="high")
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        assert "thinking" not in mock_client.messages.create.call_args.kwargs

    def test_small_max_tokens_no_longer_suppresses_thinking_on_adaptive_models(self):
        """
        O mínimo de 1024 tokens só existia no formato legado por orçamento.
        Com adaptive thinking, max_tokens pequeno não impede o raciocínio.
        """
        # max_tokens=512 -> abaixo do mínimo do formato legado.
        agent = _build_agent("anthropic", "claude-opus-5", reasoning_effort="high")
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "high"}

    def test_legacy_model_with_small_max_tokens_sends_no_thinking(self):
        # max_tokens=512 -> orçamento calculado abaixo do mínimo de 1024 da API.
        agent = _build_agent("anthropic", "claude-haiku-4-5", reasoning_effort="high")
        mock_client = _mock_anthropic_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")

        assert "thinking" not in mock_client.messages.create.call_args.kwargs


class TestAnthropicWirePayload:
    """Testes no nível do transporte HTTP: valida o JSON real enviado à API."""

    @staticmethod
    def _capturing_anthropic(captured: dict):
        """Devolve uma fábrica de cliente Anthropic real com transporte mockado."""
        import anthropic

        # Guarda a classe real antes do patch: dentro da fábrica o nome
        # `anthropic.Anthropic` já aponta para a própria fábrica.
        real_client_cls = anthropic.Anthropic

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            captured["_headers"] = dict(request.headers)
            return httpx.Response(
                200,
                json={
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "model": captured.get("model", "claude-opus-5"),
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                },
            )

        def _factory(**_kwargs):
            return real_client_cls(
                api_key="test-key",
                http_client=httpx.Client(transport=httpx.MockTransport(_handler)),
            )

        return _factory

    def test_flagship_wire_payload_uses_adaptive_thinking_and_effort(self):
        agent = AIAgent(
            model="claude-opus-5",
            provider="anthropic",
            api_key="test-key",
            max_tokens=8192,
            request_overrides={"reasoning_effort": "high", "temperature": 0.3},
        )
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["model"] == "claude-opus-5"
        assert captured["thinking"] == {"type": "adaptive"}
        assert captured["output_config"] == {"effort": "high"}
        # O formato legado devolveria 400 neste modelo.
        assert "budget_tokens" not in json.dumps(captured)
        assert "temperature" not in captured

    def test_system_prompt_marked_for_ephemeral_caching(self):
        """Prompt caching: o system prompt (estatico entre chamadas do mesmo
        agente) deve ir como bloco com cache_control=ephemeral, nao como string
        simples -- senao a API reprocessa/re-cobra o prompt inteiro a cada uma
        das ~25 chamadas por auditoria (docs Anthropic: -90% custo, -85% latencia
        em prefixos repetidos)."""
        agent = AIAgent(
            model="claude-opus-5",
            provider="anthropic",
            api_key="test-key",
            ephemeral_system_prompt="You are a WCAG specialist. Your ONLY job is...",
        )
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["system"] == [
            {
                "type": "text",
                "text": "You are a WCAG specialist. Your ONLY job is...",
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def test_response_schema_merged_into_output_config(self):
        """Structured Outputs (GA desde Claude 4.5+): output_config.format
        com o schema exato -- doc oficial 2026, sem beta header."""
        schema = {"type": "object", "properties": {"issues": {"type": "array"}}}
        agent = AIAgent(
            model="claude-opus-5", provider="anthropic", api_key="test-key",
            response_schema=schema,
        )
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["output_config"] == {"format": {"type": "json_schema", "schema": schema}}

    def test_response_schema_merges_with_output_config_effort(self):
        """output_config.format e output_config.effort (adaptive thinking)
        coexistem no mesmo objeto -- nao pode um sobrescrever o outro."""
        schema = {"type": "object"}
        agent = AIAgent(
            model="claude-opus-5", provider="anthropic", api_key="test-key",
            request_overrides={"reasoning_effort": "high"},
            response_schema=schema,
        )
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["output_config"]["effort"] == "high"
        assert captured["output_config"]["format"] == {"type": "json_schema", "schema": schema}

    def test_response_schema_falls_back_gracefully_when_rejected(self):
        """Se a API rejeitar o schema (ex.: modelo antigo, conta sem GA), o
        engine refaz SEM o schema -- e sem o output_config.effort tambem
        (fallback usa o kwargs original intocado), nunca perde a resposta."""
        import anthropic as anthropic_module

        real_client_cls = anthropic_module.Anthropic
        call_log: list[dict] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            call_log.append(body)
            if "output_config" in body:
                return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "schema not supported"}})
            return httpx.Response(200, json={
                "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
                "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 2},
            })

        def _factory(**_kwargs):
            return real_client_cls(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(_handler)))

        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key", response_schema={"type": "object"})
        with patch("anthropic.Anthropic", _factory):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        assert len(call_log) == 2
        assert "output_config" in call_log[0]
        assert "output_config" not in call_log[1]

    def test_empty_system_prompt_sent_as_plain_string(self):
        """Sem system prompt, nao ha nada para cachear -- deve continuar
        enviando string vazia, nao um bloco com cache_control em branco."""
        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key")
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["system"] == ""

    def test_compaction_api_beta_sent_as_safety_net(self):
        """Compaction API nativa (beta compact-2026-01-12): rede de seguranca
        server-side complementar a compactacao client-side. Deve ir no header
        anthropic-beta + context_management no corpo, com o trigger no minimo
        suportado (50k tokens) -- client-side ja mantem o historico bem abaixo
        disso, entao esta camada so entra em casos extremos."""
        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key")
        captured: dict = {}
        with patch("anthropic.Anthropic", self._capturing_anthropic(captured)):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert captured["_headers"].get("anthropic-beta") == "compact-2026-01-12"
        assert captured["context_management"] == {
            "edits": [{
                "type": "compact_20260112",
                "trigger": {"type": "input_tokens", "value": 50_000},
            }],
        }

    def test_compaction_api_falls_back_gracefully_when_unsupported(self):
        """Se a conta/SDK ainda nao suportar o beta, a API rejeita a chamada
        (ex.: 400) e o engine deve refazer sem o beta/context_management, sem
        propagar a falha para o restante do fluxo."""
        import anthropic as anthropic_module

        real_client_cls = anthropic_module.Anthropic
        call_log: list[dict] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            call_log.append(body)
            if "context_management" in body:
                return httpx.Response(
                    400,
                    json={"type": "error", "error": {"type": "invalid_request_error", "message": "beta not enabled"}},
                )
            return httpx.Response(
                200,
                json={
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                },
            )

        def _factory(**_kwargs):
            return real_client_cls(
                api_key="test-key",
                http_client=httpx.Client(transport=httpx.MockTransport(_handler)),
            )

        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key")
        with patch("anthropic.Anthropic", _factory):
            result = agent._run_anthropic("hello")

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        # Duas chamadas HTTP: a primeira com context_management (rejeitada),
        # a segunda (fallback) sem ele.
        assert len(call_log) == 2
        assert "context_management" in call_log[0]
        assert "context_management" not in call_log[1]


class TestChatCompletionsStructuredOutputs:
    """Ollama/Ollama Cloud (endpoint OpenAI-compat, _run_chat_completions).
    Ollama Cloud documentadamente NAO suporta structured outputs hoje -- a
    tentativa e inofensiva (cai pro fallback), mas o teste prova o fallback
    funciona de ponta a ponta, nao so que nao quebra nada."""

    @staticmethod
    def _mock_chat_completions_client(captured, raise_on_response_format=False):
        mock_client = MagicMock()

        def _create(**kwargs):
            if raise_on_response_format and "response_format" in kwargs:
                raise RuntimeError("response_format not supported")
            captured.update(kwargs)
            message = MagicMock(content="ok", tool_calls=None)
            choice = MagicMock(message=message)
            resp = MagicMock(choices=[choice], usage=None)
            return resp

        mock_client.chat.completions.create.side_effect = _create
        return mock_client

    def test_response_schema_sent_as_response_format(self):
        schema = {"type": "object", "properties": {"issues": {"type": "array"}}}
        agent = AIAgent(model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key", response_schema=schema)
        captured: dict = {}
        with patch("openai.OpenAI", return_value=self._mock_chat_completions_client(captured)):
            result = agent._run_chat_completions("hello")

        assert result["failed"] is False
        assert captured["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "accessibility_issues", "schema": schema, "strict": True},
        }

    def test_response_schema_falls_back_gracefully_when_unsupported(self):
        schema = {"type": "object"}
        agent = AIAgent(model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key", response_schema=schema)
        captured: dict = {}
        client = self._mock_chat_completions_client(captured, raise_on_response_format=True)
        with patch("openai.OpenAI", return_value=client):
            result = agent._run_chat_completions("hello")

        assert result["failed"] is False
        assert result["final_response"] == "ok"
        assert "response_format" not in captured


class TestTokenUsageIsReported:
    """
    Bug real de auditoria: nenhum dos quatro caminhos de provider lia
    `response.usage`, então não existia rastreio de tokens/custo em lugar nenhum
    -- nem para logs, nem para telemetria. Agora cada caminho devolve o usage
    normalizado em result["usage"].
    """

    def test_openai_responses_reports_usage(self):
        agent = _build_agent("openai", "gpt-5.6")
        mock_client = MagicMock()

        def _create(**_kwargs):
            resp = MagicMock()
            resp.status = "completed"
            resp.output_text = "ok"
            resp.output = []
            resp.usage = MagicMock(input_tokens=11, output_tokens=5, total_tokens=16)
            return resp

        mock_client.responses.create.side_effect = _create
        with patch("openai.OpenAI", return_value=mock_client):
            result = agent._run_openai("hello")

        assert result["usage"] == {"input_tokens": 11, "output_tokens": 5, "total_tokens": 16}

    def test_chat_completions_reports_usage_from_prompt_and_completion_tokens(self):
        agent = _build_agent("ollama-cloud", "deepseek-v4-pro:cloud")
        mock_client = _mock_ollama_client(
            lambda **_kwargs: [_ollama_chunk(content="ok", done=True, prompt_eval_count=9, eval_count=4)]
        )
        with patch("ollama.Client", return_value=mock_client):
            result = agent._run_openai("hello")

        assert result["usage"] == {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13}

    def test_anthropic_reports_usage(self):
        agent = _build_agent("anthropic", "claude-opus-5")
        mock_client = _mock_anthropic_client(usage=MagicMock(input_tokens=20, output_tokens=6))
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = agent._run_anthropic("hello")

        assert result["usage"] == {"input_tokens": 20, "output_tokens": 6, "total_tokens": 26}

    def test_gemini_reports_usage_from_usage_metadata(self):
        agent = _build_agent("gemini", "gemini-3.6-flash")
        interaction = MagicMock()
        interaction.id = "interaction-1"
        interaction.status = "completed"
        interaction.steps = [MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])]
        interaction.usage_metadata = MagicMock(
            prompt_token_count=30, candidates_token_count=7, total_token_count=37
        )
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = interaction

        with patch("google.genai.Client", return_value=mock_client):
            result = agent._run_gemini("hello")

        assert result["usage"] == {"input_tokens": 30, "output_tokens": 7, "total_tokens": 37}

    def test_usage_accumulates_across_tool_iterations(self):
        agent = AIAgent(
            model="gpt-5.6",
            provider="openai",
            api_key="test-key",
            max_tokens=512,
            max_iterations=2,
        )
        first = MagicMock()
        first.status = "requires_action"
        first.output_text = ""
        first.output = [MagicMock(type="function_call", call_id="c1", name="missing_tool", arguments="{}")]
        first.usage = MagicMock(input_tokens=10, output_tokens=2, total_tokens=12)
        second = MagicMock()
        second.status = "completed"
        second.output_text = "done"
        second.output = []
        second.usage = MagicMock(input_tokens=5, output_tokens=3, total_tokens=8)

        mock_client = MagicMock()
        mock_client.responses.create.side_effect = [first, second]
        with patch("openai.OpenAI", return_value=mock_client):
            result = agent._run_openai("hello")

        assert result["usage"] == {"input_tokens": 15, "output_tokens": 5, "total_tokens": 20}


class TestNativeWebSearchInParallelWithTavilyExa:
    """Busca web nativa do provider (2026-08-11, pedido do usuário): deve
    rodar EM PARALELO com tavily_search/exa_search (nunca substituindo),
    opt-in por agente (enable_native_web_search), e nunca combinada com
    function tools no Gemini (incompatibilidade documentada da API)."""

    def test_disabled_by_default_openai(self):
        agent = _build_agent("openai", "gpt-5.6")
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")
        tool_types = [t.get("type") for t in captured.get("tools") or []]
        assert "web_search" not in tool_types

    def test_openai_gets_native_web_search_when_enabled(self):
        agent = AIAgent(model="gpt-5.6", provider="openai", api_key="test-key", enable_native_web_search=True)
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")
        tool_types = [t.get("type") for t in captured.get("tools") or []]
        assert "web_search" in tool_types

    def test_xai_gets_native_web_search_when_enabled(self):
        agent = AIAgent(model="grok-4.5", provider="xai", api_key="test-key", enable_native_web_search=True)
        captured = {}
        with patch("openai.OpenAI", return_value=_mock_openai_client(captured)):
            agent._run_openai("hello")
        tool_types = [t.get("type") for t in captured.get("tools") or []]
        assert "web_search" in tool_types

    def test_ollama_cloud_never_gets_native_web_search(self):
        """Ollama nao tem busca nativa boa (motivo original do usuário pra
        usar tavily/exa) -- enable_native_web_search=True nao deve adicionar
        nada pra esse provider mesmo se setado por engano."""
        agent = AIAgent(model="deepseek-v4-pro", provider="ollama-cloud", api_key="test-key", enable_native_web_search=True)
        tools = agent._get_response_tools()
        tool_types = [t.get("type") for t in tools]
        assert "web_search" not in tool_types

    def test_anthropic_gets_native_web_search_when_enabled(self):
        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key", enable_native_web_search=True)
        captured = {}

        def _create(**kwargs):
            captured.update(kwargs)
            text_block = MagicMock(type="text")
            text_block.text = "ok"
            return MagicMock(content=[text_block], usage=None)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _create
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")
        tool_types = [t.get("type") for t in captured.get("tools") or []]
        assert "web_search_20260209" in tool_types

    def test_anthropic_disabled_by_default(self):
        agent = AIAgent(model="claude-opus-5", provider="anthropic", api_key="test-key")
        captured = {}

        def _create(**kwargs):
            captured.update(kwargs)
            text_block = MagicMock(type="text")
            text_block.text = "ok"
            return MagicMock(content=[text_block], usage=None)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _create
        with patch("anthropic.Anthropic", return_value=mock_client):
            agent._run_anthropic("hello")
        tool_types = [t.get("type") for t in (captured.get("tools") or [])]
        assert "web_search_20260209" not in tool_types

    def test_gemini_never_gets_native_web_search_even_when_enabled(self):
        """Doc oficial 2026: Gemini nao suporta combinar googleSearch com
        function tools na mesma chamada -- adicionar quebraria o tool-calling
        normal do agente inteiro, entao NUNCA deve ser adicionado aqui,
        mesmo com enable_native_web_search=True."""
        agent = AIAgent(model="gemini-3.6-flash", provider="gemini", api_key="test-key", enable_native_web_search=True)
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = MagicMock(
            status="completed",
            steps=[MagicMock(type="model_output", content=[MagicMock(type="text", text="ok")])],
        )
        with patch("google.genai.Client", return_value=mock_client):
            agent._run_gemini("hello")
        _, kwargs = mock_client.interactions.create.call_args
        tools_sent = kwargs.get("tools") or []
        tool_types = [t.get("type") for t in tools_sent if isinstance(t, dict)]
        assert "web_search" not in tool_types
        assert "google_search" not in tool_types
