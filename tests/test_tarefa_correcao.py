"""Quando alguem clica 'Nao validei' no card do Teams (advogado ou Maria), o
fluxo do Power Automate manda um e-mail 'LegalOne - Correcao Necessaria' com
JSON (cnj, pasta, advogado_email, advogado_nome, motivo, quem_recusou). O bot
cria uma tarefa de correcao no LegalOne pro advogado responsavel, com o
motivo na descricao. Prazo: mesma regra das tarefas pos-cadastro (+2 dias).
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

AGORA = datetime(2026, 9, 11, 16, 0)

DADOS_CORRECAO = {
    "cnj": "0010481-42.2025.5.03.0097",
    "pasta": "Proc - 0006136",
    "advogado_email": "monica@carvalhofurtadoadv.com.br",
    "advogado_nome": "Mônica Furtado Pinheiro Chagas",
    "quem_recusou": "maria",
    "motivo": "Falta o valor da causa",
}


def _bot():
    bot = object.__new__(LegalOneCadastro)
    bot.page = None
    return bot


def test_tarefa_correcao_vai_para_advogado_responsavel():
    bot = _bot()
    tarefa = bot._montar_tarefa_correcao(DADOS_CORRECAO, agora=AGORA)
    assert tarefa["envolvido_nome"] == "Mônica Furtado Pinheiro Chagas"
    assert tarefa["envolvido_email"] == "monica@carvalhofurtadoadv.com.br"
    assert tarefa["inicio"] == AGORA
    assert tarefa["conclusao"] == AGORA + timedelta(days=2)


def test_descricao_cita_cnj_e_motivo():
    bot = _bot()
    tarefa = bot._montar_tarefa_correcao(DADOS_CORRECAO, agora=AGORA)
    assert "0010481-42.2025.5.03.0097" in tarefa["descricao"]
    assert "Falta o valor da causa" in tarefa["descricao"]


def test_descricao_sem_motivo_nao_quebra():
    bot = _bot()
    dados = dict(DADOS_CORRECAO, motivo="")
    tarefa = bot._montar_tarefa_correcao(dados, agora=AGORA)
    assert "0010481-42.2025.5.03.0097" in tarefa["descricao"]


if __name__ == "__main__":
    test_tarefa_correcao_vai_para_advogado_responsavel()
    test_descricao_cita_cnj_e_motivo()
    test_descricao_sem_motivo_nao_quebra()
    print("ok")
