"""Sem sessao Microsoft, o Forms nao pode ser lido: o motivo real tem que chegar ao email de erro.

Regressao do incidente 28/07/2026 20:06 (VM): browser sem state.json -> login wall ->
5 min de espera -> motivo reportado era "CNJ nao encontrado na extracao".
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forms_extractor import FormsExtractor


def test_erro_extracao_propagado_quando_forms_nao_abre():
    ex = FormsExtractor(use_firecrawl=False)

    async def _falha(*_args, **_kwargs):
        ex.erro_extracao = "Sessao Microsoft ausente/expirada"
        return False

    ex._garantir_forms_aberto = _falha

    dados = asyncio.run(ex.extrair_dados_forms("https://forms.office.com/x"))

    assert dados['cnj'] is None
    assert dados['erro_extracao'] == "Sessao Microsoft ausente/expirada"


if __name__ == "__main__":
    test_erro_extracao_propagado_quando_forms_nao_abre()
    print("OK")
