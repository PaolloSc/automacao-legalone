"""Cadastro real de teste no LegalOne para validar preenchimento de campos.

Uso:
    python scripts/cadastrar_teste_execucao_fiscal.py --dry-run
    python scripts/cadastrar_teste_execucao_fiscal.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from legalone_cadastro import LegalOneCadastro


def build_dados_teste() -> dict:
    return {
        "cnj": "0004647-90.2017.4.01.3811",
        "titulo": "BQI Imoveis LTDA x União - Fazenda Nacional",
        "cliente": "BQI Imoveis LTDA",
        "contrario": "União - Fazenda Nacional",
        "posicao": "Executado",
        "natureza": "EXECUÇÃO FISCAL",
        "tipo_acao": "Execução Fiscal",
        "status_processo": "Ativo",
        "fase": "Sentença",
        "valor_causa": "R$ 52.316,00",
        "responsavel": os.getenv("LEGALONE_TEST_RESPONSAVEL", "Marco Tulio Fonseca Furtado"),
        "advogado_responsavel": os.getenv("LEGALONE_TEST_RESPONSAVEL", "Marco Tulio Fonseca Furtado"),
        "advogado": "Marco Tulio Fonseca Furtado",
        "comarca": "Divinópolis, MG",
        "tribunal": "TRF1",
        "instancia": "Justiça Federal",
        "tipo_tarefa_identificada": "CADASTRO_INICIAL",
        "descricao_pedidos": (
            "Pedido teste: validar preenchimento do cadastro LegalOne; "
            "valor R$ 1.000,00; probabilidade êxito possível."
        ),
        "pedidos": [
            {
                "pedido": "Pedido teste",
                "tipo": "Êxito",
                "grau": "Possível",
                "valor": "R$ 1.000,00",
            }
        ],
        "outros_dados": {
            "Valor da causa": "R$ 52.316,00",
            "Assunto": (
                "DIREITO TRIBUTÁRIO - Impostos - IRPJ/Imposto de Renda "
                "de Pessoa Jurídica"
            ),
            "Tribunal de origem": "TRF1 - Divinópolis, MG",
            "Início do processo": "2017",
            "Natureza": "EXECUÇÃO FISCAL",
            "Poder Judiciário": "Justiça Federal",
            "Juiz": "Walter Henrique Vilela Santos",
            "Polo Ativo": "União - Fazenda Nacional; União Federal",
            "Polo Passivo": "BQI Imoveis LTDA",
            "Advogados polo passivo": (
                "Cleber Junior Ferreira - OAB 170851/MG; "
                "Marco Tulio Fonseca Furtado - OAB 36959/MG; "
                "Noara Magalhaes Tavares - OAB 75900/MG; "
                "Sérgio Adolfo Eliazar de Carvalho - OAB 41311/MG"
            ),
            "Fase": "Sentença",
            "Descreva todos os pedidos": (
                "Pedido teste: validar preenchimento do cadastro LegalOne; "
                "valor R$ 1.000,00; probabilidade êxito possível."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Mostra os dados sem cadastrar")
    args = parser.parse_args()

    dados = build_dados_teste()
    if args.dry_run:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    os.environ["LEGALONE_USE_API"] = "false"
    os.environ["LEGALONE_USE_AGENTQL"] = "false"
    os.environ["LEGALONE_REQUIRE_CONTEXT"] = "false"
    try:
        import config_automacao
        config_automacao.VISUAL_GUARDIAN_CONFIG["habilitado"] = False
    except Exception:
        pass

    cadastrador = LegalOneCadastro(use_agentql=False)
    ok = cadastrador.cadastrar_processo(dados)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
