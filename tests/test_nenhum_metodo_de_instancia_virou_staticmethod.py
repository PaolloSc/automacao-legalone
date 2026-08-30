"""Regressao 27/08/2026: apagar um metodo deixou o @staticmethod da linha
de cima orfao, e ele passou a decorar o metodo seguinte por engano
(_preencher_lookup_antigo virou staticmethod sem querer, quebrando 4
call sites em runtime com TypeError). hasattr() nao pega isso -- um
staticmethod ainda passa hasattr. Precisa inspecionar o descriptor cru."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from legalone_cadastro import LegalOneCadastro


def _metodos_de_instancia_por_assinatura():
    """Nomes de metodos cujo primeiro parametro declarado e' 'self' --
    isso e' o que faz um metodo ser 'de instancia' na intencao do autor,
    independente de como o Python acabou o decorando."""
    nomes = []
    for nome, descriptor in vars(LegalOneCadastro).items():
        # Precisamos extrair a funcao subjacente se o descriptor for um staticmethod/classmethod
        valor = descriptor
        if isinstance(descriptor, staticmethod):
            valor = descriptor.__func__
        elif isinstance(descriptor, classmethod):
            valor = descriptor.__func__

        if not inspect.isfunction(valor):
            continue
        try:
            params = list(inspect.signature(valor).parameters)
        except (ValueError, TypeError):
            continue
        if params and params[0] == 'self':
            nomes.append(nome)
    return nomes


@pytest.mark.parametrize("nome", _metodos_de_instancia_por_assinatura())
def test_metodo_com_self_nao_e_staticmethod(nome):
    descriptor_cru = inspect.getattr_static(LegalOneCadastro, nome)
    assert not isinstance(descriptor_cru, staticmethod), (
        f"{nome} tem 'self' como primeiro parametro mas foi decorado como "
        "staticmethod -- provavelmente um @staticmethod orfao de um metodo "
        "deletado ao lado (ver bug de 27/08/2026 em _preencher_lookup_antigo)"
    )


if __name__ == "__main__":
    for _n in _metodos_de_instancia_por_assinatura():
        test_metodo_com_self_nao_e_staticmethod(_n)
    print("ok")
