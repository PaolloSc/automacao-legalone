"""Regressao: resposta 233 do Forms civel mandou os pedidos numa unica linha
separados por "- Maiuscula" (bullet), em vez de quebra de linha. O parser so
separava por \n/;, entao virava 1 pedido gigante que nao batia no catalogo do
LegalOne e travava o cadastro (17/08/2026)."""
from legalone_cadastro import LegalOneCadastro

TEXTO_233 = (
    "- Concessão do efeito suspensivo, para suspender a exigibilidade do "
    "recolhimento das custas processuais complementares até o julgamento "
    "definitivo do recurso: chance de êxito provável - Conceder aos "
    "Agravantes os benefícios da gratuidade de justiça: chance de êxito "
    "possível - Isenção parcial ou redução percentual das custas: chance de "
    "êxito possível - Reabertura do prazo para recolhimento das custas "
    "complementares fixadas pelo Juízo de origem: chance de êxito provável"
)


def test_bullet_separado_por_hifen_maiuscula_vira_quatro_pedidos():
    cadastro = LegalOneCadastro(username="", password="")
    itens = cadastro._parse_pedidos_detalhados(TEXTO_233)
    assert len(itens) == 4
    assert itens[0]["pedido"].startswith("Concessão do efeito suspensivo")
    assert itens[1]["pedido"].startswith("Conceder aos Agravantes")
    assert itens[2]["pedido"].startswith("Isenção parcial")
    assert itens[3]["pedido"].startswith("Reabertura do prazo")


def test_grau_minusculo_apos_hifen_nao_quebra_a_linha():
    cadastro = LegalOneCadastro(username="", password="")
    itens = cadastro._parse_pedidos_detalhados("Verbas Rescisórias - possível")
    assert len(itens) == 1
    assert itens[0]["grau"] == "Possível"


def test_split_por_quebra_de_linha_continua_funcionando():
    cadastro = LegalOneCadastro(username="", password="")
    itens = cadastro._parse_pedidos_detalhados("Multa\nFérias Proporcionais")
    assert len(itens) == 2
