"""Fotografa o DOM de um bento-combobox, para comparar selecao do bot x a mao.

O bot ve o texto no input e declara sucesso; o LegalOne recusa. Para saber o que
falta, precisamos do DOM dos dois estados:

  1) bot:   python scripts/dump_combobox.py mainCustomer --preencher "Livia Milena Souza Moreira"
  2) a mao: (selecione o campo na janela aberta) e depois
            python scripts/dump_combobox.py mainCustomer --rotulo mao

O diff dos dois arquivos mostra exatamente o que uma selecao de verdade produz.
"""
import argparse
import time
from datetime import datetime
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")

from legalone_cadastro import LegalOneCadastro  # noqa: E402

URL = "https://firm.legalone.com.br/litigation/create/17988"
SAIDA = REPO / "docs" / "varredura"
SEL_ROWS = ('.bento-list-row.bui-bento-combobox-container-item, '
            '.bento-list-row.bento-combobox-container-item, .bento-list-row')

JS_DUMP = """
(fcn) => {
  const host = document.querySelector(`bento-combobox[formcontrolname="${fcn}"]`)
            || document.querySelector(`[formcontrolname="${fcn}"]`);
  if (!host) return null;
  const input = host.querySelector('input');
  // Angular guarda o contexto do componente aqui; o valor do controle costuma
  // aparecer em alguma propriedade do contexto.
  let ctx = null;
  try {
    const c = host.__ngContext__;
    if (c) ctx = Object.keys(c).length ? 'presente' : 'vazio';
  } catch (e) { ctx = 'inacessivel'; }
  return {
    html: host.outerHTML,
    input_value: input ? input.value : null,
    input_attrs: input ? Object.fromEntries(
        Array.from(input.attributes).map(a => [a.name, a.value])) : null,
    host_classes: Array.from(host.classList),
    ng_context: ctx,
    // qualquer input/hidden dentro do host que possa guardar o id selecionado
    internos: Array.from(host.querySelectorAll('input, select, [aria-selected="true"]')).map(el => ({
      tag: el.tagName.toLowerCase(), type: el.getAttribute('type'),
      id: el.id || null, value: el.value !== undefined ? el.value : null,
      aria_selected: el.getAttribute('aria-selected'),
    })),
  };
}
"""


def _salvar_dump(args, d) -> None:
    """Grava a foto do DOM e imprime o resumo (o que interessa: bfm-invalid)."""
    if not d:
        print(f"controle {args.fcn} ausente na pagina")
        return
    rotulo = args.rotulo or (args.metodo if args.preencher else "atual")
    arq = SAIDA / f"combo_{args.fcn}_{rotulo}_{datetime.now():%H%M%S}.html"
    arq.write_text(d["html"], encoding="utf-8")
    print(f"arquivo: {arq.name} ({len(d['html'])} bytes)")
    print(f"input.value = {d['input_value']!r}")
    print(f"host classes = {d['host_classes']}")
    print("internos:")
    for i in d["internos"]:
        print(f"  {i}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fcn")
    ap.add_argument("--preencher", default=None, help="valor a selecionar")
    ap.add_argument("--metodo", default="js", choices=["js", "teclado"],
                    help="js = dispatchEvent (bot antigo); teclado = setas + Enter")
    ap.add_argument("--rotulo", default=None, help="sufixo do arquivo (ex.: mao, bot)")
    ap.add_argument("--sem-navegar", action="store_true", help="usa a pagina como esta")
    args = ap.parse_args()

    SAIDA.mkdir(parents=True, exist_ok=True)
    bot = LegalOneCadastro()
    if not bot.garantir_sessao_ativa():
        print("nao consegui abrir o navegador")
        return 1
    page = bot.page

    if not args.sem_navegar and URL not in (page.url or ""):
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(9)

    if args.preencher:
        sel = f'bento-combobox[formcontrolname="{args.fcn}"] input'
        campo = page.query_selector(sel)
        if not campo:
            print(f"campo {args.fcn} nao encontrado")
            return 1
        campo.scroll_into_view_if_needed()
        campo.click()
        campo.fill("")
        campo.type(args.preencher[:28], delay=45)
        try:
            page.wait_for_selector(SEL_ROWS, state="visible", timeout=15000)
            time.sleep(1.0)
            if args.metodo == "teclado":
                page.keyboard.press("ArrowDown")
                time.sleep(0.3)
                page.keyboard.press("Enter")
                time.sleep(1.0)
                d = page.evaluate(JS_DUMP, args.fcn)
                _salvar_dump(args, d)
                return 0
            page.evaluate(
                """(args) => {
                    const [sel, val] = args;
                    const lower = val.toLowerCase();
                    const rows = Array.from(document.querySelectorAll(sel)).filter(r => r.offsetHeight > 0);
                    const alvo = rows.find(r => (r.innerText || '').toLowerCase().includes(lower)) || rows[0];
                    if (alvo) {
                        alvo.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        alvo.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    }
                }""",
                [SEL_ROWS, args.preencher],
            )
            time.sleep(1.0)
        except Exception as e:
            print(f"dropdown nao abriu: {e}")

    d = page.evaluate(JS_DUMP, args.fcn)
    if not d:
        print(f"controle {args.fcn} ausente na pagina")
        return 1

    rotulo = args.rotulo or ("bot" if args.preencher else "atual")
    marca = datetime.now().strftime("%H%M%S")
    arq = SAIDA / f"combo_{args.fcn}_{rotulo}_{marca}.html"
    arq.write_text(d["html"], encoding="utf-8")

    print(f"arquivo: {arq.name} ({len(d['html'])} bytes)")
    print(f"input.value = {d['input_value']!r}")
    print(f"host classes = {d['host_classes']}")
    print(f"ng_context = {d['ng_context']}")
    print("internos:")
    for i in d["internos"]:
        print(f"  {i}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
