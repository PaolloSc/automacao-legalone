"""Abre o Forms num Chromium visivel, espera voce logar e salva browser_data/state.json.

Rode NO PC (precisa de login/2FA interativo):
    venv\\Scripts\\python.exe scripts\\capturar_sessao_forms.py

Depois: scripts/deploy_vm.sh leva o state.json pra VM.
"""
import asyncio
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(RAIZ, "browser_data", "state.json")
URL = "https://forms.office.com/Pages/DesignPageV2.aspx"

from playwright.async_api import async_playwright  # noqa: E402


async def main():
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("FACA LOGIN NA JANELA QUE ABRIU (conta que recebe as respostas).")
        print("Quando a lista de formularios aparecer, volte aqui e tecle ENTER.")
        print("=" * 60)
        input()

        url = page.url
        if "login" in url.lower():
            print(f"[ERRO] Ainda na tela de login ({url}). Nada foi salvo.")
            await browser.close()
            return 1

        await ctx.storage_state(path=STATE)
        await browser.close()
        print(f"[OK] Sessao salva em {STATE}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
