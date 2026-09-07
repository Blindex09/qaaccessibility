"""
screen_reader_verification.py
Verifica anuncios de leitor de tela cruzando a arvore de acessibilidade REAL
do navegador (Chromium/CDP via browser.py::fetch_accessibility_tree_nodes --
a mesma API que NVDA/JAWS/Narrator consultam no Windows) contra regras
deterministicas de nome acessivel ausente ou generico, e opcionalmente valida
interacoes de teclado e mudancas na arvore de acessibilidade.

Por que a arvore real em vez do NVDA capturando a propria fala: o NVDA nao
expoe API oficial para "o que foi realmente anunciado" (isso exigiria um
add-on Python rodando dentro do processo do NVDA, fora do escopo seguro de
automacao externa). A arvore de acessibilidade do Chromium e a mesma fonte
que qualquer leitor de tela real consulta -- um no sem nome aqui e uma
violacao confirmada pelo motor de acessibilidade do proprio SO, nao uma
suposicao da IA a partir do HTML bruto.
"""

import logging
from dataclasses import dataclass, field

from backend.src.services.browser import (
    AccessibilityTreeNode,
    fetch_accessibility_tree_nodes,
    run_accessibility_interaction_audit,
)

logger = logging.getLogger(__name__)

# Nomes genericos que nao descrevem a acao/destino real -- um leitor de tela
# anuncia literalmente essas palavras, que nao ajudam o usuario a decidir se
# deve ativar o controle. Bilingue (PT/EN) porque a arvore real reflete o
# idioma real da pagina auditada.
_GENERIC_NAMES = frozenset(
    {
        "button",
        "link",
        "click here",
        "clique aqui",
        "clique",
        "saiba mais",
        "read more",
        "here",
        "aqui",
        "more",
        "mais",
        "ok",
        "submit",
        "enviar",
        "menu",
        "icon",
        "icone",
    }
)

@dataclass(frozen=True)
class ScreenReaderFinding:
    """Um problema de anuncio confirmado pela arvore de acessibilidade real
    (nao uma suposicao de LLM sobre o HTML bruto)."""

    role: str
    path: str
    problem: str
    severity: str  # "critical" | "high" -- ver shared.models.Severity
    announcement_preview: str  # o que um leitor de tela anunciaria hoje


def _classify_node(node: AccessibilityTreeNode) -> ScreenReaderFinding | None:
    if not node.is_interactive:
        return None
    name = node.name.strip()
    if not name:
        return ScreenReaderFinding(
            role=node.role,
            path=node.path,
            severity="critical",
            problem=(
                "Sem nome acessivel -- o leitor de tela anuncia so o papel "
                "do controle, sem indicar o que ele faz ou para onde leva."
            ),
            announcement_preview=node.role,
        )
    if name.lower() in _GENERIC_NAMES:
        return ScreenReaderFinding(
            role=node.role,
            path=node.path,
            severity="high",
            problem=f'Nome acessivel generico ("{name}") -- nao descreve a acao nem o destino real.',
            announcement_preview=f"{node.role}, {name}",
        )
    return None


def detect_screen_reader_findings(nodes: list[AccessibilityTreeNode]) -> list[ScreenReaderFinding]:
    """Regras deterministicas sobre a arvore REAL -- zero inferencia de IA:
    cada achado e confirmado pelo proprio motor de acessibilidade do navegador,
    nao por um chute do LLM a partir do HTML bruto."""
    findings: list[ScreenReaderFinding] = []
    for node in nodes:
        finding = _classify_node(node)
        if finding is not None:
            findings.append(finding)
    return findings


@dataclass(frozen=True)
class ScreenReaderVerificationResult:
    url: str
    total_interactive_nodes: int
    findings: list[ScreenReaderFinding] = field(default_factory=list)
    # `False` = a arvore de acessibilidade NAO foi capturada (sem Browserless,
    # navegacao falhou, pagina vazia). Sem este campo, uma captura que falhou
    # e uma pagina impecavel produziam exatamente a mesma resposta:
    # "0 nos interativos, 0 achados". Como esta e a unica verificacao do
    # produto sem inferencia de IA, dar "limpo" quando nada foi inspecionado
    # e o pior erro possivel aqui.
    tree_captured: bool = True
    not_verified_reason: str | None = None
    interaction_steps: list[dict[str, object]] = field(default_factory=list)
    interaction_browser_mode: str | None = None


