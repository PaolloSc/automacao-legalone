"""Arquivamento completo: casar o valor deferido do Forms com o pedido certo.

A parte de navegacao/DOM so da' para exercitar no LegalOne; o que quebra em
silencio e' o casamento nome-do-pedido -> valor, entao e' isso que fica preso
por teste.
"""
from legalone_cadastro import LegalOneCadastro


parse = LegalOneCadastro._parse_valores_deferidos


def test_parse_uma_linha_por_pedido():
    texto = (
        "Horas extras: R$ 1.500,00\n"
        "13o Salario Proporcional - R$ 320,45\n"
        "Danos morais: indeferido\n"
    )
    assert parse(texto) == {
        "horas extras": "1.500,00",
        "13o salario proporcional": "320,45",
    }


def test_parse_aceita_lista_e_ponto_e_virgula():
    assert parse(["Multa 477: R$ 900,00; FGTS+40%: R$ 1.000,00"]) == {
        "multa 477": "900,00",
        "fgts+40%": "1.000,00",
    }


def test_parse_vazio():
    assert parse(None) == {} and parse("") == {} and parse("NAO LOCALIZADO") == {}


def test_valor_casa_pelo_nome_do_pedido():
    bot = LegalOneCadastro.__new__(LegalOneCadastro)  # sem navegador
    valores = parse("Horas extras: R$ 1.500,00\nAviso previo: R$ 200,00")
    assert bot._valor_deferido_do_pedido("Horas Extras", valores) == "1.500,00"
    assert bot._valor_deferido_do_pedido("Aviso Prévio", valores) == "200,00"
    # Pedido que o Forms nao valorou nao pode herdar o valor de outro.
    assert bot._valor_deferido_do_pedido("Danos morais", valores) == ""
