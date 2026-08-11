"""Mesma pergunta com duas respostas viravam 'Exito total | Perda'.

O indice de perguntas juntava `perguntas_forms` (extracao estruturada, com as
opcoes realmente marcadas) e todo o `outros_dados` (varredura do DOM, que as
vezes le a opcao errada). Duas respostas para a mesma pergunta eram unidas por
' | ' e chegavam assim no LegalOne — 10/08/2026, com uma marcacao so no Forms.

A estruturada manda; `outros_dados` so entra quando ela nao respondeu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forms_mapping import mapear_formulario

ESTRUTURADA = [
    {
        "pergunta": "1. Tipo de cadastro Requer resposta. Opção única.",
        "resposta": "Decisões",
        "marcadas": ["Decisões"],
    },
    {
        "pergunta": "19. Resultado Requer resposta. Opção única.",
        "resposta": "Êxito total",
        "marcadas": ["Êxito total"],
    },
    {
        "pergunta": "30. Risco Requer resposta. Opção única.",
        "resposta": "Médio",
        "marcadas": ["Médio"],
    },
]


def _campos(outros):
    return mapear_formulario(
        {"perguntas_forms": list(ESTRUTURADA), "outros_dados": dict(outros)}
    )["campos"]


def test_dom_nao_sobrepoe_a_extracao_estruturada():
    campos = _campos({"Resultado": "Perda", "Risco": "Baixo"})
    assert campos["resultado"] == "Êxito total", campos["resultado"]
    assert campos["risco"] == "Médio", campos["risco"]


def test_nunca_devolve_duas_respostas_coladas():
    campos = _campos({"Resultado": "Perda", "Risco": "Baixo"})
    assert " | " not in campos["resultado"]
    assert " | " not in campos["risco"]


def test_outros_dados_ainda_responde_o_que_a_estruturada_nao_pegou():
    campos = _campos({"Resultado": "Perda", "Custas": "Sem pagamento"})
    assert campos.get("custas") == "Sem pagamento"


def test_pergunta_sem_resposta_na_estruturada_cede_a_vez():
    estruturada = list(ESTRUTURADA) + [
        {"pergunta": "17. Custas Requer resposta. Opção única.", "resposta": ""}
    ]
    campos = mapear_formulario(
        {"perguntas_forms": estruturada, "outros_dados": {"Custas": "Sem pagamento"}}
    )["campos"]
    assert campos.get("custas") == "Sem pagamento"


if __name__ == "__main__":
    test_dom_nao_sobrepoe_a_extracao_estruturada()
    test_nunca_devolve_duas_respostas_coladas()
    test_outros_dados_ainda_responde_o_que_a_estruturada_nao_pegou()
    test_pergunta_sem_resposta_na_estruturada_cede_a_vez()
    print("ok")
