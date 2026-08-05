"""Anexa no Chrome do bot pelo CDP e conta o que esta na tela. SO LEITURA.

O cadastro roda no seu proprio Playwright; aqui a gente entra pela porta de
depuracao (--remote-debugging-port) como observador. Nao clica, nao digita,
nao navega — so le URL, titulo, campos obrigatorios vazios e erros do console.

Uso:
  python scripts/espiar_navegador.py            # uma foto
  python scripts/espiar_navegador.py --shot x.png
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

PORTA = os.getenv("LEGALONE_CDP_PORT", "9222")

JS_ESTADO = """
() => {
  const txt = (e) => ((e && (e.innerText || e.textContent)) || '').trim();
  const salvar = Array.from(document.querySelectorAll('button, a'))
      .find(b => /^salvar$/i.test(txt(b)));
  const erros = Array.from(document.querySelectorAll(
      '.bento-error, bento-error, .invalid-feedback, .validation-message, .text-danger'))
      .map(txt).filter(Boolean).slice(0, 15);
  const campos = Array.from(document.querySelectorAll('bento-combobox[formcontrolname]'))
      .map(h => ({
        campo: h.getAttribute('formcontrolname'),
        valor: (h.querySelector('input') || {}).value || '',
        invalido: h.classList.contains('bfm-invalid') || h.classList.contains('ng-invalid'),
      }));
  return {
    titulo: document.title,
    salvar: salvar ? (salvar.disabled || salvar.getAttribute('aria-disabled') === 'true'
                      ? 'desabilitado' : 'habilitado') : 'ausente',
    erros,
    campos,
    total_inputs: document.querySelectorAll('input, select, textarea').length,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", help="salva screenshot neste caminho")
    args = ap.parse_args()

    with sync_playwright() as p:
        try:
            navegador = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA}")
        except Exception as e:
            print(f"nao consegui anexar na porta {PORTA}: {e}")
            return 1
        paginas = [pg for ctx in navegador.contexts for pg in ctx.pages]
        if not paginas:
            print("nenhuma aba aberta")
            return 1
        # A aba do cadastro e' a ultima ativa; as outras sao busca de CNPJ etc.
        pg = next((x for x in reversed(paginas) if "legalone" in (x.url or "").lower()
                   or "novajus" in (x.url or "").lower()), paginas[-1])
        estado = pg.evaluate(JS_ESTADO)
        estado["url"] = pg.url
        estado["abas"] = [x.url for x in paginas]
        print(json.dumps(estado, ensure_ascii=False, indent=2))
        if args.shot:
            pg.screenshot(path=args.shot)
            print(f"screenshot: {args.shot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
