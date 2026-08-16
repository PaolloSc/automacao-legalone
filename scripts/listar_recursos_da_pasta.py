"""Lista (read-only) os recursos vinculados a pasta de origem 7444, pra
confirmar se existe mais de um registro para o CNJ de teste.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessao")
        return

    bot.page.goto(
        "https://carvalhofurtadoadv.novajus.com.br/processos/processos/details/7444"
        "?hasNavigation=True&currentPage=1",
        wait_until="domcontentloaded", timeout=30000)
    bot.page.wait_for_timeout(3000)

    links = bot.page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href*="/Recursos/"], a[href*="/recursos/"]'))
            .map(a => ({href: a.getAttribute('href'), texto: (a.innerText||'').trim()}))
            .filter(x => x.href && !x.href.includes('/create'))"""
    ) or []
    print(f"Links de recurso na pasta 7444: {len(links)}")
    for l in links:
        print(" ", l)

    texto = bot.page.evaluate("() => document.body.innerText.replace(/\\s+/g,' ')")
    i = texto.lower().find('recurso')
    print("\n--- trecho em torno de 'recurso' ---")
    print(texto[max(0, i - 100): i + 500])


if __name__ == "__main__":
    main()
