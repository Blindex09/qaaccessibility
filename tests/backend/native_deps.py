"""Detecção de dependências nativas opcionais usadas pela suíte.

O WeasyPrint carrega Pango/GObject/cairo por FFI. Essas bibliotecas são
instaláveis via gerenciador de pacotes no Linux (o CI as instala e roda os
testes de PDF de verdade), mas não acompanham o `pip install` no Windows.

Os testes que dependem delas usam `skipif(not WEASYPRINT_AVAILABLE)` para que
sejam pulados apenas quando as libs realmente faltam -- nunca desligados de
forma incondicional só para a suíte "passar".
"""

import pytest


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


WEASYPRINT_AVAILABLE = _weasyprint_available()

requires_weasyprint = pytest.mark.skipif(
    not WEASYPRINT_AVAILABLE,
    reason=(
        "Bibliotecas nativas do WeasyPrint (Pango/GObject/cairo) não estão "
        "instaladas neste ambiente; a geração de PDF não pode ser exercitada."
    ),
)
