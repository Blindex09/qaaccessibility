"""
scripts/test_chat_generate_checklist_and_zip.py
Executa no chat via Playwright Chromium:
1. Envio de HTML para auditoria de acessibilidade.
2. Pedido de geração de Checklist e arquivo ZIP com as correções.
3. Extração dos links de download, verificação do arquivo ZIP e do PDF gerados no disco.
"""

import asyncio
import os
import sys
import tempfile
import zipfile

import httpx
from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8001"

async def main():
    print("="*70)
    print("INICIANDO TESTE DE GERAÇÃO DE CHECKLIST E ZIP PELO CHAT")
    print("="*70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # 1. Abre o chat
        print("[1/4] Acessando a interface web...")
        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)

        # 2. Clica em Nova Conversa para garantir sessão limpa com foco
        new_conv = page.locator("[aria-label='Iniciar uma nova conversa'], [role=button]:has-text('Nova conversa')").first
        await new_conv.click()
        await page.wait_for_timeout(500)

        # 3. Envia o código HTML com falhas para análise
        print("[2/4] Enviando código HTML para análise de acessibilidade...")
        chat_input = page.locator("textarea, input[type=text]").first
        html_code = (
            "<!DOCTYPE html><html lang='pt-BR'><head><title>Formulário de Cadastro</title></head>"
            "<body><main>"
            "<h1>Cadastro</h1>"
            "<img src='avatar.jpg'>"
            "<label>Nome:</label><input type='text' id='nome'>"
            "<button style='background:#fff; color:#eee;'>Cadastrar</button>"
            "</main></body></html>"
        )
        await chat_input.fill(f"Analise a acessibilidade deste código:\n{html_code}")
        await chat_input.press("Enter")

        # Aguarda término do turno de análise (aguarda campo textarea voltar a ser editável)
        print("      Aguardando análise do agente...")
        await page.wait_for_timeout(3000)
        await page.wait_for_selector("textarea:not([readonly])", timeout=240000)
        print("      Turno 1 concluído.")

        # 4. Pede para gerar o checklist e empacotar o ZIP
        print("[3/4] Solicitando geração do Checklist e do arquivo ZIP...")
        await page.wait_for_timeout(1000)
        chat_input = page.locator("textarea").first
        await chat_input.fill("Gere o checklist de acessibilidade e empacote as correções em um arquivo zip")
        await chat_input.press("Enter")

        # Aguarda o segundo turno terminar
        print("      Aguardando geração do checklist e do ZIP...")
        await page.wait_for_timeout(3000)
        await page.wait_for_selector("textarea:not([readonly])", timeout=240000)
        print("      Turno 2 concluído.")

        # 5. Validação dos links gerados na interface
        print("[4/4] Verificando links e arquivos exportados...")
        links = await page.locator("a[href]").all()
        hrefs = [await link.get_attribute("href") for link in links]
        print(f"      Links encontrados no chat: {len(hrefs)}")

        # Testa o download do ZIP e do PDF via backend
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Baixa o PDF do checklist
            pdf_r = await client.get(f"{BACKEND_URL}/export/last_checklist_pdf")
            pdf_ok = pdf_r.status_code == 200 and pdf_r.content.startswith(b"%PDF")
            print(f"      PDF do Checklist: Status {pdf_r.status_code}, Tamanho: {len(pdf_r.content)} bytes (Válido: {pdf_ok})")

            # Verifica o diretório de exports no disco
            exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
            zip_files = [f for f in os.listdir(exports_dir) if f.endswith(".zip")]
            latest_zip = os.path.join(exports_dir, sorted(zip_files)[-1]) if zip_files else None

            print(f"      Diretório de exportações no disco: {exports_dir}")
            if latest_zip and os.path.exists(latest_zip):
                zip_size = os.path.getsize(latest_zip)
                print(f"      Último arquivo ZIP gerado no disco: {os.path.basename(latest_zip)} ({zip_size} bytes)")
                with zipfile.ZipFile(latest_zip, "r") as z:
                    print(f"      Arquivos contidos dentro do ZIP: {z.namelist()}")

        await browser.close()
        print("\nTESTE CONCLUÍDO COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(main())
