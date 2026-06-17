"""
JusBrasil Scraper — best-effort scraping da fase e última movimentação
de um processo a partir de uma busca pública.

Fail-safe: qualquer erro/timeout retorna None silenciosamente.
Cache em arquivo JSON com TTL de 7 dias.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jusbrasil_cache.json")
_CACHE_TTL = timedelta(days=7)


def _load_cache() -> dict:
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class JusBrasilScraper:
    SEARCH_URL = "https://www.jusbrasil.com.br/consulta-processual/busca?q={cnj}"

    def __init__(self):
        self._cache = _load_cache()

    def _cache_get(self, cnj: str) -> Optional[dict]:
        entry = self._cache.get(cnj)
        if not entry:
            return None
        try:
            ts = datetime.fromisoformat(entry.get("_ts", ""))
            if datetime.now() - ts < _CACHE_TTL:
                return entry.get("data")
        except Exception:
            return None
        return None

    def _cache_put(self, cnj: str, data: Optional[dict]) -> None:
        try:
            self._cache[cnj] = {"_ts": datetime.now().isoformat(), "data": data}
            _save_cache(self._cache)
        except Exception:
            pass

    def consultar_fase(self, cnj: str, page: Any = None) -> Optional[dict]:
        """Retorna {fase, ultima_mov, data} ou None se não conseguir."""
        if not cnj:
            return None
        cached = self._cache_get(cnj)
        if cached is not None:
            return cached

        resultado: Optional[dict] = None
        owns_page = False
        playwright_ctx = None
        browser = None

        try:
            url = self.SEARCH_URL.format(cnj=re.sub(r"\D", "", cnj))

            if page is None:
                try:
                    from playwright.sync_api import sync_playwright
                    playwright_ctx = sync_playwright().start()
                    browser = playwright_ctx.chromium.launch(headless=True)
                    ctx = browser.new_context()
                    page = ctx.new_page()
                    owns_page = True
                except Exception as e:
                    logger.info(f"[JUSBRASIL] Playwright indisponível: {e}")
                    self._cache_put(cnj, None)
                    return None

            try:
                page.goto(url, timeout=10000, wait_until="domcontentloaded")
            except Exception:
                self._cache_put(cnj, None)
                return None

            # heurística: extrair primeiro card de resultado
            fase = None
            ultima_mov = None
            data_mov = None
            try:
                txt = page.locator("body").inner_text(timeout=5000) or ""
                m_fase = re.search(r"(fase|situação)\s*[:\-]?\s*([^\n]{3,80})", txt, re.I)
                if m_fase:
                    fase = m_fase.group(2).strip()
                m_mov = re.search(r"última\s+(movimentação|atualização)\s*[:\-]?\s*([^\n]{3,160})", txt, re.I)
                if m_mov:
                    ultima_mov = m_mov.group(2).strip()
                m_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", txt)
                if m_data:
                    data_mov = m_data.group(1)
            except Exception:
                pass

            if any([fase, ultima_mov, data_mov]):
                resultado = {"fase": fase, "ultima_mov": ultima_mov, "data": data_mov}
            else:
                resultado = None

            self._cache_put(cnj, resultado)
            return resultado
        except Exception as e:
            logger.info(f"[JUSBRASIL] erro: {e}")
            self._cache_put(cnj, None)
            return None
        finally:
            if owns_page:
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass
                try:
                    if playwright_ctx:
                        playwright_ctx.stop()
                except Exception:
                    pass
