"""Taxa de improcedencia por assunto, medida no DataJud (API publica do CNJ).

Para que serve: o agente do Copilot chuta `risco` a partir do que o modelo
"acha" da jurisprudencia. Aqui a frequencia e' contada de verdade -- entre os
processos que tem aquele assunto e ja' receberam sentenca de merito, quantos
foram julgados improcedentes.

Por que gerar um arquivo em vez de consultar ao vivo: metade das chamadas ao
DataJud publico volta 429/504, e a taxa e' estatistica estavel (milhoes de
processos). Roda-se isto de tempos em tempos e o .md vira Conhecimento do
agente.

    python jurimetria_datajud.py            # TRT3
    python jurimetria_datajud.py trt3 tjmg  # varios
    python jurimetria_datajud.py --todos    # todos os tribunais do DataJud

O STF nao entra: a base do CNJ cobre STJ, TST, TSE, STM, TRFs, TJs e TRTs; o
Supremo tem base propria, fora desta API.

Limite conhecido: o movimento de sentenca e' do PROCESSO, nao do pedido. Uma
reclamacao com 12 pedidos julgada "procedente em parte" (o caso de ~70% deles)
nao diz qual pedido caiu. O que discrimina e' a taxa de improcedencia TOTAL de
quem pede aquilo, comparada com a media -- e' assim que a tabela deve ser lida.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# Chave publica que o CNJ divulga na documentacao da API.
CHAVE = ("APIKey cDZHYzlZa0JadVREZDJCendQbXY6"
         "SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==")

# Tribunal superior nao julga merito: julga recurso. Onde a vara registra
# "Improcedencia" (codigo TPU 220), o STJ/TST registra "Nao-Provimento". Sao
# duas metricas diferentes com a mesma leitura -- desfecho contrario a quem
# pediu -- entao cada indice usa a sua.
SUPERIORES = ("stj", "tst", "tse", "stm")

# Abaixo disso a distancia entre os tercis nao separa nada de util.
LARGURA_MINIMA = 3.0

# Casam por keyword: tem de vir acentuado exatamente como esta' no indice.
_NEGADOS = ["Não-Provimento", "Não Conhecimento de recurso",
            "Negação de Seguimento"]
_PROVIDOS = ["Provimento", "Provimento em Parte"]

METRICAS = {
    "merito": {
        "rotulo": "Improcedencia",
        "decididos": {"terms": {"movimentos.codigo": [219, 220, 221]}},
        "contra": {"term": {"movimentos.codigo": 220}},
    },
    "recurso": {
        "rotulo": "Recurso negado",
        "decididos": {"terms": {"movimentos.nome.keyword": _NEGADOS + _PROVIDOS}},
        "contra": {"terms": {"movimentos.nome.keyword": _NEGADOS}},
    },
}

# O corte e' por tercil da propria distribuicao de assuntos, nao um numero
# fixo: 22% de improcedencia e' pouco num tribunal que rejeita 28% e muito num
# que rejeita 15%. Media nao serve de ancora aqui -- a distribuicao tem cauda
# longa a direita e a media fica acima da maioria dos assuntos.


ESTADOS = ("ac al am ap ba ce dft es go ma mg ms mt pa pb pe pi pr rj rn ro rr"
           " rs sc se sp to").split()

# Ordem do CNJ para o codigo TR da Justica Estadual (Res. CNJ 65/2008): e'
# alfabetica pelo NOME do estado, nao pela sigla -- por isso Mato Grosso vem
# antes de Mato Grosso do Sul e Parana antes de Pernambuco. Nao reaproveite
# ESTADOS aqui, que esta' ordenado por sigla e daria outro tribunal.
_TR_ESTADUAL = ("ac al ap am ba ce dft es go ma mt ms mg pa pb pr pe pi rj rn"
                " rs ro rr sc se sp to").split()
# Eleitoral (TREs) e militar (TJMs) ficam de fora: nao e' materia do
# escritorio e sao +30 consultas lentas. Basta acrescentar aqui se precisar.
TRIBUNAIS = (["stj", "tst", "tse", "stm"]
             + [f"trf{n}" for n in range(1, 7)]
             + [f"tj{uf}" for uf in ESTADOS]
             + [f"trt{n}" for n in range(1, 25)])


def consultar(alias: str, corpo: dict, tentativas: int = 8) -> dict | None:
    """POST no indice do tribunal. 429/504 sao a regra, nao a excecao."""
    url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{alias}/_search"
    dados = json.dumps(corpo).encode()
    for i in range(tentativas):
        req = urllib.request.Request(url, dados, {
            "Authorization": CHAVE, "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
        except Exception as e:
            print(f"  [{alias}] tentativa {i+1}: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
            continue
        if "error" in r:
            print(f"  [{alias}] tentativa {i+1}: {r['error'].get('type')}",
                  file=sys.stderr)
            time.sleep(5 * (i + 1))
            continue
        return r
    return None


def alias_do_cnj(cnj: str) -> str | None:
    """NNNNNNN-DD.AAAA.J.TR.OOOO -> indice do DataJud.

    O proprio numero diz o tribunal: J e' o segmento e TR o tribunal dentro
    dele. Vale mais que o campo 'tribunal' que vem do Forms, que e' texto
    digitado por gente.
    """
    d = re.sub(r"\D", "", cnj or "")
    if len(d) != 20:
        return None
    segmento, tr = d[13], int(d[14:16])
    if segmento == "5" and 1 <= tr <= 24:
        return f"trt{tr}"
    if segmento == "4" and 1 <= tr <= 6:
        return f"trf{tr}"
    if segmento == "8" and 1 <= tr <= len(_TR_ESTADUAL):
        return f"tj{_TR_ESTADUAL[tr - 1]}"
    if segmento == "3":
        return "stj"
    return None  # eleitoral, militar, STF: fora do que geramos


def capa(cnj: str) -> dict | None:
    """Capa do processo no DataJud: vara, classe, distribuicao e assuntos TPU.

    Nao traz partes nem valor da causa -- isso vem da peticao. O que interessa
    aqui e' o codigo TPU do assunto, que casa exato com a tabela de jurimetria
    em vez de casar por nome.
    """
    alias = alias_do_cnj(cnj)
    if not alias:
        return None
    digitos = re.sub(r"\D", "", cnj)
    r = consultar(alias, {"size": 1,
                          "query": {"match": {"numeroProcesso": digitos}}})
    if not r or not r["hits"]["hits"]:
        return None
    s = r["hits"]["hits"][0]["_source"]
    return {
        "tribunal": alias,
        "numeroProcesso": s.get("numeroProcesso"),
        "grau": s.get("grau"),
        "classe": (s.get("classe") or {}).get("nome"),
        "orgao_julgador": (s.get("orgaoJulgador") or {}).get("nome"),
        "data_ajuizamento": _data(s.get("dataAjuizamento")),
        "assuntos": [{"codigo": a.get("codigo"), "nome": a.get("nome")}
                     for a in (s.get("assuntos") or [])],
    }


def _data(aaaammdd: str | None) -> str | None:
    """20230714000000 -> 14/07/2023 (formato que o LegalOne espera)."""
    d = (aaaammdd or "")[:8]
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else None


def grau_de(alias: str) -> str | None:
    """1o grau nos tribunais que tem varas; nos superiores nao ha' G1."""
    return None if alias in SUPERIORES else "G1"


