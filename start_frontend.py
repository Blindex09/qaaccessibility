import os
import subprocess

cwd = r"C:\qaaccessibility"
env = os.environ.copy()
env["PORT"] = "3000"
env["BACKEND_PORT"] = "8001"
log_dir = os.path.join(cwd, "logs")
os.makedirs(log_dir, exist_ok=True)

proc = subprocess.Popen(
    ["node", "web/proxy-server.js"],
    cwd=cwd,
    env=env,
    # These handles must outlive this script -- Popen keeps the detached child's
    # stdout/stderr redirected to them for its whole lifetime, so a `with` block
    # (which would close them immediately) doesn't apply here.
    stdout=open(os.path.join(log_dir, "frontend.log"), "a"),  # noqa: SIM115
    stderr=open(os.path.join(log_dir, "frontend.err.log"), "a"),  # noqa: SIM115
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)

with open("frontend.pid", "w") as f:
    f.write(str(proc.pid))

print("Frontend started on PID", proc.pid)
