"""So' leitura: abre o recurso ja cadastrado (5300618-93.2023.8.09.0051)
e busca no catalogo de pedidos por termos relacionados a "admissao" e
"recurso especial", pra achar o nome exato que bate no LegalOne.
Nunca clica em Salvar.

    python scripts/verificar_pedido_admissao.py
"""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

ORIGEM = "5300618-93.2023.8.09.0051"
TERMOS = ["Admiss", "Recurso Especial", "Admissibilidade"]


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

    if not cadastro._abrir_novo_recurso_da_pasta(ORIGEM, "Ação Promoção de Vendas Ltda."):
        print(f"[ERRO] pasta nao encontrada: {cadastro.last_error_reason}")
        return

    if not cadastro._clicar_adicionar_pedido():
        print("[ERRO] nao consegui clicar 'Adicionar pedido'")
        return
    campo = cadastro.page.query_selector('ul.pedidos-list li:last-child input[id*="NomePedidoText"]')
    if not campo:
        print("[ERRO] campo NomePedidoText nao apareceu")
        return

    for termo in TERMOS:
        opcoes = cadastro._abrir_lista_lookup(campo, [termo])
        print(f"[{termo!r}] {len(opcoes)} opcao(oes): {[t for _, t in opcoes]}")
        cadastro.page.keyboard.press("Escape")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
