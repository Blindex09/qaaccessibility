"""Roda uma cópia limitada de arquivos num contêiner Linux descartável e sem rede (portado do sandbox do Agentic).

É evidência de desenvolvimento: passar aqui nunca prova que a aplicação funciona no ambiente real da pessoa. Não existe
caminho de volta para rodar no host, montagem de pasta, repasse de credencial nem download automático de imagem. Quem chama
é dono da concessão e da aprovação.

Regra 8: não há prazo fixo. O contêiner roda enquanto escreve alguma coisa; se a execução do turno parar de avançar ou a
pessoa cancelar, o contêiner é removido (limpeza garantida, por isso este processo não vai para segundo plano como um
comando do host). Os limites que existem são de segurança e de recurso (arquivos, bytes, memória, processos), não de tempo.
"""

import asyncio
import contextlib
import hashlib
import io
import os
import shutil
import stat
import tarfile
import uuid
from pathlib import Path
from typing import Any

from backend.src.security.process_env import clean_env
from backend.src.services.execution_scope import note_progress, run_until_stalled

RUNTIME_IMAGES = {"python": "python:3.11-slim", "node": "node:22-slim"}
MAX_SNAPSHOT_FILES = 3000
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".env", ".venv", "venv", "env", "node_modules", "checkpoints", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".ssh", ".aws", ".azure", ".config", ".claude",
    "dist", "build", ".next",
}
_EXCLUDED_FILES = {".npmrc", ".pypirc", ".netrc", "credentials.json", "id_rsa", "id_ed25519"}
LIMITATIONS = [
    "Prova de desenvolvimento em Linux isolado; ainda exige validação funcional no ambiente real.",
    "Sem rede, credenciais ou dependências instaladas do host; usa somente a imagem local permitida.",
    "Arquivos alterados no contêiner são descartados; a pasta original não é modificada.",
    "Arquivos de ambiente, credenciais conhecidas, caches e links são excluídos da cópia.",
]


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def snapshot_files(workspace: Path) -> list[tuple[str, bytes, int]]:
    """Copia só o que pode entrar no sandbox. Recusa link, estouro de limite e arquivo que muda durante a captura."""
    root = workspace.absolute()
    if _is_link(root.lstat()) or not root.is_dir():
        raise ValueError("A pasta do sandbox precisa ser um diretório real, não um link.")
    resolved_root = root.resolve()
    files: list[tuple[str, bytes, int]] = []
    directories = [root]
    total_bytes = 0
    while directories:
        directory = directories.pop()
        if _is_link(directory.lstat()):
            raise ValueError("A pasta mudou para um link durante a captura.")
        directory.resolve().relative_to(resolved_root)
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            name = entry.name.casefold()
            info = os.lstat(entry.path)
            if _is_link(info):
                continue
            path = Path(entry.path)
            if stat.S_ISDIR(info.st_mode):
                if name not in _EXCLUDED_DIRS and not name.endswith(".egg-info"):
                    directories.append(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            if name.startswith(".env") or name in _EXCLUDED_FILES or name.endswith((".pem", ".key")):
                continue
            if len(files) >= MAX_SNAPSHOT_FILES or total_bytes + info.st_size > MAX_SNAPSHOT_BYTES:
                raise ValueError("A cópia para o sandbox excede o limite de arquivos ou de tamanho.")
            path.resolve().relative_to(resolved_root)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(path, flags), "rb") as source:
                opened = os.fstat(source.fileno())
                if _is_link(opened) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                    raise ValueError("Um arquivo mudou durante a captura do sandbox.")
                content = source.read(MAX_SNAPSHOT_BYTES - total_bytes + 1)
            total_bytes += len(content)
            if total_bytes > MAX_SNAPSHOT_BYTES:
                raise ValueError("A cópia para o sandbox excede o limite de tamanho.")
            files.append((path.relative_to(root).as_posix(), content, 0o755 if info.st_mode & 0o111 else 0o644))
    return sorted(files)


def _fingerprint(files: list[tuple[str, bytes, int]]) -> str:
    digest = hashlib.sha256()
    for name, content, mode in files:
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(mode.to_bytes(4, "big"))
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _capture(workspace: Path) -> tuple[bytes, str]:
    files = snapshot_files(workspace)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content, mode in files:
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), mode
            archive.addfile(member, io.BytesIO(content))
    return output.getvalue(), _fingerprint(files)


async def _communicate_bounded(process: asyncio.subprocess.Process, payload: bytes = b"") -> tuple[int, str]:
    """Alimenta a entrada, guarda só o final da saída e sinaliza progresso a cada pedaço recebido."""
    tail = bytearray()
    total = 0

    async def feed() -> None:
        if process.stdin is not None:
            try:
                process.stdin.write(payload)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()

    async def read() -> None:
        nonlocal total
        if process.stdout is not None:
            while chunk := await process.stdout.read(8192):
                total += len(chunk)
                tail.extend(chunk)
                note_progress()
                if len(tail) > MAX_OUTPUT_BYTES:
                    del tail[:-MAX_OUTPUT_BYTES]

    await asyncio.gather(feed(), read(), process.wait())
    prefix = "[Saída truncada; últimas linhas disponíveis.]\n" if total > MAX_OUTPUT_BYTES else ""
    return process.returncode if process.returncode is not None else -1, prefix + tail.decode("utf-8", errors="replace")


