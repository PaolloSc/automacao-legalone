"""Empate na similaridade com o valor original nao pode devolver a lista inteira.

30/07, Contrario Principal 'Itau Unibanco S/A': a busca caiu na variante
'Itau Unibanco' e trouxe 'Itau Unibanco Holding S.A.' junto com 5 filiais do
'Itau Unibanco S.A.' — todas com o mesmo score de 85%. A fase de similaridade
com o valor original dava 1.0 para as 5 filiais e 0.8 para o Holding, mas
desistia porque as filiais empatavam entre si; a fase seguinte entao pegava o
primeiro da lista, que era o Holding.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _bot():
    return LegalOneCadastro.__new__(LegalOneCadastro)


def _opcao(nome, doc, origem="Existente na base"):
    return {"nome": nome, "cpf_cnpj": doc, "origem": origem,
            "texto_completo": f"{doc} {nome} {origem}"}


CASO_REAL = [
    _opcao("Itaú Unibanco Holding S.A.", "60.872.504/0001-23"),
    _opcao("Itaú Unibanco S.A.", "60.701.190/0001-04"),
    _opcao("Itaú Unibanco S.A.", "60.701.190/1719-28"),
    _opcao("Itaú Unibanco S.A.", "60.701.190/1397-90"),
    _opcao("Itau Unibanco S.A", "", "Capturado no órgão"),
]


def test_holding_perde_para_a_matriz():
    escolhido = _bot()._selecionar_melhor_opcao_combobox(
        "Itaú Unibanco", CASO_REAL, valor_original="Itaú Unibanco S/A")
    assert escolhido is not None
    assert escolhido["cpf_cnpj"] == "60.701.190/0001-04", escolhido["nome"]


def test_holding_vence_quando_e_ele_o_pedido():
    escolhido = _bot()._selecionar_melhor_opcao_combobox(
        "Itaú Unibanco", CASO_REAL, valor_original="Itaú Unibanco Holding S.A.")
    assert escolhido["cpf_cnpj"] == "60.872.504/0001-23"


def test_sem_valor_original_nao_quebra():
    assert _bot()._selecionar_melhor_opcao_combobox("Itaú Unibanco", CASO_REAL) is not None


if __name__ == "__main__":
    test_holding_perde_para_a_matriz()
    test_holding_vence_quando_e_ele_o_pedido()
    test_sem_valor_original_nao_quebra()
    print("ok")
