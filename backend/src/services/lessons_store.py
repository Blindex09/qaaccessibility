"""
lessons_store.py
Memória persistente de padrões de falso positivo confirmados entre análises
(mesmo espírito da "skill memory" do Hermes Agent, ver pesquisa 2026-08-11:
um agente que erra, ajusta a estratégia e converge pra decisões melhores em
tarefas recorrentes -- aqui, sem re-treino de peso, via um registro em disco
que acumula o que o a11y_expert_reviewer JÁ confirmou como falso positivo em
análises passadas, e injeta isso de volta como contexto nas próximas.

Decisão de escopo: só grava padrões GENERALIZÁVEIS (criterion + assinatura
estrutural do elemento -- tag + role/primeira classe -- nunca o HTML completo
de uma página específica), porque uma lição só é útil se se repetir em
páginas DIFERENTES. Só vira "conhecimento" (injetado no prompt de análises
futuras) depois de se repetir MIN_COUNT_TO_SURFACE vezes -- um único evento
isolado pode ser coincidência, não um padrão real.
"""

import json
import logging
import os
import re
import tempfile
import time
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "record_false_positive_removal",
    "get_known_false_positive_patterns",
]

_STORE_PATH = os.path.join(tempfile.gettempdir(), "qa_accessibility_lessons", "false_positive_patterns.json")
MIN_COUNT_TO_SURFACE = 3
MAX_PATTERNS_SURFACED = 10

_TAG_RE = re.compile(r"<\s*([a-zA-Z][\w-]*)", re.I)
_ROLE_RE = re.compile(r"\brole\s*=\s*['\"]?([\w-]+)", re.I)
_CLASS_RE = re.compile(r"\bclass\s*=\s*['\"]([^'\"]+)['\"]", re.I)


def _element_signature(element: str) -> str:
    """Assinatura estrutural generalizavel do elemento -- tag + role (se
    houver) + primeira classe (se houver) -- nunca o HTML completo, que varia
    demais entre paginas diferentes pra ser reutilizavel como licao."""
    tag = _TAG_RE.search(element)
    role = _ROLE_RE.search(element)
    css_class = _CLASS_RE.search(element)
    parts = [tag.group(1).lower() if tag else "unknown"]
    if role:
        parts.append(f"role={role.group(1).lower()}")
    if css_class:
        first_class = css_class.group(1).split()[0] if css_class.group(1).split() else ""
        if first_class:
            parts.append(f"class={first_class.lower()}")
    return "|".join(parts)


def _pattern_key(criterion: str, element_signature: str) -> str:
    return f"{criterion.strip().lower()}::{element_signature}"


def _load_store() -> dict[str, dict[str, Any]]:
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[LessonsStore] Falha ao ler o registro de lições: %s", exc)
        return {}


def _save_store(store: dict[str, dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("[LessonsStore] Falha ao salvar o registro de lições: %s", exc)


def record_false_positive_removal(criterion: str, element: str, example_description: str = "") -> None:
    """Registra que o a11y_expert_reviewer removeu um issue deste
    criterion+assinatura de elemento como falso positivo NESTA análise.
    Acumula contagem entre análises -- nunca sobrescreve o histórico."""
    if not criterion or not element:
        return
    signature = _element_signature(element)
    key = _pattern_key(criterion, signature)
    store = _load_store()
    entry = store.get(key, {
        "criterion": criterion,
        "element_signature": signature,
        "count": 0,
        "example_description": example_description,
    })
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last_seen"] = time.time()
    if example_description:
        entry["example_description"] = example_description
    store[key] = entry
    _save_store(store)


def get_known_false_positive_patterns(
    min_count: int = MIN_COUNT_TO_SURFACE,
    limit: int = MAX_PATTERNS_SURFACED,
) -> list[dict[str, Any]]:
    """Devolve os padrões que já se repetiram como falso positivo confirmado
    em análises passadas (contagem >= min_count), ordenados pelos mais
    recorrentes -- prontos pra injetar como contexto no próximo review.
    Nunca devolve um evento isolado (min_count protege contra ruído de
    coincidência de página única)."""
    store = _load_store()
    patterns = [entry for entry in store.values() if int(entry.get("count", 0)) >= min_count]
    patterns.sort(key=lambda e: int(e.get("count", 0)), reverse=True)
    return patterns[:limit]
