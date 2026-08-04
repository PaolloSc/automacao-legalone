"""O Orgao sai do painel 'Monitorar publicacoes', que so tem o nome do diario."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

_f = LegalOneCadastro._orgao_do_monitoramento


def test_extrai_do_texto_real_do_painel():
    assert _f("TRT03 - Diário do Tribunal Regional do Trabalho da 3ª Região") == "TRT 3"


def test_zero_a_esquerda_e_dois_digitos():
    assert _f("TRT15 - Diário ...") == "TRT 15"
    assert _f("trt 08 - qualquer coisa") == "TRT 8"


def test_sem_trt_nao_inventa():
    assert _f("DJEN - Diário de Justiça Eletrônico Nacional") == ""
    assert _f("") == ""


if __name__ == "__main__":
    test_extrai_do_texto_real_do_painel()
    test_zero_a_esquerda_e_dois_digitos()
    test_sem_trt_nao_inventa()
    print("ok")
