"""
Claude Brain — Cérebro da automação via OAuth browser login.

Fluxo de autenticação:
1. Se auth.json existe com tokens válidos → usa direto
2. Se não → abre navegador para login OAuth na Anthropic
3. Recebe callback em localhost, troca code por tokens
4. Salva tokens em auth.json para reuso

Faz refresh automático quando o access token expira.
"""

import json
import os
import sys
import time
import logging
import hashlib
import secrets
import base64
import webbrowser
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Caminho padrão para salvar tokens
_DEFAULT_AUTH_PATH = Path.home() / ".claude_brain_auth.json"

# Caminhos adicionais para buscar auth.json existente (compatibilidade)
_AUTH_PATHS = [
    _DEFAULT_AUTH_PATH,
    Path.home() / ".gsd" / "agent" / "auth.json",
]
if os.getenv("APPDATA"):
    _AUTH_PATHS.append(Path(os.getenv("APPDATA")) / "gsd" / "agent" / "auth.json")
if os.getenv("USERPROFILE"):
    _AUTH_PATHS.append(Path(os.getenv("USERPROFILE")) / ".gsd" / "agent" / "auth.json")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_AUTH_URL = "https://console.anthropic.com/oauth/authorize"
ANTHROPIC_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_API_VERSION = "2023-06-01"

CALLBACK_PORT = 19485
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _find_auth_file() -> Optional[Path]:
    """Encontra auth.json existente."""
    for p in _AUTH_PATHS:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Aceita formato antigo (anthropic.type=oauth) ou novo (access_token direto)
                if "access_token" in data or (
                    isinstance(data.get("anthropic"), dict)
                    and data["anthropic"].get("access")
                ):
                    return p
            except (json.JSONDecodeError, KeyError):
                continue
    return None


