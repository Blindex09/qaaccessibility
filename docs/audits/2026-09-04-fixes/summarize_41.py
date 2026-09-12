"""Merge the full run and explicit reruns, never counting skipped cases as pass."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
selection = "-k trajectory_completes_successfully or response_matches_agent_result_contract or accessibility_eval_pipeline_succeeds or baseline_model_matches"
suffix = hashlib.sha256(selection.encode()).hexdigest()[:8]
sources = [HERE / "real-41.xml", HERE / f"real-41-{suffix}.xml"]
cases = {}
for index, source in enumerate(sources):
    tree = ET.parse(source)
    entries = tree.findall(".//testcase")
    assert len(entries) == (41 if index == 0 else 4), (source.name, len(entries))
    for case in entries:
        key = (case.attrib["classname"], case.attrib["name"])
        if index:
            assert key in cases, key
        status = next((tag for tag in ("failure", "error", "skipped") if case.find(tag) is not None), "passed")
        cases[key] = {"test": "::".join(key), "status": status, "source": source.name}

result = {"provider": "factory", "model": "auto", "total": len(cases),
          "passed": sum(case["status"] == "passed" for case in cases.values()),
          "cases": list(cases.values()), "sources": [source.name for source in sources]}
(HERE / "real-41-summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key != "cases"}))
assert result["passed"] == result["total"] == 41, "Unmet tests remain; inspect per-case evidence"
