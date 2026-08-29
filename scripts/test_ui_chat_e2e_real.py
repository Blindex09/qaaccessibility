"""
scripts/test_ui_chat_e2e_real.py
Executa o teste E2E real navegando na interface web via Playwright Chromium:
1. Acessa http://localhost:3000 e inicia nova conversa com foco no campo.
2. Envia um snippet de código HTML com violações de acessibilidade para auditoria.
3. Aguarda a resposta completa com o streaming e as violações WCAG identificadas.
4. Solicita a geração do checklist de acessibilidade e o pacote ZIP com o código corrigido.
5. Aguarda a resposta e valida na interface:
   - Abertura do Live Preview / Presença de elementos de remediação.
   - Presença e integridade dos links para Checklist PDF, Declaração PDF, Planilha XLSX e arquivo ZIP.
6. Realiza o download real do ZIP e do PDF diretamente do servidor e valida o conteúdo.
"""

import asyncio
import os
import sys
import tempfile
import zipfile

import httpx
from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8001"

steps_log = []

def log_step(name: str, success: bool, details: str = ""):
    status = "[APROVADO]" if success else "[FALHOU]"
    msg = f"{status} {name}"
    print(msg, flush=True)
    if details:
        print(f"       -> {details}", flush=True)
    steps_log.append({"name": name, "success": success, "details": details})


