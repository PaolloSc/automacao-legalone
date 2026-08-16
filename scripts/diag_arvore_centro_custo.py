"""Diagnostico/teste iterativo do campo 'Centro de custo' (lookupTree) na tela
de Novo recurso. Mantem o MESMO browser aberto entre tentativas (nao reinicia
o fluxo inteiro a cada teste) e tenta, nesta ordem:
  1) clique real via Playwright locator (nao JS .click())
  2) fallback via cua-driver/UIA (cua_win.clicar_label) se o clique do
     Playwright nao gravar o hidden id

Nao salva nada. Se tudo falhar, NAO fecha o navegador (fica aberto pra
inspecionar/tentar mais coisas na mesma sessao).
"""
import json
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402
import cua_win  # noqa: E402

ORIGEM = sys.argv[1] if len(sys.argv) > 1 else "4028550-54.2025.8.26.0100"
CAMINHO = ["Carvalho & Furtado Advogados Associados", "Área operacional", "Cível"]


def dump_tree(bot):
    return bot.page.evaluate(
        """() => Array.from(document.querySelectorAll('tr[data-val-level]'))
            .map(tr => ({nivel: tr.getAttribute('data-val-level'),
                          texto: (tr.querySelector('td')||{}).innerText,
                          visivel: tr.offsetHeight > 0,
                          colapsada: tr.className.includes('collapsed')}))"""
    ) or []


def clicar_via_playwright(bot, nivel: int, texto: str, e_expander: bool) -> bool:
    """Clique real (CDP), nao page.evaluate(...).click() -- a arvore pode
    ignorar clique sintetico."""
    try:
        linhas = bot.page.locator(f'tr[data-val-level="{nivel}"]:visible')
        n = linhas.count()
        for i in range(n):
            linha = linhas.nth(i)
            if texto.strip().lower() not in (linha.inner_text() or '').strip().lower():
                continue
            alvo = linha.locator('.expander') if e_expander else linha.locator('td').first
            if e_expander and alvo.count() == 0:
                alvo = linha  # sem expander -> ja e' leaf, clica na linha mesmo
            alvo.first.click(timeout=3000)
            return True
    except Exception as e:
        print(f"   [PW] clique falhou: {e}")
    return False


def main():
    bot = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not bot.garantir_sessao_ativa():
        print("[ERRO] sem sessao")
        return
    if not bot._abrir_novo_recurso_da_pasta(ORIGEM):
        print(f"[ERRO] {bot.last_error_reason}")
        return

    id_text = bot.page.evaluate(
        """() => {
            const el = document.querySelector('[id^="Areas_"][id$="__AreaText"]');
            return el ? el.id : null;
        }"""
    )
    id_hidden = id_text.replace("Text", "Id")
    print("id_text:", id_text)
    print("hidden antes:", repr(bot._texto_do_campo(id_hidden)))

    # abre a arvore (clique real no botao)
    btn = bot.page.locator(f'#{id_text}').locator(
        'xpath=ancestor::div[contains(@class,"lookup")][1]'
    ).locator('.lookup-show').first
    try:
        btn.click(timeout=5000)
        print("[OK] .lookup-show clicado (Playwright real click)")
    except Exception as e:
        print(f"[ERRO] nao cliquei .lookup-show: {e}")
        return
    time.sleep(1.0)

    print("arvore apos abrir:", json.dumps(dump_tree(bot), ensure_ascii=False, indent=2)[:800])

    cua_ok = cua_win.disponivel()
    print("CUA disponivel:", cua_ok)

    for nivel, segmento in enumerate(CAMINHO):
        ultimo = nivel == len(CAMINHO) - 1
        print(f"\n--- nivel {nivel}: {segmento!r} (ultimo={ultimo}) ---")

        ok = clicar_via_playwright(bot, nivel, segmento, e_expander=not ultimo)
        print(f"   [PW] clique em nivel {nivel}: {'OK' if ok else 'FALHOU'}")
        time.sleep(0.8)

        hidden_agora = bot._texto_do_campo(id_hidden)
        texto_agora = bot._texto_do_campo(id_text)
        print(f"   hidden={hidden_agora!r} texto={texto_agora!r}")

        if ultimo and hidden_agora:
            print(f"\n[SUCESSO via Playwright] {texto_agora}")
            return

        if not ultimo:
            arvore = dump_tree(bot)
            proximo_nivel_visivel = any(
                l['nivel'] == str(nivel + 1) and l['visivel'] for l in arvore)
            if proximo_nivel_visivel:
                print(f"   [OK] nivel {nivel+1} ja visivel, seguindo sem CUA")
                continue

        # fallback CUA
        if cua_ok:
            print(f"   [CUA] tentando clicar {segmento!r} via UIA...")
            if cua_win.clicar_label(segmento, roles=("text", "row", "tree item", "list item")):
                print("   [CUA] clique OK")
            else:
                print("   [CUA] clique FALHOU")
            time.sleep(1.0)
            hidden_agora = bot._texto_do_campo(id_hidden)
            texto_agora = bot._texto_do_campo(id_text)
            print(f"   apos CUA: hidden={hidden_agora!r} texto={texto_agora!r}")
            if ultimo and hidden_agora:
                print(f"\n[SUCESSO via CUA] {texto_agora}")
                return
        else:
            print("   [CUA] indisponivel, pulando fallback")

    print("\n[FALHOU] nao selecionou ate o fim — navegador FICA ABERTO para inspecao")
    print(f"   estado final: hidden={bot._texto_do_campo(id_hidden)!r} "
          f"texto={bot._texto_do_campo(id_text)!r}")
    print("   arvore final:", json.dumps(dump_tree(bot), ensure_ascii=False, indent=2)[:1500])
    bot.page.screenshot(path="qa_screenshots/diag_centro_custo.png", full_page=False)
    with open("debug_diag_centro_custo.html", "w", encoding="utf-8") as f:
        f.write(bot.page.content())
    print("screenshot + html salvos. Aguardando 180s com o Chrome aberto...")
    time.sleep(180)


if __name__ == "__main__":
    main()
