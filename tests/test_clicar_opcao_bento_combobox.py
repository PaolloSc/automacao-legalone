"""_clicar_opcao_bento_combobox nunca tinha teste, apesar de ser a funcao que
resolve o bug central registrado em memoria de projeto: clicar/dispatchEvent
na linha do bento-combobox NAO commita a selecao — so setas+Enter commitam,
e mesmo assim o LegalOne pode recusar (bfm-invalid) ou commitar a linha
errada se a lista mudou no meio da navegacao (bug real de 30/07: Contrario
Principal virou 'Augusto Nasser Borges').

Cobre os tres jeitos de a selecao ser perdida sem o bot perceber: nao achar
a linha destacada, o LegalOne recusar a selecao, e commitar valor diferente
do pretendido.
"""
from unittest.mock import patch

from legalone_cadastro import LegalOneCadastro


class _Keyboard:
    def __init__(self):
        self.teclas = []

    def press(self, tecla):
        self.teclas.append(tecla)


class _PageFalsa:
    """Simula: a cada ArrowDown a linha 'highlighted' avanca por `ordem`.
    `commitou` e `valor_apos_commit` decidem a resposta das checagens
    pos-Enter (_combobox_commitou / _campo_confere_com), que sao os dois
    sinais que substituiram o texto do input (nao confiavel)."""

    def __init__(self, ordem, commitou=True, valor_apos_commit=None):
        self.ordem = ordem
        self._pos = -1
        self.keyboard = _Keyboard()
        self.commitou = commitou
        self.valor_apos_commit = valor_apos_commit

    def evaluate(self, js):
        if 'highlighted' in js:
            self._pos = min(self._pos + 1, len(self.ordem) - 1)
            row_id, texto = self.ordem[self._pos]
            return {'id': row_id, 'texto': texto}
        if 'bfm-invalid' in js:
            return self.commitou
        # _campo_confere_com: le o valor atual do input
        return self.valor_apos_commit


def _cadastro_fake(page):
    cad = object.__new__(LegalOneCadastro)
    cad.page = page
    return cad


def _sem_sleep(fn):
    return patch('legalone_cadastro.time.sleep', lambda *_a, **_k: None)(fn)


@_sem_sleep
def test_desce_ate_a_linha_certa_e_commita():
    ordem = [('row-0', 'Reclamante'), ('row-1', 'Reclamado')]
    page = _PageFalsa(ordem, commitou=True, valor_apos_commit='Reclamado')
    cad = _cadastro_fake(page)

    ok = cad._clicar_opcao_bento_combobox(
        {'id': 'row-1', 'nome': 'Reclamado', 'index': 1}
    )

    assert ok is True
    assert page.keyboard.teclas[-1] == 'Enter'


@_sem_sleep
def test_nao_consegue_destacar_a_linha_aborta_sem_apertar_enter():
    # A lista so' tem 'row-0' — a linha pretendida 'row-5' nunca aparece
    # 'highlighted', entao nao pode confirmar as cegas.
    ordem = [('row-0', 'Reclamante')]
    page = _PageFalsa(ordem)
    cad = _cadastro_fake(page)

    ok = cad._clicar_opcao_bento_combobox(
        {'id': 'row-5', 'nome': 'Outra Opcao', 'index': 5}
    )

    assert ok is False
    assert 'Enter' not in page.keyboard.teclas


@_sem_sleep
def test_legalone_recusa_a_selecao_bfm_invalid():
    ordem = [('row-0', 'Itaú Unibanco S.A.')]
    page = _PageFalsa(ordem, commitou=False)
    cad = _cadastro_fake(page)

    ok = cad._clicar_opcao_bento_combobox(
        {'id': 'row-0', 'nome': 'Itaú Unibanco S.A.', 'index': 0}
    )

    assert ok is False


@_sem_sleep
def test_commita_valor_diferente_do_pretendido_limpa_o_campo():
    # Bug real de 30/07: a lista mudou durante a navegacao e o Enter commitou
    # 'Augusto Nasser Borges' em vez de 'Itaú Unibanco S.A.'. bfm-invalid
    # sozinho nao pega isso porque o campo ficou VALIDO, so' errado.
    ordem = [('row-0', 'Itaú Unibanco S.A.')]
    page = _PageFalsa(ordem, commitou=True, valor_apos_commit='Augusto Nasser Borges')
    cad = _cadastro_fake(page)

    ok = cad._clicar_opcao_bento_combobox(
        {'id': 'row-0', 'nome': 'Itaú Unibanco S.A.', 'index': 0}
    )

    assert ok is False
    # limpou o campo em vez de deixar o valor errado gravado
    assert 'Control+a' in page.keyboard.teclas


if __name__ == '__main__':
    test_desce_ate_a_linha_certa_e_commita()
    test_nao_consegue_destacar_a_linha_aborta_sem_apertar_enter()
    test_legalone_recusa_a_selecao_bfm_invalid()
    test_commita_valor_diferente_do_pretendido_limpa_o_campo()
    print('ok')
