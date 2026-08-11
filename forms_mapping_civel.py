"""
Mapeamento do Microsoft Forms "Cível - cadastro LegalOne".

Módulo separado de `forms_mapping.py` (trabalhista) de propósito: as perguntas
se chamam igual mas os domínios de opções divergem (motivo, instância, fase,
tipo de vínculo, tipo de cadastro). Sobrescrever o mapeamento trabalhista
quebraria o que já funciona.

Coleta: 2026-08-04 — ver `docs/MAPEAMENTO_FORMS_CIVEL.md` (190 perguntas, 9 seções).

Diferença estrutural em relação ao trabalhista: este formulário também cadastra
PARTES (pessoa jurídica / pessoa física), não só processo. A pergunta 1 escolhe
a entidade; só no ramo "Processo" é que a pergunta 34 escolhe o tipo de cadastro.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from forms_mapping import (
    CampoForms,
    _buscar_por_alias,
    _filtrar_valores,
    _indice_perguntas,
    _normalizar_entrada_perguntas,
    normalizar_texto,
)


# ─────────────────────────── Vocabulário ───────────────────────────

TIPOS_ENTIDADE = ("PESSOA JURIDICA", "PESSOA FISICA", "PROCESSO")

TIPOS_CADASTRO = (
    "CADASTRO INICIAL",
    "DECISOES",
    "RECURSO",
    "ARQUIVAMENTO",
    "INCIDENTE",
)

# Q1. Conjunto DISJUNTO do de baixo — é isso que permite desambiguar as duas
# perguntas chamadas "Tipo de cadastro" pelo valor da resposta, sem depender
# da ordem em que o extrator devolveu as perguntas.
ENTIDADE_ALIAS = {
    "pessoa juridica": "PESSOA JURIDICA",
    "pessoa fisica": "PESSOA FISICA",
    "pj": "PESSOA JURIDICA",
    "pf": "PESSOA FISICA",
    "processo": "PROCESSO",
}

# Q34. "Recurso" vem com espaço inicial na definição do Forms (" Recurso");
# normalizar_texto já faz strip, mas fica registrado aqui o porquê.
TIPO_ALIAS = {
    "cadastro inicial": "CADASTRO INICIAL",
    "cadastro_inicial": "CADASTRO INICIAL",
    "decisao": "DECISOES",
    "decisoes": "DECISOES",
    "recurso": "RECURSO",
    "recursos": "RECURSO",
    "arquivamento": "ARQUIVAMENTO",
    # o cível tem um único arquivamento; aceita os nomes do trabalhista por engano do usuário
    "arquivamento completo": "ARQUIVAMENTO",
    "arquivamento simples": "ARQUIVAMENTO",
    "incidente": "INCIDENTE",
}

TIPO_TAREFA_POR_CADASTRO = {
    "CADASTRO INICIAL": "CADASTRO_INICIAL",
    "DECISOES": "DECISAO",
    "RECURSO": "RECURSO",
    "ARQUIVAMENTO": "ARQUIVAMENTO",
    "INCIDENTE": "INCIDENTE",
}


# ─────────────────────────── Ramificação ───────────────────────────


@dataclass(frozen=True)
class Ramificacao:
    """Uma pergunta que desvia o respondente para uma seção.

    Extraída de `questionInfo.Choices[].BranchInfo.TargetQuestionId` na
    definição do formulário. Só existem duas no formulário inteiro.
    """

    pergunta_num: int
    campo: str
    pergunta: str
    destinos: dict[str, str]  # valor normalizado da opção → nome da seção


@dataclass(frozen=True)
class Secao:
    nome: str
    numero: int
    primeira_pergunta: int
    ultima_pergunta: int


SECOES = (
    Secao("RAIZ", 1, 1, 1),
    Secao("PESSOA JURIDICA", 2, 2, 11),
    Secao("PESSOA FISICA", 3, 12, 33),
    Secao("PROCESSO", 4, 34, 34),
    Secao("CADASTRO INICIAL", 5, 35, 78),
    Secao("INCIDENTE", 6, 79, 119),
    Secao("DECISOES", 7, 120, 146),
    Secao("RECURSO", 8, 147, 168),
    Secao("ARQUIVAMENTO", 9, 169, 190),
)

RAMIFICACOES = (
    Ramificacao(
        pergunta_num=1,
        campo="tipo_entidade",
        pergunta="Tipo de cadastro",
        destinos={
            "pessoa juridica": "PESSOA JURIDICA",
            "pessoa fisica": "PESSOA FISICA",
            "processo": "PROCESSO",
        },
    ),
    Ramificacao(
        pergunta_num=34,
        campo="tipo_cadastro",
        pergunta="Tipo de cadastro",
        destinos={
            "cadastro inicial": "CADASTRO INICIAL",
            "decisoes": "DECISOES",
            "recurso": "RECURSO",
            "arquivamento": "ARQUIVAMENTO",
            "incidente": "INCIDENTE",
        },
    ),
)

# ponytail: fim de seção não modelado — o Forms não tem salto de saída
# configurado no fim das seções (NÃO CONFIRMADO no doc, item 1). Se aparecer
# resposta de duas seções no mesmo payload, a seção escolhida em Q34 é que vale.


# ────────────────── Listas de opções longas (seção 3 do doc) ──────────────────

ACOES_CADASTRO_INICIAL = (
    "Abertura, registro, reconhecimento, aprovação e cumprimento de testamento",
    "Ação Civil Coletiva", "Ação Civil Pública", "Ação de Divisão e Demarcação de Terras",
    "Ação de Divórcio", "Ação de Exigir Contas", "Ação de Improbidade Administrativa",
    "Ação de Regresso", "Ação Ordinária", "Ação Pauliana", "Ação Penal", "Ação Rescisória",
    "Ação Revisional", "Adjudicação Compulsória", "Alienação Judicial", "Alimentos",
    "Anulatória", "Auto de Infração", "Cautelar de Arrolamento de Bens",
    "Cautelar de Busca e Apreensão", "Cautelar de Protestos, Notificações e Interpelações",
    "Cautelar Inominada", "Cobrança", "Consignação em Pagamento", "Cumprimento de Sentença",
    "Cumprimento Provisório de Sentença", "Declaratória", "Desapropriação", "Despejo",
    "Dissolução de Sociedade", "Embargos à Execução", "Embargos à Execução Fiscal",
    "Embargos de Terceiro", "Execução", "Execução Fiscal", "Execução Provisória", "Falência",
    "Habeas Corpus", "Habeas Data", "Homologação da Transação Extrajudicial",
    "Homologação de Decisão Estrangeira", "Homologação do Penhor Legal", "Indenizatória",
    "Inquérito Policial", "Interdição", "Interdito Proibitório", "Inventário",
    "Investigação de Paternidade", "Liquidação", "Liquidação Provisória",
    "Mandado de Segurança", "Monitória", "Notificação Administrativa", "Obrigação de Fazer",
    "Oposição", "Precatório", "Produção Antecipada de Prova", "Queixa-Crime",
    "Reclamação Administrativa", "Reclamação Constitucional", "Reclamação Trabalhista",
    "Reconhecimento e Extinção de União Estável", "Recuperação Judicial",
    "Recurso Ordinário – Rito Sumaríssimo", "Recurso Ordinário Trabalhista",
    "Registro de Marca e Patente", "Regulação de Avaria Grossa",
    "Reintegração e Manutenção de Posse", "Reivindicatória", "Renovatória de Locação",
    "Repetição de Indébito", "Requisição de Pequeno Valor", "Rescisória",
    "Restauração de Autos", "Restituição", "Separação Consensual", "Separação Litigiosa",
    "Tutelas de Urgência Antecipada e Cautelar Requeridas em Caráter Antecedente",
    "Usucapião",
)

ACOES_INCIDENTE = (
    "Arguição de Falsidade Documental", "Carta de Ordem Cível", "Carta Precatória",
    "Carta Rogatória", "Conflito de Competência", "Desconsideração da Personalidade Jurídica",
    "Exceção de Incompetência", "Exceção de Pré-Executividade", "Habilitação de Crédito",
    "Impugnação à Assistência Gratuita", "Impugnação ao Valor da Causa",
    "Impugnação de Crédito", "Incidente de Apresentação de Contas",
    "Incidente de Arguição de Inconstitucionalidade", "Incidente de Assunção de Competência",
    "Incidente de Resolução de Demandas Repetitivas",
    "Incidente de Uniformização de Jurisprudência", "Inquérito Policial",
    "Requerimento de Efeito Suspensivo", "Suspeição e Impedimento",
)

TIPOS_RECURSO = (
    "Agravo de Instrumento", "Agravo de Instrumento em Agravo de Petição",
    "Agravo de Instrumento em Recurso de Revista",
    "Agravo de Instrumento em Recurso Ordinário", "Agravo de Petição",
    "Agravo em Recurso Especial", "Agravo em Recurso Extraordinário", "Agravo Interno",
    "Agravo Regimental", "Apelação", "Embargos de Declaração", "Embargos de Divergência",
    "Embargos Infringentes", "Recurso Administrativo", "Recurso de Revista",
    "Recurso em Sentido Estrito", "Recurso Especial", "Recurso Extraordinário",
    "Recurso Inominado", "Recurso Ordinário",
)

GRUPOS = (
    "Autoridade", "Cliente", "Colaborador", "Correspondente", "Ministério Público",
    "Parceiro", "Perito", "Potencial cliente", "Potencial fornecedor",
    "Potencial parceiro", "Sindicato", "Outra",
)

FASES = (
    "Arquivado", "Conciliatória", "Conhecimento", "Cumprimento de Sentença", "Decisória",
    "Encerrado", "Executória", "Extinto", "Inicial", "Instrutória", "Julgamento",
    "Liquidação", "Recursal",
)

NATUREZAS = (
    "Administrativo", "Ambiental", "Cível", "Constitucional", "Criminal", "Empresarial",
    "Família", "Sucessões", "Trabalhista", "Tributária",
)

PROCEDIMENTOS = ("Administrativo", "Especial", "Ordinário", "Sumário", "Sumaríssimo")

TIPOS_PROCESSO = ("Judicial", "Administrativo", "Arbitral")

CENTROS_CUSTO = (
    "Cível", "Tributário", "Trabalhista", "Ambiental", "Administrativo", "Família",
    "Relações governamentais", "Pastas sigilosas", "Penal", "Outra",
)

TIPOS_VINCULO_CADASTRO_INICIAL = (
    "Cautelar", "Conexo", "Consulta", "Cumprimento de Sentença", "Embargos à execução",
    "Embargos de terceiros", "Execução", "Execução Provisória", "Habeas corpus",
    "Habilitação de crédito", "Inventário", "Liquidação", "Mandado de segurança",
    "Negociação do contrato de honorário", "Parecer", "Processo Administrativo",
    "Reclamação Constitucional", "Recuperação Judicial",
)

TIPOS_VINCULO_INCIDENTE = TIPOS_VINCULO_CADASTRO_INICIAL + ("Requerimento de Efeito Suspensivo",)

TIPOS_VINCULO_RESULTADO = (
    "Liminar", "Incidentes", "Embargos à execução", "Execução",
    "Cumprimento de sentença", "Carta precatória", "Recurso", "Outra",
)

SITUACOES_PEDIDO = (
    "Deferido", "Extinto", "Indeferido", "Parcialmente deferido", "Suspenso", "Acordo", "Outra",
)

TIPOS_RESULTADO = ("Acórdão", "Acordo", "Decisão", "Sentença", "Outra")

RESULTADOS = ("Êxito total", "Acordo", "Êxito Parcial", "Extinto", "Perda", "Outra")

CUSTAS = ("Favorável", "Desfavorável", "Sem posição")

MOTIVOS_BASE = (
    "Ausência de concreta fundamentação", "Ausência de provas", "Danos constatados",
    "Falta de documentos", "Precedentes jurisprudenciais",
)


# ─────────────────────── Seção 1 — qual entidade ───────────────────────

ENTIDADE_FIELDS = (
    CampoForms(
        campo="tipo_entidade",
        pergunta="Tipo de cadastro",
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Pessoa jurídica", "Pessoa física", "Processo"),
        observacao="Pergunta 1. Ramifica para PJ / PF / PROCESSO. NÃO confundir com a "
                   "pergunta 34, que também se chama 'Tipo de cadastro' — a desambiguação "
                   "é pelo VALOR da resposta (ver classificar_tipo_cadastro).",
    ),
)


# ─────────────────── Seção 2 — PESSOA JURÍDICA (Q2–Q11) ───────────────────

PESSOA_JURIDICA_FIELDS = ENTIDADE_FIELDS + (
    CampoForms(campo="cnpj", pergunta="CNPJ", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="grupos", pergunta="Grupos", tipo_resposta="opcao_unica", opcoes=GRUPOS),
    CampoForms(campo="endereco_alternativo", pergunta="Endereço alternativo",
               tipo_resposta="texto", observacao="Subtítulo: Residencial e/ou Comercial."),
    CampoForms(campo="telefone", pergunta="Contato telefônico",
               aliases=("contato telefonico",), tipo_resposta="texto",
               observacao="Subtítulo: Residencial, pessoal, comercial e/ou celular."),
    CampoForms(campo="email", pergunta="Endereço eletrônico", tipo_resposta="texto"),
    CampoForms(campo="data_fundacao", pergunta="Data da fundação", tipo_resposta="data"),
    CampoForms(campo="grupo_empresarial", pergunta="Grupo empresarial", tipo_resposta="texto"),
    CampoForms(campo="origem_prospeccao", pergunta="Origem da prospecção", tipo_resposta="texto"),
    CampoForms(campo="categoria_cliente", pergunta="Categoria de cliente", tipo_resposta="texto"),
    CampoForms(campo="rede_social", pergunta="Rede social", tipo_resposta="texto"),
)


# ──────────────────── Seção 3 — PESSOA FÍSICA (Q12–Q33) ────────────────────

PESSOA_FISICA_FIELDS = ENTIDADE_FIELDS + (
    CampoForms(campo="nome", pergunta="Nome", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="titulo_eleitor", pergunta="Título de eleitor", tipo_resposta="texto"),
    CampoForms(campo="cpf", pergunta="CPF", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="data_nascimento", pergunta="Data de nascimento", tipo_resposta="data"),
    CampoForms(campo="sexo", pergunta="Sexo", obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("Feminino", "Masculino")),
    CampoForms(campo="ctps", pergunta="N° da CTPS", aliases=("no da ctps", "n da ctps", "ctps"),
               tipo_resposta="texto"),
    CampoForms(campo="profissao", pergunta="Profissão", tipo_resposta="texto"),
    CampoForms(campo="identidade_profissional", pergunta="Identidade profissional",
               tipo_resposta="texto"),
    CampoForms(campo="nit_pis_pasep", pergunta="NIT/PIS/PASEP", tipo_resposta="texto"),
    CampoForms(campo="rg", pergunta="RG", tipo_resposta="texto"),
    CampoForms(campo="grupos", pergunta="Grupos", obrigatorio=True,
               tipo_resposta="opcao_multipla", opcoes=GRUPOS),
    CampoForms(campo="classificacoes", pergunta="Classificações", tipo_resposta="opcao_unica",
               opcoes=("Ativo", "Inativo", "Outra")),
    CampoForms(campo="telefone", pergunta="Contato Telefônico",
               aliases=("contato telefonico",), tipo_resposta="texto"),
    CampoForms(campo="email", pergunta="Endereço Eletrônico", tipo_resposta="texto"),
    CampoForms(campo="endereco_alternativo", pergunta="Endereço Alternativo",
               tipo_resposta="texto"),
    CampoForms(campo="data_admissao", pergunta="Data de admissão", tipo_resposta="data"),
    CampoForms(campo="data_desligamento", pergunta="Data de desligamento", tipo_resposta="data"),
    CampoForms(campo="responsavel_prospeccao", pergunta="Responsável pela prospecção",
               tipo_resposta="texto"),
    CampoForms(campo="origem_prospeccao", pergunta="Origem da prospecção", tipo_resposta="texto"),
    CampoForms(campo="empresa_vinculo", pergunta="Empresa que a pessoa possui vínculo",
               tipo_resposta="texto"),
    CampoForms(campo="categoria_cliente", pergunta="Categoria de cliente", tipo_resposta="texto"),
    CampoForms(campo="rede_social", pergunta="Rede social", tipo_resposta="texto"),
)


# ───────────── Seção 4 — PROCESSO: escolhe o tipo de cadastro (Q34) ─────────────

TIPO_CADASTRO_FIELD = CampoForms(
    campo="tipo_cadastro",
    pergunta="Tipo de cadastro",
    obrigatorio=True,
    tipo_resposta="opcao_unica",
    opcoes=("Cadastro inicial", "Decisões", "Recurso", "Arquivamento", "Incidente"),
    observacao="Pergunta 34. 'Recurso' está gravado com espaço inicial na definição do Forms.",
)


# Bloco comum a CADASTRO INICIAL (Q35–78) e INCIDENTE (Q79–119).
# As duas seções perguntam exatamente as mesmas coisas, com duas diferenças:
# a lista de "Ação" e a lista de "Tipo de vínculo" (tratadas separadamente abaixo),
# e "Contrato"/"Sistema do processo eletrônico"/"Fase Processual (2ª vez)" que só
# existem no cadastro inicial.
_PROCESSO_COMUM = (
    CampoForms(campo="cliente", pergunta="Nome do cliente",
               aliases=("cliente principal", "cliente"), obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="contrato_honorarios", pergunta="Negociação do contrato de honorários",
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="tipo_processo", pergunta="Tipo", aliases=("tipo de procedimento",),
               obrigatorio=True, tipo_resposta="opcao_unica", opcoes=TIPOS_PROCESSO),
    CampoForms(campo="cnj", pergunta="Número do processo",
               aliases=("numero do processo", "numero cnj", "numero de cnj"),
               obrigatorio=True, tipo_resposta="texto",
               observacao="Subtítulo: CNJ de preferência. Se for outro número indicar o tipo "
                          "- AI, BO, Ofício, Ordem ou TRT antigo."),
    CampoForms(campo="procedimento", pergunta="Procedimento", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=PROCEDIMENTOS),
    CampoForms(campo="natureza", pergunta="Natureza", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=NATUREZAS),
    CampoForms(campo="fase", pergunta="Fase Processual", aliases=("fase",), obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=FASES),
    CampoForms(campo="cidade_comarca", pergunta="Cidade/Comarca", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="pesquisa_rtonline", pergunta="Pesquisa RTOnline", tipo_resposta="texto",
               observacao="Subtítulo: Objeto/mérito da ação para pesquisas."),
    CampoForms(campo="posicao", pergunta="Posição nos autos do Cliente Principal",
               aliases=("posicao cliente principal", "posicao"), obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="contrario", pergunta="Contrário principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="advogado", pergunta="Advogado responsável pelo processo",
               aliases=("advogado responsavel",), obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="magistrado", pergunta="Magistrado", obrigatorio=True, tipo_resposta="texto",
               observacao="Subtítulo: Juiz ou Desembargador Relator."),
    CampoForms(campo="outros_envolvidos",
               pergunta="Outros envolvidos (se houver) e sua posição nos autos",
               tipo_resposta="texto_multilinha"),
    CampoForms(campo="vinculo", pergunta="Vínculo", tipo_resposta="texto"),
    CampoForms(campo="objeto_processo", pergunta="Objeto do processo", obrigatorio=True,
               tipo_resposta="texto_multilinha",
               observacao="Subtítulo: Não se trata da Ação, tipo de procedimento e/ou pedido "
                          "– indicar a matéria."),
    CampoForms(campo="pedidos", pergunta="Pedidos e objetos dos pedidos", obrigatorio=True,
               tipo_resposta="texto_multilinha",
               observacao="No cível é TEXTO LIVRE, diferente do trabalhista (múltipla escolha)."),
    CampoForms(campo="classificacao_pedidos",
               pergunta="Classificação de cada pedido ( Probabilidade atual de êxito ou perda "
                        "- remota, possível, provável) e os valores de provisão para cada "
                        "pedido (remota, possível, provável)",
               aliases=("classificacao de cada pedido",),
               obrigatorio=True, tipo_resposta="texto_multilinha"),
    CampoForms(campo="valor_causa", pergunta="Valor da causa", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="centro_custo", pergunta="Centro de custo", obrigatorio=True,
               tipo_resposta="opcao_multipla", opcoes=CENTROS_CUSTO),
    CampoForms(campo="contingencia", pergunta="Contigência", aliases=("contingencia",),
               obrigatorio=True, tipo_resposta="opcao_unica", opcoes=("Ativa", "Passiva"),
               observacao="Grafia do formulário é 'Contigência' (sem o 'n')."),
    CampoForms(campo="risco", pergunta="Risco do processo", aliases=("risco",), obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=("Médio", "Alto", "Baixo")),
    CampoForms(campo="probabilidade", pergunta="Probabilidade atual", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=("Êxito", "Perda")),
    CampoForms(campo="grau_probabilidade", pergunta="Faixa de probabilidade atual",
               obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("Provável", "Possível", "Remota")),
    CampoForms(campo="observacoes", pergunta="Observações", tipo_resposta="texto_multilinha"),
    CampoForms(campo="supermercado_loja", pergunta="Supermercado Loja", tipo_resposta="texto"),
    CampoForms(campo="centro_custo_cliente", pergunta="Centro de custo do cliente",
               tipo_resposta="texto"),
    CampoForms(campo="numero_cliente", pergunta="N° do cliente",
               aliases=("no do cliente", "n do cliente"), tipo_resposta="texto"),
    CampoForms(campo="residencial", pergunta="Residencial", tipo_resposta="texto"),
    CampoForms(campo="obra", pergunta="Obra", tipo_resposta="texto"),
    CampoForms(campo="data_citacao", pergunta="Data da citação", tipo_resposta="data"),
    CampoForms(campo="prescricao_bienal", pergunta="Prescrição Bienal", tipo_resposta="texto"),
    CampoForms(campo="prescricao_quinquenal", pergunta="Prescrição quinquenal",
               tipo_resposta="texto"),
    CampoForms(campo="cobranca_honorarios_sucumbenciais",
               pergunta="Cobrança de Honorários de Sucumbenciais?",
               aliases=("cobranca de honorarios sucumbenciais",), tipo_resposta="texto",
               observacao="Subtítulo: Incluir justificativa. Aqui é texto livre; nas seções "
                          "DECISÕES/ARQUIVAMENTO a mesma pergunta é Sim/Não."),
    CampoForms(campo="honorarios_exito", pergunta="Honorários de êxito", tipo_resposta="texto"),
    CampoForms(campo="dividas_nao_tributarias", pergunta="Dívidas não tributárias",
               tipo_resposta="texto"),
    CampoForms(campo="data_pagamento", pergunta="Data do pagamento", tipo_resposta="data"),
    CampoForms(campo="valor_adicional_provisao", pergunta="Valor adicional de provisão",
               tipo_resposta="texto"),
)


# ──────────────── Seção 5 — CADASTRO INICIAL (Q35–Q78) ────────────────

CADASTRO_INICIAL_FIELDS = (TIPO_CADASTRO_FIELD,) + _PROCESSO_COMUM + (
    CampoForms(campo="contrato_arquivo", pergunta="Contrato", tipo_resposta="upload",
               observacao="Até 10 arquivos, 1 GB cada; Word/Excel/PPT/PDF/Imagem/Vídeo/Áudio."),
    CampoForms(campo="sistema_eletronico", pergunta="Sistema do processo eletrônico",
               tipo_resposta="texto"),
    CampoForms(campo="acao", pergunta="Ação", obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=ACOES_CADASTRO_INICIAL),
    CampoForms(campo="tipo_vinculo", pergunta="Tipo de vínculo", tipo_resposta="opcao_unica",
               opcoes=TIPOS_VINCULO_CADASTRO_INICIAL),
)


# ─────────────────── Seção 6 — INCIDENTE (Q79–Q119) ───────────────────

INCIDENTE_FIELDS = (TIPO_CADASTRO_FIELD,) + _PROCESSO_COMUM + (
    CampoForms(campo="acao", pergunta="Ação", obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=ACOES_INCIDENTE),
    CampoForms(campo="tipo_vinculo", pergunta="Tipo de vínculo", tipo_resposta="opcao_unica",
               opcoes=TIPOS_VINCULO_INCIDENTE),
)


# Bloco comum a DECISÕES (Q120–146) e ARQUIVAMENTO (Q169–190).
# Divergem em: domínio de `motivo`, obrigatoriedade, `data_arquivamento` e o
# bloco de contingência/risco (só em DECISÕES).
_RESULTADO_COMUM = (
    CampoForms(campo="cnj", pergunta="Número CNJ", aliases=("numero cnj", "numero de cnj"),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="cliente", pergunta="Cliente principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="contrario", pergunta="Contrário principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="instancia", pergunta="Instância", tipo_resposta="opcao_unica",
               opcoes=("1ª instância", "2ª instância", "Outra")),
    CampoForms(campo="situacao_pedido", pergunta="Situação do pedido",
               tipo_resposta="opcao_unica", opcoes=SITUACOES_PEDIDO),
    CampoForms(campo="valor_deferido", pergunta="Valor deferido", tipo_resposta="texto"),
    CampoForms(campo="valor_acordo_condenacao", pergunta="Valor do acordo/condenção",
               aliases=("valor do acordo/condenacao", "valor do acordo condenacao"),
               tipo_resposta="texto",
               observacao="Grafia do formulário: 'condenção'."),
    CampoForms(campo="valor_honorarios", pergunta="Valor de honorários", tipo_resposta="texto"),
    CampoForms(campo="valor_custas", pergunta="Valor custas", tipo_resposta="texto"),
    CampoForms(campo="custas", pergunta="Custas", tipo_resposta="opcao_unica", opcoes=CUSTAS),
    CampoForms(campo="tipo_resultado", pergunta="Tipo de resultado", tipo_resposta="opcao_unica",
               opcoes=TIPOS_RESULTADO),
    CampoForms(campo="resultado", pergunta="Resultado", tipo_resposta="opcao_unica",
               opcoes=RESULTADOS),
    CampoForms(campo="motivo_resultado", pergunta="Motivo do resultado",
               tipo_resposta="texto_multilinha"),
    CampoForms(campo="data_resultado", pergunta="Data do resultado", tipo_resposta="data"),
    CampoForms(campo="data_sentenca", pergunta="Data da sentença", tipo_resposta="data"),
    CampoForms(campo="cobranca_honorarios_sucumbenciais",
               pergunta="Cobrança de honorários sucumbenciais?", tipo_resposta="opcao_unica",
               opcoes=("Sim", "Não")),
    CampoForms(campo="justificativa_nao_cobranca_honorarios_sucumbenciais",
               pergunta="Justifique a não cobrança de honorários sucumbenciais",
               tipo_resposta="opcao_unica", opcoes=("Sem previsão legal", "Outra"),
               observacao="Domínio de uma opção só + Outra — confirmar com a área se falta "
                          "opção cadastrada (item 2 dos NÃO CONFIRMADOS)."),
    CampoForms(campo="cobranca_honorarios_contratuais_exito",
               pergunta="Cobrança de honorários contratuais de êxito?",
               tipo_resposta="opcao_unica", opcoes=("Sim", "Não")),
    CampoForms(campo="justificativa_nao_cobranca_honorarios_contratuais",
               pergunta="Justifique a não cobrança de honorários contratuais de êxito",
               tipo_resposta="opcao_unica", opcoes=("Sem previsão contratual", "Outra"),
               observacao="Mesmo caso do campo acima."),
    CampoForms(campo="observacoes", pergunta="Observações", tipo_resposta="texto_multilinha"),
)


# ─────────────────── Seção 7 — DECISÕES (Q120–Q146) ───────────────────

DECISOES_FIELDS = (TIPO_CADASTRO_FIELD,) + _RESULTADO_COMUM + (
    CampoForms(campo="motivo", pergunta="Motivo", tipo_resposta="opcao_unica",
               opcoes=MOTIVOS_BASE + ("Provas produzidas pelo réu",
                                      "Provas produzidas pelo autor", "Outra"),
               observacao="No cível/DECISÕES as duas últimas opções são réu/autor. "
                          "Em ARQUIVAMENTO voltam a ser Empresa/RCTE."),
    CampoForms(campo="contingencia", pergunta="Contingência", tipo_resposta="opcao_unica",
               opcoes=("Ativa", "Passiva")),
    CampoForms(campo="probabilidade", pergunta="Probabilidade atual",
               tipo_resposta="opcao_unica", opcoes=("Êxito", "Perda")),
    CampoForms(campo="grau_probabilidade", pergunta="Faixa de probabilidade atual",
               tipo_resposta="opcao_unica", opcoes=("Provável", "Possível", "Remota")),
    CampoForms(campo="risco", pergunta="Risco", tipo_resposta="opcao_unica",
               opcoes=("Alto", "Médio", "Baixo")),
    CampoForms(campo="vinculo", pergunta="Vínculo (se houver - processo ou serviço)",
               aliases=("vinculo",), tipo_resposta="texto"),
    CampoForms(campo="tipo_vinculo", pergunta="Tipo de vínculo", tipo_resposta="opcao_unica",
               opcoes=TIPOS_VINCULO_RESULTADO),
)


# ─────────────────── Seção 8 — RECURSO (Q147–Q168) ───────────────────

RECURSO_FIELDS = (
    TIPO_CADASTRO_FIELD,
    CampoForms(campo="cnj", pergunta="Número de CNJ", aliases=("numero cnj", "numero de cnj"),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="numero_antigo", pergunta="Número antigo", tipo_resposta="texto"),
    CampoForms(campo="cliente", pergunta="Cliente principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="posicao", pergunta="Posição cliente principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="contrario", pergunta="Contrário principal", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="advogado", pergunta="Advogado responsável", obrigatorio=True,
               tipo_resposta="texto"),
    CampoForms(campo="data_distribuicao", pergunta="Data de distribuição do recurso",
               obrigatorio=True, tipo_resposta="data"),
    CampoForms(campo="tipo_processo", pergunta="Tipo de procedimento", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=TIPOS_PROCESSO),
    CampoForms(campo="tipo_classe_recurso", pergunta="Tipo de recurso", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=TIPOS_RECURSO),
    CampoForms(campo="vinculo", pergunta="Vínculo (se houver - processo ou serviço)",
               aliases=("vinculo",), tipo_resposta="texto"),
    CampoForms(campo="tipo_vinculo", pergunta="Tipo de vínculo", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=TIPOS_VINCULO_RESULTADO),
    CampoForms(campo="natureza", pergunta="Natureza", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=("Cível", "Trabalhista", "Tributário", "Outra"),
               observacao="Domínio reduzido; nas seções de processo são 10 naturezas."),
    CampoForms(campo="orgao", pergunta="Órgão", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="uf", pergunta="UF", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="cidade", pergunta="Cidade", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="comarca", pergunta="Comarca", obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="instancia", pergunta="Instância", obrigatorio=True,
               tipo_resposta="opcao_unica", opcoes=("1° Grau", "2º Grau", "STJ", "Outra"),
               observacao="Domínio diferente de DECISÕES/ARQUIVAMENTO (1ª/2ª instância)."),
    CampoForms(campo="numero_turma", pergunta="N° Turma", aliases=("no turma", "n turma"),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="nome_vara_turma", pergunta="Nome da vara/turma", tipo_resposta="texto"),
    CampoForms(campo="objetos_recurso", pergunta="Objeto do recurso", obrigatorio=True,
               tipo_resposta="texto_multilinha"),
    CampoForms(campo="classificacao_pedidos_recurso",
               pergunta="Classificação de cada pedido ( Probabilidade atual de êxito ou perda "
                        "- remota, possível, provável) e os valores de provisão para cada "
                        "pedido (remota, possível, provável)",
               aliases=("classificacao de cada pedido",),
               obrigatorio=True, tipo_resposta="texto_multilinha"),
    CampoForms(campo="observacoes", pergunta="Observações", tipo_resposta="texto_multilinha"),
)


# ───────────────── Seção 9 — ARQUIVAMENTO (Q169–Q190) ─────────────────
# Quase tudo obrigatório aqui, ao contrário de DECISÕES.

_ARQUIVAMENTO_OBRIGATORIOS = {
    "instancia", "situacao_pedido", "valor_deferido", "valor_acordo_condenacao",
    "custas", "valor_custas", "tipo_resultado", "resultado", "motivo_resultado",
    "data_resultado", "data_sentenca", "cobranca_honorarios_sucumbenciais",
    "justificativa_nao_cobranca_honorarios_sucumbenciais",
    "cobranca_honorarios_contratuais_exito",
    "justificativa_nao_cobranca_honorarios_contratuais",
}

ARQUIVAMENTO_FIELDS = (TIPO_CADASTRO_FIELD,) + tuple(
    CampoForms(
        campo=c.campo,
        pergunta=c.pergunta,
        aliases=c.aliases,
        obrigatorio=c.obrigatorio or c.campo in _ARQUIVAMENTO_OBRIGATORIOS,
        tipo_resposta=("texto_multilinha" if c.campo == "valor_deferido" else c.tipo_resposta),
        opcoes=c.opcoes,
        observacao=c.observacao,
    )
    for c in _RESULTADO_COMUM
) + (
    CampoForms(campo="motivo", pergunta="Motivo", obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=MOTIVOS_BASE + ("Provas produzidas pela Empresa",
                                      "Provas produzidas pelo RCTE", "Outra")),
    CampoForms(campo="data_arquivamento", pergunta="Data de arquivamento", obrigatorio=True,
               tipo_resposta="data"),
)


MAPEAMENTO_POR_SECAO: dict[str, tuple[CampoForms, ...]] = {
    "PESSOA JURIDICA": PESSOA_JURIDICA_FIELDS,
    "PESSOA FISICA": PESSOA_FISICA_FIELDS,
    "CADASTRO INICIAL": CADASTRO_INICIAL_FIELDS,
    "INCIDENTE": INCIDENTE_FIELDS,
    "DECISOES": DECISOES_FIELDS,
    "RECURSO": RECURSO_FIELDS,
    "ARQUIVAMENTO": ARQUIVAMENTO_FIELDS,
}


# ─────────────────────────── API ───────────────────────────


def detectar_entidade(valor: str | None) -> str | None:
    """Q1: pessoa jurídica / pessoa física / processo."""
    return ENTIDADE_ALIAS.get(normalizar_texto(valor).replace("_", " "))


def detectar_tipo_cadastro(valor: str | None) -> str | None:
    """Q34: cadastro inicial / decisões / recurso / arquivamento / incidente."""
    return TIPO_ALIAS.get(normalizar_texto(valor).replace("_", " "))


def classificar_tipo_cadastro(valores: list[str]) -> tuple[str | None, str | None]:
    """Desambigua as DUAS perguntas chamadas "Tipo de cadastro".

    O extrator devolve as respostas de Q1 e Q34 sob o mesmo título, então casar
    por posição erra. Como os dois domínios de opções são disjuntos, dá para
    classificar pelo próprio valor da resposta.

    Retorna (entidade, tipo_cadastro) — qualquer um pode ser None.
    """
    entidade = tipo_cadastro = None
    for valor in valores:
        entidade = detectar_entidade(valor) or entidade
        tipo_cadastro = detectar_tipo_cadastro(valor) or tipo_cadastro
    return entidade, tipo_cadastro


def secao_de(entidade: str | None, tipo_cadastro: str | None) -> str | None:
    """Aplica RAMIFICACOES: a seção cujos campos devem ser usados."""
    if entidade in ("PESSOA JURIDICA", "PESSOA FISICA"):
        return entidade
    if entidade == "PROCESSO" or entidade is None:
        return tipo_cadastro
    return None


def obter_regras_secao(secao: str | None) -> tuple[CampoForms, ...]:
    return MAPEAMENTO_POR_SECAO.get(secao or "", ENTIDADE_FIELDS)


def mapear_formulario(dados: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """Mapeia respostas do Forms cível para campos internos.

    Mesma assinatura de `forms_mapping.mapear_formulario`, mas resolve a
    ramificação (entidade → seção) antes de escolher as regras.
    """
    perguntas = _normalizar_entrada_perguntas(dados)
    indice = _indice_perguntas(perguntas)

    valores_tipo = _filtrar_valores(indice.get("tipo de cadastro") or [], indice)
    entidade, tipo_cadastro = classificar_tipo_cadastro(valores_tipo)
    # payload do Copilot pode mandar as chaves já como campo interno
    if entidade is None:
        entidade, _ = classificar_tipo_cadastro(indice.get("tipo_entidade") or [])
    if tipo_cadastro is None:
        _, tipo_cadastro = classificar_tipo_cadastro(indice.get("tipo_cadastro") or [])

    secao = secao_de(entidade, tipo_cadastro)
    regras = obter_regras_secao(secao)

    resultado: dict[str, Any] = {
        "tipo_entidade": entidade,
        "tipo_cadastro": tipo_cadastro,
        "secao": secao,
        "tipo_tarefa_identificada": TIPO_TAREFA_POR_CADASTRO.get(tipo_cadastro or "", "GENERICO"),
        "campos": {},
        "nao_mapeados": [],
        "faltando_obrigatorios": [],
    }

    for regra in regras:
        valor = _buscar_por_alias(indice, regra)
        if valor:
            resultado["campos"][regra.campo] = valor
        elif regra.obrigatorio:
            resultado["faltando_obrigatorios"].append(regra.campo)

    # tipo_entidade/tipo_cadastro vêm da ramificação, não do casamento por alias
    # (que pegaria a resposta errada das duas perguntas homônimas)
    if entidade:
        resultado["campos"]["tipo_entidade"] = entidade
    if tipo_cadastro:
        resultado["campos"]["tipo_cadastro"] = tipo_cadastro

    conhecidas = {normalizar_texto(r.pergunta) for r in regras}
    conhecidas.update(normalizar_texto(a) for r in regras for a in r.aliases)
    conhecidas.update(normalizar_texto(r.campo) for r in regras)
    conhecidas.add("tipo de cadastro")

    for item in perguntas:
        pergunta = str(item.get("pergunta") or "").strip()
        if pergunta and normalizar_texto(pergunta) not in conhecidas:
            resultado["nao_mapeados"].append(
                {
                    "pergunta": pergunta,
                    "resposta": item.get("resposta") or "",
                    "marcadas": item.get("marcadas") or [],
                    "opcoes": item.get("opcoes") or [],
                }
            )

    return resultado


def descrever_secao(secao: str | None) -> dict[str, Any]:
    regras = obter_regras_secao(secao)
    return {
        "secao": secao,
        "quantidade_campos": len(regras),
        "campos": [asdict(r) for r in regras],
    }


def _autoteste() -> None:
    # ramificação: entidade PJ/PF ignora tipo_cadastro
    assert secao_de("PESSOA JURIDICA", None) == "PESSOA JURIDICA"
    assert secao_de("PROCESSO", "DECISOES") == "DECISOES"
    assert secao_de(None, "RECURSO") == "RECURSO"

    # o "Recurso" com espaço inicial da definição do Forms
    assert detectar_tipo_cadastro(" Recurso") == "RECURSO"
    # domínios disjuntos: cada valor só casa com uma das duas perguntas
    assert detectar_entidade("Decisões") is None
    assert detectar_tipo_cadastro("Pessoa física") is None

    # a desambiguação das duas perguntas homônimas, em qualquer ordem
    assert classificar_tipo_cadastro(["Processo", "Decisões"]) == ("PROCESSO", "DECISOES")
    assert classificar_tipo_cadastro(["Decisões", "Processo"]) == ("PROCESSO", "DECISOES")
    assert classificar_tipo_cadastro(["Pessoa jurídica"]) == ("PESSOA JURIDICA", None)

    # ponta a ponta: payload com as duas perguntas "Tipo de cadastro"
    r = mapear_formulario({
        "perguntas_forms": [
            {"pergunta": "Tipo de cadastro", "resposta": "Processo"},
            {"pergunta": "Tipo de cadastro", "resposta": "Decisões"},
            {"pergunta": "Número CNJ", "resposta": "1234567-89.2025.8.13.0024"},
            {"pergunta": "Cliente principal", "resposta": "MVC"},
            {"pergunta": "Contrário principal", "resposta": "Fulano"},
            {"pergunta": "Motivo", "resposta": "Provas produzidas pelo autor"},
        ]
    })
    assert r["secao"] == "DECISOES", r["secao"]
    assert r["campos"]["tipo_entidade"] == "PROCESSO"
    assert r["campos"]["tipo_cadastro"] == "DECISOES"
    assert r["campos"]["cnj"] == "1234567-89.2025.8.13.0024"
    assert r["faltando_obrigatorios"] == [], r["faltando_obrigatorios"]

    # cadastro de parte não exige nada de processo
    pj = mapear_formulario({
        "perguntas_forms": [
            {"pergunta": "Tipo de cadastro", "resposta": "Pessoa jurídica"},
            {"pergunta": "CNPJ", "resposta": "12.345.678/0001-90"},
        ]
    })
    assert pj["secao"] == "PESSOA JURIDICA"
    assert pj["campos"]["cnpj"] == "12.345.678/0001-90"

    # arquivamento endurece obrigatoriedade que em decisões é opcional
    opcional = {c.campo for c in DECISOES_FIELDS if not c.obrigatorio}
    obrigatorio = {c.campo for c in ARQUIVAMENTO_FIELDS if c.obrigatorio}
    assert "situacao_pedido" in opcional and "situacao_pedido" in obrigatorio

    # cada ramificação aponta para seções que existem
    nomes = {s.nome for s in SECOES}
    for ram in RAMIFICACOES:
        assert set(ram.destinos.values()) <= nomes, ram

    print("ok — forms_mapping_civel")


if __name__ == "__main__":
    _autoteste()
