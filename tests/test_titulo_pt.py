"""Nomes de partes vem do Forms em CAIXA ALTA; LegalOne salva o texto
literal. str.title() do Python capitaliza QUALQUER palavra ('Chapadão Do
Sul'), errado pra preposicoes do portugues. _titulo_pt corrige isso e so
mexe em texto que esta' 100% em caixa alta (case misto fica intocado).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import _titulo_pt


def test_preposicoes_ficam_minusculas_no_meio_do_nome():
    assert _titulo_pt("CLINICA CIRURGICA ODONTOLOGICA CHAPADÃO DO SUL LTDA") == \
        "Clinica Cirurgica Odontologica Chapadão do Sul Ltda"
    assert _titulo_pt("CLAUDIANA DA SILVA BRITO") == "Claudiana da Silva Brito"


def test_nao_mexe_em_texto_ja_com_case_misto():
    # Evita reprocessar um valor que ja veio certo (ex.: do Copilot).
    assert _titulo_pt("Já Misto Não Mexe") == "Já Misto Não Mexe"


def test_valores_vazios_nao_explodem():
    assert _titulo_pt("") == ""
    assert _titulo_pt(None) is None


if __name__ == "__main__":
    test_preposicoes_ficam_minusculas_no_meio_do_nome()
    test_nao_mexe_em_texto_ja_com_case_misto()
    test_valores_vazios_nao_explodem()
    print("ok")
