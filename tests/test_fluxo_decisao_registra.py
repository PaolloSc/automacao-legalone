"""Decisao que nao registrou nada nao pode ser salva como sucesso.

Run de 10/08/2026 (CNJ 0013231-78.2024.5.15.0077): o Forms mandou DECISOES, o
roteador acertou o tipo, o bot abriu /processos/processos/edit/6876 e salvou —
mas a decisao nao entrou. O passo 6.1 chamava `preencher_detalhes_faltantes`,
o preenchedor generico do cadastro inicial, que numa tela Kendo mexe na ficha
do processo e nao grava resultado nenhum.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro

DECISAO_DO_FORMS = {
    "cnj": "0013231-78.2024.5.15.0077",
    "outros_dados": {
        "resultado": "Êxito total",
        "tipo_resultado": "Sentença",
        "data_sentenca": "10/08/2026",
        "situacao_pedido": "Indeferido",
        "valor_total_deferido": "80.000,00",
    },
}


def _bot(pedidos=(0, 0), resultado=False, data=False):
    """`resultado`: o painel gravou tudo. `data`: gravou alguma data."""
    bot = object.__new__(LegalOneCadastro)
    bot.last_error_reason = None
    bot.page = None
    bot._preencher_classificacoes_pedidos = lambda dados: pedidos
    bot._expandir_painel = lambda titulo: 'ja-aberto'
    preenchidos = (1 if resultado else 0) + (1 if data else 0)
    falhas = [] if resultado else ['Resultado']
    bot._preencher_painel_resultado = lambda obter: (preenchidos, falhas)
    bot._preencher_valores_monetarios = lambda obter: (0, [])
    bot._preencher_valores_monetarios_decisao = lambda obter: (0, [])
    bot._enriquecer_dados_datajud = lambda dados: None
    return bot


def test_nada_gravado_com_decisao_no_forms_falha():
    assert not _bot()._registrar_decisao(DECISAO_DO_FORMS)


def test_resultado_gravado_basta():
    assert _bot(resultado=True)._registrar_decisao(DECISAO_DO_FORMS)


def test_pedido_classificado_basta_quando_nao_veio_resultado():
    so_pedido = {"outros_dados": {"situacao_pedido": "Indeferido"}}
    assert _bot(pedidos=(2, 2))._registrar_decisao(so_pedido)


def test_resultado_gravado_mas_nenhum_pedido_classificado_reprova():
    # Veio pedido junto do resultado: gravar so o resultado deixa metade fora.
    assert not _bot(resultado=True, pedidos=(0, 2))._registrar_decisao(DECISAO_DO_FORMS)


def test_data_gravada_basta_quando_nao_veio_resultado():
    so_pedido = {"outros_dados": {"situacao_pedido": "Indeferido",
                                  "data_sentenca": "10/08/2026"}}
    assert _bot(data=True)._registrar_decisao(so_pedido)


def test_resultado_que_falhou_reprova_mesmo_com_data_gravada():
    # Meia decisao gravada e' o mesmo erro de antes com outra roupa.
    assert not _bot(resultado=False, data=True)._registrar_decisao(DECISAO_DO_FORMS)


def test_pedido_que_falhou_reprova_quando_so_veio_pedido():
    so_pedido = {"outros_dados": {"situacao_pedido": "Indeferido"}}
    assert not _bot()._registrar_decisao(so_pedido)


def test_sem_dados_de_decisao_nao_reprova_a_troca_de_fase():
    # Forms so trocou a fase: nao ha o que registrar, nao e' falha.
    assert _bot()._registrar_decisao({"cnj": "1", "outros_dados": {}})


def test_placeholder_do_forms_nao_conta_como_decisao():
    vazio = {"outros_dados": {"resultado": "Nenhuma resposta fornecida"}}
    assert _bot()._registrar_decisao(vazio)


if __name__ == "__main__":
    test_nada_gravado_com_decisao_no_forms_falha()
    test_resultado_gravado_basta()
    test_pedido_classificado_basta_quando_nao_veio_resultado()
    test_resultado_gravado_mas_nenhum_pedido_classificado_reprova()
    test_data_gravada_basta_quando_nao_veio_resultado()
    test_resultado_que_falhou_reprova_mesmo_com_data_gravada()
    test_pedido_que_falhou_reprova_quando_so_veio_pedido()
    test_sem_dados_de_decisao_nao_reprova_a_troca_de_fase()
    test_placeholder_do_forms_nao_conta_como_decisao()
    print("ok")
