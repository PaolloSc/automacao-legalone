"""Validação de CNPJ nos dados do processo — warning para CNPJ inválido/placeholder."""
from automacao_legalone_completa import AutomacaoLegalOne


def test_dv_cnpj():
    assert AutomacaoLegalOne._cnpj_dv_ok("11.222.333/0001-81")  # válido
    assert not AutomacaoLegalOne._cnpj_dv_ok("12.345.678/0001-90")  # placeholder clássico
    assert not AutomacaoLegalOne._cnpj_dv_ok("11.111.111/1111-11")  # sequência repetida


def test_warning_em_campo_com_cnpj_invalido():
    dados = {"contrario": "ALFA LTDA. (CNPJ 12.345.678/0001-90)", "cliente": "NELSON AVIZ"}
    AutomacaoLegalOne._validar_cnpjs(AutomacaoLegalOne.__new__(AutomacaoLegalOne), dados)
    assert any("CNPJ INVÁLIDO" in w for w in dados.get("_qa_warnings", []))


def test_cnpj_valido_nao_gera_warning():
    dados = {"contrario": "BETA SA (CNPJ 11.222.333/0001-81)"}
    AutomacaoLegalOne._validar_cnpjs(AutomacaoLegalOne.__new__(AutomacaoLegalOne), dados)
    assert not dados.get("_qa_warnings")
