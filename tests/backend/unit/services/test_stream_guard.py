"""Regressão (e2e real 2026-10-08): uma chamada de especialista ficou 29,7 minutos em fluxo, sem erro e sem custo
registrado. A hipótese sustentada pelo código é geração degenerada (espaços e quebras de linha sem fim) sob saída
restrita por esquema JSON; estes testes provam que esse padrão é encerrado e que respostas longas e variadas não são."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.stream_guard import DegenerateStreamError, StreamGuard
from run_agent import AIAgent


def test_a_long_run_of_whitespace_is_a_degenerate_stream():
    guard = StreamGuard("teste", run_limit=50)
    guard.observe("{")
    with pytest.raises(DegenerateStreamError):
        for _ in range(60):
            guard.observe("\n")


def test_the_same_chunk_repeated_is_a_degenerate_stream():
    guard = StreamGuard("teste", run_limit=50)
    with pytest.raises(DegenerateStreamError):
        for _ in range(60):
            guard.observe("ab")


def test_a_long_varied_answer_is_never_cut():
    guard = StreamGuard("teste", run_limit=50)
    for index in range(5000):  # muito mais pedaços do que o limite, mas todos diferentes
        guard.observe(f"palavra{index} ")
    assert guard.chunks == 5000


def test_whitespace_between_real_words_resets_the_run():
    guard = StreamGuard("teste", run_limit=50)
    for _ in range(10):
        for _ in range(40):
            guard.observe(" ")
        guard.observe("texto")  # conteúdo real zera a corrida


def test_a_long_call_leaves_a_diagnostic_line_so_the_next_cause_is_proved_not_guessed(caplog):
    guard = StreamGuard("ollama/kimi", run_limit=1000, interval=0.0)
    with caplog.at_level(logging.WARNING, logger="backend.src.services.stream_guard"):
        guard.observe("olá")
    assert "chamada longa em andamento" in caplog.text
    assert "ollama/kimi" in caplog.text


def _chunk(content="", thinking=None, done=False):
    chunk = MagicMock()
    chunk.message.content = content
    chunk.message.thinking = thinking
    chunk.message.tool_calls = None
    chunk.done = done
    chunk.prompt_eval_count = None
    chunk.eval_count = None
    return chunk


def test_the_agent_gives_up_on_a_stream_that_only_emits_whitespace_instead_of_hanging(caplog):
    agent = AIAgent(model="kimi-k2.7-code", provider="ollama-cloud", api_key="x", max_iterations=1, enabled_toolsets=[])
    client = MagicMock()
    client.chat.side_effect = lambda **_k: iter([_chunk("{")] + [_chunk(" \n") for _ in range(5000)] + [_chunk("}", done=True)])
    with patch("ollama.Client", return_value=client), patch.object(AIAgent, "_resolve_auto_fallback", return_value=None):
        result = agent.run_conversation("hello")
    assert result["failed"] is True
    assert "fluxo degenerado" in caplog.text  # a causa fica provada no log
    assert client.chat.call_count == 1  # não refez a mesma geração por outro endpoint
