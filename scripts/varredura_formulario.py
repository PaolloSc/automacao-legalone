"""Varredura do formulario de cadastro do LegalOne: pega o HTML e o estado real.

Motivacao: o bot loga '✓ selecionado' em 8 campos e o LegalOne considera os
mesmos 8 vazios ao habilitar o Salvar. Isso quer dizer que o valor entra no
input visivel mas nao no modelo do componente (bento-combobox / Angular).
Este script tira uma foto de ambos os lados para poder comparar.

Uso:
  python scripts/varredura_formulario.py [url]

Sem url, usa a do ultimo rascunho que falhou. Salva em docs/varredura/.

Serve para as duas UIs. Para inventariar a ficha classica (Novajus) e mapear
mais campos do Forms -> LegalOne, abra a tela de ALTERACAO de um processo:
  python scripts/varredura_formulario.py \\
    https://carvalhofurtadoadv.novajus.com.br/processos/processos/edit/<ID>
O JSON sai com painel/label/id/name/opcoes de cada controle.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")

from legalone_cadastro import LegalOneCadastro  # noqa: E402

URL_PADRAO = "https://firm.legalone.com.br/litigation/create/17988"
SAIDA = REPO / "docs" / "varredura"

# Estado por campo: o que se ve no input x o que o Angular acha do controle.
JS_CAMPOS = """
() => {
  const norm = (s) => (s || '').trim();
  const acharLabel = (el) => {
    // UI nova (Angular/bento)
    const grupo = el.closest('.form-group, .bento-form-group, [class*="form-group"], bento-form-field');
    if (grupo) {
      const lab = grupo.querySelector('label, .bento-label, [class*="label"]');
      if (lab) return norm(lab.innerText || lab.textContent);
    }
    // UI classica (Novajus): <div class="header"><label for="Id">
    if (el.id) {
      const por = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (por) return norm(por.innerText || por.textContent);
    }
    const linha = el.closest('.span1, .span2, .span3, .row');
    const lab2 = linha && linha.querySelector('.header label, label');
    return lab2 ? norm(lab2.innerText || lab2.textContent) : null;
  };
  // Painel da ficha classica ('Valores', 'Previsao e resultado', ...)
  const acharPainel = (el) => {
    const p = el.closest('.edit-panel-responsive-wrapper');
    const t = p && p.querySelector('.panel-title');
    return t ? norm(t.innerText || t.textContent) : null;
  };
  const classesNg = (el) => Array.from(el.classList).filter(c => c.startsWith('ng-'));
  const saida = [];
  document.querySelectorAll('bento-combobox, bento-multiselect-combobox, input, select, textarea')
    .forEach((el) => {
      const tag = el.tagName.toLowerCase();
      const input = tag.startsWith('bento') ? el.querySelector('input') : el;
      if (!input) return;
      const host = tag.startsWith('bento') ? el : (el.closest('bento-combobox') || el);
      saida.push({
        tag,
        painel: acharPainel(el),
        label: acharLabel(el),
        id: input.id || null,
        name: input.name || null,
        tipo: input.type || null,
        // select: as opcoes (value/texto) que o mapeamento precisa
        opcoes: tag === 'select'
          ? Array.from(el.options).map(o => ({v: o.value, t: norm(o.text)})).slice(0, 40)
          : null,
        formcontrolname: host.getAttribute('formcontrolname')
                      || input.getAttribute('formcontrolname') || null,
        // o que aparece na tela
        valor_visivel: norm(input.value),
        // o que o Angular acha: ng-valid/ng-invalid/ng-touched/ng-dirty/ng-pristine
        ng_input: classesNg(input),
        ng_host: classesNg(host),
        required: input.required || input.getAttribute('aria-required') === 'true'
                  || !!host.querySelector('.bento-required, [class*="required"]'),
        aria_invalid: input.getAttribute('aria-invalid'),
        disabled: input.disabled,
        readonly: input.readOnly,
      });
    });
  return saida;
}
"""

JS_VALIDACAO = """
() => {
  // Mensagens que o proprio LegalOne mostra, e o estado do botao Salvar.
  const txt = (el) => (el.innerText || el.textContent || '').trim();
  const salvar = Array.from(document.querySelectorAll('button, a')).find(
    b => /salvar/i.test(txt(b)));
  return {
    salvar_encontrado: !!salvar,
    salvar_disabled: salvar ? (salvar.disabled ||
      salvar.getAttribute('aria-disabled') === 'true' ||
      salvar.classList.contains('disabled')) : null,
    mensagens: Array.from(document.querySelectorAll(
      '.bento-error, .invalid-feedback, [class*="error-message"], ' +
      '.validation-message, bento-error, .text-danger'))
      .map(txt).filter(Boolean).slice(0, 60),
    invalidos_ng: Array.from(document.querySelectorAll('.ng-invalid'))
      .map(el => el.getAttribute('formcontrolname') || el.id || el.tagName.toLowerCase())
      .filter(Boolean).slice(0, 80),
  };
}
"""


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else URL_PADRAO
    SAIDA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    bot = LegalOneCadastro()
    if not bot.garantir_sessao_ativa():
        print("nao consegui abrir o navegador / sessao")
        return 1

    print(f"abrindo {url}")
    bot.page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)  # o form monta em Angular depois do domcontentloaded

    if "authentication" in (bot.page.url or "") or "login" in (bot.page.url or "").lower():
        print(f"caiu no login: {bot.page.url} — refazendo")
        bot.fazer_login()
        bot.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)

    html = SAIDA / f"form_{marca}.html"
    html.write_text(bot.page.content(), encoding="utf-8")
    print(f"html: {html.name} ({html.stat().st_size // 1024} KB)")

    campos = bot.page.evaluate(JS_CAMPOS)
    valida = bot.page.evaluate(JS_VALIDACAO)
    dump = SAIDA / f"campos_{marca}.json"
    dump.write_text(json.dumps({"url": bot.page.url, "campos": campos, "validacao": valida},
                               indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"json: {dump.name} | {len(campos)} campos | "
          f"salvar_disabled={valida.get('salvar_disabled')}")

    obrigatorios = [c for c in campos if c["required"]]
    print(f"\nobrigatorios ({len(obrigatorios)}):")
    for c in obrigatorios:
        print(f"  {c['label'] or c['id']!r:42} visivel={c['valor_visivel']!r:30} "
              f"ng={','.join(c['ng_input']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
