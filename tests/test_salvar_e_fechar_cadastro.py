"""Fase 3 do refactor sequencial: 'Salvar e fechar' vira metodo proprio em
vez de logica duplicada inline dentro de realizar_acoes_pos_cadastro
(ver PROMPT_REFATORACAO_LEGALONE.md, requisito 'salvar_e_fechar_cadastro')."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def test_metodo_salvar_e_fechar_cadastro_existe():
    assert callable(getattr(LegalOneCadastro, "salvar_e_fechar_cadastro", None))


def test_realizar_acoes_pos_cadastro_chama_o_metodo_extraido():
    src = inspect.getsource(LegalOneCadastro.realizar_acoes_pos_cadastro)
    assert "self.salvar_e_fechar_cadastro()" in src
    # a lista de seletores duplicada nao pode mais estar inline aqui
    assert 'button[name="ButtonSave"][value="0"]' not in src


def test_metodo_extraido_tem_os_mesmos_seletores_de_antes():
    src = inspect.getsource(LegalOneCadastro.salvar_e_fechar_cadastro)
    assert 'button[name="ButtonSave"][value="0"]' in src
    assert 'Salvar e fechar' in src


if __name__ == "__main__":
    test_metodo_salvar_e_fechar_cadastro_existe()
    test_realizar_acoes_pos_cadastro_chama_o_metodo_extraido()
    test_metodo_extraido_tem_os_mesmos_seletores_de_antes()
    print("ok")
