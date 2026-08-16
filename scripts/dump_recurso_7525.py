"""Dump read-only dos campos da pasta 7525 (recurso ja salvo com sucesso) —
serve pra ver o que Classe (CNJ), Assunto (CNJ), Objetos e Vara/turma ficaram
depois de um save que funcionou. Nao mexe em nada.
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

URL = (
    "https://carvalhofurtadoadv.novajus.com.br/processos/Recursos/edit/7525"
    "?returnUrl=%2Fprocessos%2Fprocessos%2Fdetails%2F7525%3FhasNavigation%3DTrue"
)

JS_CAMPOS = """
() => {
    const rotulo = (el) => {
        if (el.id) {
            const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (l) return l.innerText.trim();
        }
        const w = el.closest('.first, .value, td, div');
        let cur = w;
        for (let i = 0; i < 4 && cur; i++) {
            const l = cur.parentElement && cur.parentElement.querySelector(':scope > .header label, :scope > .first.header label, label');
            if (l) return l.innerText.trim();
            cur = cur.parentElement;
        }
        return '';
    };
    return Array.from(document.querySelectorAll('input, select, textarea'))
        .filter(el => el.offsetHeight > 0 || el.type === 'hidden')
        .map(el => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            id: el.id || '',
            name: el.name || '',
            valor: el.value || '',
            label: rotulo(el),
            visivel: el.offsetHeight > 0,
        }));
}
"""


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessao")
        return
    bot.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    bot.page.wait_for_timeout(3000)

    campos = bot.page.evaluate(JS_CAMPOS)
    with open("debug_recurso_7525_editado.html", "w", encoding="utf-8") as f:
        f.write(bot.page.content())
    bot.page.screenshot(path="qa_screenshots/recurso_7525_editado.png", full_page=True)

    with open("debug_recurso_7525_campos.json", "w", encoding="utf-8") as f:
        json.dump(campos, f, indent=2, ensure_ascii=False)

    print(f"[OK] {len(campos)} campos -> debug_recurso_7525_campos.json")
    alvos = ("classe", "assunto", "objeto", "vara", "pedido")
    for c in campos:
        chave = f"{c['id']} {c['label']}".lower()
        if any(a in chave for a in alvos):
            print(f"  {c['tag']}/{c['type']:<8} id={c['id']:<45} "
                  f"label={c['label'][:35]!r:<38} valor={c['valor'][:60]!r}")

    # painel Objetos: procura o container e lista linhas existentes
    objetos = bot.page.evaluate(
        """() => {
            const h = Array.from(document.querySelectorAll('label, .panel-title'))
                .find(e => /objetos/i.test(e.innerText||'') && !/objeto do processo/i.test(e.innerText||''));
            if (!h) return null;
            const painel = h.closest('.edit-panel-responsive-wrapper') || h.parentElement;
            return painel ? painel.innerText.slice(0, 800) : null;
        }"""
    )
    print("\n--- painel Objetos (texto bruto) ---")
    print(objetos)


if __name__ == "__main__":
    main()
