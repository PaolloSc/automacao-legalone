"""'Assunto (CNJ)' — lista repetivel do painel Dados complementares.

Ids conferidos em docs/varredura/campos_20260811_111409.json:
    Assuntos_<guid>__AssuntoText  (visivel)
    Assuntos_<guid>__AssuntoId    (hidden, prova que gravou)
O GUID muda a cada ficha, entao os ids saem do DOM. A linha ja' vem no HTML:
para um assunto nao se clica em "Adicionar assunto (CNJ)".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro as L

GUID = "0da7a954_f98e_4999_a291_74a7933bdce4"


class _Page:
    def __init__(self, valor=""):
        self.valor = valor

    def evaluate(self, js):
        return {"text": f"Assuntos_{GUID}__AssuntoText",
                "hidden": f"Assuntos_{GUID}__AssuntoId",
                "valor": self.valor}


class _PageSemCampo:
    def evaluate(self, js):
        return None


def _bot(page, valor_dados="Rescisão / Resolução"):
    bot = object.__new__(L)
    bot.page = page
    bot._valor_limpo = lambda v: L._valor_limpo(bot, v)
    bot._texto_forms_invalido = lambda v: False
    bot.chamadas = []
    bot._preencher_lookup_por_id = lambda t, h, v: (bot.chamadas.append((t, h, v)) or True)
    return bot, {"assunto_cnj": valor_dados, "outros_dados": {}}


def test_preenche_a_linha_vazia_com_os_ids_do_dom():
    bot, dados = _bot(_Page(valor=""))
    assert bot._preencher_assunto_cnj(dados) is True
    assert bot.chamadas == [(f"Assuntos_{GUID}__AssuntoText",
                             f"Assuntos_{GUID}__AssuntoId",
                             "Rescisão / Resolução")]


def test_nao_sobrescreve_assunto_ja_preenchido():
    bot, dados = _bot(_Page(valor="DIREITO CIVIL / ... / Rescisão"))
    assert bot._preencher_assunto_cnj(dados) is False
    assert bot.chamadas == []


def test_sem_o_campo_na_tela_nao_faz_nada():
    bot, dados = _bot(_PageSemCampo())
    assert bot._preencher_assunto_cnj(dados) is False
    assert bot.chamadas == []


def test_sem_assunto_no_datajud_nao_faz_nada():
    bot, dados = _bot(_Page(valor=""), valor_dados="NAO LOCALIZADO")
    assert bot._preencher_assunto_cnj(dados) is False
    assert bot.chamadas == []
