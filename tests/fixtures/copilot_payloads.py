"""Payloads de exemplo no formato que o Copilot Studio manda (dados_diretos),
um por tipo_cadastro, pro agente de teste E2E (Nivel A).

O caso LIVIA/ITAU e' real: extraido de
Peticao_Inicial_Trabalhista_TESTE_0000283-33.2024.5.08.0002.docx (documento
de teste, dados publicos do processo TRT8, valores ficticios). E' o mesmo
caso que gerou os avisos falsos de 'campo VAZIO' do qa_validator.py.

CNJ prefixado onde o caso e' sintetico (nao vem do doc real), pra nunca
confundir com processo de verdade se algum dia isso tocar o LegalOne real.
"""

# Caso real (documento de teste), tipo CADASTRO INICIAL, versao LIMPA
# (o que o Copilot Studio DEVERIA mandar seguindo as Regras de Preenchimento)
LIVIA_ITAU_LIMPO = {
    "tipo_cadastro": "Cadastro Inicial",
    "cnj": "0000283-33.2024.5.08.0002",
    "cliente": "LIVIA MILENA SOUZA MOREIRA",
    "contrario": "ITAU UNIBANCO S/A",
    "natureza": "Trabalhista",
    "instancia": "1a",
    "fase": "Conhecimento",
    "posicao": "Reclamante",
    "contingencia": "Ativa",
    "probabilidade": "NAO LOCALIZADO",
    "grau_probabilidade": "NAO LOCALIZADO",
    "risco": "NAO LOCALIZADO",
    "advogado": "NAO LOCALIZADO",  # advogada que assina a peca (Monica Pinheiro) NAO e' do escritorio
    "cidade_comarca": "Belem/PA",
    "valor_causa": "895000.00",
    "objetos": "Horas extras, intervalo intrajornada, PLR, FGTS + 40%, verbas rescisorias",
    "data_distribuicao": "NAO LOCALIZADO",
    "pedidos": (
        "1) Citacao da reclamada; 2) Procedencia total dos pedidos "
        "(horas extras, intervalo intrajornada, PLR, FGTS+40%, verbas "
        "rescisorias); 3) Juros e correcao monetaria; 4) Justica gratuita; "
        "5) Honorarios sucumbenciais; 6) Recolhimento previdenciario/fiscal"
    ),
    "descricao_pedidos": "Pedidos trabalhistas decorrentes de jornada extraordinaria nao paga e verbas rescisorias",
    "cnpj_contrario": "60.701.190/0001-04",
}

# Mesmo caso, versao SUJA — exatamente o formato que gerou o bug real
# reportado (papel/CNPJ colado no valor). Usado pra provar que a limpeza
# em legalone_cadastro.py (Nivel A / Task 3) continua funcionando.
LIVIA_ITAU_SUJO = {
    **LIVIA_ITAU_LIMPO,
    "cliente": "LIVIA MILENA SOUZA MOREIRA (Reclamante)",
    "contrario": "ITAU UNIBANCO S/A (CNPJ 60.701.190/0001-04)",
    "posicao": "Reclamante (Ativo)",
}

# Fixtures sinteticas pros outros 4 tipos — CNJ prefixado, nunca confundir
# com processo real. O prefixo NAO pode ter digito: `cnj_valido()` conta os
# digitos da string inteira, e o '2' de 'E2E' fazia 21 e reprovava o payload.
DECISOES_SINTETICO = {
    "tipo_cadastro": "Decisoes",
    "cnj": "TESTE-AGENTE-0000001-11.2026.5.03.0001",
    "cliente": "Fulano de Tal (Reclamante)",
    "contrario": "Empresa Teste LTDA",
    "natureza": "Trabalhista",
    "instancia": "1a",
    "fase": "Decisoria",
    "posicao": "Reclamante",
    "contingencia": "Ativa",
    "situacao_pedido": "Parcialmente deferido",
    "valor_total_deferido": "5000.00",
    "terceirizacao_1": "Nao",
    "terceirizacao_2": "Nao",
    "tipo_resultado": "Sentenca",
    "resultado": "Exito Parcial",
    "data_resultado": "01/03/2026",
    "cobranca_honorarios_sucumbenciais": "Sim",
    "cobranca_honorarios_contratuais_exito": "Nao",
    "justificativa_nao_cobranca_honorarios_contratuais": "Sem previsao contratual",
}

RECURSO_SINTETICO = {
    "tipo_cadastro": "Recurso",
    "cnj": "TESTE-AGENTE-0000002-22.2026.5.03.0002",
    "cliente": "Ciclana Souza",
    "contrario": "Banco Teste S/A (CNPJ 00.000.000/0001-00)",
    "natureza": "Trabalhista",
    "instancia": "2a",
    "fase": "Recursal",
    "posicao": "Recorrida",
    "contingencia": "Passiva",
    "data_distribuicao": "15/02/2026",
    "tipo_classe_recurso": "Recurso Ordinario",
    "orgao": "TRT3",
    "uf": "MG",
    "cidade": "Belo Horizonte",
    "comarca": "Belo Horizonte",
    "datacloud_configurado": "Sim",
}

ARQUIVAMENTO_COMPLETO_SINTETICO = {
    "tipo_cadastro": "Arquivamento Completo",
    "cnj": "TESTE-AGENTE-0000003-33.2026.5.03.0003",
    "cliente": "Escritorio Teste Advocacia",
    "contrario": "Sicrano de Souza",
    "natureza": "Civel",
    "instancia": "1a",
    "fase": "Arquivado",
    "posicao": "Autor",
    "contingencia": "Ativa",
    "situacao_pedido": "Deferido",
    "tipo_resultado": "Acordo",
    "resultado": "Acordo",
    "data_arquivamento": "20/03/2026",
    "cobranca_honorarios_sucumbenciais": "Sim",
    "cobranca_honorarios_contratuais_exito": "Sim",
}

ARQUIVAMENTO_SIMPLES_SINTETICO = {
    "tipo_cadastro": "Arquivamento Simples",
    "cnj": "TESTE-AGENTE-0000004-44.2026.5.03.0004",
    "cliente": "Beltrana Costa",
    "contrario": "Comercio Teste ME",
    "natureza": "Civel",
    "instancia": "1a",
    "fase": "Arquivado",
    "posicao": "Reu",
    "contingencia": "Passiva",
    "data_arquivamento": "05/04/2026",
    "honorarios_favor_escritorio": "Nao",
}

PAYLOADS = {
    "CADASTRO INICIAL": LIVIA_ITAU_SUJO,
    "DECISOES": DECISOES_SINTETICO,
    "RECURSO": RECURSO_SINTETICO,
    "ARQUIVAMENTO COMPLETO": ARQUIVAMENTO_COMPLETO_SINTETICO,
    "ARQUIVAMENTO SIMPLES": ARQUIVAMENTO_SIMPLES_SINTETICO,
}


def email_data_copilot(payload: dict) -> dict:
    """Monta o email_data no formato que OutlookMonitorGraph produz pro Copilot."""
    return {
        "subject": "LegalOne - Dados Extraidos de Peticao",
        "sender": "flow@carvalhofurtadoadv.com.br",
        "received_time": "2026-07-27T12:00:00Z",
        "body": "",
        "entry_id": f"teste-{payload.get('cnj', 'sem-cnj')}",
        "forms_link": None,
        "dados_diretos": dict(payload),
    }
