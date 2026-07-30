"""Descobre como o bento-combobox marca a row ativa durante a navegacao.

Contar ArrowDown por indice erra a linha (medido em 30/07: negotiationContract
commitou 'Hon - 0000080/001' quando a escolha era outra). Para navegar conferindo,
precisamos do marcador de row ativa. Esta sonda pressiona ArrowDown duas vezes e
mostra o que mudou no DOM entre os dois estados.
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")
from legalone_cadastro import LegalOneCadastro  # noqa: E402

URL = "https://firm.legalone.com.br/litigation/create/17988"
SEL_ROWS = ('.bento-list-row.bui-bento-combobox-container-item, '
            '.bento-list-row.bento-combobox-container-item, .bento-list-row')

JS_ESTADO = """
(sel) => {
  const input = document.activeElement;
  const rows = Array.from(document.querySelectorAll(sel)).filter(r => r.offsetHeight > 0);
  return {
    activedescendant: input ? input.getAttribute('aria-activedescendant') : null,
    input_id: input ? input.id : null,
    rows: rows.slice(0, 12).map((r, i) => ({
      i, id: r.id || null,
      classes: Array.from(r.classList),
      aria_selected: r.getAttribute('aria-selected'),
      tabindex: r.getAttribute('tabindex'),
      texto: (r.innerText || r.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60),
    })),
  };
}
"""


def main() -> int:
    campo = sys.argv[1] if len(sys.argv) > 1 else "mainCustomer"
    valor = sys.argv[2] if len(sys.argv) > 2 else "Livia"
    bot = LegalOneCadastro()
    if not bot.garantir_sessao_ativa():
        return 1
    page = bot.page
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(9)

    inp = page.query_selector(f'bento-combobox[formcontrolname="{campo}"] input')
    if not inp:
        print(f"campo {campo} nao encontrado")
        return 1
    inp.scroll_into_view_if_needed()
    inp.click()
    inp.fill("")
    inp.type(valor, delay=50)
    page.wait_for_selector(SEL_ROWS, state="visible", timeout=15000)
    time.sleep(1.2)

    estados = {"aberto": page.evaluate(JS_ESTADO, SEL_ROWS)}
    for n in (1, 2):
        page.keyboard.press("ArrowDown")
        time.sleep(0.4)
        estados[f"seta{n}"] = page.evaluate(JS_ESTADO, SEL_ROWS)

    for nome, e in estados.items():
        print(f"\n=== {nome} | aria-activedescendant={e['activedescendant']!r}")
        for r in e["rows"][:6]:
            print(f"  [{r['i']}] id={r['id']} sel={r['aria_selected']} "
                  f"tab={r['tabindex']} cls={r['classes']}")
            print(f"      {r['texto']}")

    saida = REPO / "docs" / "varredura" / f"sonda_{campo}.json"
    saida.write_text(json.dumps(estados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {saida.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
