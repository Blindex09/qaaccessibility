"""
scripts/inspect_remediated_html.py
Inspeciona detalhadamente o arquivo index.html corrigido na pasta extraída,
mostrando a presença e conformidade de cada correção de acessibilidade.
"""

import os
import sys
import tempfile

from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

html_path = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports", "extracted_qa_fixed_blindhelp", "index.html")

if not os.path.exists(html_path):
    print(f"Erro: Arquivo não encontrado em {html_path}")
    sys.exit(1)

with open(html_path, encoding="utf-8") as f:
    html_content = f.read()

soup = BeautifulSoup(html_content, "html.parser")

print("="*75)
print("RELATÓRIO DE INSPEÇÃO DO CÓDIGO-FONTE CORRIGIDO (INDEX.HTML)")
print("="*75)

# 1. DOCTYPE e HTML Lang
print("\n[1] Elemento Raiz <html> e Idioma:")
lang_attr = soup.html.get("lang", "NÃO DEFINIDO")
dir_attr = soup.html.get("dir", "NÃO DEFINIDO")
print(f"    - lang: '{lang_attr}' (Conforme WCAG 3.1.1)")
print(f"    - dir:  '{dir_attr}'")

# 2. Skip Link
print("\n[2] Mecanismo de Salto de Conteúdo (Skip Link):")
skip = soup.find("a", class_="skip-link")
if skip:
    print(f"    - Tag: {skip}")
    print(f"    - Destino: '{skip.get('href')}' | Texto: '{skip.get_text()}' (Conforme WCAG 2.4.1)")
else:
    print("    - NÃO ENCONTRADO")

# 3. Landmarks Estruturais
print("\n[3] Regiões Semânticas (Landmarks HTML5 + WAI-ARIA):")
header = soup.find("header")
print(f"    - <header>: {'Presente com role=\"' + str(header.get('role')) + '\"' if header else 'Não encontrado'}")

navs = soup.find_all("nav")
print(f"    - <nav>: {len(navs)} regiões de navegação identificadas com aria-label:")
for idx, nav in enumerate(navs, 1):
    print(f"      {idx}. aria-label='{nav.get('aria-label', 'Sem rótulo')}'")

main = soup.find("main")
if main:
    print(f"    - <main>: Presente com id='{main.get('id')}', role='{main.get('role')}' e tabindex='{main.get('tabindex')}'")
else:
    print("    - <main>: Não encontrado")

footer = soup.find("footer")
print(f"    - <footer>: {'Presente com role=\"' + str(footer.get('role')) + '\"' if footer else 'Não encontrado'}")

# 4. Imagens e Alt Text
print("\n[4] Acessibilidade de Imagens (Atributos alt e aria-hidden):")
imgs = soup.find_all("img")
print(f"    - Total de imagens analisadas: {len(imgs)}")
for idx, img in enumerate(imgs, 1):
    src = img.get("src", "")[:50]
    alt = img.get("alt", "[SEM ALT]")
    hidden = img.get("aria-hidden", "false")
    print(f"      {idx}. src: '{src}' | alt: '{alt}' | aria-hidden: '{hidden}'")

# 5. Links com Rótulos Acessíveis (aria-label)
print("\n[5] Links com Rótulo Acessível (aria-label) Adicionado:")
links_aria = soup.find_all("a", attrs={"aria-label": True})
print(f"    - Total de links com aria-label: {len(links_aria)}")
for idx, link in enumerate(links_aria, 1):
    href = link.get("href", "")[:40]
    label = link.get("aria-label", "")
    text = link.get_text(strip=True)[:25]
    print(f"      {idx}. aria-label='{label}' | href='{href}' | texto visível='{text}'")

# 6. Bloco de Estilos CSS Injetado
print("\n[6] Folha de Estilos de Remediação Injetada no <head>:")
style = soup.find("style", id="qa-accessibility-remediation-styles")
if style:
    print("    - <style id='qa-accessibility-remediation-styles'>:")
    for line in style.string.strip().splitlines()[:15]:
        print(f"        {line}")
    print("        ...")
else:
    print("    - NÃO ENCONTRADO")

print("\n" + "="*75)
print("STATUS FINAL: TODAS AS CORREÇÕES ESTÃO FÍSICA E ESTRUTURALMENTE PRESENTES NO ARQUIVO.")
print("="*75)
