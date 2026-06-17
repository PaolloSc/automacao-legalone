"""Cliente HTTP da API REST do LegalOne — estilo headless (puro requests).

Espelha o padrão de jt_juris_teste_headless.py: Session com retry, auth via
.env, JSON in/out, fail-safe com log. Único módulo que conhece base URL e auth.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("LEGALONE_API")


def _build_session() -> requests.Session:
    try:
        from urllib3.util.retry import Retry
        retry = Retry(total=3, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "POST"]))
        adapter = HTTPAdapter(max_retries=retry)
    except Exception:
        adapter = HTTPAdapter(max_retries=3)
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


class LegalOneApiClient:
    def __init__(self, client_id: str, client_secret: str, token_url: str,
                 base_url: str, timeout: int = 30):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = _build_session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    @classmethod
    def from_env(cls) -> "LegalOneApiClient":
        from config_automacao import LEGALONE_API_CONFIG as cfg
        return cls(
            client_id=cfg["client_id"], client_secret=cfg["client_secret"],
            token_url=cfg["token_url"], base_url=cfg["base_url"],
            timeout=cfg.get("timeout", 30),
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_token(self) -> Optional[str]:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token
        try:
            resp = self.session.post(
                self.token_url,
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.error("[AUTH] token falhou status=%s body=%s",
                             resp.status_code, resp.text[:200])
                return None
            body = resp.json() or {}
            self._token = body.get("access_token")
            self._token_expiry = now + int(body.get("expires_in", 3600)) - 60
            return self._token
        except Exception as e:
            logger.error("[AUTH] erro ao obter token: %s", e)
            return None

    def _headers(self) -> dict:
        token = self.get_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.get(url, headers=self._headers(),
                                    params=params, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("[GET] %s status=%s body=%s", path,
                               resp.status_code, resp.text[:200])
                return {}
            return resp.json() or {}
        except Exception as e:
            logger.warning("[GET] %s erro: %s", path, e)
            return {}

    def post_json(self, path: str, payload: dict) -> tuple[int, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.post(url, json=payload,
                                     headers=self._headers(), timeout=self.timeout)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            if resp.status_code >= 400:
                logger.error("[POST] %s status=%s body=%s", path,
                             resp.status_code, str(body)[:300])
            return resp.status_code, body
        except Exception as e:
            logger.error("[POST] %s erro: %s", path, e)
            return 0, {"error": str(e)}
