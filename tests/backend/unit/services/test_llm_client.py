import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services import agent_hooks, batch_collector
from backend.src.services.llm_client import call_llm, call_llm_structured, extract_json_array
from backend.src.services.response_cache import clear_cache as clear_response_cache


def setup_function():
    clear_response_cache()
    agent_hooks.clear_all_hooks()


class TestExtractJsonArrayUnwrapsRedundantWrapper:
    """Achado real (2026-08-10, validação E2E com a API nativa do Ollama): o
    modelo às vezes envolve o array esperado num wrapper redundante --
    `[{"issues": []}]` em vez de `[]` -- sobretudo ao expressar "nenhum
    problema encontrado". Sem desembrulhar, `AccessibilityIssue(**{"issues": []})`
    falhava com "Field required" em todos os campos, quebrando o agente inteiro
    (reproduzido ao vivo: spatial_3d_xr falhou exatamente assim)."""

    def test_unwraps_single_element_single_key_list_wrapper(self):
        assert extract_json_array('[{"issues": []}]') == []

    def test_unwraps_wrapper_with_real_items_inside(self):
        assert extract_json_array('[{"issues": [{"id": "p-1"}]}]') == [{"id": "p-1"}]

    def test_does_not_unwrap_a_real_multi_item_array(self):
        """Um array de verdade com múltiplos issues (cada um um dict
        multi-campo) não deve ser confundido com o wrapper redundante."""
        real_array = [{"id": "p-1", "severity": "high"}, {"id": "p-2", "severity": "low"}]
        assert extract_json_array(json.dumps(real_array)) == real_array

    def test_does_not_unwrap_single_item_with_multiple_keys(self):
        """Um array com 1 item só, mas que tem múltiplos campos (um issue de
        verdade, não um wrapper), não deve ser desembrulhado."""
        single_real_issue = [{"id": "p-1", "severity": "high", "criterion": "1.1.1"}]
        assert extract_json_array(json.dumps(single_real_issue)) == single_real_issue

    def test_top_level_dict_with_list_value_still_works(self):
        """Regressão: o caso já suportado (dict no topo, não array) continua
        funcionando -- não é o mesmo código-path do wrapper-dentro-de-array."""
        assert extract_json_array('{"issues": [{"id": "p-1"}]}') == [{"id": "p-1"}]


