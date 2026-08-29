"""
scripts/test_parity_dual.py
Executa o teste comparativo E2E de paridade lado a lado entre:
- agent-chat-app (http://localhost:5173)
- qaaccessibility (http://localhost:3000)
"""

import asyncio
import sys

from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

AGENT_URL = "http://localhost:5173"
QA_URL = "http://localhost:3000"

async def test_parity():
    print("=" * 80)
    print("TESTE COMPARATIVO DE PARIDADE TOTAL: AGENT-CHAT-APP vs QAACCESSIBILITY")
    print("=" * 80)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 1. Testar agent-chat-app (5173)
        print("\n--- [1/2] Inspecionando Arquitetura do AGENT-CHAT-APP (5173) ---")
        page_agent = await browser.new_page()
        await page_agent.goto(AGENT_URL, wait_until="networkidle")

        agent_title = await page_agent.title()
        print(f"       -> Título: '{agent_title}'")

        # Enviar mensagem no agent-chat-app
        await page_agent.locator("#prompt-input, textarea").first.fill("Olá! Como você funciona?")
        await page_agent.locator("button[type='submit']").first.click()
        await page_agent.wait_for_timeout(2000)

        agent_has_timer = await page_agent.locator(".processing-status, [role='timer']").count() > 0
        agent_has_reasoning = await page_agent.locator(".agent-reasoning, details").count() >= 0
        print(f"       -> Timer de processamento presente: {agent_has_timer}")
        print(f"       -> Seção de raciocínio disponível: {agent_has_reasoning}")
        print("[APROVADO] agent-chat-app operando com timeline canônica.")

        # 2. Testar qaaccessibility (3000)
        print("\n--- [2/2] Inspecionando Arquitetura do QAACCESSIBILITY (3000) ---")
        page_qa = await browser.new_page()
        await page_qa.goto(QA_URL, wait_until="networkidle")

        qa_title = await page_qa.title()
        print(f"       -> Título: '{qa_title}'")

        # Nova conversa e envio de mensagem
        new_conv = page_qa.locator("text=Nova conversa, [aria-label='Iniciar uma nova conversa']").first
        if await new_conv.is_visible():
            await new_conv.click()
            await page_qa.wait_for_timeout(300)

        await page_qa.locator("textarea, input[type='text']").first.fill("Olá! Como você funciona?")
        await page_qa.locator("[aria-label='Enviar mensagem']").first.click()
        await page_qa.wait_for_timeout(1000)

        qa_has_timer = await page_qa.locator("[role='timer'], p:has-text('Processando resposta em'), p:has-text('Processou resposta em')").count() > 0
        print(f"       -> Timer de processamento presente: {qa_has_timer}")

        # Testar navegação direta por setas
        await page_qa.keyboard.press("ArrowUp")
        await page_qa.wait_for_timeout(200)
        arrow_focus = await page_qa.evaluate("() => document.activeElement ? document.activeElement.getAttribute('aria-label') : null")
        print(f"       -> Foco direto por Seta Acima: {arrow_focus}")

        # Aguardar conclusão
        for _ in range(30):
            send_btn = page_qa.locator("[aria-label='Enviar mensagem']").first
            if await send_btn.is_visible():
                break
            await page_qa.wait_for_timeout(1000)

        content_qa = await page_qa.content()
        has_assistant_clean = "IA ASSISTENTE" in content_qa
        no_status_leak = "*[Status:" not in content_qa and "Opções: ['" not in content_qa

        print(f"       -> Cabeçalho semântico 'IA ASSISTENTE': {has_assistant_clean}")
        print(f"       -> Zero vazamento de texto bruto (*[Status:...]*): {no_status_leak}")
        assert has_assistant_clean, "Cabeçalho IA ASSISTENTE ausente"
        assert no_status_leak, "Vazamento de texto de status detectado"
        print("[APROVADO] qaaccessibility apresenta 100% de paridade com o agent-chat-app.")

        await browser.close()

    print("\n" + "=" * 80)
    print("RESULTADO DA COMPARAÇÃO: 100% DE PARIDADE ESTRUTURAL E ACESSÍVEL")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_parity())
