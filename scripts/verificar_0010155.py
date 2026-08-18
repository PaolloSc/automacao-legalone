"""So' leitura: confere o que realmente ficou gravado (se algo ficou) pro
processo 0010155-82.2025.5.03.0097. Nunca clica em Salvar/editar.

    python scripts/verificar_0010155.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

CNJ = "0010155-82.2025.5.03.0097"


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

    cadastro._pesquisar_processos(CNJ)
    href = cadastro._link_detalhes_da_busca(CNJ)
    print(f"href_detalhes={href}")
    if not href:
        print("[RESULTADO] Nao achei nada pra esse CNJ na busca — nao foi gravado.")
        return

    from urllib.parse import urljoin
    cadastro.page.goto(urljoin(cadastro.page.url, href),
                        wait_until="domcontentloaded", timeout=30000)
    import time
    time.sleep(2.0)
    print(f"[RESULTADO] url={cadastro.page.url}")

    cadastro.page.screenshot(path="qa_screenshots/verificar_0010155.png", full_page=True)
    print("[SCREENSHOT] qa_screenshots/verificar_0010155.png")
    texto = cadastro.page.evaluate("() => document.body.innerText")
    print("[TEXTO]")
    print(texto[:3000])


if __name__ == "__main__":
    main()
