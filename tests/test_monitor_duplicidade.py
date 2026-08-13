"""O e-mail do Copilot chega DUAS vezes na caixa.

O Power Automate manda de paollo.sanchez@ para paollo.sanchez@, entao a mesma
mensagem existe em "Itens Enviados" e na "Caixa de Entrada". A consulta do
Graph e' em /messages (todas as pastas) e cada copia tem um `id` diferente —
so' o `internetMessageId` e' o mesmo. Dedupando por `id`, o bot processava as
duas e mandava dois e-mails de erro por peticao (visto em 13/08/2026, 11:57 e
14:57).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import outlook_monitor_graph as omg


CORPO = '<p>{ "cnj": "0010555-44.2025.5.03.0012", "cliente": "Fulano" }</p>'
MESMO_IMID = "<RIXP284MB37846D40E71AA00355EEED5DDCDB2@RIXP284MB3784.PROD.OUTLOOK.COM>"


def _duas_copias():
    """As duas copias da MESMA mensagem, como o Graph devolve."""
    base = {
        "subject": omg.OutlookMonitorGraph.COPILOT_ASSUNTO,
        "from": {"emailAddress": {"address": "paollo.sanchez@carvalhofurtadoadv.com.br"}},
        "receivedDateTime": "2026-08-13T14:57:56Z",
        "body": {"content": CORPO},
        "internetMessageId": MESMO_IMID,
    }
    return [dict(base, id="AAA_copia_enviados"), dict(base, id="BBB_copia_entrada")]


def _monitor(monkeypatch, mensagens):
    mon = object.__new__(omg.OutlookMonitorGraph)
    mon.user_email = "paollo.sanchez@carvalhofurtadoadv.com.br"
    mon.assunto_filtro = "Forms"
    mon.remetente_filtro = ""
    mon.emails_processados = set()
    mon._headers = lambda: {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": mensagens}

    monkeypatch.setattr(omg.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(omg.requests, "patch", lambda *a, **k: None)
    monkeypatch.setattr(omg, "_save_state", lambda ids: None)
    return mon


def test_mesma_mensagem_em_duas_pastas_processa_uma_vez(monkeypatch):
    mon = _monitor(monkeypatch, _duas_copias())
    assert len(mon.buscar_novos_emails()) == 1


def test_mensagens_diferentes_continuam_passando(monkeypatch):
    """Duas peticoes de verdade nao podem ser confundidas com duplicata."""
    a, b = _duas_copias()
    b["internetMessageId"] = "<outra-peticao@outlook.com>"
    mon = _monitor(monkeypatch, [a, b])
    assert len(mon.buscar_novos_emails()) == 2


def test_estado_antigo_por_id_continua_valendo(monkeypatch):
    """graph_processed_emails.json gravado antes da mudanca guarda id de
    mensagem. Sem honrar isso, o primeiro ciclo apos o deploy reprocessaria a
    janela inteira (1440 min) e recadastraria tudo."""
    copias = _duas_copias()
    mon = _monitor(monkeypatch, copias)
    mon.emails_processados = {copias[0]["id"], copias[1]["id"]}
    assert mon.buscar_novos_emails() == []


def test_sem_internet_message_id_cai_no_id_da_mensagem(monkeypatch):
    """Graph sem o campo (ou mock antigo): dedupe volta a ser pelo id."""
    a, b = _duas_copias()
    del a["internetMessageId"]
    del b["internetMessageId"]
    mon = _monitor(monkeypatch, [a, b])
    assert len(mon.buscar_novos_emails()) == 2
