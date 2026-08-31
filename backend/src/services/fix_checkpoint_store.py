"""Checkpoint da remediação, isolado por sessão/conversa, para permitir desfazer.

`fix_and_zip_files` é a única chat tool que sobrescreve estado compartilhado: ele
substitui o cache da última análise (`last_analysis_store`) e as páginas de
preview (`last_fix_store`). Até aqui isso era irreversível -- corrigiu, perdeu o
estado anterior, e o usuário não tinha caminho de volta.

Este store tira uma foto desse estado ANTES da correção rodar e sabe repô-la. Ele
segue o mesmo padrão por sessão do `last_analysis_store` (um slot por
conversation_id, sessão corrente vinda de `session_context.py`) em vez de um
global, porque duas conversas simultâneas corrigindo projetos diferentes
desfariam uma o trabalho da outra. Só em memória, como o `last_fix_store`: um
checkpoint não precisa sobreviver a um restart do processo.

Apenas um nível de undo: desfazer restaura e consome o checkpoint.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.src.services.session_context import (
    DEFAULT_SESSION_ID,
    reset_current_session,
    resolve_session,
    set_current_session,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SESSION_ID",
    "set_current_session",
    "reset_current_session",
    "FixCheckpoint",
    "create_checkpoint",
    "get_checkpoint",
    "restore_checkpoint",
    "clear",
]

_checkpoints: dict[str, "FixCheckpoint"] = {}


@dataclass(frozen=True)
class FixCheckpoint:
    """Estado dos caches de acessibilidade imediatamente antes de uma correção."""

    label: str
    created_at: float
    issues: list[dict[str, Any]] = field(default_factory=list)
    url: str = ""
    fix_pages: list[dict[str, Any]] = field(default_factory=list)
    # Correção LOCAL: diretório do projeto e cópia dos arquivos originais que
    # `fix_local_project_files` sobrescreveu. Sem estes dois campos o undo
    # devolvia "Estado anterior à última correção restaurado" enquanto os
    # arquivos no computador do usuário continuavam alterados -- medido em
    # 2026-08-31. O backup já era feito antes de escrever; faltava alguém
    # saber dele na hora de voltar atrás.
    project_dir: str = ""
    backup_dir: str = ""

    def describe(self) -> str:
        parte_local = f", {self.project_dir}" if self.project_dir else ""
        return (
            f"{self.label} ({len(self.issues)} issue(s), "
            f"{len(self.fix_pages)} página(s) de preview, origem: {self.url or 'n/d'}{parte_local})"
        )


def _resolve_session(session_id: str | None) -> str:
    return resolve_session(session_id)


def create_checkpoint(
    label: str,
    session_id: str | None = None,
    project_dir: str = "",
    backup_dir: str = "",
) -> FixCheckpoint:
    """Fotografa o estado atual dos caches da sessão antes de uma correção."""
    from backend.src.services.last_analysis_store import get_last_analysis
    from backend.src.services.last_fix_store import get_last_fix

    session = _resolve_session(session_id)
    issues, url = get_last_analysis(session_id=session)
    checkpoint = FixCheckpoint(
        label=label,
        created_at=time.time(),
        issues=[dict(issue) for issue in issues],
        url=url,
        fix_pages=[dict(page) for page in get_last_fix(session_id=session)],
        project_dir=project_dir,
        backup_dir=backup_dir,
    )
    _checkpoints[session] = checkpoint
    logger.info("[FixCheckpointStore] Checkpoint criado (sessão %s): %s", session, checkpoint.describe())
    return checkpoint


def get_checkpoint(session_id: str | None = None) -> FixCheckpoint | None:
    """Devolve o checkpoint da sessão, ou None se não houver."""
    return _checkpoints.get(_resolve_session(session_id))


def restore_checkpoint(session_id: str | None = None) -> FixCheckpoint | None:
    """Repõe o estado guardado e consome o checkpoint. None se não houver nenhum."""
    from backend.src.services.last_analysis_store import set_last_analysis
    from backend.src.services.last_fix_store import set_last_fix

    session = _resolve_session(session_id)
    checkpoint = _checkpoints.pop(session, None)
    if checkpoint is None:
        return None

    set_last_analysis(
        [dict(issue) for issue in checkpoint.issues],
        checkpoint.url,
        append=False,
        session_id=session,
    )
    set_last_fix([dict(page) for page in checkpoint.fix_pages], session_id=session)
    restaurados = _restaurar_arquivos_locais(checkpoint)
    logger.info(
        "[FixCheckpointStore] Checkpoint restaurado (sessão %s): %s -- %d arquivo(s) em disco",
        session,
        checkpoint.describe(),
        restaurados,
    )
    return checkpoint


def _restaurar_arquivos_locais(checkpoint: FixCheckpoint) -> int:
    """Repõe no disco os arquivos que a correção local sobrescreveu.

    `fix_local_project_files` ja copiava cada original para um diretorio de
    backup antes de escrever -- mas ninguem guardava esse caminho, entao
    `undo_last_fix` respondia "Estado anterior à última correção restaurado"
    com os arquivos do usuário ainda alterados (medido em 2026-08-31). O backup
    existia; faltava a costura.

    Best-effort por arquivo: uma falha isolada nao aborta os demais nem levanta
    para o chamador -- desfazer parcialmente e melhor do que nao desfazer nada,
    e cada falha e logada com o caminho.
    """
    if not checkpoint.backup_dir or not checkpoint.project_dir:
        return 0
    if not os.path.isdir(checkpoint.backup_dir):
        logger.warning(
            "[FixCheckpointStore] Backup de %s nao existe mais em %s -- nada a restaurar em disco.",
            checkpoint.project_dir,
            checkpoint.backup_dir,
        )
        return 0

    restaurados = 0
    for raiz, _dirs, arquivos in os.walk(checkpoint.backup_dir):
        for nome in arquivos:
            origem = os.path.join(raiz, nome)
            relativo = os.path.relpath(origem, checkpoint.backup_dir)
            destino = os.path.join(checkpoint.project_dir, relativo)
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(origem, "rb") as src, open(destino, "wb") as dst:
                    dst.write(src.read())
                restaurados += 1
            except OSError as exc:
                logger.error("[FixCheckpointStore] Falha ao restaurar %s: %s", destino, exc)
    return restaurados


def clear(session_id: str | None = None) -> None:
    """Descarta o checkpoint da sessão (sem restaurar)."""
    _checkpoints.pop(_resolve_session(session_id), None)
