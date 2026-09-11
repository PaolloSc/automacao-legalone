"""Validacao no Teams: o Python nao posta a mensagem — so aciona um fluxo do
Power Automate (Action.Http nao funciona em Adaptive Card sem bot; a acao
nativa 'Postar cartao adaptavel e aguardar uma resposta' do Power Automate
resolve isso sem precisar de bot). O payload carrega tudo que o fluxo precisa
pra montar o card e, depois do clique, avisar a Maria.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automacao_legalone_completa import _montar_payload_teams_validacao


def test_payload_cita_cnj_pasta_e_cliente():
    payload = _montar_payload_teams_validacao(
        dados_processo={
            "cnj": "0010481-42.2025.5.03.0097",
            "numero_pasta": "Proc - 0006136",
            "cliente": "MVC",
            "contrario": "Empresa X",
        },
        advogado_nome="Mônica Furtado Pinheiro Chagas",
        advogado_email="monica@carvalhofurtadoadv.com.br",
        maria_email="arquivo@carvalhofurtadoadv.com.br",
    )
    assert payload["cnj"] == "0010481-42.2025.5.03.0097"
    assert payload["pasta"] == "Proc - 0006136"
    assert payload["cliente"] == "MVC"
    assert payload["contrario"] == "Empresa X"
    assert payload["advogado_nome"] == "Mônica Furtado Pinheiro Chagas"
    assert payload["advogado_email"] == "monica@carvalhofurtadoadv.com.br"
    assert payload["maria_email"] == "arquivo@carvalhofurtadoadv.com.br"


def test_payload_sem_pasta_usa_na():
    payload = _montar_payload_teams_validacao(
        dados_processo={"cnj": "0010481-42.2025.5.03.0097"},
        advogado_nome="Paollo Sanchez",
        advogado_email="paollo.sanchez@carvalhofurtadoadv.com.br",
        maria_email="arquivo@carvalhofurtadoadv.com.br",
    )
    assert payload["pasta"] == "N/A"
    assert payload["cliente"] == "N/A"


if __name__ == "__main__":
    test_payload_cita_cnj_pasta_e_cliente()
    test_payload_sem_pasta_usa_na()
    print("ok")
