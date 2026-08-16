"""Lista (read-only) todos os recursos vinculados a pasta 7444 (Proc - 0006390)
com o CNJ de teste, pra confirmar quais sao as duplicatas antes de apagar
qualquer coisa.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

CNJ_TESTE = "4105424-55.2026.8.26.0000"


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessao")
        return

    bot.page.goto(
        "https://carvalhofurtadoadv.novajus.com.br/processos/processos/search",
        wait_until="domcontentloaded", timeout=25000)
    campo = bot.page.wait_for_selector('#Search, input[name="Search"]', timeout=15000)
    campo.click()
    campo.fill("")
    campo.type(CNJ_TESTE, delay=30)
    bot.page.click('#search-box-input-submit, input[value="Pesquisar"]')
    bot.page.wait_for_load_state("domcontentloaded")
    bot.page.wait_for_timeout(2500)

    linhas = bot.page.evaluate(
        """() => Array.from(document.querySelectorAll('tr'))
            .filter(tr => tr.querySelector('a[href*="/edit/"], a[href*="/details/"]'))
            .map(tr => {
                const a = tr.querySelector('a[href*="/edit/"], a[href*="/details/"]');
                return {
                    texto: (tr.innerText || '').replace(/\\s+/g, ' ').trim(),
                    href: a ? a.getAttribute('href') : null,
                };
            })"""
    ) or []
    print(f"[BUSCA] {CNJ_TESTE} -> {len(linhas)} linha(s)")
    for i, l in enumerate(linhas, 1):
        print(f"{i}. href={l['href']}")
        print(f"   {l['texto'][:250]}")

    with open("debug_duplicatas_recurso.json", "w", encoding="utf-8") as f:
        json.dump(linhas, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