def metrica_de(alias: str) -> dict:
    return METRICAS["recurso" if alias in SUPERIORES else "merito"]


def taxas(alias: str, quantos: int = 60) -> list[dict]:
    """Uma unica consulta: top assuntos, e dentro de cada um a contagem de
    decididos e de desfechos contrarios a quem pediu."""
    grau, m = grau_de(alias), metrica_de(alias)
    r = consultar(alias, {
        "size": 0,
        # `grau` e' texto analisado: term em "G1" nao casa, match casa.
        "query": ({"match": {"grau": grau}} if grau else {"match_all": {}}),
        "aggs": {"assunto": {
            "terms": {"field": "assuntos.nome.keyword", "size": quantos},
            # O codigo TPU do proprio assunto do bucket: ele esta' em TODOS os
            # processos do bucket, entao e' o mais frequente. Sem ele a tabela
            # so' casa por texto -- que e' o que o codigo existe para evitar.
            "aggs": {"decididos": {"filter": m["decididos"]},
                     "contra": {"filter": m["contra"]},
                     "codigo": {"terms": {"field": "assuntos.codigo",
                                          "size": 1}}}}},
    })
    if not r:
        return []
    linhas = []
    for b in r["aggregations"]["assunto"]["buckets"]:
        decididos = b["decididos"]["doc_count"]
        if decididos < 500:  # amostra pequena demais para virar percentual
            continue
        pct = 100 * b["contra"]["doc_count"] / decididos
        cods = (b.get("codigo") or {}).get("buckets") or [{}]
        linhas.append({"codigo": cods[0].get("key"), "assunto": b["key"],
                       "decididos": decididos, "taxa": round(pct, 1)})
    linhas.sort(key=lambda x: x["taxa"])
    # Tribunal pequeno (ou indice recem-repovoado) pode nao ter NENHUM assunto
    # com amostra: `cortes` de lista vazia estourava IndexError, e quem chamava
    # via CLI so' via "list index out of range" em vez do motivo.
    if not linhas:
        return []
    ca, cb = cortes([l["taxa"] for l in linhas])
    for l in linhas:
        l["risco"] = risco(l["taxa"], ca, cb)
    return linhas


