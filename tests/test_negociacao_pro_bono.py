"""Fase 1 do refactor: campo 'Negociacao de contrato de honorarios' vazio
deve virar 'Pro Bono' + warning de log + flag de correcao manual (nao mais
o default generico 'Negociação padrão'/env var). Ver
PROMPT_REFATORACAO_LEGALONE.md Fase 1, item 7."""
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


def test_default_e_pro_bono_nao_negociacao_padrao():
    trecho = _trecho_negociacao()
    assert "negociacao = 'Pro Bono'" in trecho
    assert "LEGALONE_NEGOCIACAO_PADRAO" not in trecho


def test_loga_warning_explicito():
    trecho = _trecho_negociacao()
    assert "logger.warning(" in trecho


def test_registra_qa_warning_para_correcao_manual():
    trecho = _trecho_negociacao()
    assert "_qa_warnings" in trecho
    assert "Pro Bono" in trecho


if __name__ == "__main__":
    test_default_e_pro_bono_nao_negociacao_padrao()
    test_loga_warning_explicito()
    test_registra_qa_warning_para_correcao_manual()
    print("ok")
