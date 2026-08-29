"""
Verificacao deterministica de contraste WCAG (1.4.3 / 1.4.11).

Recomputa o ratio EXATO dos issues de contraste produzidos pelos sub-agentes e
remove falsos positivos -- sem depender de tool-call do LLM (robusto em qualquer
provider, calculo em Python puro sem depender do tool-loop do modelo).

Estrategia conservadora: so age quando encontra EXATAMENTE 2 cores parseaveis no
texto do issue. Com 0, 1 ou 3+ cores, deixa o issue intacto (não da para saber
com seguranca qual par comparar). Como o ratio de contraste e simetrico, a ordem
foreground/background e irrelevante.
"""

import logging
import re

from backend.src.services.a11y_domain_tools import contrast_ratio_rgb, parse_color
from backend.src.services.apca import apca_contrast, srgb_to_y
from backend.src.shared.models import AccessibilityIssue

logger = logging.getLogger(__name__)

_CONTRAST_CRITERIA = ("1.4.3", "1.4.11")

# Ordem importa: 6 digitos antes de 3 para casar #ffffff inteiro.
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
_RGB_RE = re.compile(r"rgba?\([^)]*\)", re.IGNORECASE)

# Extracao best-effort de regras CSS planas: "seletor { decls }".
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]+)\}")
# 'color:' sem ser parte de 'background-color'/'border-color' (lookbehind nega -/\w).
_DECL_FG_RE = re.compile(r"(?<![\w-])color\s*:\s*([^;]+)", re.IGNORECASE)
_DECL_BG_RE = re.compile(r"background(?:-color)?\s*:\s*([^;]+)", re.IGNORECASE)
# Identificadores de seletor (classe/id/tag), descartando tokens triviais (len<2).
_SELECTOR_IDENT_RE = re.compile(r"[.#]?([a-zA-Z_][\w-]+)")


def _threshold(criterion: str, level: str | None) -> float:
    """Limite WCAG para decidir falso positivo (conservador para evitar drop indevido)."""
    if criterion.startswith("1.4.11"):
        return 3.0  # Non-text Contrast
    if (level or "").strip().upper() == "AAA":
        return 7.0  # 1.4.6 territorio / AAA
    return 4.5  # 1.4.3 AA normal (drop so quando passa >= 4.5, valido p/ normal e large)


def extract_colors(text: str) -> list[tuple[int, int, int]]:
    """Extrai cores distintas (hex e rgb/rgba) de um texto, preservando ordem."""
    tokens = _HEX_RE.findall(text) + _RGB_RE.findall(text)
    seen: list[tuple[int, int, int]] = []
    for token in tokens:
        try:
            rgb = parse_color(token)
        except ValueError:
            continue
        if rgb not in seen:
            seen.append(rgb)
    return seen


def _extract_css_rules(source: str) -> list[tuple[str, str]]:
    """Extrai pares (seletor, corpo) de regras CSS planas do contexto [STYLES]."""
    return [(m.group(1).strip(), m.group(2)) for m in _RULE_RE.finditer(source)]


def _first_color(value: str) -> tuple[int, int, int] | None:
    colors = extract_colors(value)
    return colors[0] if colors else None


def _rule_color_pair(body: str) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """Retorna (cor_texto, cor_fundo) de uma regra que tem ambas, ou None."""
    fg_match = _DECL_FG_RE.search(body)
    bg_match = _DECL_BG_RE.search(body)
    if not fg_match or not bg_match:
        return None
    fg = _first_color(fg_match.group(1))
    bg = _first_color(bg_match.group(1))
    if fg is None or bg is None:
        return None
    return fg, bg


def _selector_matches(selector: str, element_text: str) -> bool:
    """True se algum identificador (len>=2) do seletor aparece no elemento do issue."""
    target = element_text.lower()
    return any(len(token) >= 2 and token.lower() in target for token in _SELECTOR_IDENT_RE.findall(selector))


def _source_color_pair(
    issue: AccessibilityIssue, rules: list[tuple[str, str]]
) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """
    Acha o par de cores da regra CSS do elemento do issue. So retorna quando
    EXATAMENTE uma regra casa o seletor E tem um par cor+fundo (sem ambiguidade).
    """
    matches: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for selector, body in rules:
        if not _selector_matches(selector, issue.element):
            continue
        pair = _rule_color_pair(body)
        if pair is not None:
            matches.append(pair)
    return matches[0] if len(matches) == 1 else None