async def _command(argv: list[str], payload: bytes = b"", *, guarded: bool = True) -> tuple[int, str]:
    """`guarded` espera enquanto a execução avança e desiste se ela parar. A limpeza (`guarded=False`) roda fora desse
    orçamento: justamente quando o orçamento já esgotou é que o contêiner precisa ser removido."""
    # O cliente do Docker precisa das variáveis DOCKER_*; nenhuma chave de provedor passa para ele.
    env = clean_env({k: v for k, v in os.environ.items() if k.startswith("DOCKER_")})
    process = await asyncio.create_subprocess_exec(
        *argv, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        work = _communicate_bounded(process, payload)
        return await (run_until_stalled(work) if guarded else work)
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()


def docker_run_args(docker: list[str], name: str, image_id: str, command: list[str]) -> list[str]:
    """Sem rede, sistema de arquivos só de leitura, sem capacidades, sem privilégios novos, usuário sem poder, memória,
    processos e CPU limitados, entrada pelo tar na entrada padrão. Nenhum argumento vem do modelo ou do disco."""
    return [
        *docker, "run", "--rm", "--name", name, "--pull", "never", "--interactive",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "256m", "--memory-swap", "256m", "--cpus", "1",
        "--user", "65534:65534", "--workdir", "/workspace", "--no-healthcheck",
        "--tmpfs", "/workspace:rw,nosuid,nodev,size=64m,uid=65534,gid=65534,mode=0700",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777",
        "--env", "HOME=/tmp", "--entrypoint", "/bin/sh", image_id,
        "-c", 'tar --no-same-owner --no-same-permissions -xf - -C /workspace && exec "$@"',
        "sandbox-run", *command,
    ]


def _valid_command(command: Any) -> bool:
    return (
        isinstance(command, list) and 0 < len(command) <= 128
        and all(isinstance(arg, str) and arg and "\x00" not in arg for arg in command)
        and sum(map(len, command)) <= 32000
    )


async def run_code_in_sandbox(workspace: Path, command: list[str], runtime: str = "python") -> dict[str, Any]:
    """Executa código de verdade sem dar acesso a arquivos, rede ou processos do host.

    Estados: passed, failed (erro do comando), unavailable (Docker ou imagem ausentes), rejected (entrada ou captura
    inválida), stalled (parou de avançar). Cancelamento propaga depois da limpeza.
    """
    evidence: dict[str, Any] = {
        "passed": False, "status": "rejected", "command": command, "runtime": runtime,
        "image": RUNTIME_IMAGES.get(runtime, ""), "image_id": None, "output": "",
        "workspace_fingerprint": None, "limitations": list(LIMITATIONS), "exit_code": None,
    }
    if runtime not in RUNTIME_IMAGES:
        evidence["output"] = "Runtime não permitido; use python ou node."
        return evidence
    if not _valid_command(command):
        evidence["output"] = "Comando inválido para o sandbox."
        return evidence
    executable = docker_cli()
    if not executable:
        evidence.update(status="unavailable", output="Docker não está instalado nesta máquina, então o sandbox não rodou.")
        return evidence
    try:
        payload, fingerprint = await asyncio.to_thread(_capture, workspace)
        evidence["workspace_fingerprint"] = fingerprint
    except (OSError, ValueError, RuntimeError) as exc:
        evidence["output"] = f"Não foi possível capturar a pasta do sandbox: {exc}"
        return evidence
    docker = [executable]
    name = "qaaccessibility-sandbox-" + uuid.uuid4().hex
    attempted_run = False
    try:
        # Nunca copiar arquivos para um contexto Docker remoto: fixa o endpoint local inspecionado.
        endpoint = os.getenv("DOCKER_HOST")
        if not endpoint:
            code, output = await _command([executable, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"])
            if code:
                evidence.update(status="unavailable", output=output)
                return evidence
            endpoint = output.strip()
        if not endpoint.startswith(("unix://", "npipe://")):
            evidence.update(status="unavailable", output="O sandbox exige um Docker local; contexto remoto recusado.")
            return evidence
        docker.extend(["--host", endpoint])
        code, output = await _command([*docker, "image", "inspect", "--format", "{{.Id}}", evidence["image"]])
        image_id = output.strip()
        if code or not image_id.startswith("sha256:"):
            evidence.update(status="unavailable", output="Docker parado ou imagem local ausente: " + output)
            return evidence
        evidence["image_id"] = image_id
        attempted_run = True
        code, output = await _command(docker_run_args(docker, name, image_id, command), payload)
        evidence.update(passed=code == 0, status="passed" if code == 0 else "failed", output=output, exit_code=code)
    except TimeoutError:
        evidence.update(
            status="stalled" if attempted_run else "unavailable",
            output="O sandbox foi parado porque parou de avançar." if attempted_run else "O Docker não respondeu.",
        )
    except OSError as exc:
        evidence.update(status="unavailable", output=f"Não foi possível executar o Docker: {exc}")
    finally:
        if attempted_run:
            try:
                code, output = await asyncio.shield(_command([*docker, "rm", "--force", name], guarded=False))
                if code and "No such container" not in output:
                    evidence["passed"] = False
                    evidence["status"] = "failed"
                    evidence["limitations"].append("Não foi possível confirmar a remoção do contêiner: " + output)
            except (OSError, TimeoutError):
                evidence["passed"] = False
                evidence["status"] = "failed"
                evidence["limitations"].append("Docker indisponível durante a confirmação de remoção do contêiner.")
    return evidence


def docker_cli() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    bundled = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
    return str(bundled) if os.name == "nt" and bundled.is_file() else None
