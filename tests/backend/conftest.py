import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]

path_str = str(PROJECT_ROOT)
if PROJECT_ROOT.exists() and path_str not in sys.path:
    sys.path.insert(0, path_str)

# A suíte precisa ser hermética: nada aqui pode depender de um .env local nem
# tocar no cofre de segredos real do desenvolvedor. Definimos os valores antes
# de importar backend.src.main, porque get_settings() roda no import do módulo.
os.environ.setdefault("QA_SECRET_STORE_PATH", str(Path(tempfile.gettempdir()) / "qa-a11y-test-secrets.json"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.security.rate_limiter import _request_log
from backend.src.shared.models import (
    AccessibilityIssue,
    ChecklistItem,
    ChecklistStatus,
    Guideline,
    Severity,
)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    _request_log.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_issue() -> AccessibilityIssue:
    return AccessibilityIssue(
        id="issue-001",
        guideline=Guideline.WCAG_2_2,
        criterion="1.1.1 Non-text Content",
        severity=Severity.CRITICAL,
        element="img",
        description="Image missing alt attribute",
        suggestion="Add a descriptive alt attribute to the img element",
        wcag_url="https://www.w3.org/WAI/WCAG22/Understanding/non-text-content",
    )


@pytest.fixture
def sample_checklist_item() -> ChecklistItem:
    return ChecklistItem(
        id="check-001",
        criterion="1.1.1 Non-text Content",
        guideline=Guideline.WCAG_2_2,
        status=ChecklistStatus.FAIL,
        priority=Severity.CRITICAL,
        notes="All images must have descriptive alt text",
    )


@pytest.fixture
def sample_html() -> str:
    return "<html><body><img src='logo.png'><button>X</button></body></html>"


@pytest.fixture
def mock_llm_response():
    return AsyncMock(return_value="[]")
