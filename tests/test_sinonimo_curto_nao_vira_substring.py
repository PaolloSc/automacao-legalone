"""Regressao 19/08/2026: o fallback de sinonimos de pedido usava substring
puro ('cand_norm in txt_norm') -- o sinonimo curto 'he' (sigla de 'Horas
extras') bateu por acidente dentro de 'reconHEcimento de vinculo' e trocou
o pedido 'Horas extras' pelo pedido errado, ja usado numa linha anterior.
Confirmado ao vivo: script travou 90s tentando clicar numa opcao que nao
era a que devia. Sinonimos curtos (<4 chars) agora exigem match de palavra
inteira (\\b...\\b), nao pedaco de palavra."""
import re

from legalone_cadastro import LegalOneCadastro, _normalizar_pedido


def _bate(cand: str, txt: str) -> bool:
    cand_norm = _normalizar_pedido(cand)
    txt_norm = _normalizar_pedido(txt)
    curto = len(cand_norm) < 4
    if curto:
        return re.search(rf'\b{re.escape(cand_norm)}\b', txt_norm) is not None
    return cand_norm in txt_norm or txt_norm in cand_norm


def test_sigla_curta_nao_bate_dentro_de_outra_palavra():
    assert _bate('he', 'Reconhecimento de vínculo') is False


def test_sigla_curta_bate_como_palavra_inteira():
    assert _bate('he', 'HE noturna') is True


def test_sinonimo_longo_continua_com_substring():
    assert _bate('horas extraordinárias', 'Horas Extraordinárias - CLT') is True


def test_metodo_realmente_usa_a_regra_de_palavra_inteira():
    import inspect
    src = inspect.getsource(LegalOneCadastro._selecionar_pedido_no_dropdown)
    assert 'curto = len(cand_norm) < 4' in src
    assert r'\b{re.escape(cand_norm)}\b' in src


if __name__ == '__main__':
    test_sigla_curta_nao_bate_dentro_de_outra_palavra()
    test_sigla_curta_bate_como_palavra_inteira()
    test_sinonimo_longo_continua_com_substring()
    test_metodo_realmente_usa_a_regra_de_palavra_inteira()
    print('ok')
