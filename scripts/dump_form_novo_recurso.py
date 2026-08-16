"""
Abre o formulário 'Novo recurso' da pasta de origem e lista os campos.
NÃO salva nada — serve para escrever o preenchimento em cima do HTML real.

    python scripts/dump_form_novo_recurso.py 4028550-54.2025.8.26.0100
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

ORIGEM = sys.argv[1] if len(sys.argv) > 1 else "4028550-54.2025.8.26.0100"

JS_CAMPOS = """
() => Array.from(document.querySelectorAll('input, select, textarea')).map(el => {
    const id = el.id || '';
    let label = '';
    if (id) {
        const l = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (l) label = l.innerText.trim();
    }
    if (!label) {
        const w = el.closest('.form-group, .field, td, div');
        if (w) {
            const l = w.querySelector('label');
            if (l) label = l.innerText.trim();
        }
    }
    return {
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        id,
        name: el.name || '',
        label,
        visivel: el.offsetHeight > 0,
        opcoes: el.tagName === 'SELECT'
            ? Array.from(el.options).map(o => o.text.trim()).slice(0, 40) : undefined,
    };
}).filter(c => c.visivel && c.type !== 'hidden')
"""


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessão no LegalOne")
        return
    if not bot._abrir_novo_recurso_da_pasta(ORIGEM):
        print(f"[ERRO] {bot.last_error_reason}")
        return

    campos = bot.page.evaluate(JS_CAMPOS)
    destino = os.path.join(RAIZ, "debug_form_novo_recurso.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"url": bot.page.url, "campos": campos}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(RAIZ, "debug_form_novo_recurso.html"), "w", encoding="utf-8") as f:
        f.write(bot.page.content())
    print(f"[OK] {len(campos)} campos -> {destino}")
    for c in campos:
        print(f"  {c['tag']}/{c['type']:<10} id={c['id']:<40} label={c['label'][:45]!r}")


if __name__ == "__main__":
    main()
