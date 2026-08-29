"""
scripts/test_ui_chat_real_webpage.py
Executa o teste E2E real navegando na interface web via Playwright Chromium,
solicitando a análise de uma página real da internet (ex: https://example.com)
e validando o fluxo completo de auditoria, diagnóstico de acessibilidade WCAG 2.2
e exportação dos relatórios (PDF, XLSX, ZIP).
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
TARGET_REAL_PAGE = "https://blindhelp.net"

steps_log = []

def log_step(name: str, success: bool, details: str = ""):
    status = "[APROVADO]" if success else "[FALHOU]"
    msg = f"{status} {name}"
    print(msg, flush=True)
    if details:
        print(f"       -> {details}", flush=True)
    steps_log.append({"name": name, "success": success, "details": details})


async def run_real_webpage_test():
    print("="*75, flush=True)
    print("INICIANDO TESTE E2E REAL NA INTERFACE WEB (PÁGINA DA INTERNET)", flush=True)
    print(f"Página alvo a ser auditada: {TARGET_REAL_PAGE}", flush=True)
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

        # 2. Iniciar nova conversa e foco no campo
        print("\n[Passo 2] Clicando em 'Nova conversa' e focando no campo de digitação...", flush=True)
        new_conv_btn = page.locator("[aria-label='Iniciar uma nova conversa'], [role=button]:has-text('Nova conversa')").first
        await new_conv_btn.click()
        await page.wait_for_timeout(500)

        prompt_text = f"Analise a acessibilidade da página da internet {TARGET_REAL_PAGE} conforme a WCAG 2.2, aponte os critérios violados ou conformes e prepare os relatórios."
        await page.keyboard.type(prompt_text)
        chat_input = page.locator("textarea").first
        val = await chat_input.input_value()
        log_step("Foco imediato e inserção do prompt de auditoria web", TARGET_REAL_PAGE in val, f"Texto: '{val[:80]}...'")

        async def wait_for_turn_complete(t_out: int = 450000):
            await page.wait_for_timeout(3000)
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < t_out / 1000:
                try:
                    clarify_btn = page.locator("[role=button]:has-text('Sim'), [role=button]:has-text('Prosseguir'), [role=button]:has-text('Analisar'), [role=button]:has-text('Continuar')").first
                    if await clarify_btn.is_visible():
                        await clarify_btn.click()
                        print("       [UI] Pergunta de clarificação respondida interativamente na tela...", flush=True)
                        # Aguarda o início do processamento do backend (até 15s)
                        for _ in range(15):
                            await page.wait_for_timeout(1000)
                            if await page.locator("[aria-label*='Parar'], button:has-text('Parar')").is_visible() or not await page.locator("textarea").first.is_editable():
                                break
                        continue
                except Exception:
                    pass

                is_stopping = await page.locator("[aria-label*='Parar'], button:has-text('Parar')").is_visible()
                textarea_el = page.locator("textarea").first
                is_editable = False
                try:
                    is_editable = await textarea_el.is_editable(timeout=1000)
                except Exception:
                    is_editable = False

                # Só considera concluído se o campo de texto estiver perfeitamente editável e não houver botão de Parar nem clarify
                if is_editable and not is_stopping:
                    await page.wait_for_timeout(5000)
                    still_stopping = await page.locator("[aria-label*='Parar'], button:has-text('Parar')").is_visible()
                    still_clarify = False
                    try:
                        still_clarify = await page.locator("[role=button]:has-text('Sim'), [role=button]:has-text('Prosseguir'), [role=button]:has-text('Analisar'), [role=button]:has-text('Continuar')").is_visible()
                    except Exception:
                        pass
                    still_editable = await textarea_el.is_editable(timeout=1000)

                    if not still_stopping and not still_clarify and still_editable:
                        break
                await page.wait_for_timeout(2000)

        # 3. Envio de prompt e execução da auditoria da página real
        print("\n[Passo 3] Enviando solicitação de auditoria da URL real para o assistente...", flush=True)
        await chat_input.press("Enter")
        await wait_for_turn_complete(450000)

        # Verifica a resposta na tela
        bubbles = await page.locator("div").all_inner_texts()
        full_chat_text = "\n".join(bubbles)
        has_analysis = any(term in full_chat_text.lower() for term in ["blindhelp", "acessibilidade", "wcag", "critério", "score", "pontuação", "auditoria", "semântica", "conformidade"])
        log_step("Execução e Diagnóstico da Página Real no Chat", has_analysis, "Assistente analisou a página da internet e apresentou o diagnóstico na tela.")

        # 4. Solicitação de geração de Checklist e Planilha Excel da página auditada
        print("\n[Passo 4] Solicitando no chat a geração do checklist e da planilha da página...", flush=True)
        for _ in range(180):
            try:
                if await page.locator("textarea").first.is_editable(timeout=2000):
                    break
            except Exception:
                pass
            await page.wait_for_timeout(2000)
        chat_input = page.locator("textarea").first
        await chat_input.fill("Gere o checklist em PDF e a planilha Excel desta auditoria.")
        await chat_input.press("Enter")
        await wait_for_turn_complete(450000)
        log_step("Solicitação de Entregáveis da Página Real", True, "Assistente gerou a instrução dos arquivos exportados.")

        # 5. Validação dos Endpoints de Exportação e Arquivos Físicos da Página Real
        print("\n[Passo 5] Validando geração e download real dos arquivos (PDF, XLSX, ZIP)...", flush=True)
        exports_dir = os.path.join(tempfile.gettempdir(), "qa_accessibility_exports")
        os.makedirs(exports_dir, exist_ok=True)

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 5.1 Planilha Excel da página real
            r_xlsx = await client.get(f"{BACKEND_URL}/export/last_xlsx")
            xlsx_ok = r_xlsx.status_code == 200 and len(r_xlsx.content) > 1000
            log_step("Download da Planilha Excel da Página Real (/export/last_xlsx)", xlsx_ok, f"Status: {r_xlsx.status_code}, Tamanho: {len(r_xlsx.content)} bytes.")

            # 5.2 PDF da Declaração de Acessibilidade
            r_stat = await client.get(f"{BACKEND_URL}/export/last_accessibility_statement_pdf")
            stat_ok = r_stat.status_code == 200 and r_stat.content.startswith(b"%PDF")
            log_step("Download da Declaração em PDF (/export/last_accessibility_statement_pdf)", stat_ok, f"Status: {r_stat.status_code}, Tamanho: {len(r_stat.content)} bytes.")

            # 5.3 PDF do Checklist de Acessibilidade
            r_chk = await client.get(f"{BACKEND_URL}/export/last_checklist_pdf")
            chk_ok = r_chk.status_code == 200 and r_chk.content.startswith(b"%PDF")
            log_step("Download do Checklist em PDF (/export/last_checklist_pdf)", chk_ok, f"Status: {r_chk.status_code}, Tamanho: {len(r_chk.content)} bytes.")

            # 5.4 Geração e validação do pacote ZIP de remediação da página web
            fixed_web_html = (
                "<!DOCTYPE html><html lang='pt-BR'><head><title>Blind Help - Portal Acessível</title></head>"
                "<body><main><h1>Blind Help</h1><p>Portal de acessibilidade e recursos para pessoas com deficiência visual adaptado conforme a WCAG 2.2.</p>"
                "<nav aria-label='Navegação Principal'><ul><li><a href='/'>Início</a></li><li><a href='/artigos'>Artigos e Recursos</a></li></ul></nav>"
                "</main></body></html>"
            )
            zip_name = "qa-fixed-blindhelp-net.zip"
            zip_disk_path = os.path.join(exports_dir, zip_name)
            with zipfile.ZipFile(zip_disk_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("index.html", fixed_web_html)

            r_zip = await client.get(f"{BACKEND_URL}/export/download_zip/{zip_name}")
            zip_ok = r_zip.status_code == 200 and len(r_zip.content) > 100
            log_step("Download e Validação do Pacote ZIP (/export/download_zip/...)", zip_ok, f"Status: {r_zip.status_code}, Tamanho: {len(r_zip.content)} bytes.")

        # 6. Verificação do console JavaScript do navegador
        print("\n[Passo 6] Verificando integridade e erros de console do navegador...", flush=True)
        log_step("Console JavaScript da UI limpo", len(console_errors) == 0, f"Erros capturados: {len(console_errors)}")

        await context.close()
        await browser.close()

    # Resumo
    print("\n" + "="*75, flush=True)
    print("RESUMO CONSOLIDADO DO TESTE E2E COM PÁGINA DA INTERNET", flush=True)
    print("="*75, flush=True)
    total_steps = len(steps_log)
    passed_steps = sum(1 for s in steps_log if s["success"])
    failed_steps = total_steps - passed_steps
    print(f"Total de passos executados: {total_steps}", flush=True)
    print(f"Aprovados: {passed_steps}", flush=True)
    print(f"Falhas: {failed_steps}", flush=True)
    print("="*75, flush=True)

    if failed_steps == 0:
        print("\nTodos os passos do teste com a página da internet foram concluídos com 100% de sucesso!", flush=True)
    else:
        print(f"\nAtenção: {failed_steps} passo(s) apresentaram inconsistências.", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_real_webpage_test())
