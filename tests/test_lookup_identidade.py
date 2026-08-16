"""Escolha de opção em lookup: semelhança sozinha erra de tribunal."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legalone_cadastro import LegalOneCadastro


def _bot():
    return LegalOneCadastro.__new__(LegalOneCadastro)


def test_veta_outro_tribunal():
    bot = _bot()
    alvo = ["Tribunal de Justiça do Estado de São Paulo"]
    # 0.85 de semelhança, mas nada de 'são paulo' — não pode ser aceito
    assert not bot._compartilha_identidade(alvo, "Tribunal de Justiça do Estado da Paraíba")
    assert bot._compartilha_identidade(alvo, "Tribunal de Justiça do Estado de São Paulo")


def test_aceita_abreviacao_do_catalogo():
    bot = _bot()
    assert bot._compartilha_identidade(
        ["Tribunal Regional do Trabalho da 3ª Região"], "TRT 3ª Região")


def test_opcao_em_colunas_casa_pela_coluna():
    bot = _bot()
    opcao = "SP\tSão Paulo\tBrasil"
    assert bot._compartilha_identidade(["SP"], opcao)
    assert max(bot._calcular_similaridade("SP", p) for p in opcao.split("\t")) == 1.0
