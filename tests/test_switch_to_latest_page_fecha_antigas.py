"""Regressao 19/08/2026: o fluxo de cadastro abre uma aba nova (ex: 'Continuar
cadastro') e _switch_to_latest_page so trocava a referencia do Playwright,
sem fechar a aba antiga nem trazer a nova pra frente. O Playwright continuava
operando certo na aba nova (via CDP), mas o CUA le a arvore UIA da aba
VISIVEL de verdade -- com a antiga ainda em primeiro plano, o CUA clicava em
controles do proprio Chrome (favoritos, aviso --no-sandbox) em vez do
formulario do LegalOne. Usuario relatou: 'abre duas telas e fecha so uma'."""
from unittest.mock import MagicMock

from legalone_cadastro import LegalOneCadastro


def _pagina(fechada=False):
    p = MagicMock()
    p.is_closed.return_value = fechada
    return p


def test_traz_a_pagina_nova_pra_frente():
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    antiga, nova = _pagina(), _pagina()
    bot.context = MagicMock(pages=[antiga, nova])

    assert bot._switch_to_latest_page() is True

    assert bot.page is nova
    nova.bring_to_front.assert_called_once()


def test_fecha_as_paginas_antigas():
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    antiga, nova = _pagina(), _pagina()
    bot.context = MagicMock(pages=[antiga, nova])

    bot._switch_to_latest_page()

    antiga.close.assert_called_once()
    nova.close.assert_not_called()


def test_so_uma_pagina_nao_fecha_nada():
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    unica = _pagina()
    bot.context = MagicMock(pages=[unica])

    assert bot._switch_to_latest_page() is True
    unica.close.assert_not_called()
    unica.bring_to_front.assert_called_once()


if __name__ == '__main__':
    test_traz_a_pagina_nova_pra_frente()
    test_fecha_as_paginas_antigas()
    test_so_uma_pagina_nao_fecha_nada()
    print('ok')
