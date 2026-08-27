"""Fecha o cadastro do Proc - 0007368 (CNJ 0011190-56.2026.5.03.0028,
resposta #852 do Forms trabalhista), que ficou incompleto: o Salvar foi
REJEITADO pelo LegalOne (campo obrigatorio vazio) numa tentativa anterior,
antes do fix de 19/08/2026 que faz o ciclo abortar nesse caso em vez de
declarar sucesso. Como o processo ja existe no LegalOne, o roteador normal
(cadastrar_processo) trata "cadastro inicial que ja existe" como nada-a-fazer
e nunca reabre pra completar pedidos/honorarios -- por isso este script
pontual chama realizar_acoes_pos_cadastro() direto, que busca o processo
pelo CNJ, entra em Alterar e preenche os pedidos do Forms.

    python scripts/completar_pedidos_0011190.py [--dry]
"""
import asyncio
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

os.environ["FORMS_RESPOSTA_FIXA"] = "852"

from forms_extractor import FormsExtractor  # noqa: E402
from legalone_cadastro import LegalOneCadastro  # noqa: E402

FORMS_LINK = (
    "https://forms.office.com/Pages/DesignPage.aspx#FormId="
    "Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUQTUwVjlNRENJT1k3UDI0UElCMVE3T1lVVS4u"
    "&Analysis=true&origin=EmailNotification"
)


def main():
    extrator = FormsExtractor(modulo_mapeamento="forms_mapping")
    dados_processo = asyncio.run(extrator.extrair_dados_forms(FORMS_LINK))
    cnj = (dados_processo or {}).get("cnj")
    print(f"[OK] Forms extraido: CNJ={cnj!r}")
    if cnj != "0011190-56.2026.5.03.0028":
        print(f"[ERRO] CNJ inesperado ({cnj!r}) — abortando pra nao mexer no processo errado")
        return

    if "--dry" in sys.argv:
        print("[DRY] extracao ok, parando antes de abrir o LegalOne")
        return

    cadastro = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    if not cadastro.garantir_sessao_ativa():
        print("[ERRO] nao consegui abrir/logar no LegalOne")
        return

    pos_ok = cadastro.realizar_acoes_pos_cadastro(dados_processo)
    print(f"[POS-CADASTRO] ok={pos_ok}")
    print(f"[STATS] {dados_processo.get('_pedidos_stats')}")

    confirmado = cadastro._confirmar_no_acervo(dados_processo)
    print(f"[ACERVO] confirmado={confirmado} pasta={dados_processo.get('numero_pasta')}")


if __name__ == "__main__":
    main()
