"""O ciclo de 11/08/2026 que mandou e-mail de sucesso sem cadastrar nada.

Sessao do Forms expirada -> a pagina de respostas carrega sem conteudo -> o
extrator raspa o texto da tela e devolve CNJ '. . .' (o '...' do menu) -> o
bot vai ao LegalOne, a pesquisa nao acha nada, ele continua na tela de
Pesquisa e conclui "processo ja cadastrado" -> "[OK] PROCESSO CADASTRADO!".

Duas travas, uma em cada ponta: CNJ sem os 20 digitos nao sai da extracao, e
"ja existe" exige prova na tela em vez da URL.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automacao_legalone_completa import cnj_valido  # noqa: E402
from legalone_cadastro import LegalOneCadastro  # noqa: E402

CNJ = '0010307-23.2026.5.03.0089'


def test_cnj_valido_recusa_texto_raspado_da_tela():
    assert cnj_valido(CNJ)
    assert cnj_valido('00103072320265030089')
    assert not cnj_valido('. . .')          # o que passou em 11/08
    assert not cnj_valido('')
    assert not cnj_valido(None)
    assert not cnj_valido('Mais detalhes 328 Respostas')
    assert not cnj_valido('0010307-23.2026.5.03.008')   # 19 digitos


class PageFake:
    def __init__(self, *, linhas_grid=(), corpo=''):
        self.linhas_grid = list(linhas_grid)
        self.corpo = corpo

    def evaluate(self, script, arg=None):
        assert 'grid-edit-action-row' in script, script[:60]
        so_digitos = lambda t: ''.join(c for c in t if c.isdigit())  # noqa: E731
        return any(arg in so_digitos(linha) for linha in self.linhas_grid)

    def inner_text(self, _seletor):
        return self.corpo


def _bot(page):
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    bot.page = page
    return bot


def test_linha_da_grid_com_o_cnj_e_prova():
    bot = _bot(PageFake(linhas_grid=[f'Alterar {CNJ} Reclamante X']))
    assert bot._ja_cadastrado_com_prova(CNJ) is True


def test_aviso_ja_cadastrado_e_prova():
    bot = _bot(PageFake(corpo=f'O numero {CNJ} ja encontra-se cadastrado na pasta Proc - 0007349.'))
    assert bot._ja_cadastrado_com_prova(CNJ) is True


def test_pesquisa_vazia_nao_e_prova():
    """A tela de Pesquisa sem resultado — o caso de 11/08."""
    bot = _bot(PageFake(corpo='Nenhum registro encontrado.'))
    assert bot._ja_cadastrado_com_prova(CNJ) is False


def test_cnj_no_corpo_sozinho_nao_e_prova():
    """'nenhum resultado para <CNJ>' tem o CNJ e significa o contrario."""
    bot = _bot(PageFake(corpo=f'Nenhum resultado encontrado para {CNJ}.'))
    assert bot._ja_cadastrado_com_prova(CNJ) is False


def test_sem_cnj_nao_ha_prova_possivel():
    """Sem isso a trava morre justamente no caso que a criou: CNJ '. . .'."""
    corpo = 'O numero ja encontra-se cadastrado na pasta Proc - 0007349.'
    assert _bot(PageFake(corpo=corpo))._ja_cadastrado_com_prova('. . .') is False
    assert _bot(PageFake(corpo=corpo))._ja_cadastrado_com_prova('') is False
    assert _bot(PageFake(corpo=corpo))._ja_cadastrado_com_prova(None) is False


def test_extracao_lixo_nao_chega_no_legalone(monkeypatch):
    """O incidente inteiro: CNJ '. . .' tem que morrer antes do LegalOne."""
    from fixtures.copilot_payloads import LIVIA_ITAU_LIMPO, email_data_copilot
    from test_e2e_mock_pipeline import _montar_automacao_fake

    bot = _montar_automacao_fake(monkeypatch)
    bot.processar_email(email_data_copilot({**LIVIA_ITAU_LIMPO, 'cnj': '. . .'}))

    assert bot.legalone.chamadas == [], 'lixo chegou no LegalOne'
    assert bot.stats['erros'] == 1
    assert bot.stats['processos_cadastrados'] == 0
    bot.salvar_log_erro.assert_called_once()      # e-mail de erro, nao de sucesso
    bot._enviar_email_sucesso.assert_not_called()


if __name__ == '__main__':
    for nome, fn in sorted(globals().items()):
        if nome.startswith('test_'):
            fn()
            print(f'ok {nome}')
