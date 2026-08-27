"""O retorno do clique cua-driver em 'continuar com o preenchimento' era
descartado (`a or b` sem checar o resultado) -> quando o clique via UIA
falhava silenciosamente, o log ficava 3min mudo ate o erro final de
'Salvar desabilitado' (log 18/08 18:16-18:19), sem pista do motivo real.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _bot_base():
    bot = object.__new__(LegalOneCadastro)
    bot._ir_para_pre_cadastro = lambda: True
    bot.page = MagicMock()
    bot.page.url = "https://firm.legalone.com.br/litigation/create/18022"
    bot._switch_to_latest_page = lambda: None
    return bot


def test_loga_aviso_quando_clique_continuar_falha(caplog):
    bot = _bot_base()
    cua_win = MagicMock()
    cua_win.disponivel.return_value = True
    cua_win.clicar_editar_do_cnj.return_value = True
    cua_win.clicar_label.return_value = False  # clique falhou nas duas tentativas

    with patch.dict(sys.modules, {"cua_win": cua_win}):
        with caplog.at_level("WARNING", logger="AutomacaoLegalOne"):
            bot._continuar_preenchimento_rascunho("0001423-95.2026.5.02.0030")

    assert any("continuar com o preenchimento" in r.message and "falhou" in r.message
               for r in caplog.records)


def test_nao_loga_aviso_quando_clique_continuar_funciona(caplog):
    bot = _bot_base()
    cua_win = MagicMock()
    cua_win.disponivel.return_value = True
    cua_win.clicar_editar_do_cnj.return_value = True
    cua_win.clicar_label.return_value = True

    with patch.dict(sys.modules, {"cua_win": cua_win}):
        with caplog.at_level("WARNING", logger="AutomacaoLegalOne"):
            bot._continuar_preenchimento_rascunho("0001423-95.2026.5.02.0030")

    assert not any("nao respondeu" in r.message for r in caplog.records)
