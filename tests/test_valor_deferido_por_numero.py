"""Multa 467 nao pode herdar o valor da Multa 477.

10/08/2026: o Forms deu 'MULTA ARTIGO 467 - 0' e 'MULTA ARTIGO 477 - R$ 1.000,00'.
Como o zero fica de fora do dicionario, a 467 casou por similaridade (0.97!) com
a 477 e recebeu R$ 1.000,00 na tela. Numero em nome de pedido e' identidade.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

VALORES = {
    "multa artigo 477": "1.000,00",
    "verbas rescisorias": "2.000,00",
    "hon adv sucumbencial": "6.000,00",
}


def _bot():
    return object.__new__(LegalOneCadastro)


def test_multa_467_nao_pega_o_valor_da_477():
    assert _bot()._valor_deferido_do_pedido("Multa artigo 467 CLT", VALORES) == ""


def test_multa_477_pega_o_proprio_valor():
    assert _bot()._valor_deferido_do_pedido("Multa artigo 477 CLT", VALORES) == "1.000,00"


def test_pedido_sem_numero_continua_casando_por_semelhanca():
    assert _bot()._valor_deferido_do_pedido("Verbas Rescisórias", VALORES) == "2.000,00"
    assert _bot()._valor_deferido_do_pedido(
        "Honorários advocatícios sucumbenciais", VALORES
    ) == "6.000,00"


def test_pedido_com_numero_nao_casa_com_pedido_sem_numero():
    assert _bot()._valor_deferido_do_pedido("13o salario", VALORES) == ""


if __name__ == "__main__":
    test_multa_467_nao_pega_o_valor_da_477()
    test_multa_477_pega_o_proprio_valor()
    test_pedido_sem_numero_continua_casando_por_semelhanca()
    test_pedido_com_numero_nao_casa_com_pedido_sem_numero()
    print("ok")
