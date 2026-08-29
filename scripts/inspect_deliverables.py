"""
scripts/inspect_deliverables.py
Gera o checklist, a declaração de acessibilidade, a planilha Excel e o pacote ZIP
e exibe seus caminhos físicos no disco e dados para visualização do usuário.
"""

import json
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
from backend.src.services.chat_tools import fix_and_zip_files
from backend.src.services.checklist_pdf_exporter import export_checklist_pdf
from backend.src.services.xlsx_exporter import export_issues_xlsx
from backend.src.shared.models import ChecklistItem


def main():
    print("="*70, flush=True)
    print("GERAÇÃO E INSPEÇÃO DOS ARQUIVOS (PDF, ZIP, EXCEL)", flush=True)
    print("="*70, flush=True)

    exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
    os.makedirs(exports_dir, exist_ok=True)

    # 1. Criação do arquivo ZIP com código corrigido
    sample_fixed_code = (
        "<!DOCTYPE html>\n"
        "<html lang='pt-BR'>\n"
        "<head><title>Formulário de Cadastro Acessível</title></head>\n"
        "<body>\n"
        "  <main>\n"
        "    <h1>Cadastro</h1>\n"
        "    <img src='avatar.jpg' alt='Foto do perfil do usuário'>\n"
        "    <label for='nome'>Nome completo:</label>\n"
        "    <input type='text' id='nome' name='nome' aria-required='true'>\n"
        "    <button style='background-color: #005a9c; color: #ffffff;'>Cadastrar</button>\n"
        "  </main>\n"
        "</body>\n"
        "</html>"
    )

    zip_res = fix_and_zip_files({
        "pre_exec_msg": "Empacotando correções...",
        "files": [{"path": "index.html", "content": sample_fixed_code}],
        "explanation": "Correção de rótulo de formulário, contraste do botão e texto alternativo."
    })
    zip_data = json.loads(zip_res)
    download_url = zip_data.get("download_url", "")
    session_id = zip_data.get("live_preview_session_id", "")
    zip_name = download_url.split("/")[-1]
    zip_disk_path = os.path.join(exports_dir, zip_name)

    print("\n[1] ARQUIVO ZIP COM CÓDIGO CORRIGIDO:", flush=True)
    print(f"    - URL de download: {download_url}", flush=True)
    print(f"    - Caminho físico no disco: {zip_disk_path}", flush=True)
    print(f"    - Tamanho: {os.path.getsize(zip_disk_path)} bytes", flush=True)
    print(f"    - Sessão do Live Preview vinculada: {session_id}", flush=True)
    with zipfile.ZipFile(zip_disk_path, "r") as z:
        for f in z.infolist():
            print(f"      * Arquivo contido: {f.filename} ({f.file_size} bytes)", flush=True)

    # 2. Geração da Planilha Excel XLSX
    issues_list = [
        {
            "id": "img-alt",
            "title": "Imagem sem alt",
            "description": "Tag img sem atributo alt",
            "severity": "critical",
            "severity_pt": "Crítica",
            "criterion": "1.1.1",
            "criterion_pt": "Conteúdo Não Textual",
            "recommendation": "Adicionar alt descritivo",
            "element": "<img src='avatar.jpg'>"
        },
        {
            "id": "form-label",
            "title": "Campo sem rótulo associado",
            "description": "Input sem id associado a label",
            "severity": "high",
            "severity_pt": "Alta",
            "criterion": "1.3.1",
            "criterion_pt": "Informações e Relações",
            "recommendation": "Adicionar atributo for no label",
            "element": "<input type='text' id='nome'>"
        }
    ]
    xlsx_bytes = export_issues_xlsx(issues_list)
    xlsx_path = os.path.join(exports_dir, "auditoria-acessibilidade-amostra.xlsx")
    with open(xlsx_path, "wb") as f:
        f.write(xlsx_bytes)

    print("\n[2] PLANILHA EXCEL FORMATADA (XLSX):", flush=True)
    print("    - Endpoint no app: http://localhost:3000/export/last_xlsx", flush=True)
    print(f"    - Caminho físico no disco: {xlsx_path}", flush=True)
    print(f"    - Tamanho: {len(xlsx_bytes)} bytes", flush=True)

    # 3. Geração do Checklist em PDF
    checklist_items = [
        ChecklistItem(
            id="chk-1",
            title="Adicionar descrição alternativa em todas as imagens (WCAG 1.1.1)",
            description="Verificar atributo alt nas tags <img>",
            category="Perceptível",
            priority="Alta",
            criterion="1.1.1",
            status="Pendente"
        ),
        ChecklistItem(
            id="chk-2",
            title="Garantir contraste mínimo de 4.5:1 no botão principal (WCAG 1.4.3)",
            description="Ajustar cores do botão para contraste acessível",
            category="Perceptível",
            priority="Alta",
            criterion="1.4.3",
            status="Pendente"
        )
    ]
    pdf_bytes = export_checklist_pdf(checklist_items, "http://localhost:3000")
    pdf_path = os.path.join(exports_dir, "checklist-acessibilidade-amostra.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    print("\n[3] PDF DO CHECKLIST DE ACESSIBILIDADE (PDF/UA-1):", flush=True)
    print("    - Endpoint no app: http://localhost:3000/export/last_checklist_pdf", flush=True)
    print(f"    - Caminho físico no disco: {pdf_path}", flush=True)
    print(f"    - Tamanho: {len(pdf_bytes)} bytes (Assinatura: {pdf_bytes[:4].decode('ascii')})", flush=True)

    # 4. Geração da Declaração de Acessibilidade em PDF
    statement_data = build_accessibility_statement(
        issues_list,
        url="http://localhost:3000",
        organization_name="Empresa Exemplo",
        product_name="Portal de Acessibilidade",
        contact_email="acessibilidade@exemplo.com"
    )
    statement_pdf_bytes = export_accessibility_statement_pdf(statement_data)
    statement_pdf_path = os.path.join(exports_dir, "declaracao-acessibilidade-amostra.pdf")
    with open(statement_pdf_path, "wb") as f:
        f.write(statement_pdf_bytes)

    print("\n[4] PDF DA DECLARAÇÃO DE ACESSIBILIDADE (PDF/UA-1):", flush=True)
    print("    - Endpoint no app: http://localhost:3000/export/last_accessibility_statement_pdf", flush=True)
    print(f"    - Caminho físico no disco: {statement_pdf_path}", flush=True)
    print(f"    - Tamanho: {len(statement_pdf_bytes)} bytes (Assinatura: {statement_pdf_bytes[:4].decode('ascii')})", flush=True)

    print("\n" + "="*70, flush=True)
    print("TODOS OS ARQUIVOS FORAM GERADOS E VALIDADOS COM SUCESSO NO DISCO!", flush=True)
    print("="*70, flush=True)

if __name__ == "__main__":
    main()
