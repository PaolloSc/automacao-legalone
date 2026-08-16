"""
Testes de integração para o roteamento entre Forms trabalhista e cível.

Garante que o fluxo principal escolhe o mapeador correto conforme o assunto
do e-mail de notificação do Microsoft Forms.
"""

import pytest
import sys
import os

# Garante importação do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_automacao import FORMS_TIPOS
from forms_extractor import FormsExtractor
from automacao_legalone_completa import (
    AutomacaoLegalOne,
    detectar_tipo_forms_pelo_assunto,
)


@pytest.mark.parametrize(
    "assunto, modulo_esperado, natureza_esperada",
    [
        (
            "Cadastro de processos NOVOS LegalOne trabalhista",
            "forms_mapping",
            "Trabalhista",
        ),
        (
            "Re: Cadastro de processos NOVOS LegalOne trabalhista",
            "forms_mapping",
            "Trabalhista",
        ),
        (
            "Nova resposta de Cível - cadastro LegalOne",
            "forms_mapping_civel",
            "Cível",
        ),
        (
            "FW: Nova resposta de Cível - cadastro LegalOne",
            "forms_mapping_civel",
            "Cível",
        ),
    ],
)
def test_detectar_tipo_forms_pelo_assunto(assunto, modulo_esperado, natureza_esperada):
    cfg = detectar_tipo_forms_pelo_assunto(assunto)
    assert cfg["modulo_mapeamento"] == modulo_esperado
    assert cfg["natureza_default"] == natureza_esperada


def test_detectar_tipo_forms_fallback_trabalhista():
    cfg = detectar_tipo_forms_pelo_assunto("Assunto desconhecido")
    assert cfg["modulo_mapeamento"] == "forms_mapping"
    assert cfg["natureza_default"] == "Trabalhista"


def test_forms_extractor_carrega_mapeador_civel():
    ex = FormsExtractor(modulo_mapeamento="forms_mapping_civel")
    assert ex.modulo_mapeamento == "forms_mapping_civel"
    assert ex._mapear_formulario is not None
    # ponta a ponta: payload cível é mapeado corretamente
    resultado = ex._mapear_formulario(
        {
            "perguntas_forms": [
                {"pergunta": "Tipo de cadastro", "resposta": "Processo"},
                {"pergunta": "Tipo de cadastro", "resposta": "Decisões"},
                {"pergunta": "Número CNJ", "resposta": "1234567-89.2025.8.13.0024"},
                {"pergunta": "Cliente principal", "resposta": "MVC"},
                {"pergunta": "Contrário principal", "resposta": "Fulano"},
            ]
        }
    )
    assert resultado["secao"] == "DECISOES"
    assert resultado["campos"]["tipo_entidade"] == "PROCESSO"
    assert resultado["campos"]["tipo_cadastro"] == "DECISOES"


def test_recurso_civel_vira_cadastro_novo():
    """No cível o recurso é criado DENTRO da pasta de origem ('Novo recurso'),
    não pode cair no _fluxo_recurso do trabalhista, que altera o processo."""
    ex = FormsExtractor(modulo_mapeamento="forms_mapping_civel")
    dados = ex._aplicar_mapeamento_forms(
        {
            "perguntas_forms": [
                {"pergunta": "1. Tipo de cadastro Required to answer. Single choice.",
                 "resposta": "Processo"},
                {"pergunta": "2. Tipo de cadastro Required to answer. Single choice.",
                 "resposta": "Recurso"},
                {"pergunta": "3. Número de CNJ Required to answer. Single line text.",
                 "resposta": "4105424-55.2026.8.26.0000"},
                {"pergunta": "12. Vínculo (se houver - processo ou serviço) Single line text.",
                 "resposta": "4028550-54.2025.8.26.0100"},
            ],
        }
    )
    assert dados["cnj"] == "4105424-55.2026.8.26.0000"  # CNJ do próprio recurso
    assert dados["vinculo"] == "4028550-54.2025.8.26.0100"  # processo de origem
    assert dados["tipo_tarefa_identificada"] == "RECURSO_CIVEL"
    assert dados["tipo_cadastro"] == "RECURSO"
    assert dados["nao_mapeados_forms"] == []


def test_resposta_traz_enunciado_colado_e_roteia_recurso():
    """Payload real da resposta 232: o texto da pergunta vem colado no valor.

    Sem limpar, 'Vínculo' ficava com 22 dígitos (o "12." do enunciado) e não
    servia para achar a pasta de origem; e 'tipo_cadastro' ficava 'PROCESSO',
    o que jogava o recurso no fluxo de cadastro de processo avulso.
    """
    ex = FormsExtractor(modulo_mapeamento="forms_mapping_civel")
    dados = ex._aplicar_mapeamento_forms(
        {
            "cnj": "4105424-55.2026.8.26.0000",
            "tipo_cadastro": "PROCESSO",  # varredura do DOM pegou a pergunta 1
            "perguntas_forms": [
                {"pergunta": "1. Tipo de cadastro Requer resposta. Opção única.",
                 "resposta": "Processo", "marcadas": ["Processo"]},
                {"pergunta": "2. Tipo de cadastro Requer resposta. Opção única.",
                 "resposta": "Recurso", "marcadas": ["Recurso"]},
                {"pergunta": "3. Número de CNJ Requer resposta. Texto de linha única.",
                 "resposta": "3. Número de CNJ Requer resposta. Texto de linha única. "
                             "4105424-55.2026.8.26.0000"},
                {"pergunta": "5. Cliente principal Requer resposta. Texto de linha única.",
                 "resposta": "5. Cliente principal Requer resposta. Texto de linha única. "
                             "Amanda Alves Pereira da Silva"},
                {"pergunta": "4. Número antigo Texto de linha única.",
                 "resposta": "4. Número antigo Texto de linha única. Nenhuma resposta fornecida."},
                {"pergunta": "12. Vínculo (se houver - processo ou serviço) Texto de linha única.",
                 "resposta": "12. Vínculo (se houver - processo ou serviço) Texto de linha única. "
                             "4028550-54.2025.8.26.0100"},
            ],
        }
    )
    assert dados["cliente"] == "Amanda Alves Pereira da Silva"
    assert dados["tipo_cadastro"] == "RECURSO"
    assert dados["tipo_tarefa_identificada"] == "RECURSO_CIVEL"
    assert dados["cnj"] == "4105424-55.2026.8.26.0000"
    assert dados["vinculo"] == "4028550-54.2025.8.26.0100"
    assert not dados["mapeamento_forms"]["campos"].get("numero_antigo")


def test_automacao_cria_extratores_por_natureza():
    auto = AutomacaoLegalOne(config={"skip_email": True})
    assert len(auto.forms_extractors) == len(FORMS_TIPOS)
    for cfg in FORMS_TIPOS:
        extrator = auto.forms_extractors.get(cfg["assunto_filtro"])
        assert extrator is not None
        assert extrator.modulo_mapeamento == cfg["modulo_mapeamento"]
        # contador e piso por formulário: o cível está na faixa 200 e o
        # trabalhista na 800 — compartilhar leva a resposta vazia
        assert extrator.counter_file == cfg["contador"]
        assert extrator.resposta_minima == cfg["resposta_minima"]

    contadores = [cfg["contador"] for cfg in FORMS_TIPOS]
    assert len(set(contadores)) == len(contadores)
