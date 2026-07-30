"""Acento nao pode decidir qual contato ganha.

30/07: dado 'Itau Unibanco S/A' (sem acento) casava 85% com a linha 'Capturado no
orgao' e 83% com a da base 'Itau Unibanco S.A.' — o contato errado ganhava por
2 pontos so por causa do acento.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalone_cadastro import LegalOneCadastro

bot = LegalOneCadastro.__new__(LegalOneCadastro)


def test_acento_nao_muda_o_score():
    com = bot._calcular_similaridade("Itau Unibanco S/A", "Itaú Unibanco S.A.")
    sem = bot._calcular_similaridade("Itau Unibanco S/A", "Itau Unibanco S.A")
    assert com == sem == 1.0


def test_nomes_diferentes_seguem_diferentes():
    assert bot._calcular_similaridade("Itau Unibanco", "Augusto Nasser Borges") < 0.5


def test_vazio_nao_explode():
    assert bot._calcular_similaridade("", "Itaú") == 0.0


if __name__ == "__main__":
    test_acento_nao_muda_o_score()
    test_nomes_diferentes_seguem_diferentes()
    test_vazio_nao_explode()
    print("ok")
