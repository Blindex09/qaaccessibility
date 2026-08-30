import os
import subprocess
import sys

# Raiz derivada do proprio arquivo -- um caminho absoluto fixo so funcionava
# nesta maquina (mesma correcao ja aplicada em start_frontend.py e nos
# scripts de execucao manual).
cwd = os.path.dirname(os.path.abspath(__file__))

env = os.environ.copy()
env["PYTHONPATH"] = cwd
env["PYTHONUNBUFFERED"] = "1"
venv_python = os.path.join(cwd, ".venv", "Scripts", "python.exe")
python_exe = venv_python if os.path.exists(venv_python) else sys.executable
log_dir = os.path.join(cwd, "logs")
os.makedirs(log_dir, exist_ok=True)

cmd = [
    python_exe,
    "-u",
    "-m",
    "uvicorn",
    "backend.src.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8001",
    "--timeout-keep-alive",
    "600",
    "--access-log",
]

# `--env-file` so entra quando o arquivo existe: o uvicorn aborta se apontarem
# para um .env inexistente, e backend/.env nao e versionado (nem deve ser).
# Sem ele, as variaveis vem do ambiente do processo, que e como o CI e os
# scripts de execucao real ja passam as chaves.
env_file = os.path.join(cwd, "backend", ".env")
if os.path.exists(env_file):
    cmd += ["--env-file", env_file]
else:
    print("[backend] backend/.env nao encontrado -- usando as variaveis do ambiente.")

proc = subprocess.Popen(
    cmd,
    cwd=cwd,
    env=env,
    # These handles must outlive this script -- Popen keeps the detached child's
    # stdout/stderr redirected to them for its whole lifetime, so a `with` block
    # (which would close them immediately) doesn't apply here.
    stdout=open(os.path.join(log_dir, "backend.log"), "a"),  # noqa: SIM115
    stderr=open(os.path.join(log_dir, "backend.err.log"), "a"),  # noqa: SIM115
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
)

with open(os.path.join(cwd, "backend.pid"), "w") as f:
    f.write(str(proc.pid))

print("Backend started on PID", proc.pid)
