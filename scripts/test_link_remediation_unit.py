"""
scripts/test_link_remediation_unit.py
Testa a integração da sanitização semântica de links no backend.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.src.services.chat_tools as ct

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

html_sample = """
<div>
  <a href="https://www.Facebook.com/test" aria-label="Ir para https://www.Facebook.com/test"><img src="fb.png" alt="Facebook"></a>
  <a href="https://whatsapp.com/channel/123" aria-label="Ir para https://whatsapp.com/channel/123"></a>
  <a href="https://drupal-admin.com" target="_blank"><img src="drupal.svg" alt="Drupal Admin"></a>
  <a href="https://mega.nz" target="_blank"><img src="mega.png" alt="Mega Cloud"></a>
</div>
"""

res, notes = ct._sanitize_accessible_links_and_labels(html_sample)
print("=== RESULTADO DA SANITIZAÇÃO NO BACKEND ===")
print(res.strip())
print("\n=== NOTAS REGISTRADAS ===")
for n in notes:
    print("-", n)

assert "Ir para https://" not in res, "Erro: URL crua ainda presente no aria-label"
assert "Página do Facebook" in res, "Erro: Facebook não humanizado"
assert "Canal do WhatsApp" in res, "Erro: WhatsApp não humanizado"
assert "Drupal Admin (abre em nova janela)" in res, "Erro: Alvo com target _blank sem aviso de nova janela"
print("\n[SUCESSO] Todas as asserções de acessibilidade no projeto qaaccessibility passaram com 100% de conformidade!")
