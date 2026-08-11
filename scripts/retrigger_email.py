"""Faz o bot reprocessar um e-mail que ele ja marcou como visto.

RODE NA VM, da raiz do pacote:
    venv/bin/python scripts/retrigger_email.py                 # lista
    venv/bin/python scripts/retrigger_email.py --desmarcar 8gQ86AAA=

O e-mail entra em `graph_processed_emails.json` no momento em que o Graph o
entrega (outlook_monitor_graph.py:246), nao quando o cadastro da certo — um
ciclo que falha consome o e-mail do mesmo jeito. Por isso: so desmarque
depois de consertar o que quebrou, senao o proximo ciclo (5 min) come o
e-mail de novo e voce volta pra ca.

O servico guarda o set em memoria e reescreve o arquivo a cada ciclo, entao
mexer no JSON sem reiniciar nao adianta nada — o --desmarcar reinicia.
"""
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
ESTADO = os.path.join(RAIZ, os.getenv('GRAPH_STATE_FILE', 'graph_processed_emails.json'))


def _monitor():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(RAIZ, '.env'))
    from outlook_monitor_graph import OutlookMonitorGraph
    return OutlookMonitorGraph()


def listar() -> int:
    import requests
    m = _monitor()
    url = (f"{m.GRAPH_BASE}/users/{m.user_email}/messages"
           "?$top=20&$orderby=receivedDateTime desc"
           "&$select=id,subject,receivedDateTime")
    r = requests.get(url, headers=m._headers(), timeout=30)
    r.raise_for_status()
    for msg in r.json().get('value', []):
        visto = msg['id'] in m.emails_processados
        print(f"{'JA-VISTO ' if visto else 'pendente '} {msg['receivedDateTime']} "
              f"| {msg['subject'][:52]}")
        print(f"           sufixo: {msg['id'][-12:]}")
    return 0


def desmarcar(sufixo: str) -> int:
    with open(ESTADO, encoding='utf-8') as f:
        ids = json.load(f)
    alvos = [i for i in ids if i.endswith(sufixo)]
    if len(alvos) != 1:
        print(f"[ERRO] sufixo {sufixo!r} casou com {len(alvos)} ids — precisa casar com 1")
        return 1

    os.replace(ESTADO, ESTADO + '.bak')
    with open(ESTADO, 'w', encoding='utf-8') as f:
        json.dump([i for i in ids if i != alvos[0]], f)
    print(f"[OK] removido ({len(ids)} -> {len(ids) - 1}); backup em {ESTADO}.bak")

    # Sem reiniciar, o set em memoria sobrescreve o arquivo no proximo ciclo.
    subprocess.run(['sudo', 'systemctl', 'restart', 'legalone'], check=True)
    print("[OK] servico reiniciado — o e-mail volta no proximo ciclo (ate 5 min)")
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--desmarcar':
        raise SystemExit(desmarcar(sys.argv[2]))
    raise SystemExit(listar())