class TestReasoningEffortForTradeoff:
    """Achado real (2026-08-11, a pedido do usuário + pesquisa ARES/Claude 4.6
    effort routing): antes desta função, TODA chamada do projeto desligava o
    raciocínio incondicionalmente (reasoning_effort="none" fixo em call_llm),
    mesmo quando o classificador de complexidade real já tinha marcado a
    tarefa como precisando de mais cuidado -- só o modelo mudava com o
    tradeoff, nunca o esforço de pensamento daquele modelo. Trava aqui o
    mapeamento 0-10 -> nível de esforço."""

    def setup_method(self):
        # `setup_function` (nível de módulo) não se aplica a métodos dentro de
        # uma classe -- sem isto, os testes desta classe reaproveitam cache de
        # resposta entre si (mesmo system_prompt/user_prompt "s"/"u"),
        # fazendo AIAgent nunca ser chamado de fato na segunda rodada.
        clear_response_cache()

    def test_extremes_preserve_historical_behavior(self):
        from backend.src.services.llm_client import _reasoning_effort_for_tradeoff
        assert _reasoning_effort_for_tradeoff(10) == "none"
        assert _reasoning_effort_for_tradeoff(9) == "none"
        assert _reasoning_effort_for_tradeoff(8) == "none"

    def test_mid_range_maps_to_low_and_medium(self):
        from backend.src.services.llm_client import _reasoning_effort_for_tradeoff
        assert _reasoning_effort_for_tradeoff(7) == "low"
        assert _reasoning_effort_for_tradeoff(6) == "low"
        assert _reasoning_effort_for_tradeoff(5) == "medium"
        assert _reasoning_effort_for_tradeoff(3) == "medium"

    def test_low_tradeoff_favors_quality_with_high_effort(self):
        from backend.src.services.llm_client import _reasoning_effort_for_tradeoff
        assert _reasoning_effort_for_tradeoff(2) == "high"
        assert _reasoning_effort_for_tradeoff(0) == "high"

    @pytest.mark.asyncio
    async def test_call_llm_uses_high_effort_when_complexity_router_favors_quality(self):
        """Tradeoff baixo (classificador real marcou a tarefa como
        complexa/precisando de qualidade) -> reasoning_effort='high' chega de
        verdade no AIAgent, não mais 'none' fixo."""
        from backend.src.services import complexity_router

        mock_res = {"final_response": "ok", "failed": False}
        complexity_router.set_current_tradeoff(0)
        try:
            with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
                inst = MagicMock()
                inst.run_conversation.return_value = mock_res
                MockAgentClass.return_value = inst
                await call_llm(system_prompt="s", user_prompt="u", agent_label="aria_specialist")
            assert MockAgentClass.call_args.kwargs["request_overrides"]["reasoning_effort"] == "high"
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    @pytest.mark.asyncio
    async def test_call_llm_uses_none_effort_when_complexity_router_favors_cost(self):
        """Tradeoff alto (classificador real marcou a tarefa como simples,
        favorece custo) -> reasoning_effort='none', preservando o
        comportamento histórico só onde ele faz sentido de verdade."""
        from backend.src.services import complexity_router

        mock_res = {"final_response": "ok", "failed": False}
        complexity_router.set_current_tradeoff(9)
        try:
            with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
                inst = MagicMock()
                inst.run_conversation.return_value = mock_res
                MockAgentClass.return_value = inst
                await call_llm(system_prompt="s", user_prompt="u", agent_label="operability")
            assert MockAgentClass.call_args.kwargs["request_overrides"]["reasoning_effort"] == "none"
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    @pytest.mark.asyncio
    async def test_call_llm_classifier_label_always_uses_none_regardless_of_tradeoff(self):
        """O classificador de complexidade em si (agent_label='classifier') é
        sempre barato por design -- não deve herdar um tradeoff baixo (favor
        qualidade) que a PÁGINA analisada recebeu; mesma regra já aplicada
        pro tier 'fast' em model_router.py."""
        from backend.src.services import complexity_router

        mock_res = {"final_response": "ok", "failed": False}
        complexity_router.set_current_tradeoff(0)  # complexidade alta classificada pra pagina
        try:
            with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
                inst = MagicMock()
                inst.run_conversation.return_value = mock_res
                MockAgentClass.return_value = inst
                await call_llm(system_prompt="s", user_prompt="u", agent_label="classifier")
            assert MockAgentClass.call_args.kwargs["request_overrides"]["reasoning_effort"] == "none"
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)


@pytest.mark.asyncio
async def test_call_llm_via_hermes():
    """
    Testa se call_llm instancia e executa corretamente o AIAgent do Hermes,
    passando os prompts de sistema e usuário apropriados.
    """
    mock_res = {
        "final_response": "Test response content from Hermes",
        "failed": False,
        "completed": True,
    }

    with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_conversation.return_value = mock_res
        MockAgentClass.return_value = mock_agent_instance

        result = await call_llm(
            system_prompt="Test system prompt",
            user_prompt="Test user prompt",
            temperature=0.1,
        )

        # Verifica se o retorno final corresponde a resposta do Hermes
        assert result == "Test response content from Hermes"

        # Verifica se a classe AIAgent foi instanciada com os parametros corretos
        MockAgentClass.assert_called_once()
        kwargs = MockAgentClass.call_args[1]
        assert kwargs["max_iterations"] == 1
        assert kwargs["quiet_mode"] is True

        # temperatura agora chega ao modelo via request_overrides (antes era ignorada).
        # reasoning_effort="medium" -- tradeoff default (3) via
        # _reasoning_effort_for_tradeoff, não mais "none" fixo pra toda chamada
        # (achado real 2026-08-11: nenhuma chamada do projeto recebia esforço
        # extra de raciocínio antes desta mudança, ver llm_client.py).
        assert kwargs["request_overrides"] == {
            "temperature": 0.1,
            "reasoning_effort": "medium",
        }

        # leaf subagent Hermes: prompt focado via ephemeral_system_prompt e SEM tools
        assert kwargs["ephemeral_system_prompt"] == "Test system prompt"
        assert kwargs["enabled_toolsets"] == []

        # run_conversation recebe user_message + task_id isolado (sem system_message)
        mock_agent_instance.run_conversation.assert_called_once()
        run_kwargs = mock_agent_instance.run_conversation.call_args[1]
        assert run_kwargs["user_message"] == "Test user prompt"
        assert run_kwargs["task_id"].startswith("a11y-")
        assert "system_message" not in run_kwargs


