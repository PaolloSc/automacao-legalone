"""Regressao 19/08/2026: o fallback de texto pro menu 'Adicionar' incluia
'novo' e '+', que tambem batem num atalho solto "+ Novo processo" que
NAVEGA direto pra /processos/processos/create (cadastro manual, sem CNJ)
em vez de abrir o popover. So' 'adicionar' deve sobrar na lista."""
from legalone_cadastro import LegalOneCadastro
import inspect


def test_fallback_de_texto_nao_inclui_novo_nem_mais():
    src = inspect.getsource(LegalOneCadastro.navegar_cadastro_cnj)
    assert '_click_by_text(["adicionar"])' in src
    assert '"novo", "+"' not in src


if __name__ == '__main__':
    test_fallback_de_texto_nao_inclui_novo_nem_mais()
    print('ok')
