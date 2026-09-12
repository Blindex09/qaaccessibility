"""Bind local evidence to source hashes without copying source or credentials."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[3]
paths = subprocess.check_output(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root,
).decode().split("\0")
hashes = {}
for name in paths:
    file = root / name
    if (file.suffix not in {".py", ".ts", ".tsx", ".toml", ".ini"}
            or not file.is_file()):
        continue
    hashes[name] = hashlib.sha256(file.read_bytes()).hexdigest()
data = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
    "dirty_worktree": True,
    "source_sha256": hashes,
}
Path(__file__).with_name("snapshot.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"Snapshot: {len(hashes)} source/config files fingerprinted; no source content copied")
