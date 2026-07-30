"""Validação de CNPJ nos dados do processo — warning para CNPJ inválido/placeholder."""
import responses

from automacao_legalone_completa import AutomacaoLegalOne


def _auto():
    # A consulta a Receita e' cacheada por CNPJ; sem limpar, o mesmo numero
    # devolveria a resposta mockada do teste anterior.
    AutomacaoLegalOne._consultar_receita_cached.cache_clear()
    return AutomacaoLegalOne.__new__(AutomacaoLegalOne)


def test_dv_cnpj():
    assert AutomacaoLegalOne._cnpj_dv_ok("11.222.333/0001-81")  # válido
    assert not AutomacaoLegalOne._cnpj_dv_ok("12.345.678/0001-90")  # placeholder clássico
    assert not AutomacaoLegalOne._cnpj_dv_ok("11.111.111/1111-11")  # sequência repetida


def test_warning_em_campo_com_cnpj_invalido():
    dados = {"contrario": "ALFA LTDA. (CNPJ 12.345.678/0001-90)", "cliente": "NELSON AVIZ"}
    AutomacaoLegalOne._validar_cnpjs(AutomacaoLegalOne.__new__(AutomacaoLegalOne), dados)
    assert any("CNPJ INVÁLIDO" in w for w in dados.get("_qa_warnings", []))


@responses.activate
def test_cnpj_valido_com_razao_batendo_nao_gera_warning():
    responses.get(
        "https://brasilapi.com.br/api/cnpj/v1/11222333000181",
        json={"razao_social": "BETA COMERCIO LTDA"},
    )
    dados = {"contrario": "BETA SA (CNPJ 11.222.333/0001-81)"}
    AutomacaoLegalOne._validar_cnpjs(_auto(), dados)
    assert not dados.get("_qa_warnings")


@responses.activate
def test_cnpj_de_outra_empresa_gera_warning():
    responses.get(
        "https://brasilapi.com.br/api/cnpj/v1/11222333000181",
        json={"razao_social": "GAMA TRANSPORTES LTDA"},
    )
    dados = {"contrario": "BETA SA (CNPJ 11.222.333/0001-81)"}
    AutomacaoLegalOne._validar_cnpjs(_auto(), dados)
    assert any("pertence a 'GAMA TRANSPORTES LTDA'" in w for w in dados["_qa_warnings"])


@responses.activate
def test_cnpj_inexistente_na_receita_gera_warning():
    responses.get("https://brasilapi.com.br/api/cnpj/v1/11222333000181", status=404)
    dados = {"contrario": "BETA SA (CNPJ 11.222.333/0001-81)"}
    AutomacaoLegalOne._validar_cnpjs(_auto(), dados)
    assert any("NÃO consta na Receita" in w for w in dados["_qa_warnings"])
