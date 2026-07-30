"""Contato da base ganha do 'Capturado no orgao', mesmo com score menor.

30/07, campo Contrario Principal, valor 'Itau Unibanco S/A':

  [0] Itau Unibanco S.A   | Doc: N/A                | Capturado no orgao | 85%
  [1] Itau Unibanco S.A.  | Doc: 60.701.190/0001-04 | Existente na base  | 83%

A ordenacao por score puro elegia a [0] — sem CNPJ e exigindo adicao manual —
porque a grafia sem acento do dado casava melhor com a versao capturada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import _prioridade_origem


def test_base_vence_capturado():
    base = {"origem": "Existente na base"}
    capturado = {"origem": "Capturado no órgão"}
    assert _prioridade_origem(base) < _prioridade_origem(capturado)


def test_ordenacao_reproduz_o_caso_real():
    candidatos = [
        ({"nome": "Itau Unibanco S.A", "origem": "Capturado no órgão", "cpf_cnpj": ""}, 0.85),
        ({"nome": "Itaú Unibanco S.A.", "origem": "Existente na base",
          "cpf_cnpj": "60.701.190/0001-04"}, 0.83),
    ]
    candidatos.sort(key=lambda x: (_prioridade_origem(x[0]), -x[1]))
    assert candidatos[0][0]["cpf_cnpj"] == "60.701.190/0001-04"


def test_capturado_e_ultimo_recurso():
    # Sem equivalente na base, o capturado ainda pode ser escolhido.
    so_capturado = [({"origem": "Capturado no órgão"}, 0.9)]
    so_capturado.sort(key=lambda x: (_prioridade_origem(x[0]), -x[1]))
    assert so_capturado


def test_origem_desconhecida_fica_no_meio():
    assert (_prioridade_origem({"origem": "Existente na base"})
            < _prioridade_origem({"origem": ""})
            < _prioridade_origem({"origem": "Capturado no órgão"}))




def test_matriz_desempata_entre_filiais():
    """Sem CNPJ nos dados, as 4 filiais do Itau empatam em nome e score."""
    from legalone_cadastro import _eh_matriz

    filiais = [
        ({"nome": "Itaú Unibanco S.A.", "origem": "Existente na base",
          "cpf_cnpj": "60.701.190/1719-28"}, 0.83),
        ({"nome": "Itaú Unibanco S.A.", "origem": "Existente na base",
          "cpf_cnpj": "60.701.190/0001-04"}, 0.83),
        ({"nome": "Itaú Unibanco S.A.", "origem": "Existente na base",
          "cpf_cnpj": "60.701.190/1397-90"}, 0.83),
    ]
    filiais.sort(key=lambda x: (_prioridade_origem(x[0]), -x[1], 0 if _eh_matriz(x[0]) else 1))
    assert filiais[0][0]["cpf_cnpj"] == "60.701.190/0001-04"


def test_eh_matriz_reconhece_o_bloco_de_ordem():
    from legalone_cadastro import _eh_matriz

    assert _eh_matriz({"cpf_cnpj": "60.701.190/0001-04"})
    assert not _eh_matriz({"cpf_cnpj": "60.701.190/1719-28"})
    assert not _eh_matriz({"cpf_cnpj": ""})          # sem documento
    assert not _eh_matriz({"cpf_cnpj": "123.456.789-00"})  # CPF, nao CNPJ


if __name__ == "__main__":
    test_base_vence_capturado()
    test_ordenacao_reproduz_o_caso_real()
    test_capturado_e_ultimo_recurso()
    test_origem_desconhecida_fica_no_meio()
    test_matriz_desempata_entre_filiais()
    test_eh_matriz_reconhece_o_bloco_de_ordem()
    print("ok")