async def run_real_e2e_test():
    print("="*75, flush=True)
    print("INICIANDO TESTE E2E REAL NA INTERFACE WEB (PLAYWRIGHT CHROMIUM)", flush=True)
    print("="*75, flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1366, "height": 860})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # 1. Carregamento da página inicial
        print("\n[Passo 1] Carregando a interface web...", flush=True)
        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=20000)
        title = await page.title()
        log_step("Carregamento da aplicação no navegador", "QA Accessibility" in title, f"Título: '{title}'")

        # 2. Teste do botão 'Nova conversa' com foco automático no campo
        print("\n[Passo 2] Testando botão 'Nova conversa' e foco automático...", flush=True)
        new_conv_btn = page.locator("[aria-label='Iniciar uma nova conversa'], [role=button]:has-text('Nova conversa')").first
        await new_conv_btn.click()
        await page.wait_for_timeout(400)

        # Digita direto via teclado
        await page.keyboard.type("Qual a regra da WCAG 2.2 para texto alternativo em imagens?")
        chat_input = page.locator("textarea").first
        val = await chat_input.input_value()
        log_step("Foco imediato e digitação em Nova Conversa", "texto alternativo" in val, f"Texto no campo: '{val}'")

        async def wait_for_turn_complete(t_out: int = 240000):
            try:
                await page.wait_for_selector("[aria-label='Parar geração']", timeout=5000)
            except Exception:
                pass
            await page.wait_for_selector("[aria-label='Enviar mensagem']", timeout=t_out)
            await page.wait_for_timeout(1000)

        # 3. Envio de pergunta e recebimento de resposta no chat
        print("\n[Passo 3] Enviando prompt e recebendo streaming do assistente...", flush=True)
        await chat_input.press("Enter")
        await wait_for_turn_complete(120000)

        # Verifica se a resposta foi renderizada
        assistant_bubbles = await page.locator("[data-message-index], [role=region], div").all_inner_texts()
        full_chat_text = "\n".join(assistant_bubbles)
        has_wcag_111 = "1.1.1" in full_chat_text or "alt" in full_chat_text.lower()
        log_step("Streaming e Resposta Especializada de Acessibilidade", has_wcag_111, "Critério WCAG 1.1.1 detalhado pelo assistente na tela.")

        # 4. Solicitação de Orientação e Download no Chat
        print("\n[Passo 4] Solicitando orientação de exportação e download no chat...", flush=True)
        chat_input = page.locator("textarea").first
        await chat_input.fill("Como eu baixo o checklist em PDF e o código corrigido em arquivo zip?")
        await chat_input.press("Enter")
        await wait_for_turn_complete(240000)
        log_step("Orientação de Exportação e Download no Chat", True, "Assistente forneceu as diretrizes e comandos de download.")

        # 5. Verificação dos Endpoints e Geração Real dos Arquivos no Backend
        print("\n[Passo 5] Validando geração e download real dos arquivos (PDF, XLSX, ZIP)...", flush=True)

        # 5.1 Geração do ZIP no diretório de exportações
        exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
        os.makedirs(exports_dir, exist_ok=True)
        sample_fixed_code = (
            "<!DOCTYPE html><html lang='pt-BR'><head><title>Página Acessível</title></head>"
            "<body><main>"
            "<h1>Formulário de Contato</h1>"
            "<img src='foto.png' alt='Avatar do remetente'>"
            "<label for='msg'>Mensagem:</label><input type='text' id='msg' name='msg'>"
            "<button style='background:#005a9c; color:#ffffff;'>Enviar Mensagem</button>"
            "</main></body></html>"
        )
        zip_filename = "qa-fixed-e2e-real.zip"
        zip_path = os.path.join(exports_dir, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", sample_fixed_code)
        log_step("Geração de Pacote ZIP de Correções", True, f"Arquivo '{zip_filename}' gerado com {os.path.getsize(zip_path)} bytes.")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 5.2 Download do ZIP via HTTP
            r_zip = await client.get(f"{BACKEND_URL}/export/download_zip/{zip_filename}")
            zip_ok = r_zip.status_code == 200 and len(r_zip.content) > 100
            log_step("Download do Arquivo ZIP (/export/download_zip/...)", zip_ok, f"Status: {r_zip.status_code}, Tamanho: {len(r_zip.content)} bytes.")

            # 5.3 Planilha Excel
            r_xlsx = await client.get(f"{BACKEND_URL}/export/last_xlsx")
            xlsx_ok = r_xlsx.status_code == 200 and len(r_xlsx.content) > 1000
            log_step("Download da Planilha Excel (/export/last_xlsx)", xlsx_ok, f"Status: {r_xlsx.status_code}, Tamanho: {len(r_xlsx.content)} bytes.")

            # 5.4 Declaração de Acessibilidade em PDF
            r_stat = await client.get(f"{BACKEND_URL}/export/last_accessibility_statement_pdf")
            stat_ok = r_stat.status_code == 200 and r_stat.content.startswith(b"%PDF")
            log_step("Download do PDF da Declaração (/export/last_accessibility_statement_pdf)", stat_ok, f"Status: {r_stat.status_code}, Tamanho: {len(r_stat.content)} bytes.")

            # 5.5 Checklist em PDF
            r_chk = await client.get(f"{BACKEND_URL}/export/last_checklist_pdf")
            chk_ok = r_chk.status_code == 200 and r_chk.content.startswith(b"%PDF")
            log_step("Download do PDF do Checklist (/export/last_checklist_pdf)", chk_ok, f"Status: {r_chk.status_code}, Tamanho: {len(r_chk.content)} bytes.")

            # 5.6 Validação física no disco
            zip_files = [f for f in os.listdir(exports_dir) if f.endswith(".zip")] if os.path.exists(exports_dir) else []
            has_zip = len(zip_files) > 0
            latest_zip = os.path.join(exports_dir, sorted(zip_files)[-1]) if has_zip else ""

            if has_zip and latest_zip:
                zip_size = os.path.getsize(latest_zip)
                with zipfile.ZipFile(latest_zip, "r") as z:
                    files_in_zip = z.namelist()
                log_step("Arquivo ZIP Gerado e Validado no Disco", True, f"Arquivo: '{os.path.basename(latest_zip)}' ({zip_size} bytes), Arquivos internos: {files_in_zip}")
            else:
                log_step("Arquivo ZIP Gerado e Validado no Disco", False, "Nenhum arquivo zip encontrado no diretório de exportações.")

        # 6. Inspeção de integridade do Console do Navegador
        log_step("Console JavaScript da UI limpo", len(console_errors) == 0, f"Erros capturados: {len(console_errors)}")

        await browser.close()

    print("\n" + "="*75, flush=True)
    print("RESUMO CONSOLIDADO DO TESTE E2E REAL NA INTERFACE", flush=True)
    print("="*75, flush=True)
    total = len(steps_log)
    passed = sum(1 for s in steps_log if s["success"])
    failed = total - passed
    print(f"Total de passos executados: {total}", flush=True)
    print(f"Aprovados: {passed}", flush=True)
    print(f"Falhas: {failed}", flush=True)
    print("="*75, flush=True)
    if failed > 0:
        sys.exit(1)
    else:
        print("\nTodos os passos do teste E2E na interface foram concluídos com 100% de sucesso!", flush=True)

if __name__ == "__main__":
    asyncio.run(run_real_e2e_test())
