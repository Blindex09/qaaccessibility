import os

import pytest

from backend.src.services.trace_replay import (
    Trace,
    TraceReplayer,
    TraceStep,
    load_trace,
    save_trace,
)


class TestTraceRecord:
    def test_record_appends_step_with_incrementing_index(self):
        trace = Trace(trace_id="t1")
        step1 = trace.record("llm_call", "fixer", input="<html>a</html>", output={"fixed_html": "<html>b</html>"})
        step2 = trace.record("tool_call", "run_fixer", input={"issues": []}, output="ok")

        assert step1.step_index == 0
        assert step2.step_index == 1
        assert len(trace.steps) == 2
        assert trace.steps[0].name == "fixer"
        assert trace.steps[1].kind == "tool_call"

    def test_record_captures_arbitrary_metadata(self):
        trace = Trace(trace_id="t1")
        step = trace.record("decision", "router", input="x", output="y", model_tier="alto", cost=0.002)
        assert step.metadata == {"model_tier": "alto", "cost": 0.002}


class TestTraceSerialization:
    def test_to_dict_and_from_dict_roundtrip(self):
        trace = Trace(trace_id="t1")
        trace.record("llm_call", "perceiver", input="<html></html>", output={"issues": []})
        data = trace.to_dict()
        restored = Trace.from_dict(data)

        assert restored.trace_id == "t1"
        assert len(restored.steps) == 1
        assert restored.steps[0].name == "perceiver"
        assert isinstance(restored.steps[0], TraceStep)

    def test_save_and_load_trace_roundtrip(self, tmp_path):
        trace = Trace(trace_id="save-load-test")
        trace.record("llm_call", "fixer", input="in", output={"fixed_html": "out"})

        path = save_trace(trace, directory=str(tmp_path))
        assert os.path.exists(path)
        assert path.endswith("save-load-test.json")

        loaded = load_trace(path)
        assert loaded.trace_id == "save-load-test"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].output == {"fixed_html": "out"}

    def test_save_trace_creates_directory_if_missing(self, tmp_path):
        target_dir = str(tmp_path / "nested" / "traces")
        trace = Trace(trace_id="nested-dir-test")
        path = save_trace(trace, directory=target_dir)
        assert os.path.exists(path)


class TestTraceReplayer:
    def _sample_trace(self) -> Trace:
        trace = Trace(trace_id="replay-test")
        trace.record("llm_call", "classifier", input="<html></html>", output={"frameworks": ["react"]})
        trace.record("tool_call", "run_fixer", input={"issues": ["i1"]}, output={"fixed_html": "<html>fixed</html>"})
        return trace

    def test_replays_steps_in_recorded_order_without_reexecuting(self):
        replayer = TraceReplayer(self._sample_trace())

        assert replayer.has_next()
        first = replayer.next()
        assert first.name == "classifier"
        assert first.output == {"frameworks": ["react"]}

        second = replayer.next()
        assert second.name == "run_fixer"
        assert second.output == {"fixed_html": "<html>fixed</html>"}

        assert not replayer.has_next()

    def test_next_raises_when_trace_exhausted(self):
        replayer = TraceReplayer(Trace(trace_id="empty"))
        with pytest.raises(StopIteration):
            replayer.next()

    def test_find_by_name_does_not_advance_cursor(self):
        replayer = TraceReplayer(self._sample_trace())
        found = replayer.find_by_name("run_fixer")
        assert found is not None
        assert found.output == {"fixed_html": "<html>fixed</html>"}
        # cursor nao avancou -- has_next ainda True e next() retorna o PRIMEIRO passo
        assert replayer.has_next()
        assert replayer.next().name == "classifier"

    def test_find_by_name_returns_none_when_not_found(self):
        replayer = TraceReplayer(self._sample_trace())
        assert replayer.find_by_name("does_not_exist") is None

    def test_reset_rewinds_cursor(self):
        replayer = TraceReplayer(self._sample_trace())
        replayer.next()
        replayer.next()
        assert not replayer.has_next()
        replayer.reset()
        assert replayer.has_next()
        assert replayer.next().name == "classifier"

    def test_all_steps_returns_full_list(self):
        replayer = TraceReplayer(self._sample_trace())
        steps = replayer.all_steps()
        assert len(steps) == 2
        assert [s.name for s in steps] == ["classifier", "run_fixer"]

    def test_trace_id_property(self):
        replayer = TraceReplayer(self._sample_trace())
        assert replayer.trace_id == "replay-test"
