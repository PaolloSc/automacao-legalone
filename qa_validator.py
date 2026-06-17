"""QA Validator — valida em tempo real o preenchimento do formulário LegalOne.

Uso:
    from qa_validator import QAValidator
    qa = QAValidator(page, dados_processo)
    qa.validar_antes_de_salvar()   # loga warnings, NÃO aborta

Validações: campos obrigatórios preenchidos, checkbox "Solicitar monitoramento"
marcado, mensagens de "Campo obrigatório" ausentes. Também salva screenshot
quando detecta discrepâncias.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

CAMPOS_OBRIGATORIOS = [
    ("Título", ["input[name*='Title' i]", "input[placeholder*='ítulo' i]"], "titulo"),
    ("Natureza", ["select[name*='Nature' i]", "[aria-label*='Natureza' i]"], "natureza"),
    ("Status", ["select[name*='Status' i]", "[aria-label*='Status' i]"], "status_processo"),
    ("Posição", ["select[name*='Position' i]", "[aria-label*='Posição' i]"], "posicao"),
    ("Cliente principal", ["[name*='MainCustomer' i]", "[aria-label*='Cliente principal' i]"], "cliente"),
    ("Contrário Principal", ["[name*='MainOpposing' i]", "[aria-label*='Contrário' i]"], "contrario"),
    ("Negociação de contrato de honorários",
     ["select[name*='FeeContract' i]", "[aria-label*='Negociação' i]", "[aria-label*='honorários' i]"],
     "negociacao_contrato"),
    ("Data da baixa",
     ["input[name*='Discharge' i]", "input[name*='DataBaixa' i]", "input[placeholder*='baixa' i]"],
     "data_baixa"),
]

MONITORAMENTO_SELECTORS = [
    "input[type=checkbox][name*='monitor' i]",
    "input[type=checkbox][name*='Solicit' i]",
    "label:has-text('Solicitar monitoramento') input[type=checkbox]",
]


class QAValidator:
    def __init__(self, page: Any, dados_processo: dict, screenshot_dir: str | None = None):
        self.page = page
        self.dados = dados_processo or {}
        self.warnings: list[str] = []
        self.screenshot_dir = screenshot_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "qa_screenshots"
        )
        os.makedirs(self.screenshot_dir, exist_ok=True)

    # --------------------------------------------------------------
    def _log_warn(self, msg: str):
        self.warnings.append(msg)
        logger.warning(f"[QA] ⚠ {msg}")

    def _valor_campo(self, seletores: list[str]) -> str | None:
        for sel in seletores:
            try:
                loc = self.page.locator(sel).first
                if loc.count() == 0:
                    continue
                val = loc.input_value(timeout=1000)
                if val is not None:
                    return val.strip()
            except Exception:
                try:
                    txt = loc.inner_text(timeout=500)
                    if txt:
                        return txt.strip()
                except Exception:
                    continue
        return None

    def _tem_erro_obrigatorio(self, rotulo: str) -> bool:
        try:
            xpath = (
                f"xpath=//label[contains(., '{rotulo}')]/following::*[contains(@class,'error')"
                f" or contains(., 'obrigatório')][1]"
            )
            loc = self.page.locator(xpath).first
            if loc.count() == 0:
                return False
            txt = (loc.inner_text(timeout=500) or "").lower()
            return "obrigat" in txt
        except Exception:
            return False

    # --------------------------------------------------------------
    def validar_antes_de_salvar(self) -> list[str]:
        """Executa todas as validações. Retorna lista de warnings (nunca aborta)."""
        logger.info("[QA] 🔍 Iniciando validação pré-salvar...")
        self._validar_campos_obrigatorios()
        self._validar_monitoramento()
        self._validar_mensagens_erro_visiveis()

        if self.warnings:
            self._tirar_screenshot("validacao_falhou")
            logger.warning(f"[QA] {len(self.warnings)} warning(s) detectado(s) — seguindo mesmo assim.")
        else:
            logger.info("[QA] ✅ Formulário validado sem warnings.")
        return list(self.warnings)

    def _validar_campos_obrigatorios(self):
        for rotulo, seletores, chave_dado in CAMPOS_OBRIGATORIOS:
            esperado = self.dados.get(chave_dado)
            if not esperado:
                esperado = (self.dados.get("outros_dados", {}) or {}).get(rotulo)
            if not esperado:
                continue  # não temos o dado → não validamos
            valor = self._valor_campo(seletores)
            if not valor:
                self._log_warn(
                    f"Campo '{rotulo}' VAZIO no formulário (dados disponíveis: '{esperado}')"
                )
            elif str(esperado).strip().lower() not in str(valor).strip().lower() and \
                    str(valor).strip().lower() not in str(esperado).strip().lower():
                self._log_warn(
                    f"Campo '{rotulo}' com valor divergente: form='{valor}' esperado='{esperado}'"
                )

    def _validar_monitoramento(self):
        if not self.dados.get("solicitar_monitoramento", True):
            return
        for sel in MONITORAMENTO_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.count() == 0:
                    continue
                if loc.is_checked(timeout=500):
                    return
                self._log_warn("Checkbox 'Solicitar monitoramento' NÃO marcado")
                return
            except Exception:
                continue

    def _validar_mensagens_erro_visiveis(self):
        try:
            erros = self.page.locator("xpath=//*[contains(., 'Campo obrigatório')]")
            count = erros.count()
            if count:
                visiveis = 0
                for i in range(min(count, 10)):
                    try:
                        if erros.nth(i).is_visible(timeout=300):
                            visiveis += 1
                    except Exception:
                        continue
                if visiveis:
                    self._log_warn(f"{visiveis} mensagem(ns) 'Campo obrigatório' visíveis na página")
        except Exception:
            pass

    def _tirar_screenshot(self, tag: str):
        try:
            cnj = (self.dados.get("cnj") or "sem-cnj").replace("/", "_").replace(".", "_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.screenshot_dir, f"qa_{tag}_{cnj}_{ts}.png")
            self.page.screenshot(path=path, full_page=True)
            logger.warning(f"[QA] 📸 Screenshot: {path}")
        except Exception as e:
            logger.warning(f"[QA] Falha ao capturar screenshot: {e}")
