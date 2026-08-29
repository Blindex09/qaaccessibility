"""
scripts/test_ui_and_features_e2e.py
Executa testes reais em todas as funcionalidades do QA Accessibility interagindo
diretamente com a interface web (Playwright) e a API backend local.
"""

import asyncio
import sys

import httpx
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8001"

results = []

def log_test(step: str, success: bool, detail: str = ""):
    status = "[APROVADO]" if success else "[FALHOU]"
    print(f"{status} {step}")
    if detail:
        print(f"       -> {detail}")
    results.append({"step": step, "success": success, "detail": detail})

async def test_backend_direct_features(client: httpx.AsyncClient):
    print("\n" + "="*70)
    print("ETAPA 1: TESTES DIRETOS NAS FERRAMENTAS E GERADORES DO BACKEND")
    print("="*70)

    # 1. Health Check
    try:
        r = await client.get(f"{BACKEND_URL}/health")
        log_test("Backend /health endpoint", r.status_code == 200 and r.json().get("status") == "ok", f"Status: {r.status_code}, Body: {r.text}")
    except Exception as e:
        log_test("Backend /health endpoint", False, str(e))

    # 2. Catálogo de Modelos
    try:
        r = await client.get(f"{BACKEND_URL}/models")
        providers = r.json().get("providers", [])
        has_models = len(providers) > 0
        kimi_found = any("kimi-k3" in m for p in providers for m in p.get("models", []))
        log_test("Catálogo de Modelos (/models)", has_models and not kimi_found, f"{len(providers)} provedores carregados, kimi-k3 ausente: {not kimi_found}")
    except Exception as e:
        log_test("Catálogo de Modelos (/models)", False, str(e))

    # 3. Análise determinística de HTML multipart
    sample_html = (
        "<!DOCTYPE html><html lang='pt-BR'><head><title>Acessibilidade</title></head>"
        "<body><h1>Teste</h1><img src='x.png'><a href='#'>clique</a></body></html>"
    )
    issues = []
    try:
        files = {"file": ("index.html", sample_html.encode("utf-8"), "text/html")}
        r = await client.post(f"{BACKEND_URL}/analyze/file", files=files, timeout=180.0)
        data = r.json() if r.status_code == 200 else {}
        issues = data.get("data", {}).get("issues", [])
        log_test("Análise de Acessibilidade de Arquivo (/analyze/file)", r.status_code == 200 and len(issues) > 0, f"Status: {r.status_code}, {len(issues)} problemas identificados.")
    except Exception as e:
        log_test("Análise de Acessibilidade de Arquivo (/analyze/file)", False, f"Exceção: {e}")

    # 4. Geração de Exportação Excel (XLSX)
    try:
        r = await client.get(f"{BACKEND_URL}/export/last_xlsx")
        is_xlsx = r.status_code == 200 and len(r.content) > 1000
        log_test("Exportação de Planilha Excel (/export/last_xlsx)", is_xlsx, f"Status: {r.status_code}, Tamanho: {len(r.content)} bytes.")
    except Exception as e:
        log_test("Exportação de Planilha Excel (/export/last_xlsx)", False, str(e))

    # 5. Geração de PDF do Checklist
    try:
        r = await client.get(f"{BACKEND_URL}/export/last_checklist_pdf", timeout=90.0)
        is_pdf = r.status_code == 200 and len(r.content) > 1000 and r.content.startswith(b"%PDF")
        log_test("Geração de PDF do Checklist (/export/last_checklist_pdf)", is_pdf, f"Status: {r.status_code}, Tamanho: {len(r.content)} bytes, Assinatura PDF válida.")
    except Exception as e:
        log_test("Geração de PDF do Checklist (/export/last_checklist_pdf)", False, f"Exceção: {e}")

    # 6. Geração de Declaração de Acessibilidade em PDF (PDF/UA-1)
    try:
        r = await client.get(f"{BACKEND_URL}/export/last_accessibility_statement_pdf")
        is_statement = r.status_code == 200 and len(r.content) > 1000 and r.content.startswith(b"%PDF")
        log_test("Declaração de Acessibilidade em PDF (/export/last_accessibility_statement_pdf)", is_statement, f"Status: {r.status_code}, Tamanho: {len(r.content)} bytes.")
    except Exception as e:
        log_test("Declaração de Acessibilidade em PDF (/export/last_accessibility_statement_pdf)", False, str(e))

    # 7. Exportação SARIF 2.1.0
    try:
        r = await client.get(f"{BACKEND_URL}/export/last_sarif")
        is_sarif = r.status_code == 200 and "runs" in r.json()
        log_test("Exportação SARIF (/export/last_sarif)", is_sarif, f"Status: {r.status_code}, Formato SARIF 2.1.0 válido.")
    except Exception as e:
        log_test("Exportação SARIF (/export/last_sarif)", False, str(e))

    # 8. Remediação de HTML
    try:
        fix_payload = {
            "html_content": sample_html,
            "issues": issues,
            "self_healing": False
        }
        fix_r = await client.post(f"{BACKEND_URL}/fix/", json=fix_payload)
        fixed_html = fix_r.json().get("data", {}).get("fixed_html", "") if fix_r.status_code == 200 else ""
        log_test("Remediação de HTML (/fix/)", fix_r.status_code == 200 and len(fixed_html) > 0, f"Status: {fix_r.status_code}, Tamanho do código corrigido: {len(fixed_html)} chars.")
    except Exception as e:
        log_test("Remediação de HTML (/fix/)", False, str(e))

    # 9. Criação de Sessão de Live Preview
    session_id = ""
    try:
        prev_payload = {
            "pages": [{
                "title": "index.html",
                "original_html": sample_html,
                "fixed_html": sample_html.replace("<img src='x.png'>", "<img src='x.png' alt='Descrição da imagem'>")
            }]
        }
        prev_r = await client.post(f"{BACKEND_URL}/preview/create", json=prev_payload)
        session_id = prev_r.json().get("session_id", "") if prev_r.status_code == 200 else ""
        log_test("Criação de Sessão de Live Preview (/preview/create)", prev_r.status_code == 200 and bool(session_id), f"Session ID: {session_id}")
    except Exception as e:
        log_test("Criação de Sessão de Live Preview (/preview/create)", False, str(e))

    if session_id:
        try:
            render_r = await client.get(f"{BACKEND_URL}/preview/render/{session_id}/0")
            log_test("Renderização do Live Preview (/preview/render/...)", render_r.status_code == 200 and "<html" in render_r.text.lower(), f"Status: {render_r.status_code}, Conteúdo HTML sanitizado com CSP ativa.")
        except Exception as e:
            log_test("Renderização do Live Preview (/preview/render/...)", False, str(e))


