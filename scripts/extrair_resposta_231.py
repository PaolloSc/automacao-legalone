"""
Extrai a resposta ridx=231 do Forms cível usando sessão salva em browser_data/state.json.
Salva debug_perguntas_231.json com todas as perguntas/respostas encontradas.
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(RAIZ, "browser_data", "state.json")
URL = (
    "https://forms.cloud.microsoft/pages/designpagev2.aspx?"
    "analysis=true&origin=EmailNotification&subpage=design"
    "&id=Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u"
    "&topview=SurveyResults&qid=r99ca8e9c481c4a99af9ad799e1bd0299&ridx=231"
)
JS_FILE = os.path.join(os.path.dirname(__file__), "extrair_forms_civel_231.js")


async def main():
    with open(JS_FILE, "r", encoding="utf-8") as f:
        js_extracao = f.read()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=STATE)
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=120000)
        await page.wait_for_timeout(8000)

        # Scroll suave para carregar todo conteúdo
        await page.evaluate(
            """
            async () => {
                window.scrollTo(0, 0);
                await new Promise(r => setTimeout(r, 500));
                const total = document.body.scrollHeight;
                for (let i = 0; i <= 20; i++) {
                    window.scrollTo(0, total * i / 20);
                    await new Promise(r => setTimeout(r, 400));
                }
                await new Promise(r => setTimeout(r, 1000));
            }
            """
        )
        await page.wait_for_timeout(3000)

        perguntas = await page.evaluate(js_extracao)
        print(f"[OK] Extraidas {len(perguntas)} perguntas")

        output = os.path.join(RAIZ, "debug_perguntas_231.json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(perguntas, f, indent=2, ensure_ascii=False)
        print(f"[OK] Salvo em {output}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
