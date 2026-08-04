"""O CUA tem que mirar a janela que o bot dirige, nao qualquer Chrome aberto.

04/08: quatro janelas Chrome abertas — e a do usuario tambem estava com uma tela
do LegalOne ('Civel - cadastro LegalOne'). Nem 'chrome' nem 'legalone' no titulo
separam; quem sabe qual e' a certa e' o Playwright, pelo titulo da propria pagina.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cua_fallback


JANELAS_REAIS = [
    {"title": "Cível - cadastro LegalOne - Google Chrome", "pid": 19404, "window_id": 1},
    {"title": "Calculadora de Honorários · Carvalho & Furtado", "pid": 27572, "window_id": 2},
    {"title": "Alterando processo: Proc - 0004394 - Legal One - Google Chrome",
     "pid": 55160, "window_id": 3},
    {"title": "Microsoft Forms: Google Chrome for Testing", "pid": 25236, "window_id": 4},
]


def _cenario(monkeypatch, janelas, titulo=""):
    monkeypatch.setattr(cua_fallback, "_call", lambda *a, **k: {"windows": janelas})
    monkeypatch.setattr(cua_fallback, "titulo_alvo", titulo)


def test_acha_a_janela_pelo_titulo_da_pagina(monkeypatch):
    _cenario(monkeypatch, JANELAS_REAIS, "Alterando processo: Proc - 0004394 - Legal One")
    assert cua_fallback._janela_chromium() == (55160, 3)


def test_nao_confunde_com_o_legalone_do_usuario(monkeypatch):
    _cenario(monkeypatch, JANELAS_REAIS, "Microsoft Forms")
    assert cua_fallback._janela_chromium() == (25236, 4)


def test_sem_titulo_cai_na_primeira(monkeypatch):
    _cenario(monkeypatch, JANELAS_REAIS, "")
    assert cua_fallback._janela_chromium() == (19404, 1)


def test_sem_janela_nenhuma(monkeypatch):
    _cenario(monkeypatch, [], "qualquer")
    assert cua_fallback._janela_chromium() == (None, None)
