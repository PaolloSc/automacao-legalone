"""
Page Analyzer — preenchedor inteligente de páginas LegalOne.

Combina:
1. Snapshot estruturado dos campos visíveis (via JS) — agrupa label + input/
   widget vizinho e detecta o tipo do controle (text, date, select, radio,
   kendo-combobox, kendo-numeric, autocomplete-popup, textarea).
2. Mapeamento label-do-formulário → resposta do Forms (heurística + LLM
   opcional) — aproveita `dados['outros_dados']` quando disponível e ignora
   prefixos como "1. ", "Requer resposta. ", "Opção única.", etc.
3. Execução por tipo de widget — clica, digita, espera popup do Kendo e
   clica na opção correta; em radios identifica a opção pelo texto; em
   datas usa o formato 'dd/MM/yyyy'.

Exporta:
    get_analyzer() -> PageAnalyzer
    PageAnalyzer.ver_e_preencher(page, dados, confianca_minima=0.4)
        -> {"resultado": {"sucesso": int, "tentativas": int, "campos": [...]}}
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from typing import Any, Iterable

logger = logging.getLogger(__name__)

try:  # opcional — LLM ajuda no matching ambíguo
    from claude_brain import ClaudeBrain  # type: ignore
except Exception:  # pragma: no cover
    ClaudeBrain = None  # type: ignore

try:  # opcional — Scrapling para parsing HTML resiliente
    # https://github.com/D4Vinci/Scrapling
    try:
        from scrapling import Selector as _ScraplingAdaptor  # type: ignore  # 0.4+
    except ImportError:
        from scrapling import Adaptor as _ScraplingAdaptor  # type: ignore  # 0.2/0.3
except Exception:  # pragma: no cover
    _ScraplingAdaptor = None  # type: ignore


# ---------------------------------------------------------------------------
# Snapshot dos campos da página
# ---------------------------------------------------------------------------

_SNAPSHOT_JS = r"""
() => {
    const visivel = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return false;
        const cs = window.getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
    };
    const limpar = (s) => (s || '').replace(/\s+/g, ' ').trim();

    // Para um <label> (ou .field-label), descobre o input controlado.
    // Prioriza for= mas se este apontar para input invisível (Kendo hidden),
    // procura pelo input visível dentro do mesmo wrapper Kendo.
    const inputDoLabel = (lbl) => {
        let alvo = null;
        const forId = lbl.getAttribute && lbl.getAttribute('for');
        if (forId) alvo = document.getElementById(forId);

        if (!alvo) {
            // Procura input próximo: irmão seguinte ou container pai
            let cont = lbl.closest('.field, .form-group, .control-group, '
                + 'dl, .field-row, .editor-row, .form-row, .input-wrapper, '
                + 'div[class*="field"], div[class*="row"]');
            if (!cont) cont = lbl.parentElement;
            if (cont) {
                alvo = cont.querySelector(
                    'input:not([type=hidden]):not([type=button]):not([type=submit]),'
                    + ' select, textarea'
                );
            }
        }
        if (!alvo) return null;

        // Se o alvo é hidden ou invisível, procura o k-input no mesmo wrapper
        const cs = window.getComputedStyle(alvo);
        const escondido = (alvo.type === 'hidden')
            || cs.display === 'none' || cs.visibility === 'hidden';
        if (escondido) {
            const wrap = alvo.parentElement && (
                alvo.closest('.k-widget, .k-combobox, .k-dropdown, '
                    + '.k-datepicker, .k-numerictextbox, .k-autocomplete')
                || alvo.parentElement.querySelector('.k-widget')
                || alvo.parentElement
            );
            if (wrap) {
                const cand = wrap.querySelector(
                    'input.k-input, input.k-textbox, input[type=text]:not([type=hidden])'
                );
                if (cand && visivel(cand)) alvo = cand;
            }
        }
        return visivel(alvo) ? alvo : null;
    };

    const temLookupSibling = (el) => {
        // sobe alguns níveis e procura botão de lookup ao lado do input
        let p = el;
        for (let i = 0; i < 5 && p; i++) {
            if (p.querySelector
                && p.querySelector(':scope .lookup-button, '
                    + ':scope .lookup-show, :scope .field-lookup, '
                    + ':scope span.k-select, :scope .k-i-arrow-s')) {
                return true;
            }
            p = p.parentElement;
        }
        return false;
    };

    const tipoDe = (el) => {
        const tag = (el.tagName || '').toLowerCase();
        const cls = (el.className || '').toString().toLowerCase();
        if (tag === 'select') return 'select';
        if (tag === 'textarea') return 'textarea';
        if (tag === 'input') {
            const t = (el.type || 'text').toLowerCase();
            if (t === 'checkbox') return 'checkbox';
            if (t === 'radio') return 'radio';
            if (t === 'date') return 'date-native';
            const wrap = el.closest('.k-widget, .k-combobox, .k-dropdown, '
                + '.k-datepicker, .k-numerictextbox, .k-autocomplete');
            if (wrap) {
                const wc = wrap.className.toLowerCase();
                if (wc.includes('datepicker')) return 'kendo-date';
                if (wc.includes('numeric')) return 'kendo-numeric';
                if (wc.includes('combobox') || wc.includes('dropdown')
                    || wc.includes('autocomplete')) return 'kendo-combobox';
            }
            if (cls.includes('k-input') || cls.includes('k-textbox')) return 'kendo-combobox';
            // Detecta autocomplete via botão de lookup vizinho (LegalOne usa
            // .lookup-button / .lookup-show ao lado de inputs sem classe Kendo)
            if (temLookupSibling(el)) return 'kendo-combobox';
            if (cls.includes('date') || (el.placeholder || '').match(/\d{2}\/\d{2}\/\d{4}/)) return 'date';
            return 'text';
        }
        return 'other';
    };

    const labels = Array.from(document.querySelectorAll(
        'label, .field-label, .control-label, .editor-label'
    )).filter(visivel);

    const seenInput = new Set();
    const campos = [];

    for (const lbl of labels) {
        const texto = limpar(lbl.innerText);
        if (!texto || texto.length > 100) continue;

        // Detecta radio-group: label que contém vários radios
        const radios = lbl.querySelectorAll('input[type=radio]');
        if (radios.length > 1) {
            const opcoes = Array.from(radios).map(r => {
                const lbl2 = r.id && document.querySelector(`label[for="${r.id}"]`);
                const txt = lbl2 ? lbl2.innerText : (r.parentElement?.innerText || r.value);
                return { value: r.value, label: limpar(txt), checked: r.checked };
            });
            campos.push({
                label: texto, tipo: 'radio-group',
                name: radios[0].name, opcoes, id: null,
            });
            radios.forEach(r => seenInput.add(r));
            continue;
        }

        const inp = inputDoLabel(lbl);
        if (!inp || seenInput.has(inp)) continue;
        const tipo = tipoDe(inp);
        if (tipo === 'other') continue;

        if (tipo === 'radio') {
            const grupo = Array.from(document.querySelectorAll(
                `input[type=radio][name="${inp.name}"]`
            ));
            grupo.forEach(r => seenInput.add(r));
            const opcoes = grupo.map(r => {
                const lbl2 = r.id && document.querySelector(`label[for="${r.id}"]`);
                const txt = lbl2 ? lbl2.innerText : (r.parentElement?.innerText || r.value);
                return { value: r.value, label: limpar(txt), checked: r.checked };
            });
            campos.push({
                label: texto, tipo: 'radio-group',
                name: inp.name, opcoes, id: null,
            });
            continue;
        }

        seenInput.add(inp);
        let opcoes = null;
        if (tipo === 'select') {
            opcoes = Array.from(inp.options).map(o => ({
                value: o.value, label: limpar(o.text), selected: o.selected
            }));
        }
        campos.push({
            label: texto,
            tipo,
            id: inp.id || null,
            name: inp.name || null,
            value: (inp.value || '').toString(),
            placeholder: inp.placeholder || '',
            opcoes,
        });
    }
    return campos;
}
"""


# ---------------------------------------------------------------------------
# Helpers de matching
# ---------------------------------------------------------------------------

_PREFIX_RE = re.compile(r"^\s*\d+\.\s*")
_META_RE = re.compile(
    r"\b(requer\s+resposta|texto\s+(de\s+linha\s+[uú]nica|multilinha|longo)"
    r"|op[çc][aã]o\s+[uú]nica|m[uú]ltipla\s+escolha|obrigat[oó]ria|data|n[uú]mero)\.?",
    re.IGNORECASE,
)


def _normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    t = _PREFIX_RE.sub("", str(texto))
    t = _META_RE.sub("", t)
    t = t.replace("?", "").replace(":", "").strip(" -–.")
    nfkd = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()


# tokens que invalidam o match quando aparecem em apenas um dos lados
# (evitam confundir campos análogos na seção "Encerramento" com os
# da seção "Resultado", e campos personalizados com dados do Forms)
_TOKENS_DISCRIMINATIVOS = {
    "encerramento", "encerrar", "baixa",
    "obra", "supermercado", "loja", "residencial",
}


def _similar(a: str, b: str) -> float:
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    # Se um lado tem token discriminativo que o outro não tem, rejeita
    only_a = ta - tb
    only_b = tb - ta
    if (only_a & _TOKENS_DISCRIMINATIVOS) or (only_b & _TOKENS_DISCRIMINATIVOS):
        return 0.0
    # Containment por palavras inteiras (não por substring) — evita
    # 'acao' bater em 'situacao' ou 'motivo' bater em 'motivo do resultado'.
    if ta.issubset(tb) or tb.issubset(ta):
        # quanto mais próximo o tamanho, maior a confiança
        ratio = min(len(ta), len(tb)) / max(len(ta), len(tb))
        return 0.7 + 0.25 * ratio
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def _coletar_dados_kv(dados: dict[str, Any]) -> dict[str, str]:
    """Achata dados em label→valor, preferindo `outros_dados` cru.
    Ignora chaves auxiliares com sufixo ' - Texto completo', ' - Opções' etc.
    """
    out: dict[str, str] = {}
    if not isinstance(dados, dict):
        return out

    # campos top-level conhecidos
    top = {
        "Valor da causa": dados.get("valor_causa"),
        "Fase": dados.get("fase"),
        "Instância": dados.get("instancia"),
        "Comarca": dados.get("comarca"),
        "Cidade": dados.get("cidade") or dados.get("cidade_comarca"),
        "Natureza": dados.get("natureza"),
        "Status": dados.get("status_processo"),
        "Cliente principal": dados.get("cliente"),
        "Contrário principal": dados.get("contrario"),
    }
    for k, v in top.items():
        if v and len(str(v)) <= 300:
            out[k] = str(v)

    outros = dados.get("outros_dados") or {}
    if isinstance(outros, dict):
        # primeiro: chaves "Marcadas" (selecionadas em radio/checkbox)
        marcadas: dict[str, str] = {}
        for k, v in outros.items():
            if not isinstance(k, str):
                continue
            if k.endswith(" - Marcadas"):
                base = k[: -len(" - Marcadas")]
                if isinstance(v, (list, tuple)) and v:
                    marcadas[base] = str(v[0])
                elif isinstance(v, str):
                    marcadas[base] = v
        for base, val in marcadas.items():
            limpa = _PREFIX_RE.sub("", base).strip()
            limpa = _META_RE.sub("", limpa).strip(" .-")
            if limpa and val:
                out[limpa] = val

        # depois: respostas diretas (não-meta)
        for k, v in outros.items():
            if not isinstance(k, str) or not isinstance(v, (str, int, float)):
                continue
            if any(k.endswith(suf) for suf in (
                " - Texto completo", " - Opções", " - Marcadas",
            )):
                continue
            limpa = _PREFIX_RE.sub("", k).strip()
            limpa = _META_RE.sub("", limpa).strip(" .-")
            if not limpa:
                continue
            valor = str(v).strip()
            if not valor or valor.lower().startswith("nenhuma resposta"):
                continue
            # remove o próprio título grudado no valor (ex: "X Texto único. valor")
            for prefixo in (k, limpa):
                if valor.lower().startswith(prefixo.lower()):
                    valor = valor[len(prefixo):].strip(" .-:")
            if len(valor) > 500:
                continue
            # não sobrescreve se já temos a Marcadas
            if limpa not in out:
                out[limpa] = valor

    return out


# ---------------------------------------------------------------------------
# Preenchimento por tipo de widget
# ---------------------------------------------------------------------------


class _Filler:
    def __init__(self, page) -> None:
        self.page = page

    def fill_text(self, campo: dict, valor: str) -> bool:
        sel = self._sel(campo)
        if not sel:
            return False
        try:
            el = self.page.query_selector(sel)
            if not el:
                return False
            el.click()
            el.fill("")
            el.type(valor, delay=20)
            el.evaluate(
                "(el) => { ['input','change','blur'].forEach(e => "
                "el.dispatchEvent(new Event(e, { bubbles: true }))); }"
            )
            return True
        except Exception as e:
            logger.debug(f"[FILLER] text falhou ({campo.get('label')}): {e}")
            return False

    def fill_textarea(self, campo: dict, valor: str) -> bool:
        return self.fill_text(campo, valor)

    def fill_date(self, campo: dict, valor: str) -> bool:
        # Normaliza para dd/MM/yyyy
        v = valor.strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            v = f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
        return self.fill_text(campo, v)

    def fill_select(self, campo: dict, valor: str) -> bool:
        sel = self._sel(campo)
        if not sel:
            return False
        try:
            opcoes = campo.get("opcoes") or []
            alvo = self._melhor_opcao([o.get("label", "") for o in opcoes], valor)
            if alvo is None:
                return False
            valor_alvo = opcoes[alvo].get("value") or opcoes[alvo].get("label")
            self.page.select_option(sel, value=valor_alvo)
            return True
        except Exception as e:
            logger.debug(f"[FILLER] select falhou ({campo.get('label')}): {e}")
            return False

    def fill_radio(self, campo: dict, valor: str) -> bool:
        try:
            opcoes = campo.get("opcoes") or []
            labels = [o.get("label", "") for o in opcoes]
            idx = self._melhor_opcao(labels, valor)
            if idx is None:
                return False
            alvo = opcoes[idx]
            # Tenta clicar no label associado ao radio
            name = campo.get("name")
            value = alvo.get("value")
            if name and value is not None:
                clicou = self.page.evaluate(
                    """
                    ({name, value}) => {
                        const radios = Array.from(document.querySelectorAll(
                            `input[type=radio][name="${name}"]`));
                        const r = radios.find(x => x.value === value);
                        if (!r) return false;
                        r.click();
                        r.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    """,
                    {"name": name, "value": value},
                )
                return bool(clicou)
            return False
        except Exception as e:
            logger.debug(f"[FILLER] radio falhou ({campo.get('label')}): {e}")
            return False

    def fill_kendo_combobox(self, campo: dict, valor: str) -> bool:
        sel = self._sel(campo)
        if not sel:
            return False
        try:
            el = self.page.query_selector(sel)
            if not el:
                return False

            # 0) Fecha qualquer popup pendente
            try:
                self.page.keyboard.press("Escape")
                time.sleep(0.2)
            except Exception:
                pass

            el.scroll_into_view_if_needed()

            # 1) Estratégia principal: clica no botão lookup-button para
            #    abrir o popup-tabela do LegalOne, lê <td data-val-field>
            #    e clica no que casar com o valor.
            abriu = self._abrir_lookup(el, campo)
            if abriu:
                opcoes_dom = self._coletar_opcoes_visiveis()
                if opcoes_dom:
                    idx = _Filler._melhor_opcao(
                        [o["texto"] for o in opcoes_dom], valor
                    )
                    if idx is not None:
                        try:
                            texto_escolhido = opcoes_dom[idx]["texto"]
                            alvo_el = opcoes_dom[idx]["el"]
                            # Sobe até o <tr> mais próximo, alguns popups
                            # esperam o clique na linha inteira.
                            try:
                                tr = alvo_el.evaluate_handle(
                                    "el => el.closest('tr') || el"
                                )
                                if tr:
                                    try:
                                        tr.as_element().click()
                                    except Exception:
                                        alvo_el.click()
                            except Exception:
                                alvo_el.click()
                            time.sleep(0.3)
                            # Double-click — alguns popups exigem para
                            # confirmar a seleção.
                            try:
                                alvo_el.dblclick()
                            except Exception:
                                pass
                            time.sleep(0.3)
                            # Procura botão de confirmação ("Selecionar",
                            # "Confirmar", "OK") dentro do popup
                            self._clicar_botao_confirmacao_popup()
                            time.sleep(0.4)
                            self._forcar_valor_kendo(campo, texto_escolhido)
                            time.sleep(0.2)
                            try:
                                final_val = (el.input_value() or "").strip()
                                if final_val:
                                    return True
                            except Exception:
                                return True
                        except Exception as e:
                            logger.debug(f"[FILLER] click td falhou: {e}")
                # Se o popup abriu mas não achou opção que casa, fecha
                try:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.15)
                except Exception:
                    pass

            # 2) Fallback: digitar + ArrowDown + Enter (autocomplete Kendo)
            try:
                el.click()
                el.fill("")
                el.type(valor, delay=35)
                time.sleep(0.7)
                self.page.wait_for_selector(
                    ".k-list-container:visible, "
                    ".k-animation-container:visible, "
                    "ul.k-list:visible li, "
                    'td[data-val-field="Value"]:visible',
                    timeout=2500,
                )
                el.press("ArrowDown")
                time.sleep(0.15)
                el.press("Enter")
                time.sleep(0.25)
                el.evaluate(
                    "el => ['change','blur'].forEach("
                    "e => el.dispatchEvent(new Event(e, {bubbles:true})))"
                )
                final_val = (el.input_value() or "").strip()
                if final_val:
                    return True
            except Exception as e:
                logger.debug(f"[FILLER] fallback teclado falhou: {e}")

            # 3) Último recurso
            try:
                el.fill(valor)
                el.press("Tab")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.debug(f"[FILLER] kendo falhou ({campo.get('label')}): {e}")
            return False

    # ------------------------------------------------------------------
    def _abrir_lookup(self, input_el, campo: dict) -> bool:
        """Procura e clica no botão de lookup ao lado do input.
        Tenta vários seletores: lookup-button/lookup-show, k-select,
        k-i-arrow-s, botão com ícone de lupa, etc.
        Retorna True se algum dropdown ficou visível."""
        try:
            container_id = (
                campo.get("id") or campo.get("name") or ""
            )
            # Procura botão de lookup no entorno do input
            seletores = [
                'div.lookup-button.lookup-show',
                'div.lookup-show',
                '.lookup-button',
                'span.k-select',
                '.k-icon.k-i-arrow-s',
                '.k-icon.k-i-arrow-60-down',
                'button[aria-label*="abrir" i]',
                'button[title*="lookup" i]',
            ]
            ancestrais_js = """
                (input) => {
                    let p = input;
                    const out = [];
                    for (let i = 0; i < 6 && p; i++) {
                        out.push(p);
                        p = p.parentElement;
                    }
                    return out;
                }
            """
            ancestrais = input_el.evaluate_handle(ancestrais_js)
            # Em vez de iterar handles, vamos usar query relativa via JS
            achou = self.page.evaluate(
                """
                ({selectors, inputId, inputName}) => {
                    const input = (inputId && document.getElementById(inputId))
                        || (inputName && document.querySelector(`[name="${inputName}"]`));
                    if (!input) return false;
                    let p = input;
                    for (let i = 0; i < 8 && p; i++) {
                        for (const sel of selectors) {
                            const btn = p.querySelector(sel);
                            if (btn && btn.offsetParent !== null) {
                                btn.click();
                                return true;
                            }
                        }
                        p = p.parentElement;
                    }
                    return false;
                }
                """,
                {
                    "selectors": seletores,
                    "inputId": campo.get("id"),
                    "inputName": campo.get("name"),
                },
            )
            if not achou:
                return False
            # Aguarda popup ficar visível
            try:
                self.page.wait_for_selector(
                    ".k-list-container:visible, .k-animation-container:visible, "
                    ".lookup-result:visible, .lookup-popup:visible, "
                    "ul.k-list li",
                    timeout=3000,
                )
            except Exception:
                pass
            time.sleep(0.4)
            return True
        except Exception as e:
            logger.debug(f"[FILLER] _abrir_lookup falhou: {e}")
            return False

    def _clicar_botao_confirmacao_popup(self) -> bool:
        """Procura e clica em botões 'Selecionar/Confirmar/OK' dentro
        de popups visíveis."""
        try:
            return bool(self.page.evaluate(
                """
                () => {
                    const norm = s => (s||'').toLowerCase()
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').trim();
                    const alvos = ['selecionar','confirmar','ok','aplicar','salvar e fechar'];
                    const containers = Array.from(document.querySelectorAll(
                        '.lookup-popup, .lookup-result, .modal.show, '
                        + '.k-window, .k-animation-container'
                    )).filter(c => c.offsetParent !== null);
                    for (const c of containers) {
                        const btns = c.querySelectorAll('button, input[type=button], input[type=submit], a.button');
                        for (const b of btns) {
                            const t = norm(b.innerText || b.value || '');
                            if (alvos.includes(t)) {
                                b.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
                """
            ))
        except Exception:
            return False

    def _forcar_valor_kendo(self, campo: dict, texto: str) -> None:
        """Após clicar a opção do popup, NÃO sobrescreve `el.value`
        (isso destruiria a sincronia Kendo entre o input visível e o
        hidden Id que vai no submit). Apenas dispara change/blur para
        garantir que o form `dirty-state` seja atualizado, e — se o
        widget tem API jQuery — confirma o valor pela API oficial,
        que já cuida de propagar para o hidden Id."""
        try:
            self.page.evaluate(
                """
                ({inputId, inputName, texto}) => {
                    const sel = inputId ? `#${inputId}`
                        : (inputName ? `[name="${inputName}"]` : null);
                    if (!sel) return;
                    const el = document.querySelector(sel);
                    if (!el) return;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                    if (typeof window.$ === 'function' && window.$.fn && window.$.fn.data) {
                        const $el = window.$(sel);
                        const widget = $el.data('kendoComboBox')
                            || $el.data('kendoDropDownList')
                            || $el.data('kendoAutoComplete');
                        if (widget) {
                            try {
                                // só seta se o widget está vazio — o click
                                // anterior na opção JÁ deve ter setado.
                                const cur = (typeof widget.value === 'function')
                                    ? widget.value() : '';
                                if (!cur) {
                                    if (typeof widget.text === 'function') widget.text(texto);
                                    if (typeof widget.value === 'function') widget.value(texto);
                                }
                                if (typeof widget.trigger === 'function') {
                                    widget.trigger('change');
                                }
                            } catch (e) {}
                        }
                    }
                }
                """,
                {
                    "inputId": campo.get("id"),
                    "inputName": campo.get("name"),
                    "texto": texto,
                },
            )
        except Exception as e:
            logger.debug(f"[FILLER] _forcar_valor_kendo falhou: {e}")

    def _coletar_opcoes_visiveis(self) -> list[dict]:
        """Pega itens clicáveis visíveis nos popups conhecidos.
        LegalOne usa popup em tabela com <td data-val-field="Value">.
        Também suporta listas Kendo padrão.
        """
        try:
            handles = self.page.query_selector_all(
                # Popup-tabela do LegalOne (formato principal)
                'td[data-val-field="Value"], '
                'td[data-val-field="Name"], '
                'td[data-val-field="Text"], '
                # Linhas inteiras (fallback caso o td seja só wrapper)
                '.lookup-popup tr td, '
                '.lookup-result tr td, '
                # Listas Kendo
                ".k-list-container .k-item, "
                ".k-animation-container .k-item, "
                "ul.k-list:visible li, "
                # Genéricos
                ".lookup-result li, "
                ".lookup-popup li, "
                ".dropdown-menu.show li, .dropdown-menu.show a"
            )
            out = []
            seen_text = set()
            for h in handles:
                try:
                    if not h.is_visible():
                        continue
                    txt = (h.inner_text() or "").strip()
                    if not txt or len(txt) > 200:
                        continue
                    # dedup por texto
                    key = txt.lower()
                    if key in seen_text:
                        continue
                    seen_text.add(key)
                    out.append({"el": h, "texto": txt})
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def fill_kendo_numeric(self, campo: dict, valor: str) -> bool:
        # Numérico aceita só dígitos + separador
        v = re.sub(r"[^\d,.\-]", "", str(valor))
        return self.fill_text(campo, v)

    # ------------------------------------------------------------------
    def _sel(self, campo: dict) -> str | None:
        if campo.get("id"):
            return f"#{campo['id']}"
        if campo.get("name"):
            return f'[name="{campo["name"]}"]'
        return None

    @staticmethod
    def _melhor_opcao(opcoes: list[str], valor: str) -> int | None:
        if not opcoes:
            return None
        scores = [(_similar(o, valor), i) for i, o in enumerate(opcoes)]
        scores.sort(reverse=True)
        if scores and scores[0][0] >= 0.7:
            return scores[0][1]
        return None


# ---------------------------------------------------------------------------
# Page Analyzer
# ---------------------------------------------------------------------------


class PageAnalyzer:
    def __init__(self) -> None:
        self._brain = None
        if ClaudeBrain is not None:
            try:
                self._brain = ClaudeBrain()
            except Exception as e:
                logger.warning(f"[PAGE_ANALYZER] LLM indisponível: {e}")
                self._brain = None

    @property
    def disponivel(self) -> bool:
        # disponível mesmo sem LLM — usa heurística
        return True

    # ------------------------------------------------------------------
    def _enriquecer_via_scrapling(self, page, campos: list[dict]) -> list[dict]:
        """Usa Scrapling (https://github.com/D4Vinci/Scrapling) para parsear
        o HTML e adicionar pares label→input que o snapshot via JS pode ter
        deixado escapar (ex.: campos em iframes/seções colapsadas após a
        captura inicial). Idempotente: não duplica ids já vistos."""
        if _ScraplingAdaptor is None:
            return campos
        try:
            html = page.content()
        except Exception as e:
            logger.debug(f"[SCRAPLING] page.content() falhou: {e}")
            return campos

        try:
            ad = _ScraplingAdaptor(html, auto_match=False)
        except Exception as e:
            logger.debug(f"[SCRAPLING] Adaptor falhou: {e}")
            return campos

        ja_vistos = {(c.get("id") or c.get("name") or c.get("label")) for c in campos}
        adicionados = 0

        try:
            # Para cada label[for=...], localiza o input correspondente
            for lbl in ad.css("label[for]"):
                try:
                    for_id = lbl.attrib.get("for")
                    texto = (lbl.text or "").strip()
                    if not for_id or not texto:
                        continue
                    if for_id in ja_vistos or texto in ja_vistos:
                        continue
                    inp = ad.css_first(f"#{for_id}")
                    if not inp:
                        continue
                    tag = (inp.tag or "").lower()
                    if tag not in ("input", "select", "textarea"):
                        continue
                    cls = (inp.attrib.get("class") or "").lower()
                    placeholder = inp.attrib.get("placeholder") or ""
                    tipo_attr = (inp.attrib.get("type") or "text").lower()
                    if tag == "select":
                        tipo = "select"
                    elif tag == "textarea":
                        tipo = "textarea"
                    elif "k-input" in cls or "k-textbox" in cls:
                        tipo = "kendo-combobox"
                    elif tipo_attr == "radio":
                        tipo = "radio-group"
                    elif tipo_attr == "checkbox":
                        tipo = "checkbox"
                    elif tipo_attr == "date" or "date" in cls:
                        tipo = "date"
                    else:
                        tipo = "text"
                    campos.append({
                        "label": texto,
                        "tipo": tipo,
                        "id": for_id,
                        "name": inp.attrib.get("name"),
                        "value": inp.attrib.get("value", ""),
                        "placeholder": placeholder,
                        "opcoes": None,
                        "_origem": "scrapling",
                    })
                    ja_vistos.add(for_id)
                    adicionados += 1
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[SCRAPLING] enriquecimento falhou: {e}")

        if adicionados:
            logger.info(f"[SCRAPLING] +{adicionados} campos adicionados via parser HTML")
        return campos

    def ver_e_preencher(
        self,
        page,
        dados: dict[str, Any],
        confianca_minima: float = 0.85,
        labels_alvo: list[str] | None = None,
    ) -> dict[str, Any]:
        """Se `labels_alvo` for fornecido, só tenta preencher campos cujo
        label esteja na lista (modo correção pós-erro)."""
        try:
            campos = page.evaluate(_SNAPSHOT_JS) or []
        except Exception as e:
            logger.warning(f"[PAGE_ANALYZER] Falha no snapshot: {e}")
            return {"resultado": {"sucesso": 0, "tentativas": 0, "campos": []}}

        # Enriquece com Scrapling se disponível
        campos = self._enriquecer_via_scrapling(page, campos)

        # NÃO sobrescreve campos já preenchidos. Selects ficam de fora
        # também — uma vez que sempre têm valor inicial. Para radios,
        # tenta apenas se nenhuma opção está marcada.
        def _vazio(c: dict) -> bool:
            tipo = c.get("tipo", "")
            if tipo == "radio-group":
                opcoes = c.get("opcoes") or []
                return not any(o.get("checked") for o in opcoes)
            if tipo == "select":
                # select sempre tem valor; só preenche se for valor "vazio"
                return not (c.get("value") or "").strip()
            return not (c.get("value") or "").strip()

        candidatos = [c for c in campos if _vazio(c)]
        if labels_alvo:
            alvos_norm = {_normalizar(l) for l in labels_alvo}
            candidatos = [
                c for c in candidatos
                if _normalizar(c.get("label", "")) in alvos_norm
            ]
        logger.info(
            f"[PAGE_ANALYZER] {len(candidatos)} campos candidatos "
            f"(de {len(campos)} no total)"
        )

        kv = _coletar_dados_kv(dados)
        if not kv:
            logger.info("[PAGE_ANALYZER] Nenhum dado para preencher")
            return {"resultado": {"sucesso": 0, "tentativas": 0, "campos": []}}

        # Matching: para cada campo candidato, escolhe o melhor par (chave_kv, score)
        pares: list[tuple[dict, str, str, float]] = []
        kv_keys = list(kv.keys())
        usados: set[str] = set()
        for campo in candidatos:
            label = campo.get("label", "")
            melhor_key, melhor_score = None, 0.0
            for k in kv_keys:
                if k in usados:
                    continue
                s = _similar(label, k)
                if s > melhor_score:
                    melhor_key, melhor_score = k, s
            if melhor_key and melhor_score >= confianca_minima:
                usados.add(melhor_key)
                pares.append((campo, melhor_key, kv[melhor_key], melhor_score))

        logger.info(f"[PAGE_ANALYZER] {len(pares)} pares casados acima do limite")

        filler = _Filler(page)
        sucesso = 0
        relatorio: list[dict] = []
        for campo, chave, valor, score in pares:
            tipo = campo.get("tipo", "")
            label = campo.get("label", "")
            ok = False
            try:
                if tipo == "kendo-combobox":
                    ok = filler.fill_kendo_combobox(campo, valor)
                elif tipo == "kendo-numeric":
                    ok = filler.fill_kendo_numeric(campo, valor)
                elif tipo in ("kendo-date", "date", "date-native"):
                    ok = filler.fill_date(campo, valor)
                elif tipo == "select":
                    ok = filler.fill_select(campo, valor)
                elif tipo == "radio-group":
                    ok = filler.fill_radio(campo, valor)
                elif tipo == "textarea":
                    ok = filler.fill_textarea(campo, valor)
                else:
                    ok = filler.fill_text(campo, valor)
            except Exception as e:
                logger.debug(f"[PAGE_ANALYZER] erro ao preencher '{label}': {e}")

            if ok:
                sucesso += 1
                logger.info(
                    f"   ✓ [{tipo}] '{label}' ← '{valor}' (score={score:.2f})"
                )
            else:
                logger.info(
                    f"   ✗ [{tipo}] '{label}' (alvo='{valor}', score={score:.2f})"
                )
            relatorio.append({
                "label": label, "tipo": tipo, "valor": valor,
                "score": score, "ok": ok,
            })
            time.sleep(0.15)

        return {
            "resultado": {
                "sucesso": sucesso,
                "tentativas": len(pares),
                "campos": relatorio,
            }
        }


_singleton: PageAnalyzer | None = None


def get_analyzer() -> PageAnalyzer:
    global _singleton
    if _singleton is None:
        _singleton = PageAnalyzer()
    return _singleton
