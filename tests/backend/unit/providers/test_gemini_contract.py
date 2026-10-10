"""Contrato do Gemini contra uma chamada REAL gravada (scripts/record_provider_contract.py).

Mock inventado não prova integração (regra 11): o leitor do fluxo quebrou em produção porque os testes usavam eventos que a API
já não enviava. Estes testes reproduzem exatamente o que o Gemini devolveu quando foi gravado. Se a API mudar, o modo --check do
gravador acusa e a gravação é refeita junto com o leitor."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from run_agent import AIAgent

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "providers" / "gemini" / "contract.json"
RECORDING = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Tipos de evento que o leitor conhece. Um tipo novo na gravação sem estar aqui é mudança de formato a tratar.
HANDLED_EVENT_TYPES = {
    "interaction.created", "interaction.status_update", "step.start", "step.delta", "step.stop", "interaction.completed",
}


def as_object(value):
    """Dicionário gravado vira objeto com atributos, como o SDK entrega."""
    if isinstance(value, dict):
        # `arguments` chega como dicionário comum no SDK; os demais blocos são objetos com atributos.
        return SimpleNamespace(**{key: (item if key == "arguments" else as_object(item)) for key, item in value.items()})
    if isinstance(value, list):
        return [as_object(item) for item in value]
    return value


def events_of(scenario: str):
    return [as_object(event) for event in RECORDING["scenarios"][scenario]["events"]]


def stored_of(scenario: str):
    return as_object(RECORDING["scenarios"][scenario]["stored_interaction"])


def recorded_text(scenario: str) -> str:
    steps = RECORDING["scenarios"][scenario]["stored_interaction"]["steps"]
    return "".join(
        part["text"] for step in steps if step["type"] == "model_output" for part in step["content"] if part["type"] == "text"
    )


def agent(**kwargs) -> AIAgent:
    return AIAgent(model=RECORDING["model"], provider="gemini", api_key="k", max_iterations=3, **kwargs)


def test_every_recorded_event_type_is_one_the_reader_handles():
    seen = {event["event_type"] for scenario in RECORDING["scenarios"].values() for event in scenario["events"]}
    assert seen <= HANDLED_EVENT_TYPES, f"o Gemini enviou eventos novos: {sorted(seen - HANDLED_EVENT_TYPES)}"


def test_the_recording_never_contains_a_credential():
    assert "AIza" not in FIXTURE.read_text(encoding="utf-8")


def test_text_stream_reaches_the_user_and_the_final_answer_with_measured_cost():
    received = []
    reader = agent()
    reader.stream_delta_callback = received.append
    client = MagicMock()
    client.interactions.create.return_value = iter(events_of("text"))
    client.interactions.get.return_value = stored_of("text")
    with patch("google.genai.Client", return_value=client):
        result = reader._run_gemini("o que é contraste?")
    assert result["failed"] is False
    assert "".join(received) == recorded_text("text")
    assert result["final_response"] == recorded_text("text")
    usage = RECORDING["scenarios"]["text"]["stored_interaction"]["usage"]
    assert result["usage"]["input_tokens"] == usage["total_input_tokens"] > 0
    assert result["usage"]["output_tokens"] == usage["total_output_tokens"] > 0


def test_tool_call_round_trip_executes_the_tool_with_the_recorded_arguments_and_then_answers():
    reader = agent()
    reader.stream_delta_callback = lambda _t: None
    call = RECORDING["scenarios"]["tool_call"]["stored_interaction"]["steps"][-1]
    assert call["type"] == "function_call"
    client = MagicMock()
    client.interactions.create.side_effect = [iter(events_of("tool_call")), iter(events_of("text"))]
    client.interactions.get.side_effect = [stored_of("tool_call"), stored_of("text")]
    with (
        patch("google.genai.Client", return_value=client),
        patch.object(reader, "_execute_tool_calls", return_value={call["id"]: "Sol, 30 graus"}) as run_tools,
    ):
        result = reader._run_gemini("clima em Recife")
    assert result["failed"] is False
    assert result["final_response"] == recorded_text("text")
    executed = run_tools.call_args.args[0]
    assert len(executed) == 1
    followup = client.interactions.create.call_args_list[1].kwargs
    assert followup["input"][0]["call_id"] == call["id"]
    assert followup["previous_interaction_id"] == RECORDING["scenarios"]["tool_call"]["stored_interaction"]["id"]


@pytest.mark.parametrize("scenario", ["text", "tool_call"])
def test_a_stream_cut_before_the_completed_event_is_a_failure_not_a_silent_empty_answer(scenario):
    reader = agent()
    reader.stream_delta_callback = lambda _t: None
    client = MagicMock()
    client.interactions.create.return_value = iter(events_of(scenario)[:-1])
    with patch("google.genai.Client", return_value=client):
        result = reader._run_gemini("oi")
    assert result["failed"] is True
