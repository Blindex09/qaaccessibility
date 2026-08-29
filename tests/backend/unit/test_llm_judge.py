"""
LLM-as-Judge evaluation suite — llm-evaluation skill.

Usa um "judge" (mock determinístico) para avaliar a qualidade do output do Fixer
em múltiplas dimensões, sem depender de string matching exato.

Dimensões avaliadas (llm-evaluation skill):
- Correctness: o fix realmente corrige a issue reportada?
- Minimality: o fix não reescreve código não relacionado?
- Preservation: os atributos acessíveis existentes foram mantidos?
- No-regression: o fix não introduziu novos problemas de acessibilidade?
- Completeness: todos os issues foram endereçados?

Abordagem: pointwise scoring (0-2 por dimensão) e reference-based comparison.
Em testes unitários, o "judge" é implementado como asserções determinísticas
sobre o output — sem chamar outro LLM (evita custo e não-determinismo em CI).
"""
import json
import re
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.fixer.fixer import run_fixer
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity

# ---------------------------------------------------------------------------
# Judge helpers — avaliação determinística de qualidade
# ---------------------------------------------------------------------------


def judge_correctness(issue: AccessibilityIssue, fixed_html: str) -> int:
    """
    Verifica se o fix endereçou o issue reportado.
    Score: 0 = não corrigido, 1 = parcialmente, 2 = corretamente corrigido.
    """
    element_tag = re.match(r"<([a-zA-Z][a-zA-Z0-9]*)", issue.element)
    tag = element_tag.group(1).lower() if element_tag else issue.element.lower()

    # Heurísticas por tipo de criterion
    criterion = issue.criterion.lower()
    if "1.1.1" in criterion or "non-text" in criterion:
        # img deve ter alt
        if re.search(rf"<{tag}[^>]+alt\s*=", fixed_html, re.IGNORECASE):
            return 2
        return 0
    if "4.1.2" in criterion or "name, role" in criterion:
        # elemento deve ter aria-label, aria-labelledby ou label
        if re.search(r"aria-label(ledby)?\s*=", fixed_html, re.IGNORECASE):
            return 2
        return 0
    if "1.3.1" in criterion or "info and relationship" in criterion:
        # label ou role semântico
        if re.search(r"<label|aria-labelledby|<th", fixed_html, re.IGNORECASE):
            return 2
        return 1
    # Default: assume corrigido se changes_summary não está vazio
    return 1


def judge_minimality(original_html: str, fixed_html: str, changes_summary: list[str]) -> int:
    """
    Verifica se o fixer não reescreveu código excessivamente.
    Score: 0 = reescrita massiva, 1 = mudanças moderadas, 2 = mudanças cirúrgicas.
    """
    if not original_html or not fixed_html:
        return 0
    # Proporção de caracteres preservados
    preserved_ratio = len(set(original_html) & set(fixed_html)) / max(len(set(original_html)), 1)
    size_ratio = len(fixed_html) / max(len(original_html), 1)
    # Fix aceitável: tamanho não mais que 3x o original
    if size_ratio > 3.0:
        return 0
    if size_ratio > 1.5:
        return 1
    return 2


def judge_preservation(original_html: str, fixed_html: str) -> int:
    """
    Verifica se atributos acessíveis existentes foram preservados.
    Score: 0 = atributos removidos, 2 = todos preservados.
    """
    # Extrai todos aria-* e role= do original
    existing_attrs = re.findall(r'(aria-\w+|role)\s*=\s*["\'][^"\']*["\']', original_html, re.IGNORECASE)
    if not existing_attrs:
        return 2  # Nada para preservar
    preserved = sum(1 for attr in existing_attrs if attr.split("=")[0].strip() in fixed_html)
    ratio = preserved / len(existing_attrs)
    return 2 if ratio >= 0.9 else (1 if ratio >= 0.5 else 0)


