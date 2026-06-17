# LegalOne — Cadastro de Processos via API REST — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o preenchimento do cadastro de processos no LegalOne (hoje via navegador Playwright) por chamadas diretas à API REST oficial do LegalOne, no estilo headless (puro `requests`) do `jt_juris_teste_headless.py`, ganhando precisão (campos por ID em vez de autocomplete) e dispensando o browser.

**Architecture:** Três módulos novos, todos `requests`-only (sem Playwright), espelhando o padrão do `jt_juris_teste_headless.py` (Session com retry, credenciais no `.env`, JSON in/out, fail-safe com log):
1. `legalone_api_client.py` — transporte HTTP + OAuth `client_credentials` (token com auto-refresh) + helpers GET/POST.
2. `legalone_field_resolver.py` — resolve nome→ID dos campos por ID (Natureza, Posição, Tipo de ação, Área) via GET nas System Tables, com mapa estático do escritório + cache em memória + fallback à API.
3. `legalone_api_cadastro.py` — orquestra: recebe o `dados` dict já extraído (Forms/DataJud), monta o corpo POST do Lawsuit (com `participants` e `claims` aninhados), envia, trata a resposta. Integra-se ao pipeline existente atrás da flag `LEGALONE_USE_API=1`, mantendo o fluxo de navegador como fallback.

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`. Testes com `pytest` + `responses` (mock HTTP, zero rede). Sem browser, roda em Linux/VPS/cron.

**Premissas explícitas (confirmar antes do Task 8):**
- API alvo é a API REST oficial do LegalOne (planilha `API - Resource Mapping`), auth OAuth2 `client_credentials`. Base URL e URL de token ficam **configuráveis no `.env`** (defaults documentados, validados no Task 0). Se o seu acesso for via endpoints internos do tenant `novajus` com cookie de sessão, só o Task 1 (auth) muda — os demais módulos não.
- Participantes (cliente / parte contrária) exigem `contactId` de um contato já existente no LegalOne. Este plano resolve `contactId` via **GET por documento (CPF/CNPJ)**; criação de contato novo fica fora do escopo desta v1 (se não achar o contato, o participante é omitido e logado — não quebra o cadastro do processo).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `legalone_api_client.py` (criar) | Session com retry, OAuth token (cache + refresh), `get_json()` / `post_json()`. Único ponto que conhece base URL e auth. |
| `legalone_field_resolver.py` (criar) | `resolve_natureza()`, `resolve_posicao()`, `resolve_tipo_acao()`, `resolve_area()`, `resolve_contact_id()`. Mapa estático + GET system tables + cache. |
| `legalone_api_payload.py` (criar) | Funções puras (sem rede): `build_lawsuit_payload(dados, resolver)`, `build_claims(dados_pedidos)`, `build_participants(dados, resolver)`. |
| `legalone_api_cadastro.py` (criar) | `LegalOneApiCadastro.cadastrar_processo(dados)` — junta client+resolver+payload, faz POST, trata resposta/erros. API pública igual à do fluxo browser. |
| `config_automacao.py` (modificar) | Adicionar bloco `LEGALONE_API_CONFIG` lendo `.env`. |
| `.env.example` (modificar) | Documentar novas variáveis de API. |
| `requirements.txt` (modificar) | Adicionar `responses` (dev/test). |
| `automacao_legalone_completa.py` (modificar) | Atrás da flag `LEGALONE_USE_API`, rotear cadastro para a API; browser como fallback. |
| `tests/test_legalone_api_client.py` (criar) | Testes do client (token, retry, erros). |
| `tests/test_legalone_field_resolver.py` (criar) | Testes do resolver (mapa, GET, cache, fallback). |
| `tests/test_legalone_api_payload.py` (criar) | Testes das funções de payload (puras). |
| `tests/test_legalone_api_cadastro.py` (criar) | Testes do orquestrador (POST mockado). |

**Mapa de campos `dados` → Lawsuit POST** (referência para Tasks 4–5):

| `dados` (origem) | Campo API (`Rest.LawsuitScopes.Lawsuits`) | Tipo | Resolução |
|---|---|---|---|
| `cnj` | `identifierNumber` | String | direto |
| `tipo` (default `"Judicial"`) | `type` | enum | constante |
| `titulo` | `title` | String | direto |
| `status_processo` | `statusId` | Integer | resolver (system table Status) |
| `natureza` | `natureId` | Integer | resolver `LitigationNatures` |
| `responsavel`/`advogado_responsavel` | `responsibleAreaId` | Integer | resolver `Areas` |
| (mesma área) | `originAreaId` | Integer | mesmo `responsibleAreaId` |
| `tipo_acao`/`outros_dados['Tipo de ação']` | `actionTypeId` | Integer | resolver `LitigationActionAppealProceduralIssuetypes` |
| `valor_causa` | `monetaryAmount.value` (+ `MonetaryAmountType="Determined"`) | Double | parse `"1.234,56"`→`1234.56` |
| `fase` | `phaseId` | Integer | resolver (system table Fase) |
| cliente (`cliente`+`cpf_cliente`/`cnpj_cliente`, `posicao`) | `participants[]` | array | `build_participants` |
| parte contrária (`contrario`+docs) | `participants[]` | array | `build_participants` |
| `_parse_pedidos_detalhados(...)` → `[{pedido,tipo,grau,valor}]` | `claims[]` | array | `build_claims` |

**Mapa pedido → claim** (Task 5):

| pedido dict | claim API | Regra |
|---|---|---|
| `pedido` (nome) | `Claim.description` | direto |
| `tipo` (`Êxito`/`Perda`) | `probabilityType` | `Êxito`→`"Success"`, `Perda`→`"Loss"` |
| `tipo` | `contingency` | `Perda`→`"Passive"`, senão `"Active"` |
| `grau` (`Possível`/`Provável`/`Remota`) | `probability.description` | direto (string) |
| `valor` (`"1.234,56"`) | `claimAmount.value` | parse para Double |

---

### Task 0: Configuração de auth + smoke test de conectividade

**Files:**
- Modify: `.env.example`
- Modify: `config_automacao.py`
- Modify: `requirements.txt`
- Create: `scripts/smoke_legalone_api.py`

- [ ] **Step 1: Adicionar variáveis ao `.env.example`**

Acrescentar ao final de `.env.example`:

```bash
# ---------- LegalOne API REST ----------
# Ative o cadastro via API (em vez do navegador):
LEGALONE_USE_API=false
# OAuth client_credentials (obtenha client_id/secret junto à Thomson Reuters / suporte LegalOne)
LEGALONE_API_CLIENT_ID=
LEGALONE_API_CLIENT_SECRET=
# URL de obtenção do token OAuth (confirme com o suporte; default abaixo é o documentado para a API pública)
LEGALONE_API_TOKEN_URL=https://api.thomsonreuters.com/legalone/oauth?grant_type=client_credentials
# Base dos recursos REST (confirme com o suporte; ajuste para o seu produto/tenant)
LEGALONE_API_BASE=https://api.thomsonreuters.com/legalone/lawsuit/v1/api/rest/v1
# IDs padrão do escritório (preencha após validar via smoke test — evitam lookups em runtime)
LEGALONE_DEFAULT_STATUS_ID=
LEGALONE_DEFAULT_AREA_ID=
```

- [ ] **Step 2: Adicionar bloco de config em `config_automacao.py`**

Acrescentar ao final de `config_automacao.py`:

```python
# ==================== LEGALONE API REST ====================
LEGALONE_API_CONFIG = {
    'use_api': os.getenv('LEGALONE_USE_API', 'false').strip().lower() in ('1', 'true', 'yes', 'y'),
    'client_id': os.getenv('LEGALONE_API_CLIENT_ID', ''),
    'client_secret': os.getenv('LEGALONE_API_CLIENT_SECRET', ''),
    'token_url': os.getenv('LEGALONE_API_TOKEN_URL', 'https://api.thomsonreuters.com/legalone/oauth?grant_type=client_credentials'),
    'base_url': os.getenv('LEGALONE_API_BASE', 'https://api.thomsonreuters.com/legalone/lawsuit/v1/api/rest/v1'),
    'default_status_id': os.getenv('LEGALONE_DEFAULT_STATUS_ID', ''),
    'default_area_id': os.getenv('LEGALONE_DEFAULT_AREA_ID', ''),
    'timeout': 30,
}
```

- [ ] **Step 3: Adicionar dependência de teste**

Acrescentar em `requirements.txt`:

```
# Testes — mock de HTTP (sem rede real)
responses>=0.25
pytest>=8.0
```

- [ ] **Step 4: Criar script de smoke test**

Create `scripts/smoke_legalone_api.py`:

```python
"""Smoke test manual: valida auth + 1 GET em system table. NÃO faz POST.
Uso: python scripts/smoke_legalone_api.py
"""
import sys
from legalone_api_client import LegalOneApiClient


