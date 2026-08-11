"""Fallback de clique via cua-driver (AT-SPI) para combobox que o Playwright nao commita.

Usado como ultimo recurso pelo legalone_cadastro: o Playwright digita para abrir o
dropdown e o cua-driver clica na opcao pela arvore de acessibilidade do Chromium.
Requer a infra da VM: Xvfb :99 + bus de sessao padrao + cuadriver.service.
"""
import json
import logging
import os
import shutil
import subprocess
import unicodedata

logger = logging.getLogger("AutomacaoLegalOne")

# Windows usa .exe e caminho proprio; CUA_BIN sobrescreve os dois.
CUA_BIN = os.getenv("CUA_BIN") or next(
    (p for p in (os.path.expanduser("~/.local/bin/cua-driver"),
                 os.path.expanduser("~/.local/bin/cua-driver.exe"),
                 shutil.which("cua-driver") or "") if p and os.path.exists(p)),
    os.path.expanduser("~/.local/bin/cua-driver"))


# Titulo da pagina que o Playwright esta dirigindo. Sem isso nao da' para separar a
# janela do bot das do usuario: em 04/08 o Chrome pessoal tambem estava com uma tela
# do LegalOne aberta. Quem preenche e' o legalone_cadastro, antes de acionar o CUA.
titulo_alvo: str = ""


def disponivel() -> bool:
    return os.path.exists(CUA_BIN)


def _call(tool: str, payload: dict, timeout: int = 90) -> dict | None:
    try:
        r = subprocess.run(
            [CUA_BIN, "call", tool],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            # text=True sozinho decodifica em cp1252 no Windows: o primeiro acento da
            # arvore do LegalOne matava a thread de leitura e stdout virava None —
            # era esse o '[CUA] falhou: ... not NoneType' (04/08).
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if r.returncode != 0:
            logger.warning(f"[CUA] {tool} rc={r.returncode}: {(r.stderr or r.stdout or '')[:200]}")
            return None
        # Sem isso, stdout vazio virava 'json object must be str... not NoneType' e
        # escondia o motivo real (o driver nao respondeu).
        if not (r.stdout or '').strip():
            logger.warning(f"[CUA] {tool} nao respondeu nada. stderr={(r.stderr or '')[:200]}")
            return None
        return json.loads(r.stdout)
    except Exception as e:
        logger.warning(f"[CUA] {tool} falhou ({type(e).__name__}): {e}")
        return None


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _janela_chromium():
    """Janela do navegador que a automacao dirige — nao a do usuario.

    O Playwright abre 'Chrome for Testing'; pegar a primeira janela com 'chrome'
    no titulo entregava o Chrome pessoal (04/08: 4 janelas abertas, a nossa era a
    quarta). O CUA lia e clicava na tela errada, e por isso nunca achava elemento.
    """
    d = _call("list_windows", {}, timeout=30)
    janelas = [w for w in (d or {}).get("windows", [])
               if "chrome" in (w.get("title") or "").lower()]
    if not janelas:
        return None, None
    t = (titulo_alvo or "").strip().lower()
    alvo = next((w for w in janelas if t and t in (w.get("title") or "").lower()),
                janelas[0])
    if t and t not in (alvo.get("title") or "").lower():
        logger.warning(
            f"[CUA] Janela {titulo_alvo[:40]!r} nao esta aberta; "
            f"usando {alvo.get('title', '')[:40]!r}"
        )
    return alvo.get("pid"), alvo.get("window_id")


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
    if ok is None:
        # 'Element N not in cache': a arvore mudou entre o snapshot e o clique
        # (a tela do LegalOne se reorganiza sozinha). Um snapshot novo resolve.
        logger.info("[CUA] indice invalidado — refazendo o snapshot e clicando de novo")
        st2 = _call(
            "get_window_state",
            {"pid": pid, "window_id": wid, "include_screenshot": False, "max_elements": 3000},
            timeout=120,
        )
        alvo_lbl = _norm(el.get("label"))
        novo_idx = next(
            (e.get("element_index") for e in (st2 or {}).get("elements", [])
             if _norm(e.get("label")) == alvo_lbl and e.get("element_index") is not None),
            None,
        )
        if novo_idx is not None:
            ok = _call(
                "click",
                {"pid": pid, "window_id": wid, "element_index": novo_idx},
                timeout=30,
            )
    logger.info(
        f"[CUA] Click [{el.get('role')}] '{(el.get('label') or '')[:60]}' -> {'OK' if ok else 'FALHOU'}"
    )
    return ok is not None


def clicar_campo(label: str) -> bool:
    """Clica no proprio campo/combobox pela label na arvore (dispensa seletor CSS)."""
    return clicar_opcao(label, papeis=("combo box", "entry", "text", "push button", "label"))


def arvore_resumida(max_itens: int = 250) -> list[dict]:
    """Elementos acionaveis da janela (indice/role/label) para a IA decidir."""
    pid, wid = _janela_chromium()
    if not pid:
        return []
    st = _call(
        "get_window_state",
        {"pid": pid, "window_id": wid, "include_screenshot": False, "max_elements": 3000},
        timeout=120,
    )
    itens = []
    for el in (st or {}).get("elements", []):
        lbl = (el.get("label") or "").strip()
        if lbl and el.get("element_index") is not None:
            itens.append({"i": el["element_index"], "role": el.get("role"), "label": lbl[:80]})
        if len(itens) >= max_itens:
            break
    return itens


def clicar_por_indice(indice: int) -> bool:
    pid, wid = _janela_chromium()
    if not pid:
        return False
    return _call("click", {"pid": pid, "window_id": wid, "element_index": indice}, timeout=30) is not None


def clicar_com_ia(objetivo: str, brain=None) -> bool:
    """cua = olhos (arvore AT-SPI), IA = cerebro: escolhe o elemento e clica.

    Usado quando os seletores deterministicos nao acham o alvo (UI mudou).
    """
    itens = arvore_resumida()
    if not itens:
        return False
    if brain is None:
        try:
            from claude_brain import ClaudeBrain
            brain = ClaudeBrain()
        except Exception as e:
            logger.warning(f"[CUA-IA] Sem cerebro disponivel: {e}")
            return False
    prompt = (
        f"Objetivo na tela do sistema juridico LegalOne: {objetivo}\n\n"
        f"Elementos da tela (JSON): {json.dumps(itens, ensure_ascii=False)}\n\n"
        "Responda APENAS com o numero do campo 'i' do elemento que deve ser clicado "
        "para cumprir o objetivo. Se nenhum servir, responda -1."
    )
    try:
        resposta = brain.ask(prompt)
        idx = int("".join(c for c in resposta if c.isdigit() or c == "-")[:4])
    except Exception as e:
        logger.warning(f"[CUA-IA] Resposta invalida do cerebro: {e}")
        return False
    if idx < 0:
        logger.warning(f"[CUA-IA] Cerebro nao encontrou elemento para: {objetivo}")
        return False
    alvo = next((x for x in itens if x["i"] == idx), None)
    logger.info(f"[CUA-IA] Cerebro escolheu [{idx}] {alvo['label'][:60] if alvo else '?'} para '{objetivo}'")
    return clicar_por_indice(idx)
