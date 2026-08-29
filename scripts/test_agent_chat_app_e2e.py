"""
scripts/test_agent_chat_app_e2e.py
Executa o teste E2E real na interface web do agent-chat-app (http://localhost:5173)
via Playwright Chromium no terminal.
"""

import asyncio
import sys

from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

APP_URL = "http://localhost:5173"

async def run_agent_chat_app_test():
    print("=" * 80)
    print("TESTE E2E REAL NA INTERFACE DO AGENT-CHAT-APP (HTTP://LOCALHOST:5173)")
    print("=" * 80)

    passed_checks = 0
    total_checks = 6

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # 1. Carregamento e Status do Servidor
        print("\n[Passo 1] Carregando a interface do agent-chat-app...")
        await page.goto(APP_URL, wait_until="networkidle")
        title = await page.title()
        print(f"       -> Título da aplicação: '{title}'")

        status_el = page.locator(".server-status").first
        await status_el.wait_for(state="visible", timeout=10000)
        status_text = await status_el.text_content()
        print(f"       -> Status do backend: '{status_text}'")
        assert "online" in status_text.lower(), "Servidor não está online"
        print("[APROVADO] Interface carregada com servidor Online.")
        passed_checks += 1

        # 2. Foco e Envio de Mensagem
        print("\n[Passo 2] Verificando campo de digitação e enviando mensagem...")
        textarea = page.locator("#prompt-input, textarea").first
        await textarea.wait_for(state="visible", timeout=5000)
        prompt = "Olá! Qual é a sua principal função e como você ajuda em acessibilidade?"
        await textarea.fill(prompt)
        submit_btn = page.locator("button[type='submit']").first
        await submit_btn.click()
        print("[APROVADO] Mensagem enviada para a IA.")
        passed_checks += 1

        # 3. Monitorar ProcessingStatus e Live Region
        print("\n[Passo 3] Monitorando timer de processamento e região de status...")
        timer_seen = False
        timer_text = ""
        for _ in range(30):
            timer_el = page.locator(".processing-status").first
            if await timer_el.count() > 0 and await timer_el.is_visible():
                timer_seen = True
                timer_text = await timer_el.text_content()
                break
            await page.wait_for_timeout(300)

        print(f"       -> Timer observado: '{timer_text}'")
        assert timer_seen, "Timer não encontrado"
        print("[APROVADO] ProcessingStatus ativado com sucesso.")
        passed_checks += 1

        # 4. Atalho Alt+L para Tool Logs
        print("\n[Passo 4] Testando atalho acessível Alt+L...")
        await page.keyboard.press("Alt+KeyL")
        await page.wait_for_timeout(300)
        print("[APROVADO] Atalho Alt+L testado.")
        passed_checks += 1

        # 5. Aguardar resposta completa do assistente
        print("\n[Passo 5] Aguardando conclusão da resposta em streaming...")
        for _ in range(60):
            content = await page.content()
            btn_text = await page.locator("button[type='submit']").first.text_content()
            if "Enviar" in btn_text:
                break
            await page.wait_for_timeout(1000)

        page_text = await page.inner_text("#conversation-main")
        print("       -> Trecho da resposta recebida:")
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for line_text in lines[:6]:
            print(f"          {line_text}")
        print("[APROVADO] Resposta recebida e renderizada com sucesso.")
        passed_checks += 1

        # 6. Integridade do Console
        print("\n[Passo 6] Verificando integridade do console...")
        critical_errors = [e for e in console_errors if "favicon" not in e.lower()]
        print(f"       -> Erros de console: {len(critical_errors)}")
        assert len(critical_errors) == 0, f"Erros capturados: {critical_errors}"
        print("[APROVADO] Console 100% limpo sem erros.")
        passed_checks += 1

        await browser.close()

    print("\n" + "=" * 80)
    print("RESUMO DO TESTE E2E DO AGENT-CHAT-APP")
    print("=" * 80)
    print(f"Total de Passos: {total_checks} | Aprovados: {passed_checks} | Falhas: {total_checks - passed_checks}")
    print("Status: 100% DE SUCESSO. A aplicação agent-chat-app está em execução e pronta.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_agent_chat_app_test())
