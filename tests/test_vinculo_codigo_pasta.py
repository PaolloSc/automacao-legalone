"""Regressao: _fluxo_recurso_civel rejeitava o campo 'Vinculo' sempre que
nao fosse um CNJ completo (20 digitos) — mas o Forms as vezes vem
preenchido com o codigo de pasta do LegalOne ('Proc - 0004487', o que o
advogado ve na tela) em vez do CNJ. Confirmado ao vivo (19/08/2026) que
_link_detalhes_da_busca ja resolve esse formato corretamente, inclusive
desambiguando entre varios processos parecidos do mesmo cliente — o
guard so' precisava aceitar o formato, nao inventar busca nova."""
from unittest.mock import MagicMock, patch

from legalone_cadastro import LegalOneCadastro


def test_aceita_cnj_completo():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.last_error_reason = None
    with patch.object(c, "_abrir_novo_recurso_da_pasta", return_value=False) as m:
        c._fluxo_recurso_civel({"vinculo": "5300618-93.2023.8.09.0051", "cliente": "X"})
    m.assert_called_once()
    assert c.last_error_reason is None


def test_aceita_codigo_de_pasta_legalone():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.last_error_reason = None
    with patch.object(c, "_abrir_novo_recurso_da_pasta", return_value=False) as m:
        c._fluxo_recurso_civel({"vinculo": "Proc - 0004487", "cliente": "X"})
    m.assert_called_once()
    assert c.last_error_reason is None


def test_rejeita_vinculo_vazio():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.last_error_reason = None
    with patch.object(c, "_abrir_novo_recurso_da_pasta") as m:
        resultado = c._fluxo_recurso_civel({"vinculo": "", "cliente": "X"})
    m.assert_not_called()
    assert resultado is False
    assert "tratar manualmente" in c.last_error_reason


def test_rejeita_texto_sem_relacao():
    c = LegalOneCadastro.__new__(LegalOneCadastro)
    c.last_error_reason = None
    with patch.object(c, "_abrir_novo_recurso_da_pasta") as m:
        resultado = c._fluxo_recurso_civel({"vinculo": "algum texto qualquer", "cliente": "X"})
    m.assert_not_called()
    assert resultado is False
