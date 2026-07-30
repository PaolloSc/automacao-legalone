"""Quem e' quem no escritorio, para o Responsavel principal cair sempre na
mesma pessoa.

O que chega da peticao e' o nome como o advogado assina ('Monica Pinheiro'),
que nao e' o nome cadastrado no LegalOne ('Monica Furtado Pinheiro Chagas').
O combobox casava por fuzzy e acertava por sorte: 'Marcela', 'Marcello' e
'Marcelo' sao tres pessoas, e 'Pinheiro' e' sobrenome de duas. O e-mail e'
unico, entao e' ele que vai para a busca.
"""
import re
import unicodedata

EQUIPE = {
    "Ana Luíza Ricardo Oliveira": "atendimento@carvalhofurtadoadv.com.br",
    "André Fortes Chaves": "andre@carvalhofurtadoadv.com.br",
    "Caio César Amaral Franco": "caio@carvalhofurtadoadv.com.br",
    "Gabriel Siqueira Eliazar de Carvalho": "gabriel@carvalhofurtadoadv.com.br",
    "Gabriela Peixoto Mello de Azevedo": "gabriela.azevedo@carvalhofurtadoadv.com.br",
    "Isabela Vicentino Silva": "isabela.vicentino@carvalhofurtadoadv.com.br",
    "Lilian Silveira Correa": "financeiro@carvalhofurtadoadv.com.br",
    "Marcela Leite Kato": "trabalhista3@carvalhofurtadoadv.com.br",
    "Marcello Silva Nunes Leite": "marcello.leite@carvalhofurtadoadv.com.br",
    "Marcelo Pinheiro Chagas": "marcelo@carvalhofurtadoadv.com.br",
    "Marco Tulio Fonseca Furtado": "marcotulio@carvalhofurtadoadv.com.br",
    "Maria Eduarda Ferreira Correa": "maria.eduarda@carvalhofurtadoadv.com.br",
    "Maria Karolyne Moraes Malard": "arquivo@carvalhofurtadoadv.com.br",
    "Mariana Krollmann Fogli": "mariana@carvalhofurtadoadv.com.br",
    "Mônica Furtado Pinheiro Chagas": "monica@carvalhofurtadoadv.com.br",
    "Natália Xavier Cunha": "natalia@carvalhofurtadoadv.com.br",
    "Paollo Sanchez": "paollo.sanchez@carvalhofurtadoadv.com.br",
    "Sérgio Adolfo Eliazar de Carvalho": "sergio.carvalho@carvalhofurtadoadv.com.br",
    "Victor Barbosa Horta": "victor.horta@carvalhofurtadoadv.com.br",
}


def _tokens(texto: str) -> set[str]:
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    # 'de', 'da', 'do' aparecem em varios nomes e nao distinguem ninguem.
    return {p for p in re.split(r'[^a-z0-9]+', t.lower()) if len(p) > 2 and p not in
            ('dos', 'das')}


def resolver(nome: str) -> tuple[str, str] | None:
    """Nome como veio da peticao -> (nome cadastrado, e-mail). None se ambiguo.

    Vence quem tem mais tokens em comum, e so se estiver sozinho na frente:
    'Marcelo Pinheiro' e 'Monica Pinheiro' nao podem virar a mesma pessoa.
    """
    pedido = _tokens(nome)
    if not pedido:
        return None
    if '@' in str(nome):  # ja veio o e-mail
        for n, e in EQUIPE.items():
            if e.lower() == nome.strip().lower():
                return n, e
    placar = sorted(((len(pedido & _tokens(n)), n) for n in EQUIPE), reverse=True)
    melhor, nome_cad = placar[0]
    if melhor == 0 or (len(placar) > 1 and placar[1][0] == melhor):
        return None
    return nome_cad, EQUIPE[nome_cad]


if __name__ == "__main__":
    assert resolver("Monica Pinheiro")[1] == "monica@carvalhofurtadoadv.com.br"
    assert resolver("Mônica Furtado Pinheiro Chagas")[1] == "monica@carvalhofurtadoadv.com.br"
    assert resolver("Marcelo Pinheiro Chagas")[1] == "marcelo@carvalhofurtadoadv.com.br"
    assert resolver("Pinheiro") is None          # sobrenome de duas pessoas
    assert resolver("Fulano de Tal") is None     # nao e' do escritorio
    print("ok")
