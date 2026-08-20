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
