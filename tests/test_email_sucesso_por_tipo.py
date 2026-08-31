"""E-mail de sucesso deve distinguir cadastro inicial de decisao e trazer pasta.

Evidencia 10/08/2026 (CNJ 0013231-78.2024.5.15.0077): Forms → DECISOES → DECISAO,
mas o assunto saia `[OK CADASTRO] Pasta N/A — ... cadastro concluido`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automacao_legalone_completa import rotulos_email_sucesso
from legalone_cadastro import LegalOneCadastro


def test_decisao_nao_usa_assunto_de_cadastro():
    r = rotulos_email_sucesso({
        "cnj": "0013231-78.2024.5.15.0077",
        "numero_pasta": "Proc - 0006136",
        "tipo_tarefa_identificada": "DECISAO",
    })
    assert r["assunto"].startswith("[OK DECISAO]")
    assert "decisão registrada" in r["assunto"].lower() or "decisao registrada" in r["assunto"].lower()
    assert "CADASTRO" not in r["assunto"]
    assert r["tipo_label"] == "Decisão"
    assert "Proc - 0006136" in r["assunto"]


def test_cadastro_inicial_continua_ok_cadastro():
    r = rotulos_email_sucesso({
        "cnj": "0000283-33.2024.5.08.0002",
        "numero_pasta": "Proc - 0007344",
        "tipo_tarefa_identificada": "CADASTRO_INICIAL",
    })
    assert r["assunto"].startswith("[OK CADASTRO]")
    assert "cadastro concluído" in r["assunto"].lower() or "cadastro concluido" in r["assunto"].lower()
    assert r["tipo_label"] == "Cadastro inicial"


def test_recurso_civel_usa_assunto_de_recurso():
    """Regressao 31/08/2026: forms_mapping_civel mapeia 'RECURSO' ->
    'RECURSO_CIVEL', mas o check era so' == 'RECURSO' -- caia no generico
    '[OK CADASTRO]' em vez de '[OK RECURSO]'."""
    r = rotulos_email_sucesso({
        "cnj": "0000283-33.2024.5.08.0002",
        "numero_pasta": "Proc - 0007344",
        "tipo_tarefa_identificada": "RECURSO_CIVEL",
    })
    assert r["assunto"].startswith("[OK RECURSO]")
    assert r["tipo_label"] == "Recurso"


def test_ja_cadastrado_tem_prefixo_proprio():
    r = rotulos_email_sucesso(
        {"cnj": "0000283-33.2024.5.08.0002"},
        pasta_existente="Proc - 0007349",
    )
    assert r["assunto"].startswith("[JA CADASTRADO]")


def test_captura_pasta_do_titulo_da_edicao():
    """Decisao: titulo 'Alterando processo: Proc - 0006136 - Legal One'."""
    bot = object.__new__(LegalOneCadastro)

    class _Page:
        def title(self):
            return "Alterando processo: Proc - 0006136 - Legal One"

    bot.page = _Page()
    bot._ler_valor_campo_formulario = lambda *_a, **_k: None
    bot._valor_limpo = lambda v: v

    dados = {"cnj": "0013231-78.2024.5.15.0077"}
    pasta = bot._capturar_numero_pasta(dados)
    assert pasta == "Proc - 0006136"
    assert dados["numero_pasta"] == "Proc - 0006136"


def test_captura_pasta_nao_sobrescreve_valor_ja_gravado():
    bot = object.__new__(LegalOneCadastro)
    bot.page = None
    dados = {"numero_pasta": "Proc - 0007344"}
    assert bot._capturar_numero_pasta(dados) == "Proc - 0007344"


def test_captura_pasta_nao_aceita_titulo_generico_da_pagina():
    """Regressao 31/08/2026: se o campo 'Pasta' nao respondeu e o titulo da
    pagina nao bate com 'Proc - NNNN', o fallback fraco aceitava QUALQUER
    titulo com menos de 80 chars -- um titulo generico tipo 'Editar
    processo' virava numero_pasta por engano."""
    bot = object.__new__(LegalOneCadastro)

    class _Page:
        def title(self):
            return "Editar processo"

    bot.page = _Page()
    bot._ler_valor_campo_formulario = lambda *_a, **_k: None
    bot._valor_limpo = lambda v: v

    dados = {"cnj": "0013231-78.2024.5.15.0077"}
    assert bot._capturar_numero_pasta(dados) is None
    assert "numero_pasta" not in dados


if __name__ == "__main__":
    test_decisao_nao_usa_assunto_de_cadastro()
    test_cadastro_inicial_continua_ok_cadastro()
    test_recurso_civel_usa_assunto_de_recurso()
    test_ja_cadastrado_tem_prefixo_proprio()
    test_captura_pasta_do_titulo_da_edicao()
    test_captura_pasta_nao_sobrescreve_valor_ja_gravado()
    test_captura_pasta_nao_aceita_titulo_generico_da_pagina()
    print("ok")
