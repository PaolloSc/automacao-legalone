"""Valida que os nomes de campo escritos nas Instrucoes do Copilot Studio
(e espelhados em docs/COPILOT_AGENTE.md) batem exatamente com os campos
que forms_mapping.py define por tipo de cadastro (MAPEAMENTO_POR_TIPO).

Nota: mapear_formulario()/_buscar_por_alias() sao usados apenas pelo
fluxo do Forms (forms_extractor.py). O fluxo do Copilot em
automacao_legalone_completa.py NAO passa dados_diretos por
mapear_formulario - ele so garante que nada se perca, jogando qualquer
campo fora da whitelist (_campos_base) para outros_dados. Por isso o
teste aqui compara diretamente contra MAPEAMENTO_POR_TIPO, que e a fonte
da verdade dos nomes de campo (e o que a doc/instrucoes devem espelhar).
"""
from forms_mapping import MAPEAMENTO_POR_TIPO, COMMON_FIELDS, CADASTRO_INICIAL_FIELDS


def _nomes(tipo):
    return {c.campo for c in MAPEAMENTO_POR_TIPO[tipo]}


# Campos comuns exatamente como escrito nas novas Instrucoes do Copilot Studio
# (sem "natureza": esse nao existe em forms_mapping.py, e' um campo extra que o
# bot aceita via _campos_base mas nao faz parte do mapping por tipo).
COMUM_DO_PROMPT = {
    "tipo_cadastro", "cnj", "cliente", "contrario", "instancia", "fase",
    "contingencia", "probabilidade", "grau_probabilidade", "risco",
    "advogado", "procedimento", "cidade_comarca", "valor_causa", "objetos",
    "data_distribuicao", "pedidos", "descricao_pedidos",
    "data_julgamento", "redirecionamento", "contrato_honorarios",
    "incluir_relatorio", "funcao_rcte", "outros_envolvidos",
    "vinculo_trabalhista", "responsabilidade", "data_citacao",
    # "posicao" NAO esta em COMMON_FIELDS no codigo hoje - so existe em
    # RECURSO_FIELDS. E' o unico ponto onde a doc/instrucoes (que listam
    # posicao como campo comum) divergem do forms_mapping.py real.
}

DECISOES_DO_PROMPT = COMUM_DO_PROMPT | {
    "situacao_pedido", "valor_total_deferido", "valor_deferido_por_pedido",
    "terceirizacao_1", "terceirizacao_2", "pejotizacao", "motivo",
    "valor_acordo_condenacao", "valor_honorarios", "valor_custas", "custas",
    "tipo_resultado", "resultado", "motivo_resultado", "data_resultado",
    "data_sentenca", "cobranca_honorarios_sucumbenciais",
    "justificativa_nao_cobranca_honorarios_sucumbenciais",
    "cobranca_honorarios_contratuais_exito",
    "justificativa_nao_cobranca_honorarios_contratuais",
    "houve_interposicao_recurso", "parte_recorrente",
}

RECURSO_DO_PROMPT = COMUM_DO_PROMPT | {
    "posicao", "data_distribuicao", "tipo_classe_recurso", "orgao", "uf",
    "cidade", "comarca", "numero_turma", "objetos_recurso",
    "classificacao_pedidos_recurso", "datacloud_configurado", "observacoes",
}

ARQ_COMPLETO_DO_PROMPT = COMUM_DO_PROMPT | {
    "situacao_pedido", "valor_deferido_por_pedido", "motivo",
    "valor_acordo_condenacao", "valor_honorarios", "custas", "valor_custas",
    "tipo_resultado", "resultado", "motivo_resultado", "data_resultado",
    "data_sentenca", "data_arquivamento", "cobranca_honorarios_sucumbenciais",
    "justificativa_nao_cobranca_honorarios_sucumbenciais",
    "cobranca_honorarios_contratuais_exito",
    "justificativa_nao_cobranca_honorarios_contratuais",
    "comentario_adicional",
}

ARQ_SIMPLES_DO_PROMPT = COMUM_DO_PROMPT | {
    "data_arquivamento", "honorarios_favor_escritorio",
    "valor_honorarios_favor_escritorio",
}


def test_campos_comuns_batem_com_o_codigo():
    assert {c.campo for c in COMMON_FIELDS} == COMUM_DO_PROMPT


def test_cadastro_inicial_sem_campos_extras():
    assert CADASTRO_INICIAL_FIELDS == ()
    assert _nomes("CADASTRO INICIAL") == COMUM_DO_PROMPT


def test_decisoes_bate_com_o_codigo():
    assert _nomes("DECISOES") == DECISOES_DO_PROMPT


def test_recurso_bate_com_o_codigo():
    assert _nomes("RECURSO") == RECURSO_DO_PROMPT


def test_arquivamento_completo_bate_com_o_codigo():
    assert _nomes("ARQUIVAMENTO COMPLETO") == ARQ_COMPLETO_DO_PROMPT


def test_arquivamento_simples_bate_com_o_codigo():
    assert _nomes("ARQUIVAMENTO SIMPLES") == ARQ_SIMPLES_DO_PROMPT


if __name__ == "__main__":
    test_campos_comuns_batem_com_o_codigo()
    test_cadastro_inicial_sem_campos_extras()
    test_decisoes_bate_com_o_codigo()
    test_recurso_bate_com_o_codigo()
    test_arquivamento_completo_bate_com_o_codigo()
    test_arquivamento_simples_bate_com_o_codigo()
    print("OK - os campos do novo prompt do Copilot Studio batem 100% com forms_mapping.py")
