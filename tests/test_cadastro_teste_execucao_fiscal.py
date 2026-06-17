from scripts.cadastrar_teste_execucao_fiscal import build_dados_teste


def test_build_dados_teste_execucao_fiscal():
    dados = build_dados_teste()
    assert dados["cnj"] == "0004647-90.2017.4.01.3811"
    assert dados["cliente"] == "BQI Imoveis LTDA"
    assert dados["contrario"] == "União - Fazenda Nacional"
    assert dados["natureza"] == "EXECUÇÃO FISCAL"
    assert dados["fase"] == "Sentença"
    assert dados["valor_causa"] == "R$ 52.316,00"
    assert "Execução Fiscal" in dados["tipo_acao"]
    assert "Pedido teste" in dados["descricao_pedidos"]
