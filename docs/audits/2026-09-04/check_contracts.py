"""Success marker only after the real acceptance probe suite exits zero."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
result = subprocess.run(
    [sys.executable, "-m", "pytest", "docs/audits/2026-09-04/test_factory_contracts.py",
     "-o", "addopts=", "-q"], cwd=root, check=False,
)
if result.returncode == 0:
    print("FACTORY_CONTRACTS_MET")
raise SystemExit(result.returncode)
