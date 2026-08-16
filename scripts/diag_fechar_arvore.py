"""Diagnostico isolado: seleciona a Area (arvore) e testa jeitos de FECHAR o
popup que fica aberto no DOM depois — pra achar qual mecanismo realmente
funciona antes de aplicar no codigo de producao.
"""
import json
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

ORIGEM = "4028550-54.2025.8.26.0100"


def linhas_visiveis(bot):
    return bot.page.evaluate(
        """() => Array.from(document.querySelectorAll('tr[data-val-level]'))
            .filter(tr => tr.offsetHeight > 0)
            .map(tr => (tr.querySelector('td')||{}).innerText || '')"""
    )


def linhas_initialized_sem_filtro(bot):
    return bot.page.evaluate(
        """() => Array.from(document.querySelectorAll('.lookup-dropdown .treeTable tbody tr.initialized, .lookup-dropdown .treeTable tbody tr[data-val-level]'))
            .map(tr => ({texto: (tr.querySelector('td')||{}).innerText || '', altura: tr.offsetHeight}))"""
    )


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessao")
        return
    if not bot._abrir_novo_recurso_da_pasta(ORIGEM):
        print(f"[ERRO] {bot.last_error_reason}")
        return

    area = 'Carvalho & Furtado Advogados Associados / Área operacional / Cível'
    ids = bot.page.evaluate(
        """() => {
            const el = document.querySelector('[id^="Areas_"][id$="__AreaText"]');
            return el ? el.id : null;
        }"""
    )
    print("Selecionando Area:", area, "em", ids)
    ok = bot._selecionar_em_lookup_tree(ids, area)
    print("selecao ok?", ok)
    print("linhas visiveis logo apos selecao+escape:", linhas_visiveis(bot))

    # Teste 1: clicar em um elemento neutro (heading da pagina)
    try:
        bot.page.locator('h1, .page-title, body').first.click(timeout=3000, position={"x": 5, "y": 5})
    except Exception as e:
        print("clique neutro falhou:", e)
    time.sleep(0.5)
    print("apos clique neutro:", linhas_visiveis(bot))
    print("SEM FILTRO offsetHeight:", linhas_initialized_sem_filtro(bot))

    # Teste 2: clicar de novo no .lookup-show (toggle)
    try:
        btn = bot.page.locator(f'#{ids}').locator(
            'xpath=ancestor::div[contains(@class,"lookup")][1]').locator('.lookup-show').first
        btn.click(timeout=3000)
    except Exception as e:
        print("toggle lookup-show falhou:", e)
    time.sleep(0.5)
    print("apos toggle lookup-show:", linhas_visiveis(bot))


if __name__ == "__main__":
    main()
