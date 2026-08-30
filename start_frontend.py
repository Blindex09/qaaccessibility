import os
import shutil
import subprocess
import sys

# Raiz derivada do proprio arquivo: um caminho absoluto fixo so funcionava
# nesta maquina (mesmo problema ja corrigido nos scripts de execucao manual).
cwd = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(cwd, "web")
web_build = os.path.join(web_dir, "web-build")

env = os.environ.copy()
env["PORT"] = "3000"
env["BACKEND_PORT"] = "8001"
log_dir = os.path.join(cwd, "logs")
os.makedirs(log_dir, exist_ok=True)


def _run(cmd: list[str], descricao: str) -> None:
    """Roda um passo de build e aborta com mensagem clara se ele falhar."""
    print(f"[frontend] {descricao}...")
    # shell=True no Windows: `npm`/`npx` sao shims .cmd e nao resolvem por
    # PATHEXT quando chamados diretamente pelo subprocess.
    resultado = subprocess.run(cmd, cwd=web_dir, env=env, shell=os.name == "nt")
    if resultado.returncode != 0:
        sys.exit(f"[frontend] Falhou: {descricao}. Rode manualmente em web/ para ver o erro.")


# web-build/ e artefato de build e nao e versionado. Em vez de deixar o proxy
# servir 404 mudo (ou exigir que a pessoa descubra o comando sozinha), gera o
# bundle na primeira execucao. Builds seguintes reaproveitam o que ja existe --
# para refazer do zero, apague web/web-build.
if not os.path.exists(os.path.join(web_build, "index.html")):
    if shutil.which("npm") is None:
        sys.exit("[frontend] npm nao encontrado no PATH -- necessario para gerar o bundle da interface.")
    if not os.path.isdir(os.path.join(web_dir, "node_modules")):
        # web/.npmrc fixa legacy-peer-deps; sem ele o install aborta com ERESOLVE.
        _run(["npm", "ci"], "instalando dependencias do web")
    _run(["npx", "expo", "export:web"], "gerando o bundle da interface")

proc = subprocess.Popen(
    ["node", "web/proxy-server.js"],
    cwd=cwd,
    env=env,
    # These handles must outlive this script -- Popen keeps the detached child's
    # stdout/stderr redirected to them for its whole lifetime, so a `with` block
    # (which would close them immediately) doesn't apply here.
    stdout=open(os.path.join(log_dir, "frontend.log"), "a"),  # noqa: SIM115
    stderr=open(os.path.join(log_dir, "frontend.err.log"), "a"),  # noqa: SIM115
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
)

with open("frontend.pid", "w") as f:
    f.write(str(proc.pid))

print("Frontend started on PID", proc.pid)