def _issue_text(issue: AccessibilityIssue) -> str:
    parts = [
        issue.element,
        issue.description,
        issue.description_technical,
        issue.why_technical,
        issue.suggestion,
        issue.suggestion_technical,
    ]
    return " ".join(p for p in parts if p)


def _is_complex_rule(body: str) -> bool:
    body_lower = body.lower()
    return "url(" in body_lower or "gradient" in body_lower or "opacity" in body_lower


def verify_contrast_issues(
    issues: list[AccessibilityIssue],
    source_html: str | None = None,
) -> tuple[list[AccessibilityIssue], int]:
    """
    Recomputa o contraste dos issues 1.4.3 / 1.4.11 com o ratio WCAG exato.

    Dois caminhos:
    1. Texto do issue com EXATAMENTE 2 cores -> alta confianca: remove falso
       positivo (ratio >= limite) ou anota o ratio verificado.
    2. Caminho CSS-fonte (source_html): quando o texto não tem 2 cores, tenta o
       par cor+fundo da regra CSS do elemento. Modo ANOTACAO-APENAS -- nunca
       remove (matching de seletor e best-effort, drop seria arriscado).

    Retorna (issues_filtrados, qtde_removida).
    """
    rules = _extract_css_rules(source_html) if source_html else []
    kept: list[AccessibilityIssue] = []
    removed = 0

    for issue in issues:
        criterion = issue.criterion or ""
        if not criterion.startswith(_CONTRAST_CRITERIA):
            kept.append(issue)
            continue

        threshold = _threshold(criterion, issue.level)
        colors = extract_colors(_issue_text(issue))

        has_complex_bg = False
        if "data-complex-bg" in (issue.element or ""):
            has_complex_bg = True
        elif rules:
            for selector, body in rules:
                if _selector_matches(selector, issue.element) and _is_complex_rule(body):
                    has_complex_bg = True
                    break

        # Caminho 1 -- alta confianca (pode remover falso positivo).
        if len(colors) == 2:
            ratio = round(contrast_ratio_rgb(colors[0], colors[1]), 2)
            if ratio >= threshold:
                if has_complex_bg:
                    issue.why_technical = (issue.why_technical or "") + (
                        " [Revisão manual recomendada: O elemento utiliza imagem de fundo, gradiente ou opacidade que impossibilita o cálculo exato]"
                    )
                    kept.append(issue)
                    continue
                removed += 1
                logger.info(
                    "[ContrastVerifier] Falso positivo removido: %s ratio=%.2f >= limite=%.1f",
                    issue.id,
                    ratio,
                    threshold,
                )
                continue

            y0 = srgb_to_y(*colors[0])
            y1 = srgb_to_y(*colors[1])
            lc = round(apca_contrast(y0, y1), 1)
            issue.why_technical = (issue.why_technical or "") + (
                f" [Contraste verificado: {ratio}:1 (limite {threshold}:1) | APCA Lc: {lc}]"
            )
            if has_complex_bg:
                issue.why_technical = (issue.why_technical or "") + (
                    " [Revisão manual recomendada: O elemento utiliza imagem de fundo, gradiente ou opacidade que impossibilita o cálculo exato]"
                )
            kept.append(issue)
            continue

        # Caminho 2 -- CSS-fonte, anotacao-apenas (nunca remove).
        if rules and not has_complex_bg:
            pair = _source_color_pair(issue, rules)
            if pair is not None:
                ratio = round(contrast_ratio_rgb(pair[0], pair[1]), 2)
                if ratio < threshold:
                    y_txt = srgb_to_y(*pair[0])
                    y_bg = srgb_to_y(*pair[1])
                    lc = round(apca_contrast(y_txt, y_bg), 1)
                    issue.why_technical = (issue.why_technical or "") + (
                        f" [Contraste verificado (CSS): {ratio}:1 (limite {threshold}:1) | APCA Lc: {lc}]"
                    )
        elif has_complex_bg:
            issue.why_technical = (issue.why_technical or "") + (
                " [Revisão manual recomendada: O elemento utiliza imagem de fundo, gradiente ou opacidade que impossibilita o cálculo exato]"
            )

        kept.append(issue)

    return kept, removed
