"""Run the opt-in suite with Factory; secrets never appear in persisted output."""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent / "2026-09-04"))
from live_probe import load_keys  # noqa: E402

keys = load_keys(Path(r"C:\Users\olive\Downloads\chaves de api.txt"))
os.environ.update(FACTORY_API_KEY=keys["factory"], RUN_REAL_LLM_TESTS="1", REAL_LLM_PROVIDER="factory")
import pytest  # noqa: E402

terminal = sys.stdout
suffix = "-" + hashlib.sha256(" ".join(sys.argv[1:]).encode()).hexdigest()[:8] if sys.argv[1:] else ""


class Progress:
    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed:
            print(report.nodeid + ": " + report.outcome, file=terminal, flush=True)


with tempfile.TemporaryDirectory(prefix="qa-real-evals-") as directory:
    os.environ["QA_SECRET_STORE_PATH"] = str(Path(directory) / "secrets.json")
    output = io.StringIO()
    xml = Path(directory) / "results.xml"
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        status = pytest.main(["tests/backend/real_llm", "-o", "addopts=", "-o", "junit_family=xunit1", "-q", "--tb=short",
                              f"--junitxml={xml}", *sys.argv[1:]], plugins=[Progress()])
    for name, content in [(f"real-41{suffix}.log", output.getvalue()),
                          (f"real-41{suffix}.xml", xml.read_text(encoding="utf-8") if xml.exists() else "")]:
        for key in keys.values():
            content = content.replace(key, "[REDACTED]")
        (HERE / name).write_text(content, encoding="utf-8")
print(f"REAL_SUITE_EXIT={status}", flush=True)
raise SystemExit(status)
