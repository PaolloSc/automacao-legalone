"""Cliente HTTP para a API interna do Microsoft Forms (formapi).

Nao e' uma API publica/documentada — ver docs/SPIKE_FORMAPI_ACHADOS.md pro
levantamento completo (host, URLs, formato de autenticacao). Usa os cookies
de sessao salvos em browser_data/state.json pelo login manual
(scripts/capturar_sessao_forms.py) — nao funciona com service principal.
"""
from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

FORMS_API_HOST = "https://forms.cloud.microsoft"


class SessaoFormsExpirada(Exception):
    """Cookies de state.json nao autenticam mais na API do Forms."""


class FormsApiCliente:
    def __init__(self, state_file: str, tenant_id: str, user_id: str, timeout: float = 30.0):
        self.state_file = state_file
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._cliente = self._montar_cliente(state_file, timeout)

    @staticmethod
    def _montar_cliente(state_file: str, timeout: float) -> httpx.Client:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        jar = httpx.Cookies()
        csrf_valor = None
        for c in state.get("cookies", []):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
            if c["name"] == "__RequestVerificationToken":
                csrf_valor = c["value"]

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OData-Version": "4.0",
            "Accept-Language": "pt-BR",
            "X-MS-Form-Request-Source": "ms-formweb",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if csrf_valor:
            # dupla submissao CSRF: o header precisa ecoar o valor do cookie
            # __RequestVerificationToken. Sem browser, sem chamada extra — e'
            # so' ler o proprio cookie (docs/SPIKE_FORMAPI_ACHADOS.md).
            headers["__RequestVerificationToken"] = csrf_valor

        return httpx.Client(cookies=jar, headers=headers, timeout=timeout)

    def _base_url_forms(self, form_id: str) -> str:
        return (
            f"{FORMS_API_HOST}/formapi/api/{self.tenant_id}/users/{self.user_id}"
            f"/light/forms('{form_id}')"
        )

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        r = self._cliente.get(url, params=params)
        if r.status_code == 401:
            corpo_erro = ""
            try:
                corpo_erro = r.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise SessaoFormsExpirada(
                f"Sessao Microsoft expirada/invalida ({self.state_file}) — {corpo_erro} "
                "— rode scripts/capturar_sessao_forms.py de novo e copie o state.json"
            )
        if r.status_code in (301, 302) and "login" in r.headers.get("location", "").lower():
            raise SessaoFormsExpirada(
                f"Sessao Microsoft expirada ({self.state_file}) — rode "
                "scripts/capturar_sessao_forms.py de novo e copie o state.json"
            )
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "json" not in content_type:
            raise SessaoFormsExpirada(
                f"Resposta nao-JSON da API do Forms (content-type={content_type}) — "
                "provavel pagina de login HTML"
            )
        return r.json()

    def definicao_formulario(self, form_id: str) -> dict:
        params = {
            "$select": "id,title,questions",
            "$expand": "questions($expand=choices)",
        }
        return self._get_json(self._base_url_forms(form_id), params=params)

    def listar_respostas(self, form_id: str, skip: int = 0, top: int = 50) -> list[dict]:
        url = f"{self._base_url_forms(form_id)}/responses"
        params = {"$expand": "comments", "$top": str(top), "$skip": str(skip)}
        dados = self._get_json(url, params=params)
        respostas = dados.get("value", []) if isinstance(dados, dict) else dados
        # 'answers' vem como STRING JSON-encoded — decodifica aqui pra quem
        # chama ja' receber uma lista de dict, nao uma string pra reparsear.
        for resp in respostas:
            crua = resp.get("answers")
            if isinstance(crua, str):
                resp["answers"] = json.loads(crua) if crua else []
        return respostas
