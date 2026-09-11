"""Quando o Forms nao traz negociacao de honorarios explicita mas o campo JA
TEM um valor (ex.: auto-sugestao do LegalOne ao selecionar o Cliente
Principal), a automacao deve MANTER esse valor -- nao sobrescrever com
'Pro Bono'. So cai no fallback Pro Bono quando o campo esta' REALMENTE
vazio. Achado ao vivo 11/09/2026: sobrescrevia 'Hon - 0000379' (valor real,
'Contrato de honorarios: PENDENTE' no Forms) com 'Pro Bono' so' porque essa
natureza de Forms nao pergunta negociacao explicitamente.

Complementa test_negociacao_pro_bono.py (que trava o caso campo vazio -> Pro
Bono, PROMPT_REFATORACAO_LEGALONE.md Fase 1 item 7) checando o caso campo
JA PREENCHIDO -> mantem.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _trecho_negociacao():
    src = inspect.getsource(LegalOneCadastro.preencher_campos_obrigatorios)
    inicio = src.index("# 5. Negociação de contrato de honorários")
    fim = src.index("# 6. Data da baixa")
    return src[inicio:fim]


def test_campo_ja_preenchido_e_mantido_sem_forms():
    trecho = _trecho_negociacao()
    assert "elif valor_atual_negociacao:" in trecho
    # o ramo do "campo ja tem algo, Forms nao trouxe nada" nao pode
    # sobrescrever com Pro Bono -- so' loga e segue.
    bloco_manter = trecho[trecho.index("elif valor_atual_negociacao:"):trecho.index("else:", trecho.index("elif valor_atual_negociacao:"))]
    # o ramo "mantem" nao pode CHAMAR o preenchimento do campo -- so' loga e segue.
    assert "preencher_campo_autocomplete" not in bloco_manter
    assert "pulando" in bloco_manter


def test_pro_bono_so_quando_campo_realmente_vazio():
    trecho = _trecho_negociacao()
    # o ramo Pro Bono e' o ULTIMO else, alcancado so' quando nem Forms nem
    # o campo ja preenchido deram valor.
    idx_elif = trecho.index("elif valor_atual_negociacao:")
    idx_else = trecho.index("else:", idx_elif)
    idx_pro_bono = trecho.index("negociacao = 'Pro Bono'")
    assert idx_pro_bono > idx_else > idx_elif


if __name__ == "__main__":
    test_campo_ja_preenchido_e_mantido_sem_forms()
    test_pro_bono_so_quando_campo_realmente_vazio()
    print("ok")
