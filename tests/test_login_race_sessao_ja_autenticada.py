"""Corrida com o SSO: o caller ve 'Sign In' por um instante (bounce do
signon.thomsonreuters.com) e chama o login legado, mas o redirect automatico
(sessao ja valida) pode terminar ANTES do login legado rodar. Sem checar isso,
'input:visible' pega o primeiro input da pagina ja autenticada -- a barra de
busca do Home -- digita o usuario nela e trava esperando senha que nunca
aparece (achado ao vivo 11/09/2026, CNJ 0024767-91.2026.5.24.0101, e
reproduzido isolado em teste headless no mesmo dia).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _bot():
    bot = object.__new__(LegalOneCadastro)
    bot.page = MagicMock()
    return bot


def test_pula_login_legado_quando_ja_autenticado():
    bot = _bot()
    # Ja aterrissou no Home (sessao valida) -- nao ha /login, /signon nem /auth na URL.
    bot.page.url = "https://firm.legalone.com.br/home"

    resultado = bot._fazer_login_signon_legacy()

    assert resultado is True
    bot.page.wait_for_selector.assert_not_called()
    bot.page.keyboard.type.assert_not_called()


def test_segue_login_legado_quando_realmente_na_tela_de_login():
    bot = _bot()
    bot.page.url = "https://carvalhofurtadoadv.novajus.com.br/login/password"
    campo_usuario = MagicMock()
    bot.page.wait_for_selector.return_value = campo_usuario

    # Sem interromper no meio (o mock nao replica a pagina real inteira), so'
    # confirma que a guarda nao suprime o login legitimo: o primeiro elemento
    # buscado continua sendo o input de usuario, e ele e' clicado.
    try:
        bot._fazer_login_signon_legacy()
    except Exception:
        pass

    primeira_chamada = bot.page.wait_for_selector.call_args_list[0]
    assert primeira_chamada.args[0] == 'input:visible'
    campo_usuario.click.assert_called()


if __name__ == "__main__":
    test_pula_login_legado_quando_ja_autenticado()
    test_segue_login_legado_quando_realmente_na_tela_de_login()
    print("ok")
