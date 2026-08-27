"""Regressao 19/08/2026 (CNJ 0011190-56.2026.5.03.0028): navegar_cadastro_cnj
clicava no link/texto de 'Cadastro Automatico' e devolvia True so' porque o
clique nao deu excecao -- sem checar se o MODAL com o campo de CNJ realmente
abriu. O diagnostico da falha seguinte ('Preencher CNJ') mostrou a pagina
ainda na lista de Pesquisa, sem nenhum modal. Agora so' retorna True se
#CNJNumberAutomaticModal aparecer."""
import inspect

from legalone_cadastro import LegalOneCadastro


def test_so_retorna_true_se_modal_cnj_confirmado():
    src = inspect.getsource(LegalOneCadastro.navegar_cadastro_cnj)
    assert '_modal_cnj_abriu' in src
    assert "'#CNJNumberAutomaticModal'" in src
    # Os dois caminhos de clique (link direto e por texto) tem que checar
    # o modal antes de devolver True -- nao so' confiar que o clique rodou.
    assert src.count('if _modal_cnj_abriu():') == 2


def test_relogin_e_retry_guardado_contra_loop_infinito():
    src = inspect.getsource(LegalOneCadastro.navegar_cadastro_cnj)
    assert '_retry_apos_relogin' in src
    assert 'navegar_cadastro_cnj(_retry_apos_relogin=False)' in src


if __name__ == '__main__':
    test_so_retorna_true_se_modal_cnj_confirmado()
    test_relogin_e_retry_guardado_contra_loop_infinito()
    print('ok')
