"""Regressao 13/08/2026: logo apos navegar/avancar de resposta no Forms, a
tela ainda mostra 'Lendo suas respostas...' (loading) e varios campos com
'. . .' — extrair nesse instante grava esse texto como valor de CADA
pergunta, inclusive o CNJ, e o processo falha rio abaixo com
'CNJ ausente ou invalido na extracao'. _aguardar_resposta_carregada() tem
que segurar ate o placeholder sumir."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forms_extractor import FormsExtractor


class _BodyLocatorFake:
    def __init__(self, textos):
        self._textos = list(textos)
        self.chamadas = 0

    async def inner_text(self):
        idx = min(self.chamadas, len(self._textos) - 1)
        self.chamadas += 1
        return self._textos[idx]


class _PageFake:
    def __init__(self, textos):
        self.body = _BodyLocatorFake(textos)

    def locator(self, sel):
        assert sel == 'body'
        return self.body


def _sem_sleep_real(fn):
    orig_sleep = asyncio.sleep

    async def _rapido(_s):
        return None

    async def _run():
        asyncio.sleep = _rapido
        try:
            await fn()
        finally:
            asyncio.sleep = orig_sleep

    asyncio.run(_run())


def test_espera_ate_placeholder_de_loading_sumir():
    ex = FormsExtractor(use_firecrawl=False)
    ex._page = _PageFake(
        ['Lendo suas respostas...', 'Lendo suas respostas...', 'CNJ: 1234567-89.2026.8.13.0000'])

    _sem_sleep_real(lambda: ex._aguardar_resposta_carregada(tentativas=8))

    assert ex._page.body.chamadas == 3  # parou assim que sumiu o placeholder


def test_desiste_apos_esgotar_tentativas_sem_travar():
    ex = FormsExtractor(use_firecrawl=False)
    ex._page = _PageFake(['Lendo suas respostas...'])  # nunca some

    _sem_sleep_real(lambda: ex._aguardar_resposta_carregada(tentativas=3))

    assert ex._page.body.chamadas == 3  # nao trava: consome so' as tentativas


if __name__ == "__main__":
    test_espera_ate_placeholder_de_loading_sumir()
    test_desiste_apos_esgotar_tentativas_sem_travar()
    print("OK")
