"""Smoke test manual: valida auth + 1 GET em system table. NÃO faz POST.
Uso: python scripts/smoke_legalone_api.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from legalone_api_client import LegalOneApiClient


def main() -> int:
    client = LegalOneApiClient.from_env()
    if not client.configured:
        print("ERRO: credenciais ausentes. Preencha LEGALONE_API_CLIENT_ID/SECRET no .env")
        return 2
    print("Obtendo token...")
    token = client.get_token()
    print("Token OK:", (token[:12] + "...") if token else "FALHOU")
    print("GET LitigationNatures...")
    data = client.get_json("SystemTables.Litigation/LitigationNatures")
    items = data.get("value", data) if isinstance(data, dict) else data
    print(f"Naturezas retornadas: {len(items) if items else 0}")
    if items:
        print("Exemplo:", items[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
