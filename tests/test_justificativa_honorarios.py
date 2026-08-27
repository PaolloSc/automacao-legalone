"""Fase 3 do refactor: se a cobranca de honorarios (sucumbenciais ou
contratuais de exito) foi respondida 'Nao', a justificativa correspondente
e' obrigatoria. Como a automacao nao pode inventar o texto, a regra vira
aviso em _qa_warnings (mesmo canal que alimenta o e-mail de conclusao).
Ver PROMPT_REFATORACAO_LEGALONE.md Fase 3, itens 5 e 6."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def _instancia():
    """Instancia sem __init__ (evita abrir navegador) - so' precisa dos
    metodos puros usados pela validacao."""
    return LegalOneCadastro.__new__(LegalOneCadastro)


def test_nao_sem_justificativa_gera_aviso():
    cad = _instancia()
    dados = {
        'cobranca_honorarios_sucumbenciais': 'Não',
        'cobranca_honorarios_contratuais_exito': 'Sim',
    }
    avisos = cad._validar_justificativas_honorarios(dados)
    assert len(avisos) == 1
    assert 'sucumbenciais' in avisos[0].lower()
    assert dados['_qa_warnings'] == avisos


def test_nao_com_justificativa_nao_gera_aviso():
    cad = _instancia()
    dados = {
        'cobranca_honorarios_sucumbenciais': 'Não',
        'justificativa_nao_cobranca_honorarios_sucumbenciais': 'Acordo extrajudicial cobre os honorarios.',
    }
    avisos = cad._validar_justificativas_honorarios(dados)
    assert avisos == []


def test_sim_nunca_exige_justificativa():
    cad = _instancia()
    dados = {
        'cobranca_honorarios_sucumbenciais': 'Sim',
        'cobranca_honorarios_contratuais_exito': 'Sim',
    }
    assert cad._validar_justificativas_honorarios(dados) == []


def test_ambas_nao_sem_justificativa_gera_dois_avisos():
    cad = _instancia()
    dados = {
        'cobranca_honorarios_sucumbenciais': 'Não',
        'cobranca_honorarios_contratuais_exito': 'Não',
    }
    assert len(cad._validar_justificativas_honorarios(dados)) == 2


if __name__ == "__main__":
    test_nao_sem_justificativa_gera_aviso()
    test_nao_com_justificativa_nao_gera_aviso()
    test_sim_nunca_exige_justificativa()
    test_ambas_nao_sem_justificativa_gera_dois_avisos()
    print("ok")
