"""Run the external-evaluator matrix against QA Accessibility trajectories.

The matrix is deliberately explicit: a project is marked ``not_applicable``
when it does not expose an evaluator contract for another agent.  It must not
be reported as a pass merely because its own unit tests pass.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAJECTORIES = ROOT / "docs" / "audits" / "cross-project" / "qaaccessibility-trajectories.jsonl"
FIX_TRAJECTORIES = ROOT / "docs" / "audits" / "cross-project" / "qaaccessibility-fix-trajectories.jsonl"
EXPECTED_PROJECTS = {
    "A2E",
    "agent-eval-harness",
    "agent-health",
    "agentevals",
    "agentfit",
    "AgentOps-Bench",
    "HarnessFix",
    "adl",
    "aga-verify-agent",
    "ArgusAgent",
    "horizon",
    "skillgate",
    "unlazy",
    "Zaofu",
}


@dataclass(frozen=True)
class MatrixResult:
    project: str
    category: str
    status: str
    evidence: str
    output: str | None = None


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=process_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def _native_results(output_dir: Path) -> list[MatrixResult]:
    results: list[MatrixResult] = []
    commands = [
        (
            "agent-eval-harness",
            "trajectory, tool-use, suite and gate evaluation",
            ["node", r"scripts\audit-qaaccessibility.mjs"],
            Path(r"C:\aprovacao\agent-eval-harness"),
        ),
        (
            "agent-health",
            "native evaluator and trajectory observability",
            [
                "node",
                r"scripts\audit-qaaccessibility.mjs",
                str(TRAJECTORIES),
                str(output_dir / "agent-health.json"),
            ],
            Path(r"C:\aprovacao\agent-health"),
        ),
        (
            "A2E",
            "trajectory evaluator",
            [
                "uv",
                "run",
                "--offline",
                "--project",
                r"C:\aprovacao\A2E\eval",
                "python",
                r"scripts\audit_qaaccessibility.py",
                "--input",
                str(TRAJECTORIES),
                "--output",
                str(output_dir / "a2e.json"),
            ],
            Path(r"C:\aprovacao\A2E\eval"),
        ),
        (
            "agentfit",
            "agent evaluation",
            [r"C:\aprovacao\agentfit\.venv\Scripts\python.exe", r"scripts\audit_qaaccessibility.py"],
            Path(r"C:\aprovacao\agentfit"),
        ),
        (
            "agentevals",
            "trajectory evaluation",
            [r"C:\aprovacao\agentevals\python\.venv\Scripts\python.exe", r"scripts\audit_qaaccessibility.py"],
            Path(r"C:\aprovacao\agentevals\python"),
        ),
        (
            "AgentOps-Bench",
            "reliability and safety scoring",
            [r"C:\aprovacao\agentops-bench\.venv\Scripts\python.exe", r"scripts\audit_qaaccessibility.py"],
            Path(r"C:\aprovacao\agentops-bench"),
        ),
        (
            "HarnessFix",
            "remediation lifecycle scoring",
            [
                r"C:\aprovacao\HarnessFix\.venv\Scripts\python.exe",
                r"scripts\audit_qaaccessibility.py",
                "--input",
                str(TRAJECTORIES),
                "--fix-input",
                str(FIX_TRAJECTORIES),
                "--output",
                str(output_dir / "harnessfix.json"),
            ],
            Path(r"C:\aprovacao\HarnessFix"),
        ),
    ]
    for project, category, command, cwd in commands:
        if not cwd.exists():
            results.append(MatrixResult(project, category, "unavailable", f"diretório ausente: {cwd}"))
            continue
        env = {"QA_AUDIT_JSONL": str(TRAJECTORIES)}
        if project == "A2E":
            env["PYTHONPATH"] = os.pathsep.join(
                [
                    r"C:\aprovacao\A2E\eval",
                    r"C:\aprovacao\A2E\eval\packages\a2e-evals\src",
                ]
            )
        elif project == "agentfit":
            env["PYTHONPATH"] = r"C:\aprovacao\agentfit"
        elif project == "agentevals":
            env["PYTHONPATH"] = r"C:\aprovacao\agentevals\python"
        elif project == "AgentOps-Bench":
            env["PYTHONPATH"] = r"C:\aprovacao\agentops-bench\src"
        code, text = _run(command, cwd, env)
        results.append(
            MatrixResult(
                project,
                category,
                "passed" if code == 0 else "failed",
                text[-1200:],
            )
        )
    return results


def _deterministic_results() -> list[MatrixResult]:
    results: list[MatrixResult] = []
    skillgate = Path(r"C:\confirmacao\skillgate")
    if skillgate.exists():
        code, text = _run(
            ["node", r"dist\src\cli.js", "audit", "--cwd", str(ROOT)],
            skillgate,
        )
        results.append(MatrixResult("skillgate", "deterministic repository gate", "passed" if code == 0 else "failed", text[-1200:]))
    else:
        results.append(MatrixResult("skillgate", "deterministic repository gate", "unavailable", str(skillgate)))

    unlazy_script = Path(r"C:\confirmacao\unlazy\scripts\gate-check.mjs")
    ledger = ROOT / "GATES.md"
    if unlazy_script.exists() and ledger.exists():
        code, text = _run(["node", str(unlazy_script), "--status", str(ledger)], ROOT)
        results.append(MatrixResult("unlazy", "acceptance-ledger status", "passed" if code == 0 else "failed", text[-1200:]))
    else:
        results.append(MatrixResult("unlazy", "acceptance-ledger status", "unavailable", "script or ledger absent"))
    return results


def _not_applicable_results() -> list[MatrixResult]:
    return [
        MatrixResult("adl", "agent discipline skill", "not_applicable", "skill installation/goal contract, not an external agent evaluator"),
        MatrixResult("aga-verify-agent", "completion verifier skill", "not_applicable", "requires an accepted task and candidate snapshot, not a generic agent trajectory"),
        MatrixResult("ArgusAgent", "persistent agent runtime", "not_applicable", "runtime under test has no evaluator adapter for QA"),
        MatrixResult("horizon", "generate-execute-repair benchmark", "not_applicable", "benchmark runner has no QA trajectory adapter"),
        MatrixResult("Zaofu", "multi-agent runtime", "not_applicable", "runtime under test has no evaluator adapter for QA"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "audits" / "cross-project" / "external-evaluator-matrix.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_dir = args.output.parent / "external-evaluator-runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = _native_results(output_dir) + _deterministic_results() + _not_applicable_results()
    project_names = [item.project for item in results]
    if set(project_names) != EXPECTED_PROJECTS or len(project_names) != len(EXPECTED_PROJECTS):
        missing = sorted(EXPECTED_PROJECTS - set(project_names))
        unexpected = sorted(set(project_names) - EXPECTED_PROJECTS)
        duplicates = sorted({name for name in project_names if project_names.count(name) > 1})
        raise RuntimeError(f"invalid evaluator matrix: missing={missing}, unexpected={unexpected}, duplicates={duplicates}")
    payload = {"target": str(ROOT), "results": [asdict(item) for item in results]}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"target": str(ROOT), "total": len(results), "output": str(args.output), "statuses": {status: sum(item.status == status for item in results) for status in {item.status for item in results}}}, ensure_ascii=False))
    return 0 if all(item.status not in {"failed", "unavailable"} for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
