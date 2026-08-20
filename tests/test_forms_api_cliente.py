import json
import httpx
import pytest
import respx

from forms_api_cliente import FormsApiCliente, SessaoFormsExpirada

FORM_ID = "abc123"
TENANT_ID = "tenant-fake"
USER_ID = "user-fake"

def _state_file_valido(tmp_path, csrf_valor="csrf-token-fake"):
    state = {"cookies": [
        {"name": "FormsWebSessionId", "value": "fake", "domain": ".forms.cloud.microsoft", "path": "/"},
        {"name": "__RequestVerificationToken", "value": csrf_valor, "domain": ".forms.cloud.microsoft", "path": "/"},
    ], "origins": []}
    p = tmp_path / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return str(p)


def _url_definicao(form_id=FORM_ID, tenant=TENANT_ID, user=USER_ID):
    return (
        f"https://forms.cloud.microsoft/formapi/api/{tenant}/users/{user}"
        f"/light/forms('{form_id}')"
    )


@respx.mock
def test_definicao_formulario_retorna_json_e_ecoa_csrf_no_header(tmp_path):
    state_file = _state_file_valido(tmp_path, csrf_valor="meu-token-csrf")
    rota = respx.get(url__startswith=_url_definicao()).mock(
        return_value=httpx.Response(200, json={"id": FORM_ID, "questions": []})
    )
    cliente = FormsApiCliente(state_file=state_file, tenant_id=TENANT_ID, user_id=USER_ID)
    dados = cliente.definicao_formulario(FORM_ID)
    assert dados["id"] == FORM_ID
    # o header precisa ecoar EXATAMENTE o valor do cookie __RequestVerificationToken
    assert rota.calls.last.request.headers["__requestverificationtoken"] == "meu-token-csrf"


@respx.mock
def test_listar_respostas_usa_skip_e_top_e_decodifica_answers_json(tmp_path):
    state_file = _state_file_valido(tmp_path)
    payload_respostas = {
        "value": [
            {
                "id": 201,
                "responder": "fulano@exemplo.com",
                "answers": '[{"answer1":"1234567-89.2025.8.13.0024","questionId":"q1"}]',
            }
        ]
    }
    rota = respx.get(url__startswith=_url_definicao() + "/responses").mock(
        return_value=httpx.Response(200, json=payload_respostas)
    )
    cliente = FormsApiCliente(state_file=state_file, tenant_id=TENANT_ID, user_id=USER_ID)
    respostas = cliente.listar_respostas(FORM_ID, skip=200, top=50)
    assert respostas[0]["id"] == 201
    # answers ja' vem DECODIFICADO (lista de dict), nao mais a string JSON crua
    assert respostas[0]["answers"] == [{"answer1": "1234567-89.2025.8.13.0024", "questionId": "q1"}]
    qs = dict(rota.calls.last.request.url.params)
    assert qs["$skip"] == "200"
    assert qs["$top"] == "50"


@respx.mock
def test_sessao_expirada_levanta_excecao_clara_no_401(tmp_path):
    state_file = _state_file_valido(tmp_path)
    respx.get(url__startswith=_url_definicao()).mock(
        return_value=httpx.Response(
            401, json={"error": {"code": "701", "message": "Required user login."}}
        )
    )
    cliente = FormsApiCliente(state_file=state_file, tenant_id=TENANT_ID, user_id=USER_ID)
    with pytest.raises(SessaoFormsExpirada):
        cliente.definicao_formulario(FORM_ID)
