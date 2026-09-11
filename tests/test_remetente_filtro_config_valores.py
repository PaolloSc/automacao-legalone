"""Os testes de logica em test_remetente_filtro_forms.py provam que
'microsoft' funciona e 'microsoft.com' nao -- mas nao pegam uma regressao
onde alguem volta o VALOR DEFAULT pra 'microsoft.com' nos 4 lugares onde ele
esta hardcoded. Este teste fecha essa lacuna.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_config_automacao_usa_dominio_correto():
    import config_automacao
    assert config_automacao.OUTLOOK_CONFIG['remetente_filtro'] == 'microsoft'


def test_outlook_monitor_graph_default_usa_dominio_correto():
    import inspect
    import outlook_monitor_graph as omg
    default = inspect.signature(omg.OutlookMonitorGraph.__init__).parameters['remetente_filtro'].default
    assert default == 'microsoft'


def test_outlook_monitor_com_default_usa_dominio_correto():
    import inspect
    try:
        import outlook_monitor as om  # win32com so existe no Windows com pywin32
    except ModuleNotFoundError:
        import pytest
        pytest.skip("pywin32 indisponivel neste ambiente (outlook_monitor.py e' so' fallback desktop)")
    default = inspect.signature(om.OutlookMonitor.__init__).parameters['remetente_filtro'].default
    assert default == 'microsoft'


if __name__ == "__main__":
    test_config_automacao_usa_dominio_correto()
    test_outlook_monitor_graph_default_usa_dominio_correto()
    test_outlook_monitor_com_default_usa_dominio_correto()
    print("ok")
