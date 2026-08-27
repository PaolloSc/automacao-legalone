"""So' leitura: pega os ultimos e-mails de Forms (Graph API) e testa o
regex extrair_respondente contra o corpo real, pra achar por que so 3/44
casos conseguiram identificar quem respondeu.

    python scripts/testar_extrair_respondente.py
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(RAIZ)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))
load_dotenv()

from outlook_monitor_graph import OutlookMonitorGraph  # noqa: E402
import requests  # noqa: E402


def main():
    m = OutlookMonitorGraph()
    url = (f"{m.GRAPH_BASE}/users/{m.user_email}/messages"
           "?$top=50&$orderby=receivedDateTime desc"
           "&$select=id,subject,receivedDateTime,body")
    r = requests.get(url, headers=m._headers(), timeout=30)
    r.raise_for_status()
    msgs = r.json().get("value", [])

    formularios = [msg for msg in msgs
                   if any(a.lower() in (msg.get("subject") or "").lower()
                          for a in m.assunto_filtro)]
    print(f"[TOTAL] {len(msgs)} emails recentes, {len(formularios)} de Forms")

    for msg in formularios[:5]:
        corpo = (msg.get("body") or {}).get("content", "")
        nome = m.extrair_respondente(corpo)
        print(f"\n[EMAIL] {msg['subject'][:60]!r} em {msg['receivedDateTime']}")
        print(f"[RESPONDENTE EXTRAIDO] {nome!r}")
        # Mostra o trecho do corpo perto de 'resposta de' pra debug.
        texto = re.sub(r'<[^>]+>', ' ', corpo)
        import html as html_mod
        texto = html_mod.unescape(texto)
        idx = texto.lower().find("resposta de")
        if idx >= 0:
            print(f"[TRECHO] ...{texto[max(0,idx-30):idx+120]!r}...")
        else:
            print("[TRECHO] 'resposta de' NAO aparece no corpo")


if __name__ == "__main__":
    main()
