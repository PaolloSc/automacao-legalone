"""So' leitura: abre o dropdown 'Orgao' do formulario de novo recurso e
lista as opcoes reais do catalogo pra cada tribunal que a banca usa
(levantado de processos_cadastrados.log/processos_erro.log). Nunca clica
numa opcao nem salva nada.

    python scripts/mapear_catalogo_orgao.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

ORIGEM = "5068141-71.2023.8.13.0024"

# termo de busca -> alias do CNJ (jurimetria_datajud.alias_do_cnj), levantados
# do historico real de cadastros (J.TR visto em processos_cadastrados/erro.log)
TERMOS = [
    ("trt3", "Regional do Trabalho da 3"),
    ("trt5", "Regional do Trabalho da 5"),
    ("trt8", "Regional do Trabalho da 8"),
    ("trt9", "Regional do Trabalho da 9"),
    ("trt15", "Regional do Trabalho da 15"),
]


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
    if "signon.thomsonreuters.com" in cadastro.page.url:
        print(f"[ERRO] login nao completou, url={cadastro.page.url}")
        return

    if not cadastro._abrir_novo_recurso_da_pasta(ORIGEM):
        print(f"[ERRO] pasta de origem {ORIGEM} nao encontrada: {cadastro.last_error_reason}")
        return

    campo = cadastro.page.query_selector('[id="OrgaoText"]')
    if not campo:
        print("[ERRO] campo OrgaoText nao esta na tela")
        return

    import time

    def buscar(termo):
        campo.click(timeout=5000)
        campo.fill("", timeout=5000)
        campo.type(termo, delay=40, timeout=5000)
        campo.press("Enter")
        opcoes = []
        limite = time.time() + 4
        while time.time() < limite:
            opcoes = cadastro._opcoes_lookup_visiveis()
            if opcoes:
                break
            time.sleep(0.25)
        cadastro.page.keyboard.press("Escape")
        return [t for _, t in opcoes]

    for alias, termo in TERMOS:
        try:
            textos = buscar(termo)
        except Exception as e:
            print(f"[{alias}] busca {termo!r} falhou: {e}")
            continue
        print(f"[{alias}] busca={termo!r} -> {textos or 'NENHUMA OPCAO'}")


if __name__ == "__main__":
    main()
