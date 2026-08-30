"""Disponibilidade do motor de PDF (WeasyPrint) e falha legível quando falta.

Por que existe: o WeasyPrint carrega Pango/GObject/cairo por FFI já no
`import`. Num Windows sem GTK instalado, `import weasyprint` estoura com

    cannot load library 'libgobject-2.0-0': error 0x7e

(verificado nesta máquina em 2026-08-30: falha no import, não na renderização
-- por isso a checagem cobre as duas etapas.)

As rotas que exportam PDF capturavam isso num `except Exception` genérico e
devolviam 500 "Falha ao gerar PDF do checklist." -- sem dizer que o problema
era uma biblioteca nativa ausente, e portanto sem dizer o que instalar. Pior:
a checagem só acontecia DEPOIS do ChecklistAgent rodar, então o usuário
esperava ~50 segundos de chamada de LLM paga para receber um erro que já era
conhecido antes de começar.

Aqui a checagem é feita uma vez, cacheada, e a mensagem diz exatamente o que
falta e como resolver em cada sistema.
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

INSTRUCOES_INSTALACAO = (
    "A geração de PDF usa WeasyPrint, que carrega Pango, GObject e cairo por FFI. "
    "Essas bibliotecas nativas não estão disponíveis nesta máquina. "
    "Windows: instale o GTK3 runtime (https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer) "
    "e reinicie o backend. "
    "Debian/Ubuntu: sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libcairo2. "
    "macOS: brew install pango cairo gdk-pixbuf libffi. "
    "As demais exportações (XLSX, SARIF, checklist em JSON) não dependem disso e continuam funcionando."
)


class MotorPdfIndisponivelError(RuntimeError):
    """O WeasyPrint não consegue renderizar nesta máquina (libs nativas ausentes)."""


@lru_cache(maxsize=1)
def motor_pdf_disponivel() -> tuple[bool, str]:
    """(disponível, motivo). Cobre import E renderização.

    Onde exatamente falha depende do sistema: no Windows sem GTK, o próprio
    `import weasyprint` estoura (o FFI resolve as libs na importação); em
    outros ambientes o import passa e só a renderização quebra. As duas
    etapas ficam dentro do mesmo try, então qualquer um dos casos vira um
    "indisponível" com motivo legível.

    Cacheado: o resultado não muda durante a vida do processo.
    """
    try:
        from weasyprint import HTML

        HTML(string="<p>x</p>").write_pdf()
    except Exception as exc:  # OSError do ctypes, ImportError, e o que mais vier do FFI
        motivo = f"{type(exc).__name__}: {exc}"
        logger.warning("[PdfEngine] Motor de PDF indisponivel -- %s", motivo)
        return False, motivo
    return True, ""


def exigir_motor_pdf() -> None:
    """Levanta `MotorPdfIndisponivelError` com instrução acionável se faltar.

    Chame ANTES do trabalho caro (agente/LLM): falhar em milissegundos com uma
    mensagem útil é melhor que falhar em 50 segundos com "erro ao gerar PDF".
    """
    disponivel, motivo = motor_pdf_disponivel()
    if not disponivel:
        raise MotorPdfIndisponivelError(f"{INSTRUCOES_INSTALACAO} (causa técnica: {motivo})")
