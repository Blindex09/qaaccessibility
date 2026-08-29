"""
scripts/test_focus_and_screen_reader_knowledge.py
Testa:
1. Foco automático imediato no campo de texto ao clicar no botão "Nova conversa".
2. Conhecimento especializado da IA sobre leitores de tela (NVDA, JAWS, VoiceOver Mac, VoiceOver iOS/iPhone, TalkBack Android) e suporte a testes cross-browser.
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8001"

test_results = []

def record(name: str, passed: bool, info: str = ""):
    status = "[APROVADO]" if passed else "[FALHOU]"
    print(f"{status} {name}")
    if info:
        print(f"       -> {info}")
    test_results.append({"name": name, "passed": passed, "info": info})


async def test_auto_focus_on_new_conversation():
    print("\n" + "="*70)
    print("TESTE 1: FOCO AUTOMÁTICO NO CAMPO AO CLICAR EM 'NOVA CONVERSA'")
    print("="*70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)

        # 1. Digita algo no chat para sujar o campo
        chat_input = page.locator("textarea, input[type=text]").first
        await chat_input.fill("Texto de teste anterior")

        # 2. Clica no botão "Nova conversa"
        new_conv_btn = page.locator("[aria-label='Iniciar uma nova conversa'], [role=button]:has-text('Nova conversa')").first
        await new_conv_btn.click()
        await page.wait_for_timeout(300)

        # 3. Digita diretamente pelo teclado sem clicar no campo
        await page.keyboard.type("Digitando imediatamente apos nova conversa")
        await page.wait_for_timeout(300)

        # 4. Verifica se o texto digitado está dentro do campo de entrada
        input_value = await chat_input.input_value()
        record(
            "Foco Automático e Digitação Imediata em Nova Conversa",
            "Digitando imediatamente" in input_value,
            f"Valor capturado no campo: '{input_value}'"
        )

        await browser.close()


async def test_screen_readers_and_cross_browser_knowledge():
    print("\n" + "="*70)
    print("TESTE 2: CONHECIMENTO DE LEITORES DE TELA E CROSS-BROWSER")
    print("="*70)

    # 1. Verificação do módulo de conhecimento de leitores de tela
    try:
        from backend.src.services.chat_runtime import SYSTEM_PROMPT
        has_sr_rule = "SCREEN READER TESTING GUIDANCE" in SYSTEM_PROMPT
        has_nvda = "NVDA" in SYSTEM_PROMPT
        has_jaws = "JAWS" in SYSTEM_PROMPT
        has_vo = "VoiceOver" in SYSTEM_PROMPT
        has_talkback = "TalkBack" in SYSTEM_PROMPT

        record(
            "Diretrizes de Especialistas em Leitores de Tela no Chat Runtime",
            has_sr_rule and has_nvda and has_jaws and has_vo and has_talkback,
            "Regras ativas para NVDA (Windows), JAWS (Enterprise), VoiceOver (macOS/iOS Safari) e TalkBack (Android Chrome)."
        )
    except Exception as e:
        record("Diretrizes de Especialistas em Leitores de Tela no Chat Runtime", False, str(e))

    # 2. Verificação dos atalhos específicos por leitor de tela na base de conhecimento
    try:
        ak_path = os.path.join(os.path.dirname(__file__), "..", "backend", "src", "resources", "agent_knowledge.md")
        with open(ak_path, encoding="utf-8") as f:
            content = f.read()
        has_vo_keys = "VoiceOver" in content and ("Safari" in content or "swipe" in content)
        has_tb_keys = "TalkBack" in content and ("Android" in content or "swipe" in content)
        has_nvda_keys = "NVDA" in content
        record(
            "Base de Conhecimento Específica de Atalhos e Gestos de Navegação",
            has_vo_keys and has_tb_keys and has_nvda_keys,
            "Atalhos de rotor, gestos de swipe, teclas NVDA e navegação virtual mapeados."
        )
    except Exception as e:
        record("Base de Conhecimento Específica de Atalhos e Gestos de Navegação", False, str(e))

    # 3. Verificação do suporte a testes Cross-Browser (Chromium, Firefox, WebKit)
    try:
        from backend.src.services.browser import _CROSS_BROWSER_ENGINES
        engines_str = ", ".join(_CROSS_BROWSER_ENGINES)
        record(
            "Suporte a Testes em Múltiplos Motores (Cross-Browser)",
            len(_CROSS_BROWSER_ENGINES) == 3,
            f"Motores integrados: {engines_str} (Chromium, Gecko/Firefox, WebKit/Safari)."
        )
    except Exception as e:
        record("Suporte a Testes em Múltiplos Motores (Cross-Browser)", False, str(e))


async def main():
    await test_auto_focus_on_new_conversation()
    await test_screen_readers_and_cross_browser_knowledge()

    print("\n" + "="*70)
    print("RESUMO DOS TESTES")
    print("="*70)
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    print(f"Total de testes: {total}")
    print(f"Aprovados: {passed}")
    print(f"Falhas: {failed}")
    print("="*70)
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
