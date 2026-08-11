"""Moedas do Forms DECISOES → ids reais do LegalOne.

Ex.: 'Valor do acordo/condenção' R$ 80.000,00 → #ValorAcordoCondenacao_Value.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def test_parse_moeda_br_aceita_formatos_comuns():
    assert LegalOneCadastro._parse_moeda_br("R$ 80.000,00") == 80000.0
    assert LegalOneCadastro._parse_moeda_br("80.000,00") == 80000.0
    assert LegalOneCadastro._parse_moeda_br("80000") == 80000.0
    assert LegalOneCadastro._parse_moeda_br("75911,0000") == 75911.0
    assert LegalOneCadastro._parse_moeda_br("") is None
    assert LegalOneCadastro._parse_moeda_br("N/A") is None


def test_acordo_usa_valor_total_deferido_como_fallback():
    bot = object.__new__(LegalOneCadastro)
    lotes = []

    def fake_lote(itens):
        lotes.append(itens)
        return (len(itens), [])

    bot._preencher_moedas_em_lote = fake_lote
    bot._selecionar_por_id = lambda *a, **k: True
    bot.page = None
    bot._normalizar_texto_busca = lambda v: LegalOneCadastro._normalizar_texto_busca(bot, v)
    bot._parse_moeda_br = LegalOneCadastro._parse_moeda_br

    def obter(*campos):
        mapa = {"valor_total_deferido": "R$ 80.000,00", "custas": "Favorável"}
        for c in campos:
            if c in mapa:
                return mapa[c]
        return ""

    ok, falhas = bot._preencher_valores_monetarios(obter)
    assert ok >= 2
    assert falhas == []
    ids = [it["id"] for it in lotes[0]]
    assert "ValorAcordoCondenacao_Value" in ids
    acordo = next(it for it in lotes[0] if it["id"] == "ValorAcordoCondenacao_Value")
    assert acordo["num"] == 80000.0


def test_valor_causa_so_preenche_se_vazio():
    bot = object.__new__(LegalOneCadastro)
    flags = []

    def fake_lote(itens):
        for it in itens:
            flags.append((it["id"], it["so_vazio"]))
        return (len(itens), [])

    bot._preencher_moedas_em_lote = fake_lote
    bot._selecionar_por_id = lambda *a, **k: True
    bot.page = None
    bot._normalizar_texto_busca = lambda v: LegalOneCadastro._normalizar_texto_busca(bot, v)
    bot._parse_moeda_br = LegalOneCadastro._parse_moeda_br

    def obter(*campos):
        if "valor_causa" in campos:
            return "75.911,00"
        return ""

    bot._preencher_valores_monetarios(obter)
    assert ("ValorCausa_Value", True) in flags


def test_lote_grava_varios_campos_num_unico_evaluate():
    """Sem API: um page.evaluate preenche acordo + honorarios de uma vez."""
    bot = object.__new__(LegalOneCadastro)
    chamadas = []

    class FakePage:
        def evaluate(self, script, arg=None):
            chamadas.append(arg)
            return [
                {"id": it["id"], "ok": True, "valor": str(it["num"])}
                for it in (arg or [])
            ]

    bot.page = FakePage()
    ok, falhas = bot._preencher_moedas_em_lote([
        {"id": "ValorAcordoCondenacao_Value", "num": 80000.0, "so_vazio": False},
        {"id": "ValorHonorarios_Value", "num": 1000.0, "so_vazio": False},
    ])
    assert ok == 2 and falhas == []
    assert len(chamadas) == 1  # um unico round-trip ao DOM


def test_datajud_nao_sobrescreve_valor_causa_do_forms():
    bot = object.__new__(LegalOneCadastro)
    bot._valor_limpo = lambda v: LegalOneCadastro._valor_limpo(bot, v)
    bot._parse_moeda_br = LegalOneCadastro._parse_moeda_br
    dados = {"cnj": "0013231-78.2024.5.15.0077", "valor_causa": "10.000,00"}
    bot._enriquecer_dados_datajud(dados)
    assert dados["valor_causa"] == "10.000,00"


def test_datajud_completa_valor_causa_ausente():
    bot = object.__new__(LegalOneCadastro)
    bot._valor_limpo = lambda v: (str(v).strip() if v not in (None, "") else "")
    bot._parse_moeda_br = LegalOneCadastro._parse_moeda_br

    class FakeClient:
        def consultar(self, cnj):
            return [{"valorAcao": 75911.0}]

    import datajud_client
    original = datajud_client.DatajudClient
    datajud_client.DatajudClient = FakeClient
    try:
        dados = {"cnj": "0013231-78.2024.5.15.0077", "outros_dados": {}}
        bot._enriquecer_dados_datajud(dados)
        assert dados["valor_causa"] == "75.911,00"
    finally:
        datajud_client.DatajudClient = original


def test_aplicar_valores_monetarios_no_cadastro_e_recurso():
    """Cadastro inicial e recurso usam o mesmo entrypoint _aplicar_valores_monetarios."""
    bot = object.__new__(LegalOneCadastro)
    bot._enriquecer_dados_datajud = lambda dados: None
    visto = []

    def fake_preencher(obter):
        visto.append(obter("valor_acordo_condenacao") or obter("valor_causa"))
        return (1, [])

    bot._preencher_valores_monetarios = fake_preencher
    bot._valor_limpo = lambda v: (str(v).strip() if v not in (None, "") else "")
    bot._texto_forms_invalido = lambda v: False

    # Rebind obter path used inside _aplicar
    ok, falhas = LegalOneCadastro._aplicar_valores_monetarios(
        bot, {"valor_causa": "10.000,00", "tipo_tarefa_identificada": "CADASTRO_INICIAL"}
    )
    assert ok == 1 and falhas == []
    assert visto[-1] == "10.000,00"

    ok, falhas = LegalOneCadastro._aplicar_valores_monetarios(
        bot, {
            "valor_acordo_condenacao": "R$ 80.000,00",
            "tipo_tarefa_identificada": "RECURSO",
        }
    )
    assert ok == 1
    assert visto[-1] == "R$ 80.000,00"


def test_roteador_recurso_nao_cai_em_cadastro_inicial():
    bot = object.__new__(LegalOneCadastro)
    bot.last_error_reason = None
    bot._guardian = None
    bot._guardian_recovered = False
    bot.use_agentql = False
    bot.require_context = False
    bot.garantir_sessao_ativa = lambda: True
    bot._get_guardian = lambda: None
    chamado = {"recurso": False, "cadastro_cnj": False}

    bot._fluxo_recurso = lambda dados: chamado.__setitem__("recurso", True) or True
    bot.navegar_cadastro_cnj = lambda: chamado.__setitem__("cadastro_cnj", True) or True

    ok = LegalOneCadastro.cadastrar_processo(
        bot, {"cnj": "0013231-78.2024.5.15.0077", "tipo_tarefa_identificada": "RECURSO"}
    )
    assert ok is True
    assert chamado["recurso"] is True
    assert chamado["cadastro_cnj"] is False


if __name__ == "__main__":
    test_parse_moeda_br_aceita_formatos_comuns()
    test_acordo_usa_valor_total_deferido_como_fallback()
    test_valor_causa_so_preenche_se_vazio()
    test_lote_grava_varios_campos_num_unico_evaluate()
    test_datajud_nao_sobrescreve_valor_causa_do_forms()
    test_datajud_completa_valor_causa_ausente()
    test_aplicar_valores_monetarios_no_cadastro_e_recurso()
    test_roteador_recurso_nao_cai_em_cadastro_inicial()
    print("ok")
