"""Fase 2 do refactor: _preencher_lookups_edicao sobrescrevia Orgao/
Procedimento/Fase sem checar se ja vieram preenchidos da captura do
tribunal, batendo na frente do guard 'so-se-vazio' de _preencher_ficha_forms
(_FICHA_LOOKUPS ja cobre os 3 campos com esse guard). Ver
PROMPT_REFATORACAO_LEGALONE.md Fase 2."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def test_metodo_inseguro_foi_removido():
    assert getattr(LegalOneCadastro, "_preencher_lookups_edicao", None) is None


def test_realizar_acoes_pos_cadastro_nao_chama_mais_o_metodo_removido():
    src = inspect.getsource(LegalOneCadastro.realizar_acoes_pos_cadastro)
    assert "_preencher_lookups_edicao" not in src


def test_orgao_procedimento_fase_continuam_cobertos_pela_ficha():
    bases = dict(LegalOneCadastro._FICHA_LOOKUPS)
    assert bases.get("Orgao") == ("orgao",)
    assert bases.get("Procedimento") == ("procedimento",)
    assert bases.get("Fase") == ("fase",)


if __name__ == "__main__":
    test_metodo_inseguro_foi_removido()
    test_realizar_acoes_pos_cadastro_nao_chama_mais_o_metodo_removido()
    test_orgao_procedimento_fase_continuam_cobertos_pela_ficha()
    print("ok")
