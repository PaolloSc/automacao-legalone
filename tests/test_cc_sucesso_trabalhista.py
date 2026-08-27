"""Sucesso trabalhista sempre copia a Monica.

Pedido: todo cadastro trabalhista concluido com sucesso sai com
monica@carvalhofurtadoadv.com.br em CC. A natureza pode vir dos dados do
processo ou do assunto do e-mail do Forms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automacao_legalone_completa import AutomacaoLegalOne

MONICA = "monica@carvalhofurtadoadv.com.br"


def test_natureza_trabalhista_copia_monica():
    cc = AutomacaoLegalOne._cc_sucesso({}, {"natureza": "Trabalhista"})
    assert cc == [MONICA]


def test_assunto_trabalhista_copia_monica():
    email = {"subject": "Cadastro de processos NOVOS LegalOne trabalhista"}
    assert AutomacaoLegalOne._cc_sucesso(email, {}) == [MONICA]


def test_civel_nao_copia_ninguem():
    assert AutomacaoLegalOne._cc_sucesso({}, {"natureza": "Cível"}) == []
    assert AutomacaoLegalOne._cc_sucesso(None, None) == []