def main() -> int:
    client = LegalOneApiClient.from_env()
    if not client.configured:
        print("ERRO: credenciais ausentes. Preencha LEGALONE_API_CLIENT_ID/SECRET no .env")
        return 2
    print("Obtendo token...")
    token = client.get_token()
    print("Token OK:", (token[:12] + "...") if token else "FALHOU")
    print("GET LitigationNatures...")
    data = client.get_json("SystemTables.Litigation/LitigationNatures")
    items = data.get("value", data) if isinstance(data, dict) else data
    print(f"Naturezas retornadas: {len(items) if items else 0}")
    if items:
        print("Exemplo:", items[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Instalar dependências**

Run: `pip install -r requirements.txt`
Expected: instala `responses` e `pytest` sem erro.

- [ ] **Step 6: Commit**

```bash
git add .env.example config_automacao.py requirements.txt scripts/smoke_legalone_api.py
git commit -m "chore: config e smoke test para cadastro LegalOne via API"
```

> **Nota:** O smoke test só roda de verdade após o Task 1 (o client ainda não existe). Ele fica pronto aqui e será executado no Task 8.

---

### Task 1: API client — Session, OAuth token, helpers GET/POST

**Files:**
- Create: `legalone_api_client.py`
- Test: `tests/test_legalone_api_client.py`

- [ ] **Step 1: Escrever o teste que falha**

Create `tests/test_legalone_api_client.py`:

```python
import time
import responses
from legalone_api_client import LegalOneApiClient

TOKEN_URL = "https://api.example.com/oauth"
BASE = "https://api.example.com/rest/v1"


def make_client():
    return LegalOneApiClient(
        client_id="id", client_secret="secret",
        token_url=TOKEN_URL, base_url=BASE, timeout=5,
    )


@responses.activate
def test_get_token_caches_until_expiry():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "abc123", "expires_in": 3600}, status=200)
    c = make_client()
    assert c.get_token() == "abc123"
    # segunda chamada não bate na rede de novo (cache)
    assert c.get_token() == "abc123"
    assert len(responses.calls) == 1


@responses.activate
def test_get_json_sends_bearer_and_parses():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "tok", "expires_in": 3600}, status=200)
    responses.add(responses.GET, f"{BASE}/Foo/Bar",
                  json={"value": [{"id": 1, "name": "X"}]}, status=200)
    c = make_client()
    data = c.get_json("Foo/Bar")
    assert data["value"][0]["id"] == 1
    auth = responses.calls[-1].request.headers["Authorization"]
    assert auth == "Bearer tok"


@responses.activate
def test_post_json_returns_body_and_status():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "tok", "expires_in": 3600}, status=200)
    responses.add(responses.POST, f"{BASE}/Lawsuits",
                  json={"id": 999}, status=201)
    c = make_client()
    status, body = c.post_json("Lawsuits", {"folder": "x"})
    assert status == 201
    assert body["id"] == 999


def test_configured_false_when_no_creds():
    c = LegalOneApiClient(client_id="", client_secret="",
                          token_url=TOKEN_URL, base_url=BASE)
    assert c.configured is False
```

- [ ] **Step 2: Rodar o teste — deve falhar**

Run: `pytest tests/test_legalone_api_client.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'legalone_api_client'`

- [ ] **Step 3: Implementar `legalone_api_client.py`**

Create `legalone_api_client.py`:

```python
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
```

- [ ] **Step 4: Rodar o teste — deve passar**

Run: `pytest tests/test_legalone_api_client.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add legalone_api_client.py tests/test_legalone_api_client.py
git commit -m "feat: cliente HTTP LegalOne API (OAuth token + GET/POST)"
```

---

### Task 2: Field resolver — nome→ID via system tables (mapa + cache + GET)

**Files:**
- Create: `legalone_field_resolver.py`
- Test: `tests/test_legalone_field_resolver.py`

- [ ] **Step 1: Escrever o teste que falha**

Create `tests/test_legalone_field_resolver.py`:

```python
from legalone_field_resolver import FieldResolver


class FakeClient:
    """Client fake: registra paths chamados e devolve listas fixas."""
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def get_json(self, path, params=None):
        self.calls.append(path)
        return {"value": self.tables.get(path, [])}


def test_resolve_natureza_via_get_and_cache():
    client = FakeClient({
        "SystemTables.Litigation/LitigationNatures": [
            {"id": 10, "name": "Trabalhista"}, {"id": 11, "name": "Cível"},
        ]
    })
    r = FieldResolver(client)
    assert r.resolve_natureza("Trabalhista") == 10
    # segunda chamada usa cache: nenhum GET novo
    assert r.resolve_natureza("trabalhista") == 10
    assert len(client.calls) == 1


def test_resolve_natureza_accent_and_case_insensitive():
    client = FakeClient({
        "SystemTables.Litigation/LitigationNatures": [{"id": 11, "name": "Cível"}]
    })
    r = FieldResolver(client)
    assert r.resolve_natureza("civel") == 11


def test_resolve_returns_none_when_not_found():
    client = FakeClient({"SystemTables.Litigation/LitigationNatures": []})
    r = FieldResolver(client)
    assert r.resolve_natureza("Inexistente") is None


def test_static_map_short_circuits_get():
    client = FakeClient({})
    r = FieldResolver(client, static_map={"natureza": {"trabalhista": 99}})
    assert r.resolve_natureza("Trabalhista") == 99
    assert client.calls == []  # nenhum GET


def test_resolve_posicao_and_tipo_acao_use_correct_paths():
    client = FakeClient({
        "SystemTables.Litigation/LitigationParticipantPositions": [{"id": 5, "name": "Réu"}],
        "SystemTables.Litigation/LitigationActionAppealProceduralIssuetypes": [{"id": 7, "name": "Reclamação Trabalhista"}],
    })
    r = FieldResolver(client)
    assert r.resolve_posicao("Réu") == 5
    assert r.resolve_tipo_acao("Reclamação Trabalhista") == 7
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `pytest tests/test_legalone_field_resolver.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'legalone_field_resolver'`

- [ ] **Step 3: Implementar `legalone_field_resolver.py`**

Create `legalone_field_resolver.py`:

```python
"""Resolve nome→ID dos campos por ID do LegalOne.

Estratégia: mapa estático do escritório (rápido) → GET na system table
(com cache em memória) → None se não encontrar. Match normalizado
(sem acento, case-insensitive).
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Optional

logger = logging.getLogger("LEGALONE_API")

# path da system table por campo lógico
_PATHS = {
    "natureza": "SystemTables.Litigation/LitigationNatures",
    "posicao": "SystemTables.Litigation/LitigationParticipantPositions",
    "tipo_acao": "SystemTables.Litigation/LitigationActionAppealProceduralIssuetypes",
    "area": "SystemTables.General/Areas",
}


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


class FieldResolver:
    def __init__(self, client, static_map: Optional[dict] = None):
        self.client = client
        self.static_map = static_map or {}
        # cache[campo] = {nome_normalizado: id}
        self._cache: dict[str, dict[str, int]] = {}

    def _lookup(self, campo: str, nome: str) -> Optional[int]:
        if not nome:
            return None
        key = _norm(nome)
        # 1. mapa estático
        smap = {_norm(k): v for k, v in self.static_map.get(campo, {}).items()}
        if key in smap:
            return smap[key]
        # 2. cache (carrega da API uma vez por campo)
        if campo not in self._cache:
            self._cache[campo] = self._carregar_tabela(campo)
        return self._cache[campo].get(key)

    def _carregar_tabela(self, campo: str) -> dict[str, int]:
        path = _PATHS.get(campo)
        if not path:
            return {}
        data = self.client.get_json(path)
        itens = data.get("value", data) if isinstance(data, dict) else (data or [])
        tabela: dict[str, int] = {}
        for it in itens or []:
            nome = it.get("name") or it.get("Nome")
            _id = it.get("id") or it.get("Id")
            if nome and _id is not None:
                tabela[_norm(nome)] = int(_id)
        return tabela

    def resolve_natureza(self, nome: str) -> Optional[int]:
        return self._lookup("natureza", nome)

    def resolve_posicao(self, nome: str) -> Optional[int]:
        return self._lookup("posicao", nome)

    def resolve_tipo_acao(self, nome: str) -> Optional[int]:
        return self._lookup("tipo_acao", nome)

    def resolve_area(self, nome: str) -> Optional[int]:
        return self._lookup("area", nome)

    def resolve_contact_id(self, documento: str) -> Optional[int]:
        """Busca contato existente por CPF/CNPJ. Retorna id ou None."""
        doc = "".join(ch for ch in (documento or "") if ch.isdigit())
        if not doc:
            return None
        data = self.client.get_json(
            "Contacts", params={"$filter": f"registrationNumber eq '{doc}'"}
        )
        itens = data.get("value", data) if isinstance(data, dict) else (data or [])
        if itens:
            first = itens[0]
            cid = first.get("id") or first.get("Id")
            return int(cid) if cid is not None else None
        return None
```

- [ ] **Step 4: Rodar — deve passar**

Run: `pytest tests/test_legalone_field_resolver.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add legalone_field_resolver.py tests/test_legalone_field_resolver.py
git commit -m "feat: resolver nome->ID das system tables do LegalOne"
```

---

### Task 3: Payload builder — funções puras `dados` → corpo POST

**Files:**
- Create: `legalone_api_payload.py`
- Test: `tests/test_legalone_api_payload.py`

- [ ] **Step 1: Escrever o teste que falha**

Create `tests/test_legalone_api_payload.py`:

```python
from legalone_api_payload import (
    parse_valor_brl, build_claims, build_participants, build_lawsuit_payload,
)


class FakeResolver:
    def resolve_natureza(self, n): return 10 if n else None
    def resolve_posicao(self, n): return {"Reclamante": 1, "Reclamado": 2}.get(n)
    def resolve_tipo_acao(self, n): return 7 if n else None
    def resolve_area(self, n): return 3 if n else None
    def resolve_contact_id(self, doc): return 555 if doc else None


def test_parse_valor_brl():
    assert parse_valor_brl("1.234,56") == 1234.56
    assert parse_valor_brl("R$ 50.000,00") == 50000.0
    assert parse_valor_brl("") is None
    assert parse_valor_brl(None) is None


def test_build_claims_maps_probability_and_amount():
    pedidos = [
        {"pedido": "Horas Extras", "tipo": "Êxito", "grau": "Provável", "valor": "10.000,00"},
        {"pedido": "Danos Morais", "tipo": "Perda", "grau": "Remota", "valor": "0,00"},
    ]
    claims = build_claims(pedidos)
    assert claims[0]["Claim"]["description"] == "Horas Extras"
    assert claims[0]["probabilityType"] == "Success"
    assert claims[0]["contingency"] == "Active"
    assert claims[0]["probability"]["description"] == "Provável"
    assert claims[0]["claimAmount"]["value"] == 10000.0
    assert claims[1]["probabilityType"] == "Loss"
    assert claims[1]["contingency"] == "Passive"


def test_build_participants_resolves_contact_and_position():
    dados = {
        "cliente": "ACME LTDA", "cnpj_cliente": "12.345.678/0001-99",
        "contrario": "Fulano", "cpf_contrario": "111.222.333-44",
    }
    parts = build_participants(dados, FakeResolver())
    cliente = [p for p in parts if p["isMainParticipant"]][0]
    assert cliente["contactId"] == 555
    assert cliente["type"] == "Customer"
    assert any(p["type"] == "OtherParty" for p in parts)


def test_build_participants_omits_when_contact_not_found():
    class NoContact(FakeResolver):
        def resolve_contact_id(self, doc): return None
    dados = {"cliente": "X", "cpf_cliente": "1", "contrario": "Y", "cpf_contrario": "2"}
    assert build_participants(dados, NoContact()) == []


def test_build_lawsuit_payload_full():
    dados = {
        "cnj": "0010307-23.2026.5.03.0089",
        "titulo": "ACME x Fulano",
        "natureza": "Trabalhista",
        "responsavel": "Trabalhista",
        "tipo_acao": "Reclamação Trabalhista",
        "valor_causa": "50.000,00",
        "cliente": "ACME LTDA", "cnpj_cliente": "12.345.678/0001-99", "posicao": "Reclamado",
        "contrario": "Fulano", "cpf_contrario": "111.222.333-44",
    }
    pedidos = [{"pedido": "Horas Extras", "tipo": "Êxito", "grau": "Provável", "valor": "10.000,00"}]
    payload = build_lawsuit_payload(dados, FakeResolver(), pedidos=pedidos,
                                    default_status_id=1)
    assert payload["identifierNumber"] == "0010307-23.2026.5.03.0089"
    assert payload["type"] == "Judicial"
    assert payload["natureId"] == 10
    assert payload["responsibleAreaId"] == 3
    assert payload["actionTypeId"] == 7
    assert payload["statusId"] == 1
    assert payload["monetaryAmount"]["value"] == 50000.0
    assert payload["MonetaryAmountType"] == "Determined"
    assert len(payload["participants"]) >= 1
    assert len(payload["claims"]) == 1
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `pytest tests/test_legalone_api_payload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'legalone_api_payload'`

- [ ] **Step 3: Implementar `legalone_api_payload.py`**

Create `legalone_api_payload.py`:

```python
"""Funções puras (sem rede) que montam o corpo POST do Lawsuit a partir do
dict `dados` extraído (Forms/DataJud). Recebe um resolver para campos por ID.
"""
from __future__ import annotations

import re
from typing import Optional


def parse_valor_brl(v) -> Optional[float]:
    """'1.234,56' / 'R$ 50.000,00' -> 1234.56 / 50000.0. None se vazio/inválido."""
    if not v:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", str(v))
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def _doc_cliente(dados: dict) -> str:
    return (dados.get("cpf_cliente") or dados.get("cnpj_cliente")
            or dados.get("documento_cliente") or "")


def _doc_contrario(dados: dict) -> str:
    return (dados.get("cpf_contrario") or dados.get("cnpj_contrario")
            or dados.get("documento_contrario") or "")


def build_claims(pedidos: list[dict]) -> list[dict]:
    claims = []
    for p in pedidos or []:
        tipo = (p.get("tipo") or "Êxito")
        prob_type = "Loss" if tipo == "Perda" else "Success"
        contingency = "Passive" if tipo == "Perda" else "Active"
        valor = parse_valor_brl(p.get("valor"))
        claim = {
            "Claim": {"description": p.get("pedido", "")},
            "probabilityType": prob_type,
            "contingency": contingency,
            "probability": {"description": p.get("grau", "Possível")},
        }
        if valor is not None:
            claim["claimAmount"] = {"value": valor}
        claims.append(claim)
    return claims


def build_participants(dados: dict, resolver) -> list[dict]:
    parts: list[dict] = []

    doc_cli = _doc_cliente(dados)
    if dados.get("cliente") and doc_cli:
        cid = resolver.resolve_contact_id(doc_cli)
        if cid:
            pos = resolver.resolve_posicao(dados.get("posicao") or "")
            p = {"contactId": cid, "isMainParticipant": True, "type": "Customer"}
            if pos:
                p["positionId"] = pos
            parts.append(p)

    doc_con = _doc_contrario(dados)
    if dados.get("contrario") and doc_con:
        cid = resolver.resolve_contact_id(doc_con)
        if cid:
            parts.append({"contactId": cid, "isMainParticipant": False,
                          "type": "OtherParty"})

    return parts


def build_lawsuit_payload(dados: dict, resolver, pedidos: Optional[list[dict]] = None,
                          default_status_id: Optional[int] = None,
                          default_area_id: Optional[int] = None) -> dict:
    payload: dict = {
        "identifierNumber": dados.get("cnj", ""),
        "type": dados.get("tipo") or "Judicial",
    }
    if dados.get("titulo"):
        payload["title"] = dados["titulo"]

    natureza = resolver.resolve_natureza(dados.get("natureza") or "")
    if natureza:
        payload["natureId"] = natureza

    area_nome = dados.get("responsavel") or dados.get("advogado_responsavel") or ""
    area = resolver.resolve_area(area_nome) or default_area_id
    if area:
        payload["responsibleAreaId"] = area
        payload["originAreaId"] = area

    tipo_acao = resolver.resolve_tipo_acao(dados.get("tipo_acao") or "")
    if tipo_acao:
        payload["actionTypeId"] = tipo_acao

    status = default_status_id
    if status:
        payload["statusId"] = status

    valor = parse_valor_brl(dados.get("valor_causa"))
    if valor is not None:
        payload["MonetaryAmountType"] = "Determined"
        payload["monetaryAmount"] = {"value": valor}

    participants = build_participants(dados, resolver)
    if participants:
        payload["participants"] = participants

    claims = build_claims(pedidos or [])
    if claims:
        payload["claims"] = claims

    return payload
```

- [ ] **Step 4: Rodar — deve passar**

Run: `pytest tests/test_legalone_api_payload.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add legalone_api_payload.py tests/test_legalone_api_payload.py
git commit -m "feat: builder do payload POST do Lawsuit (puro, testado)"
```

---

### Task 4: Orquestrador — `LegalOneApiCadastro.cadastrar_processo`

**Files:**
- Create: `legalone_api_cadastro.py`
- Test: `tests/test_legalone_api_cadastro.py`

- [ ] **Step 1: Escrever o teste que falha**

Create `tests/test_legalone_api_cadastro.py`:

```python
import responses
from legalone_api_cadastro import LegalOneApiCadastro

TOKEN_URL = "https://api.example.com/oauth"
BASE = "https://api.example.com/rest/v1"


def _add_token():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "tok", "expires_in": 3600}, status=200)


def _add_system_tables():
    responses.add(responses.GET, f"{BASE}/SystemTables.Litigation/LitigationNatures",
                  json={"value": [{"id": 10, "name": "Trabalhista"}]}, status=200)
    responses.add(responses.GET, f"{BASE}/SystemTables.General/Areas",
                  json={"value": [{"id": 3, "name": "Trabalhista"}]}, status=200)
    responses.add(responses.GET,
                  f"{BASE}/SystemTables.Litigation/LitigationParticipantPositions",
                  json={"value": [{"id": 2, "name": "Reclamado"}]}, status=200)
    responses.add(responses.GET,
                  f"{BASE}/SystemTables.Litigation/LitigationActionAppealProceduralIssuetypes",
                  json={"value": [{"id": 7, "name": "Reclamação Trabalhista"}]}, status=200)
    responses.add(responses.GET, f"{BASE}/Contacts",
                  json={"value": []}, status=200)


def _make():
    from legalone_api_client import LegalOneApiClient
    client = LegalOneApiClient("id", "secret", TOKEN_URL, BASE, timeout=5)
    return LegalOneApiCadastro(client=client, default_status_id=1)


@responses.activate
def test_cadastrar_sucesso_retorna_id():
    _add_token(); _add_system_tables()
    responses.add(responses.POST, f"{BASE}/Lawsuits",
                  json={"id": 4242}, status=201)
    cad = _make()
    dados = {"cnj": "0010307-23.2026.5.03.0089", "natureza": "Trabalhista",
             "responsavel": "Trabalhista"}
    res = cad.cadastrar_processo(dados)
    assert res["sucesso"] is True
    assert res["id"] == 4242


@responses.activate
def test_cadastrar_falha_http_retorna_erro():
    _add_token(); _add_system_tables()
    responses.add(responses.POST, f"{BASE}/Lawsuits",
                  json={"message": "validation error"}, status=400)
    cad = _make()
    res = cad.cadastrar_processo({"cnj": "123", "natureza": "Trabalhista"})
    assert res["sucesso"] is False
    assert "400" in str(res["erro"]) or "validation" in str(res["erro"]).lower()


def test_cadastrar_sem_cnj_falha_cedo():
    cad = _make()
    res = cad.cadastrar_processo({})
    assert res["sucesso"] is False
    assert "cnj" in str(res["erro"]).lower()
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `pytest tests/test_legalone_api_cadastro.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'legalone_api_cadastro'`

- [ ] **Step 3: Implementar `legalone_api_cadastro.py`**

Create `legalone_api_cadastro.py`:

```python
"""Orquestrador do cadastro de processo via API REST do LegalOne.

API pública espelha o fluxo de navegador: cadastrar_processo(dados) -> dict.
Junta client + resolver + payload, faz POST e traduz a resposta.
"""
from __future__ import annotations

import logging
from typing import Optional

from legalone_api_client import LegalOneApiClient
from legalone_field_resolver import FieldResolver
from legalone_api_payload import build_lawsuit_payload

logger = logging.getLogger("LEGALONE_API")

# Mapa estático do escritório — preencha com IDs já conhecidos para evitar GET.
# Ex.: {"natureza": {"trabalhista": 10}, "area": {"trabalhista": 3}}
STATIC_MAP: dict = {}

LAWSUITS_PATH = "Lawsuits"


class LegalOneApiCadastro:
    def __init__(self, client: Optional[LegalOneApiClient] = None,
                 default_status_id: Optional[int] = None,
                 default_area_id: Optional[int] = None,
                 static_map: Optional[dict] = None):
        self.client = client or LegalOneApiClient.from_env()
        self.resolver = FieldResolver(self.client, static_map or STATIC_MAP)
        self.default_status_id = default_status_id
        self.default_area_id = default_area_id

    def _extrair_pedidos(self, dados: dict) -> list[dict]:
        """Reusa o parser de pedidos já existente no fluxo browser, se houver
        texto detalhado; senão retorna lista vazia."""
        pedidos = dados.get("pedidos")
        if isinstance(pedidos, list):
            return pedidos
        return []

    def cadastrar_processo(self, dados: dict) -> dict:
        cnj = (dados or {}).get("cnj")
        if not cnj:
            return {"sucesso": False, "erro": "CNJ ausente nos dados", "id": None}

        if not self.client.configured:
            return {"sucesso": False,
                    "erro": "API não configurada (client_id/secret ausentes)",
                    "id": None}

        logger.info("[API] Cadastrando processo CNJ=%s", cnj)
        pedidos = self._extrair_pedidos(dados)
        payload = build_lawsuit_payload(
            dados, self.resolver, pedidos=pedidos,
            default_status_id=self.default_status_id,
            default_area_id=self.default_area_id,
        )

        status, body = self.client.post_json(LAWSUITS_PATH, payload)
        if 200 <= status < 300:
            new_id = body.get("id") if isinstance(body, dict) else None
            logger.info("[API] Processo cadastrado id=%s", new_id)
            return {"sucesso": True, "erro": None, "id": new_id, "payload": payload}

        erro = f"HTTP {status}: {str(body)[:300]}"
        logger.error("[API] Falha no cadastro CNJ=%s — %s", cnj, erro)
        return {"sucesso": False, "erro": erro, "id": None, "payload": payload}
```

- [ ] **Step 4: Rodar — deve passar**

Run: `pytest tests/test_legalone_api_cadastro.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Rodar a suíte toda**

Run: `pytest tests/ -v`
Expected: PASS (todos os testes das Tasks 1–4).

- [ ] **Step 6: Commit**

```bash
git add legalone_api_cadastro.py tests/test_legalone_api_cadastro.py
git commit -m "feat: orquestrador de cadastro de processo via API LegalOne"
```

---

### Task 5: Integração no pipeline atrás da flag `LEGALONE_USE_API`

**Files:**
- Modify: `automacao_legalone_completa.py` (no ponto que hoje chama o cadastro via navegador)
- Test: `tests/test_pipeline_api_routing.py` (criar)

- [ ] **Step 1: Localizar o ponto de cadastro no pipeline**

Run: `grep -nE "cadastrar_processo|LegalOneCadastro" automacao_legalone_completa.py`
Expected: mostra onde `LegalOneCadastro(...).cadastrar_processo(dados)` (ou equivalente) é chamado. Anote o número da linha para o Step 3.

- [ ] **Step 2: Escrever o teste que falha**

Create `tests/test_pipeline_api_routing.py`:

```python
import importlib
from automacao_legalone_completa import escolher_cadastro


def test_escolhe_api_quando_flag_ligada(monkeypatch):
    monkeypatch.setattr("config_automacao.LEGALONE_API_CONFIG",
                        {"use_api": True, "client_id": "x", "client_secret": "y",
                         "token_url": "u", "base_url": "b",
                         "default_status_id": "1", "default_area_id": "3", "timeout": 30},
                        raising=False)
    backend = escolher_cadastro()
    assert backend == "api"


def test_escolhe_browser_quando_flag_desligada(monkeypatch):
    monkeypatch.setattr("config_automacao.LEGALONE_API_CONFIG",
                        {"use_api": False, "client_id": "", "client_secret": "",
                         "token_url": "u", "base_url": "b",
                         "default_status_id": "", "default_area_id": "", "timeout": 30},
                        raising=False)
    backend = escolher_cadastro()
    assert backend == "browser"
```

- [ ] **Step 3: Rodar — deve falhar**

Run: `pytest tests/test_pipeline_api_routing.py -v`
Expected: FAIL com `ImportError: cannot import name 'escolher_cadastro'`

- [ ] **Step 4: Implementar o roteamento**

Em `automacao_legalone_completa.py`, adicionar a função de seleção (perto dos imports/topo do módulo):

```python
def escolher_cadastro() -> str:
    """Decide o backend de cadastro: 'api' se a flag estiver ligada, senão 'browser'."""
    from config_automacao import LEGALONE_API_CONFIG
    return "api" if LEGALONE_API_CONFIG.get("use_api") else "browser"
```

No ponto localizado no Step 1, trocar a chamada direta pelo roteamento. Substituir o bloco que hoje faz o cadastro via navegador por:

```python
if escolher_cadastro() == "api":
    from legalone_api_cadastro import LegalOneApiCadastro
    from config_automacao import LEGALONE_API_CONFIG as _api_cfg
    _status = int(_api_cfg["default_status_id"]) if _api_cfg.get("default_status_id") else None
    _area = int(_api_cfg["default_area_id"]) if _api_cfg.get("default_area_id") else None
    cad_api = LegalOneApiCadastro(default_status_id=_status, default_area_id=_area)
    resultado = cad_api.cadastrar_processo(dados)
    if not resultado["sucesso"]:
        logger.error("[API] Cadastro falhou: %s — fazendo fallback para navegador.",
                     resultado["erro"])
        # fallback: mantém o fluxo de navegador existente abaixo
    else:
        logger.info("[API] Cadastro OK id=%s", resultado["id"])
        # segue o fluxo pós-cadastro normal
```

> **Nota para o executor:** preserve o código de cadastro via navegador existente como o caminho de fallback (quando `escolher_cadastro() == "browser"` ou quando a API falha). Não apague o fluxo Playwright.

- [ ] **Step 5: Rodar — deve passar**

Run: `pytest tests/test_pipeline_api_routing.py -v`
Expected: PASS (2 testes).

- [ ] **Step 6: Rodar a suíte toda**

Run: `pytest tests/ -v`
Expected: PASS (todos).

- [ ] **Step 7: Commit**

```bash
git add automacao_legalone_completa.py tests/test_pipeline_api_routing.py
git commit -m "feat: rotear cadastro para API atras da flag LEGALONE_USE_API (browser fallback)"
```

---

### Task 6: Smoke test real + ajuste de paths/IDs

**Files:**
- Modify (se necessário): `legalone_api_client.py`, `legalone_field_resolver.py`, `legalone_api_cadastro.py` (apenas paths/URLs conforme realidade da API)
- Modify: `.env` (credenciais reais — NÃO commitar)

- [ ] **Step 1: Preencher credenciais reais no `.env`**

Editar `.env` (não versionado) com `LEGALONE_API_CLIENT_ID`, `LEGALONE_API_CLIENT_SECRET` reais e confirmar `LEGALONE_API_TOKEN_URL` / `LEGALONE_API_BASE` com o suporte LegalOne.

- [ ] **Step 2: Rodar o smoke test de conectividade**

Run: `python scripts/smoke_legalone_api.py`
Expected: imprime "Token OK: ..." e "Naturezas retornadas: N" com N > 0.
Se 401/403: revisar credenciais. Se 404 no GET: ajustar os paths em `_PATHS` (`legalone_field_resolver.py`) e em `LAWSUITS_PATH`/base URL conforme o retorno real da API. **Esses ajustes não exigem mudar testes** (os testes usam paths mockados próprios).

- [ ] **Step 3: Preencher IDs padrão do escritório**

Com a saída do smoke test (lista de naturezas/áreas/status), preencher `LEGALONE_DEFAULT_STATUS_ID` e `LEGALONE_DEFAULT_AREA_ID` no `.env`, e popular `STATIC_MAP` em `legalone_api_cadastro.py` com os valores recorrentes (ex.: `{"natureza": {"trabalhista": <id>}, "area": {"trabalhista": <id>}}`).

- [ ] **Step 4: Teste de cadastro real com 1 CNJ (ambiente de homologação se disponível)**

Run (Python REPL ou script ad-hoc):
```python
from legalone_api_cadastro import LegalOneApiCadastro
cad = LegalOneApiCadastro(default_status_id=<ID>, default_area_id=<ID>)
print(cad.cadastrar_processo({
    "cnj": "0010307-23.2026.5.03.0089",
    "titulo": "TESTE API",
    "natureza": "Trabalhista",
    "responsavel": "Trabalhista",
}))
```
Expected: `{'sucesso': True, 'id': <int>, ...}`. Verificar no LegalOne que a pasta do processo foi criada com os campos corretos.

- [ ] **Step 5: Rodar a suíte toda (garantir que ajustes não quebraram nada)**

Run: `pytest tests/ -v`
Expected: PASS (todos).

- [ ] **Step 6: Commit (somente código; nunca o `.env`)**

```bash
git add legalone_api_client.py legalone_field_resolver.py legalone_api_cadastro.py
git commit -m "fix: ajustar paths/IDs da API LegalOne conforme smoke test real"
```

---

## Self-Review

**1. Cobertura do pedido:** "preencher os campos através da API, igual ao `jt_juris_teste_headless.py`" →
- Estilo headless (`requests` + Session retry + `.env` + JSON + fail-safe) → Task 1. ✅
- Preencher campos via API (não navegador) → Tasks 3–4 (payload + POST). ✅
- Precisão (campos por ID) → Task 2 (resolver nome→ID). ✅
- Sem quebrar o que funciona → Task 5 (flag + fallback browser). ✅
- Validação real → Task 6. ✅

**2. Placeholders:** Todos os steps de código têm código completo. URLs/paths que dependem da API real estão como defaults em `.env`/constantes e têm Task 6 dedicada para confirmação — não são placeholders no código.

**3. Consistência de tipos:** `cadastrar_processo(dados) -> dict{sucesso,erro,id}` usado igual em Tasks 4 e 5. `FieldResolver.resolve_*` e `resolve_contact_id` usados consistentemente em payload (Task 3) e orquestrador (Task 4). `LegalOneApiClient.get_json/post_json` assinaturas batem entre Tasks 1, 2 e 4. `build_lawsuit_payload(dados, resolver, pedidos, default_status_id, default_area_id)` idêntico em Task 3 e Task 4.

**Riscos conhecidos (não bloqueiam o plano):**
- Base URL / token URL / nomes dos paths das system tables podem diferir do default documentado → isolados no `.env` + `_PATHS`, resolvidos no Task 6 sem tocar em testes.
- Criação de contato novo (quando não existe) está fora do escopo v1 — participante é omitido e logado. Pode virar um Task 7 futuro (`Rest.Contacts` POST) se necessário.
