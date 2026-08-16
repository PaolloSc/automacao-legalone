"""Confere se um CNJ já existe no LegalOne (pesquisa de processos). Não altera nada.

    python scripts/checar_recurso_civel.py 4105424-55.2026.8.26.0000
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

CNJ = sys.argv[1] if len(sys.argv) > 1 else "4105424-55.2026.8.26.0000"


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessão")
        return
    bot.page.goto(
        "https://carvalhofurtadoadv.novajus.com.br/processos/processos/search",
        wait_until="domcontentloaded", timeout=20000)
    campo = bot.page.wait_for_selector('#Search, input[name="Search"]', timeout=15000)
    campo.click()
    campo.fill("")
    campo.type(CNJ, delay=30)
    bot.page.click('#search-box-input-submit, input[value="Pesquisar"]')
    bot.page.wait_for_load_state("domcontentloaded")
    bot.page.wait_for_timeout(2500)

    linhas = bot.page.evaluate(
        """
        () => Array.from(document.querySelectorAll('tr'))
            .map(r => (r.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter(t => t.length > 20).slice(0, 10)
        """
    ) or []
    print(f"[BUSCA] {CNJ} -> {len(linhas)} linha(s)")
    for t in linhas:
        print("  ", t[:200])


if __name__ == "__main__":
    main()
