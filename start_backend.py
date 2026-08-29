import os
import subprocess
import sys

env = os.environ.copy()
cwd = r"C:\qaaccessibility"
env["PYTHONPATH"] = r"C:\qaaccessibility"
env["PYTHONUNBUFFERED"] = "1"
venv_python = os.path.join(cwd, ".venv", "Scripts", "python.exe")
python_exe = venv_python if os.path.exists(venv_python) else sys.executable
log_dir = os.path.join(cwd, "logs")
os.makedirs(log_dir, exist_ok=True)

proc = subprocess.Popen(
    [python_exe, "-u", "-m", "uvicorn", "backend.src.main:app", "--host", "0.0.0.0", "--port", "8001", "--env-file", "backend/.env", "--timeout-keep-alive", "600", "--access-log"],
    cwd=cwd,
    env=env,
    # These handles must outlive this script -- Popen keeps the detached child's
    # stdout/stderr redirected to them for its whole lifetime, so a `with` block
    # (which would close them immediately) doesn't apply here.
    stdout=open(os.path.join(log_dir, "backend.log"), "a"),  # noqa: SIM115
    stderr=open(os.path.join(log_dir, "backend.err.log"), "a"),  # noqa: SIM115
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)

with open("backend.pid", "w") as f:
    f.write(str(proc.pid))

print("Backend started on PID", proc.pid)