def judge_no_regression(fixed_html: str) -> int:
    """
    Verifica se o fix não introduziu padrões problemáticos de acessibilidade.
    Score: 0 = regressão detectada, 2 = sem regressão.

    Regras verificadas:
    - tabindex > 0 (proibido)
    - link genérico "click here"
    - aria-hidden="true" em elementos CONTAINER que contêm filhos focusáveis
      (não aplica a void elements como img, input, svg standalone)
    """
    # Regressão 1: tabindex > 0
    if re.search(r'tabindex\s*=\s*"[2-9]', fixed_html):
        return 0

    # Regressão 2: link com texto genérico
    if re.search(r'<a\s+[^>]*>\s*(?:click here|here)\s*</a>', fixed_html, re.IGNORECASE):
        return 0

    # Regressão 3: aria-hidden em elemento CONTAINER com filho focusável
    # Só verificar elementos não-void (div, span, nav, section, etc.)
    container_pattern = r'<(div|span|nav|section|article|aside|header|footer|main)[^>]*aria-hidden\s*=\s*"true"[^>]*>'
    for match in re.finditer(container_pattern, fixed_html, re.IGNORECASE):
        tag = match.group(1)
        start = match.end()
        close = re.search(rf'</{tag}>', fixed_html[start:], re.IGNORECASE)
        if close:
            inner = fixed_html[start : start + close.start()]
            if re.search(r'<(button|a\s|input|select|textarea)', inner, re.IGNORECASE):
                return 0

    return 2


def evaluate_fix(
    issue: AccessibilityIssue,
    original_html: str,
    fixed_html: str,
    changes_summary: list[str],
) -> dict[str, int]:
    """Avalia o fix em 4 dimensões. Score máximo: 8."""
    return {
        "correctness": judge_correctness(issue, fixed_html),
        "minimality": judge_minimality(original_html, fixed_html, changes_summary),
        "preservation": judge_preservation(original_html, fixed_html),
        "no_regression": judge_no_regression(fixed_html),
    }


# ---------------------------------------------------------------------------
# Golden test cases para LLM-as-Judge
# ---------------------------------------------------------------------------

JUDGE_CASES = [
    {
        "id": "JC001",
        "description": "img sem alt — deve adicionar alt descritivo",
        "html": '<html><body><img src="logo.png"></body></html>',
        "fixed": '<html><body><img src="logo.png" alt="Company Logo"></body></html>',
        "changes": ["Added alt='Company Logo' to img element"],
        "issue_criterion": "1.1.1 Non-text Content",
        "issue_element": "<img src='logo.png'>",
        "min_score": 6,  # de 8
    },
    {
        "id": "JC002",
        "description": "button ícone sem aria-label — deve adicionar aria-label",
        "html": '<html><body><button><svg></svg></button></body></html>',
        "fixed": '<html><body><button aria-label="Close"><svg aria-hidden="true" focusable="false"></svg></button></body></html>',
        "changes": ["Added aria-label='Close' to button", "Added aria-hidden to decorative SVG"],
        "issue_criterion": "4.1.2 Name, Role, Value",
        "issue_element": "<button>",
        "min_score": 6,
    },
    {
        "id": "JC003",
        "description": "input sem label — deve adicionar label",
        "html": '<html><body><form><input type="email" name="email"></form></body></html>',
        "fixed": '<html><body><form><label for="email">Email</label><input type="email" name="email" id="email" autocomplete="email"></form></body></html>',
        "changes": ["Added label for email input", "Added autocomplete='email'"],
        "issue_criterion": "1.3.1 Info and Relationships",
        "issue_element": "<input type='email'>",
        "min_score": 6,
    },
    {
        "id": "JC004",
        "description": "atributos acessíveis existentes devem ser preservados",
        "html": '<html><body><button aria-pressed="false" type="button">Mute</button></body></html>',
        "fixed": '<html><body><button aria-pressed="false" type="button" aria-label="Mute audio">Mute</button></body></html>',
        "changes": ["Added aria-label to button for clarity"],
        "issue_criterion": "4.1.2 Name, Role, Value",
        "issue_element": "<button>",
        "min_score": 7,  # alta porque preservação é crítica aqui
    },
    {
        "id": "JC005",
        "description": "fixer não deve introduzir tabindex > 0",
        "html": '<html><body><div onclick="save()">Save</div></body></html>',
        "fixed": '<html><body><button onclick="save()">Save</button></body></html>',
        "changes": ["Replaced div with native button element"],
        "issue_criterion": "2.1.1 Keyboard",
        "issue_element": "<div>",
        "min_score": 6,
    },
]


def _make_issue(criterion: str, element: str) -> AccessibilityIssue:
    return AccessibilityIssue(
        id="j-001",
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=Severity.CRITICAL,
        element=element,
        description=f"Violation of {criterion}",
        suggestion="Fix it",
    )


