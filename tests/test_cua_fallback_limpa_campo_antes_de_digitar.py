"""O caminho deterministico (_selecionar_melhor_opcao_combobox) limpa o campo
a cada tentativa mas desiste sem limpar de novo, deixando a ULTIMA variante
testada (ex.: 'Tributaria') no campo. Sem selecionar tudo + apagar antes de
digitar, o fallback CUA digita em cima disso e commita os dois valores
concatenados -- achado ao vivo 11/09/2026 (Centro de Custo virou
'TributariaTributario', CNJ 1004487-43.2020.4.01.3811, reproduzido em teste
headless isolado no mesmo dia).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _bot():
    bot = object.__new__(LegalOneCadastro)
    bot.page = MagicMock()
    bot.page.title.return_value = "Legal One"
    return bot


def _cua_mock(*, opcao_encontrada: bool):
    cua = MagicMock()
    cua.disponivel.return_value = True
    cua.clicar_campo.return_value = True  # foco via AT-SPI funcionou
    cua.clicar_opcao.return_value = opcao_encontrada
    return cua


def test_limpa_campo_antes_de_digitar_o_valor():
    bot = _bot()
    cua = _cua_mock(opcao_encontrada=True)

    with patch.dict(sys.modules, {"cua_fallback": cua}):
        bot._fallback_cua_combobox(
            seletor=None, valor="Tributário",
            nome_campo="Centro de Custo", label_form="Centro de Custo",
        )

    chamadas = [c for c in bot.page.keyboard.method_calls]
    nomes = [c[0] for c in chamadas]
    # Control+A e Delete tem que vir ANTES do type, e nessa ordem.
    assert "press" in nomes and "type" in nomes
    idx_ctrl_a = nomes.index("press")
    idx_type = len(nomes) - 1 - nomes[::-1].index("type")
    assert idx_ctrl_a < idx_type, f"limpeza deve vir antes do type: {chamadas}"
    presses = [c.args[0] for c in chamadas if c[0] == "press"]
    assert presses == ["Control+A", "Delete"], presses


if __name__ == "__main__":
    test_limpa_campo_antes_de_digitar_o_valor()
    print("ok")
