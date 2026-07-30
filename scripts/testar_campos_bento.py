"""Testa, campo por campo, se a selecao no bento-combobox realmente commita.

O bot loga '✓ selecionado' olhando o texto do input — e o LegalOne recusa o
Salvar dizendo que o campo esta vazio. Este script separa as duas coisas: aplica
uma estrategia de selecao e le o veredito do proprio Angular (ng-invalid no
controle + mensagem de erro do grupo), nao o texto visivel.

Uso:
  python scripts/testar_campos_bento.py js        # dispatchEvent (o que o bot faz hoje)
  python scripts/testar_campos_bento.py clique    # clique real do Playwright
  python scripts/testar_campos_bento.py teclado   # setas + Enter
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")

from legalone_cadastro import LegalOneCadastro  # noqa: E402

URL = "https://firm.legalone.com.br/litigation/create/17988"

# formcontrolname -> valor de teste. So comboboxes; os campos de texto/data
# nao tem o problema de commit.
CAMPOS = [
    ("mainCustomer", "Livia Milena Souza Moreira"),
    ("position", "Reclamante"),
    ("mainOpposite", "Itaú Unibanco Holding S.A."),
    ("mainResponsible", "Monica Pinheiro"),
    ("negotiationContract", "Hon - 0000080/001"),
    ("actionType", "Reclamação Trabalhista"),
]

SEL_ROWS = ('.bento-list-row.bui-bento-combobox-container-item, '
            '.bento-list-row.bento-combobox-container-item, .bento-list-row')

# Veredito: o que o Angular acha do controle, e o erro que o grupo mostra.
JS_VEREDITO = """
(fcn) => {
  const host = document.querySelector(`bento-combobox[formcontrolname="${fcn}"]`)
            || document.querySelector(`[formcontrolname="${fcn}"]`);
  if (!host) return {achou: false};
  const input = host.querySelector('input') || host;
  const grupo = host.closest('.form-group, .bento-form-group, bento-form-field, [class*="form-group"]');
  const erro = grupo ? Array.from(grupo.querySelectorAll(
      '.bento-error, bento-error, .invalid-feedback, .validation-message, .text-danger'))
      .map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean) : [];
  const cls = (el) => Array.from(el.classList).filter(c => c.startsWith('ng-'));
  return {
    achou: true,
    visivel: (input.value || '').trim(),
    ng_host: cls(host),
    ng_input: cls(input),
    invalido: host.classList.contains('ng-invalid') || input.classList.contains('ng-invalid'),
    erros: erro,
  };
}
"""


def salvar_habilitado(page) -> bool | None:
    return page.evaluate("""
      () => {
        const txt = (e) => (e.innerText || e.textContent || '').trim();
        const b = Array.from(document.querySelectorAll('button, a')).find(x => /^salvar$/i.test(txt(x)));
        if (!b) return null;
        return !(b.disabled || b.getAttribute('aria-disabled') === 'true'
                 || b.classList.contains('disabled'));
      }
    """)


def selecionar_pelo_bot(bot, fcn: str, valor: str) -> str:
    """Usa o caminho de producao (preencher_campo_autocomplete) — testa o fix."""
    seletor = f'bento-combobox[formcontrolname="{fcn}"] input'
    bot.page.keyboard.press("Escape")
    time.sleep(0.4)
    ok = bot.preencher_campo_autocomplete(seletor, valor, fcn, permitir_adicionar=False)
    time.sleep(0.5)
    bot.page.keyboard.press("Tab")
    time.sleep(0.5)
    return "ok" if ok else "retornou False"


def selecionar(page, fcn: str, valor: str, metodo: str) -> str:
    """Abre o dropdown, filtra pelo valor e confirma pelo metodo pedido."""
    sel_input = f'bento-combobox[formcontrolname="{fcn}"] input, [formcontrolname="{fcn}"] input'
    campo = page.query_selector(sel_input)
    if not campo:
        return "campo nao encontrado"

    # Fecha overlay do campo anterior: aberto, ele intercepta o clique do proximo.
    page.keyboard.press("Escape")
    time.sleep(0.4)

    campo.scroll_into_view_if_needed()
    campo.click()
    campo.fill("")
    campo.type(valor[:28], delay=45)
    try:
        # A lista vem do servidor; 6s era curto para os campos de pessoa.
        page.wait_for_selector(SEL_ROWS, state="visible", timeout=15000)
    except Exception:
        return "dropdown nao abriu"
    time.sleep(1.2)

    if metodo == "js":
        # Exatamente o que o bot faz hoje: MouseEvent sintetico na row.
        achou = page.evaluate(
            """(args) => {
                const [sel, val] = args;
                const lower = val.toLowerCase();
                const rows = Array.from(document.querySelectorAll(sel))
                                  .filter(r => r.offsetHeight > 0);
                const alvo = rows.find(r => (r.innerText || '').trim().toLowerCase().includes(lower))
                          || rows[0];
                if (!alvo) return null;
                alvo.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                alvo.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                return (alvo.innerText || '').trim();
            }""",
            [SEL_ROWS, valor],
        )
        if not achou:
            return "nenhuma row"
    elif metodo == "clique":
        # Clique real (CDP): gera pointer events de verdade.
        linhas = page.locator(SEL_ROWS)
        n = linhas.count()
        alvo = None
        for i in range(min(n, 40)):
            li = linhas.nth(i)
            try:
                if li.is_visible() and valor.split()[0].lower() in (li.inner_text() or "").lower():
                    alvo = li
                    break
            except Exception:
                continue
        if alvo is None:
            alvo = linhas.filter(visible=True).first
        alvo.click(timeout=4000)
    elif metodo == "teclado":
        page.keyboard.press("ArrowDown")
        time.sleep(0.3)
        page.keyboard.press("Enter")
    else:
        return f"metodo desconhecido: {metodo}"

    time.sleep(0.6)
    # Blur: marca o controle como touched, que e' o que faz o erro aparecer.
    page.keyboard.press("Tab")
    time.sleep(0.6)
    return "ok"


def main() -> int:
    metodo = sys.argv[1] if len(sys.argv) > 1 else "js"
    bot = LegalOneCadastro()
    if not bot.garantir_sessao_ativa():
        print("nao consegui abrir o navegador")
        return 1
    page = bot.page
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(9)

    print(f"\n=== metodo: {metodo} | salvar habilitado no inicio: {salvar_habilitado(page)}\n")
    print(f"{'campo':22} {'acao':18} {'visivel':26} {'invalido':9} erros")
    for fcn, valor in CAMPOS:
        acao = (selecionar_pelo_bot(bot, fcn, valor) if metodo == "bot"
                else selecionar(page, fcn, valor, metodo))
        v = page.evaluate(JS_VEREDITO, fcn)
        if not v.get("achou"):
            print(f"{fcn:22} {acao:18} {'-':26} {'-':9} controle ausente")
            continue
        print(f"{fcn:22} {acao:18} {v['visivel'][:25]!r:26} "
              f"{str(v['invalido']):9} {';'.join(v['erros'])[:40]}")

    print(f"\nsalvar habilitado no fim: {salvar_habilitado(page)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
