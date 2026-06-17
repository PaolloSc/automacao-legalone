"""Resolve nome -> ID dos campos por ID do LegalOne.

Estratégia: mapa estático do escritório (rápido) -> GET na system table
(com cache em memória) -> None se não encontrar. Match normalizado
(sem acento, case-insensitive).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Optional

logger = logging.getLogger("LEGALONE_API")


_PATHS = {
    "natureza": "SystemTables.Litigation/LitigationNatures",
    "posicao": "SystemTables.Litigation/LitigationParticipantPositions",
    "tipo_acao": "SystemTables.Litigation/LitigationActionAppealProceduralIssuetypes",
    "area": "SystemTables.General/Areas",
    "status": "SystemTables.Litigation/LitigationStatuses",
    "fase": "SystemTables.Litigation/LitigationPhases",
}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _only_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


class FieldResolver:
    def __init__(self, client, static_map: Optional[dict] = None):
        self.client = client
        self.static_map = static_map or {}
        self._cache: dict[str, list[dict]] = {}
        self._contact_cache: dict[str, Optional[int]] = {}

    def _resolve_table(self, kind: str, name: Any) -> Optional[int]:
        key = _normalize(name)
        if not key:
            return None

        static_values = self.static_map.get(kind, {})
        static_hit = static_values.get(key)
        if static_hit is not None:
            return static_hit

        path = _PATHS[kind]
        if path not in self._cache:
            data = self.client.get_json(path)
            rows = data.get("value", data) if isinstance(data, dict) else data
            self._cache[path] = rows if isinstance(rows, list) else []

        for row in self._cache[path]:
            row_name = row.get("name") or row.get("description") or row.get("title")
            if _normalize(row_name) == key:
                return row.get("id")

        logger.warning("[RESOLVE] %s nao encontrado: %s", kind, name)
        return None

    def resolve_natureza(self, name: Any) -> Optional[int]:
        return self._resolve_table("natureza", name)

    def resolve_posicao(self, name: Any) -> Optional[int]:
        return self._resolve_table("posicao", name)

    def resolve_tipo_acao(self, name: Any) -> Optional[int]:
        return self._resolve_table("tipo_acao", name)

    def resolve_area(self, name: Any) -> Optional[int]:
        return self._resolve_table("area", name)

    def resolve_status(self, name: Any) -> Optional[int]:
        return self._resolve_table("status", name)

    def resolve_fase(self, name: Any) -> Optional[int]:
        return self._resolve_table("fase", name)

    def resolve_contact_id(self, document: Any) -> Optional[int]:
        digits = _only_digits(document)
        if not digits:
            return None
        if digits in self._contact_cache:
            return self._contact_cache[digits]

        params = {"$filter": f"documentNumber eq '{digits}'"}
        data = self.client.get_json("Contacts", params=params)
        rows = data.get("value", data) if isinstance(data, dict) else data
        contact_id = None
        if isinstance(rows, list):
            for row in rows:
                candidates = (
                    row.get("documentNumber"),
                    row.get("document"),
                    row.get("cpf"),
                    row.get("cnpj"),
                    row.get("taxId"),
                )
                if any(_only_digits(candidate) == digits for candidate in candidates):
                    contact_id = row.get("id") or row.get("contactId")
                    break
            if contact_id is None and len(rows) == 1:
                contact_id = rows[0].get("id") or rows[0].get("contactId")

        self._contact_cache[digits] = contact_id
        if contact_id is None:
            logger.warning("[RESOLVE] contato nao encontrado para documento: %s", digits)
        return contact_id
