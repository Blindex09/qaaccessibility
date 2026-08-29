"""Testes do modo de coleta pra Batch Inference (batch_collector.py)."""

from backend.src.services import batch_collector


def test_not_collecting_by_default():
    assert batch_collector.is_collecting() is False


def test_enable_disable_toggles_is_collecting():
    token = batch_collector.enable()
    try:
        assert batch_collector.is_collecting() is True
    finally:
        batch_collector.disable(token)
    assert batch_collector.is_collecting() is False


def test_record_noop_without_bound_list():
    # Sem bind_pending_list, record() nao deve levantar nem guardar nada visivel.
    batch_collector.record("key", "openai", "gpt-5.6", "sys", "user")


def test_bind_pending_list_accumulates_records():
    token, pending = batch_collector.bind_pending_list()
    try:
        batch_collector.record("k1", "openai", "gpt-5.6", "s1", "u1")
        batch_collector.record("k2", "anthropic", "claude-opus-5", "s2", "u2")
        assert len(pending) == 2
        assert pending[0].cache_key == "k1"
        assert pending[0].provider == "openai"
        assert pending[1].system_prompt == "s2"
    finally:
        batch_collector.unbind_pending_list(token)


def test_pending_list_persists_across_multiple_enable_disable_cycles():
    """Cenario real: a rota faz bind UMA vez antes do loop de páginas; cada
    página chama orchestrate() (que liga/desliga _active em torno do gather)
    -- tudo tem que cair na MESMA lista."""
    list_token, pending = batch_collector.bind_pending_list()
    try:
        for page_num in range(3):
            active_token = batch_collector.enable()
            try:
                batch_collector.record(f"page-{page_num}", "gemini", "gemini-3.6-flash", "s", "u")
            finally:
                batch_collector.disable(active_token)
        assert len(pending) == 3
        assert [r.cache_key for r in pending] == ["page-0", "page-1", "page-2"]
    finally:
        batch_collector.unbind_pending_list(list_token)


def test_unbind_removes_the_list_record_becomes_noop_again():
    token, pending = batch_collector.bind_pending_list()
    batch_collector.unbind_pending_list(token)
    batch_collector.record("k", "openai", "m", "s", "u")
    assert pending == []  # a lista antiga nao recebe mais nada apos o unbind
