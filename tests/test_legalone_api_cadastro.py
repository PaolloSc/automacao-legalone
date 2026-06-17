import responses

from legalone_api_cadastro import LegalOneApiCadastro

TOKEN_URL = "https://api.example.com/oauth"
BASE = "https://api.example.com/rest/v1"


def _add_token():
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "expires_in": 3600},
        status=200,
    )


def _add_system_tables():
    responses.add(
        responses.GET,
        f"{BASE}/SystemTables.Litigation/LitigationNatures",
        json={"value": [{"id": 10, "name": "Trabalhista"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/SystemTables.General/Areas",
        json={"value": [{"id": 3, "name": "Trabalhista"}]},
        status=200,
    )


def _make():
    from legalone_api_client import LegalOneApiClient

    client = LegalOneApiClient("id", "secret", TOKEN_URL, BASE, timeout=5)
    return LegalOneApiCadastro(client=client, default_status_id=1)


@responses.activate
def test_cadastrar_sucesso_retorna_id():
    _add_token()
    _add_system_tables()
    responses.add(responses.POST, f"{BASE}/Lawsuits", json={"id": 4242}, status=201)
    cad = _make()
    dados = {
        "cnj": "0010307-23.2026.5.03.0089",
        "natureza": "Trabalhista",
        "responsavel": "Trabalhista",
    }
    res = cad.cadastrar_processo(dados)
    assert res["sucesso"] is True
    assert res["id"] == 4242


@responses.activate
def test_cadastrar_falha_http_retorna_erro():
    _add_token()
    _add_system_tables()
    responses.add(
        responses.POST,
        f"{BASE}/Lawsuits",
        json={"message": "validation error"},
        status=400,
    )
    cad = _make()
    res = cad.cadastrar_processo({"cnj": "123", "natureza": "Trabalhista"})
    assert res["sucesso"] is False
    assert "400" in str(res["erro"]) or "validation" in str(res["erro"]).lower()


def test_cadastrar_sem_cnj_falha_cedo():
    cad = _make()
    res = cad.cadastrar_processo({})
    assert res["sucesso"] is False
    assert "cnj" in str(res["erro"]).lower()