@pytest.mark.asyncio
async def test_call_llm_fires_pre_and_post_llm_call_hooks_on_success():
    """agent_hooks: call_llm dispara PRE_LLM_CALL e POST_LLM_CALL(success=True)
    para qualquer observador plugável registrado, sem precisar de parametro
    novo em call_llm nem em quem o chama."""
    pre_calls = []
    post_calls = []
    agent_hooks.register_hook(agent_hooks.PRE_LLM_CALL, lambda *a: pre_calls.append(a))
    agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, lambda *a: post_calls.append(a))

    mock_res = {"final_response": "ok", "failed": False, "completed": True}
    with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_conversation.return_value = mock_res
        MockAgentClass.return_value = mock_agent_instance
        await call_llm(system_prompt="s", user_prompt="u", agent_label="perceiver")

    assert len(pre_calls) == 1
    assert len(post_calls) == 1
    *_, success, duration_ms = post_calls[0]
    assert success is True
    assert duration_ms >= 0


@pytest.mark.asyncio
async def test_call_llm_fires_on_error_hook_on_failure():
    agent_hooks.clear_all_hooks()
    error_calls = []
    agent_hooks.register_hook(agent_hooks.ON_ERROR, lambda *a: error_calls.append(a))

    mock_res = {"failed": True, "error": "provider unreachable"}
    with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_conversation.return_value = mock_res
        MockAgentClass.return_value = mock_agent_instance
        with pytest.raises(Exception, match="provider unreachable"):
            await call_llm(system_prompt="s", user_prompt="u")

    assert len(error_calls) == 1


@pytest.mark.asyncio
async def test_call_llm_hook_failure_does_not_break_the_call():
    """Um hook plugável quebrado nunca pode impedir a resposta real de voltar."""
    agent_hooks.clear_all_hooks()

    def bad_hook(*a):
        raise RuntimeError("hook de terceiro quebrado")

    agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, bad_hook)

    mock_res = {"final_response": "ok despite bad hook", "failed": False, "completed": True}
    with patch("backend.src.services.llm_client.AIAgent") as MockAgentClass:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_conversation.return_value = mock_res
        MockAgentClass.return_value = mock_agent_instance
        result = await call_llm(system_prompt="s", user_prompt="u")

    assert result == "ok despite bad hook"


@pytest.mark.asyncio
async def test_call_llm_forwards_fallback_model_when_configured():
    """
    Quando o failover esta configurado em settings, call_llm deve repassar
    fallback_model ao AIAgent. Sem configuração, deve ser None (sem failover).
    """
    mock_res = {"final_response": "ok", "failed": False, "completed": True}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_conversation.return_value = mock_res
        MockAgentClass.return_value = mock_agent_instance

        settings = MagicMock()
        settings.llm_model = "gpt-5.5"
        settings.llm_api_key = "sk-test"
        settings.llm_provider = "openai"
        settings.llm_base_url = None
        settings.build_fallback_model.return_value = {
            "provider": "openrouter",
            "model": "meta-llama/llama-3.3-70b-instruct",
        }
        mock_get_settings.return_value = settings

        await call_llm(system_prompt="s", user_prompt="u")

        kwargs = MockAgentClass.call_args[1]
        assert kwargs["fallback_model"] == {
            "provider": "openrouter",
            "model": "meta-llama/llama-3.3-70b-instruct",
        }


