"""Risco de um pedido lido da tabela de jurimetria ja gerada, pelo CODIGO TPU.

O agente do Copilot casa o assunto por texto ("Horas in Itinere"), e grafia
varia entre a peticao, o tribunal e a tabela. O hit do DataJud que o bot ja'
busca para a capa do processo traz `assuntos[].codigo` -- o mesmo codigo que
`jurimetria_datajud.py` agora grava na primeira coluna do .md. Casar por ele e'
exato.

Aqui so' se le' arquivo: nada de rede, nada de dependencia nova.

    >>> tabela("trt3")[13770]["risco"]      # Horas in Itinere
    'Alto'
"""
from __future__ import annotations

import re
from pathlib import Path

PASTA = Path(__file__).parent / "docs" / "jurimetria"

# | 13770 | Horas in Itinere | 30572 | 16.8% | Alto |
_LINHA = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)%\s*\|\s*(\w+)\s*\|",
    re.MULTILINE,
)

_cache: dict[str, dict[int, dict]] = {}


def tabela(alias: str) -> dict[int, dict]:
    """codigo TPU -> {assunto, decididos, taxa, risco} do tribunal.

    Tabela antiga (gerada antes da coluna de codigo) ou inexistente devolve
    vazio -- quem chama simplesmente nao preenche o risco, em vez de chutar.
    """
    alias = re.sub(r"[^a-z0-9]", "", (alias or "").lower())
    if not alias:
        return {}
    if alias not in _cache:
        arq = PASTA / f"jurimetria_{alias}.md"
        linhas: dict[int, dict] = {}
        if arq.exists():
            texto = arq.read_text(encoding="utf-8")
            for cod, assunto, decididos, taxa, risco in _LINHA.findall(texto):
                linhas[int(cod)] = {"assunto": assunto,
                                    "decididos": int(decididos),
                                    "taxa": float(taxa), "risco": risco}
        _cache[alias] = linhas
    return _cache[alias]


def riscos(alias: str, assuntos) -> list[dict]:
    """Assuntos do hit do DataJud -> linhas da tabela, na ordem recebida.

    Assunto fora da tabela nao vira "Medio": fica de fora, e quem le' escreve
    "sem base" (regra das instrucoes do agente).
    """
    t = tabela(alias)
    fora = []
    for a in (assuntos or []):
        cod = (a or {}).get("codigo") if isinstance(a, dict) else None
        try:
            cod = int(cod)
        except (TypeError, ValueError):
            continue
        linha = t.get(cod)
        if linha:
            fora.append({"codigo": cod, **linha})
    return fora


def risco_do_processo(alias: str, assuntos) -> tuple[str | None, str]:
    """(risco, detalhe por assunto) do processo.

    ponytail: usa o assunto PRINCIPAL (o primeiro que o DataJud devolve), nao
    o pedido de maior valor -- o valor por pedido nao existe no DataJud nem no
    hit da capa. Trocar para maior-valor quando o bot tiver a tabela de
    pedidos com valores.
    """
    linhas = riscos(alias, assuntos)
    if not linhas:
        return None, ""
    detalhe = "; ".join(f'{l["codigo"]} {l["assunto"]}: {l["risco"]}'
                        f' ({l["taxa"]}%)' for l in linhas)
    return linhas[0]["risco"], detalhe


def demo():
    """Self-check do parser, sem rede: usa a tabela do TRT3 no disco."""
    t = tabela("trt3")
    if not t:
        print("tabela do trt3 ainda sem coluna de codigo; nada a checar")
        return
    assert all(isinstance(k, int) for k in t)
    assert t[13770]["risco"] in ("Alto", "Medio", "Baixo")
    r, d = risco_do_processo("TRT3", [{"codigo": 13770, "nome": "x"},
                                      {"codigo": 999999}])
    assert r == t[13770]["risco"] and "13770" in d and "999999" not in d
    assert risco_do_processo("trt3", []) == (None, "")
    assert tabela("nao_existe") == {}
    print("ok")


if __name__ == "__main__":
    demo()
