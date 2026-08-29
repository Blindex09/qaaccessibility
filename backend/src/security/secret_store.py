"""DPAPI-backed secret persistence for the local Windows application."""

import base64
import contextlib
import ctypes
import json
import logging
import os
import tempfile
import threading
from ctypes import wintypes
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_STORE_LOCK = threading.RLock()

logger = logging.getLogger(__name__)


class SecretStoreUnreadableError(RuntimeError):
    """O cofre local existe mas não pôde ser decifrado nesta máquina/usuário.

    Acontece, por exemplo, quando o arquivo é copiado para outro computador ou
    outro perfil do Windows: o DPAPI é vinculado ao usuário que o gravou.
    """


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _store_path() -> Path:
    configured = os.getenv("QA_SECRET_STORE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path("backend/.secrets.json").resolve()


def _fallback_key_path() -> Path:
    return _store_path().with_suffix(".key")


def _as_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    input_blob, input_buffer = _as_blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    description = "QA Accessibility local secrets" if protect else None
    if not function(
        ctypes.byref(input_blob),
        description,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
        del input_buffer


def _fallback_fernet() -> Fernet:
    key_path = _fallback_key_path()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        key = key_path.read_bytes()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        with contextlib.suppress(OSError):
            os.chmod(key_path, 0o600)
    return Fernet(key)


def _protect(data: bytes) -> str:
    if os.name == "nt":
        encrypted = _dpapi(data, protect=True)
        return "dpapi:v1:" + base64.urlsafe_b64encode(encrypted).decode("ascii")
    return "fernet:v1:" + _fallback_fernet().encrypt(data).decode("ascii")


def _unprotect(value: str) -> bytes:
    if value.startswith("dpapi:v1:"):
        encrypted = base64.urlsafe_b64decode(value.removeprefix("dpapi:v1:").encode("ascii"))
        return _dpapi(encrypted, protect=False)
    if value.startswith("fernet:v1:"):
        return _fallback_fernet().decrypt(value.removeprefix("fernet:v1:").encode("ascii"))
    raise ValueError("Formato de cofre local desconhecido.")


def load_secrets() -> dict[str, str]:
    with _STORE_LOCK:
        path = _store_path()
        if not path.exists():
            return {}
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            plaintext = _unprotect(str(envelope["protected"]))
            payload = json.loads(plaintext.decode("utf-8"))
        except (OSError, ValueError, KeyError, InvalidToken) as error:
            raise SecretStoreUnreadableError(f"Não foi possível ler o cofre local em {path}: {error}") from error
        if not isinstance(payload, dict):
            raise SecretStoreUnreadableError("O cofre local não contém um objeto válido.")
        return {str(key): str(value) for key, value in payload.items()}


def _load_secrets_tolerant() -> dict[str, str]:
    """Como load_secrets(), mas devolve {} quando o cofre é ilegível.

    Usado nos caminhos de leitura de inicialização: um cofre ilegível não pode
    derrubar a aplicação inteira -- as chaves simplesmente não são carregadas e
    o usuário é orientado a reconfigurá-las.
    """
    try:
        return load_secrets()
    except SecretStoreUnreadableError as error:
        logger.warning(
            "%s -- as chaves salvas serão ignoradas. Reconfigure-as na tela de "
            "Configurações para regravar o cofre nesta máquina.",
            error,
        )
        return {}


def _save_all(values: dict[str, str]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect(json.dumps(values, ensure_ascii=False).encode("utf-8"))
    envelope = json.dumps({"version": 1, "protected": protected}, ensure_ascii=False)
    handle, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temporary:
            temporary.write(envelope)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary_name)


def save_secret(name: str, value: str) -> None:
    with _STORE_LOCK:
        values = _load_secrets_tolerant()
        values[name] = value
        _save_all(values)


def delete_secret(name: str) -> None:
    with _STORE_LOCK:
        values = _load_secrets_tolerant()
        if name in values:
            del values[name]
            _save_all(values)


def load_secrets_into_environment() -> None:
    for name, value in _load_secrets_tolerant().items():
        os.environ[name] = value


def migrate_plaintext_env_secrets(env_path: Path, secret_names: set[str]) -> int:
    """Move known secret assignments out of .env and into the protected store."""
    with _STORE_LOCK:
        if not env_path.exists():
            load_secrets_into_environment()
            return 0
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept: list[str] = []
        migrated: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                kept.append(line)
                continue
            name, value = stripped.split("=", 1)
            name = name.strip()
            if name in secret_names and value:
                migrated[name] = value
            else:
                kept.append(line)
        if migrated:
            values = _load_secrets_tolerant()
            values.update(migrated)
            _save_all(values)
            temporary = env_path.with_suffix(env_path.suffix + ".tmp")
            temporary.write_text("".join(kept), encoding="utf-8")
            os.replace(temporary, env_path)
        load_secrets_into_environment()
        return len(migrated)
