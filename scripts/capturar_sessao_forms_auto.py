"""
Abre o Forms num Chromium visível, aguarda login manual (com 2FA) e salva
browser_data/state.json automaticamente quando a sessão estiver válida.

Rode NO PC:
    python scripts\capturar_sessao_forms_auto.py

Faça login na janela do Chrome que abrir. O script detecta sozinho quando
você sair da tela de login e salva a sessão.
"""
import asyncio
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(RAIZ, "browser_data", "state.json")
URL = "https://forms.cloud.microsoft/pages/designpagev2.aspx?analysis=true&origin=EmailNotification&subpage=design&id=Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u&topview=SurveyResults&qid=r99ca8e9c481c4a99af9ad799e1bd0299&ridx=231"

from playwright.async_api import async_playwright  # noqa: E402


async def main():
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("JANELA DO CHROME ABERTA.")
        print("Faca login no Microsoft 365 (2FA incluso).")
        print("O script salvara a sessao automaticamente quando sair da tela de login.")
        print("=" * 60)

        # Aguarda até 5 minutos pelo login
        timeout_segundos = 300
        intervalo = 3
        tentativas = timeout_segundos // intervalo

        for i in range(tentativas):
            await asyncio.sleep(intervalo)
            url = page.url.lower()
            titulo = await page.title()
            print(f"[{i*intervalo}s] URL: {url[:80]}... | Titulo: {titulo}")

            if "login" not in url and "entrar" not in titulo.lower() and "sign in" not in titulo.lower():
                print("\n[OK] Login detectado. Salvando sessao...")
                await ctx.storage_state(path=STATE)
                await browser.close()
                print(f"[OK] Sessao salva em {STATE}")
                return 0

        print("\n[AVISO] Tempo esgotado. Salvando sessao atual (pode ainda nao estar logada)...")
        await ctx.storage_state(path=STATE)
        await browser.close()
        print(f"[OK] Sessao salva em {STATE}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
