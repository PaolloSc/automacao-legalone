"""Regressao: Cadastro Inicial civel com 'Tipo de vinculo' = Embargos de
terceiros ignorava completamente o campo Vinculo — so' o fluxo de Recurso
tratava vinculo. Restrito a esse unico tipo por decisao explicita de
escopo (18/08/2026); os outros tipos da mesma lista (Cautelar, Conexo,
Execucao etc.) continuam sem tratamento.

Validado ao vivo contra a tela real 'Novo processo' do LegalOne: a secao
'Vinculos' e' uma linha por GUID (mesmo padrao de Pedidos/Assuntos), com
os inputs (TipoVinculoText/Id, ProcessoVinculoText/Id) usando o guid com
'_' e o <select> VinculadoAId usando o MESMO guid com '-' original."""
from unittest.mock import MagicMock, patch

from legalone_cadastro import LegalOneCadastro, _resolver_pedido_catalogo


def test_alias_liberacao_penhora_vira_penhora_de_imovel():
    assert _resolver_pedido_catalogo("Liberação de penhora de imóveis") == "Penhora de Imóvel"
    assert _resolver_pedido_catalogo("liberacao de penhora de imoveis") == "Penhora de Imóvel"


def test_ficha_forms_so_trata_vinculo_para_embargos_de_terceiro():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c._FICHA_LOOKUPS = ()
    c._FICHA_TEXTOS = ()
    c._FICHA_DATAS = ()
    c._PERSONALIZADOS_LOOKUP = ()
    c._PERSONALIZADOS_TEXTO = ()
    c._PERSONALIZADOS_DATA = ()
    c._PERSONALIZADOS_MOEDA = ()
    c._estado_campo = MagicMock(return_value='vazio')

    with patch.object(LegalOneCadastro, "_preencher_vinculo_embargos_terceiro") as m:
        c._preencher_ficha_forms(lambda *campos: {"tipo_vinculo": "Cautelar"}.get(campos[0]))
    m.assert_not_called()

    with patch.object(LegalOneCadastro, "_preencher_vinculo_embargos_terceiro",
                       return_value=True) as m:
        c._preencher_ficha_forms(
            lambda *campos: {"tipo_vinculo": "Embargos de terceiros"}.get(campos[0]))
    m.assert_called_once()


def test_preencher_vinculo_sem_cnj_antigo_nao_tenta_nada():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    with patch.object(c, "_clicar_adicionar_vinculo") as m:
        resultado = c._preencher_vinculo_embargos_terceiro(lambda *campos: None)
    assert resultado is False
    m.assert_not_called()


def test_preencher_vinculo_usa_guid_diferente_pro_select():
    """Input usa '_' no guid, select usa '-' no MESMO guid — se a base
    estivesse errada, o _selecionar_por_id apontaria pro elemento errado."""
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = MagicMock()
    c.page.evaluate.return_value = [
        "Vinculos_3eec516c_e507_4bce_91d3_7523f8a49d37__TipoVinculoId"
    ]
    with patch.object(c, "_clicar_adicionar_vinculo", return_value=True), \
         patch.object(c, "_preencher_lookup_por_id", return_value=True) as m_lookup, \
         patch.object(c, "_selecionar_por_id", return_value=True) as m_select:
        resultado = c._preencher_vinculo_embargos_terceiro(
            lambda *campos: {"vinculo": "5068141-71.2023.8.13.0024"}.get(campos[0]))

    assert resultado is True
    m_select.assert_called_once_with(
        "Vinculos_3eec516c-e507-4bce-91d3-7523f8a49d37__VinculadoAId",
        "0", "Vinculado a (Processo)")
    ids_chamados = [c[0][0] for c in m_lookup.call_args_list]
    assert "Vinculos_3eec516c_e507_4bce_91d3_7523f8a49d37__TipoVinculoText" in ids_chamados
    assert "Vinculos_3eec516c_e507_4bce_91d3_7523f8a49d37__ProcessoVinculoText" in ids_chamados
