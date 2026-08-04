# -*- coding: utf-8 -*-
"""Armadilhas do Forms cível que quebram o mapeador trabalhista.

Cada teste demonstra o comportamento do mapeador trabalhista (`forms_mapping`)
sobre um payload cível e prova que `forms_mapping_civel` o contorna.
Referência: docs/MAPEAMENTO_FORMS_CIVEL.md (coleta 2026-08-04).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forms_mapping as trab
import forms_mapping_civel as civel


def _payload(q34, extras=None):
    """Payload cível: as DUAS perguntas 'Tipo de cadastro' (Q1 e Q34)."""
    perguntas = [
        {"pergunta": "Tipo de cadastro", "resposta": "Processo"},
        {"pergunta": "Tipo de cadastro", "resposta": q34},
    ]
    perguntas.extend(extras or [])
    return {"perguntas_forms": perguntas}


# ── Armadilha 1: "Tipo de cadastro" aparece duas vezes ────────────────────────


@pytest.mark.parametrize("q34", ["Decisões", "Arquivamento", "Incidente", " Recurso"])
def test_tipo_cadastro_duplicado_polui_o_campo_no_trabalhista(q34):
    """`_buscar_por_alias` junta as respostas de Q1 e Q34 com ' | '.

    Acontece SEMPRE, mesmo quando a classificação por acaso acerta.
    """
    campo = trab.mapear_formulario(_payload(q34))["campos"]["tipo_cadastro"]
    assert " | " in campo
    assert campo.startswith("Processo")


@pytest.mark.parametrize(
    "q34,esperado",
    [
        ("Cadastro inicial", "CADASTRO INICIAL"),
        ("Decisões", "DECISOES"),
        (" Recurso", "RECURSO"),
        ("Arquivamento", "ARQUIVAMENTO"),
        ("Incidente", "INCIDENTE"),
    ],
)
def test_civel_desambigua_as_duas_perguntas_homonimas(q34, esperado):
    r = civel.mapear_formulario(_payload(q34))
    assert r["campos"]["tipo_entidade"] == "PROCESSO"
    assert r["campos"]["tipo_cadastro"] == esperado
    assert r["secao"] == esperado


def test_civel_desambigua_em_qualquer_ordem_de_resposta():
    """Os domínios de Q1 e Q34 são disjuntos, então a ordem não importa."""
    direto = civel.classificar_tipo_cadastro(["Processo", "Decisões"])
    invertido = civel.classificar_tipo_cadastro(["Decisões", "Processo"])
    assert direto == invertido == ("PROCESSO", "DECISOES")


def test_civel_roteia_pessoa_juridica_sem_precisar_de_q34():
    """Quem escolhe PJ/PF nem chega na pergunta 34."""
    r = civel.mapear_formulario({"perguntas_forms": [
        {"pergunta": "Tipo de cadastro", "resposta": "Pessoa jurídica"},
        {"pergunta": "CNPJ", "resposta": "12.345.678/0001-90"},
    ]})
    assert r["secao"] == "PESSOA JURIDICA"
    assert r["campos"]["cnpj"] == "12.345.678/0001-90"
    assert r["tipo_cadastro"] is None


# ── Armadilha 2: `pedidos` é texto livre no cível ─────────────────────────────


def test_pedidos_texto_livre_no_civel_vs_multipla_escolha_no_trabalhista():
    (trab_pedidos,) = [c for c in trab.MAPEAMENTO_POR_TIPO["CADASTRO INICIAL"]
                       if c.campo == "pedidos"]
    (civel_pedidos,) = [c for c in civel.CADASTRO_INICIAL_FIELDS if c.campo == "pedidos"]
    assert trab_pedidos.tipo_resposta == "opcao_multipla"
    assert civel_pedidos.tipo_resposta == "texto_multilinha"


def test_pedidos_longo_sobrevive_inteiro():
    texto = ("Danos morais R$ 50.000,00; danos materiais R$ 12.345,67; "
             "obrigação de fazer — reparo do imóvel")
    r = civel.mapear_formulario(_payload("Cadastro inicial", [
        {"pergunta": "Pedidos e objetos dos pedidos", "resposta": texto},
    ]))
    assert r["campos"]["pedidos"] == texto


# ── Armadilha 3: domínios divergentes por seção ───────────────────────────────


def _opcoes(regras, campo):
    return next(c.opcoes for c in regras if c.campo == campo)


def test_motivo_muda_de_dominio_entre_decisoes_e_arquivamento():
    """Decisões usa réu/autor; Arquivamento mantém Empresa/RCTE (como o trabalhista)."""
    decisoes = _opcoes(civel.DECISOES_FIELDS, "motivo")
    arquivamento = _opcoes(civel.ARQUIVAMENTO_FIELDS, "motivo")
    assert "Provas produzidas pelo réu" in decisoes
    assert "Provas produzidas pelo autor" in decisoes
    assert "Provas produzidas pela Empresa" in arquivamento
    assert "Provas produzidas pelo RCTE" in arquivamento
    assert set(decisoes) != set(arquivamento)


def test_instancia_tem_dominio_proprio_em_recurso():
    assert _opcoes(civel.DECISOES_FIELDS, "instancia") == ("1ª instância", "2ª instância", "Outra")
    assert _opcoes(civel.RECURSO_FIELDS, "instancia") == ("1° Grau", "2º Grau", "STJ", "Outra")
    # o trabalhista tem um domínio único que não serve para nenhum dos dois
    trab_instancia = _opcoes(trab.MAPEAMENTO_POR_TIPO["DECISOES"], "instancia")
    assert "STJ" not in trab_instancia


def test_tipo_vinculo_tem_tres_dominios_distintos():
    inicial = _opcoes(civel.CADASTRO_INICIAL_FIELDS, "tipo_vinculo")
    incidente = _opcoes(civel.INCIDENTE_FIELDS, "tipo_vinculo")
    resultado = _opcoes(civel.DECISOES_FIELDS, "tipo_vinculo")
    assert len(inicial) == 18
    assert len(incidente) == 19
    assert "Requerimento de Efeito Suspensivo" in incidente
    assert "Requerimento de Efeito Suspensivo" not in inicial
    assert len(resultado) == 8  # 7 opções + "Outra"
    assert len({inicial, incidente, resultado}) == 3


def test_fase_usa_a_lista_civel():
    fase = _opcoes(civel.CADASTRO_INICIAL_FIELDS, "fase")
    assert len(fase) == 13
    assert "Conciliatória" in fase and "Recursal" in fase
    # no trabalhista `fase` não tem domínio declarado — nada a herdar
    assert _opcoes(trab.MAPEAMENTO_POR_TIPO["CADASTRO INICIAL"], "fase") == ()


def test_acao_muda_de_dominio_entre_cadastro_inicial_e_incidente():
    # 79 conferido item a item contra a lista do doc; o rótulo "(76 opções)"
    # que o doc trazia estava errado e foi corrigido.
    assert len(_opcoes(civel.CADASTRO_INICIAL_FIELDS, "acao")) == 79
    assert len(_opcoes(civel.INCIDENTE_FIELDS, "acao")) == 20


# ── Armadilha 4: um único "Arquivamento", e " Recurso" com espaço inicial ─────


@pytest.mark.parametrize("valor", ["Arquivamento", "Incidente"])
def test_trabalhista_nao_reconhece_arquivamento_unico_nem_incidente(valor):
    assert trab.detectar_tipo_cadastro(valor) is None
    r = trab.mapear_formulario(_payload(valor))
    assert r["tipo_tarefa_identificada"] == "GENERICO"


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("Arquivamento", "ARQUIVAMENTO"),
        ("Incidente", "INCIDENTE"),
        # nomes do trabalhista aceitos por engano do usuário
        ("Arquivamento completo", "ARQUIVAMENTO"),
        ("Arquivamento simples", "ARQUIVAMENTO"),
    ],
)
def test_civel_reconhece_arquivamento_unico_e_incidente(valor, esperado):
    assert civel.detectar_tipo_cadastro(valor) == esperado
    assert civel.TIPO_TAREFA_POR_CADASTRO[esperado] == esperado.replace(" ", "_")


def test_recurso_com_espaco_inicial():
    """Como gravado na definição do Forms: ' Recurso'."""
    assert civel.detectar_tipo_cadastro(" Recurso") == "RECURSO"
    assert civel.detectar_tipo_cadastro("Recurso ") == "RECURSO"


def test_arquivamento_endurece_obrigatoriedade_em_relacao_a_decisoes():
    opcionais = {c.campo for c in civel.DECISOES_FIELDS if not c.obrigatorio}
    obrigatorios = {c.campo for c in civel.ARQUIVAMENTO_FIELDS if c.obrigatorio}
    assert {"situacao_pedido", "tipo_resultado", "resultado"} <= opcionais & obrigatorios


def test_data_arquivamento_so_existe_no_arquivamento():
    assert any(c.campo == "data_arquivamento" for c in civel.ARQUIVAMENTO_FIELDS)
    assert not any(c.campo == "data_arquivamento" for c in civel.DECISOES_FIELDS)


# ── Armadilha 5: campos do trabalhista que não existem no cível ───────────────

CAMPOS_SO_DO_TRABALHISTA = (
    "funcao_rcte", "incluir_relatorio", "objetos", "vinculo_trabalhista",
    "descricao_pedidos", "terceirizacao_1", "terceirizacao_2", "pejotizacao",
    "valor_total_deferido", "data_julgamento", "responsabilidade", "redirecionamento",
    "houve_interposicao_recurso", "parte_recorrente", "datacloud_configurado",
    "honorarios_favor_escritorio", "valor_honorarios_favor_escritorio",
    "comentario_adicional",
)


def test_campos_exclusivos_do_trabalhista_ausentes_do_civel():
    todos_civel = {c.campo for regras in civel.MAPEAMENTO_POR_SECAO.values() for c in regras}
    assert todos_civel.isdisjoint(CAMPOS_SO_DO_TRABALHISTA)


def test_civel_nao_cobra_obrigatorio_que_nao_existe_no_formulario():
    """Payload cível completo de DECISÕES não pode pedir campo trabalhista."""
    r = civel.mapear_formulario(_payload("Decisões", [
        {"pergunta": "Número CNJ", "resposta": "1234567-89.2025.8.13.0024"},
        {"pergunta": "Cliente principal", "resposta": "MVC"},
        {"pergunta": "Contrário principal", "resposta": "Fulano"},
    ]))
    assert r["faltando_obrigatorios"] == []
    assert set(r["campos"]).isdisjoint(CAMPOS_SO_DO_TRABALHISTA)


# ── Cobertura da ramificação ─────────────────────────────────────────────────


def test_toda_ramificacao_aponta_para_secao_existente():
    nomes = {s.nome for s in civel.SECOES}
    for ram in civel.RAMIFICACOES:
        assert set(ram.destinos.values()) <= nomes


def test_toda_secao_de_destino_tem_campos_mapeados():
    destinos = {d for ram in civel.RAMIFICACOES for d in ram.destinos.values()}
    destinos.discard("PROCESSO")  # seção 4 só contém a própria pergunta 34
    for destino in destinos:
        assert civel.MAPEAMENTO_POR_SECAO[destino], destino
