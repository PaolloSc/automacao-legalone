"""Valores deferidos vem numa linha so, com o rotulo da pergunta grudado.

Resposta real do Forms (10/08/2026, CNJ 0013231-78.2024.5.15.0077): o campo
multilinha chegou sem quebra de linha nenhuma. O parser antigo quebrava por
'\\n' ou ';', via UMA linha, pegava so o primeiro valor com um nome lixo — e
nenhum valor deferido era preenchido no LegalOne.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

RESPOSTA_REAL = (
    "9. Valor deferido para cada pedido Texto Multilinha. Em caso de acordo, "
    "discriminar parcelas VERBAS RESCISÓRIAS - R$ 2.000,00 "
    "MULTA ARTIGO 477 - R$ 1.000,00 MULTA ARTIGO 467 - 0 "
    "BENEFICIOS CCT - R$ 1.000,00 SEGURO OBRIGATÓRIO - R$ 20.000,00 "
    "ESTABILIDADE ACIDENTE - R$ 50.000,00 INDENIZAÇÃO DANOS MORAIS - 0 "
    "HON ADV SUCUMBENCIAL - R$ 6.000,00"
)


def test_extrai_todos_os_pares_de_uma_linha_so():
    valores = LegalOneCadastro._parse_valores_deferidos(RESPOSTA_REAL)
    assert valores == {
        "verbas rescisorias": "2.000,00",
        "multa artigo 477": "1.000,00",
        "multa artigo 467": "0,00",
        "beneficios cct": "1.000,00",
        "seguro obrigatorio": "20.000,00",
        "estabilidade acidente": "50.000,00",
        "indenizacao danos morais": "0,00",
        "hon adv sucumbencial": "6.000,00",
    }, valores


def test_rotulo_da_pergunta_nao_gruda_no_primeiro_pedido():
    # 'discriminar parcelas VERBAS RESCISORIAS' nao casaria com o pedido.
    assert "verbas rescisorias" in LegalOneCadastro._parse_valores_deferidos(RESPOSTA_REAL)


def test_pedido_zerado_grava_zero_explicito():
    # Campo em branco na tela le-se 'nao informado'; 0,00 diz que foi zerado.
    valores = LegalOneCadastro._parse_valores_deferidos(RESPOSTA_REAL)
    assert valores["multa artigo 467"] == "0,00"
    assert valores["indenizacao danos morais"] == "0,00"


def test_formato_com_quebra_de_linha_continua_valendo():
    valores = LegalOneCadastro._parse_valores_deferidos(
        "Horas extras: R$ 1.500,00\nFérias: R$ 300,00"
    )
    assert valores == {"horas extras": "1.500,00", "ferias": "300,00"}, valores


def test_vazio_nao_explode():
    assert LegalOneCadastro._parse_valores_deferidos(None) == {}
    assert LegalOneCadastro._parse_valores_deferidos("") == {}


if __name__ == "__main__":
    test_extrai_todos_os_pares_de_uma_linha_so()
    test_rotulo_da_pergunta_nao_gruda_no_primeiro_pedido()
    test_pedido_zerado_grava_zero_explicito()
    test_formato_com_quebra_de_linha_continua_valendo()
    test_vazio_nao_explode()
    print("ok")
