"""Regressao: _opcoes_lookup_visiveis so' reconhecia linhas com
'data-val-id' (lista plana) — mas o catalogo do Pedido "Nome" do recurso
usa o MESMO widget lookupTree da Area/Centro de custo (linha com
'data-val-level'), mesmo sendo uma lista de um nivel so. Por isso a
busca sempre voltava "0 opções" mesmo com o nome exato existindo no
catalogo ('Admissão do recurso especial', confirmado ao vivo em
19/08/2026 — html real da linha: <tr data-val-level="0">). Provavelmente
a causa raiz de varios "pedido nao encontrado" vistos ao longo do dia,
nao so' esse caso."""
from unittest.mock import MagicMock

from legalone_cadastro import LegalOneCadastro


def _mock_page_com_linhas(html_por_seletor: dict):
    """Simula page.query_selector_all devolvendo elementos so' pro
    seletor certo, cada um com inner_text() fixo."""
    page = MagicMock()

    def query_selector_all(seletor):
        textos = html_por_seletor.get(seletor, [])
        elementos = []
        for texto in textos:
            el = MagicMock()
            el.inner_text.return_value = texto
            elementos.append(el)
        return elementos

    page.query_selector_all.side_effect = query_selector_all
    return page


def test_reconhece_linha_data_val_level_lookup_tree():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = _mock_page_com_linhas({
        '.lookup-dropdown:visible tr[data-val-level]': ['Admissão do recurso especial'],
    })
    opcoes = c._opcoes_lookup_visiveis()
    assert [t for _, t in opcoes] == ['Admissão do recurso especial']


def test_ainda_reconhece_lista_plana_data_val_id():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = _mock_page_com_linhas({
        '.lookup-dropdown:visible tr[data-val-id]': ['Tribunal de Justiça do Estado de Minas Gerais'],
    })
    opcoes = c._opcoes_lookup_visiveis()
    assert [t for _, t in opcoes] == ['Tribunal de Justiça do Estado de Minas Gerais']


def test_prefere_lista_plana_quando_ambas_existem():
    """Ordem dos seletores importa: lista plana e' o caso mais comum,
    tentada primeiro; so cai pra lookupTree se a plana vier vazia."""
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.page = _mock_page_com_linhas({
        '.lookup-dropdown:visible tr[data-val-id]': ['Opcao Plana'],
        '.lookup-dropdown:visible tr[data-val-level]': ['Opcao Arvore'],
    })
    opcoes = c._opcoes_lookup_visiveis()
    assert [t for _, t in opcoes] == ['Opcao Plana']
