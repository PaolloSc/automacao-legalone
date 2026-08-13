"""'Justica (CNJ)' sai do proprio numero do processo.

Campo #JusticaId da ficha (varredura de 13/08/2026) chega vazio do tribunal.
O digito J do CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO) diz o segmento — Res. CNJ
65/2008 —, entao nao ha' consulta nenhuma a fazer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro as L


def test_segmento_vira_justica():
    assert L._justica_do_cnj("0001623-21.2011.5.08.0114") == "Justiça do Trabalho"
    assert L._justica_do_cnj("5014928-36.2025.8.13.0686") == "Justiça Estadual"
    assert L._justica_do_cnj("0000123-45.2024.4.06.0000") == "Justiça Federal"
    assert L._justica_do_cnj("0000123-45.2024.3.00.0000") == "Superior Tribunal de Justiça"


def test_numero_invalido_nao_chuta():
    assert L._justica_do_cnj("") is None
    assert L._justica_do_cnj("123") is None
    assert L._justica_do_cnj("NAO LOCALIZADO") is None
    assert L._justica_do_cnj(None) is None


def test_ficha_tem_o_campo():
    """Sem a linha em _FICHA_LOOKUPS o valor e' calculado e nunca preenchido."""
    campos = {base for base, _ in L._FICHA_LOOKUPS}
    assert "Justica" in campos
    assert "justica" in L._DATAJUD_CAMPOS
