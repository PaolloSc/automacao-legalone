"""
Mapeamento separado do Microsoft Forms por tipo de cadastro.

Objetivo:
- centralizar as perguntas esperadas de cada tipo de cadastro;
- permitir mapear `perguntas_forms` / `outros_dados` para campos internos;
- deixar pronto o esqueleto dos tipos ainda não detalhados.

Status atual:
- DECISÕES: mapeado com base nas perguntas informadas pelo usuário.
- RECURSO / ARQUIVAMENTO COMPLETO / ARQUIVAMENTO SIMPLES: mapeados a partir
    dos links pré-preenchidos coletados.
- CADASTRO INICIAL: estrutura criada, aguardando perguntas finais.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable
import re
import unicodedata


TIPOS_CADASTRO_SUPORTADOS = (
    "CADASTRO INICIAL",
    "DECISOES",
    "RECURSO",
    "ARQUIVAMENTO COMPLETO",
    "ARQUIVAMENTO SIMPLES",
)


TIPO_TAREFA_POR_CADASTRO = {
    "CADASTRO INICIAL": "CADASTRO_INICIAL",
    "DECISOES": "DECISAO",
    "RECURSO": "RECURSO",
    "ARQUIVAMENTO COMPLETO": "ARQUIVAMENTO",
    "ARQUIVAMENTO SIMPLES": "ARQUIVAMENTO",
}


TIPO_ALIAS = {
    "cadastro inicial": "CADASTRO INICIAL",
    "cadastro_inicial": "CADASTRO INICIAL",
    "decisao": "DECISOES",
    "decisoes": "DECISOES",
    "decisões": "DECISOES",
    "decisoes_": "DECISOES",
    "recurso": "RECURSO",
    "arquivamento completo": "ARQUIVAMENTO COMPLETO",
    "arquivamento_completo": "ARQUIVAMENTO COMPLETO",
    "arquivamento simples": "ARQUIVAMENTO SIMPLES",
    "arquivamento_simples": "ARQUIVAMENTO SIMPLES",
}


@dataclass(frozen=True)
class CampoForms:
    campo: str
    pergunta: str
    aliases: tuple[str, ...] = ()
    obrigatorio: bool = False
    tipo_resposta: str = "texto"
    opcoes: tuple[str, ...] = ()
    observacao: str = ""


COMMON_FIELDS = (
    CampoForms(
        campo="tipo_cadastro",
        pergunta="Tipo de cadastro",
        aliases=("1.tipo de cadastro",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=(
            "Cadastro inicial",
            "Decisões",
            "Recurso",
            "Arquivamento completo",
            "Arquivamento simples",
        ),
    ),
    CampoForms(
        campo="cnj",
        pergunta="Número CNJ",
        aliases=("numero cnj", "número cnj", "2.número cnj", "numero de cnj", "número de cnj", "numero do processo", "número do processo"),
        obrigatorio=True,
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="cliente",
        pergunta="Cliente principal",
        aliases=("cliente", "3.cliente principal"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="contrario",
        pergunta="Contrário principal",
        aliases=("contrario principal", "contrário principal", "4.contrário principal", "5.contrário principal"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="instancia",
        pergunta="Instância",
        aliases=("instancia", "5.instância", "12.instância"),
        tipo_resposta="opcao_unica",
        opcoes=("1ª instância", "2ª instância", "TST", "1º grau", "2º grau"),
    ),
    CampoForms(
        campo="fase",
        pergunta="Fase",
        aliases=("4.fase", "6.fase", "7.fase", "13.fase"),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="contingencia",
        pergunta="Contingência",
        aliases=("27.contingência",),
        tipo_resposta="opcao_unica",
        opcoes=("Ativa", "Passiva"),
    ),
    CampoForms(
        campo="probabilidade",
        pergunta="Probabilidade atual",
        aliases=("28.probabilidade atual",),
        tipo_resposta="opcao_unica",
        opcoes=("Êxito", "Perda"),
    ),
    CampoForms(
        campo="grau_probabilidade",
        pergunta="Faixa de probabilidade atual",
        aliases=("29.faixa de probabilidade atual", "grau de probabilidade atual", "grau probabilidade"),
        tipo_resposta="opcao_unica",
        opcoes=("Provável", "Possível", "Remota"),
    ),
    CampoForms(
        campo="risco",
        pergunta="Risco",
        aliases=("30.risco",),
        tipo_resposta="opcao_unica",
        opcoes=("Alto", "Médio", "Baixo"),
    ),
    # ── Campos comuns a todos os tipos (extraídos pelo extrator para CADASTRO INICIAL
    # mas precisam estar no mapping para DECISOES, RECURSO e ARQUIVAMENTO) ──────────
    CampoForms(
        campo="contrato_honorarios",
        pergunta="Contrato de honorários",
        aliases=("contrato de honorarios",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="incluir_relatorio",
        pergunta="Incluir no relatório do LegalOne de horas trabalhadas?",
        aliases=("incluir no relatorio do legalone de horas trabalhadas", "incluir no relatorio", "incluir relatorio"),
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="funcao_rcte",
        pergunta="Função exercida pelo RCTE",
        aliases=("funcao exercida pelo rcte", "3.função exercida pelo rcte"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="outros_envolvidos",
        pergunta="Outros envolvidos e posição nos autos",
        aliases=("outros envolvidos e posicao nos autos", "outros envolvidos"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="advogado",
        pergunta="Advogado responsável",
        aliases=("advogado responsavel", "5.advogado responsável"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="procedimento",
        pergunta="Procedimento",
        aliases=("6.procedimento", "7.procedimento", "8.procedimento"),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="cidade_comarca",
        pergunta="Cidade/Comarca",
        aliases=("cidade/comarca", "7.cidade/comarca", "8.cidade/comarca", "9.cidade/comarca"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="valor_causa",
        pergunta="Valor da causa",
        aliases=("valor da causa", "9.valor da causa", "10.valor da causa"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="objetos",
        pergunta="Objetos",
        aliases=("10.objetos", "11.objetos"),
        tipo_resposta="opcao_unica",
        opcoes=("Contrato de trabalho", "Outra"),
    ),
    CampoForms(
        campo="data_distribuicao",
        pergunta="Data de distribuição",
        aliases=("data de distribuicao", "data dos pedidos", "11.data de distribuição", "12.data de distribuição"),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="pedidos",
        pergunta="Pedidos",
        aliases=("12.pedidos", "13.pedidos", "22.pedidos"),
        tipo_resposta="opcao_multipla",
        observacao="Campo de múltipla escolha — armazenado como lista.",
    ),
    CampoForms(
        campo="vinculo_trabalhista",
        pergunta="Há pedido de vínculo trabalhista?",
        aliases=("ha pedido de vinculo trabalhista", "23.há pedido de vínculo trabalhista?", "vinculo trabalhista"),
        tipo_resposta="opcao_unica",
        opcoes=("Não", "Outra"),
    ),
    CampoForms(
        campo="descricao_pedidos",
        pergunta="Descreva todos os pedidos com as respectivas informações: pedido, valor, probabilidade atual (êxito ou perda - possível, provável, remota)",
        aliases=(
            "descreva todos os pedidos com as respectivas informacoes",
            "descreva todos os pedidos",
            "24.descreva todos os pedidos",
        ),
        tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="responsabilidade",
        pergunta="Responsabilidade",
        aliases=("responsabilidade",),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="data_julgamento",
        pergunta="Data do julgamento",
        aliases=("data do julgamento",),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="data_citacao",
        pergunta="Data da citação",
        aliases=("data da citacao",),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="redirecionamento",
        pergunta="Redirecionamento da execução",
        aliases=("redirecionamento da execucao", "redirecionamento"),
        tipo_resposta="texto",
    ),
)


DECISOES_FIELDS = (
    CampoForms(
        campo="situacao_pedido",
        pergunta="Situação do pedido",
        aliases=("6.situação do pedido", "situacao do pedido"),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Deferido", "Extinto", "Indeferido", "Parcialmente deferido", "Suspenso", "Acordo", "Outra"),
    ),
    CampoForms(
        campo="valor_total_deferido",
        pergunta="Valor total deferido",
        aliases=("8.valor total deferido",),
        obrigatorio=True,
    ),
    CampoForms(
        campo="valor_deferido_por_pedido",
        pergunta="Valor deferido para cada pedido",
        aliases=("9.valor deferido para cada pedido",),
        obrigatorio=True,
        tipo_resposta="texto_multilinha",
        observacao="Em caso de acordo, discriminar parcelas.",
    ),
    CampoForms(
        campo="terceirizacao_1",
        pergunta="Terceirização",
        aliases=("10.terceirização",),
        tipo_resposta="opcao_unica",
        observacao="Primeira ocorrência da pergunta Terceirização.",
    ),
    CampoForms(
        campo="terceirizacao_2",
        pergunta="Terceirização",
        aliases=("11.terceirização",),
        tipo_resposta="opcao_unica",
        observacao="Segunda ocorrência da pergunta Terceirização.",
    ),
    CampoForms(
        campo="pejotizacao",
        pergunta="Pejotização",
        aliases=("12.pejotização", "pejotizacao"),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="motivo",
        pergunta="Motivo",
        aliases=("13.motivo",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=(
            "Ausência de concreta fundamentação",
            "Ausência de provas",
            "Danos constatados",
            "Falta de documentos",
            "Precedentes jurisprudenciais",
            "Provas produzidas pela Empresa",
            "Provas produzidas pelo RCTE",
            "Outra",
        ),
    ),
    CampoForms(
        campo="valor_acordo_condenacao",
        pergunta="Valor do acordo/condenção",
        aliases=("valor do acordo/condenção", "valor do acordo/condenacao", "14.valor do acordo/condenção"),
        obrigatorio=True,
    ),
    CampoForms(
        campo="valor_honorarios",
        pergunta="Valor de honorários",
        aliases=("15.valor de honorários", "valor de honorarios"),
        obrigatorio=True,
    ),
    CampoForms(
        campo="valor_custas",
        pergunta="Valor custas",
        aliases=("16.valor custas",),
        obrigatorio=True,
    ),
    CampoForms(
        campo="custas",
        pergunta="Custas",
        aliases=("17.custas",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Favorável", "Desfavorável", "Sem posição"),
    ),
    CampoForms(
        campo="tipo_resultado",
        pergunta="Tipo de resultado",
        aliases=("18.tipo de resultado",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Acórdão", "Acordo", "Decisão", "Sentença", "Outra"),
    ),
    CampoForms(
        campo="resultado",
        pergunta="Resultado",
        aliases=("19.resultado",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Êxito total", "Acordo", "Êxito Parcial", "Extinto", "Perda", "Outra"),
    ),
    CampoForms(
        campo="motivo_resultado",
        pergunta="Motivo do resultado",
        aliases=("20.motivo do resultado",),
        obrigatorio=True,
        tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="data_resultado",
        pergunta="Data do resultado",
        aliases=("21.data do resultado",),
        obrigatorio=True,
        tipo_resposta="data",
    ),
    CampoForms(
        campo="data_sentenca",
        pergunta="Data da sentença",
        aliases=("22.data da sentença", "22.data da sentenca"),
        obrigatorio=True,
        tipo_resposta="data",
    ),
    CampoForms(
        campo="cobranca_honorarios_sucumbenciais",
        pergunta="Cobrança de honorários sucumbenciais?",
        aliases=("23.cobrança de honorários sucumbenciais?", "23.cobranca de honorarios sucumbenciais?"),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="justificativa_nao_cobranca_honorarios_sucumbenciais",
        pergunta="Justifique a não cobrança de honorários sucumbenciais",
        aliases=(
            "24.justifique a não cobrança de honorários sucumbenciais",
            "24.justifique a nao cobranca de honorarios sucumbenciais",
        ),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Sem previsão legal", "Prejudicado - vide pergunta anterior", "Reclamante beneficiário da Justiça Gratuita", "Outra"),
    ),
    CampoForms(
        campo="cobranca_honorarios_contratuais_exito",
        pergunta="Cobrança de honorários contratuais de êxito?",
        aliases=(
            "25.cobrança de honorários contratuais de êxito?",
            "25.cobranca de honorarios contratuais de exito?",
        ),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="justificativa_nao_cobranca_honorarios_contratuais",
        pergunta="Justifique a não cobrança de honorários contratuais de êxito",
        aliases=(
            "26.justifique a não cobrança de honorários contratuais de êxito",
            "26.justifique a nao cobranca de honorarios contratuais de exito",
        ),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Sem previsão contratual", "Prejudicado - vide resposta anterior", "Outra"),
    ),
    CampoForms(
        campo="houve_interposicao_recurso",
        pergunta="Houve a interposição de recurso? Se sim, qual?",
        aliases=(
            "31.houve a interposição de recurso? se sim, qual?",
            "31.houve a interposicao de recurso? se sim, qual?",
        ),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Não", "Outra"),
    ),
    CampoForms(
        campo="parte_recorrente",
        pergunta="Parte recorrente",
        aliases=("32.parte recorrente",),
        tipo_resposta="opcao_unica",
    ),
)


CADASTRO_INICIAL_FIELDS: tuple[CampoForms, ...] = ()
RECURSO_FIELDS = (
    CampoForms(
        campo="posicao",
        pergunta="Posição cliente principal",
        aliases=("4.posição cliente principal", "4.posicao cliente principal"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="data_distribuicao",
        pergunta="Data de distribuição do recurso",
        aliases=("6.data de distribuição do recurso", "6.data de distribuicao do recurso"),
        obrigatorio=True,
        tipo_resposta="data",
    ),
    CampoForms(
        campo="tipo_classe_recurso",
        pergunta="Tipo/classe de recurso",
        aliases=("7.tipo/classe de recurso",),
        obrigatorio=True,
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="orgao",
        pergunta="Órgão",
        aliases=("8.órgão", "8.orgão", "8.orgao"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="uf",
        pergunta="UF",
        aliases=("9.uf",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="cidade",
        pergunta="Cidade",
        aliases=("10.cidade",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="comarca",
        pergunta="Comarca",
        aliases=("11.comarca",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="numero_turma",
        pergunta="Nº Turma",
        aliases=("14.nº turma", "14.no turma", "14.num turma"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="objetos_recurso",
        pergunta="Objetos do recurso",
        aliases=("15.objetos do recurso",),
        tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="valor_causa",
        pergunta="Valor",
        aliases=("16.valor",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="classificacao_pedidos_recurso",
        pergunta="Classificação de cada pedido ( Probabilidade atual de êxito ou perda - remota, possível, provável) e os valores de provisão para cada pedido (remota, possível, provável)",
        aliases=("17.classificação de cada pedido", "17.classificacao de cada pedido"),
        tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="datacloud_configurado",
        pergunta="Cadastrar no DataCloud?",
        aliases=("18.cadastrar no datacloud?",),
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="observacoes",
        pergunta="Observações",
        aliases=("19.observações", "19.observacoes"),
        tipo_resposta="texto_multilinha",
    ),
)

ARQUIVAMENTO_COMPLETO_FIELDS = (
    CampoForms(
        campo="situacao_pedido",
        pergunta="Situação do pedido",
        aliases=("7.situação do pedido", "7.situacao do pedido"),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Deferido", "Extinto", "Indeferido", "Parcialmente deferido", "Suspenso", "Acordo", "Outra"),
    ),
    CampoForms(
        campo="valor_deferido_por_pedido",
        pergunta="Valor de cada pedido deferido",
        aliases=("8.valor de cada pedido deferido",),
        tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="motivo",
        pergunta="Motivo",
        aliases=("9.motivo",),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="valor_acordo_condenacao",
        pergunta="Valor total do acordo/condenção",
        aliases=("10.valor total do acordo/condenção", "10.valor total do acordo/condenacao"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="valor_honorarios",
        pergunta="Valor de honorários",
        aliases=("11.valor de honorários", "11.valor de honorarios"),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="custas",
        pergunta="Custas",
        aliases=("12.custas",),
        tipo_resposta="opcao_unica",
        opcoes=("Favorável", "Desfavorável", "Sem posição"),
    ),
    CampoForms(
        campo="valor_custas",
        pergunta="Valor custas",
        aliases=("13.valor custas",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="tipo_resultado",
        pergunta="Tipo de resultado",
        aliases=("14.tipo de resultado",),
        tipo_resposta="opcao_unica",
        opcoes=("Acórdão", "Acordo", "Decisão", "Sentença", "Outra"),
    ),
    CampoForms(
        campo="resultado",
        pergunta="Resultado",
        aliases=("15.resultado",),
        tipo_resposta="opcao_unica",
        opcoes=("Êxito total", "Acordo", "Êxito Parcial", "Extinto", "Perda", "Outra"),
    ),
    CampoForms(
        campo="motivo_resultado",
        pergunta="Motivo do resultado",
        aliases=("16.motivo do resultado",),
        tipo_resposta="texto",
    ),
    CampoForms(
        campo="data_resultado",
        pergunta="Data do resultado",
        aliases=("17.data do resultado",),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="data_sentenca",
        pergunta="Data da sentença",
        aliases=("18.data da sentença", "18.data da sentenca"),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="data_arquivamento",
        pergunta="Data do arquivamento",
        aliases=("19.data do arquivamento",),
        tipo_resposta="data",
    ),
    CampoForms(
        campo="cobranca_honorarios_sucumbenciais",
        pergunta="Cobrança de honorários sucumbenciais?",
        aliases=("20.cobrança de honorários sucumbenciais?", "20.cobranca de honorarios sucumbenciais?"),
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="justificativa_nao_cobranca_honorarios_sucumbenciais",
        pergunta="Justifique a não cobrança de honorários sucumbenciais",
        aliases=("21.justifique a não cobrança de honorários sucumbenciais", "21.justifique a nao cobranca de honorarios sucumbenciais"),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="cobranca_honorarios_contratuais_exito",
        pergunta="Cobrança de honorários contratuais de êxito?",
        aliases=("22.cobrança de honorários contratuais de êxito?", "22.cobranca de honorarios contratuais de exito?"),
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="justificativa_nao_cobranca_honorarios_contratuais",
        pergunta="Justifique a não cobrança de honorários contratuais de êxito",
        aliases=("23.justifique a não cobrança de honorários contratuais de êxito", "23.justifique a nao cobranca de honorarios contratuais de exito"),
        tipo_resposta="opcao_unica",
    ),
    CampoForms(
        campo="comentario_adicional",
        pergunta="Comentário adicional",
        aliases=("24.comentário adicional", "24.comentario adicional"),
        tipo_resposta="texto_multilinha",
    ),
)

ARQUIVAMENTO_SIMPLES_FIELDS = (
    CampoForms(
        campo="data_arquivamento",
        pergunta="Data do arquivamento",
        aliases=("3.data do arquivamento",),
        obrigatorio=True,
        tipo_resposta="data",
    ),
    CampoForms(
        campo="honorarios_favor_escritorio",
        pergunta="Honorários em favor do escritório?",
        aliases=("5.honorários em favor do escritório?", "5.honorarios em favor do escritorio?"),
        tipo_resposta="opcao_unica",
        opcoes=("Sim", "Não"),
    ),
    CampoForms(
        campo="valor_honorarios_favor_escritorio",
        pergunta="Valor honorários em favor do escritório",
        aliases=("6.valor honorários em favor do escritório", "6.valor honorarios em favor do escritorio"),
        tipo_resposta="texto",
    ),
)


MAPEAMENTO_POR_TIPO = {
    "CADASTRO INICIAL": COMMON_FIELDS + CADASTRO_INICIAL_FIELDS,
    "DECISOES": COMMON_FIELDS + DECISOES_FIELDS,
    "RECURSO": COMMON_FIELDS + RECURSO_FIELDS,
    "ARQUIVAMENTO COMPLETO": COMMON_FIELDS + ARQUIVAMENTO_COMPLETO_FIELDS,
    "ARQUIVAMENTO SIMPLES": COMMON_FIELDS + ARQUIVAMENTO_SIMPLES_FIELDS,
}


def normalizar_texto(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().lower()


# Sufixos de metadados que o Forms injeta no texto da pergunta,
# ex.: "Fase Requer resposta. Opção única." → "fase"
_RE_METADATA_SUFIXO = re.compile(
    r"\s*\.?\s*(?:requer resposta\.?\s*)?"  # "Requer resposta." opcional
    r"(?:opcao unica|multipla escolha|texto de linha unica"
    r"|texto multilinha|texto longo|carregar arquivo|data|classificacao|numero)\b.*$",
    re.IGNORECASE,
)
_RE_METADATA_REQUER = re.compile(r"\s+requer resposta\b.*$", re.IGNORECASE)


def normalizar_pergunta(valor: Any) -> str:
    texto = normalizar_texto(valor)  # já remove acentos e normaliza espaços
    # Remove prefixo numérico ("1. ", "2) ", etc.)
    texto = re.sub(r"^\d+[\.)-]?\s*", "", texto)
    # Remove sufixos de metadados que o Forms às vezes cola no título
    # Ex.: "Fase Requer resposta. Opção única." → "Fase"
    texto = _RE_METADATA_REQUER.sub("", texto)
    texto = _RE_METADATA_SUFIXO.sub("", texto)
    return texto.strip()


def detectar_tipo_cadastro(valor: str | None) -> str | None:
    chave = normalizar_texto(valor).replace("_", " ")
    if not chave:
        return None
    return TIPO_ALIAS.get(chave)


def _normalizar_entrada_perguntas(dados: Any) -> list[dict[str, Any]]:
    if isinstance(dados, dict):
        itens: list[dict[str, Any]] = []
        if isinstance(dados.get("perguntas_forms"), list):
            itens.extend(item for item in dados["perguntas_forms"] if isinstance(item, dict))
        outros = dados.get("outros_dados") or {}
        if isinstance(outros, dict):
            itens.extend(
                {
                    "pergunta": pergunta,
                    "resposta": resposta,
                }
                for pergunta, resposta in outros.items()
                # normalizar_texto remove acentos, então usar formas sem acento
                if " - opcoes" not in normalizar_texto(pergunta)
                and " - marcadas" not in normalizar_texto(pergunta)
                and " - texto completo" not in normalizar_texto(pergunta)
                and "mapeamento forms -" not in normalizar_texto(pergunta)
            )
        return itens
    if isinstance(dados, list):
        return [item for item in dados if isinstance(item, dict)]
    return []


def _extrair_resposta(item: dict[str, Any]) -> str:
    resposta = item.get("resposta") or item.get("resposta_texto") or ""
    if resposta:
        return str(resposta).strip()
    marcadas = item.get("marcadas") or []
    if marcadas:
        return ", ".join(str(x).strip() for x in marcadas if str(x).strip())
    return ""


def _indice_perguntas(perguntas: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    indice: dict[str, list[str]] = {}
    for item in perguntas:
        pergunta = str(item.get("pergunta") or "").strip()
        if not pergunta:
            continue
        pergunta_norm = normalizar_texto(pergunta)
        pergunta_sem_numero = normalizar_pergunta(pergunta)
        resposta = _extrair_resposta(item)
        indice.setdefault(pergunta_norm, []).append(resposta)
        indice.setdefault(pergunta_sem_numero, []).append(resposta)
    return indice


def _buscar_por_alias(indice: dict[str, list[str]], campo: CampoForms) -> str | None:
    candidatos = (campo.pergunta, *campo.aliases)
    candidatos_norm = []
    for candidato in candidatos:
        if not candidato:
            continue
        candidatos_norm.append(normalizar_texto(candidato))
        candidatos_norm.append(normalizar_pergunta(candidato))
    candidatos_norm = [x for x in candidatos_norm if x]

    for candidato in candidatos_norm:
        valores = indice.get(candidato)
        if valores:
            unicos = _filtrar_valores(valores, indice)
            return unicos[0] if len(unicos) == 1 else " | ".join(unicos)

    for pergunta_norm, valores in indice.items():
        if any(candidato and candidato in pergunta_norm for candidato in candidatos_norm):
            unicos = _filtrar_valores(valores, indice)
            return unicos[0] if len(unicos) == 1 else " | ".join(unicos)

    return None


def _filtrar_valores(valores: list[str], indice: dict[str, list[str]]) -> list[str]:
    """Remove valores que são títulos de pergunta (ecoados pelo extrator)
    e deduplica preservando a ordem."""
    vistos: set[str] = set()
    resultado: list[str] = []
    for v in valores:
        if not v:
            continue
        v_norm = normalizar_texto(v)
        # Salta se for um título de pergunta (aparece como chave no índice)
        if v_norm in indice:
            continue
        if v_norm not in vistos:
            vistos.add(v_norm)
            resultado.append(v)
    # Fallback: se tudo foi filtrado, retorna os deduplicados originais
    if not resultado:
        for v in valores:
            if v and normalizar_texto(v) not in vistos:
                vistos.add(normalizar_texto(v))
                resultado.append(v)
    return resultado


def obter_regras_tipo(tipo_cadastro: str | None) -> tuple[CampoForms, ...]:
    tipo = detectar_tipo_cadastro(tipo_cadastro)
    if not tipo:
        return COMMON_FIELDS
    return MAPEAMENTO_POR_TIPO.get(tipo, COMMON_FIELDS)


def mapear_formulario(dados: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """Mapeia respostas do Forms para campos internos.

    Aceita:
    - payload completo com `perguntas_forms` e/ou `outros_dados`
    - lista de itens no formato `[{pergunta, resposta, marcadas, ...}]`
    """
    perguntas = _normalizar_entrada_perguntas(dados)
    indice = _indice_perguntas(perguntas)

    tipo_bruto = None
    for chave in ("tipo de cadastro", "1.tipo de cadastro"):
        valores_tipo = indice.get(chave) or []
        # Filtra títulos ecoados e prioriza o primeiro valor reconhecido
        for _v in _filtrar_valores(valores_tipo, indice):
            if detectar_tipo_cadastro(_v):
                tipo_bruto = _v
                break
        if tipo_bruto:
            break
        # Fallback: pega qualquer valor reconhecido antes da filtragem
        if not tipo_bruto:
            for _v in valores_tipo:
                if detectar_tipo_cadastro(_v):
                    tipo_bruto = _v
                    break
        if tipo_bruto:
            break
        if not tipo_bruto and valores_tipo:
            tipo_bruto = valores_tipo[0]

    tipo_cadastro = detectar_tipo_cadastro(tipo_bruto) or (str(tipo_bruto).strip().upper() if tipo_bruto else None)
    regras = obter_regras_tipo(tipo_cadastro)

    resultado: dict[str, Any] = {
        "tipo_cadastro": tipo_cadastro,
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

    campos_mapeados = set(resultado["campos"])
    for regra in regras:
        if regra.campo not in campos_mapeados and not regra.obrigatorio:
            continue

    perguntas_conhecidas = {
        normalizar_texto(regra.pergunta)
        for regra in regras
    }
    perguntas_conhecidas.update(normalizar_pergunta(regra.pergunta) for regra in regras)
    perguntas_conhecidas.update(normalizar_texto(alias) for regra in regras for alias in regra.aliases)
    perguntas_conhecidas.update(normalizar_pergunta(alias) for regra in regras for alias in regra.aliases)

    for item in perguntas:
        pergunta = str(item.get("pergunta") or "").strip()
        if not pergunta:
            continue
        pergunta_norm = normalizar_texto(pergunta)
        pergunta_sem_numero = normalizar_pergunta(pergunta)
        if pergunta_norm not in perguntas_conhecidas and pergunta_sem_numero not in perguntas_conhecidas:
            resultado["nao_mapeados"].append(
                {
                    "pergunta": pergunta,
                    "resposta": _extrair_resposta(item),
                    "marcadas": item.get("marcadas") or [],
                    "opcoes": item.get("opcoes") or [],
                }
            )

    return resultado


def descrever_tipo_cadastro(tipo_cadastro: str | None) -> dict[str, Any]:
    tipo = detectar_tipo_cadastro(tipo_cadastro)
    regras = obter_regras_tipo(tipo)
    return {
        "tipo_cadastro": tipo,
        "tipo_tarefa_identificada": TIPO_TAREFA_POR_CADASTRO.get(tipo or "", "GENERICO"),
        "quantidade_campos": len(regras),
        "campos": [asdict(regra) for regra in regras],
    }


if __name__ == "__main__":
    exemplo = {
        "perguntas_forms": [
            {"pergunta": "Tipo de cadastro", "resposta": "Decisões"},
            {"pergunta": "Número CNJ", "resposta": "0010481-42.2025.5.03.0097"},
            {"pergunta": "Cliente principal", "resposta": "MVC"},
            {"pergunta": "Resultado", "resposta": "Êxito Parcial"},
        ]
    }
    from pprint import pprint
    pprint(mapear_formulario(exemplo))
