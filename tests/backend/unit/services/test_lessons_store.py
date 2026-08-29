import json
import os

import pytest

from backend.src.services import lessons_store


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Isola cada teste com um arquivo de store proprio -- nunca toca o
    registro real em disco nem vaza estado entre testes."""
    fake_path = str(tmp_path / "false_positive_patterns.json")
    monkeypatch.setattr(lessons_store, "_STORE_PATH", fake_path)
    yield fake_path


class TestElementSignature:
    def test_extracts_tag_role_and_class(self):
        sig = lessons_store._element_signature('<div role="button" class="btn primary">')
        assert sig == "div|role=button|class=btn"

    def test_tag_only_when_no_role_or_class(self):
        sig = lessons_store._element_signature("<img>")
        assert sig == "img"

    def test_unknown_when_no_tag_found(self):
        sig = lessons_store._element_signature("some text without a tag")
        assert sig == "unknown"


class TestRecordAndSurfacePatterns:
    def test_pattern_below_min_count_is_not_surfaced(self):
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "decorative icon")
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "decorative icon")
        patterns = lessons_store.get_known_false_positive_patterns(min_count=3)
        assert patterns == []

    def test_pattern_reaching_min_count_is_surfaced(self):
        for _ in range(3):
            lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "decorative icon")
        patterns = lessons_store.get_known_false_positive_patterns(min_count=3)
        assert len(patterns) == 1
        assert patterns[0]["criterion"] == "1.1.1 Non-text Content"
        assert patterns[0]["element_signature"] == "img"
        assert patterns[0]["count"] == 3

    def test_different_signatures_tracked_separately(self):
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "x")
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", '<div role="button">', "y")
        store = lessons_store._load_store()
        assert len(store) == 2

    def test_patterns_sorted_by_count_descending(self):
        for _ in range(3):
            lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "x")
        for _ in range(5):
            lessons_store.record_false_positive_removal("4.1.2 Name, Role, Value", '<div role="button">', "y")
        patterns = lessons_store.get_known_false_positive_patterns(min_count=3)
        assert patterns[0]["count"] == 5
        assert patterns[1]["count"] == 3

    def test_limit_caps_returned_patterns(self):
        for i in range(5):
            for _ in range(3):
                lessons_store.record_false_positive_removal(f"crit-{i}", "<img>", "x")
        patterns = lessons_store.get_known_false_positive_patterns(min_count=3, limit=2)
        assert len(patterns) == 2

    def test_empty_criterion_or_element_is_ignored(self):
        lessons_store.record_false_positive_removal("", "<img>", "x")
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "", "x")
        assert lessons_store._load_store() == {}

    def test_persists_to_disk_across_calls(self, _isolated_store):
        lessons_store.record_false_positive_removal("1.1.1 Non-text Content", "<img>", "x")
        assert os.path.exists(_isolated_store)
        with open(_isolated_store, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1

    def test_corrupted_store_file_degrades_gracefully(self, _isolated_store):
        os.makedirs(os.path.dirname(_isolated_store), exist_ok=True)
        with open(_isolated_store, "w", encoding="utf-8") as f:
            f.write("not valid json{{{")
        patterns = lessons_store.get_known_false_positive_patterns()
        assert patterns == []
