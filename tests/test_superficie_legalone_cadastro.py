"""Atributos e metodos que o fluxo de decisao usa em runtime.

Duas vezes em 10/08/2026 uma edicao por intervalo ("recorta daqui ate o proximo
def") engoliu um bloco de constantes vizinho: `_SELETORES_OPCAO_LOOKUP` e
depois `_PAINEL_SELECTS`. O codigo importava, os testes passavam, e o bot so
descobria no meio do cadastro, com o navegador aberto e o processo em edicao.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from legalone_cadastro import LegalOneCadastro

ATRIBUTOS = (
    "_PAINEL_SELECTS",
    "_PAINEL_LOOKUPS",
    "_PAINEL_DATAS",
    "_IDS_PAINEL_RESULTADO",
    "_SELETORES_OPCAO_LOOKUP",
    "_SEPARADOR_OPCOES",
    "_RE_PAR_DEFERIDO",
    "SEMELHANCA_MINIMA_LOOKUP",
    "ABREVIACOES_LOOKUP",
    "_CAMPOS_MOEDA",
)

METODOS = (
    "_registrar_decisao",
    "_preencher_painel_resultado",
    "_preencher_classificacoes_pedidos",
    "_preencher_lookup_por_id",
    "_preencher_lookup_antigo",
    "_abrir_lista_lookup",
    "_opcoes_lookup_visiveis",
    "_limpar_lookup",
    "_lookup_gravou",
    "_expandir_abreviacoes",
    "_expandir_painel",
    "_selecionar_por_id",
    "_ja_tem_valor",
    "_preencher_data_por_id",
    "_valor_deferido_do_pedido",
    "_parse_valores_deferidos",
    "_alterar_fase_processo",
    "_fluxo_decisao",
    "_fluxo_recurso",
    "_capturar_numero_pasta",
    "_parse_moeda_br",
    "_preencher_moeda_por_id",
    "_preencher_moedas_em_lote",
    "_preencher_valores_monetarios",
    "_aplicar_valores_monetarios",
    "_enriquecer_dados_datajud",
    "preencher_fase1_capa",
    "preencher_fase2_processual",
    "preencher_fase3_risco_honorarios",
)


@pytest.mark.parametrize("nome", ATRIBUTOS)
def test_atributo_de_classe_existe(nome):
    assert hasattr(LegalOneCadastro, nome), f"{nome} sumiu da classe"


@pytest.mark.parametrize("nome", METODOS)
def test_metodo_existe(nome):
    assert callable(getattr(LegalOneCadastro, nome, None)), f"{nome} sumiu da classe"


def test_piso_de_semelhanca_continua_exigente():
    # Abaixo de 0.6 o 'melhor da lista' vira chute (o caso 'Acordo homologado').
    assert LegalOneCadastro.SEMELHANCA_MINIMA_LOOKUP >= 0.6


if __name__ == "__main__":
    for _n in ATRIBUTOS:
        test_atributo_de_classe_existe(_n)
    for _n in METODOS:
        test_metodo_existe(_n)
    test_piso_de_semelhanca_continua_exigente()
    print("ok")
