import json
import os

from forms_api_conversor import converter_resposta_para_perguntas_forms

_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "formapi_resposta_exemplo.json"
)


def _carregar_fixture():
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        dados = json.load(f)
    resposta = dados["resposta"]
    # Na API crua 'answers' vem como string JSON-encoded; FormsApiCliente.listar_respostas
    # ja decodifica isso pra quem consome (Task 1). O conversor (Task 2) recebe a lista
    # ja decodificada, entao replicamos aqui o mesmo decode que o cliente faz.
    if isinstance(resposta.get("answers"), str):
        resposta = dict(resposta, answers=json.loads(resposta["answers"]))
    return dados["definicao"], resposta


def test_converte_resposta_em_perguntas_forms():
    definicao, resposta = _carregar_fixture()
    perguntas = converter_resposta_para_perguntas_forms(definicao, resposta)
    assert isinstance(perguntas, list)
    assert perguntas, "nenhuma pergunta convertida"
    assert len(perguntas) == 5
    primeira = perguntas[0]
    assert set(primeira.keys()) >= {
        "pergunta", "resposta", "resposta_texto", "opcoes", "marcadas", "texto_completo"
    }
    assert primeira["pergunta"] == "Tipo de cadastro"
    assert primeira["resposta"] == "Cadastro inicial"
    # e' pergunta de escolha unica (Question.ChoiceText) cujo valor bate com
    # uma das opcoes conhecidas, entao tambem conta como "marcada" (1 item)
    assert primeira["marcadas"] == ["Cadastro inicial"]

    cnj = next(p for p in perguntas if p["pergunta"] == "Número CNJ")
    assert cnj["resposta"] == "1234567-89.2025.8.13.0024"
    assert cnj["opcoes"] == []


def test_pergunta_de_multipla_escolha_marca_opcoes():
    definicao, resposta = _carregar_fixture()
    perguntas = converter_resposta_para_perguntas_forms(definicao, resposta)
    marcada = next((p for p in perguntas if len(p["marcadas"]) > 1), None)
    assert marcada is not None
    assert marcada["pergunta"] == "Centro de custo"
    assert marcada["marcadas"] == ["Cível", "Trabalhista"]
    assert marcada["resposta"] == ", ".join(marcada["marcadas"])
    assert marcada["resposta_texto"] == "Cível;Trabalhista"


def test_saida_do_conversor_e_aceita_pelo_mapeamento_civel():
    from forms_extractor import FormsExtractor

    definicao, resposta = _carregar_fixture()
    perguntas = converter_resposta_para_perguntas_forms(definicao, resposta)
    ex = FormsExtractor(modulo_mapeamento="forms_mapping_civel")
    resultado = ex._aplicar_mapeamento_forms({"perguntas_forms": perguntas})
    assert resultado.get("cnj")
