"""Regressao 19/08/2026: na tela 'Alterar processo' (pedido adicionado via
'Adicionar pedido'), digitar no campo Nome do pedido NUNCA abria o
.lookup-dropdown, mesmo com o texto certo e varios segundos de espera --
confirmado ao vivo via Claude in Chrome/DOM. So' apareceu apos um ArrowDown
explicito: o widget so renderiza a lista em resposta a navegacao por
teclado, nao ao typing. Sem isso, TODO pedido dessa tela falhava com
'Nenhuma opcao disponivel', mesmo com o fix de janela de espera de antes."""
import inspect

from legalone_cadastro import LegalOneCadastro


def test_pressiona_arrowdown_logo_apos_digitar():
    src = inspect.getsource(LegalOneCadastro._selecionar_pedido_no_dropdown)
    idx_type = src.index("inp_nome.type(texto_busca, delay=30, timeout=5000)")
    idx_arrowdown = src.index("inp_nome.press('ArrowDown'", idx_type)
    idx_loop = src.index("for tentativa in range(14):")
    # ArrowDown tem que vir ANTES do loop de polling, senao a primeira
    # rodada de tentativas nunca acha nada (dropdown ainda fechado).
    assert idx_type < idx_arrowdown < idx_loop


def test_arrowdown_tambem_no_meio_do_retry():
    src = inspect.getsource(LegalOneCadastro._selecionar_pedido_no_dropdown)
    assert src.count("inp_nome.press('ArrowDown'") == 2


if __name__ == '__main__':
    test_pressiona_arrowdown_logo_apos_digitar()
    test_arrowdown_tambem_no_meio_do_retry()
    print('ok')
