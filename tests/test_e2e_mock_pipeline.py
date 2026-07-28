"""Agente de teste E2E — Nivel A (mockado, sem rede, sem browser).

Simula o pipeline inteiro Copilot -> processar_email -> preenchimento de
campos, SEM tocar Outlook, Playwright ou LegalOne real. Mocka pesado em vez
de refatorar automacao_legalone_completa.py/legalone_cadastro.py (decisao
explicita do usuario), entao chama os metodos reais como producao chamaria.

Caso real usado: Peticao_Inicial_Trabalhista_TESTE_0000283-33.2024.5.08.0002
(LIVIA MILENA SOUZA MOREIRA vs. ITAU UNIBANCO S/A) — o mesmo caso que gerou
os avisos falsos de 'campo VAZIO' do qa_validator.py numa sessao anterior.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import automacao_legalone_completa as alc
import legalone_cadastro as lc
from fixtures.copilot_payloads import (
    LIVIA_ITAU_LIMPO,
    LIVIA_ITAU_SUJO,
    PAYLOADS,
    email_data_copilot,
)


# ------------------------------------------------------------------
# Nivel A.1 — processar_email(): classificacao de campos (Copilot -> dados_processo)
# ------------------------------------------------------------------

class _FakeLegalOneCadastro:
    """Substitui o LegalOneCadastro real: nao abre browser, nao loga no
    LegalOne. So grava o dados_processo que receberia pra cadastrar."""

    def __init__(self):
        self.chamadas: list[dict] = []

    def cadastrar_processo(self, dados_processo: dict) -> bool:
        self.chamadas.append(dict(dados_processo))
        return True


def _montar_automacao_fake(monkeypatch) -> alc.AutomacaoLegalOne:
    """Instancia AutomacaoLegalOne SEM rodar o __init__ real (que abriria
    Outlook/Playwright/Claude Brain) e seta so o minimo que
    processar_email() usa no caminho do Copilot."""
    bot = object.__new__(alc.AutomacaoLegalOne)
    bot.config = {"modo_automatico": True}
    bot.stats = {"emails_recebidos": 0, "processos_cadastrados": 0, "erros": 0}
    bot.brain = None
    bot.forms_extractor = None
    bot.forms_extractor_enhanced = None
    bot.legalone = _FakeLegalOneCadastro()
    # _validar_cnpjs faz um GET real na BrasilAPI pra CNPJ com DV valido
    # (ITAU e' real) — simula API fora do ar, o codigo ja trata isso.
    monkeypatch.setattr(alc.requests, "get", MagicMock(side_effect=alc.requests.RequestException("offline no teste")))
    # BUG DE ISOLAMENTO DE TESTE (achado em producao 2026-07-27): sem isto,
    # processar_email() manda um email REAL de sucesso via Microsoft Graph
    # ("[OK CADASTRO] ... cadastro concluido") e grava nos logs REAIS de
    # producao (processos_cadastrados.log/automacao_legalone.log) mesmo
    # com self.legalone fake. Ja aconteceu: 3 execucoes desta suite
    # mandaram 3 emails falsos de "cadastro concluido" pra
    # paollo.sanchez@... e arquivo@... sem nunca ter tocado o LegalOne.
    monkeypatch.setattr(bot, "_enviar_email_sucesso", MagicMock())
    monkeypatch.setattr(bot, "_enviar_email_erro", MagicMock())
    monkeypatch.setattr(bot, "salvar_log_sucesso", MagicMock())
    monkeypatch.setattr(bot, "salvar_log_erro", MagicMock())
    return bot


def test_processar_email_classifica_campos_base_caso_real(monkeypatch):
    bot = _montar_automacao_fake(monkeypatch)
    email_data = email_data_copilot(LIVIA_ITAU_SUJO)

    bot.processar_email(email_data)

    assert bot.stats["processos_cadastrados"] == 1, "processar_email nao chegou a chamar cadastrar_processo"
    dados = bot.legalone.chamadas[0]

    assert dados["cnj"] == "0000283-33.2024.5.08.0002"
    # campos base ficam top-level (nao devem ter ido pra outros_dados)
    for campo in ("cliente", "contrario", "natureza", "posicao", "tipo_cadastro"):
        assert dados.get(campo), f"campo base '{campo}' vazio em dados_processo"
    assert "outros_dados" in dados


def test_processar_email_todos_os_tipos_sem_crash(monkeypatch):
    for tipo, payload in PAYLOADS.items():
        bot = _montar_automacao_fake(monkeypatch)
        email_data = email_data_copilot(payload)
        bot.processar_email(email_data)
        assert bot.stats["processos_cadastrados"] == 1, f"falhou pro tipo {tipo}"
        assert bot.legalone.chamadas[0]["cnj"] == payload["cnj"]


# ------------------------------------------------------------------
# Nivel A.2 — preencher_campos_obrigatorios(): confirma que cliente/contrario/
# posicao chegam LIMPOS (sem papel/CNPJ colado) no ponto onde seriam
# digitados no formulario real, mesmo recebendo o payload SUJO do Copilot.
# ------------------------------------------------------------------

def _montar_cadastro_fake():
    """Instancia LegalOneCadastro sem abrir browser, com os metodos que
    tocam Playwright mockados (gravam chamada, nao interagem com pagina de
    verdade). Metodos puros (_nome_parte, _valor_limpo, _obter_outro_dado)
    ficam REAIS — sao o que queremos provar que funciona."""
    cad = object.__new__(lc.LegalOneCadastro)
    cad.page = MagicMock()

    chamadas_autocomplete: list[tuple] = []

    def _fake_autocomplete(seletor, valor, nome_campo, **kwargs):
        chamadas_autocomplete.append((nome_campo, valor))
        return True

    cad.preencher_campo_autocomplete = _fake_autocomplete
    cad._chamadas_autocomplete = chamadas_autocomplete

    # leitura do campo formulario: devolve o ultimo valor "digitado" por
    # preencher_campo_autocomplete pro mesmo rotulo, simulando que o
    # preenchimento funcionou de primeira (sem forcar os fallbacks).
    _rotulo_por_campo = {
        "Cliente principal": "Cliente Principal",
        "Contrário Principal": "Contrário Principal",
        "Posição": "Posição",
    }

    def _fake_ler_valor(label_texto):
        alvo = _rotulo_por_campo.get(label_texto, label_texto)
        for nome_campo, valor in reversed(chamadas_autocomplete):
            if nome_campo == alvo:
                return valor
        return None

    cad._ler_valor_campo_formulario = _fake_ler_valor
    cad._encontrar_input_por_label_exato = lambda *_a, **_k: "input#fake"
    cad._tratar_modal_criacao_obrigatoria = lambda *_a, **_k: None
    cad._corrigir_captura_orgao = lambda *_a, **_k: True
    cad._preencher_campo_visual = lambda *_a, **_k: None
    cad._calcular_similaridade = lambda a, b: 1.0
    cad._garantir_preenchimento_campo_texto = lambda *_a, **_k: True
    cad._fill_by_label = lambda *_a, **_k: True
    cad._resolver_seletor_por_label = lambda *_a, **_k: None
    cad._detectar_campos_obrigatorios_vazios = lambda: []
    cad._preencher_status_select = lambda *_a, **_k: True
    return cad


def test_preenchimento_limpa_cliente_contrario_posicao_do_payload_sujo():
    cad = _montar_cadastro_fake()

    # roda o metodo real de producao (nao reimplementado) — so os pontos
    # que tocariam Playwright de verdade estao mockados acima.
    cad.preencher_campos_obrigatorios(dict(LIVIA_ITAU_SUJO))

    chamadas = dict(cad._chamadas_autocomplete)
    assert chamadas.get("Cliente Principal") == "LIVIA MILENA SOUZA MOREIRA", (
        f"cliente deveria chegar limpo (sem '(Reclamante)'), veio: {chamadas.get('Cliente Principal')!r}"
    )
    assert chamadas.get("Contrário Principal") == "ITAU UNIBANCO S/A", (
        f"contrario deveria chegar limpo (sem CNPJ colado), veio: {chamadas.get('Contrário Principal')!r}"
    )
    assert chamadas.get("Posição") == "Reclamante", (
        f"posicao deveria chegar limpa (sem '(Ativo)'), veio: {chamadas.get('Posição')!r}"
    )


def test_payload_limpo_e_sujo_dao_o_mesmo_resultado_final():
    """Prova que a limpeza e' idempotente: input ja limpo (o que as
    Instrucoes do Copilot Studio deveriam mandar) e input sujo (o que
    realmente chegou no incidente) terminam preenchendo os MESMOS valores."""
    cad_limpo = _montar_cadastro_fake()
    cad_limpo.preencher_campos_obrigatorios(dict(LIVIA_ITAU_LIMPO))

    cad_sujo = _montar_cadastro_fake()
    cad_sujo.preencher_campos_obrigatorios(dict(LIVIA_ITAU_SUJO))

    assert dict(cad_limpo._chamadas_autocomplete) == dict(cad_sujo._chamadas_autocomplete)


# ------------------------------------------------------------------
# Nivel B (achado real) — 'advogado' extraido da PETICAO real, via upload
# do docx de teste no agente publicado (nao mockado): o Copilot retornou
# advogado='Monica Pinheiro', que e' quem ASSINA a peticao pela Reclamante
# (parte cliente), nao um responsavel interno do escritorio.
#
# Prove-It: este teste documenta que o codigo NAO tem nenhuma validacao
# pra isso hoje — 'advogado' vira 'Responsavel principal' sem checagem.
# Nao existe (ainda) lista de advogados do escritorio pra validar contra
# (dependente da tabela advogado->area que ainda nao foi levantada), entao
# o fix de hoje e' so no PROMPT do Copilot Studio (nao extrair advogado da
# assinatura da peticao). Este teste falha se algum dia um guard-rail for
# adicionado sem atualizar este comentario/expectativa.
# ------------------------------------------------------------------

def test_advogado_da_assinatura_da_peticao_passa_sem_validacao():
    """Documenta o gap: nada no codigo hoje distingue 'advogado' informado
    pelo usuario de 'advogado' extraido erroneamente da assinatura de uma
    peticao (parte externa). Fix real e' no prompt do Copilot Studio."""
    cad = _montar_cadastro_fake()
    payload = {**LIVIA_ITAU_LIMPO, "advogado": "Monica Pinheiro"}

    cad.preencher_campos_obrigatorios(payload)

    chamadas = dict(cad._chamadas_autocomplete)
    assert chamadas.get("Responsável principal") == "Monica Pinheiro", (
        "comportamento mudou — se alguem adicionou validacao de advogado, "
        "atualize este teste pra refletir o novo comportamento esperado"
    )


if __name__ == "__main__":
    import sys
    import types

    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _FakeMonkeypatch()
    test_processar_email_classifica_campos_base_caso_real(mp)
    test_processar_email_todos_os_tipos_sem_crash(mp)
    test_preenchimento_limpa_cliente_contrario_posicao_do_payload_sujo()
    test_payload_limpo_e_sujo_dao_o_mesmo_resultado_final()
    print("OK - pipeline mockado (Nivel A) passou sem tocar rede/browser/LegalOne")