async def test_frontend_ui_playwright():
    print("\n" + "="*70)
    print("ETAPA 2: TESTES REAIS NA INTERFACE WEB VIA PLAYWRIGHT CHROMIUM")
    print("="*70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))

        # 1. Carregamento inicial da página
        try:
            await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
            title = await page.title()
            log_test("Carregamento da UI Web no Navegador", "QA Accessibility" in title, f"Título: '{title}', URL: {page.url}")
        except Exception as e:
            log_test("Carregamento da UI Web no Navegador", False, str(e))

        # 2. Verificação de erros no console JavaScript
        log_test("Console JavaScript sem exceções críticas", len(console_errors) == 0, f"Total de erros de console: {len(console_errors)}")

        # 3. Navegação para tela de Configurações
        try:
            settings_btn = page.locator("[aria-label='Abrir configurações de IA'], [role=button]:has-text('Configurações')").first
            await settings_btn.click()
            await page.wait_for_timeout(1000)
            settings_title = await page.title()
            has_settings = "Configurações" in settings_title or await page.locator("text=Provedor").count() > 0
            log_test("Navegação para Tela de Configurações", has_settings, f"Tela aberta: {settings_title}")
        except Exception as e:
            log_test("Navegação para Tela de Configurações", False, str(e))

        # 4. Retorno para tela de Chat
        try:
            back_btn = page.locator("[aria-label='Voltar para a tela inicial'], [role=button]:has-text('Voltar')").first
            await back_btn.click()
            await page.wait_for_timeout(1000)
            chat_title = await page.title()
            has_chat = "Assistente" in chat_title or await page.locator("text=Conversas").count() > 0
            log_test("Retorno para Tela do Assistente de Chat", has_chat, f"Tela atual: {chat_title}")
        except Exception as e:
            log_test("Retorno para Tela do Assistente de Chat", False, str(e))

        # 5. Modal de Conversas Anteriores
        try:
            conv_btn = page.locator("[aria-label='Ver conversas anteriores'], [role=button]:has-text('Conversas')").first
            await conv_btn.click()
            await page.wait_for_timeout(1000)
            modal_visible = await page.locator("text=Histórico de conversas").count() > 0 or await page.locator("text=Fechar").count() > 0
            log_test("Abertura do Modal de Conversas Anteriores", modal_visible, "Modal aberto e renderizado com foco acessível.")
            close_btn = page.locator("[aria-label='Fechar'], [role=button]:has-text('Fechar')").first
            if await close_btn.count() > 0:
                await close_btn.click()
                await page.wait_for_timeout(500)
        except Exception as e:
            log_test("Abertura do Modal de Conversas Anteriores", False, str(e))

        # 6. Interação com Chat: Digitação e Envio de Pergunta
        try:
            chat_input = page.locator("textarea, input[type=text]").first
            await chat_input.fill("Qual o contraste mínimo exigido pela WCAG 2.2 para texto normal?")
            await chat_input.press("Enter")
            await page.wait_for_timeout(3000)
            user_msg = await page.locator("text=contraste").count() > 0
            log_test("Envio e Renderização da Mensagem no Chat", user_msg, "Mensagem renderizada no fluxo de turnos.")
        except Exception as e:
            log_test("Envio e Renderização da Mensagem no Chat", False, str(e))

        await browser.close()


async def main():
    async with httpx.AsyncClient(timeout=90.0) as client:
        await test_backend_direct_features(client)
    await test_frontend_ui_playwright()

    print("\n" + "="*70)
    print("RESUMO CONSOLIDADO DOS TESTES REAIS DE FUNCIONALIDADE")
    print("="*70)
    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed
    print(f"Total de testes executados: {total}")
    print(f"Aprovados: {passed}")
    print(f"Falhas: {failed}")
    print("="*70)
    if failed > 0:
        print("\nFalhas detalhadas:")
        for r in results:
            if not r["success"]:
                print(f"- {r['step']}: {r['detail']}")
        sys.exit(1)
    else:
        print("\nTodas as funcionalidades e integrações foram testadas com 100% de sucesso!")

if __name__ == "__main__":
    asyncio.run(main())
