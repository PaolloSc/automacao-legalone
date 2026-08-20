from unittest.mock import MagicMock, patch

from forms_extractor import FormsExtractor


def test_extrair_ultima_resposta_via_api_usa_contador_do_formulario(tmp_path):
    counter_file = tmp_path / "ultimo_processo_civel.txt"
    counter_file.write_text("200")

    ex = FormsExtractor(
        counter_file=str(counter_file),
        modulo_mapeamento="forms_mapping_civel",
        resposta_minima=200,
    )

    definicao_fake = {"id": "FORM123", "questions": [
        {"id": "q1", "title": "Número CNJ", "choices": []},
    ]}
    # 'answers' aqui JA' vem decodificado (lista de dict) — e' o que
    # FormsApiCliente.listar_respostas devolve depois do json.loads interno
    # (Task 1), o mock nao precisa simular a string JSON crua.
    respostas_fake = [
        {"id": 201, "answers": [{"questionId": "q1", "answer1": "1234567-89.2025.8.13.0024"}]},
        {"id": 202, "answers": [{"questionId": "q1", "answer1": "9999999-99.2025.8.13.0024"}]},
    ]

    cliente_mock = MagicMock()
    cliente_mock.definicao_formulario.return_value = definicao_fake
    cliente_mock.listar_respostas.return_value = respostas_fake

    with patch("forms_extractor.FormsApiCliente", return_value=cliente_mock):
        dados = ex.extrair_ultima_resposta_via_api(
            "https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?...&id=FORM123"
        )

    assert dados is not None
    assert any(p["resposta"] == "9999999-99.2025.8.13.0024" for p in dados["perguntas_forms"])
    assert counter_file.read_text().strip() == "202"


def test_sessao_expirada_seta_erro_extracao_sem_lancar(tmp_path):
    from forms_api_cliente import SessaoFormsExpirada

    counter_file = tmp_path / "ultimo_processo_civel.txt"
    counter_file.write_text("200")
    ex = FormsExtractor(counter_file=str(counter_file), modulo_mapeamento="forms_mapping_civel")

    with patch("forms_extractor.FormsApiCliente", side_effect=SessaoFormsExpirada("expirou")):
        dados = ex.extrair_ultima_resposta_via_api("https://forms.cloud.microsoft/...&id=FORM123")

    assert dados is None
    assert "expirou" in (ex.erro_extracao or "")


def test_nenhuma_resposta_nova_retorna_none_sem_erro(tmp_path):
    """Caminho NORMAL de 'nada novo' — nao e' erro, so' None. Distinto do
    caso de sessao expirada: aqui erro_extracao continua vazio."""
    counter_file = tmp_path / "ultimo_processo_civel.txt"
    counter_file.write_text("200")
    ex = FormsExtractor(counter_file=str(counter_file), modulo_mapeamento="forms_mapping_civel")

    cliente_mock = MagicMock()
    cliente_mock.definicao_formulario.return_value = {"id": "FORM123", "questions": []}
    # nenhuma resposta com id > ultimo_salvo (200)
    cliente_mock.listar_respostas.return_value = [{"id": 200, "answers": []}]

    with patch("forms_extractor.FormsApiCliente", return_value=cliente_mock):
        dados = ex.extrair_ultima_resposta_via_api("https://forms.cloud.microsoft/...&id=FORM123")

    assert dados is None
    assert not ex.erro_extracao


def test_forms_resposta_minima_invalida_seta_erro_extracao_sem_lancar(tmp_path, monkeypatch):
    """FORMS_RESPOSTA_MINIMA nao-numerico nao pode lancar ValueError cru —
    o metodo inteiro (inclusive o parse do piso) precisa estar dentro do
    guard de erro_extracao, igual ao resto da funcao."""
    counter_file = tmp_path / "ultimo_processo_civel.txt"
    counter_file.write_text("200")
    ex = FormsExtractor(counter_file=str(counter_file), modulo_mapeamento="forms_mapping_civel")
    monkeypatch.setenv("FORMS_RESPOSTA_MINIMA", "nao-e-numero")

    with patch("forms_extractor.FormsApiCliente", return_value=MagicMock()):
        dados = ex.extrair_ultima_resposta_via_api("https://forms.cloud.microsoft/...&id=FORM123")

    assert dados is None
    assert ex.erro_extracao
