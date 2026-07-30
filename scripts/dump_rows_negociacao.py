"""Lista as rows do combobox de honorarios com cabecalho e todas as colunas.

Existem varias negociacoes 'Pro bono' (o bot pegou 'Hon - 0000002/002' numa
rodada e 'Hon - 0000080/001' noutra). Para escolher a certa e' preciso ver o que
distingue as linhas — provavelmente o cliente numa das colunas.
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

JS = """
(sel) => {
  const t = (e) => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim();
  const cabecalhos = Array.from(document.querySelectorAll(
      '[id*="combobox-list"][id*="header"], .bento-list-header-cell, [role="columnheader"]'))
      .map(h => ({id: h.id || null, texto: t(h)})).filter(h => h.texto);
  const rows = Array.from(document.querySelectorAll(sel)).filter(r => r.offsetHeight > 0);
  return {
    cabecalhos,
    rows: rows.map((r, i) => ({
      i, id: r.id || null,
      colunas: Array.from(r.querySelectorAll('.bento-list-cell, [role="gridcell"]')).map(t),
    })),
  };
}
"""


def main() -> int:
    filtro = sys.argv[1] if len(sys.argv) > 1 else "Pro bono"
    bot = LegalOneCadastro()
    if not bot.garantir_sessao_ativa():
        return 1
    page = bot.page
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(9)

    inp = page.query_selector('bento-combobox[formcontrolname="negotiationContract"] input')
    if not inp:
        print("campo negotiationContract nao encontrado")
        return 1
    inp.scroll_into_view_if_needed()
    inp.click()
    inp.fill("")
    inp.type(filtro, delay=50)
    page.wait_for_selector(SEL_ROWS, state="visible", timeout=15000)
    time.sleep(1.5)

    d = page.evaluate(JS, SEL_ROWS)
    print("cabecalhos:")
    for h in d["cabecalhos"][:8]:
        print(f"  {h['id']}: {h['texto']}")
    print(f"\nrows ({len(d['rows'])}) com filtro {filtro!r}:")
    for r in d["rows"][:20]:
        print(f"  [{r['i']}] {r['id']}")
        for j, c in enumerate(r["colunas"]):
            print(f"        col{j}: {c[:70]}")

    saida = REPO / "docs" / "varredura" / "rows_negociacao.json"
    saida.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {saida.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
