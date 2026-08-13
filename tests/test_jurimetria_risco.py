"""Risco pelo CODIGO TPU: tabela de jurimetria -> hit do DataJud -> ficha.

O agente casava o assunto por texto; aqui casa pelo codigo que ja' vem no
mesmo hit usado para a capa do processo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jurimetria_risco as JR
from legalone_cadastro import LegalOneCadastro

TABELA_NOVA = """# Jurimetria TRT9 - 1o grau (fonte: DataJud/CNJ)

Media do tribunal: **25.0%** de improcedencia.

| Codigo | Pedido (assunto TPU) | Decididos | Improcedencia | risco |
|---:|---|---:|---:|---|
| 13770 | Horas in Itinere | 30572 | 16.8% | Alto |
| 2546 | Adicional de Insalubridade | 21000 | 24.3% | Medio |
| 2117 | Justa Causa | 9000 | 40.6% | Baixo |
"""

# Como as tabelas eram ate' 06/08/2026: sem a coluna de codigo.
TABELA_ANTIGA = """| Pedido (assunto TPU) | Decididos | Improcedencia | risco |
|---|---:|---:|---|
| Horas in Itinere | 30572 | 16.8% | Alto |
"""


def _plantar(tmp_path, nome, conteudo):
    (tmp_path / nome).write_text(conteudo, encoding="utf-8")
    JR.PASTA = tmp_path
    JR._cache.clear()


def test_tabela_indexa_por_codigo(tmp_path):
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    t = JR.tabela("TRT9")  # alias vem em caixa alta do DataJud
    assert t[13770] == {"assunto": "Horas in Itinere", "decididos": 30572,
                        "taxa": 16.8, "risco": "Alto"}
    assert t[2117]["risco"] == "Baixo"


def test_tabela_antiga_sem_codigo_nao_chuta(tmp_path):
    """Sem a coluna de codigo o certo e' nao responder, nao adivinhar."""
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_ANTIGA)
    assert JR.tabela("trt9") == {}
    assert JR.risco_do_processo("trt9", [{"codigo": 13770}]) == (None, "")


def test_tabela_inexistente(tmp_path):
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    assert JR.tabela("trt99") == {}
    assert JR.tabela("") == {}


def test_assunto_fora_da_tabela_fica_de_fora(tmp_path):
    """'sem base' e' sem base — nunca vira Medio."""
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    risco, detalhe = JR.risco_do_processo(
        "trt9", [{"codigo": 999999, "nome": "Assunto novo"},
                 {"codigo": 2117, "nome": "Justa Causa"}])
    assert risco == "Baixo"          # o principal (999999) nao casou
    assert "999999" not in detalhe
    assert detalhe == "2117 Justa Causa: Baixo (40.6%)"


def test_principal_manda_no_risco_do_processo(tmp_path):
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    risco, detalhe = JR.risco_do_processo(
        "trt9", [{"codigo": 13770}, {"codigo": 2117}])
    assert risco == "Alto"           # e nao o pior nem o melhor da lista
    assert detalhe.startswith("13770 Horas in Itinere: Alto (16.8%)")


def _bot(hits):
    bot = object.__new__(LegalOneCadastro)
    bot._valor_limpo = lambda v: LegalOneCadastro._valor_limpo(bot, v)
    bot._texto_forms_invalido = lambda v: False
    bot._parse_moeda_br = LegalOneCadastro._parse_moeda_br

    class FakeClient:
        def consultar(self, cnj):
            return hits

    import datajud_client
    original = datajud_client.DatajudClient
    datajud_client.DatajudClient = FakeClient
    return bot, (lambda: setattr(datajud_client, "DatajudClient", original))


HIT = {
    "tribunal": "TRT9",
    "assuntos": [{"codigo": 2546, "nome": "Adicional de Insalubridade"},
                 {"codigo": 2117, "nome": "Justa Causa"}],
}


def test_bot_preenche_risco_pelo_codigo(tmp_path):
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    bot, restaurar = _bot([HIT])
    try:
        dados = {"cnj": "0000123-45.2024.5.09.0001",
                 "risco": "NAO LOCALIZADO", "outros_dados": {}}
        bot._enriquecer_dados_datajud(dados)
        # Tabela escreve 'Medio' sem acento; o campo do LegalOne tem.
        assert dados["risco"] == "Médio"
        assert dados["outros_dados"]["justificativa_risco"] == (
            "2546 Adicional de Insalubridade: Medio (24.3%);"
            " 2117 Justa Causa: Baixo (40.6%)")
    finally:
        restaurar()


def test_codigo_tpu_corrige_o_risco_do_agente(tmp_path):
    """O agente casa o assunto por TEXTO e erra a linha; o codigo casa exato.

    Por isso `risco` e' a excecao ao so-se-vazio: o valor que o agente mostrou
    no chat entra, mas quem grava no LegalOne e' a tabela pelo codigo.
    """
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    bot, restaurar = _bot([HIT])
    try:
        dados = {"cnj": "0000123-45.2024.5.09.0001", "risco": "Alto",
                 "outros_dados": {}}
        bot._enriquecer_dados_datajud(dados)
        assert dados["risco"] == "Médio"          # 2546, o assunto principal
        assert dados["outros_dados"]["risco"] == "Médio"
        assert "justificativa_risco" in dados["outros_dados"]
    finally:
        restaurar()


def test_sem_tabela_o_risco_do_agente_permanece(tmp_path):
    """Tribunal sem tabela: nada a conferir, o que o agente disse fica."""
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    bot, restaurar = _bot([dict(HIT, tribunal="TRT21")])
    try:
        dados = {"cnj": "0000123-45.2024.5.21.0001", "risco": "Alto",
                 "outros_dados": {}}
        bot._enriquecer_dados_datajud(dados)
        assert dados["risco"] == "Alto"
    finally:
        restaurar()


def test_bot_sem_tabela_deixa_risco_vazio(tmp_path):
    """Tribunal sem tabela gerada: nao inventa risco."""
    _plantar(tmp_path, "jurimetria_trt9.md", TABELA_NOVA)
    bot, restaurar = _bot([dict(HIT, tribunal="TRT21")])
    try:
        dados = {"cnj": "0000123-45.2024.5.21.0001", "outros_dados": {}}
        bot._enriquecer_dados_datajud(dados)
        assert not dados.get("risco")
    finally:
        restaurar()
