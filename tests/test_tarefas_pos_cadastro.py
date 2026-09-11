"""Apos cadastro bem-sucedido, o bot cria 2 tarefas no processo: revisao da
Maria Karolyne e ciencia do advogado responsavel. Prazo: inicio = agora,
conclusao = +2 dias corridos, para as duas.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

AGORA = datetime(2026, 9, 10, 14, 30)


def _bot():
    bot = object.__new__(LegalOneCadastro)
    bot.page = None
    return bot


def test_resolve_responsavel_pelo_campo_advogado():
    bot = _bot()
    nome, email = bot._resolver_advogado_responsavel({"advogado": "Monica Pinheiro"})
    assert nome == "Mônica Furtado Pinheiro Chagas"
    assert email == "monica@carvalhofurtadoadv.com.br"


def test_resolve_responsavel_default_quando_ausente():
    bot = _bot()
    nome, email = bot._resolver_advogado_responsavel({})
    assert email == "paollo.sanchez@carvalhofurtadoadv.com.br"


def test_resolve_responsavel_none_quando_ambiguo():
    bot = _bot()
    assert bot._resolver_advogado_responsavel({"advogado": "Fulano de Tal"}) is None


def test_monta_duas_tarefas_com_prazo_de_dois_dias():
    bot = _bot()
    tarefas = bot._montar_tarefas_pos_cadastro(
        {"cnj": "0010481-42.2025.5.03.0097", "advogado": "Monica Pinheiro"},
        agora=AGORA,
    )
    assert len(tarefas) == 2

    revisao, ciencia = tarefas
    assert revisao["envolvido_nome"] == "Maria Karolyne Moraes Malard"
    assert "0010481-42.2025.5.03.0097" in revisao["descricao"]
    assert revisao["inicio"] == AGORA
    assert revisao["conclusao"] == AGORA + timedelta(days=2)

    assert ciencia["envolvido_nome"] == "Mônica Furtado Pinheiro Chagas"
    assert "0010481-42.2025.5.03.0097" in ciencia["descricao"]
    assert ciencia["inicio"] == AGORA
    assert ciencia["conclusao"] == AGORA + timedelta(days=2)


def test_so_uma_tarefa_quando_responsavel_nao_resolve():
    bot = _bot()
    tarefas = bot._montar_tarefas_pos_cadastro(
        {"cnj": "0010481-42.2025.5.03.0097", "advogado": "Fulano de Tal"},
        agora=AGORA,
    )
    assert len(tarefas) == 1
    assert tarefas[0]["envolvido_nome"] == "Maria Karolyne Moraes Malard"


if __name__ == "__main__":
    test_resolve_responsavel_pelo_campo_advogado()
    test_resolve_responsavel_default_quando_ausente()
    test_resolve_responsavel_none_quando_ambiguo()
    test_monta_duas_tarefas_com_prazo_de_dois_dias()
    test_so_uma_tarefa_quando_responsavel_nao_resolve()
    print("ok")
