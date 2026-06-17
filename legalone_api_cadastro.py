"""Orquestrador do cadastro de processo via API REST do LegalOne."""
from __future__ import annotations

import logging
from typing import Optional

from legalone_api_client import LegalOneApiClient
from legalone_api_payload import build_lawsuit_payload
from legalone_field_resolver import FieldResolver

logger = logging.getLogger("LEGALONE_API")

# Mapa estático do escritório. Preencha com IDs conhecidos para evitar GETs.
STATIC_MAP: dict = {}

LAWSUITS_PATH = "Lawsuits"


class LegalOneApiCadastro:
    def __init__(
        self,
        client: Optional[LegalOneApiClient] = None,
        default_status_id: Optional[int] = None,
        default_area_id: Optional[int] = None,
        static_map: Optional[dict] = None,
    ):
        self.client = client or LegalOneApiClient.from_env()
        self.resolver = FieldResolver(self.client, static_map or STATIC_MAP)
        self.default_status_id = default_status_id
        self.default_area_id = default_area_id

    def _extrair_pedidos(self, dados: dict) -> list[dict]:
        pedidos = (dados or {}).get("pedidos")
        if isinstance(pedidos, list):
            return pedidos
        return []

    def cadastrar_processo(self, dados: dict) -> dict:
        dados = dados or {}
        cnj = dados.get("cnj")
        if not cnj:
            return {"sucesso": False, "erro": "CNJ ausente nos dados", "id": None}

        if not self.client.configured:
            return {
                "sucesso": False,
                "erro": "API nao configurada (client_id/secret ausentes)",
                "id": None,
            }

        logger.info("[API] Cadastrando processo CNJ=%s", cnj)
        payload = build_lawsuit_payload(
            dados,
            self.resolver,
            pedidos=self._extrair_pedidos(dados),
            default_status_id=self.default_status_id,
            default_area_id=self.default_area_id,
        )

        status, body = self.client.post_json(LAWSUITS_PATH, payload)
        if 200 <= status < 300:
            new_id = body.get("id") if isinstance(body, dict) else None
            logger.info("[API] Processo cadastrado id=%s", new_id)
            return {"sucesso": True, "erro": None, "id": new_id, "payload": payload}

        erro = f"HTTP {status}: {str(body)[:300]}"
        logger.error("[API] Falha no cadastro CNJ=%s - %s", cnj, erro)
        return {"sucesso": False, "erro": erro, "id": None, "payload": payload}
