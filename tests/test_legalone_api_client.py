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
