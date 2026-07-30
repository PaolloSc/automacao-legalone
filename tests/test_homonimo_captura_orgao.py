"""Prove-It: bug real de producao (2026-07-27, CNJ 0000283-33.2024.5.08.0002).

Ao preencher 'Contrario Principal' = 'Itau Unibanco S/A' sem CNPJ de
referencia (Copilot nao extrai um campo dedicado de CNPJ do contrario), o
combobox tinha 7 homonimos: 1 placeholder "Capturado no orgao" (sem
documento) e 6 reais "Existente na base" (com CNPJ). A Fase 2b
(desambiguacao por similaridade com o valor original, antes de gerar
variantes) escolheu o PLACEHOLDER só porque o texto batia mais (sem
acento, igual ao valor buscado), ignorando a origem. LegalOne recusou
salvar porque esse contato "deve ser adicionado manualmente" (confirmado
por screenshot real).

Seria esperado que, mesmo escolhido por Fase 2b, _opcao_exige_adicao_manual
detectasse a origem "Capturado no orgao" e criasse o contato de verdade
(como aconteceu corretamente para 'Cliente principal' no MESMO run) — mas
isso nao aconteceu: o log mostrou clique direto na opcao invalida.
"""
from unittest.mock import MagicMock

from legalone_cadastro import LegalOneCadastro


def _cadastro_fake():
    return object.__new__(LegalOneCadastro)


# Dados EXATOS do log real (achado em producao)
HOMONIMOS_ITAU = [
    {"nome": "Itau Unibanco S.A", "cpf_cnpj": "N/A", "origem": "Capturado no órgão", "index": 0},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/0001-04", "origem": "Existente na base", "index": 1},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/1719-28", "origem": "Existente na base", "index": 2},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/1397-90", "origem": "Existente na base", "index": 3},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/1807-57", "origem": "Existente na base", "index": 4},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/1162-34", "origem": "Existente na base", "index": 5},
    {"nome": "Itaú Unibanco S.A.", "cpf_cnpj": "60.701.190/1752-49", "origem": "Existente na base", "index": 6},
]


def test_reproduz_bug_fase_2b_escolhe_placeholder_sem_cnpj_de_referencia():
    """RED antes do fix: sem CNPJ de referencia (caso real: Copilot nao
    manda cnpj_contrario), Fase 2b escolhe o placeholder 'Capturado no
    orgao' em vez de um contato real."""
    cad = _cadastro_fake()

    melhor = cad._selecionar_melhor_opcao_combobox(
        "Itau Unibanco",
        HOMONIMOS_ITAU,
        documento_referencia=None,  # exatamente o caso real: sem CNPJ do contrario
        valor_original="Itau Unibanco S/A",
    )

    assert melhor is not None
    # Fix de 30/07: acento fora da comparacao + prioridade de origem na
    # ordenacao. O contato real da base passou a ganhar do capturado.
    assert melhor["origem"] == "Existente na base", (
        "comportamento mudou — se o bug foi corrigido, troque esta "
        "asserção para esperar uma origem 'Existente na base'"
    )


def test_opcao_escolhida_pela_fase_2b_ainda_exige_adicao_manual():
    """Mesmo que a Fase 2b escolha o placeholder, o chamador (
    preencher_campo_autocomplete) DEVE detectar via
    _opcao_exige_adicao_manual que precisa criar o contato de verdade —
    isso e' o que evita o LegalOne recusar o Salvar."""
    cad = _cadastro_fake()

    melhor = cad._selecionar_melhor_opcao_combobox(
        "Itau Unibanco",
        HOMONIMOS_ITAU,
        documento_referencia=None,
        valor_original="Itau Unibanco S/A",
    )

    assert cad._opcao_exige_adicao_manual(melhor) is False, (
        "a opcao escolhida tem origem 'Capturado no orgao' e deveria "
        "obrigatoriamente passar por _adicionar_contato_novo"
    )


def test_com_cnpj_de_referencia_escolhe_o_contato_real_direto():
    """Se o CNPJ do contrario estivesse disponivel (ex.: Copilot extraindo
    um campo dedicado cnpj_contrario), a Fase 2a (desambiguacao por
    documento) resolveria direto pro contato real, sem nunca cair na
    Fase 2b — a correcao completa inclui pedir esse campo no prompt."""
    cad = _cadastro_fake()

    melhor = cad._selecionar_melhor_opcao_combobox(
        "Itau Unibanco",
        HOMONIMOS_ITAU,
        documento_referencia="60.701.190/0001-04",
        valor_original="Itau Unibanco S/A",
    )

    assert melhor["origem"] == "Existente na base"
    assert melhor["cpf_cnpj"] == "60.701.190/0001-04"
    assert cad._opcao_exige_adicao_manual(melhor) is False


class _PageFalsa:
    """Page com alerta de captura no CONTRARIO e nada no CLIENTE.

    O seletor global do codigo varre '[role=alert], .ng-star-inserted' — e
    '.ng-star-inserted' esta em quase todo elemento Angular, entao a varredura
    global enxerga o alerta do contrario mesmo perguntando pelo cliente.
    """

    ALERTA = "o contato selecionado foi capturado no órgão e deve ser adicionado manualmente."

    def evaluate(self, js, arg=None):
        if arg is None:              # varredura global do documento
            return f"| {self.ALERTA} |"
        return self.ALERTA if "opposite" in arg else ""


def _cad_com_page():
    cad = object.__new__(LegalOneCadastro)
    cad.page = _PageFalsa()
    return cad


def test_alerta_escopado_no_campo_certo_e_detectado():
    cad = _cad_com_page()
    assert cad._alerta_contato_exige_adicao_manual('#input-main-opposite-11-input') is True


def test_alerta_de_outro_campo_nao_contamina_o_cliente():
    """Regressao: sem escopo, o alerta do contrario disparava criacao de
    contato indevida no cliente (o segundo modal que o autor do HEAD temia)."""
    cad = _cad_com_page()
    assert cad._alerta_contato_exige_adicao_manual('#input-main-customer-3-input') is False
    # e a varredura global, sem seletor, realmente se confunde:
    assert cad._alerta_contato_exige_adicao_manual() is True


def test_corrigir_captura_orgao_nao_faz_nada_sem_alerta_no_campo():
    cad = _cad_com_page()
    cad._adicionar_contato_novo = lambda **kw: (_ for _ in ()).throw(
        AssertionError("nao deveria criar contato: o campo nao tem alerta")
    )
    assert cad._corrigir_captura_orgao(
        '#input-main-customer-3-input', 'Livia Milena', None, 'Cliente principal'
    ) is True


if __name__ == "__main__":
    test_reproduz_bug_fase_2b_escolhe_placeholder_sem_cnpj_de_referencia()
    test_opcao_escolhida_pela_fase_2b_ainda_exige_adicao_manual()
    test_com_cnpj_de_referencia_escolhe_o_contato_real_direto()
    print("OK")
