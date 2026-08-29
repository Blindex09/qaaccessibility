"""Persistência dos jobs de Batch Inference do crawl (ver batch_inference.py).

Submissão e polling são requisições HTTP SEPARADAS -- o batch pode levar até
24h (SLA documentado dos 3 providers suportados), então o estado precisa
sobreviver entre requisições e, idealmente, a um restart do processo. Mesmo
padrão de `last_analysis_store.py`: um arquivo JSON por job em disco.
"""

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    batch_id: str
    provider: str
    model: str
    root_url: str
    page_htmls: dict[str, str] = field(default_factory=dict)  # url -> html semantico
    # Falhas de crawl (renderizacao/timeout), conhecidas ANTES do batch --
    # cada item: {"url": ..., "error": ...}. Reaparecem no resultado final
    # sem precisar re-crawlear quando o batch termina.
    failed_pages: list[dict[str, str]] = field(default_factory=list)
    created_at: float = 0.0


def _job_filepath(batch_id: str) -> str:
    # batch_id vem do provider (ex.: "batch_abc123", "msgbatch_...", "batches/xyz")
    # -- sanitiza pra um nome de arquivo seguro.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in batch_id)[:120]
    return os.path.join(tempfile.gettempdir(), f"qa_accessibility_batch_job_{safe}.json")


def save(job: BatchJob) -> None:
    if not job.created_at:
        job.created_at = time.time()
    try:
        with open(_job_filepath(job.batch_id), "w", encoding="utf-8") as f:
            json.dump(asdict(job), f, ensure_ascii=False)
    except OSError as e:
        logger.error("[BatchJobStore] Falha ao salvar job %s: %s", job.batch_id, e)


def load(batch_id: str) -> BatchJob | None:
    path = _job_filepath(batch_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return BatchJob(**data)
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.error("[BatchJobStore] Falha ao carregar job %s: %s", batch_id, e)
        return None


def delete(batch_id: str) -> None:
    path = _job_filepath(batch_id)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning("[BatchJobStore] Falha ao remover job %s: %s", batch_id, e)
