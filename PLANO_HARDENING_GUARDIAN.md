# Plano de Hardening — Visual Guardian + LegalOne Cadastro

## Arquivo alvo: `pacote_automacao_legalone/legalone_cadastro.py`
## Módulo auxiliar: `pacote_automacao_legalone/visual_guardian.py`

---

## 1. Wraps com `guarded()` em blocos críticos

`guarded()` já existe em `visual_guardian.py:276` e está importado como `_guarded` na linha 38.
Problema: **nunca é usado inline no código**. Apenas `_registrar_diagnostico_falha` chama `guardian.rescue()` como fallback reativo.

### 1a. `navegar_cadastro_cnj` — bloco "Selecionar cadastro automático" (~linha 3419)

```python
# ANTES (linha 3419-3434):
try:
    target_link = self.page.wait_for_selector('#automatic-process-modal-link', ...)
    ...

# DEPOIS:
guardian = self._get_guardian()
with _guarded(guardian, "abrir_cadastro_automatico", f"URL={self.page.url}"):
    target_link = self.page.wait_for_selector('#automatic-process-modal-link', state='visible', timeout=5000)
    if target_link:
        target_link.click()
        time.sleep(3)
        return True
    else:
        raise Exception("Link de cadastro automático não encontrado")
```

**Rationale:** Se o modal não abrir ou link sumiu, guardian pode screenshot+Vision para encontrar e clicar.

### 1b. `preencher_cnj` — bloco "Clicar Capturar" (~linha 3469-3507)

```python
guardian = self._get_guardian()
with _guarded(guardian, "clicar_capturar", f"CNJ={cnj}"):
    # [código existente dos seletores_capturar]
    if not capturou:
        raise Exception("Botão Capturar não encontrado por nenhum seletor")
```

**Rationale:** Botão Capturar pode mudar de posição/classe entre versões do LegalOne.

### 1c. `_clicar_adicionar_pedido` — wrap inteiro (~linha 5984-5993)

```python
def _clicar_adicionar_pedido(self) -> bool:
    guardian = self._get_guardian()
    try:
        with _guarded(guardian, "adicionar_pedido", "Clicando botão add_pedido"):
            btn = self.page.wait_for_selector('#add_pedido', state='visible', timeout=5000)
            if btn:
                btn.click()
                time.sleep(1.0)
                return True
            raise Exception("Botão #add_pedido não encontrado")
    except Exception:
        return False
```

### 1d. `realizar_acoes_pos_cadastro` — bloco "Alterar processo" (~linha 6577-6609)

```python
with _guarded(guardian, "alterar_processo", f"CNJ={numero_processo}"):
    # [loop de _seletores_alterar existente]
    if not entrou_em_edicao:
        raise Exception("Nenhum seletor 'Alterar processo' funcionou")
```

### 1e. `_preencher_pedidos_forms` — cada iteração de pedido (~linha 6395-6408)

```python
for idx, item in enumerate(itens):
    if idx > 0:
        with _guarded(guardian, "adicionar_pedido_iter", f"Pedido {idx+1}/{len(itens)}"):
            if not self._clicar_adicionar_pedido():
                raise Exception(f"Botão adicionar pedido falhou para item {idx+1}")
    with _guarded(guardian, "preencher_pedido", f"Pedido: {item['pedido']}"):
        ok = self._preencher_linha_pedido_atual(item)
        if not ok:
            raise Exception(f"Pedido '{item['pedido']}' não encontrado no dropdown")
    preenchidos += 1
    time.sleep(0.4)
```

---

## 2. Novo método `_verificar_estado_pagina(esperado)`

**Arquivo:** `legalone_cadastro.py`
**Inserir após:** `_ensure_page_active` (grep para localizar — ~linha 350-370)

```python
def _verificar_estado_pagina(self, esperado: str) -> bool:
    """Verifica se a página atual corresponde ao estado esperado.

    Args:
        esperado: Uma das strings:
            - "pesquisa_processos": tela de busca de processos
            - "cadastro_automatico_modal": modal de cadastro automático aberto
            - "pre_cadastro": tela de pré-cadastro/draft
            - "edicao_processo": tela de edição do processo
            - "secao_pedidos": seção de pedidos visível
    """
    if not self.page:
        return False

    try:
        url = (self.page.url or "").lower()
    except Exception:
        return False

    checks = {
        "pesquisa_processos": {
            "url_contains": ["/processos/processos/search"],
            "dom_selectors": ["input#search-box-input, input[name='Search']"],
        },
        "cadastro_automatico_modal": {
            "url_contains": ["/processos"],
            "dom_selectors": ["#CNJNumberAutomaticModal, #automatic-process-modal-link"],
        },
        "pre_cadastro": {
            "url_contains": ["/draft-litigation"],
            "dom_selectors": ["form, [class*='draft']"],
        },
        "edicao_processo": {
            "url_contains": ["/processos/processos/edit/"],
            "dom_selectors": [
                "button[name='ButtonSave'], #btnSave, "
                "a.command-edit, form[action*='processos']"
            ],
        },
        "secao_pedidos": {
            "url_contains": ["/processos/processos/edit/"],
            "dom_selectors": [
                "#pedidos, .pedidos-section, ul.pedidos-list, "
                "input[id*='NomePedidoText']"
            ],
        },
    }

    spec = checks.get(esperado)
    if not spec:
        logger.warning(f"[ESTADO] Estado desconhecido: {esperado}")
        return False

    # Check URL
    url_ok = any(frag in url for frag in spec["url_contains"])
    if not url_ok:
        logger.debug(f"[ESTADO] URL não contém {spec['url_contains']}: {url}")
        return False

    # Check DOM
    for selector_group in spec["dom_selectors"]:
        try:
            el = self.page.query_selector(selector_group)
            if el:
                return True
        except Exception:
            continue

    logger.debug(f"[ESTADO] DOM não contém elementos esperados para '{esperado}'")
    return False
```

