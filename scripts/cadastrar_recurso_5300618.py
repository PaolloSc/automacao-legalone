"""Reprocessa o recurso civel do CNJ 5300618-93.2023.8.09.0051 que falhou
em 19/08/2026 (vinculo='Proc - 0004487' rejeitado pelo guard antigo, ja
corrigido). Dados reconstruidos do registro salvo em processos_erro.log.

    python scripts/cadastrar_recurso_5300618.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

DADOS = {
    "cnj": "5300618-93.2023.8.09.0051",
    "cliente": "Ação Promoção de Vendas Ltda.",
    "contrario": "Pollyana de Moura",
    "advogado": "Marcello Silva Nunes Leite",
    "posicao": "Recorrente",
    "numero_antigo": "2026/0212918-0",
    "data_distribuicao": "24/06/2026",
    "tipo_processo": "Judicial",
    "tipo_classe_recurso": "Agravo em Recurso Especial",
    "vinculo": "Proc - 0004487",
    "tipo_vinculo": "Recurso",
    "natureza": "Cível",
    "orgao": "STJ",
    "uf": "DF",
    "cidade": "Brasília",
    "comarca": "Brasília",
    "instancia": "STJ",
    "numero_turma": "4",
    "nome_vara_turma": "Turma",
    "objetos_recurso": "Decisão de não admissão do Recurso Especial",
    "classificacao_pedidos_recurso": "Admissão do recurso especial (êxito possível)",
    "tipo_entidade": "PROCESSO",
    "tipo_tarefa_identificada": "RECURSO_CIVEL",
    "tipo_cadastro_canonico": "RECURSO",
    "outros_dados": {},
}


def main():
    cadastro = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    ok = cadastro.cadastrar_processo(DADOS)
    print("[OK]" if ok else f"[ERRO] {cadastro.last_error_reason}")


if __name__ == "__main__":
    main()
