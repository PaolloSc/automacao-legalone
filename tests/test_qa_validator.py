"""qa_validator.py comparava o valor JA PREENCHIDO no formulario (limpo,
sem papel/CNPJ entre parenteses) contra o dado BRUTO extraido (com
'(Reclamante)', '(Ativo)', CNPJ etc.), gerando falsos avisos de 'campo
VAZIO' / 'valor divergente' mesmo quando o preenchimento estava correto.
"""
from qa_validator import QAValidator


def test_limpar_esperado_remove_papel_e_status_entre_parenteses():
    assert QAValidator._limpar_esperado("Reclamante (Ativo)") == "Reclamante"
    assert QAValidator._limpar_esperado("LIVIA MILENA SOUZA MOREIRA (Reclamante)") == "LIVIA MILENA SOUZA MOREIRA"
    assert QAValidator._limpar_esperado("ITAU UNIBANCO S/A (CNPJ 60.701.190/0001-04)") == "ITAU UNIBANCO S/A"
    assert QAValidator._limpar_esperado("Trabalhista") == "Trabalhista"


def test_valor_campo_usa_leitura_do_cadastro_quando_disponivel():
    class FakeCadastro:
        def _ler_valor_campo_formulario(self, rotulo):
            return {"Posição": "Reclamante"}.get(rotulo)

    qa = QAValidator(page=None, dados_processo={}, cadastro=FakeCadastro())
    assert qa._valor_campo(seletores=[], rotulo="Posição") == "Reclamante"


def test_campo_preenchido_certo_nao_gera_falso_positivo():
    class FakeCadastro:
        def _ler_valor_campo_formulario(self, rotulo):
            return {
                "Posição": "Reclamante",
                "Cliente principal": "LIVIA MILENA SOUZA MOREIRA",
            }.get(rotulo)

    dados = {
        "posicao": "Reclamante (Ativo)",
        "cliente": "LIVIA MILENA SOUZA MOREIRA (Reclamante)",
    }
    qa = QAValidator(page=None, dados_processo=dados, cadastro=FakeCadastro())
    qa._validar_campos_obrigatorios()
    assert qa.warnings == []


if __name__ == "__main__":
    test_limpar_esperado_remove_papel_e_status_entre_parenteses()
    test_valor_campo_usa_leitura_do_cadastro_quando_disponivel()
    test_campo_preenchido_certo_nao_gera_falso_positivo()
    print("OK - qa_validator nao gera mais falso positivo com dado bruto (papel/CNPJ entre parenteses)")