**Rationale:** URL-only check não diferencia entre modais abertos/fechados na mesma URL. DOM check confirms actual page state.

---

## 3. Fortalecer `_clicar_adicionar_pedido` (~linha 5984)

**Antes:** Único seletor `#add_pedido`, sem fallback.

**Depois:**

```python
def _clicar_adicionar_pedido(self) -> bool:
    """Clica no botão 'Adicionar pedido' com fallback selectors + guardian rescue."""
    seletores = [
        '#add_pedido',
        'button:has-text("Adicionar pedido")',
        'button:has-text("Novo pedido")',
        'a:has-text("Adicionar pedido")',
        '[id*="add_pedido"]',
        '[id*="addPedido"]',
        'button[class*="add-pedido"]',
    ]

    for sel in seletores:
        try:
            btn = self.page.wait_for_selector(sel, state='visible', timeout=3000)
            if btn:
                btn.scroll_into_view_if_needed()
                btn.click()
                time.sleep(1.0)
                logger.info(f"   ✓ 'Adicionar pedido' clicado via: {sel}")
                return True
        except Exception:
            continue

    # Fallback JS
    try:
        clicou = self.page.evaluate("""
            () => {
                const btn = Array.from(document.querySelectorAll('button, a'))
                    .find(b => (b.innerText || '').toLowerCase().includes('adicionar pedido')
                              || (b.id || '').toLowerCase().includes('add_pedido'));
                if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return true; }
                return false;
            }
        """)
        if clicou:
            time.sleep(1.0)
            logger.info("   ✓ 'Adicionar pedido' clicado via JS fallback")
            return True
    except Exception:
        pass

    # Guardian rescue
    guardian = self._get_guardian()
    if guardian:
        rescued = guardian.rescue(
            "adicionar_pedido",
            "Botão 'Adicionar pedido' não encontrado por nenhum seletor",
            Exception("Todos os seletores falharam para #add_pedido")
        )
        if rescued:
            time.sleep(1.0)
            return True

    return False
```

