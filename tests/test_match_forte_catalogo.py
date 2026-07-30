"""Campos de catalogo exigem match forte; nome de pessoa continua com fuzzy.

Em 30/07 o bot gravou o contrato 'Hon - 0000002/002' no processo porque o valor
pedido ('Pro bono') nao existe na lista de contratos e o fuzzy de 45% casou com
'Proveito Economico...'. Valor errado no cadastro e' pior que campo vazio.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import _campo_exige_match_forte


def test_campos_de_catalogo_exigem_match_forte():
    for campo in (
        "Negociação de contrato de honorários",
        "Negociacao de contrato de honorarios",
        "Contrato de Honorários",
        "Centro de Custo",
        # formcontrolname em ingles: alguns chamadores passam o nome do controle
        "negotiationContract",
        "costCenter",
    ):
        assert _campo_exige_match_forte(campo), campo


def test_pessoas_seguem_com_fuzzy():
    # Esses precisam do fuzzy: 'Itau Unibanco S/A' -> 'Itau Unibanco Holding S.A.'
    for campo in ("Cliente Principal", "Contrário Principal", "Responsável principal",
                  "Posição", "Natureza", "actionType", ""):
        assert not _campo_exige_match_forte(campo), campo


def test_nao_explode_com_none():
    assert not _campo_exige_match_forte(None)


if __name__ == "__main__":
    test_campos_de_catalogo_exigem_match_forte()
    test_pessoas_seguem_com_fuzzy()
    test_nao_explode_com_none()
    print("ok")
