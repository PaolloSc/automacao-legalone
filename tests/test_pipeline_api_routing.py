from automacao_legalone_completa import escolher_cadastro


def test_escolhe_api_quando_flag_ligada(monkeypatch):
    monkeypatch.setattr(
        "config_automacao.LEGALONE_API_CONFIG",
        {
            "use_api": True,
            "client_id": "x",
            "client_secret": "y",
            "token_url": "u",
            "base_url": "b",
            "default_status_id": "1",
            "default_area_id": "3",
            "timeout": 30,
        },
        raising=False,
    )
    assert escolher_cadastro() == "api"


def test_escolhe_browser_quando_flag_desligada(monkeypatch):
    monkeypatch.setattr(
        "config_automacao.LEGALONE_API_CONFIG",
        {
            "use_api": False,
            "client_id": "",
            "client_secret": "",
            "token_url": "u",
            "base_url": "b",
            "default_status_id": "",
            "default_area_id": "",
            "timeout": 30,
        },
        raising=False,
    )
    assert escolher_cadastro() == "browser"
