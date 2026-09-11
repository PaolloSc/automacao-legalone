"""Microsoft Forms mudou o dominio de envio de '...@microsoft.com' para
'no-reply@forms.mail.microsoft' (sem .com) em ago/2026. O filtro hardcoded
'microsoft.com' parou de bater com QUALQUER email do Forms desde entao --
nada era cadastrado por semanas (achado ao vivo 11/09/2026, ultimo cadastro
real em 21/08/2026 ate' a correcao).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import outlook_monitor_graph as omg


def _resposta_forms(remetente: str):
    return {
        "subject": "Nova resposta de Cadastro de processos NOVOS LegalOne trabalhista",
        "from": {"emailAddress": {"address": remetente}},
        "receivedDateTime": "2026-09-11T14:21:59Z",
        "body": {"content": '<a href="https://forms.office.com/Pages/ResponsePage.aspx">link</a>'},
        "internetMessageId": "<msg-1@forms.mail.microsoft>",
        "id": "AAA",
    }


def _monitor(monkeypatch, mensagens, remetente_filtro):
    mon = object.__new__(omg.OutlookMonitorGraph)
    mon.user_email = "paollo.sanchez@carvalhofurtadoadv.com.br"
    mon.assunto_filtro = ["Cadastro de processos NOVOS LegalOne trabalhista"]
    mon.remetente_filtro = remetente_filtro
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


def test_filtro_atual_bate_com_o_dominio_novo_do_forms(monkeypatch):
    mon = _monitor(
        monkeypatch,
        [_resposta_forms("no-reply@forms.mail.microsoft")],
        remetente_filtro="microsoft",  # valor corrigido
    )
    assert len(mon.buscar_novos_emails()) == 1


def test_filtro_antigo_derrubava_o_dominio_novo(monkeypatch):
    """Documenta o bug: com o valor ANTIGO ('microsoft.com'), o email do
    Forms simplesmente desaparece -- sem erro, sem log de falha."""
    mon = _monitor(
        monkeypatch,
        [_resposta_forms("no-reply@forms.mail.microsoft")],
        remetente_filtro="microsoft.com",  # valor antigo/quebrado
    )
    assert mon.buscar_novos_emails() == []


def test_filtro_novo_continua_aceitando_o_dominio_antigo(monkeypatch):
    mon = _monitor(
        monkeypatch,
        [_resposta_forms("no-reply@forms.microsoft.com")],
        remetente_filtro="microsoft",
    )
    assert len(mon.buscar_novos_emails()) == 1


if __name__ == "__main__":
    print("rode via pytest (usa monkeypatch)")