# ---------------------------------------------------------------------------
# Testes LLM-as-Judge — pointwise scoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMJudgePointwise:
    @pytest.mark.parametrize("case", JUDGE_CASES)
    async def test_judge_score_meets_threshold(self, case: dict) -> None:
        """LLM-as-Judge: score combinado deve atingir o limiar mínimo aceitável."""
        issue = _make_issue(case["issue_criterion"], case["issue_element"])
        mock_fix = {"fixed_html": case["fixed"], "changes_summary": case["changes"]}

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_fix)),
        ):
            result = await run_fixer(case["html"], [issue])

        assert result.success is True, f"[{case['id']}] Fixer falhou: {result.error}"

        scores = evaluate_fix(
            issue,
            original_html=case["html"],
            fixed_html=result.data["fixed_html"],
            changes_summary=result.data.get("changes_summary", []),
        )
        total = sum(scores.values())
        assert total >= case["min_score"], (
            f"[{case['id']}] Score {total}/8 abaixo do limiar {case['min_score']}. "
            f"Scores: {scores}. Desc: {case['description']}"
        )

    async def test_correctness_dimension_img_alt(self) -> None:
        """Dimensão correctness: img com alt recebe score 2."""
        issue = _make_issue("1.1.1 Non-text Content", "<img src='x.png'>")
        fixed_html = '<img src="x.png" alt="Product photo">'
        score = judge_correctness(issue, fixed_html)
        assert score == 2

    async def test_correctness_dimension_img_no_alt(self) -> None:
        """Dimensão correctness: img sem alt recebe score 0."""
        issue = _make_issue("1.1.1 Non-text Content", "<img src='x.png'>")
        score = judge_correctness(issue, '<img src="x.png">')
        assert score == 0

    async def test_minimality_rejects_bloated_output(self) -> None:
        """Dimensão minimality: output 4x maior que o input recebe score 0."""
        original = "<button>Save</button>"
        bloated = original + ("<!-- padding -->" * 200)
        score = judge_minimality(original, bloated, [])
        assert score == 0

    async def test_preservation_detects_removed_aria(self) -> None:
        """Dimensão preservation: aria-pressed removido recebe score 0."""
        original = '<button aria-pressed="false">Mute</button>'
        fixed = "<button>Mute</button>"  # aria-pressed removido
        score = judge_preservation(original, fixed)
        assert score == 0

    async def test_no_regression_detects_tabindex_abuse(self) -> None:
        """Dimensão no_regression: tabindex='2' é regressão."""
        fixed = '<button tabindex="2">Save</button>'
        score = judge_no_regression(fixed)
        assert score == 0

    async def test_no_regression_clean_output(self) -> None:
        """Dimensão no_regression: output limpo recebe score 2."""
        fixed = '<button aria-label="Close"><svg aria-hidden="true"></svg></button>'
        score = judge_no_regression(fixed)
        assert score == 2


# ---------------------------------------------------------------------------
# Reference-based comparison — compara output com referência dourada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMJudgeReferenceBased:
    async def test_fix_matches_reference_structure(self) -> None:
        """Reference-based: output deve ter mesma estrutura semântica que a referência."""
        issue = _make_issue("1.1.1 Non-text Content", "<img>")
        reference = '<html><body><img src="logo.png" alt="Logo"></body></html>'
        mock_fix = {
            "fixed_html": reference,
            "changes_summary": ["Added alt to img"],
        }
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_fix)),
        ):
            result = await run_fixer('<html><body><img src="logo.png"></body></html>', [issue])

        assert result.success is True
        # Estrutura semântica: img com alt presente
        assert re.search(r'<img[^>]+alt\s*=', result.data["fixed_html"], re.IGNORECASE)

    async def test_multi_issue_all_dimensions_pass(self) -> None:
        """Todos os 4 juízes devem passar para um fix de alta qualidade."""
        original = '<html><body><img src="x.png"><button><svg></svg></button></body></html>'
        fixed = (
            '<html><body>'
            '<img src="x.png" alt="Decorative" aria-hidden="true">'
            '<button aria-label="Close"><svg aria-hidden="true" focusable="false"></svg></button>'
            '</body></html>'
        )
        issue = _make_issue("1.1.1 Non-text Content", "<img>")
        mock_fix = {"fixed_html": fixed, "changes_summary": ["Fixed img and button"]}

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_fix)),
        ):
            result = await run_fixer(original, [issue])

        assert result.success is True
        scores = evaluate_fix(issue, original, result.data["fixed_html"], result.data["changes_summary"])
        # Todos os juízes devem dar >= 1
        for dim, score in scores.items():
            assert score >= 1, f"Dimensão '{dim}' falhou com score {score}"
