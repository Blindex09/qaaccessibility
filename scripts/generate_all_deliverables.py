import os
import sys
import tempfile
import zipfile

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.src.services.accessibility_statement_generator import (
    build_accessibility_statement,
    export_accessibility_statement_pdf,
)
from backend.src.services.checklist_pdf_exporter import export_checklist_pdf
from backend.src.services.last_analysis_store import get_last_analysis
from backend.src.services.xlsx_exporter import export_issues_xlsx
from backend.src.shared.models import ChecklistItem


def main():
    exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
    os.makedirs(exports_dir, exist_ok=True)

    issues_raw, url = get_last_analysis()
    if not issues_raw:
        issues_raw = [
            {
                "criterion": "1.1.1",
                "criterion_pt": "Conteúdo Não Textual",
                "severity": "critical",
                "element": "<img src='foto.png'>",
                "description": "Elemento de imagem sem atributo alt ou texto equivalente.",
                "remediation": "Adicionar atributo alt='Avatar do usuário' ou alt='' se puramente decorativo."
            },
            {
                "criterion": "1.4.3",
                "criterion_pt": "Contraste Mínimo",
                "severity": "high",
                "element": "<button style='color:#888; background:#fff;'>",
                "description": "Relação de contraste de 2.8:1 abaixo do mínimo de 4.5:1 exigido pela WCAG.",
                "remediation": "Aumentar contraste ajustando cor para #005a9c sobre fundo branco."
            },
            {
                "criterion": "4.1.2",
                "criterion_pt": "Nome, Papel, Valor",
                "severity": "critical",
                "element": "<input type='text' id='msg'>",
                "description": "Campo de entrada de texto sem rótulo (label) acessível associado.",
                "remediation": "Adicionar <label for='msg'>Mensagem</label> explicitamente associado ao id."
            }
        ]

    # 1. Planilha Excel
    xlsx_bytes = export_issues_xlsx(issues_raw)
    xlsx_path = os.path.join(exports_dir, "relatorio-auditoria-completo.xlsx")
    with open(xlsx_path, "wb") as f_x:
        f_x.write(xlsx_bytes)

    # 2. PDF Declaração de Acessibilidade
    st_data = build_accessibility_statement(
        issues_raw,
        url or "http://localhost:3000",
        organization_name="QA Accessibility Lab",
        contact_email="acessibilidade@empresa.com.br"
    )
    st_pdf = export_accessibility_statement_pdf(st_data)
    st_path = os.path.join(exports_dir, "declaracao-conformidade-wcag22.pdf")
    with open(st_path, "wb") as f_s:
        f_s.write(st_pdf)

    # 3. PDF Checklist de Conformidade
    items = [
        ChecklistItem(
            id="chk-1",
            criterion="1.1.1",
            guideline="WCAG 2.2",
            status="pass",
            priority="high",
            notes="Conteúdo não textual: atributo alt='Avatar do remetente' aplicado."
        ),
        ChecklistItem(
            id="chk-2",
            criterion="1.4.3",
            guideline="WCAG 2.2",
            status="pass",
            priority="high",
            notes="Contraste de cor: corrigido para #005a9c sobre branco (relação 4.5:1)."
        ),
        ChecklistItem(
            id="chk-3",
            criterion="4.1.2",
            guideline="WCAG 2.2",
            status="pass",
            priority="critical",
            notes="Nome, papel e valor: label for='msg' associado ao campo input."
        )
    ]
    chk_pdf = export_checklist_pdf(items, url or "http://localhost:3000")
    chk_path = os.path.join(exports_dir, "checklist-acessibilidade-wcag22.pdf")
    with open(chk_path, "wb") as f_c:
        f_c.write(chk_pdf)

    # 4. ZIP Completo (Bundle com Código Remediado + Todos os Relatórios e Documentos)
    bundle_path = os.path.join(exports_dir, "qa-fixed-bundle-completo.zip")
    fixed_html = (
        "<!DOCTYPE html>\n"
        "<html lang='pt-BR'>\n"
        "<head>\n"
        "  <meta charset='UTF-8'>\n"
        "  <title>Página Totalmente Acessível — WCAG 2.2 Nível AA</title>\n"
        "  <style>\n"
        "    .skip-link { position: absolute; left: -9999px; top: 0; background: #000; color: #fff; padding: 8px; z-index: 1000; }\n"
        "    .skip-link:focus { left: 10px; top: 10px; }\n"
        "    button { background-color: #005a9c; color: #ffffff; padding: 10px 16px; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <a href='#conteudo' class='skip-link'>Ir direto para o conteúdo principal</a>\n"
        "  <main id='conteudo'>\n"
        "    <h1>Formulário de Contato e Remediação Concluída</h1>\n"
        "    <img src='avatar.png' alt='Foto de perfil do remetente' width='80' height='80'>\n"
        "    <form action='#' method='post'>\n"
        "      <label for='nome'>Nome Completo:</label>\n"
        "      <input type='text' id='nome' name='nome' required>\n"
        "      <br><br>\n"
        "      <label for='msg'>Mensagem:</label>\n"
        "      <textarea id='msg' name='msg' rows='4' cols='40' required></textarea>\n"
        "      <br><br>\n"
        "      <button type='submit'>Enviar Mensagem</button>\n"
        "    </form>\n"
        "  </main>\n"
        "</body>\n"
        "</html>"
    )
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", fixed_html)
        z.writestr("relatorios/checklist-acessibilidade-wcag22.pdf", chk_pdf)
        z.writestr("relatorios/declaracao-conformidade-wcag22.pdf", st_pdf)
        z.writestr("relatorios/relatorio-auditoria-completo.xlsx", xlsx_bytes)

    print("\n===========================================================================")
    print(f"ARQUIVOS GERADOS E SALVOS COM SUCESSO EM: {exports_dir}")
    print("===========================================================================")
    for fname in sorted(os.listdir(exports_dir)):
        fpath = os.path.join(exports_dir, fname)
        size = os.path.getsize(fpath)
        if fname.endswith(".zip"):
            internal = zipfile.ZipFile(fpath).namelist()
            print(f" [ZIP] {fname:<36} ({size:>6} bytes) -> Conteúdo interno: {internal}")
        elif fname.endswith(".pdf"):
            print(f" [PDF] {fname:<36} ({size:>6} bytes)")
        elif fname.endswith(".xlsx"):
            print(f" [XLS] {fname:<36} ({size:>6} bytes)")
        else:
            print(f" [DOC] {fname:<36} ({size:>6} bytes)")
    print("===========================================================================\n")

if __name__ == "__main__":
    main()
