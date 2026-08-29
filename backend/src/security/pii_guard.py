import logging
import re

logger = logging.getLogger(__name__)

# Padrões tecnicos minimos — sem vocabulario de dominio (regra do projeto)
_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN americano
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),  # CPF brasileiro
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # Email
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),  # Numero de cartao
]


def contains_pii(text: str) -> bool:
    """Verifica se o texto contem PII tecnicamente identificavel."""
    for pattern in _PATTERNS:
        if pattern.search(text):
            logger.warning("[PIIGuard] PII detectado no output")
            return True
    return False


def redact_pii(text: str) -> str:
    """Remove PII do texto substituindo por [REDACTED]."""
    result = text
    for pattern in _PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result
