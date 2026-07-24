"""Normalizacao de valores antes de preencher o LegalOne."""
from legalone_cadastro import LegalOneCadastro as L


def test_nome_parte_remove_papel_e_lista():
    assert L._nome_parte("Katia Bela dos Santos Souza (Reclamante/Autora)") == "Katia Bela dos Santos Souza"
    assert L._nome_parte("Steel Servicos Auxiliares LTDA (Reclamado); Auristela; Rita") == "Steel Servicos Auxiliares LTDA"
    assert L._nome_parte("Fulano de Tal - Reclamado") == "Fulano de Tal"
    assert L._nome_parte("Empresa Alfa LTDA") == "Empresa Alfa LTDA"


def test_sim_ou_nao_so_aceita_dois_valores():
    assert L._sim_ou_nao("Sim") == "Sim"
    assert L._sim_ou_nao("SIM") == "Sim"
    assert L._sim_ou_nao("NAO LOCALIZADO") == "Não"
    assert L._sim_ou_nao(None) == "Não"
    assert L._sim_ou_nao("qualquer coisa") == "Não"
