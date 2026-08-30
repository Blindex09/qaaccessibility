"""Falha do motor de PDF tem de ser legivel e chegar antes do trabalho caro.

Bug real (2026-08-30): num Windows sem GTK, GET /export/last_checklist_pdf
rodava o ChecklistAgent inteiro -- ~50 segundos de LLM pago -- e so entao
tentava gerar o PDF, estourando com

    cannot load library 'libgobject-2.0-0': error 0x7e

capturado por um `except Exception` generico que devolvia
500 "Falha ao gerar PDF do checklist." O usuario nao ficava sabendo que
faltava uma biblioteca NATIVA, nem o que instalar, e ainda pagava a chamada.

Nota de ambiente: nesta maquina a falha acontece no IMPORT do weasyprint (o
FFI resolve as libs na importacao), nao na renderizacao -- por isso os testes
nao fazem patch em `weasyprint.HTML`: o modulo nem chega a ser importavel.
Faz-se patch no proprio `motor_pdf_disponivel`, que e o contrato que as rotas
consomem.
"""

from unittest.mock import patch

import pytest

from backend.src.services import pdf_engine
from backend.src.services.pdf_engine import (
    INSTRUCOES_INSTALACAO,
    MotorPdfIndisponivelError,
    exigir_motor_pdf,
    motor_pdf_disponivel,
)


@pytest.fixture(autouse=True)
def _limpa_cache():
    motor_pdf_disponivel.cache_clear()
    yield
    motor_pdf_disponivel.cache_clear()


def test_motor_ausente_vira_erro_com_instrucao_acionavel():
    causa = "OSError: cannot load library 'libgobject-2.0-0': error 0x7e"
    with patch.object(
        pdf_engine, "motor_pdf_disponivel", return_value=(False, causa)
    ), pytest.raises(MotorPdfIndisponivelError) as capturado:
        exigir_motor_pdf()

    mensagem = str(capturado.value)
    # O que instalar, em cada sistema -- nao so "falhou".
    assert "GTK3" in mensagem, "precisa dizer o que instalar no Windows"
    assert "apt-get" in mensagem, "precisa dizer o que instalar no Linux"
    assert "brew" in mensagem, "precisa dizer o que instalar no macOS"
    # E a causa tecnica, para quem for depurar.
    assert "libgobject" in mensagem
    # E o que CONTINUA funcionando -- falha parcial nao pode parecer falha total.
    assert "XLSX" in mensagem


def test_motor_disponivel_nao_levanta():
    with patch.object(pdf_engine, "motor_pdf_disponivel", return_value=(True, "")):
        exigir_motor_pdf()  # nao levanta


def test_checagem_real_devolve_par_bool_motivo():
    """Contrato de `motor_pdf_disponivel` nesta maquina, seja qual for o caso."""
    disponivel, motivo = motor_pdf_disponivel()

    assert isinstance(disponivel, bool)
    assert isinstance(motivo, str)
    # Indisponivel SEMPRE traz motivo; disponivel nunca inventa um.
    assert bool(motivo) is not disponivel


def test_instrucoes_cobrem_os_tres_sistemas():
    for esperado in ("Windows", "Debian/Ubuntu", "macOS"):
        assert esperado in INSTRUCOES_INSTALACAO
