"""Navegador fechado no meio do cadastro tem que abortar, nao seguir as cegas.

Em 29/07 alguem fechou o Chrome durante um cadastro: o bot engoliu o erro campo
por campo, reabriu o navegador, refez login e reportou 'Posição nao localizado' —
escondendo a causa real por 20s de tentativas inuteis.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import NavegadorFechado, _pagina_morta


def test_reconhece_erros_de_pagina_morta():
    # Mensagens reais do Playwright.
    assert _pagina_morta(Exception(
        "Page.wait_for_selector: Target page, context or browser has been closed"))
    assert _pagina_morta(Exception("Page.evaluate: Target page, context or browser has been closed"))
    assert _pagina_morta(Exception("Target closed"))


def test_nao_confunde_com_timeout_comum():
    # Timeout de campo e' erro recuperavel: nao deve abortar o cadastro.
    assert not _pagina_morta(Exception(
        'Page.wait_for_selector: Timeout 10000ms exceeded.\n'
        'Call log:\n  - waiting for locator("#input-position")'))
    assert not _pagina_morta(Exception("elemento nao encontrado"))


def test_navegador_fechado_e_excecao_propria():
    # Precisa ser distinguivel do Exception generico para os handlers reerguerem.
    assert issubclass(NavegadorFechado, RuntimeError)
    try:
        raise NavegadorFechado("navegador fechado ao preencher 'Cliente Principal'")
    except NavegadorFechado as e:
        assert "Cliente Principal" in str(e)


if __name__ == "__main__":
    test_reconhece_erros_de_pagina_morta()
    test_nao_confunde_com_timeout_comum()
    test_navegador_fechado_e_excecao_propria()
    print("ok")