def cortes(pcts: list[float]) -> tuple[float, float]:
    """Tercis: 1/3 dos assuntos vira Alto, 1/3 Medio, 1/3 Baixo."""
    s = sorted(pcts)
    n = len(s)
    return s[n // 3], s[2 * n // 3]


def risco(taxa_contra: float, corte_alto: float, corte_baixo: float) -> str:
    """Risco de quem se DEFENDE do pedido: rejeitado pouco = ameaca alta."""
    if taxa_contra < corte_alto:
        return "Alto"
    if taxa_contra > corte_baixo:
        return "Baixo"
    return "Medio"


def baseline(alias: str) -> float | None:
    grau, m = grau_de(alias), metrica_de(alias)
    r = consultar(alias, {
        "size": 0,
        "query": ({"match": {"grau": grau}} if grau else {"match_all": {}}),
        "aggs": {"decididos": {"filter": m["decididos"]},
                 "contra": {"filter": m["contra"]}},
    })
    if not r or not r["aggregations"]["decididos"]["doc_count"]:
        return None
    return round(100 * r["aggregations"]["contra"]["doc_count"]
                 / r["aggregations"]["decididos"]["doc_count"], 1)


def markdown(alias: str) -> str:
    grau, m = grau_de(alias), metrica_de(alias)
    base = baseline(alias)
    if not base:
        raise RuntimeError(f"{alias}: DataJud nao devolveu o baseline")
    linhas = taxas(alias)
    if len(linhas) < 6:  # tercil de uma lista minuscula nao significa nada
        raise RuntimeError(f"{alias}: so {len(linhas)} assuntos com amostra")
    ca, cb = cortes([l["taxa"] for l in linhas])
    rot = m["rotulo"]
    out = [
        f"# Jurimetria {alias.upper()} -"
        f" {'1o grau' if grau else 'recursos, todos os graus'}"
        " (fonte: DataJud/CNJ)",
        "",
        f"Media do tribunal: **{base}%** de {rot.lower()} entre os processos"
        f" {'com sentenca de merito' if grau else 'com recurso julgado'}.",
        "",
        "Como ler: a taxa e' do PROCESSO que contem aquele pedido, nao do"
        " pedido isolado. Serve para comparar com a media -- pedido rejeitado"
        " MENOS que a media e' o que mais ameaca quem se defende.",
        "",
        "So vale para pedido CONTENCIOSO. Materia sem lide (inventario,"
        " divorcio consensual, jurisdicao voluntaria) quase nunca da'"
        " improcedente, entao aparece como risco Alto sem querer dizer nada."
        " Ignore a linha nesses casos.",
        "",
        f"`risco`: {rot.lower()} < {ca}% = Alto | ate' {cb}% = Medio |"
        " acima = Baixo (tercis desta tabela).",
        "",
        # Tribunal que nega quase tudo (o TST nega 90% dos recursos) espreme
        # os tercis em 1 ponto percentual: ai' o rotulo entre linhas vizinhas
        # e' ruido, e so' os extremos da tabela dizem alguma coisa.
        (f"ATENCAO: neste tribunal os tercis ficam a menos de {LARGURA_MINIMA}"
         " pontos um do outro, entao o rotulo `risco` so' e' confiavel nos"
         " extremos da tabela. No meio, use a porcentagem, nao o rotulo."
         if cb - ca < LARGURA_MINIMA else ""),
        "",
        # A coluna do codigo TPU e' o que o bot casa (o nome varia de grafia
        # entre tribunal e peticao); o nome fica para quem le'.
        f"| Codigo | Pedido (assunto TPU) | Decididos | {rot} | risco |",
        "|---:|---|---:|---:|---|",
    ]
    for l in linhas:
        out.append(f'| {l["codigo"] if l["codigo"] is not None else ""} |'
                   f' {l["assunto"]} | {l["decididos"]} |'
                   f' {l["taxa"]}% | {l["risco"]} |')
    out += ["", f"Gerado por `jurimetria_datajud.py` em"
                f" {time.strftime('%d/%m/%Y')}."]
    return "\n".join(out)


def demo():
    assert cortes([10, 20, 30, 40, 50, 60]) == (30, 50)
    # Nenhum assunto com amostra: `taxas` devolve vazio em vez de estourar em
    # `cortes` (quem reporta o motivo e' o markdown()). trf5 e trt18 caiam
    # aqui com "list index out of range" em 13/08/2026.
    real = globals()["consultar"]
    globals()["consultar"] = lambda *a, **k: {"aggregations": {"assunto": {
        "buckets": [{"key": "Assunto raro", "decididos": {"doc_count": 3},
                     "contra": {"doc_count": 1}, "codigo": {"buckets": []}}]}}}
    try:
        assert taxas("trt3") == []
    finally:
        globals()["consultar"] = real
    ca, cb = cortes([16.8, 21.5, 24.3, 28.0, 37.3, 40.6])  # amostra do TRT3
    assert risco(16.8, ca, cb) == "Alto"    # horas in itinere
    assert risco(24.3, ca, cb) == "Medio"   # responsabilidade subsidiaria
    assert risco(40.6, ca, cb) == "Baixo"   # desconfiguracao de justa causa
    # Auto-calibragem: 22% e' Alto num tribunal severo, Baixo num permissivo.
    assert risco(22.0, 25.0, 35.0) == "Alto"
    assert risco(22.0, 12.0, 18.0) == "Baixo"

    # O CNJ diz o tribunal sozinho.
    assert alias_do_cnj("0010707-93.2023.5.03.0072") == "trt3"
    assert alias_do_cnj("1234567-89.2024.8.13.0024") == "tjmg"   # estadual MG
    assert alias_do_cnj("1234567-89.2024.8.26.0100") == "tjsp"
    assert alias_do_cnj("1234567-89.2024.8.07.0001") == "tjdft"
    assert alias_do_cnj("1234567-89.2024.4.06.0000") == "trf6"
    # A ordem do CNJ e' pelo nome do estado: 11=Mato Grosso, 12=Mato Grosso do
    # Sul, 16=Parana, 17=Pernambuco. Ordenar por sigla erraria estes quatro.
    assert alias_do_cnj("1234567-89.2024.8.11.0001") == "tjmt"
    assert alias_do_cnj("1234567-89.2024.8.12.0001") == "tjms"
    assert alias_do_cnj("1234567-89.2024.8.16.0001") == "tjpr"
    assert alias_do_cnj("1234567-89.2024.8.17.0001") == "tjpe"
    # Lixo e segmentos que nao geramos nao podem virar consulta.
    assert alias_do_cnj("") is None and alias_do_cnj("123") is None
    assert alias_do_cnj("1234567-89.2024.6.13.0001") is None      # eleitoral

    assert _data("20230714000000") == "14/07/2023"
    assert _data(None) is None and _data("2023") is None
    print("ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
        sys.exit()
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    pedidos = (TRIBUNAIS if "--todos" in flags
               else ([a for a in sys.argv[1:] if a not in flags] or ["trt3"]))
    pasta = Path(__file__).parent / "docs" / "jurimetria"
    pasta.mkdir(parents=True, exist_ok=True)
    falhas = []
    for alias in pedidos:
        destino = pasta / f"jurimetria_{alias}.md"
        # A rodada completa leva horas e vive sendo interrompida, entao retomar
        # de onde parou e' o padrao. `--refazer` para atualizar os numeros.
        if destino.exists() and "--refazer" not in flags:
            print(f"pulado (ja existe): {alias}", flush=True)
            continue
        # Um tribunal que nao responde nao pode derrubar a rodada inteira.
        try:
            destino.write_text(markdown(alias), encoding="utf-8")
            print(f"ok: {alias}", flush=True)
        except Exception as e:
            falhas.append(f"{alias}: {e}")
            print(f"FALHOU: {alias}: {e}", flush=True)
    print(f"\n{len(pedidos)-len(falhas)}/{len(pedidos)} tribunais gerados"
          f" em {pasta}")
    for f in falhas:
        print(f"  - {f}")
