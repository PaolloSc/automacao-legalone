"""O campo tem que ficar com a opcao PRETENDIDA, nao com qualquer opcao valida.

30/07: o Contrario Principal ficou 'Augusto Nasser Borges' — pessoa sem relacao
com o processo — e o bot deu por bom, porque a verificacao existente so olhava se
o componente tinha aceitado *alguma* selecao (bfm-invalid ausente).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _bot(valor_no_campo: str):
    """LegalOneCadastro sem __init__, com uma page falsa que devolve o valor dado."""
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    bot.page = SimpleNamespace(evaluate=lambda *a, **k: valor_no_campo)
    return bot


def test_aceita_o_valor_pretendido():
    assert _bot("Itaú Unibanco S.A.")._campo_confere_com("Itau Unibanco S.A.")


def test_aceita_diferenca_de_acento_e_caixa():
    assert _bot("ITAU UNIBANCO S A")._campo_confere_com("Itaú Unibanco S.A.")


def test_recusa_pessoa_diferente():
    # O caso real: campo ficou com outra pessoa e passava batido.
    assert not _bot("Augusto Nasser Borges")._campo_confere_com("Itaú Unibanco S.A.")


def test_recusa_campo_vazio():
    assert not _bot("")._campo_confere_com("Itaú Unibanco S.A.")


def test_grid_mostra_mais_que_o_nome():
    # O esperado vem da row inteira; o campo fica so com o nome.
    assert _bot("Itaú Unibanco S.A.")._campo_confere_com(
        "Itaú Unibanco S.A. 60.701.190/0001-04 Existente na base")


def test_sem_esperado_nao_reprova():
    assert _bot("qualquer coisa")._campo_confere_com("")


if __name__ == "__main__":
    test_aceita_o_valor_pretendido()
    test_aceita_diferenca_de_acento_e_caixa()
    test_recusa_pessoa_diferente()
    test_recusa_campo_vazio()
    test_grid_mostra_mais_que_o_nome()
    test_sem_esperado_nao_reprova()
    print("ok")
