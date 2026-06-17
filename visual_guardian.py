"""
Visual Guardian — Recuperação inteligente por Visão + LLM.

Quando a automação falha, tira screenshot, envia para Claude Vision,
recebe uma ação de recuperação JSON, e executa via Playwright.
"""

import base64
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime

from guardian_actions import ActionExecutor

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """Você é um assistente de recuperação de automação do sistema LegalOne.
Analise o screenshot e retorne UMA ação JSON para recuperar a automação.

Ações disponíveis:
- {"action": "click", "selector": "...", "description": "..."}
- {"action": "click_coordinates", "x": int, "y": int, "description": "..."}
- {"action": "dismiss_popup", "method": "escape|click_x|click_outside"}
- {"action": "type_text", "selector": "...", "text": "...", "description": "..."}
- {"action": "press_key", "key": "Escape|Enter|Tab"}
- {"action": "wait", "seconds": int, "for_what": "..."}
- {"action": "navigate", "url": "..."}
- {"action": "refresh"}
- {"action": "login_expired"}
- {"action": "give_up", "reason": "..."}

Inclua "confidence" (0.0-1.0). Responda APENAS JSON, sem markdown."""


class VisualGuardian:
    """Core do sistema de recuperação visual."""

    def __init__(
        self,
        page,
        brain,
        max_retries: int = 3,
        confidence_threshold: float = 0.5,
        max_calls_per_cadastro: int = 10,
        vision_model: str = "claude-sonnet-4-20250514",
        log_path: str = "guardian_log.jsonl",
        screenshot_dir: str = "guardian_screenshots",
        dry_run: bool = False,
    ):
        self.page = page
        self.brain = brain
        self.max_retries = max_retries
        self.confidence_threshold = confidence_threshold
        self.max_calls_per_cadastro = max_calls_per_cadastro
        self.vision_model = vision_model
        self.log_path = log_path
        self.screenshot_dir = screenshot_dir
        self.dry_run = dry_run
        self._calls_this_cadastro = 0
        self._action_executor = ActionExecutor(page)

        os.makedirs(screenshot_dir, exist_ok=True)

    def update_page(self, page):
        self.page = page
        self._action_executor.update_page(page)

    def reset_call_count(self):
        """Reseta o contador de chamadas (chamar no início de cada cadastro)."""
        self._calls_this_cadastro = 0

    def rescue(self, step_name: str, context: str, original_error: Exception) -> bool:
        """Ponto de entrada. Retorna True se a recuperação foi bem-sucedida."""
        if self._calls_this_cadastro >= self.max_calls_per_cadastro:
            logger.warning(f"[GUARDIAN] Limite de {self.max_calls_per_cadastro} chamadas por cadastro atingido")
            return False

        error_msg = str(original_error)
        logger.info(f"[GUARDIAN] Tentando recuperação para '{step_name}' (erro: {error_msg[:100]})")

        for attempt in range(1, self.max_retries + 1):
            start_time = time.time()
            self._calls_this_cadastro += 1

            if self._calls_this_cadastro > self.max_calls_per_cadastro:
                logger.warning("[GUARDIAN] Limite de chamadas excedido durante retry")
                return False

            # 1. Captura screenshot
            screenshot_path, screenshot_b64 = self._capture_screenshot(step_name, attempt)
            if not screenshot_b64:
                logger.error("[GUARDIAN] Falha ao capturar screenshot")
                continue

            # 2. Pergunta ao Vision
            action = self._ask_vision(screenshot_b64, step_name, context, error_msg, attempt)
            if not action:
                logger.error("[GUARDIAN] Falha ao obter resposta do Vision")
                continue

            duration_ms = int((time.time() - start_time) * 1000)

            # 3. Verifica ações especiais
            action_type = action.get("action", "")

            if action_type == "give_up":
                reason = action.get("reason", "sem motivo")
                logger.warning(f"[GUARDIAN] Vision desistiu: {reason}")
                self._log_intervention(step_name, context, error_msg, action, False, duration_ms, screenshot_path)
                return False

            if action_type == "login_expired":
                logger.warning("[GUARDIAN] Sessão expirada detectada pelo Vision")
                self._log_intervention(step_name, context, error_msg, action, False, duration_ms, screenshot_path)
                return False

            # 4. Verifica confiança
            confidence = action.get("confidence", 0.0)
            if confidence < self.confidence_threshold:
                logger.warning(f"[GUARDIAN] Confiança {confidence:.2f} < {self.confidence_threshold} — ignorando ação")
                self._log_intervention(step_name, context, error_msg, action, False, duration_ms, screenshot_path)
                continue

            # 5. Executa ação
            if self.dry_run:
                logger.info(f"[GUARDIAN] DRY RUN — ação sugerida: {json.dumps(action, ensure_ascii=False)}")
                self._log_intervention(step_name, context, error_msg, action, None, duration_ms, screenshot_path)
                return False

            success = self._action_executor.execute(action)
            self._log_intervention(step_name, context, error_msg, action, success, duration_ms, screenshot_path)

            if success:
                logger.info(f"[GUARDIAN] Recuperação bem-sucedida na tentativa {attempt}: {action.get('description', action_type)}")
                time.sleep(1)  # Breve pausa para a UI reagir
                return True

            logger.warning(f"[GUARDIAN] Ação falhou na tentativa {attempt}/{self.max_retries}")

        logger.error(f"[GUARDIAN] Todas as {self.max_retries} tentativas falharam para '{step_name}'")
        return False

    def _capture_screenshot(self, step_name: str, attempt: int) -> tuple:
        """Captura screenshot e retorna (path, base64)."""
        try:
            if not self.page:
                return ("", "")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = step_name.replace(" ", "_").replace("/", "_")[:50]
            filename = f"{safe_name}_{ts}_attempt{attempt}.png"
            filepath = os.path.join(self.screenshot_dir, filename)

            screenshot_bytes = self.page.screenshot(full_page=False)
            with open(filepath, "wb") as f:
                f.write(screenshot_bytes)

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            logger.info(f"[GUARDIAN] Screenshot salva: {filepath}")
            return (filepath, screenshot_b64)

        except Exception as e:
            logger.error(f"[GUARDIAN] Erro ao capturar screenshot: {e}")
            return ("", "")

    def _ask_vision(self, screenshot_b64: str, step_name: str, context: str,
                    error_msg: str, attempt: int) -> dict | None:
        """Envia screenshot para Claude Vision e retorna a ação JSON parseada."""
        try:
            url = ""
            try:
                url = self.page.url or ""
            except Exception:
                pass

            user_prompt = (
                f"A automação falhou no passo '{step_name}' (tentativa {attempt}).\n"
                f"Contexto: {context}\n"
                f"Erro: {error_msg}\n"
                f"URL atual: {url}\n\n"
                "Analise o screenshot e sugira UMA ação para recuperar."
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": user_prompt,
                        },
                    ],
                }
            ]

            response = self.brain.send_message(
                messages,
                system=VISION_SYSTEM_PROMPT,
                model=self.vision_model,
                max_tokens=1024,
                temperature=0.1,
            )

            # Extrai texto da resposta
            content = response.get("content", [])
            text = "".join(
                block.get("text", "") for block in content if block.get("type") == "text"
            )

            if not text.strip():
                logger.warning("[GUARDIAN] Resposta vazia do Vision")
                return None

            # Parse JSON (tenta extrair JSON mesmo se houver markdown)
            text = text.strip()
            if text.startswith("```"):
                # Remove blocos de código markdown
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()

            action = json.loads(text)
            logger.info(f"[GUARDIAN] Vision sugeriu: {action.get('action')} (conf={action.get('confidence', '?')})")
            return action

        except json.JSONDecodeError as e:
            logger.error(f"[GUARDIAN] JSON inválido do Vision: {e}")
            return None
        except Exception as e:
            logger.error(f"[GUARDIAN] Erro ao consultar Vision: {e}")
            return None

    def _log_intervention(self, step_name: str, context: str, error_msg: str,
                          action: dict, success: bool | None, duration_ms: int,
                          screenshot_path: str = "") -> None:
        """Registra intervenção no log JSONL."""
        try:
            url = ""
            try:
                url = self.page.url or ""
            except Exception:
                pass

            entry = {
                "timestamp": datetime.now().isoformat(),
                "step_name": step_name,
                "context": context,
                "error": error_msg,
                "url": url,
                "screenshot_path": screenshot_path,
                "action": action,
                "success": success,
                "dry_run": self.dry_run,
                "duration_ms": duration_ms,
            }

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.error(f"[GUARDIAN] Erro ao gravar log: {e}")


@contextmanager
def guarded(guardian, step_name: str, context: str = ""):
    """Context manager para uso inline — tenta recuperação se o bloco falhar."""
    try:
        yield
    except Exception as e:
        if guardian and guardian.rescue(step_name, context, e):
            return
        raise
