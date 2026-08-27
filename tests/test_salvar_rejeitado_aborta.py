"""Regressao 19/08/2026 (CNJ 0011190-56.2026.5.03.0028): quando o LegalOne
REJEITA o Salvar (campo obrigatorio vazio), o codigo nao abortava -- caia
direto no _confirmar_no_acervo, que so' confere se o CNJ aparece na busca de
Pastas (verdade tambem para um rascunho incompleto). Resultado: e-mail de
'[OK] PROCESSO CADASTRADO!' pra um processo que nunca foi salvo de verdade,
com Pedidos e Contrato de Honorarios nunca alcancados (ambos vivem em
realizar_acoes_pos_cadastro, que so roda apos Salvar confirmado)."""
import inspect

from legalone_cadastro import LegalOneCadastro


def test_clicar_salvar_rejeitado_retorna_false_direto_do_metodo():
    src = inspect.getsource(LegalOneCadastro.cadastrar_processo)
    assert 'if not self.clicar_salvar():' in src
    # O return False do bloco de rejeicao tem que vir ANTES do
    # realizar_acoes_pos_cadastro e do _confirmar_no_acervo, nao depois.
    idx_if = src.index('if not self.clicar_salvar():')
    idx_return_false = src.index('return False', idx_if)
    # busca a CHAMADA de verdade (nao a mencao em comentario dentro do bloco
    # de rejeicao, que tambem contem o nome da funcao explicando o motivo)
    idx_pos_cadastro = src.index('self.realizar_acoes_pos_cadastro(', idx_return_false)
    idx_acervo = src.index('self._confirmar_no_acervo(', idx_return_false)
    assert idx_return_false < idx_pos_cadastro < idx_acervo


def test_contrato_honorarios_bate_numeros_iguais():
    assert LegalOneCadastro._contrato_honorarios_bate('Hon - 0000013', 'Hon - 0000013') is True
    assert LegalOneCadastro._contrato_honorarios_bate('Hon - 0000013', 'Hon. 0000013') is True


def test_contrato_honorarios_bate_numeros_diferentes_nao_bate():
    # Achado ao vivo: campo pre-preenchido tinha um contrato, Forms pedia outro.
    assert LegalOneCadastro._contrato_honorarios_bate('Hon - 0000013', 'Hon. 00013/001') is False


def test_contrato_honorarios_bate_vazio_nunca_bate():
    assert LegalOneCadastro._contrato_honorarios_bate('', 'Hon - 0000013') is False
    assert LegalOneCadastro._contrato_honorarios_bate('Hon - 0000013', '') is False


if __name__ == '__main__':
    test_clicar_salvar_rejeitado_retorna_false_direto_do_metodo()
    test_contrato_honorarios_bate_numeros_iguais()
    test_contrato_honorarios_bate_numeros_diferentes_nao_bate()
    test_contrato_honorarios_bate_vazio_nunca_bate()
    print('ok')
