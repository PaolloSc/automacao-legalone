"""Forms: quando a tela de respostas nao abre, tem que FALHAR, nao inventar.

13/08/2026, 15:50-16:12: o botao 'Verificar resultados individuais' nao foi
encontrado, o log disse "✅ Forms aberto" mesmo assim, a captura estruturada
voltou vazia e o extrator devolveu um dict raspado da tela de EDICAO do Forms:
tipo_cadastro='75', cnj='. . .', cliente='BUFFET', fase='236'. So' o guard de
CNJ (automacao_legalone_completa.py:731) impediu que isso virasse cadastro.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forms_extractor import FormsExtractor


class _Locator:
    def __init__(self, n):
        self._n = n

    async def count(self):
        return self._n

    @property
    def first(self):
        return self

    async def click(self, **kw):
        raise AssertionError("nao deveria clicar neste teste")


class _Page:
    """Pagina onde a view de resposta individual NAO existe."""

    def __init__(self, tem_entrevistado=False):
        self.tem_entrevistado = tem_entrevistado

    def locator(self, selector):
        achou = self.tem_entrevistado and "Entrevistado" in selector
        return _Locator(1 if achou else 0)

    async def title(self):
        return "Microsoft Forms"


def _extrator(page):
    ex = object.__new__(FormsExtractor)
    ex._page = page
    ex._forms_aberto = False
    ex.erro_extracao = None
    return ex


def test_view_individual_ausente_nao_e_sucesso():
    ex = _extrator(_Page(tem_entrevistado=False))
    assert asyncio.run(ex._confirmar_resultados_individuais()) is False
    assert ex._forms_aberto is False
    assert ex.erro_extracao and "resultados individuais" in ex.erro_extracao


def test_url_do_email_vira_view_de_resposta_individual():
    """Sem `topview=SurveyResults` a pagina abre no EDITOR e so' se chega nas
    respostas clicando no botao/menu '...' — o caminho que quebrou."""
    do_email = ("https://forms.office.com/Pages/DesignPage.aspx#FormId=Aosws2Ax"
                "O0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUQTUwVjlNRENJT1k3UDI0UElCMVE3"
                "T1lVVS4u&Analysis=true&origin=EmailNotification")
    url = FormsExtractor._url_respostas_individuais(do_email)
    assert "topview=SurveyResults" in url
    assert "id=Aosws2AxO0aLjMsPVW9Od" in url
    assert FormsExtractor._url_respostas_individuais("https://exemplo.com") is None


def test_ja_na_view_nao_procura_botao():
    """Com a URL certa o campo ja' esta' na tela: nada de aba nem menu '...'."""
    ex = _extrator(_Page(tem_entrevistado=True))
    assert asyncio.run(ex._esta_em_resultados_individuais()) is True
    assert asyncio.run(_extrator(_Page(False))._esta_em_resultados_individuais()) is False


def test_view_individual_presente_e_sucesso():
    ex = _extrator(_Page(tem_entrevistado=True))
    assert asyncio.run(ex._confirmar_resultados_individuais()) is True
    assert ex._forms_aberto is True
    assert ex.erro_extracao is None
