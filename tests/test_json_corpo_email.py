"""JSON do email do Power Automate precisa ser lido mesmo aninhado / com HTML em volta.

Regressao: a regex original ({[^{}]*"cnj"[^{}]*}) nao casa objeto com "outros_dados",
e o fallback de texto inteiro falha se houver qualquer texto fora do JSON.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from outlook_monitor_graph import OutlookMonitorGraph


def _parse(corpo):
    return OutlookMonitorGraph._extrair_json_do_corpo(None, corpo)


def test_json_plano():
    assert _parse('<p>{"cnj": "0010481-42.2025.5.03.0097"}</p>')['cnj'].startswith('0010481')


def test_json_aninhado_com_texto_em_volta():
    corpo = (
        '<html><body><p>Dados do formulario:</p><pre>'
        '{"cnj": "0024634-49.2026.5.24.0101", "cliente": "ACME LTDA", '
        '"outros_dados": {"valor_causa": "R$ 10.000,00"}}'
        '</pre><p>Enviado automaticamente.</p></body></html>'
    )
    dados = _parse(corpo)
    assert dados['cnj'] == "0024634-49.2026.5.24.0101"
    assert dados['outros_dados']['valor_causa'] == "R$ 10.000,00"


def test_sem_json_retorna_none():
    assert _parse('<p>nenhum dado aqui</p>') is None


if __name__ == "__main__":
    test_json_plano()
    test_json_aninhado_com_texto_em_volta()
    test_sem_json_retorna_none()
    print("OK")
