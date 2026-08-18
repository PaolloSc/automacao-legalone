"""Regressao: campo 'Orgao' do LegalOne guarda o nome do tribunal por
extenso, nunca a sigla ('TJMG'), e a sigla do Forms/DataJud nunca resolvia
no catalogo por isso. Validado ao vivo contra o catalogo real (17/08/2026):
TJs sao sempre 'Tribunal de Justica do Estado de <Estado>' e TRTs sempre
'Tribunal Regional do Trabalho da <N>a Regiao'."""
from legalone_cadastro import LegalOneCadastro


def test_tj_estadual():
    c = LegalOneCadastro(username="", password="")
    assert c._orgao_do_cnj("4782756-12.2026.8.13.0000") == (
        "Tribunal de Justiça do Estado de Minas Gerais")
    assert c._orgao_do_cnj("4105424-55.2026.8.26.0000") == (
        "Tribunal de Justiça do Estado de São Paulo")


def test_trt():
    c = LegalOneCadastro(username="", password="")
    assert c._orgao_do_cnj("0010155-82.2025.5.03.0097") == (
        "Tribunal Regional do Trabalho da 3ª Região")


def test_superiores():
    c = LegalOneCadastro(username="", password="")
    assert c._orgao_do_cnj("0000000-00.2025.5.00.0000") == "Tribunal Superior do Trabalho"
    assert c._orgao_do_cnj("0000000-00.2025.3.00.0000") == "Superior Tribunal de Justiça"


def test_cnj_invalido_nao_quebra():
    c = LegalOneCadastro(username="", password="")
    assert c._orgao_do_cnj("") is None
    assert c._orgao_do_cnj("lixo") is None


def test_orgao_entra_na_lista_de_campos_datajud():
    assert "orgao" in LegalOneCadastro._DATAJUD_CAMPOS
