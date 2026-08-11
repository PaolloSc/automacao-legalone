"""Cada tipo do Forms tem que virar uma tarefa distinta.

Regressao de 05/08: 'DECISÃO' in 'DECISÕES' era False, entao decisao caia em
GENERICO e seguia o fluxo de cadastro inicial. Arquivamento simples/completo
tambem chegavam la — sem fluxo proprio, o cadastro abria o processo pra alterar.
"""
import pytest

from forms_mapping import TIPO_TAREFA_POR_CADASTRO, detectar_tipo_cadastro


@pytest.mark.parametrize("bruto,canonico,tarefa", [
    ("Cadastro inicial", "CADASTRO INICIAL", "CADASTRO_INICIAL"),
    ("DECISÕES", "DECISOES", "DECISAO"),          # como o extrator do Forms devolve
    ("Decisoes", "DECISOES", "DECISAO"),          # como o Copilot devolve
    ("Recurso", "RECURSO", "RECURSO"),
    ("Arquivamento simples", "ARQUIVAMENTO SIMPLES", "ARQUIVAMENTO"),
    ("Arquivamento completo", "ARQUIVAMENTO COMPLETO", "ARQUIVAMENTO"),
])
def test_tipo_do_forms_vira_tarefa_certa(bruto, canonico, tarefa):
    assert detectar_tipo_cadastro(bruto) == canonico
    assert TIPO_TAREFA_POR_CADASTRO[canonico] == tarefa


def test_arquivamento_nao_e_cadastro_inicial():
    from legalone_cadastro import eh_cadastro_inicial
    for tipo in ("ARQUIVAMENTO SIMPLES", "ARQUIVAMENTO COMPLETO", "DECISOES"):
        assert not eh_cadastro_inicial({"tipo_cadastro": tipo,
                                        "tipo_tarefa_identificada": TIPO_TAREFA_POR_CADASTRO[tipo]})
