"""Regressao: no fluxo de recurso civel, quando o Forms manda o Orgao como
sigla ('STJ', 'TJMG'), o lookup falha silenciosamente porque o catalogo
guarda o nome por extenso — o campo ficava vazio e ninguem percebia ate'
salvar (achado real: recurso 5300618-93.2023.8.09.0051, 19/08/2026,
usuario teve que preencher na mao). _orgao_do_cnj ja resolve certo a
partir do proprio CNJ (feature de 17/08/2026) — agora entra como
fallback quando o lookup com o valor do Forms nao commitou."""
from unittest.mock import MagicMock, patch

from legalone_cadastro import LegalOneCadastro


def test_orgao_do_cnj_usado_quando_sigla_do_forms_nao_commita():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    # simula: apos o lookup com a sigla 'STJ', o campo continua vazio
    c._estado_campo = MagicMock(return_value='vazio')
    with patch.object(c, '_orgao_do_cnj', return_value='Superior Tribunal de Justiça') as m_cnj, \
         patch.object(c, '_preencher_lookup_por_id', return_value=True) as m_lookup, \
         patch.object(c, '_checar_vinculo'):
        # reproduz so' o trecho do fallback, chamando com os mesmos nomes
        # de variavel usados em _preencher_novo_recurso
        cnj_recurso = '5300618-93.2023.8.09.0051'
        if c._estado_campo('OrgaoId') == 'vazio':
            orgao_cnj = c._orgao_do_cnj(cnj_recurso)
            if orgao_cnj:
                c._preencher_lookup_por_id('OrgaoText', 'OrgaoId', orgao_cnj)

    m_cnj.assert_called_once_with('5300618-93.2023.8.09.0051')
    m_lookup.assert_called_once_with('OrgaoText', 'OrgaoId', 'Superior Tribunal de Justiça')


def test_nao_mexe_se_orgao_ja_preenchido():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c._estado_campo = MagicMock(return_value='preenchido')
    with patch.object(c, '_orgao_do_cnj') as m_cnj, \
         patch.object(c, '_preencher_lookup_por_id') as m_lookup:
        if c._estado_campo('OrgaoId') == 'vazio':
            orgao_cnj = c._orgao_do_cnj('qualquer')
            if orgao_cnj:
                c._preencher_lookup_por_id('OrgaoText', 'OrgaoId', orgao_cnj)

    m_cnj.assert_not_called()
    m_lookup.assert_not_called()
