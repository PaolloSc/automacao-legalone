"""Cadastro inicial do processo 0010155-82.2025.5.03.0097 (AIRR no TST,
MVC Transporte e Logistica Ltda x Ricardo Antonio Santos Pereira).

Cliente/contrario/posicao vieram de peca fornecida pelo usuario (a API
publica do DataJud nao traz partes); o resto (orgao, vara, classe, assunto,
data, risco) vem do enriquecimento automatico via CNJ.

    python scripts/cadastrar_0010155.py [--dry]
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

DADOS = {
    "cnj": "0010155-82.2025.5.03.0097",
    "cliente": "MVC Transporte e Logística Ltda",
    "contrario": "Ricardo Antonio Santos Pereira",
    "posicao": "Agravante",
    "natureza": "Trabalhista",
    "tipo_cadastro": "CADASTRO INICIAL",
    "tipo_tarefa_identificada": "CADASTRO_INICIAL",
    "outros_dados": {},
}


def main():
    if "--dry" in sys.argv:
        print(json.dumps(DADOS, ensure_ascii=False, indent=2))
        return
    cadastro = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    ok = cadastro.cadastrar_processo(DADOS)
    print("[OK]" if ok else f"[ERRO] {cadastro.last_error_reason}")


if __name__ == "__main__":
    main()
