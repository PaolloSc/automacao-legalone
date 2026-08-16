"""Diagnostico isolado: abre direto o Novo recurso, preenche NumeroCNJ, clica
'Solicitar monitoramento' (numero) e observa o painel 'Monitorar movimentações'
ao longo do tempo — pra achar a condicao certa de espera. Nao salva nada.
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

ORIGEM = "4028550-54.2025.8.26.0100"
CNJ_TESTE = "4105424-55.2026.8.26.0000"


def estado_painel(bot):
    return bot.page.evaluate(
        """() => {
            const badge = document.getElementById('edit-panel-3319-header-tag')
                || document.querySelector('[id^="edit-panel-"][id$="-header-tag"]');
            const sel = document.getElementById('movements-monitoring-field-tipoconsulta-id');
            const btn = document.getElementById('movements-monitoring-next-button-id');
            return {
                badge: badge ? badge.innerText.trim() : null,
                opcoes: sel ? Array.from(sel.options).map(o => o.text.trim()).filter(Boolean) : [],
                btn_disabled: btn ? btn.disabled : null,
            };
        }"""
    )


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

    bot._preencher_texto_por_id('NumeroCNJ', CNJ_TESTE)
    print("ANTES do clique:", estado_painel(bot))

    bot._solicitar_monitoramento_numero()

    for i in range(20):
        time.sleep(1)
        e = estado_painel(bot)
        print(f"+{i+1}s:", e)
        if e['opcoes'] and any('numero' in o.lower().replace('ú','u').replace('º','')
                               for o in e['opcoes']):
            print(">>> opcoes com 'numero' apareceram")
            break

    print("\nFINAL:", estado_painel(bot))
    bot.page.screenshot(path="qa_screenshots/diag_monitoramento.png", full_page=False)


if __name__ == "__main__":
    main()