@pytest.mark.asyncio
async def test_call_llm_retries_without_temperature_when_provider_rejects():
    """Provider recusa 'temperature' (modelo de reasoning) -> refaz UMA vez sem ela.

    Usa o detector REAL do Hermes (`_provider_rejected_temperature`) sobre uma
    mensagem de erro 400 tipica, garantindo o self-heal de ponta a ponta.
    """
    fail_res = {
        "final_response": "",
        "failed": True,
        "error": "Unsupported parameter: 'temperature' is not supported with this model",
    }
    ok_res = {"final_response": "resposta sem temperatura", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        settings = MagicMock()
        settings.llm_model = "gpt-5"  # concreto -> sem resolucao "Alto" (sem rede)
        settings.llm_api_key = "sk-test"
        settings.llm_provider = "openai"
        settings.llm_base_url = None
        settings.build_fallback_model.return_value = None
        mock_get_settings.return_value = settings

        inst = MagicMock()
        inst.run_conversation.side_effect = [fail_res, ok_res]
        MockAgentClass.return_value = inst

        result = await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert result == "resposta sem temperatura"
    # Duas instanciacoes: 1a COM temperature, 2a SEM temperature (self-heal)
    assert MockAgentClass.call_count == 2
    assert MockAgentClass.call_args_list[0].kwargs["request_overrides"] == {
        "temperature": 0.2,
        "reasoning_effort": "medium",
    }
    assert MockAgentClass.call_args_list[1].kwargs["request_overrides"] == {
        "reasoning_effort": "medium",
    }


@pytest.mark.asyncio
async def test_call_llm_retries_without_reasoning_effort_when_provider_rejects():
    """Provider recusa controle de thinking -> refaz sem reasoning_effort."""
    fail_res = {
        "final_response": "",
        "failed": True,
        "error": "Unsupported parameter: 'reasoning_effort' is not supported",
    }
    ok_res = {"final_response": "[]", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        settings = MagicMock()
        settings.llm_model = "gpt-4o"
        settings.llm_api_key = "sk-test"
        settings.llm_provider = "openai"
        settings.llm_base_url = None
        settings.build_fallback_model.return_value = None
        mock_get_settings.return_value = settings

        inst = MagicMock()
        inst.run_conversation.side_effect = [fail_res, ok_res]
        MockAgentClass.return_value = inst

        result = await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert result == "[]"
    assert MockAgentClass.call_count == 2
    assert MockAgentClass.call_args_list[0].kwargs["request_overrides"] == {
        "temperature": 0.2,
        "reasoning_effort": "medium",
    }
    assert MockAgentClass.call_args_list[1].kwargs["request_overrides"] == {
        "temperature": 0.2,
    }


@pytest.mark.asyncio
async def test_call_llm_does_not_retry_on_non_temperature_error():
    """Falha que NÃO e rejeicao de temperatura -> sem retry, levanta o erro."""
    fail_res = {"final_response": "", "failed": True, "error": "401 Invalid API Key"}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        settings = MagicMock()
        settings.llm_model = "gpt-4o"
        settings.llm_api_key = "sk-test"
        settings.llm_provider = "openai"
        settings.llm_base_url = None
        settings.build_fallback_model.return_value = None
        mock_get_settings.return_value = settings

        inst = MagicMock()
        inst.run_conversation.return_value = fail_res
        MockAgentClass.return_value = inst

        with pytest.raises(Exception, match="chave de API"):
            await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert MockAgentClass.call_count == 1  # sem retry


@pytest.mark.asyncio
async def test_call_llm_retries_empty_terminal_response_with_json_recovery_prompt():
    empty_res = {"final_response": "(empty)", "failed": False}
    ok_res = {"final_response": "[]", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        settings = MagicMock()
        settings.llm_model = "gpt-4o"
        settings.llm_api_key = "sk-test"
        settings.llm_provider = "openai"
        settings.llm_base_url = None
        settings.build_fallback_model.return_value = None
        mock_get_settings.return_value = settings

        inst = MagicMock()
        inst.run_conversation.side_effect = [empty_res, ok_res]
        MockAgentClass.return_value = inst

        result = await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert result == "[]"
    assert MockAgentClass.call_count == 2
    assert "RECOVERY MODE" in MockAgentClass.call_args_list[1].kwargs["ephemeral_system_prompt"]
    retry_kwargs = inst.run_conversation.call_args_list[1].kwargs
    assert "valid JSON only" in retry_kwargs["user_message"]


def test_provider_rejected_temperature_detector():
    """O detector reusa a lógica do Hermes: pega rejeicao de temperatura, ignora o resto."""
    from backend.src.services.llm_client import _provider_rejected_temperature

    assert _provider_rejected_temperature(
        "Unsupported parameter: 'temperature' is not supported with this model"
    ) is True
    assert _provider_rejected_temperature("Connection reset by peer") is False
    assert _provider_rejected_temperature("") is False


def _mock_settings_with_cache(enabled: bool) -> MagicMock:
    settings = MagicMock()
    settings.llm_model = "gpt-4o"
    settings.llm_api_key = "sk-test"
    settings.llm_provider = "openai"
    settings.llm_base_url = None
    settings.build_fallback_model.return_value = None
    settings.a11y_response_cache_enabled = enabled
    settings.a11y_response_cache_ttl_seconds = 60.0
    return settings


@pytest.mark.asyncio
async def test_call_llm_second_identical_call_hits_cache_no_second_agent_call():
    ok_res = {"final_response": "resposta cacheavel", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_get_settings.return_value = _mock_settings_with_cache(enabled=True)
        inst = MagicMock()
        inst.run_conversation.return_value = ok_res
        MockAgentClass.return_value = inst

        first = await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)
        second = await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert first == second == "resposta cacheavel"
    assert MockAgentClass.call_count == 1  # 2a chamada veio do cache, sem instanciar AIAgent


@pytest.mark.asyncio
async def test_call_llm_cache_disabled_calls_agent_every_time():
    ok_res = {"final_response": "sem cache", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_get_settings.return_value = _mock_settings_with_cache(enabled=False)
        inst = MagicMock()
        inst.run_conversation.return_value = ok_res
        MockAgentClass.return_value = inst

        await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)
        await call_llm(system_prompt="s", user_prompt="u", temperature=0.2)

    assert MockAgentClass.call_count == 2


@pytest.mark.asyncio
async def test_call_llm_never_caches_when_toolsets_present():
    """Turnos com tools (chat) nunca cacheiam -- mesmo escopo do response_schema."""
    ok_res = {"final_response": "resposta de chat", "failed": False}

    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_get_settings.return_value = _mock_settings_with_cache(enabled=True)
        inst = MagicMock()
        inst.run_conversation.return_value = ok_res
        MockAgentClass.return_value = inst

        await call_llm(
            system_prompt="s", user_prompt="u", temperature=0.2, toolsets=["a11y_tools"]
        )
        await call_llm(
            system_prompt="s", user_prompt="u", temperature=0.2, toolsets=["a11y_tools"]
        )

    assert MockAgentClass.call_count == 2  # sem cache-hit: tem toolsets


@pytest.mark.asyncio
async def test_call_llm_records_request_and_returns_sentinel_when_collecting():
    """Batch Inference (ver batch_collector.py): em modo de coleta, call_llm
    nunca liga pro provider -- grava a chamada e devolve o sentinel "[]"."""
    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_get_settings.return_value = _mock_settings_with_cache(enabled=True)

        list_token, pending = batch_collector.bind_pending_list()
        active_token = batch_collector.enable()
        try:
            result = await call_llm(system_prompt="s", user_prompt="u", agent_label="perceiver")
        finally:
            batch_collector.disable(active_token)
            batch_collector.unbind_pending_list(list_token)

    assert result == "[]"
    MockAgentClass.assert_not_called()  # nunca ligou pro provider
    assert len(pending) == 1
    assert pending[0].system_prompt == "s"
    assert pending[0].user_prompt == "u"


@pytest.mark.asyncio
async def test_call_llm_collection_mode_never_applies_to_tools_turns():
    """Mesmo escopo do response_schema/response_cache: chat com tools nunca
    entra em modo de coleta, mesmo que o interruptor global esteja ligado."""
    ok_res = {"final_response": "resposta de chat", "failed": False}
    with (
        patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
        patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
    ):
        mock_get_settings.return_value = _mock_settings_with_cache(enabled=True)
        inst = MagicMock()
        inst.run_conversation.return_value = ok_res
        MockAgentClass.return_value = inst

        active_token = batch_collector.enable()
        try:
            result = await call_llm(system_prompt="s", user_prompt="u", toolsets=["a11y_tools"])
        finally:
            batch_collector.disable(active_token)

    assert result == "resposta de chat"
    MockAgentClass.assert_called_once()  # ligou pro provider normalmente


@pytest.mark.asyncio
async def test_call_llm_structured_retries_then_succeeds():
    """Output invalido na 1a tentativa -> repair retry -> 2a valida e constroi o objeto."""
    responses = ["isto não e json", '{"x": 1}']
    with patch("backend.src.services.llm_client.call_llm", new=AsyncMock(side_effect=responses)) as m:
        result = await call_llm_structured("sys", "user", build=lambda raw: json.loads(raw))
    assert result == {"x": 1}
    assert m.await_count == 2
    # a 2a chamada recebe o prompt corretivo
    assert "previous response was not valid JSON" in m.await_args.kwargs["user_prompt"]


@pytest.mark.asyncio
async def test_call_llm_structured_raises_after_all_attempts():
    """Se todas as tentativas falharem, levanta a ultima excecao de parse."""
    with patch("backend.src.services.llm_client.call_llm", new=AsyncMock(return_value="nope")) as m, pytest.raises(json.JSONDecodeError):
        await call_llm_structured("sys", "user", build=lambda raw: json.loads(raw), attempts=2)


class TestStructuredOutputFallbackChain:
    """Achado real (auditoria docs/auditoria-prompt-caching-structured-output-
    2026-08-26.md): antes, quando o roteamento caia no fallback do OpenCode Go
    (Structured Outputs garantidos), so havia UM modelo (gpt-5.6-luna) -- se
    ele estivesse fora do ar, call_llm falhava direto, sem proximo da fila.
    Agora tenta cada modelo verificado da cadeia em ordem antes de desistir."""

    def _make_agent_factory(self, model_to_result: dict[str, dict], calls: list):
        def _factory(**kwargs):
            calls.append((kwargs.get("provider"), kwargs.get("model")))
            inst = MagicMock()
            inst.run_conversation.return_value = model_to_result[kwargs["model"]]
            return inst
        return _factory

    @pytest.mark.asyncio
    async def test_falls_back_to_next_model_when_first_fails(self):
        fail_res = {"final_response": "", "failed": True, "error": "503 Service Unavailable"}
        ok_res = {"final_response": '{"issues": []}', "failed": False}
        calls: list = []

        with (
            patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
            patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
            patch(
                "backend.src.services.model_router.resolve_model_and_provider",
                return_value=("opencode-go", "gpt-5.6-luna"),
            ),
            patch(
                "backend.src.services.model_router.resolve_structured_output_chain",
                return_value=["gpt-5.6-luna", "kimi-k2.6"],
            ),
            patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "test-key"}, clear=False),
        ):
            mock_get_settings.return_value = _mock_settings_with_cache(enabled=False)
            MockAgentClass.side_effect = self._make_agent_factory(
                {"gpt-5.6-luna": fail_res, "kimi-k2.6": ok_res}, calls
            )

            result = await call_llm(system_prompt="s", user_prompt="u", response_schema={"type": "object"})

        assert result == '{"issues": []}'
        assert calls == [("opencode-go", "gpt-5.6-luna"), ("opencode-go", "kimi-k2.6")]

    @pytest.mark.asyncio
    async def test_raises_only_after_every_model_in_chain_fails(self):
        fail_luna = {"final_response": "", "failed": True, "error": "primeiro modelo indisponivel"}
        fail_kimi = {"final_response": "", "failed": True, "error": "segundo modelo tambem indisponivel"}
        calls: list = []

        with (
            patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
            patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
            patch(
                "backend.src.services.model_router.resolve_model_and_provider",
                return_value=("opencode-go", "gpt-5.6-luna"),
            ),
            patch(
                "backend.src.services.model_router.resolve_structured_output_chain",
                return_value=["gpt-5.6-luna", "kimi-k2.6"],
            ),
            patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "test-key"}, clear=False),
        ):
            mock_get_settings.return_value = _mock_settings_with_cache(enabled=False)
            MockAgentClass.side_effect = self._make_agent_factory(
                {"gpt-5.6-luna": fail_luna, "kimi-k2.6": fail_kimi}, calls
            )

            with pytest.raises(Exception, match="indisponivel"):
                await call_llm(system_prompt="s", user_prompt="u", response_schema={"type": "object"})

        assert calls == [("opencode-go", "gpt-5.6-luna"), ("opencode-go", "kimi-k2.6")]

    @pytest.mark.asyncio
    async def test_single_model_when_chain_unavailable_behaves_like_before(self):
        """Sem cadeia configurada (resolve_structured_output_chain vazia -- ex.:
        OPENCODE_GO_API_KEY ausente), mantem o comportamento antigo: um unico
        candidato, o par ja resolvido por resolve_model_and_provider."""
        ok_res = {"final_response": '{"issues": []}', "failed": False}
        calls: list = []

        with (
            patch("backend.src.services.llm_client.AIAgent") as MockAgentClass,
            patch("backend.src.services.llm_client.get_settings") as mock_get_settings,
            patch(
                "backend.src.services.model_router.resolve_model_and_provider",
                return_value=("opencode-go", "gpt-5.6-luna"),
            ),
            patch(
                "backend.src.services.model_router.resolve_structured_output_chain",
                return_value=[],
            ),
        ):
            mock_get_settings.return_value = _mock_settings_with_cache(enabled=False)
            MockAgentClass.side_effect = self._make_agent_factory({"gpt-5.6-luna": ok_res}, calls)

            result = await call_llm(system_prompt="s", user_prompt="u", response_schema={"type": "object"})

        assert result == '{"issues": []}'
        assert calls == [("opencode-go", "gpt-5.6-luna")]
