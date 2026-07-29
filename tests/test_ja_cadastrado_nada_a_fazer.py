"""Processo que ja existe + cadastro inicial = nada a fazer.

Regra do escritorio: quando o LegalOne responde '#success-content: O numero X ja
encontra-se cadastrado na pasta <a ...>Proc - NNNN</a>' e o pedido e' cadastro
inicial, nao se mexe no processo. Antes disso o bot entrava em alteracao e
deixava rascunho orfao.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import eh_cadastro_inicial


def test_reconhece_cadastro_inicial_nos_dois_campos():
    assert eh_cadastro_inicial({"tipo_cadastro": "CADASTRO INICIAL"})
    assert eh_cadastro_inicial({"tipo_tarefa_identificada": "CADASTRO_INICIAL"})
    assert eh_cadastro_inicial({"tipo_cadastro": "cadastro inicial"})


def test_nao_confunde_com_outros_tipos():
    # Esses ainda precisam do fluxo de alteracao no processo existente.
    for tipo in ("DECISAO", "RECURSO", "PEDIDOS", "ANDAMENTO", ""):
        assert not eh_cadastro_inicial({"tipo_tarefa_identificada": tipo}), tipo
    assert not eh_cadastro_inicial({})
    assert not eh_cadastro_inicial(None)


def test_campos_nulos_nao_explodem():
    assert not eh_cadastro_inicial({"tipo_cadastro": None, "tipo_tarefa_identificada": None})


if __name__ == "__main__":
    test_reconhece_cadastro_inicial_nos_dois_campos()
    test_nao_confunde_com_outros_tipos()
    test_campos_nulos_nao_explodem()
    print("ok")