def _generate_pkce() -> tuple[str, str]:
    """Gera code_verifier e code_challenge para PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler HTTP para receber callback OAuth."""

    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/callback":
            if "code" in params:
                _OAuthCallbackHandler.auth_code = params["code"][0]
                self._respond(200, "Login realizado com sucesso! Pode fechar esta aba.")
            elif "error" in params:
                _OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
                self._respond(400, f"Erro no login: {_OAuthCallbackHandler.error}")
            else:
                self._respond(400, "Resposta inesperada do servidor OAuth.")
        else:
            self._respond(404, "Not found")

    def _respond(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude Brain Auth</title>
<style>body{{font-family:system-ui;display:flex;justify-content:center;align-items:center;
height:100vh;margin:0;background:#f5f5f5}}
.card{{background:white;padding:2rem;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1);
text-align:center;max-width:400px}}</style></head>
<body><div class="card"><h2>{'&#10004; ' if code == 200 else '&#10006; '}{message}</h2></div></body></html>"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Silencia logs do HTTP server


def _oauth_browser_login() -> dict:
    """
    Abre navegador para login OAuth, recebe callback, retorna tokens.

    Returns:
        dict com access_token, refresh_token, expires_in
    """
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    # Reset handler state
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.error = None

    # Inicia servidor local para callback
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _OAuthCallbackHandler)
    server.timeout = 120  # 2 min timeout

    auth_params = urlencode({
        "response_type": "code",
        "client_id": ANTHROPIC_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": "user:inference",
    })

    auth_url = f"{ANTHROPIC_AUTH_URL}?{auth_params}"

    print("\n" + "=" * 60)
    print("  CLAUDE BRAIN — Autenticacao OAuth")
    print("=" * 60)
    print(f"\n  Abrindo navegador para login...")
    print(f"  Se nao abrir automaticamente, acesse:")
    print(f"  {auth_url}")
    print(f"\n  Aguardando callback em localhost:{CALLBACK_PORT}...")
    print("=" * 60 + "\n")

    webbrowser.open(auth_url)

    # Aguarda callback (bloqueia até receber request ou timeout)
    while _OAuthCallbackHandler.auth_code is None and _OAuthCallbackHandler.error is None:
        server.handle_request()

    server.server_close()

    if _OAuthCallbackHandler.error:
        raise RuntimeError(f"OAuth login falhou: {_OAuthCallbackHandler.error}")

    if not _OAuthCallbackHandler.auth_code:
        raise RuntimeError("OAuth login: timeout sem receber callback")

    # Troca code por tokens
    logger.info("[CLAUDE BRAIN] Trocando auth code por tokens...")
    resp = requests.post(
        ANTHROPIC_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "code": _OAuthCallbackHandler.auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": ANTHROPIC_CLIENT_ID,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Falha ao trocar code por token: {resp.status_code} {resp.text}"
        )

    return resp.json()


class ClaudeBrain:
    """
    Cerebro IA da automacao — usa Claude via OAuth token.

    Uso:
        brain = ClaudeBrain()
        resposta = brain.ask("Classifique este processo: ...")
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        auth_path: Optional[str] = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Tenta encontrar auth.json existente
        path = Path(auth_path) if auth_path else _find_auth_file()

        if path and path.exists():
            self._auth_path = path
            self._load_tokens()
        else:
            # Nenhum token salvo → login via navegador
            logger.info("[CLAUDE BRAIN] Nenhum token encontrado. Iniciando login via navegador...")
            token_data = _oauth_browser_login()
            self._auth_path = Path(auth_path) if auth_path else _DEFAULT_AUTH_PATH
            self._access_token = token_data["access_token"]
            self._refresh_token = token_data.get("refresh_token", "")
            self._expires = int(time.time() * 1000) + token_data.get("expires_in", 3600) * 1000
            self._save_tokens()
            logger.info("[CLAUDE BRAIN] Login OAuth concluido. Tokens salvos.")

        logger.info(f"[CLAUDE BRAIN] Inicializado — modelo: {self.model}")

    def _load_tokens(self):
        """Carrega tokens do auth.json (suporta formato antigo e novo)."""
        data = json.loads(self._auth_path.read_text(encoding="utf-8"))

        # Formato novo (direto)
        if "access_token" in data:
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token", "")
            self._expires = data.get("expires", 0)
            return

        # Formato antigo (anthropic.type=oauth)
        anthropic = data.get("anthropic", {})
        if anthropic.get("type") == "oauth":
            self._access_token = anthropic["access"]
            self._refresh_token = anthropic["refresh"]
            self._expires = anthropic.get("expires", 0)
            return

        raise ValueError("auth.json nao contem tokens OAuth validos")

    def _save_tokens(self):
        """Salva tokens no auth.json."""
        # Se arquivo existe, tenta preservar formato
        if self._auth_path.exists():
            try:
                data = json.loads(self._auth_path.read_text(encoding="utf-8"))
                if "anthropic" in data and isinstance(data["anthropic"], dict):
                    data["anthropic"]["access"] = self._access_token
                    data["anthropic"]["refresh"] = self._refresh_token
                    data["anthropic"]["expires"] = self._expires
                    self._auth_path.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        # Formato novo
        data = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expires": self._expires,
        }
        self._auth_path.parent.mkdir(parents=True, exist_ok=True)
        self._auth_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _is_expired(self) -> bool:
        return time.time() * 1000 >= (self._expires - 60_000)

    def _refresh_access_token(self):
        """Renova access token via refresh token. Se falhar, tenta re-login via navegador."""
        logger.info("[CLAUDE BRAIN] Renovando access token...")
        try:
            resp = requests.post(
                ANTHROPIC_TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": ANTHROPIC_CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 200:
                body = resp.json()
                self._access_token = body["access_token"]
                self._refresh_token = body.get("refresh_token", self._refresh_token)
                self._expires = int(time.time() * 1000) + body.get("expires_in", 3600) * 1000
                self._save_tokens()
                logger.info("[CLAUDE BRAIN] Token renovado com sucesso")
                return
            else:
                logger.warning(f"[CLAUDE BRAIN] Refresh falhou ({resp.status_code}). Tentando re-login...")
        except requests.RequestException as e:
            logger.warning(f"[CLAUDE BRAIN] Erro no refresh: {e}. Tentando re-login...")

        # Fallback: re-login via navegador
        token_data = _oauth_browser_login()
        self._access_token = token_data["access_token"]
        self._refresh_token = token_data.get("refresh_token", "")
        self._expires = int(time.time() * 1000) + token_data.get("expires_in", 3600) * 1000
        self._save_tokens()

    def _get_headers(self) -> dict:
        if self._is_expired():
            self._refresh_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }

    def send_message(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        payload = {
            "model": model or self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        headers = self._get_headers()

        try:
            resp = requests.post(
                ANTHROPIC_API_URL, json=payload, headers=headers, timeout=120,
            )

            if resp.status_code == 401:
                logger.warning("[CLAUDE BRAIN] 401 — tentando refresh...")
                self._refresh_access_token()
                headers = self._get_headers()
                resp = requests.post(
                    ANTHROPIC_API_URL, json=payload, headers=headers, timeout=120,
                )

            if resp.status_code == 429:
                max_attempts = 5
                for attempt in range(1, max_attempts + 1):
                    # Backoff exponencial: 30s, 60s, 120s, 240s, 480s
                    backoff_default = 30 * (2 ** (attempt - 1))
                    retry_after = int(resp.headers.get("retry-after", backoff_default))
                    logger.warning(
                        f"[CLAUDE BRAIN] 429 rate limit — aguardando {retry_after}s "
                        f"({attempt}/{max_attempts})"
                    )
                    time.sleep(retry_after)
                    resp = requests.post(
                        ANTHROPIC_API_URL, json=payload, headers=self._get_headers(), timeout=120,
                    )
                    if resp.status_code != 429:
                        break

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            logger.error(f"[CLAUDE BRAIN] Erro na chamada: {e}")
            raise

    def ask(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        response = self.send_message(messages, system=system, model=model)
        content = response.get("content", [])
        return "".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        )

    def classificar_processo(self, dados_processo: dict) -> dict:
        system = """Voce e um assistente juridico especializado em direito do trabalho brasileiro.
Sua funcao e classificar processos e recomendar acoes para cadastro no sistema LegalOne.

Responda SEMPRE em JSON valido com a seguinte estrutura:
{
    "tipo_tarefa": "CADASTRO_INICIAL|RECURSO|DECISAO|ARQUIVAMENTO|ATUALIZACAO",
    "prioridade": "ALTA|MEDIA|BAIXA",
    "classificacao": "breve descricao da classificacao",
    "campos_obrigatorios_faltando": ["lista de campos que faltam"],
    "recomendacoes": ["lista de acoes recomendadas"],
    "confianca": 0.0 a 1.0
}"""

        prompt = f"""Analise os seguintes dados de processo extraidos de um formulario Microsoft Forms
e classifique para cadastro no LegalOne:

```json
{json.dumps(dados_processo, ensure_ascii=False, indent=2, default=str)}
```

Classifique o tipo de tarefa, prioridade, e liste campos obrigatorios que estao faltando."""

        resposta_texto = self.ask(prompt, system=system)

        try:
            texto = resposta_texto.strip()
            if "```json" in texto:
                texto = texto.split("```json")[1].split("```")[0].strip()
            elif "```" in texto:
                texto = texto.split("```")[1].split("```")[0].strip()
            return json.loads(texto)
        except (json.JSONDecodeError, IndexError):
            logger.warning("[CLAUDE BRAIN] Resposta nao e JSON valido, retornando raw")
            return {
                "tipo_tarefa": "GENERICO",
                "prioridade": "MEDIA",
                "classificacao": resposta_texto[:500],
                "campos_obrigatorios_faltando": [],
                "recomendacoes": [],
                "confianca": 0.5,
                "raw_response": resposta_texto,
            }

    def analisar_pagina(self, html_ou_texto: str, instrucao: str) -> str:
        system = """Voce e um assistente de automacao web especializado no sistema LegalOne.
Analise o conteudo da pagina e forneca orientacoes precisas sobre como proceder.
Seja direto e especifico — o resultado sera usado por codigo de automacao."""

        prompt = f"""Instrucao: {instrucao}

Conteudo da pagina:
{html_ou_texto[:8000]}"""

        return self.ask(prompt, system=system)

    def decidir_acao(self, contexto: str, opcoes: list[str]) -> int:
        opcoes_fmt = "\n".join(f"{i}. {op}" for i, op in enumerate(opcoes))
        system = "Responda APENAS com o numero da opcao escolhida (0, 1, 2, ...). Nada mais."
        prompt = f"""Contexto: {contexto}

Opcoes disponiveis:
{opcoes_fmt}

Qual opcao e a mais adequada? Responda apenas o numero."""

        resposta = self.ask(prompt, system=system).strip()

        try:
            idx = int(resposta.split()[0].strip("."))
            if 0 <= idx < len(opcoes):
                return idx
        except (ValueError, IndexError):
            pass

        logger.warning(f"[CLAUDE BRAIN] Resposta inesperada: {resposta}, usando opcao 0")
        return 0


# ---- Instancia global singleton ----
_instance: Optional[ClaudeBrain] = None


def get_brain(**kwargs) -> ClaudeBrain:
    """Retorna instancia singleton do ClaudeBrain."""
    global _instance
    if _instance is None:
        _instance = ClaudeBrain(**kwargs)
    return _instance


# ---- Teste rapido ----
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    brain = ClaudeBrain()
    print("Token carregado. Testando...")
    resposta = brain.ask("Diga 'OK' se voce esta funcionando.")
    print(f"Resposta: {resposta}")
