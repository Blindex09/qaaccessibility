"""Ambiente limpo e credencial por execução para processos filhos.

Antes, os runners de projeto (Cypress, Newman, instalações) herdavam `os.environ` inteiro: toda chave de provedor e de
serviço do processo do backend ficava visível para código de terceiros (pacotes npm, specs, coleções do Postman).
Aqui o filho recebe só o ambiente mínimo do sistema mais as credenciais que aquela execução pediu pelo nome.

A credencial é emprestada para uma execução (`credential_lease`): existe só enquanto o bloco roda e é apagada ao sair,
inclusive por cancelamento ou erro. Não é uma chave que expira por relógio nem um token emitido pelo provedor (os
provedores usados aqui não emitem chave efêmera); é o menor escopo e a menor duração que o desenho permite, e o
registro guarda só os nomes, nunca os valores.
"""

import logging
import os
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Variáveis do sistema sem as quais um programa comum não roda. Nenhuma delas é segredo.
_SYSTEM_VARIABLES = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
    "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SHELL", "USER", "LOGNAME", "NODE_PATH", "PLAYWRIGHT_BROWSERS_PATH",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
)


def clean_env(extra: Mapping[str, str] | None = None, source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Ambiente mínimo do sistema + o que a execução pediu explicitamente. Nada mais do processo pai passa."""
    origin = os.environ if source is None else source
    wanted = {name.upper() for name in _SYSTEM_VARIABLES}
    env = {name: value for name, value in origin.items() if name.upper() in wanted}
    if extra:
        env.update({str(k): str(v) for k, v in extra.items() if v is not None})
    return env


class CredentialLease:
    """Credenciais emprestadas a uma execução. Depois de revogada, não entrega mais nada."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values: dict[str, str] | None = dict(values)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._values or ())

    def env(self) -> dict[str, str]:
        """Ambiente limpo do filho com as credenciais deste empréstimo."""
        if self._values is None:
            raise PermissionError("Esta credencial já foi devolvida e não pode mais ser usada.")
        return clean_env(self._values)

    def revoke(self) -> None:
        if self._values is not None:
            self._values.clear()
            self._values = None


@contextmanager
def credential_lease(names: Iterable[str], source: Mapping[str, str] | None = None) -> Iterator[CredentialLease]:
    """Empresta só as credenciais pedidas, pelo nome, durante o bloco. As ausentes simplesmente não entram."""
    origin = os.environ if source is None else source
    requested = list(names)
    values = {name: origin[name] for name in requested if origin.get(name)}
    lease = CredentialLease(values)
    logger.info("[Credencial] emprestada a uma execução: %s", ", ".join(sorted(values)) or "(nenhuma)")
    try:
        yield lease
    finally:
        lease.revoke()
        logger.info("[Credencial] devolvida: %s", ", ".join(sorted(values)) or "(nenhuma)")