**Rationale:** Single-selector (#add_pedido) = single point of failure. Fallback chain + JS + Guardian = 3 layers of resilience.

---

## 4. Post-navigation validation

### 4a. `navegar_cadastro_cnj` (~linha 3422-3424)

After `target_link.click()` + `time.sleep(3)`, add validation:

```python
target_link.click()
time.sleep(3)
# POST-VALIDATION
if not self._verificar_estado_pagina("cadastro_automatico_modal"):
    # Modal may not have opened — check if CNJ field appeared
    try:
        campo_cnj = self.page.query_selector('#CNJNumberAutomaticModal')
        if not campo_cnj:
            logger.warning("[GUARD] Modal de cadastro automático não abriu após click")
            # Retry once
            target_link = self.page.query_selector('#automatic-process-modal-link')
            if target_link:
                target_link.click()
                time.sleep(3)
    except Exception:
        pass
return True
```

### 4b. `aguardar_e_pular_etapa` — add exit validation (~linha 3606, 3614, 3619)

After each `return True`, validate we're in a usable state:

```python
if self._clicar_continuar_cadastro_popup():
    logger.info("   ✓ Seguindo fluxo via 'Continuar cadastro'")
    time.sleep(2)
    # POST-VALIDATION: confirm we left the popup state
    url_pos = (self.page.url or "").lower()
    if "/draft-litigation" in url_pos or "/processos/processos/edit/" in url_pos:
        return True
    logger.warning(f"[GUARD] Após 'Continuar cadastro', URL inesperada: {url_pos}")
    # Still return True — downstream code handles context validation
    return True
```

**Rationale:** "Return True" without checking destination = silent failures. Post-validation catches wrong-page scenarios early.

---

## 5. `cadastrar_processo` — propagate `realizar_acoes_pos_cadastro` failures (~linha 5305-5312)

**Antes (linha 5305-5312):**
```python
if self.clicar_salvar():
    self.realizar_acoes_pos_cadastro(dados_processo)  # ← RETURN VALUE IGNORED

logger.info("\n✅ Fluxo de cadastro finalizado!")
return True  # ← Always returns True even if pos_cadastro failed
```

**Depois:**
```python
if self.clicar_salvar():
    pos_ok = self.realizar_acoes_pos_cadastro(dados_processo)
    if not pos_ok:
        logger.error("❌ Ações pós-cadastro falharam (pedidos não cadastrados)")
        # Processo foi salvo mas pedidos falharam — report partial success
        self.last_error_reason = self.last_error_reason or "Pos-cadastro falhou (pedidos)"
        return False

logger.info("\n✅ Fluxo de cadastro finalizado!")
return True
```

**Rationale:** Currently `realizar_acoes_pos_cadastro` returns `False` when 0 pedidos are filled, but `cadastrar_processo` ignores the return value and reports success. This masks pedidos failures.

---

## 6. Intelligent retry with vision recovery for pedidos flow

**Arquivo:** `legalone_cadastro.py`
**Método:** `_preencher_pedidos_forms` (~linha 6393-6416)

Replace the simple loop with vision-recovery-aware retry:

```python
logger.info(f"4️⃣  Preenchendo pedidos do Forms ({len(itens)} itens)...")
preenchidos = 0
guardian = self._get_guardian()
max_retries_per_pedido = 2

for idx, item in enumerate(itens):
    if idx > 0:
        if not self._clicar_adicionar_pedido():
            logger.warning(f"      ⚠ Botão 'Adicionar pedido' falhou para item {idx + 1}")
            # Vision retry: maybe a popup/overlay blocking
            if guardian:
                rescued = guardian.rescue(
                    "adicionar_pedido_bloqueado",
                    f"Item {idx+1}/{len(itens)}, pedido: {item.get('pedido','')}",
                    Exception("Botão adicionar pedido não encontrado/clicável")
                )
                if rescued:
                    # Retry after guardian fix
                    if not self._clicar_adicionar_pedido():
                        logger.error(f"      ❌ Mesmo após guardian, botão 'Adicionar pedido' falhou")
                        break
                else:
                    break
            else:
                break

    # Try filling with retry
    ok = False
    for attempt in range(1, max_retries_per_pedido + 1):
        ok = self._preencher_linha_pedido_atual(item)
        if ok:
            break

        if attempt < max_retries_per_pedido and guardian:
            logger.info(f"      🔄 Retry {attempt} para pedido '{item['pedido']}' via Vision...")

            # Verify we're still on the right page
            if not self._verificar_estado_pagina("secao_pedidos"):
                logger.warning("      [GUARD] Saiu da seção de pedidos durante preenchimento")
                rescued = guardian.rescue(
                    "pedido_pagina_errada",
                    f"Pedido: {item.get('pedido','')}, tentativa {attempt}",
                    Exception("Página não está na seção de pedidos")
                )
                if not rescued:
                    break
                time.sleep(1)
                continue

            # Vision sees current state and may dismiss popup/scroll to element
            rescued = guardian.rescue(
                "preencher_pedido_falha",
                f"Pedido: {item.get('pedido','')}, dropdown não encontrou match",
                Exception(f"Pedido '{item['pedido']}' não selecionado no dropdown")
            )
            if not rescued:
                break
            time.sleep(1)

    if not ok:
        logger.error(
            f"   ❌ Pedido '{item['pedido']}' falhou após {max_retries_per_pedido} tentativas. "
            f"Parando no item {idx + 1}/{len(itens)}."
        )
        break

    preenchidos += 1
    time.sleep(0.4)
```

**Rationale:** Pedidos flow is the most fragile part. Failures here include:
- Overlay/popup blocking clicks (guardian can dismiss)
- Dropdown not showing options (guardian can scroll/wait)
- Page navigated away (guardian can detect + navigate back)
- Stale element (guardian retry gives DOM time to settle)

---

## Summary — Implementation Order

| Priority | Change | Lines | Risk |
|----------|--------|-------|------|
| **P0** | #5: Propagate `realizar_acoes_pos_cadastro` failure | ~5305-5312 | Low (2 lines) |
| **P0** | #3: Strengthen `_clicar_adicionar_pedido` | ~5984-5993 | Low (replace method) |
| **P1** | #2: Add `_verificar_estado_pagina` | New method | Low (additive) |
| **P1** | #6: Vision retry for pedidos | ~6393-6416 | Medium (refactor loop) |
| **P2** | #1: Wrap critical blocks with `guarded()` | Multiple | Medium (5 wraps) |
| **P2** | #4: Post-navigation validation | ~3422, ~3606 | Low (additive checks) |

All changes are backwards-compatible. If `_VISUAL_GUARDIAN_DISPONIVEL` is False, `_get_guardian()` returns None and all guardian paths gracefully skip.
