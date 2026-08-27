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


def test_cadastrar_processo_nao_chama_valores_monetarios_antes_do_save():
    """A chamada antes do clicar_salvar() era no-op (tela Angular nao tem
    os ids de _FICHA_LOOKUPS/_PERSONALIZADOS_*) e misturava Fase 3 dentro
    da Fase 1."""
    src = inspect.getsource(LegalOneCadastro.cadastrar_processo)
    idx_salvar = src.index("if not self.clicar_salvar():")
    trecho_antes_do_save = src[:idx_salvar]
    assert "_aplicar_valores_monetarios" not in trecho_antes_do_save


if __name__ == "__main__":
    test_metodo_inseguro_foi_removido()
    test_realizar_acoes_pos_cadastro_nao_chama_mais_o_metodo_removido()
    test_orgao_procedimento_fase_continuam_cobertos_pela_ficha()
    test_cadastrar_processo_nao_chama_valores_monetarios_antes_do_save()
    print("ok")
