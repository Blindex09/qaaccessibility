import time

from backend.src.services.response_cache import (
    ResponseCache,
    clear_cache,
    get_cached_response,
    make_cache_key,
    set_cached_response,
)


def setup_function():
    clear_cache()


def test_make_cache_key_is_stable_and_order_sensitive():
    key1 = make_cache_key("a", "b", "c")
    key2 = make_cache_key("a", "b", "c")
    key3 = make_cache_key("a", "c", "b")
    assert key1 == key2
    assert key1 != key3


def test_set_then_get_returns_cached_value():
    key = make_cache_key("openai", "gpt-5", "sys", "user")
    set_cached_response(key, "cached content", ttl_seconds=60)
    assert get_cached_response(key) == "cached content"


def test_get_miss_returns_none():
    assert get_cached_response(make_cache_key("nope")) is None


def test_entry_expires_after_ttl():
    cache = ResponseCache()
    cache.set("k", "v", ttl_seconds=0.01)
    time.sleep(0.02)
    assert cache.get("k") is None


def test_clear_cache_removes_all_entries():
    key = make_cache_key("a")
    set_cached_response(key, "v", ttl_seconds=60)
    clear_cache()
    assert get_cached_response(key) is None


def test_lru_eviction_when_max_entries_exceeded():
    cache = ResponseCache(max_entries=2)
    cache.set("k1", "v1", ttl_seconds=60)
    cache.set("k2", "v2", ttl_seconds=60)
    cache.set("k3", "v3", ttl_seconds=60)
    assert len(cache) == 2
    assert cache.get("k1") is None  # evicted (oldest, never re-touched)
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"
