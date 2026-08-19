"""Abre o RECURSO ja criado (nao a pasta de origem) do CNJ
5300618-93.2023.8.09.0051 e adiciona o pedido que faltou
("Admissão do recurso especial") — o fix do lookupTree ja foi commitado.

    python scripts/adicionar_pedido_recurso_5300618.py [--dry]
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
PASTA_ORIGEM = "Proc - 0004487"


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
        )).filter(a => a.offsetHeight > 0).map(a => ({
            href: a.getAttribute('href'),
            texto: (a.closest('tr') || a.parentElement).innerText.replace(/\\s+/g, ' ').trim()
        }))"""
    )
    alvo = next((l for l in linhas if PASTA_ORIGEM + "/001" in l["texto"]
                 and "Recurso" in l["texto"]), None)
    if not alvo:
        print("[ERRO] linha do recurso (Proc - 0004487/001) nao encontrada")
        for l in linhas:
            print("  -", l["texto"][:120])
        return
    print(f"[OK] recurso encontrado: {alvo['texto'][:150]}")

    from urllib.parse import urljoin
    cadastro.page.goto(urljoin(cadastro.page.url, alvo["href"]),
                        wait_until="domcontentloaded", timeout=30000)
    import time
    time.sleep(2)

    href_editar = cadastro.page.evaluate(
        """() => {
            const a = Array.from(document.querySelectorAll('a'))
                .find(a => (a.getAttribute('href')||'').toLowerCase().includes('/recursos/edit'));
            return a ? a.getAttribute('href') : null;
        }"""
    )
    if not href_editar:
        print("[ERRO] link 'Alterar' do recurso nao encontrado na tela de detalhes")
        return
    cadastro.page.goto(urljoin(cadastro.page.url, href_editar),
                        wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    print(f"[OK] tela de edicao do recurso: {cadastro.page.url}")

    if "--dry" in sys.argv:
        print("[DRY] parando antes de mexer em pedidos")
        return

    ok, falhas = cadastro._preencher_pedidos_recurso(
        {"classificacao_pedidos_recurso": "Admissão do recurso especial (êxito possível)"}
    )
    print(f"[PEDIDOS] ok={ok} falhas={falhas}")

    # Salva a EDICAO do recurso (nao a criacao) — botao padrao Salvar.
    try:
        botao = cadastro.page.locator(
            'button[name="ButtonSave"][value="0"], button[name="ButtonSave"], #btnSave').first
        botao.click(timeout=10000)
        time.sleep(3)
        print(f"[OK] salvou, url final: {cadastro.page.url}")
    except Exception as e:
        print(f"[ERRO] nao consegui salvar: {e}")


if __name__ == "__main__":
    main()
