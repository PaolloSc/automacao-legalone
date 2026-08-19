"""So' leitura: testa se buscar pelo NOME DO CLIENTE acha a pasta certa
quando o 'vinculo' do Forms e' um codigo de pasta ('Proc - NNNNNNN') em
vez do CNJ. Nunca clica em Salvar.

    python scripts/verificar_busca_por_pasta.py
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

CLIENTE = "Ação Promoção de Vendas Ltda."
VINCULO = "Proc - 0004487"


def main():
    cadastro = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not cadastro.inicializar_navegador():
        print("[ERRO] navegador nao iniciou")
        return
    try:
        cadastro.page.wait_for_url(
            lambda url: "signon.thomsonreuters.com" not in url, timeout=40000)
    except Exception:
        pass

    cadastro._pesquisar_processos(CLIENTE)
    linhas = cadastro.page.evaluate(
        """() => Array.from(document.querySelectorAll(
            'a[href*="/processos/processos/details/"]'
        )).filter(a => a.offsetHeight > 0).map(a => {
            const linha = a.closest('tr') || a.parentElement;
            return (linha && linha.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 200);
        })"""
    )
    print(f"[BUSCA POR CLIENTE] {len(linhas)} linha(s) encontrada(s):")
    for l in linhas:
        print(f"  - {l}")

    href = cadastro._link_detalhes_da_busca(VINCULO)
    print(f"\n[MATCH] _link_detalhes_da_busca({VINCULO!r}) -> {href}")


if __name__ == "__main__":
    main()
