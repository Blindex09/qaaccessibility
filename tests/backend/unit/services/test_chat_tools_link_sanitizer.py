"""Testes do comportamento REAL de _sanitize_accessible_links_and_labels.

Por que este arquivo existe: `test_chat_tools_fix_preview.py` apenas faz
patch desta funcao (ela e uma dependencia do fluxo que aquele arquivo testa),
entao o comportamento de sanitizacao em si nunca era exercitado pela suite.
As assercoes reais viviam fora do gate, em `scripts/test_link_remediation_unit.py`,
um script solto que ninguem executava no CI -- exatamente a classe de drift que
a pirâmide de verificacao existe para evitar. Promovidas para ca.

Regra de acessibilidade coberta: WCAG 2.4.4 / 2.4.9 (proposito do link) e
3.2.5 (mudanca sob demanda -- avisar quando o link abre em nova janela).
Uma URL crua como nome acessivel e lida caractere a caractere pelo leitor de
tela e nao comunica o destino.
"""

import pytest

from backend.src.services.chat_tools import _sanitize_accessible_links_and_labels


def test_urls_cruas_em_aria_label_nunca_sobrevivem():
    html = (
        '<a href="https://www.Facebook.com/test" aria-label="Ir para https://www.Facebook.com/test">'
        '<img src="fb.png" alt="Facebook"></a>'
    )
    out, _ = _sanitize_accessible_links_and_labels(html)
    assert "Ir para https://" not in out
    assert "aria-label=\"Página do Facebook\"" in out


@pytest.mark.parametrize(
    ("href", "esperado"),
    [
        ("https://www.Facebook.com/test", "Página do Facebook"),
        ("https://whatsapp.com/channel/123", "Canal do WhatsApp"),
        ("https://x.com/perfil", "Perfil do Twitter / X"),
        ("https://instagram.com/perfil", "Perfil do Instagram"),
        ("https://linkedin.com/company/x", "Página do LinkedIn"),
        ("https://t.me/canal", "Canal do Telegram"),
        ("https://youtube.com/@canal", "Canal do YouTube"),
        ("https://github.com/org/repo", "Repositório no GitHub"),
    ],
)
def test_dominios_conhecidos_viram_rotulo_humanizado(href, esperado):
    html = f'<a href="{href}" aria-label="Ir para {href}">x</a>'
    out, _ = _sanitize_accessible_links_and_labels(html)
    assert esperado in out


def test_target_blank_recebe_aviso_de_nova_janela():
    html = '<a href="https://drupal-admin.com" target="_blank"><img src="d.svg" alt="Drupal Admin"></a>'
    out, _ = _sanitize_accessible_links_and_labels(html)
    assert "Drupal Admin (abre em nova janela)" in out


def test_link_vazio_sem_rotulo_herda_alt_da_imagem():
    html = '<a href="https://mega.nz" target="_blank"><img src="m.png" alt="Mega Cloud"></a>'
    out, _ = _sanitize_accessible_links_and_labels(html)
    assert "Mega Cloud (abre em nova janela)" in out


def test_dominio_desconhecido_sem_alt_nem_title_perde_o_aria_label_cru():
    # Melhor nenhum nome acessivel (o leitor cai no href) do que uma URL crua
    # anunciada caractere a caractere como se fosse o proposito do link.
    html = '<a href="https://exemplo-desconhecido.com/x" aria-label="Ir para https://exemplo-desconhecido.com/x">.</a>'
    out, _ = _sanitize_accessible_links_and_labels(html)
    assert "aria-label" not in out


def test_notas_registram_cada_humanizacao():
    html = (
        '<a href="https://www.Facebook.com/test" aria-label="Ir para https://www.Facebook.com/test">a</a>'
        '<a href="https://whatsapp.com/channel/123" aria-label="Ir para https://whatsapp.com/channel/123">b</a>'
    )
    _, notes = _sanitize_accessible_links_and_labels(html)
    assert len(notes) == 2
    assert any("Página do Facebook" in n for n in notes)
    assert any("Canal do WhatsApp" in n for n in notes)


def test_html_sem_links_passa_intacto_e_sem_notas():
    html = "<p>sem links aqui</p>"
    out, notes = _sanitize_accessible_links_and_labels(html)
    assert out == html
    assert notes == []


def test_html_ja_acessivel_nao_e_reescrito():
    html = '<a href="https://exemplo.com" aria-label="Ver preços">Ver preços</a>'
    out, notes = _sanitize_accessible_links_and_labels(html)
    assert out == html
    assert notes == []
