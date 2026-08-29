"""
Advanced Perceptual Contrast Algorithm (APCA) - Versão 0.98G-4g.
Implementação em Python puro compatível com a especificação de contraste do WCAG 3.0 draft.
"""

# Constantes do Modelo G-4g (expoente 2.4)
MAIN_TRC = 2.4
SR_CO = 0.2126729
SG_CO = 0.7151522
SB_CO = 0.0721750

NORM_BG = 0.56
NORM_TXT = 0.57
REV_TXT = 0.62
REV_BG = 0.65

BLK_THRS = 0.022
BLK_CLMP = 1.414
SCALE_BOW = 1.14
SCALE_WOB = 1.14
LO_BOW_OFFSET = 0.027
LO_WOB_OFFSET = 0.027
DELTA_Y_MIN = 0.0005
LO_CLIP = 0.1


def srgb_to_y(r: int, g: int, b: int) -> float:
    """
    Converte canais sRGB (0-255) para luminância linear Y adaptada ao APCA.
    """
    # Garante limites
    r_val = max(0.0, min(255.0, float(r)))
    g_val = max(0.0, min(255.0, float(g)))
    b_val = max(0.0, min(255.0, float(b)))

    def simple_exp(chan: float) -> float:
        return (chan / 255.0) ** MAIN_TRC

    return SR_CO * simple_exp(r_val) + SG_CO * simple_exp(g_val) + SB_CO * simple_exp(b_val)


def apca_contrast(txt_y: float, bg_y: float) -> float:
    """
    Calcula o contraste de luminância Lc (Lightness Contrast) entre texto e fundo.
    Retorna um float assinalado de aproximadamente -108 e 106.
      - Valores negativos indicam polaridade inversa (texto claro em fundo escuro).
      - Valores positivos indicam polaridade normal (texto escuro em fundo claro).
    """
    # Garante limites Y (0.0 a 1.1 para possíveis overflows)
    txt_y = max(0.0, min(1.1, txt_y))
    bg_y = max(0.0, min(1.1, bg_y))

    # Softtoe: compressão de pretos para compensar luz difusa/flare
    txt_y_clamped = txt_y if txt_y > BLK_THRS else txt_y + (BLK_THRS - txt_y) ** BLK_CLMP
    bg_y_clamped = bg_y if bg_y > BLK_THRS else bg_y + (BLK_THRS - bg_y) ** BLK_CLMP

    # Retorna 0 early para diferenças imperceptíveis
    if abs(bg_y_clamped - txt_y_clamped) < DELTA_Y_MIN:
        return 0.0

    if bg_y_clamped > txt_y_clamped:
        # Polaridade Normal (BoW)
        sapc = ((bg_y_clamped**NORM_BG) - (txt_y_clamped**NORM_TXT)) * SCALE_BOW
        output_contrast = 0.0 if sapc < LO_CLIP else sapc - LO_BOW_OFFSET
    else:
        # Polaridade Inversa (WoB)
        sapc = ((bg_y_clamped**REV_BG) - (txt_y_clamped**REV_TXT)) * SCALE_WOB
        output_contrast = 0.0 if sapc > -LO_CLIP else sapc + LO_WOB_OFFSET

    return output_contrast * 100.0
