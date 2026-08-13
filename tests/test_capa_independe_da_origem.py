"""Os campos CNJ da ficha valem para Forms E Copilot — o gatilho e' o CNJ.

A distincao entre as duas origens existe so' em automacao_legalone_completa
(`eh_copilot = bool(email_data.get('dados_diretos'))`), onde se decide COMO
obter os dados. Dali para a frente e' o mesmo `dados_processo`, e
legalone_cadastro nao sabe de onde ele veio.

Este teste existe para impedir que alguem religue o preenchimento a um
caminho so'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fixtures.copilot_payloads import LIVIA_ITAU_LIMPO
from legalone_cadastro import LegalOneCadastro as L

HIT_TRT8 = {
    "tribunal": "TRT8",
    "grau": "G1",
    "classe": {"codigo": 985, "nome": "Ação Trabalhista - Rito Ordinário"},
    "orgaoJulgador": {"nome": "2ª VARA DO TRABALHO DE BELÉM",
                      "codigoMunicipioIBGE": 1501402},
    "assuntos": [{"codigo": 2546, "nome": "Adicional de Insalubridade"},
                 {"codigo": 2086, "nome": "Horas Extras"}],
    "dataAjuizamento": "2024-02-19T00:00:00.000Z",
}


def _bot(hits):
    bot = object.__new__(L)
    bot._valor_limpo = lambda v: L._valor_limpo(bot, v)
    bot._texto_forms_invalido = lambda v: False
    bot._parse_moeda_br = L._parse_moeda_br

    class FakeClient:
        def consultar(self, cnj):
            return hits

    import datajud_client
    original = datajud_client.DatajudClient
    datajud_client.DatajudClient = FakeClient
    return bot, (lambda: setattr(datajud_client, "DatajudClient", original))


def test_payload_do_copilot_recebe_os_campos_da_capa():
    """Payload real que o Copilot manda -> campos CNJ preenchidos."""
    bot, restaurar = _bot([HIT_TRT8])
    try:
        dados = dict(LIVIA_ITAU_LIMPO)          # como chega em dados_diretos
        dados.setdefault("outros_dados", {})
        assert dados["cnj"] == "0000283-33.2024.5.08.0002"
        bot._enriquecer_dados_datajud(dados)

        assert dados["justica"] == "Justiça do Trabalho"     # do digito J=5
        assert dados["assunto_cnj"] == "Adicional de Insalubridade"
        assert dados["tipo_classe_recurso"] == "Ação Trabalhista - Rito Ordinário"
        assert dados["nome_vara_turma"] == "2ª VARA DO TRABALHO DE BELÉM"
        assert dados["data_distribuicao"] == "19/02/2024"
    finally:
        restaurar()


def test_mesmo_cnj_pelo_forms_da_o_mesmo_resultado():
    """Dict cru (caminho Forms) com o mesmo CNJ -> mesmos valores."""
    bot, restaurar = _bot([HIT_TRT8])
    try:
        forms = {"cnj": "0000283-33.2024.5.08.0002", "outros_dados": {}}
        bot._enriquecer_dados_datajud(forms)

        copilot = dict(LIVIA_ITAU_LIMPO, outros_dados={})
        bot._enriquecer_dados_datajud(copilot)

        for campo in ("justica", "assunto_cnj", "tipo_classe_recurso",
                      "nome_vara_turma", "data_distribuicao"):
            assert forms[campo] == copilot[campo], campo
    finally:
        restaurar()
