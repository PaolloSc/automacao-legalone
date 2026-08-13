"""
DataJud Client — consulta da API Pública do CNJ (Datajud).

Resolve o alias do tribunal a partir do segmento J.TR do CNJ
(NNNNNNN-DD.AAAA.J.TR.OOOO) e faz uma busca por numeroProcesso.

Fail-safe: em qualquer erro retorna lista vazia.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# Mapeamento J.TR → alias público do Datajud
_ALIAS_MAP: dict[tuple[str, str], str] = {
    # Justiça Estadual (J=8)
    ("8", "26"): "api_publica_tjsp",
    ("8", "24"): "api_publica_tjsc",
    ("8", "19"): "api_publica_tjrj",
    ("8", "13"): "api_publica_tjmg",
    ("8", "02"): "api_publica_tjal",
    ("8", "05"): "api_publica_tjba",
    ("8", "07"): "api_publica_tjdft",
    ("8", "01"): "api_publica_tjac",
    # Justiça do Trabalho (J=5) — TRTs
    ("5", "02"): "api_publica_trt2",
    ("5", "15"): "api_publica_trt15",
    ("5", "04"): "api_publica_trt4",
    ("5", "01"): "api_publica_trt1",
    ("5", "03"): "api_publica_trt3",
    # Justiça Federal (J=4) — TRFs
    ("4", "01"): "api_publica_trf1",
    ("4", "02"): "api_publica_trf2",
    ("4", "03"): "api_publica_trf3",
    ("4", "04"): "api_publica_trf4",
    ("4", "05"): "api_publica_trf5",
    # Superiores. STJ e' J=3 (cai no fallback); J=7 e' militar da Uniao — a
    # entrada antiga mandava CNJ militar para o indice do STJ.
    ("1", "00"): "api_publica_stf",
    ("5", "00"): "api_publica_tst",
}


class DatajudClient:
    # Chave PÚBLICA do DataJud/CNJ — documentada e igual para todos:
    # https://datajud-wiki.cnj.jus.br/api-publica/acesso
    # Pode ser sobrescrita via env DATAJUD_API_KEY.
    API_KEY = os.getenv(
        "DATAJUD_API_KEY",
        "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
    )
    BASE = "https://api-publica.datajud.cnj.jus.br"

    _cache: dict[str, list[dict]] = {}

    def _resolver_alias(self, cnj: str) -> Optional[str]:
        """Parse NNNNNNN-DD.AAAA.J.TR.OOOO → 'api_publica_tjsp' etc."""
        if not cnj:
            return None
        m = re.match(
            r"^\s*(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\s*$",
            cnj.strip(),
        )
        if not m:
            # fallback: extrair apenas dígitos (20) e reparsear
            digits = re.sub(r"\D", "", cnj)
            if len(digits) != 20:
                return None
            j = digits[13]
            tr = digits[14:16]
        else:
            j = m.group(4)
            tr = m.group(5)
        alias = _ALIAS_MAP.get((j, tr))
        if alias:
            return alias
        # O mapa acima so tem os tribunais mais vistos. O resto sai da mesma
        # regra J.TR ja implementada na jurimetria (todos os TJs/TRTs/TRFs).
        try:
            from jurimetria_datajud import alias_do_cnj
            curto = alias_do_cnj(cnj)
        except Exception:
            return None
        return f"api_publica_{curto}" if curto else None

    def consultar(self, cnj: str) -> list[dict]:
        """Consulta Datajud pelo CNJ e retorna lista de hits (_source)."""
        try:
            if not cnj:
                return []
            if cnj in DatajudClient._cache:
                return DatajudClient._cache[cnj]

            alias = self._resolver_alias(cnj)
            if not alias:
                logger.info(f"[DATAJUD] Tribunal não mapeado para CNJ {cnj}")
                DatajudClient._cache[cnj] = []
                return []

            url = f"{self.BASE}/{alias}/_search"
            numero_digits = re.sub(r"\D", "", cnj)
            payload = {
                "query": {"match": {"numeroProcesso": numero_digits}}
            }
            headers = {
                "Authorization": f"APIKey {self.API_KEY}",
                "Content-Type": "application/json",
            }

            hits: list[dict] = []
            for tentativa in range(2):
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        raw_hits = (body.get("hits") or {}).get("hits") or []
                        hits = [h.get("_source", {}) for h in raw_hits if isinstance(h, dict)]
                        break
                    logger.warning(f"[DATAJUD] status={resp.status_code} body={resp.text[:200]}")
                except Exception as e:
                    logger.warning(f"[DATAJUD] tentativa {tentativa+1} falhou: {e}")

            DatajudClient._cache[cnj] = hits
            return hits
        except Exception as e:
            logger.warning(f"[DATAJUD] erro inesperado: {e}")
            return []
