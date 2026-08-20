"""
Spike descartável: confirmar o formato real da API interna do Microsoft Forms
(formapi), reutilizando os cookies de sessão salvos em browser_data/state.json.

NAO faz parte do produto final. Ver docs/SPIKE_FORMAPI_ACHADOS.md para os
achados registrados apos a execucao manual deste script.

Uso:
    venv\\Scripts\\python.exe scripts\\spike_formapi.py

Roda a partir da raiz do pacote (pacote_automacao_legalone/), pois
STATE_FILE e os caminhos de saida sao relativos a esse diretorio.
"""
import json
import httpx

STATE_FILE = "browser_data/state.json"

# docs/MAPEAMENTO_FORMS_CIVEL.md
FORM_ID_CIVEL = "Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u"


def montar_cliente_httpx(state_file: str = STATE_FILE) -> httpx.Client:
    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)
    jar = httpx.Cookies()
    for c in state.get("cookies", []):
        jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    return httpx.Client(cookies=jar, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }, follow_redirects=True, timeout=30)


def testar_definicao(cliente: httpx.Client, form_id: str):
    for host in ("https://forms.office.com", "https://forms.cloud.microsoft"):
        url = f"{host}/formapi/api/forms('{form_id}')?$expand=questions"
        r = cliente.get(url)
        print(host, r.status_code, r.headers.get("content-type"))
        if r.status_code == 200:
            with open(f"debug_formapi_definicao_{host.split('//')[1].split('.')[0]}.json", "w", encoding="utf-8") as f:
                f.write(r.text)


def testar_respostas(cliente: httpx.Client, form_id: str):
    candidatos = [
        f"https://forms.office.com/formapi/api/forms('{form_id}')/responses",
        f"https://forms.office.com/formapi/api/forms/{form_id}/responses",
        f"https://forms.cloud.microsoft/formapi/api/forms('{form_id}')/responses",
    ]
    for url in candidatos:
        r = cliente.get(url)
        print(url, r.status_code)
        if r.status_code == 200:
            with open("debug_formapi_respostas.json", "w", encoding="utf-8") as f:
                f.write(r.text)


if __name__ == "__main__":
    cliente = montar_cliente_httpx()
    testar_definicao(cliente, FORM_ID_CIVEL)
    testar_respostas(cliente, FORM_ID_CIVEL)
