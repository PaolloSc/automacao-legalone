"""garantir_sessao_ativa so checava page.title(); se a pagina caiu pro
login do Thomson Reuters (sessao expirou em execucao longa) o title ainda
responde e o bug reportava sessao ativa sem logar de novo -> falha em
'Navegar para cadastro CNJ' / 'Validar contexto do cadastro' (log 18/08).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def test_garantir_sessao_ativa_relloga_quando_pagina_caiu_no_login():
    bot = object.__new__(LegalOneCadastro)
    bot.page = MagicMock()
    bot.page.is_closed.return_value = False
    bot.page.title.return_value = "Entrar na conta de Legal One Firm | Thomson Reuters"
    bot.page.url = "https://auth.thomsonreuters.com/u/login/identifier?state=abc"

    bot.fazer_login = MagicMock(return_value=True)
    bot.inicializar_navegador = MagicMock(return_value=True)

    assert bot.garantir_sessao_ativa() is True
    bot.fazer_login.assert_called_once()
