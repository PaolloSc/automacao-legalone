from legalone_api_payload import (
    build_claims,
    build_lawsuit_payload,
    build_participants,
    parse_valor_brl,
)


class FakeResolver:
    def resolve_natureza(self, name):
        return {"Trabalhista": 10}.get(name)

    def resolve_area(self, name):
        return {"Trabalhista": 3}.get(name)

    def resolve_tipo_acao(self, name):
        return {"Reclamacao Trabalhista": 7}.get(name)

    def resolve_posicao(self, name):
        return {"Reclamado": 2}.get(name)

    def resolve_contact_id(self, doc):
        return {"12345678000199": 100, "11122233344": 200}.get(
            "".join(ch for ch in str(doc) if ch.isdigit())
        )


def test_parse_valor_brl():
    assert parse_valor_brl("R$ 1.234,56") == 1234.56
    assert parse_valor_brl("50.000,00") == 50000.0
    assert parse_valor_brl("") is None


def test_build_claims_maps_probability_and_amount():
    claims = build_claims([
        {"pedido": "Horas Extras", "tipo": "Exito", "grau": "Provavel", "valor": "10.000,00"},
        {"pedido": "Danos", "tipo": "Perda", "grau": "Remota", "valor": "1.000,00"},
    ])
    assert claims[0]["probabilityType"] == "Success"
    assert claims[0]["contingency"] == "Active"
    assert claims[0]["claimAmount"]["value"] == 10000.0
    assert claims[1]["probabilityType"] == "Loss"
    assert claims[1]["contingency"] == "Passive"


def test_build_participants_omits_missing_contact():
    dados = {
        "cliente": "ACME LTDA",
        "cnpj_cliente": "12.345.678/0001-99",
        "posicao": "Reclamado",
        "contrario": "Fulano",
        "cpf_contrario": "000.000.000-00",
    }
    parts = build_participants(dados, FakeResolver())
    assert len(parts) == 1
    assert parts[0]["contactId"] == 100
    assert parts[0]["positionId"] == 2


def test_build_lawsuit_payload_full():
    dados = {
        "cnj": "0010307-23.2026.5.03.0089",
        "titulo": "ACME x Fulano",
        "natureza": "Trabalhista",
        "responsavel": "Trabalhista",
        "tipo_acao": "Reclamacao Trabalhista",
        "valor_causa": "50.000,00",
        "cliente": "ACME LTDA",
        "cnpj_cliente": "12.345.678/0001-99",
        "posicao": "Reclamado",
        "contrario": "Fulano",
        "cpf_contrario": "111.222.333-44",
    }
    pedidos = [{"pedido": "Horas Extras", "tipo": "Exito", "grau": "Provavel", "valor": "10.000,00"}]
    payload = build_lawsuit_payload(dados, FakeResolver(), pedidos=pedidos, default_status_id=1)
    assert payload["identifierNumber"] == "0010307-23.2026.5.03.0089"
    assert payload["type"] == "Judicial"
    assert payload["natureId"] == 10
    assert payload["responsibleAreaId"] == 3
    assert payload["originAreaId"] == 3
    assert payload["actionTypeId"] == 7
    assert payload["statusId"] == 1
    assert payload["monetaryAmount"]["value"] == 50000.0
    assert payload["MonetaryAmountType"] == "Determined"
    assert len(payload["participants"]) == 2
    assert len(payload["claims"]) == 1
