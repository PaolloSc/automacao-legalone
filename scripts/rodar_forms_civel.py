"""
Roda o fluxo real (extração + cadastro no LegalOne) para UMA resposta do Forms cível.

    python scripts/rodar_forms_civel.py 232

Usa o mesmo caminho do e-mail — assunto do cível para cair no mapeador certo —
e trava o alvo com FORMS_RESPOSTA_FIXA para não pular na última resposta.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

NUMERO = sys.argv[1] if len(sys.argv) > 1 else "232"
os.environ["FORMS_RESPOSTA_FIXA"] = NUMERO

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from config_automacao import FORMS_TIPOS  # noqa: E402
from automacao_legalone_completa import AutomacaoLegalOne  # noqa: E402

CIVEL = next(c for c in FORMS_TIPOS if c["modulo_mapeamento"] == "forms_mapping_civel")
LINK = (
    "https://forms.cloud.microsoft/pages/designpagev2.aspx?analysis=true"
    "&origin=EmailNotification&subpage=design"
    "&id=Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u"
    "&topview=SurveyResults&qid=r99ca8e9c481c4a99af9ad799e1bd0299&FormId="
    "Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u"
)


def main():
    print(f"[RUN] Forms cível — resposta #{NUMERO}")
    if "--dry" in sys.argv:
        # só extrai e mostra o mapeamento; não toca no LegalOne
        import asyncio
        import json

        from forms_extractor import FormsExtractor

        ex = FormsExtractor(modulo_mapeamento="forms_mapping_civel",
                            counter_file=CIVEL["contador"],
                            resposta_minima=CIVEL["resposta_minima"])
        dados = asyncio.run(ex.extrair_dados_forms(LINK))
        alvo = os.path.join(RAIZ, f"debug_forms_civel_{NUMERO}.json")
        with open(alvo, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False, default=str)
        print(f"[DRY] payload salvo em {alvo}")
        for item in (dados or {}).get("perguntas_forms", [])[:8]:
            print(json.dumps({k: item.get(k) for k in
                              ("pergunta", "resposta", "resposta_texto", "marcadas")},
                             ensure_ascii=False))
        asyncio.run(ex.fechar_forms())
        return

    automacao = AutomacaoLegalOne({"modo_automatico": True, "skip_email": True})
    automacao.processar_email(
        {
            "subject": CIVEL["assunto_filtro"],
            "sender": "manual@script",
            "forms_link": LINK,
        }
    )
    automacao._shutdown_async_loop()
    automacao.mostrar_estatisticas()


if __name__ == "__main__":
    main()
