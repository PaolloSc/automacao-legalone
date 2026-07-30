"""Ponte para o cua-driver no Windows: enxerga os elementos do LegalOne pela arvore UIA
do Chrome e clica por element_index (UIA Invoke, sem foco, sem LLM, sem cota de visao).

Requer o cua-driver.exe instalado e o Chrome com --force-renderer-accessibility (ja no codigo).
"""
import json
import logging
import os
import re
import subprocess

logger = logging.getLogger("AutomacaoLegalOne")

CUA = os.getenv(
    "CUA_DRIVER_BIN",
    r"C:\Users\paollo\AppData\Local\Programs\Cua\cua-driver\bin\cua-driver.exe",
)


def disponivel() -> bool:
    if not os.path.exists(CUA):
        return False
    _garantir_daemon()
    return True


def _garantir_daemon():
    """Sobe o daemon (serve) se nao estiver rodando - o cache de element_index e
    compartilhado via daemon; sem ele, click reclama 'not in cache'."""
    try:
        st = subprocess.run([CUA, "status"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=15)
        if "running" in (st.stdout or "").lower():
            return
    except Exception:
        pass
    try:
        subprocess.Popen([CUA, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import time as _t
        _t.sleep(4)
        logger.info("[CUA] daemon iniciado")
    except Exception as e:
        logger.warning(f"[CUA] falha ao iniciar daemon: {str(e)[:80]}")


def _call(tool: str, payload: dict, timeout: int = 90):
    try:
        r = subprocess.run(
            [CUA, "call", tool],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",  # saida do cua e UTF-8 (Windows usaria cp1252 e quebra)
        )
        if r.returncode != 0:
            logger.warning(f"[CUA] {tool} rc={r.returncode}: {(r.stderr or r.stdout)[:150]}")
            return None
        return json.loads(r.stdout)
    except Exception as e:
        logger.warning(f"[CUA] {tool} falhou: {str(e)[:100]}")
        return None


def _janela_legalone():
    d = _call("list_windows", {}, 30) or {}
    for w in (d.get("windows") or []) + (d.get("_legacy_windows") or []):
        if "Legal One" in (w.get("title") or ""):
            return w.get("pid"), w.get("window_id")
    return None, None


def _elementos(pid, wid):
    d = _call("get_window_state", {"pid": pid, "window_id": wid, "max_elements": 3000}, 120)
    if not d:
        return []
    return (d.get("structuredContent") or d).get("elements") or d.get("elements") or []


def _clicar(pid, wid, idx) -> bool:
    return _call("click", {"pid": pid, "window_id": wid, "element_index": idx}, 30) is not None


def clicar_editar_do_cnj(cnj) -> bool:
    """Clica no botao 'Editar' do card cujo CNJ casa (Editar e o primeiro apos o texto do CNJ)."""
    pid, wid = _janela_legalone()
    if not pid:
        logger.warning("[CUA] janela LegalOne nao encontrada")
        return False
    els = _elementos(pid, wid)
    alvo = re.sub(r"\D", "", str(cnj))
    idx_cnj = None
    for e in els:
        if re.sub(r"\D", "", e.get("label") or "") == alvo and "text" in (e.get("role") or "").lower():
            idx_cnj = e.get("element_index")
            break
    if idx_cnj is None:
        logger.warning(f"[CUA] CNJ {cnj} nao encontrado na lista de Pre-cadastro")
        return False
    for e in els:
        i = e.get("element_index")
        if (i is not None and i > idx_cnj
                and "editar" in (e.get("label") or "").strip().lower()
                and "button" in (e.get("role") or "").lower()):
            logger.info(f"[CUA] Editar do CNJ {cnj} -> elemento {i}")
            return _clicar(pid, wid, i)
    logger.warning(f"[CUA] botao Editar do CNJ {cnj} nao localizado")
    return False


def clicar_label(texto, roles=("button", "link", "menu item", "menuitem")) -> bool:
    """Clica no primeiro elemento cujo label contem `texto` e o role bate."""
    pid, wid = _janela_legalone()
    if not pid:
        return False
    els = _elementos(pid, wid)
    alvo = texto.lower()
    for e in els:
        lbl = (e.get("label") or "").strip().lower()
        role = (e.get("role") or "").lower()
        if alvo in lbl and any(r in role for r in roles):
            logger.info(f"[CUA] clicar '{texto}' -> elemento {e.get('element_index')} ({lbl[:30]})")
            return _clicar(pid, wid, e.get("element_index"))
    logger.warning(f"[CUA] label '{texto}' nao encontrado")
    return False
