"""
Toolset de dominio de acessibilidade registrado no engine agentica do projeto.

Expoe ferramentas DETERMINISTICAS que os leaf subagents podem chamar para
verificar hipoteses em vez de adivinhar. A primeira e o calculo de contraste
WCAG (criterios 1.4.3 e 1.4.11) -- exatamente onde um LLM costuma alucinar
o ratio. A funcao e Python puro: sem rede, sem I/O, sem risco de seguranca.

Registrado via tools.registry.registry.register() (tools/registry.py, local
a este projeto).

Idempotente: registrar o mesmo nome sob o mesmo toolset apenas sobrescreve a
entrada, entao importar este modulo multiplas vezes e seguro.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

A11Y_TOOLSET = "a11y_tools"

# Cores nomeadas CSS mais comuns em verificacao de contraste. Lista minima e
# tecnica (não e vocabulario de dominio que condicione a IA) -- apenas mapeia
# nomes para RGB para o calculo deterministico.
_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "transparent": (255, 255, 255),
}


def parse_color(value: str) -> tuple[int, int, int]:
    """
    Converte uma cor CSS (#rgb, #rrggbb, rgb()/rgba(), nome) para RGB 0-255.
    Levanta ValueError em entrada não reconhecida.
    """
    raw = value.strip().lower()

    if raw in _NAMED_COLORS:
        return _NAMED_COLORS[raw]

    if raw.startswith("#"):
        hex_digits = raw[1:]
        if len(hex_digits) == 3:
            r, g, b = (int(c * 2, 16) for c in hex_digits)
            return (r, g, b)
        if len(hex_digits) == 6:
            r = int(hex_digits[0:2], 16)
            g = int(hex_digits[2:4], 16)
            b = int(hex_digits[4:6], 16)
            return (r, g, b)
        raise ValueError(f"Hex color invalido: {value!r}")

    if raw.startswith("rgb"):
        inside = raw[raw.find("(") + 1 : raw.find(")")]
        parts = [p.strip() for p in inside.split(",")]
        if len(parts) < 3:
            raise ValueError(f"rgb() invalido: {value!r}")
        r, g, b = (int(round(float(p))) for p in parts[:3])
        if not all(0 <= c <= 255 for c in (r, g, b)):
            raise ValueError(f"Canal RGB fora de 0-255: {value!r}")
        return (r, g, b)

    raise ValueError(f"Cor não reconhecida: {value!r}")


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Luminancia relativa WCAG 2.x de uma cor RGB 0-255."""
    channels: list[float] = []
    for c in rgb:
        srgb = c / 255.0
        linear = srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4
        channels.append(linear)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio_rgb(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Ratio de contraste WCAG entre duas cores RGB (simetrico, 1.0 a 21.0)."""
    la = _relative_luminance(a)
    lb = _relative_luminance(b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_ratio(foreground: str, background: str) -> float:
    """Ratio de contraste WCAG entre duas cores (1.0 a 21.0)."""
    return contrast_ratio_rgb(parse_color(foreground), parse_color(background))


def compute_contrast(args: dict[str, Any], **_kw: Any) -> str:
    """
    Handler da tool `compute_contrast`. Recebe foreground/background e retorna
    JSON com o ratio exato e os veredictos WCAG por nivel/tamanho de texto.
    """
    foreground = str(args.get("foreground", "")).strip()
    background = str(args.get("background", "")).strip()

    if not foreground or not background:
        return json.dumps(
            {"error": "foreground e background sao obrigatórios"},
            ensure_ascii=True,
        )

    try:
        ratio = contrast_ratio(foreground, background)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=True)

    rounded = round(ratio, 2)
    result = {
        "foreground": foreground,
        "background": background,
        "ratio": rounded,
        "passes_aa_normal": rounded >= 4.5,
        "passes_aa_large": rounded >= 3.0,
        "passes_aaa_normal": rounded >= 7.0,
        "passes_aaa_large": rounded >= 4.5,
        "thresholds": {"aa_normal": 4.5, "aa_large": 3.0, "aaa_normal": 7.0, "aaa_large": 4.5},
    }
    return json.dumps(result, ensure_ascii=True)


_COMPUTE_CONTRAST_SCHEMA: dict[str, Any] = {
    "description": (
        "Compute the exact WCAG contrast ratio between two colors. Use this to "
        "VERIFY any 1.4.3 (Contrast Minimum) or 1.4.11 (Non-text Contrast) "
        "finding before reporting it -- never estimate a ratio by eye. Accepts "
        "hex (#fff, #ffffff), rgb()/rgba(), or common color names. Returns the "
        "ratio and pass/fail for AA/AAA at normal and large text sizes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "foreground": {
                "type": "string",
                "description": "Text/foreground color (e.g. '#777', 'rgb(119,119,119)', 'gray').",
            },
            "background": {
                "type": "string",
                "description": "Background color behind the foreground.",
            },
        },
        "required": ["foreground", "background"],
    },
}


def register_a11y_tools() -> None:
    """
    Registra o toolset de acessibilidade no registry local de tools. Falha
    graceful: se o registry não estiver disponivel, loga e segue (sub-agentes
    leaf continuam funcionando sem a tool).
    """
    try:
        from tools.registry import registry
    except Exception as exc:  # pragma: no cover - registry indisponivel
        logger.warning("[a11y_tools] tools.registry indisponivel, tools não registradas: %s", exc)
        return

    registry.register(
        name="compute_contrast",
        toolset=A11Y_TOOLSET,
        schema=_COMPUTE_CONTRAST_SCHEMA,
        handler=compute_contrast,
        is_async=False,
        emoji="",
    )
    logger.info("[a11y_tools] toolset '%s' registrado (compute_contrast)", A11Y_TOOLSET)


# Registro em import-time (side-effect), padrão dos demais tool files deste projeto.
register_a11y_tools()
