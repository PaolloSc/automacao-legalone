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
            {"id": 10, "name": "Trabalhista"},
            {"id": 11, "name": "Civel"},
        ]
    })
    r = FieldResolver(client)
    assert r.resolve_natureza("Trabalhista") == 10
    assert r.resolve_natureza("trabalhista") == 10
    assert len(client.calls) == 1


def test_resolve_natureza_accent_and_case_insensitive():
    client = FakeClient({
        "SystemTables.Litigation/LitigationNatures": [{"id": 11, "name": "Civel"}]
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
    assert client.calls == []


def test_resolve_posicao_and_tipo_acao_use_correct_paths():
    client = FakeClient({
        "SystemTables.Litigation/LitigationParticipantPositions": [
            {"id": 5, "name": "Reu"}
        ],
        "SystemTables.Litigation/LitigationActionAppealProceduralIssuetypes": [
            {"id": 7, "name": "Reclamacao Trabalhista"}
        ],
    })
    r = FieldResolver(client)
    assert r.resolve_posicao("Reu") == 5
    assert r.resolve_tipo_acao("Reclamacao Trabalhista") == 7
