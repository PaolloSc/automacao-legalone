"""Regressao: veto de identidade do lookup rejeitava a opcao certa do
catalogo so por causa do plural do pt-BR (Forms manda "Agravantes" quando
ha' 2 clientes; o catalogo do LegalOne so tem "Agravante", singular).
Rodava 100% das vezes que o proprio LegalOne nao preenchia o campo sozinho
antes da gente tentar — nao era flakiness de rede, era o veto sempre
rejeitando a mesma comparacao (recurso 233, 17/08/2026)."""
from legalone_cadastro import LegalOneCadastro


def test_plural_do_forms_bate_com_singular_do_catalogo():
    cadastro = LegalOneCadastro(username="", password="")
    assert cadastro._compartilha_identidade(["Agravantes"], "Agravante") is True


def test_veto_ainda_rejeita_opcoes_sem_nenhuma_palavra_em_comum():
    cadastro = LegalOneCadastro(username="", password="")
    assert cadastro._compartilha_identidade(["Agravante"], "Recorrido") is False
