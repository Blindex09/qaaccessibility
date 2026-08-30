"""E2E real: trecho de página pública -> análise -> correção -> Live Preview."""

import asyncio
import re
import sys
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3001"
BACKEND_URL = "http://localhost:8001"
TARGET_URL = "https://www.w3.org/WAI/"


async def wait_response(page, timeout=180_000):
    await page.wait_for_selector("textarea", timeout=20_000)
    await page.wait_for_function(
        """() => {
          const buttons = [...document.querySelectorAll('button')];
          return buttons.some(b => /Enviar mensagem/i.test(b.getAttribute('aria-label') || ''));
        }""",
        timeout=timeout,
    )
    await page.wait_for_timeout(800)


async def send(page, text, timeout=180_000):
    box = page.locator("textarea").first
    await box.fill(text)
    await page.get_by_role("button", name=re.compile("Enviar mensagem", re.I)).click()
    await wait_response(page, timeout)


async def main():
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(TARGET_URL)
        response.raise_for_status()
        html = response.text

    # Limita deliberadamente o teste a uma parte real da página.
    match = re.search(r"<main\b[^>]*>([\s\S]*?)</main>", html, re.I)
    partial = match.group(0) if match else html[:12000]
    partial = partial[:16000]
    print(f"target={urlparse(TARGET_URL).netloc} partial_html_chars={len(partial)}", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 900})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30_000)
        new_conversation = page.get_by_role("button", name=re.compile("Iniciar uma nova conversa", re.I)).first
        if await new_conversation.count():
            await new_conversation.click()
            await page.wait_for_timeout(500)

        await send(
            page,
            "Analise somente este trecho real da página " + TARGET_URL +
            ". Não navegue para outra página e não analise o restante. "
            "Liste os problemas de acessibilidade encontrados:\n\n" + partial,
            timeout=240_000,
        )
        first_text = await page.locator("body").inner_text()
        print("analysis_response=ok", flush=True)

        await send(
            page,
            "Corrija os problemas encontrados somente neste trecho HTML e depois abra o painel Live Preview para eu comparar a versão original e a corrigida.",
            timeout=240_000,
        )

        # A política do produto exige aprovação antes de uma correção.
        approve = page.get_by_role("button", name=re.compile("Aplicar Correções", re.I)).first
        if await approve.count():
            await approve.click()
            await wait_response(page, timeout=300_000)
            print("remediation_approval=accepted", flush=True)
        else:
            print("remediation_approval=not_shown", flush=True)

        await send(page, "Abra agora o Live Preview lado a lado da página original e corrigida.", timeout=120_000)
        body_text = await page.locator("body").inner_text()
        marker = re.search(r"\[LIVE_PREVIEW:([^:\]]+):(\d+)\]", body_text)
        if not marker:
            raise AssertionError("marcador LIVE_PREVIEW não apareceu na interface")

        session_id, total_pages = marker.group(1), int(marker.group(2))
        async with httpx.AsyncClient(timeout=30) as client:
            original = await client.get(f"{BACKEND_URL}/preview/render/{session_id}/0?mode=original")
            fixed = await client.get(f"{BACKEND_URL}/preview/render/{session_id}/0?mode=fixed")
        if original.status_code != 200 or fixed.status_code != 200:
            raise AssertionError(f"preview HTTP original={original.status_code} fixed={fixed.status_code}")
        if original.text == fixed.text:
            raise AssertionError("página original e corrigida ficaram idênticas")

        print(f"preview=ok session={session_id} pages={total_pages} original_bytes={len(original.text)} fixed_bytes={len(fixed.text)}", flush=True)
        print(f"console_errors={len(console_errors)}", flush=True)
        print(f"analysis_mentions={any(token in first_text.lower() for token in ('wcag', 'acessibilidade', 'accessibility'))}", flush=True)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"E2E_FAILURE={type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)
