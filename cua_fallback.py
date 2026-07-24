"""Fallback de clique via cua-driver (AT-SPI) para combobox que o Playwright nao commita.

Usado como ultimo recurso pelo legalone_cadastro: o Playwright digita para abrir o
dropdown e o cua-driver clica na opcao pela arvore de acessibilidade do Chromium.
Requer a infra da VM: Xvfb :99 + bus de sessao padrao + cuadriver.service.
"""
import json
import logging
import os
import subprocess
import unicodedata

logger = logging.getLogger("AutomacaoLegalOne")

CUA_BIN = os.path.expanduser("~/.local/bin/cua-driver")


def disponivel() -> bool:
    return os.path.exists(CUA_BIN)


def _call(tool: str, payload: dict, timeout: int = 90) -> dict | None:
    try:
        r = subprocess.run(
            [CUA_BIN, "call", tool],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if r.returncode != 0:
            logger.warning(f"[CUA] {tool} rc={r.returncode}: {(r.stderr or r.stdout)[:200]}")
            return None
        return json.loads(r.stdout)
    except Exception as e:
        logger.warning(f"[CUA] {tool} falhou: {e}")
        return None


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _janela_chromium():
    d = _call("list_windows", {}, timeout=30)
    for w in (d or {}).get("windows", []):
        if "chrome" in (w.get("title") or "").lower():
            return w.get("pid"), w.get("window_id")
    return None, None


def clicar_opcao(texto: str, papeis: tuple = ("list item", "menu item", "option", "cell", "row", "static", "link")) -> bool:
    """Clica no elemento visivel cuja label melhor casa com `texto` (AT-SPI).

    Re-snapshota a arvore imediatamente antes do clique (indices sao por snapshot).
    `papeis` pondera quais roles preferir (opcoes de dropdown por padrao).
    """
    if not disponivel():
        return False
    pid, wid = _janela_chromium()
    if not pid:
        logger.warning("[CUA] Janela do Chromium nao encontrada")
        return False
    st = _call(
        "get_window_state",
        {"pid": pid, "window_id": wid, "include_screenshot": False, "max_elements": 3000},
        timeout=120,
    )
    if not st:
        return False
    alvo = _norm(texto)
    papeis_opcao = papeis
    melhor = None
    for el in st.get("elements", []):
        lbl = _norm(el.get("label"))
        idx = el.get("element_index")
        if not lbl or idx is None:
            continue
        if alvo in lbl or (len(lbl) > 4 and lbl in alvo):
            role = el.get("role") or ""
            score = 1
            if any(p in role for p in papeis_opcao):
                score += 2
            if lbl == alvo:
                score += 1
            if melhor is None or score > melhor[0]:
                melhor = (score, el)
    if not melhor:
        logger.warning(f"[CUA] Nenhum elemento com label ~ '{texto[:50]}'")
        return False
    el = melhor[1]
    ok = _call(
        "click",
        {"pid": pid, "window_id": wid, "element_index": el["element_index"]},
        timeout=30,
    )
    logger.info(
        f"[CUA] Click [{el.get('role')}] '{(el.get('label') or '')[:60]}' -> {'OK' if ok else 'FALHOU'}"
    )
    return ok is not None


def clicar_campo(label: str) -> bool:
    """Clica no proprio campo/combobox pela label na arvore (dispensa seletor CSS)."""
    return clicar_opcao(label, papeis=("combo box", "entry", "text", "push button", "label"))