async def verify_screen_reader_announcements(
    url: str,
    *,
    interaction_steps: list[dict[str, object]] | None = None,
) -> ScreenReaderVerificationResult:
    """Captura a arvore real da pagina, roda as regras deterministicas, e
    opcionalmente executa interacoes declarativas de teclado e valida a arvore
    de acessibilidade apos cada passo. A verificacao nao usa audio.

    Quando a arvore nao e capturada (sem BROWSERLESS_WS_URL, navegacao falha,
    pagina sem nos), devolve `tree_captured=False` e `not_verified_reason`
    preenchido, em vez de simplesmente "0 achados" -- que era indistinguivel
    de uma pagina impecavel.
    """
    nodes = await fetch_accessibility_tree_nodes(url)
    findings = detect_screen_reader_findings(nodes)
    interactive_count = sum(1 for node in nodes if node.is_interactive)

    # Arvore vazia NAO e "pagina sem problemas" -- e "nao verifiquei".
    tree_captured = bool(nodes)
    not_verified_reason = (
        None
        if tree_captured
        else (
            "A arvore de acessibilidade real nao foi capturada para esta URL "
            "(BROWSERLESS_WS_URL ausente, navegacao falhou, ou a pagina nao "
            "expos nos). NENHUMA verificacao foi feita: ausencia de achados "
            "aqui nao significa ausencia de problemas."
        )
    )
    if not tree_captured:
        logger.warning("[ScreenReaderVerification] %s: arvore vazia -- nada foi verificado", url)

    interaction_results: list[dict[str, object]] = []
    interaction_browser_mode: str | None = None
    if interaction_steps:
        interaction_audit = await run_accessibility_interaction_audit(url, interaction_steps)
        interaction_browser_mode = interaction_audit.get("browser_mode")
        interaction_results = list(interaction_audit.get("steps") or [])
        if interaction_audit.get("status") != "ok":
            interaction_results = [
                {
                    "index": -1,
                    "action": "interaction_audit",
                    "ok": False,
                    "errors": [interaction_audit.get("error", "Auditoria interativa não executada.")],
                    "focused": None,
                    "tree_captured": bool(interaction_audit.get("tree_captured")),
                }
            ]

    logger.info(
        "[ScreenReaderVerification] %s: %d nos interativos, %d achados, passos interativos=%d",
        url,
        interactive_count,
        len(findings),
        len(interaction_results),
    )
    return ScreenReaderVerificationResult(
        url=url,
        total_interactive_nodes=interactive_count,
        findings=findings,
        tree_captured=tree_captured,
        not_verified_reason=not_verified_reason,
        interaction_steps=interaction_results,
        interaction_browser_mode=interaction_browser_mode,
    )


def finding_to_issue_dict(finding: ScreenReaderFinding, url: str, index: int) -> dict[str, object]:
    """Converte um achado para o mesmo shape de `AccessibilityIssue` (ver
    shared/models.py) -- permite juntar estes achados na mesma lista de issues
    do restante do pipeline (export XLSX/SARIF/VPAT, checklist, etc.) em vez
    de virar um relatorio paralelo que os outros exportadores nao enxergam."""
    return {
        "id": f"sr-verify-{index}",
        "guideline": "WAI-ARIA",
        "criterion": "4.1.2 Name, Role, Value",
        "severity": finding.severity,
        "confidence": "high",
        "element": finding.path,
        "description": finding.problem,
        "description_technical": (
            f"Confirmado pela arvore de acessibilidade real do Chromium (nao estimativa de "
            f"IA): role={finding.role!r}, anuncio atual={finding.announcement_preview!r}."
        ),
        "why_simple": "Quem usa leitor de tela nao vai saber o que esse controle faz.",
        "why_technical": (
            "O motor de acessibilidade do navegador (a mesma API que NVDA/JAWS/Narrator "
            "consultam) computou um Accessible Name vazio ou generico para este no."
        ),
        "suggestion": "Adicione um nome acessivel especifico (texto visivel, aria-label ou aria-labelledby).",
        "url": url,
    }
