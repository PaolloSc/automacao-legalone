"""
Guardian Actions — Executor de ações Playwright para recuperação visual.

Traduz instruções JSON do LLM em chamadas Playwright reais.
"""

import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Domínios permitidos para navegação
ALLOWED_DOMAINS = {"novajus.com.br", "thomsonreuters.com"}


def _is_allowed_url(url: str) -> bool:
    """Verifica se a URL pertence a um domínio permitido."""
    try:
        host = urlparse(url).hostname or ""
        return any(host.endswith(d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


class ActionExecutor:
    """Executa ações Playwright baseadas em instruções JSON do Vision LLM."""

    def __init__(self, page):
        self.page = page

    def update_page(self, page):
        self.page = page

    def execute(self, action: dict) -> bool:
        """Dispatcher principal. Retorna True se a ação foi executada com sucesso."""
        action_type = action.get("action", "")
        dispatch = {
            "click": self._click,
            "click_coordinates": self._click_coordinates,
            "dismiss_popup": self._dismiss_popup,
            "type_text": self._type_text,
            "press_key": self._press_key,
            "wait": self._wait,
            "navigate": self._navigate,
            "refresh": self._refresh,
        }

        handler = dispatch.get(action_type)
        if not handler:
            logger.warning(f"[GUARDIAN] Ação desconhecida: {action_type}")
            return False

        try:
            return handler(action)
        except Exception as e:
            logger.error(f"[GUARDIAN] Erro ao executar '{action_type}': {e}")
            return False

    def _click(self, action: dict) -> bool:
        selector = action.get("selector", "")
        if not selector:
            return False
        self.page.click(selector, timeout=5000)
        logger.info(f"[GUARDIAN] Click: {selector}")
        return True

    def _click_coordinates(self, action: dict) -> bool:
        x = action.get("x", 0)
        y = action.get("y", 0)
        self.page.mouse.click(x, y)
        logger.info(f"[GUARDIAN] Click coordinates: ({x}, {y})")
        return True

    def _dismiss_popup(self, action: dict) -> bool:
        method = action.get("method", "escape")
        if method == "escape":
            self.page.keyboard.press("Escape")
        elif method == "click_x":
            # Tenta fechar via botão X comum
            close_selectors = [
                ".close-button", "button.close", "[aria-label='Close']",
                "span.i-Close-2", ".modal .close-button",
            ]
            for sel in close_selectors:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        logger.info(f"[GUARDIAN] Dismiss popup via: {sel}")
                        return True
                except Exception:
                    continue
            return False
        elif method == "click_outside":
            # Clica fora do modal
            self.page.mouse.click(10, 10)
        else:
            return False
        logger.info(f"[GUARDIAN] Dismiss popup: {method}")
        return True

    def _type_text(self, action: dict) -> bool:
        selector = action.get("selector", "")
        text = action.get("text", "")
        if not selector or not text:
            return False
        # Segurança: nunca digitar senhas via guardian
        if any(kw in text.lower() for kw in ["password", "senha", "pwd"]):
            logger.warning("[GUARDIAN] Bloqueado: tentativa de digitar senha")
            return False
        self.page.fill(selector, text, timeout=5000)
        logger.info(f"[GUARDIAN] Type text in: {selector}")
        return True

    def _press_key(self, action: dict) -> bool:
        key = action.get("key", "")
        allowed_keys = {"Escape", "Enter", "Tab", "Space", "Backspace", "Delete",
                        "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                        "F5", "Home", "End", "PageUp", "PageDown"}
        if key not in allowed_keys:
            logger.warning(f"[GUARDIAN] Tecla não permitida: {key}")
            return False
        self.page.keyboard.press(key)
        logger.info(f"[GUARDIAN] Press key: {key}")
        return True

    def _wait(self, action: dict) -> bool:
        seconds = min(action.get("seconds", 1), 30)  # Max 30s
        logger.info(f"[GUARDIAN] Waiting {seconds}s...")
        time.sleep(seconds)
        return True

    def _navigate(self, action: dict) -> bool:
        url = action.get("url", "")
        if not _is_allowed_url(url):
            logger.warning(f"[GUARDIAN] Navegação bloqueada para domínio não permitido: {url}")
            return False
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        logger.info(f"[GUARDIAN] Navigate: {url}")
        return True

    def _refresh(self, _action: dict) -> bool:
        self.page.reload(wait_until="domcontentloaded", timeout=30000)
        logger.info("[GUARDIAN] Page refreshed")
        return True
