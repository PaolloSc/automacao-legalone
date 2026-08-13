"""Quem preencheu o Forms recebe a confirmacao — so' quando da' certo.

O Forms nao identifica o respondente na resposta; quem diz e' a notificacao
("Voce recebeu uma nova resposta de Marcela Leite Kato"). Dali sai o nome, e o
equipe.py converte em e-mail. No erro, a notificacao continua so' para quem
cuida do bot (paollo + arquivo).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automacao_legalone_completa import AutomacaoLegalOne
from outlook_monitor_graph import OutlookMonitorGraph

NOTIFICACAO = (
    "<html><body><p>Cadastro de processos NOVOS LegalOne trabalhista</p>"
    "<p>Ol&aacute;,</p><p>Voc&ecirc; recebeu uma nova resposta de "
    "<b>Marcela Leite Kato</b>.</p><a href='https://forms.office.com/x'>"
    "Exibir resultados</a></body></html>"
)


def test_extrai_nome_de_quem_respondeu():
    assert OutlookMonitorGraph.extrair_respondente(NOTIFICACAO) == "Marcela Leite Kato"


def test_corpo_sem_respondente():
    assert OutlookMonitorGraph.extrair_respondente("<p>qualquer coisa</p>") is None
    assert OutlookMonitorGraph.extrair_respondente("") is None


def test_nome_vira_email_do_escritorio():
    achado = AutomacaoLegalOne._email_do_respondente({"respondente": "Marcela Leite Kato"})
    assert achado == "trabalhista3@carvalhofurtadoadv.com.br"


def test_nome_ambiguo_nao_avisa_ninguem():
    """'Pinheiro' e' sobrenome de duas pessoas — melhor nao mandar do que errar."""
    assert AutomacaoLegalOne._email_do_respondente({"respondente": "Pinheiro"}) is None
    assert AutomacaoLegalOne._email_do_respondente({"respondente": "Fulano de Tal"}) is None


def test_copilot_nao_tem_respondente():
    """No fluxo do Copilot nao existe notificacao do Forms: nada muda."""
    assert AutomacaoLegalOne._email_do_respondente({"dados_diretos": {"cnj": "x"}}) is None
    assert AutomacaoLegalOne._email_do_respondente(None) is None
