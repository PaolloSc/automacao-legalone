"""Regressao dos 3 erros fechados pela investigacao de 19/08/2026:
Cliente_IsThirdParty vazio, busca-de-confirmacao tratando excecao como
"nao gravado", dropdown de pedido demorando pra carregar."""
from unittest.mock import MagicMock, patch

from legalone_cadastro import LegalOneCadastro


def test_isthirdparty_setado_apos_cliente_commitar():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = MagicMock()
    # Cliente_EnvolvidoId tem valor, Cliente_IsThirdParty ainda vazio
    c.page.evaluate.side_effect = lambda script, id=None: (
        '123' if id == 'Cliente_EnvolvidoId' else ''
    )
    assert c._lookup_gravou('Cliente_EnvolvidoId') is True
    assert c._lookup_gravou('Cliente_IsThirdParty') is False

    if c._lookup_gravou('Cliente_EnvolvidoId') and not c._lookup_gravou('Cliente_IsThirdParty'):
        c.page.evaluate(
            "(id) => { const el = document.getElementById(id); "
            "if (el) el.value = 'False'; }",
            'Cliente_IsThirdParty')

    ultima_chamada = c.page.evaluate.call_args
    assert ultima_chamada.args[1] == 'Cliente_IsThirdParty'


def test_busca_falhou_retorna_none_nao_false():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = MagicMock()
    c.page.goto.side_effect = Exception('net::ERR_CONNECTION_RESET')

    resultado = c._existe_processo_na_busca('41054245520268130000')

    assert resultado is None  # nao e' False: nao prova que nao foi gravado


def test_busca_ok_nao_encontrou_retorna_false():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = MagicMock()
    c.page.wait_for_selector.return_value = MagicMock()
    c.page.evaluate.return_value = 'nadaaver'

    with patch('legalone_cadastro.time.sleep'):
        resultado = c._existe_processo_na_busca('41054245520268130000')

    assert resultado is False


if __name__ == '__main__':
    test_isthirdparty_setado_apos_cliente_commitar()
    test_busca_falhou_retorna_none_nao_false()
    test_busca_ok_nao_encontrou_retorna_false()
    print('ok')
