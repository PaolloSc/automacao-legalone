"""_selecionar_pedido_no_dropdown nunca tinha teste (achado ao investigar o
erro real de 17/08/2026: 'Campo do pedido nao respondeu em 5s' travou o
cadastro do recurso 4782756-12.2026.8.13.0000 e o processo nao foi gravado).

Cobre os desfechos que decidem se uma resposta que precisa de selecao em
lista suspensa e' salva ou perdida: match direto, timeout ao digitar (o erro
real do log), dropdown que nunca carrega, e nenhum match — sem crashar e sem
selecionar a linha errada.
"""
import time
from unittest.mock import patch

from legalone_cadastro import LegalOneCadastro


def _cadastro_fake(opcoes_texto):
    cad = object.__new__(LegalOneCadastro)
    cad.page = _PageFalsa(opcoes_texto)
    return cad


class _Opcao:
    def __init__(self, texto):
        self._texto = texto
        self.clicado = False

    def inner_text(self):
        return self._texto

    def scroll_into_view_if_needed(self):
        pass

    def click(self, timeout=5000):
        self.clicado = True


class _Locator:
    def __init__(self, opcoes):
        self._opcoes = opcoes

    def count(self):
        return len(self._opcoes)

    def nth(self, i):
        return self._opcoes[i]


class _Keyboard:
    def press(self, tecla):
        pass


class _PageFalsa:
    """Sempre acha as mesmas opcoes, na primeira das varias estrategias de
    seletor testadas (nao precisa simular o DOM real do LegalOne)."""

    def __init__(self, opcoes_texto):
        self.opcoes = [_Opcao(t) for t in opcoes_texto]
        self.keyboard = _Keyboard()

    def locator(self, sel):
        return _Locator(self.opcoes)


class _InputFalso:
    def __init__(self, falha_ao_digitar=False):
        self.falha_ao_digitar = falha_ao_digitar
        self.valor = ''

    def click(self, timeout=5000):
        pass

    def fill(self, valor, timeout=None):
        self.valor = valor

    def type(self, texto, delay=30, timeout=5000):
        if self.falha_ao_digitar:
            raise TimeoutError('Timeout 5000ms exceeded')
        self.valor = texto


def _sem_sleep(fn):
    return patch('legalone_cadastro.time.sleep', lambda *_a, **_k: None)(fn)


@_sem_sleep
def test_match_direto_seleciona_a_opcao_certa():
    cad = _cadastro_fake(['Verbas Rescisórias', 'Multa'])
    inp = _InputFalso()

    ok = cad._selecionar_pedido_no_dropdown(inp, 'Verbas Rescisórias')

    assert ok is True
    assert cad.page.opcoes[0].clicado is True
    assert cad.page.opcoes[1].clicado is False


@_sem_sleep
def test_timeout_ao_digitar_retorna_false_sem_crashar():
    """Reproduz o erro real de 17/08: Locator.type estoura o timeout de 5s
    (pedido concatenado gigante) — precisa falhar limpo, nao travar o loop."""
    cad = _cadastro_fake(['Verbas Rescisórias'])
    inp = _InputFalso(falha_ao_digitar=True)

    ok = cad._selecionar_pedido_no_dropdown(inp, 'Verbas Rescisórias')

    assert ok is False


@_sem_sleep
def test_dropdown_nunca_carrega_retorna_false():
    cad = _cadastro_fake([])  # nenhuma opcao aparece em nenhuma tentativa
    inp = _InputFalso()

    ok = cad._selecionar_pedido_no_dropdown(inp, 'Verbas Rescisórias')

    assert ok is False


@_sem_sleep
def test_nenhum_match_limpa_o_campo_em_vez_de_selecionar_errado():
    cad = _cadastro_fake(['Vale transporte', 'Vale alimentação'])
    inp = _InputFalso()

    ok = cad._selecionar_pedido_no_dropdown(inp, 'Pensão vitalícia completamente distinta')

    assert ok is False
    assert cad.page.opcoes[0].clicado is False
    assert cad.page.opcoes[1].clicado is False
    assert inp.valor == ''


if __name__ == '__main__':
    test_match_direto_seleciona_a_opcao_certa()
    test_timeout_ao_digitar_retorna_false_sem_crashar()
    test_dropdown_nunca_carrega_retorna_false()
    test_nenhum_match_limpa_o_campo_em_vez_de_selecionar_errado()
    print('ok')
