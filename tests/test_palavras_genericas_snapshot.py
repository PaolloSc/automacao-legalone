"""_PALAVRAS_GENERICAS e' uma lista hand-maintained que ja precisou de 2
correcoes ao vivo (Paraiba/Sao Paulo 14/08, Agravantes/Agravante 17/08) e
e' compartilhada por TODOS os lookups jQuery (_preencher_lookup_por_id) --
nao so' tribunal. Um redesign de verdade (ex.: genericidade calculada por
frequencia nas opcoes visiveis em vez de lista fixa) exigiria um caso de
falha real pra testar contra, que nao existe hoje -- entao esta suite so'
trava o comportamento ATUAL (ver review de 31/08/2026), sem mudar a
logica. Objetivo: qualquer edicao futura na lista vira um diff visivel
neste teste, revisado de proposito, em vez de um efeito colateral mudo em
outro campo de lookup (Natureza, Classe, etc.) que compartilha a mesma
lista."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro


def test_palavras_genericas_atuais():
    esperado = {
        "de", "do", "da", "dos", "das", "e", "a", "o", "as", "os",
        "no", "na", "nos", "nas", "em", "por", "para", "com", "sem",
        "tribunal", "justica", "estado", "juizo", "vara", "turma",
        "camara", "secao", "regiao", "grau", "instancia", "foro",
        "comarca", "federal", "estadual", "regional", "superior", "civel",
    }
    assert LegalOneCadastro._PALAVRAS_GENERICAS == esperado, (
        "_PALAVRAS_GENERICAS mudou -- confirme que a mudanca foi "
        "deliberada (ela afeta TODOS os lookups jQuery, nao so' tribunal) "
        "e atualize este snapshot."
    )


def test_lookup_nao_relacionado_a_tribunal_nao_e_afetado_por_palavra_generica_isolada():
    """Sanidade da coacoplagem entre paths: um campo generico qualquer
    ('Natureza', 'Classe' etc.) cujas opcoes nao compartilham nenhuma
    palavra 'juridica boilerplate' continua vetado corretamente -- a
    lista de tribunal nao introduz falso-positivo aqui."""
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    assert not bot._compartilha_identidade(["Indenizatoria"], "Trabalhista")
    assert bot._compartilha_identidade(["Indenizatoria"], "Indenizatoria")


if __name__ == "__main__":
    test_palavras_genericas_atuais()
    test_lookup_nao_relacionado_a_tribunal_nao_e_afetado_por_palavra_generica_isolada()
    print("ok")
