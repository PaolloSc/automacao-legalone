"""
Módulo para extrair dados de respostas do Microsoft Forms
Usa Firecrawl como método principal e Playwright como fallback
"""

import asyncio
from playwright.async_api import async_playwright
import re
import logging
from datetime import datetime
import unicodedata
import os

try:
    from forms_mapping import mapear_formulario
    FORMS_MAPPING_DISPONIVEL = True
except Exception as _mapping_error:
    FORMS_MAPPING_DISPONIVEL = False
    mapear_formulario = None

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

VERBOSE_FORMS_LOGS = os.getenv("FORMS_VERBOSE_LOGS", "0").strip().lower() in ("1", "true", "yes", "y")

# Scrapling opcional (fallback de captura rápida de texto)
try:
    from scrapling import Fetcher as _ScraplingFetcher
    _scrapling_fetcher = _ScraplingFetcher()

    def scrapling_fetch_text(url: str) -> str:
        """Busca texto de uma URL usando Scrapling Fetcher."""
        page = _scrapling_fetcher.get(url)
        return page.get_all_text() if page else ""

    SCRAPLING_DISPONIVEL = True
    logger.info("[INIT] Scrapling disponivel (v0.3+) - sera usado como fallback de texto")
except ImportError:
    SCRAPLING_DISPONIVEL = False
    logger.warning("[INIT] Scrapling nao disponivel - fallback de texto desativado")
except Exception as _e:
    SCRAPLING_DISPONIVEL = False
    logger.warning(f"[INIT] Scrapling falhou ao inicializar: {_e}")

# Tenta importar Firecrawl
try:
    from firecrawl_extractor import FirecrawlExtractor
    FIRECRAWL_DISPONIVEL = True
    logger.info("[INIT] Firecrawl disponivel - usando extracao inteligente")
except ImportError:
    FIRECRAWL_DISPONIVEL = False
    logger.warning("[INIT] Firecrawl nao disponivel - usando apenas Playwright")


class FormsExtractor:
    """Extrai dados de respostas do Microsoft Forms"""

    def __init__(self, state_file="browser_data/state.json", counter_file="ultimo_processo.txt",
                 use_firecrawl=True, firecrawl_api_key=None):
        """
        Inicializa o extrator

        Args:
            state_file: Caminho para arquivo de sessão do navegador
            counter_file: Caminho para arquivo que armazena o último número processado
            use_firecrawl: Se True, tenta usar Firecrawl primeiro
            firecrawl_api_key: Chave da API Firecrawl (default: env FIRECRAWL_API_KEY)
        """
        if firecrawl_api_key is None:
            firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self.state_file = state_file
        self.counter_file = counter_file
        self.use_firecrawl = use_firecrawl and FIRECRAWL_DISPONIVEL

        # --- Estado persistente do navegador (mantém Forms aberto) ---
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._forms_aberto = False  # True quando já está em "Verificar resultados individuais"
        self._forms_url_base = None  # URL base do Forms sendo monitorado

        # Inicializa Firecrawl se disponível
        self.firecrawl = None
        if self.use_firecrawl:
            try:
                self.firecrawl = FirecrawlExtractor(api_key=firecrawl_api_key)
                logger.info("[INIT] Firecrawl ativado para extracao inteligente")
            except Exception as e:
                logger.warning(f"[INIT] Erro ao inicializar Firecrawl: {e}")
                self.use_firecrawl = False

        if not FORMS_MAPPING_DISPONIVEL:
            logger.warning("[INIT] forms_mapping indisponível - mapeamento centralizado desativado")

    def _aplicar_mapeamento_forms(self, dados_extraidos: dict) -> dict:
        """Aplica o mapeamento centralizado do Forms ao payload extraído."""
        if not FORMS_MAPPING_DISPONIVEL or not mapear_formulario:
            return dados_extraidos

        try:
            resultado_mapeamento = mapear_formulario(dados_extraidos)
        except Exception as e:
            logger.warning(f"[MAPEAMENTO] Erro ao aplicar forms_mapping: {e}")
            return dados_extraidos

        dados_extraidos['mapeamento_forms'] = resultado_mapeamento
        dados_extraidos['faltando_obrigatorios_forms'] = resultado_mapeamento.get('faltando_obrigatorios', [])
        dados_extraidos['nao_mapeados_forms'] = resultado_mapeamento.get('nao_mapeados', [])

        campos_mapeados = resultado_mapeamento.get('campos') or {}
        for campo, valor in campos_mapeados.items():
            if valor and not dados_extraidos.get(campo):
                dados_extraidos[campo] = valor

        tipo_tarefa = resultado_mapeamento.get('tipo_tarefa_identificada')
        if tipo_tarefa:
            dados_extraidos['tipo_tarefa_identificada'] = tipo_tarefa

        outros = dados_extraidos.setdefault('outros_dados', {})
        if resultado_mapeamento.get('tipo_cadastro') and not dados_extraidos.get('tipo_cadastro'):
            dados_extraidos['tipo_cadastro'] = resultado_mapeamento['tipo_cadastro']

        if campos_mapeados:
            outros.setdefault('Mapeamento Forms - Campos', campos_mapeados)
        if resultado_mapeamento.get('faltando_obrigatorios'):
            outros.setdefault(
                'Mapeamento Forms - Faltando obrigatórios',
                resultado_mapeamento['faltando_obrigatorios'],
            )
            logger.info(
                f"[MAPEAMENTO] Campos obrigatórios não encontrados: {', '.join(resultado_mapeamento['faltando_obrigatorios'])}"
            )

        return dados_extraidos

    def _sincronizar_pergunta_extraida(
        self,
        dados_extraidos: dict,
        pergunta: str,
        resposta: str | None = None,
        opcoes: list | None = None,
        marcadas: list | None = None,
    ) -> None:
        """Atualiza `perguntas_forms` com dados mais completos obtidos em outras etapas."""
        if not pergunta:
            return

        pergunta_limpa = self.limpar_texto(pergunta)
        pergunta_norm = re.sub(r'^\s*\d+[\.)-]?\s*', '', pergunta_limpa).strip().lower()
        perguntas = dados_extraidos.setdefault('perguntas_forms', [])

        for item in perguntas:
            pergunta_item = self.limpar_texto(item.get('pergunta') or '')
            item_norm = re.sub(r'^\s*\d+[\.)-]?\s*', '', pergunta_item).strip().lower()
            if pergunta_limpa == pergunta_item or (pergunta_norm and pergunta_norm == item_norm):
                if resposta and (not item.get('resposta') or len(str(resposta)) > len(str(item.get('resposta') or ''))):
                    item['resposta'] = resposta
                    item['resposta_texto'] = resposta
                if opcoes:
                    atuais = item.get('opcoes') or []
                    if len(opcoes) > len(atuais):
                        item['opcoes'] = opcoes
                if marcadas:
                    atuais = item.get('marcadas') or []
                    if len(marcadas) > len(atuais):
                        item['marcadas'] = marcadas
                        if not item.get('resposta'):
                            item['resposta'] = ', '.join(marcadas)

                # Tenta recuperar resposta real quando é eco do título
                resp_atual = str(item.get('resposta') or '').strip()
                resp_norm = re.sub(r'^\s*\d+[\.)-]?\s*', '', resp_atual).strip().lower()
                if resp_atual and (resp_norm == pergunta_norm or resp_norm == item_norm):
                    texto_completo = item.get('texto_completo') or ''
                    valor_real = self._extrair_valor_de_texto_completo(texto_completo, item_norm)
                    if valor_real and valor_real.lower() != pergunta_norm:
                        item['resposta'] = valor_real
                        item['resposta_texto'] = valor_real
                return

        perguntas.append(
            {
                'pergunta': pergunta_limpa,
                'resposta': resposta or '',
                'resposta_texto': resposta or '',
                'opcoes': opcoes or [],
                'marcadas': marcadas or [],
                'texto_completo': pergunta_limpa,
            }
        )

    # Metadados que o Forms injeta — usados para limpar texto_completo
    _RE_METADATA_FORMS = re.compile(
        r'\s*\.?\s*(?:Requer resposta\.?\s*)?'
        r'(?:Opção única|Múltipla escolha|Texto de linha única'
        r'|Texto multilinha|Data|Número|Classificação por estrelas'
        r'|Escala de Likert|Imagem)\.?\s*',
        re.IGNORECASE,
    )

    @staticmethod
    def _extrair_valor_de_texto_completo(texto_completo: str, titulo_norm: str) -> str:
        """Extrai o valor da resposta do texto_completo, removendo o título e metadados."""
        if not texto_completo:
            return ''
        s = re.sub(r'^\s*\d+[\.)-]?\s*', '', texto_completo).strip()
        titulo_re = re.escape(titulo_norm)
        s = re.sub(r'(?i)^' + titulo_re + r'\s*', '', s).strip()
        s = FormsExtractor._RE_METADATA_FORMS.sub(' ', s).strip()
        if re.search(r'nenhuma resposta', s, re.IGNORECASE):
            return ''
        return s

    async def _extrair_todas_perguntas_forms(self) -> list[dict]:
        """Extrai todas as perguntas visíveis do Forms usando API nativa do Playwright."""
        if not self._page:
            return []

        page = self._page
        resultado = []

        try:
            container_selectors = [
                '[data-automation-id="questionContent"]',
                '[data-automation-id="QuestionItem"]',
            ]
            containers = None
            for sel in container_selectors:
                containers = page.locator(sel)
                count = await containers.count()
                if count > 0:
                    break

            if not containers or await containers.count() == 0:
                logger.warning("[FORMS-PW] Nenhum container de pergunta encontrado")
                return []

            total = await containers.count()
            logger.info(f"[FORMS-PW] Encontrados {total} containers de perguntas")

            for i in range(total):
                container = containers.nth(i)
                try:
                    item = await self._extrair_pergunta_playwright(container, i + 1)
                    if item and (item.get('pergunta') or item.get('resposta_texto') or item.get('marcadas')):
                        resultado.append(item)
                except Exception as e:
                    logger.debug(f"[FORMS-PW] Erro no container {i+1}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"[FORMS-PW] Erro geral na extração: {e}")

        return resultado

    async def _extrair_pergunta_playwright(self, container, indice: int) -> dict:
        """Extrai dados de uma pergunta individual usando Playwright locators."""
        page = self._page

        # --- TITULO ---
        titulo = ''
        title_selectors = [
            '[data-automation-id="questionTitle"]',
            '[data-automation-id="QuestionText"]',
            '[data-automation-id="QuestionTitle"]',
            '[role="heading"]',
        ]
        for sel in title_selectors:
            loc = container.locator(sel).first
            if await loc.count() > 0:
                titulo = (await loc.inner_text()).replace('\n', ' ').strip()
                if titulo:
                    break

        # Subtítulo/descrição da pergunta
        subtitulo = ''
        sub_selectors = [
            '[data-automation-id="questionSubtitle"]',
            '[data-automation-id="questionDescription"]',
        ]
        for sel in sub_selectors:
            loc = container.locator(sel).first
            if await loc.count() > 0:
                subtitulo = (await loc.inner_text()).replace('\n', ' ').strip()
                if subtitulo:
                    break

        # --- RESPOSTA DE TEXTO (inputs, textareas, datas) ---
        resposta_texto = ''

        # 1. input_value() em inputs de texto/data/número
        input_selectors = [
            'input[type="text"]',
            'input[type="date"]',
            'input[type="number"]',
            'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])',
        ]
        for sel in input_selectors:
            inputs = container.locator(sel)
            count = await inputs.count()
            for j in range(count):
                try:
                    val = await inputs.nth(j).input_value()
                    val = val.strip() if val else ''
                    if val and len(val) >= 1:
                        titulo_limpo = re.sub(r'^\s*\d+[\.)\-]?\s*', '', titulo).strip().lower()
                        titulo_limpo = re.sub(r'\s*requer resposta.*$', '', titulo_limpo, flags=re.IGNORECASE).strip()
                        if val.strip().lower() != titulo_limpo:
                            resposta_texto = val
                            break
                except Exception:
                    continue
            if resposta_texto:
                break

        # 2. textarea
        if not resposta_texto:
            textareas = container.locator('textarea')
            count = await textareas.count()
            for j in range(count):
                try:
                    val = await textareas.nth(j).input_value()
                    val = val.strip() if val else ''
                    if val:
                        resposta_texto = val
                        break
                except Exception:
                    continue

        # 3. [role="textbox"]
        if not resposta_texto:
            tboxes = container.locator('[role="textbox"]')
            count = await tboxes.count()
            for j in range(count):
                try:
                    val = (await tboxes.nth(j).inner_text()).strip()
                    if val:
                        resposta_texto = val
                        break
                except Exception:
                    continue

        # 4. data-automation-id específicos para respostas
        if not resposta_texto:
            answer_selectors = [
                '[data-automation-id="AnswerText"]',
                '[data-automation-id="textField"]',
                '[data-automation-id="dateField"]',
                '[data-automation-id="dateInput"]',
                '[data-automation-id="numberField"]',
                '[data-automation-id="responseSummaryText"]',
                '[data-automation-id="ChoiceSummary"]',
            ]
            titulo_limpo_ans = re.sub(r'^\s*\d+[\.)\-]?\s*', '', titulo).strip().lower()
            titulo_limpo_ans = re.sub(r'\s*requer resposta.*$', '', titulo_limpo_ans, flags=re.IGNORECASE).strip()
            titulo_limpo_ans = re.sub(r'\s*texto (de linha única|multilinha|longo)\.?\s*$', '', titulo_limpo_ans, flags=re.IGNORECASE).strip()
            sub_lower_ans = subtitulo.strip().lower() if subtitulo else ''
            for sel in answer_selectors:
                loc = container.locator(sel).first
                if await loc.count() > 0:
                    try:
                        tag = await loc.evaluate('el => el.tagName.toLowerCase()')
                        if tag in ('input', 'textarea', 'select'):
                            val = await loc.input_value()
                        else:
                            val = await loc.inner_text()
                        val = val.strip() if val else ''
                        if val:
                            val_lower = val.strip().lower()
                            # Remove subtítulo se aparecer como prefixo do valor
                            if sub_lower_ans and val_lower.startswith(sub_lower_ans):
                                val = val[len(subtitulo):].strip()
                                val_lower = val.lower() if val else ''
                            if val and val_lower != titulo_limpo_ans and val_lower != sub_lower_ans:
                                resposta_texto = val
                                break
                    except Exception:
                        continue

        # --- OPÇÕES e MARCADAS (checkboxes/radios) ---
        opcoes = []
        marcadas = []
        seen_opcoes = set()
        seen_marcadas = set()

        option_selectors = [
            '[data-automation-id="questionChoiceOptionContainer"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="option"]',
        ]

        for sel in option_selectors:
            items = container.locator(sel)
            count = await items.count()
            for j in range(count):
                item = items.nth(j)
                try:
                    aria_label = await item.get_attribute('aria-label') or ''
                    if not aria_label:
                        span = item.locator('.text-format-content, [class*="text-format"], span').first
                        if await span.count() > 0:
                            aria_label = (await span.inner_text()).strip()
                    if not aria_label:
                        text = (await item.inner_text()).strip()
                        aria_label = text.split('\n')[0].strip() if text else ''

                    if not aria_label or len(aria_label) < 2 or len(aria_label) > 200:
                        continue

                    key = aria_label.strip().lower()
                    if key not in seen_opcoes:
                        seen_opcoes.add(key)
                        opcoes.append(aria_label.strip())

                    is_checked = False

                    aria_val = await item.get_attribute('aria-checked')
                    if aria_val == 'true':
                        is_checked = True

                    if not is_checked:
                        aria_sel = await item.get_attribute('aria-selected')
                        if aria_sel == 'true':
                            is_checked = True

                    if not is_checked:
                        child = item.locator('[aria-checked="true"]')
                        if await child.count() > 0:
                            is_checked = True

                    if not is_checked:
                        checked_inp = item.locator('input:checked')
                        if await checked_inp.count() > 0:
                            is_checked = True

                    if not is_checked:
                        try:
                            parent_checked = await item.evaluate(
                                'el => el.parentElement?.getAttribute("aria-checked") === "true"'
                            )
                            if parent_checked:
                                is_checked = True
                        except Exception:
                            pass

                    if is_checked and key not in seen_marcadas:
                        seen_marcadas.add(key)
                        marcadas.append(aria_label.strip())

                except Exception:
                    continue

        # inputs nativos checkbox/radio
        native_inputs = container.locator('input[type="checkbox"], input[type="radio"]')
        native_count = await native_inputs.count()
        for j in range(native_count):
            inp = native_inputs.nth(j)
            try:
                is_checked = await inp.is_checked()
                if is_checked:
                    inp_id = await inp.get_attribute('id') or ''
                    label_text = ''
                    if inp_id:
                        lbl = self._page.locator(f'label[for="{inp_id}"]').first
                        if await lbl.count() > 0:
                            label_text = (await lbl.inner_text()).strip()
                    if not label_text:
                        parent = inp.locator('..')
                        if await parent.count() > 0:
                            label_text = (await parent.inner_text()).strip()
                            label_text = label_text.split('\n')[0].strip()
                    if label_text and len(label_text) >= 2:
                        key = label_text.lower()
                        if key not in seen_marcadas:
                            seen_marcadas.add(key)
                            marcadas.append(label_text)
                        if key not in seen_opcoes:
                            seen_opcoes.add(key)
                            opcoes.append(label_text)
            except Exception:
                continue

        if not resposta_texto and marcadas:
            resposta_texto = ', '.join(marcadas)

        # --- TEXTO COMPLETO (fallback) ---
        texto_completo = ''
        try:
            texto_completo = (await container.inner_text()).replace('\n', ' ').strip()
            texto_completo = re.sub(r'\s+', ' ', texto_completo)
        except Exception:
            pass

        resposta = resposta_texto or (', '.join(marcadas) if marcadas else '') or texto_completo

        return {
            'indice': indice,
            'pergunta': titulo,
            'resposta': resposta,
            'resposta_texto': resposta_texto,
            'opcoes': opcoes,
            'marcadas': marcadas,
            'texto_completo': texto_completo,
            'html_resumo': texto_completo[:1000],
        }

    # -------------------------------------------------------------------
    # Navegador persistente: mantém Forms aberto entre extrações
    # -------------------------------------------------------------------

    async def _garantir_forms_aberto(self, forms_url: str, timeout: int = 60000) -> bool:
        """Garante que o navegador está aberto com o Forms em 'Verificar resultados individuais'.

        Se já estiver aberto e pronto, retorna True imediatamente.
        Caso contrário, abre o navegador, navega até o Forms e clica em
        'Verificar resultados individuais'.
        """
        # --- Tenta reutilizar página existente ---
        if self._forms_aberto and self._page:
            try:
                _title = await self._page.title()
                logger.info("[FORMS] Página já está aberta, reutilizando...")
                return True
            except Exception:
                logger.warning("[FORMS] Página anterior não responde, reabrindo...")
                self._forms_aberto = False

        # --- Lança Playwright se necessário ---
        if not self._playwright:
            self._playwright = await async_playwright().__aenter__()

        async def _launch_browser():
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
            )

        async def _reset_playwright_and_launch():
            """Reseta o Playwright por completo e relança o browser."""
            logger.warning("[FORMS] Playwright stale. Resetando por completo...")
            try:
                if self._browser:
                    await self._browser.close()
            except Exception:
                pass
            try:
                if self._playwright:
                    await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass
            self._browser = None
            self._playwright = None
            self._playwright = await async_playwright().__aenter__()
            await _launch_browser()

        if not self._browser or not self._browser.is_connected():
            try:
                await _launch_browser()
            except (AttributeError, Exception) as e:
                logger.warning(f"[FORMS] Falha ao lançar browser ({e}). Resetando Playwright...")
                await _reset_playwright_and_launch()

        # --- Cria contexto e página ---
        context_options = {"viewport": {"width": 1400, "height": 900}}
        if os.path.exists(self.state_file):
            context_options["storage_state"] = self.state_file
            logger.info("💾 Carregando sessão salva")

        try:
            self._context = await self._browser.new_context(**context_options)
        except (AttributeError, Exception) as e:
            # Conexão interna do browser morreu: relança
            logger.warning(f"[FORMS] Browser com conexão morta ({e}). Relançando...")
            await _reset_playwright_and_launch()
            self._context = await self._browser.new_context(**context_options)

        self._page = await self._context.new_page()
        page = self._page

        # --- Ajusta URL se vier da página de Design/Analysis ---
        if "DesignPage" in forms_url or "Analysis=true" in forms_url:
            logger.info("[AJUSTE] Link de Design detectado, convertendo para Respostas...")
            form_id_match = re.search(r'FormId=([^&]+)', forms_url)
            if form_id_match:
                form_id = form_id_match.group(1)
                forms_url = (
                    f"https://forms.office.com/pages/designpagev2.aspx?"
                    f"analysis=true&origin=EmailNotification&subpage=design&id={form_id}"
                )
                logger.info(f"[AJUSTE] Nova URL: {forms_url}")

        self._forms_url_base = forms_url

        # --- Acessa o Forms (com retries) ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"[WEB] Acessando Forms (Tentativa {attempt+1}/{max_retries}): {forms_url}")
                await page.goto(forms_url, wait_until="domcontentloaded", timeout=timeout)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"[ERRO] Falha ao acessar Forms após {max_retries} tentativas.")
                    raise e
                logger.warning(f"[AVISO] Erro ao acessar Forms (Tentativa {attempt+1}): {e}")
                await asyncio.sleep(3)

        # --- Aguarda conteúdo dinâmico ---
        logger.info("[WEB] Aguardando conteúdo do Forms carregar...")
        try:
            await page.wait_for_selector(
                '[data-automation-id="questionTitle"], [data-automation-id="QuestionItem"], '
                '.office-form-question, input[aria-label="Entrevistado"]',
                timeout=15000
            )
            logger.info("[WEB] ✓ Conteúdo do Forms detectado")
        except Exception:
            logger.warning("[WEB] Timeout esperando elementos do Forms, continuando...")
        await asyncio.sleep(2)

        # --- Login se necessário ---
        current_url = page.url
        page_title = await page.title()
        precisa_login = (
            "login.microsoftonline.com" in current_url or
            "login.live.com" in current_url or
            "Sign in" in page_title or
            "Entrar" in page_title
        )

        if precisa_login:
            logger.warning("[LOGIN] Login necessario no Microsoft!")
            logger.info("[AGUARDE] Faca login na janela do navegador que abriu...")
            print("\n" + "="*60)
            print("[IMPORTANTE] FACA LOGIN NO NAVEGADOR QUE ABRIU!")
            print("="*60)

            for i in range(60):
                await asyncio.sleep(5)
                current_url = page.url
                if "forms.office.com" in current_url and "login" not in current_url.lower():
                    logger.info("[OK] Login realizado com sucesso!")
                    await asyncio.sleep(3)
                    await self._context.storage_state(path=self.state_file)
                    logger.info("[SALVO] Sessao salva para proximas execucoes!")
                    break
                if i % 6 == 0:
                    tempo_restante = 5 - (i // 12)
                    logger.info(f"[AGUARDANDO] Login... ({tempo_restante} minutos restantes)")
            else:
                logger.error("[ERRO] Timeout aguardando login (5 minutos)")
                return False

        await asyncio.sleep(3)

        # --- Detectar página de Design → clicar aba Respostas ---
        try:
            current_url = page.url
            if "DesignPage" in current_url or await page.locator("text=Respostas").count() > 0:
                logger.info("[DETECTADO] Página de DESIGN/EDIÇÃO identificada.")
                response_tab_selectors = [
                    "div[role='tab']:has-text('Respostas')",
                    "div[role='tab']:has-text('Responses')",
                    "button[role='tab']:has-text('Respostas')",
                    ".office-form-pivot-item:has-text('Respostas')"
                ]
                for sel in response_tab_selectors:
                    if await page.locator(sel).count() > 0:
                        await page.click(sel)
                        logger.info(f"[OK] Clicou na aba 'Respostas' ({sel})")
                        await asyncio.sleep(3)
                        break
        except Exception as e:
            logger.warning(f"[NAVEGACAO] Erro ao mudar para aba Respostas: {e}")

        # --- Clicar em "Verificar resultados individuais" ---
        try:
            if await page.locator('input[aria-label="Entrevistado"]').count() > 0:
                logger.info("[NAVEGACAO] Campo de entrevistado já disponível.")
            else:
                logger.info("[NAVEGACAO] Procurando botao 'Verificar resultados individuais'...")
                selectors_botao = [
                    "text=Verificar resultados individuais",
                    "text=View individual results",
                    "button:has-text('Revisar respostas')",
                    "text=Revisar respostas",
                    "button:has-text('Ver resultados')",
                    "text=Ver resultados",
                    "[aria-label*='resultado']",
                    "[aria-label*='result']",
                    "div:has-text('Verificar resultados individuais')",
                ]
                for selector in selectors_botao:
                    try:
                        if await page.locator(selector).count() > 0:
                            await page.locator(selector).first.click(timeout=3000)
                            logger.info(f"[OK] Clicou em 'Verificar resultados individuais' ({selector})")
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue
                else:
                    try:
                        botao = await page.wait_for_selector(
                            "text=Verificar resultados individuais", timeout=7000
                        )
                        if botao:
                            await botao.click()
                            await asyncio.sleep(3)
                    except Exception:
                        logger.warning("[AVISO] Botao 'Verificar resultados individuais' nao encontrado")
        except Exception as e:
            logger.warning(f"[AVISO] Erro ao navegar para resultados individuais: {e}")

        self._forms_aberto = True
        logger.info("[FORMS] ✅ Forms aberto em 'Verificar resultados individuais'")
        return True

    async def _avancar_resposta(self) -> bool:
        """Clica na seta para frente (próxima resposta).

        Returns:
            True se avançou para a próxima resposta.
            False se já está na última (seta desabilitada/ausente).
        """
        if not self._page:
            return False

        page = self._page

        # Captura o número da resposta atual antes de avançar
        numero_antes = await self._obter_numero_resposta_atual()

        # Seletores para o botão "próxima resposta" (seta direita ›)
        seletores_proximo = [
            'button[aria-label*="próxim" i]',
            'button[aria-label*="Próxim" i]',
            'button[aria-label*="next" i]',
            'button[aria-label*="Next" i]',
            'button[aria-label*="Avançar" i]',
            'button[aria-label*="avanc" i]',
            'button[aria-label*="Seguinte" i]',
        ]

        btn_proximo = None
        for sel in seletores_proximo:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    btn_proximo = loc.first
                    break
            except Exception:
                continue

        # Fallback: procura o botão pela posição relativa ao campo "Entrevistado"
        if not btn_proximo:
            try:
                btn_proximo_el = await page.evaluate("""
                    () => {
                        const input = document.querySelector('input[aria-label="Entrevistado"]');
                        if (!input) return null;
                        const container = input.closest('[role="group"]') || input.parentElement?.parentElement;
                        if (!container) return null;

                        // Procura botões com SVG de seta direita no mesmo container
                        const buttons = container.querySelectorAll('button');
                        // O botão "próximo" geralmente é o último botão do grupo
                        for (const btn of Array.from(buttons).reverse()) {
                            const svg = btn.querySelector('svg');
                            if (svg) {
                                const path = svg.querySelector('path');
                                if (path) {
                                    const d = path.getAttribute('d') || '';
                                    // Seta direita: o path começa com valores que vão para a direita
                                    if (d.includes('1022') || d.includes('1955') || d.includes('515')) {
                                        btn.setAttribute('data-forms-next', 'true');
                                        return true;
                                    }
                                }
                            }
                        }
                        return null;
                    }
                """)
                if btn_proximo_el:
                    btn_proximo = page.locator('button[data-forms-next="true"]')
            except Exception:
                pass

        if not btn_proximo:
            logger.warning("[NAV] Botão 'próxima resposta' não encontrado")
            return False

        # Verifica se o botão está desabilitado (última resposta)
        try:
            is_disabled = await btn_proximo.get_attribute('disabled')
            if is_disabled is not None:
                logger.info("[NAV] ⏹ Seta 'próximo' está desabilitada — última resposta alcançada")
                return False

            aria_disabled = await btn_proximo.get_attribute('aria-disabled')
            if aria_disabled == 'true':
                logger.info("[NAV] ⏹ Seta 'próximo' está aria-disabled — última resposta alcançada")
                return False
        except Exception:
            pass

        # Clica no botão
        try:
            await btn_proximo.click(timeout=3000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"[NAV] Erro ao clicar seta próximo: {e}")
            return False

        # Verifica se realmente avançou
        numero_depois = await self._obter_numero_resposta_atual()
        if numero_antes is not None and numero_depois is not None:
            if numero_depois > numero_antes:
                logger.info(f"[NAV] ✅ Avançou: resposta #{numero_antes} → #{numero_depois}")
                return True
            else:
                logger.info(f"[NAV] ⏹ Não avançou (#{numero_antes} → #{numero_depois}) — última resposta")
                return False

        # Se não conseguiu ler o número, assume que avançou (o clique foi bem-sucedido)
        logger.info("[NAV] ➡ Seta clicada (não foi possível confirmar número)")
        return True

    async def _obter_numero_resposta_atual(self) -> int | None:
        """Lê o número da resposta atual do campo 'Entrevistado'."""
        if not self._page:
            return None
        try:
            campo = await self._page.wait_for_selector(
                'input[aria-label="Entrevistado"]', timeout=3000
            )
            if campo:
                valor = await campo.get_attribute('value')
                return int(str(valor).strip()) if valor else None
        except Exception:
            return None

    async def _navegar_para_resposta(self, numero: int) -> bool:
        """Digita um número no campo 'Entrevistado' para pular direto a essa resposta.

        Args:
            numero: Número da resposta para navegar.

        Returns:
            True se navegou com sucesso.
        """
        if not self._page:
            return False
        page = self._page
        try:
            campo = await page.wait_for_selector(
                'input[aria-label="Entrevistado"]', timeout=5000
            )
            if not campo:
                logger.warning("[NAV] Campo 'Entrevistado' não encontrado")
                return False

            await campo.click()
            await campo.fill('')
            await asyncio.sleep(0.3)
            await campo.fill(str(numero))
            await asyncio.sleep(0.3)
            await page.keyboard.press('Enter')
            await asyncio.sleep(3)

            numero_atual = await self._obter_numero_resposta_atual()
            logger.info(f"[NAV] ✅ Navegou direto para resposta #{numero_atual}")
            return True
        except Exception as e:
            logger.warning(f"[NAV] Erro ao navegar para resposta #{numero}: {e}")
            return False

    async def _ir_para_ultima_resposta(self) -> int | None:
        """Pula para o último número conhecido (contador) e avança com a seta até a última resposta.

        Fluxo:
        1. Lê o último número do arquivo de contador (ex: 659)
        2. Digita esse número no campo 'Entrevistado' para pular direto
        3. Avança com a seta ➡ até não conseguir mais (última resposta)
        4. Salva o número da última resposta no contador

        Retorna o número da última resposta, ou None se não conseguir determinar.
        """
        # Passo 1: Pula direto para o último número conhecido
        ultimo_salvo = self.ler_ultimo_numero()
        logger.info(f"[NAV] 🔄 Pulando para resposta #{ultimo_salvo} (último processado)...")
        await self._navegar_para_resposta(ultimo_salvo)

        # Passo 2: Avança com a seta até a última resposta
        logger.info("[NAV] ➡ Avançando com seta até a última resposta...")
        avancos = 0
        while True:
            avancou = await self._avancar_resposta()
            if not avancou:
                break
            avancos += 1
            # Safety: limite para evitar loop infinito
            if avancos > 5000:
                logger.warning("[NAV] ⚠ Limite de 5000 avanços atingido, parando")
                break

        numero = await self._obter_numero_resposta_atual()

        # Passo 3: Salva o número atual para a próxima execução
        if numero is not None:
            self.salvar_proximo_numero(numero)

        if avancos > 0:
            logger.info(f"[NAV] ✅ Chegou na última resposta (#{numero}) após {avancos} avanço(s) a partir de #{ultimo_salvo}")
        else:
            logger.info(f"[NAV] ℹ Já estava na última resposta (#{numero})")
        return numero

    async def fechar_forms(self):
        """Fecha o navegador persistente e libera recursos."""
        self._forms_aberto = False
        try:
            if self._context:
                try:
                    await self._context.storage_state(path=self.state_file)
                except Exception:
                    pass
            if self._browser and self._browser.is_connected():
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        logger.info("[FORMS] Navegador fechado")

    def ler_ultimo_numero(self):
        """
        Lê o último número de resposta processado do arquivo

        Returns:
            int: Último número processado (639 por padrão se arquivo não existir)
        """
        import os
        if os.path.exists(self.counter_file):
            try:
                with open(self.counter_file, 'r', encoding='utf-8') as f:
                    numero = int(f.read().strip())
                    logger.info(f"[COUNTER] Ultimo numero processado: {numero}")
                    return numero
            except Exception as e:
                logger.warning(f"[COUNTER] Erro ao ler arquivo de contador: {e}")

        logger.info("[COUNTER] Arquivo de contador nao encontrado, iniciando em 639")
        return 639

    def salvar_proximo_numero(self, numero_atual):
        """
        Salva o próximo número a ser processado no arquivo

        Args:
            numero_atual: Número que acabou de ser processado
        """
        proximo = numero_atual + 1
        try:
            with open(self.counter_file, 'w', encoding='utf-8') as f:
                f.write(str(proximo))
            logger.info(f"[COUNTER] Proximo numero salvo: {proximo}")
        except Exception as e:
            logger.error(f"[COUNTER] Erro ao salvar contador: {e}")

    def limpar_texto(self, texto):
        """Remove caracteres especiais e normaliza texto"""
        if not texto:
            return ""
        texto = texto.strip()
        texto = re.sub(r'\s+', ' ', texto)  # Remove espaços múltiplos
        return texto

    def _processar_texto_completo(self, texto_completo, dados_extraidos):
        """Reaproveita a lógica de parsing em um helper reutilizável"""
        if not texto_completo:
            return dados_extraidos

        if VERBOSE_FORMS_LOGS:
            logger.info(f"[INFO] Texto extraido: {len(texto_completo)} caracteres")

        # Salva texto completo para debug
        if VERBOSE_FORMS_LOGS:
            try:
                with open("forms_texto_debug_detalhado.txt", "w", encoding="utf-8") as f:
                    f.write(texto_completo)
                logger.info("[DEBUG] Texto detalhado salvo em: forms_texto_debug_detalhado.txt")
            except Exception:
                pass

        # --- NOVA LÓGICA DE EXTRAÇÃO ---
        # Análise linha por linha para capturar perguntas e respostas
        
        linhas = texto_completo.splitlines()
        
        # Remover linhas vazias
        linhas = [linha.strip() for linha in linhas if linha.strip()]
        
        pergunta_atual = None
        coletando_resposta = False
        respostas_coletadas = []
        questao_atual = None
        
        # Termos que indicam que a linha é metadado, não resposta
        termos_metadado = [
            'requer resposta', 'obrigatória', 'opção única',
            'texto de linha única', 'texto multilinha', 'múltipla escolha',
            'data.', 'carregar arquivo', 'assinalar "sim" sempre que se tratar',
            'caso haja, gentileza especificar', 'previsão e resultado do processo',
            'data da publicação', 'distribuição da ação', 'máximo de',
            'leitura avançada', 'immersive reader', 'voltar', 'exibir resultados',
            'entrevistado', 'tempo para concluir', 'forms', 'salvo', 'ps'
        ]
        
        # Mapeamento de perguntas para campos específicos
        # ATUALIZADO: Inclui campos 16, 17, 18, 23, 24, 25 do formulário
        mapeamento_campos = {
            'Tipo de cadastro': 'tipo_cadastro',
            'Número CNJ': 'cnj',
            'Cliente principal': 'cliente',
            'Contrato de honorários': 'contrato_honorarios',
            'Incluir no relatório do LegalOne de horas trabalhadas?': 'incluir_relatorio',
            'Contrário principal': 'contrario',
            'Função exercida pelo RCTE': 'funcao_rcte',
            'Outros envolvidos e posição nos autos': 'outros_envolvidos',
            'Advogado responsável': 'advogado',
            'Vínculo (se houver - processo ou serviço)': 'vinculo',
            'Tipo de vínculo': 'tipo_vinculo',
            'Procedimento': 'procedimento',
            'Instância': 'instancia',
            'Fase': 'fase',
            # Campo 16 - Cidade/Comarca (texto)
            'Cidade/Comarca': 'cidade_comarca',
            # Campo 17 - Valor da causa (texto)
            'Valor da causa': 'valor_causa',
            # Campo 18 - Objetos (radio: Contrato de trabalho / Outra)
            'Objetos': 'objetos',
            # Campo 23 - Pedido de vínculo trabalhista (radio: Não / Outra)
            'Há pedido de vínculo trabalhista?': 'vinculo_trabalhista',
            # Campo 24 - Descrição dos pedidos (textarea)
            'Descreva todos os pedidos com as respectivas informações: pedido, valor, probabilidade atual (êxito ou perda - possível, provável, remota)': 'descricao_pedidos',
            # Variações do campo 24 (o texto pode vir truncado)
            'Descreva todos os pedidos com as respectivas informações': 'descricao_pedidos',
            'Descreva todos os pedidos': 'descricao_pedidos',
            # Campo 25 - Contingência (radio: Ativa / Passiva)
            'Contingência': 'contingencia',
            'Data dos pedidos': 'data_distribuicao',
            'Data do julgamento': 'data_julgamento',
            'Pedidos': 'pedidos',
            'Probabilidade atual': 'probabilidade',
            'Grau de probabilidade atual': 'grau_probabilidade',
            'Risco': 'risco',
            'Data da citação': 'data_citacao',
            'Responsabilidade': 'responsabilidade',
            'Redirecionamento da execução': 'redirecionamento'
        }
        
        # Mapeamento adicional para variações de perguntas (busca parcial)
        mapeamento_parcial = {
            'cidade/comarca': 'cidade_comarca',
            'valor da causa': 'valor_causa',
            'objetos': 'objetos',
            'pedido de vínculo trabalhista': 'vinculo_trabalhista',
            'vínculo trabalhista': 'vinculo_trabalhista',
            'descreva todos os pedidos': 'descricao_pedidos',
            'contingência': 'contingencia',
        }
        
        if VERBOSE_FORMS_LOGS:
            logger.info("\n🔍 ANALISANDO TODAS AS PERGUNTAS E RESPOSTAS:")
            logger.info("=" * 60)
        
        i = 0
        while i < len(linhas):
            linha = linhas[i]
            
            # Verifica se é uma nova pergunta numerada
            # Formato 1: "1. Pergunta" (tudo na mesma linha)
            match_pergunta = re.match(r'^(\d+)\.\s*(.+)$', linha)
            if match_pergunta and match_pergunta.group(2).strip():
                numero_pergunta = int(match_pergunta.group(1))
                texto_pergunta = match_pergunta.group(2).strip()
                
                # Validação: número de pergunta deve ser razoável (1-100)
                # e o texto não deve parecer um valor monetário
                eh_valor_monetario = bool(re.match(r'^[\d.,]+$', texto_pergunta))
                eh_numero_valido = 1 <= numero_pergunta <= 100
                
                if eh_numero_valido and not eh_valor_monetario:
                    # Se havia uma pergunta anterior, processa as respostas coletadas
                    if pergunta_atual and respostas_coletadas:
                        self._processar_respostas_pergunta(pergunta_atual, respostas_coletadas, dados_extraidos, mapeamento_campos)
                    
                    # Inicia nova pergunta
                    questao_atual = match_pergunta.group(1)
                    pergunta_atual = texto_pergunta
                    coletando_resposta = False
                    respostas_coletadas = []
                
                if VERBOSE_FORMS_LOGS:
                    logger.info(f"\n[{questao_atual}] {pergunta_atual}")
                i += 1
                continue
            
            # Formato 2: "1." em uma linha, "Pergunta" na próxima
            match_numero = re.match(r'^(\d+)\.$', linha)
            if match_numero and i + 1 < len(linhas):
                # Se havia uma pergunta anterior, processa as respostas coletadas
                if pergunta_atual and respostas_coletadas:
                    self._processar_respostas_pergunta(pergunta_atual, respostas_coletadas, dados_extraidos, mapeamento_campos)
                
                # Inicia nova pergunta (pega o texto da próxima linha)
                questao_atual = match_numero.group(1)
                pergunta_atual = linhas[i + 1].strip()
                coletando_resposta = False
                respostas_coletadas = []
                
                if VERBOSE_FORMS_LOGS:
                    logger.info(f"\n[{questao_atual}] {pergunta_atual}")
                i += 2  # Pula a linha do número E a linha da pergunta
                continue
            
            i += 1
            
            # Se temos uma pergunta atual, começa a coletar respostas
            if pergunta_atual and not coletando_resposta:
                # Pula metadados da pergunta
                eh_metadado = any(termo in linha.lower() for termo in termos_metadado)
                if eh_metadado:
                    logger.debug(f"   [METADADO] {linha}")
                    continue
                
                # Esta é a primeira resposta
                coletando_resposta = True
            
            # Coletando respostas para a pergunta atual
            if coletando_resposta and pergunta_atual:
                # Para perguntas de múltipla escolha, continua coletando até encontrar próxima pergunta ou fim
                respostas_coletadas.append(linha)
                logger.debug(f"   [RESPOSTA] {linha}")
        
        # Processa a última pergunta se houver
        if pergunta_atual and respostas_coletadas:
            self._processar_respostas_pergunta(pergunta_atual, respostas_coletadas, dados_extraidos, mapeamento_campos)
        
        if VERBOSE_FORMS_LOGS:
            logger.info("\n" + "=" * 80)
            logger.info("📊 RESUMO DOS DADOS EXTRAÍDOS:")
            logger.info("=" * 80)
        
        # Log dos campos mapeados (incluindo novos campos 16, 17, 18, 22, 23, 24, 25)
        campos_mapeados = ['cnj', 'tipo_cadastro', 'fase', 'instancia', 'cliente', 'contrario', 
                           'advogado', 'cidade_comarca', 'valor_causa', 'procedimento', 'data_distribuicao',
                           'probabilidade', 'grau_probabilidade', 'risco', 'contingencia',
                           'objetos', 'pedidos', 'vinculo_trabalhista', 'descricao_pedidos']
        
        if VERBOSE_FORMS_LOGS:
            for campo in campos_mapeados:
                valor = dados_extraidos.get(campo)
                if valor:
                    logger.info(f"{campo.upper()}: {valor}")
        elif dados_extraidos.get('pedidos'):
            logger.info(f"[PEDIDOS] {dados_extraidos['pedidos']}")
        
        # Log de outros dados
        if VERBOSE_FORMS_LOGS:
            outros = dados_extraidos.get('outros_dados', {})
            if outros:
                logger.info("-" * 40)
                logger.info("📋 OUTROS DADOS:")
                for pergunta, resposta in outros.items():
                    if pergunta not in mapeamento_campos:  # Evita duplicação
                        logger.info(f"   • {pergunta}: {resposta}")
            
            logger.info("=" * 80)
        
        return dados_extraidos

    def _processar_respostas_pergunta(self, pergunta, respostas, dados_extraidos, mapeamento_campos):
        """Processa as respostas coletadas para uma pergunta"""
        respostas_validas = []
        
        # IMPORTANTE: Definir pergunta_lower PRIMEIRO antes de qualquer uso
        pergunta_lower = pergunta.lower()

        termos_ignorar = [
            'nenhuma resposta fornecida', 'esta pergunta é obrigatória',
            'opção única', 'texto de linha única', 'múltipla escolha',
            'requer resposta', 'obrigatória'
        ]

        # Perguntas que são de múltipla escolha COMPLEXA (podem ter várias respostas marcadas)
        # NOTA: O campo "Pedidos" (22) é múltipla escolha
        # NOTA: "Descreva todos os pedidos" (24) é TEXTAREA, não múltipla escolha!
        perguntas_multipla_escolha = [
            'outros envolvidos', 'responsabilidade'
        ]
        
        # Campo 22 - Pedidos: é múltipla escolha mas vamos tentar capturar via texto também
        # porque a extração DOM pode falhar
        eh_campo_pedidos = pergunta_lower == 'pedidos' or (pergunta_lower.startswith('pedidos') and len(pergunta_lower) < 15)
        
        # Perguntas de opção única (radio buttons) - processamos normalmente
        perguntas_opcao_unica = [
            'objetos', 'contingência', 'vínculo trabalhista', 'há pedido de vínculo'
        ]
        
        # Perguntas que permitem texto longo (textarea)
        # IMPORTANTE: "Descreva todos os pedidos" é TEXTAREA, não múltipla escolha!
        perguntas_texto_longo = [
            'descreva todos os pedidos', 'descricao_pedidos', 'descrição'
        ]
        
        eh_multipla_escolha = any(termo in pergunta_lower for termo in perguntas_multipla_escolha)
        eh_opcao_unica = any(termo in pergunta_lower for termo in perguntas_opcao_unica)
        eh_texto_longo = any(termo in pergunta_lower for termo in perguntas_texto_longo)
        
        # "Descreva todos os pedidos" NÃO é múltipla escolha, é textarea
        if eh_texto_longo:
            eh_multipla_escolha = False

        # Para múltipla escolha COMPLEXA (exceto Pedidos), deixa extração DOM cuidar
        if eh_multipla_escolha and not eh_opcao_unica and not eh_campo_pedidos:
            if VERBOSE_FORMS_LOGS:
                logger.info(f"   ⏭️ {pergunta}: campo de múltipla escolha - será extraído via DOM")
            return

        # Define limite de caracteres baseado no tipo de campo
        # Para campo Pedidos (22), aumentamos o limite pois pode ter muitas opções
        if eh_campo_pedidos:
            limite_caracteres = 1000
        elif eh_texto_longo:
            limite_caracteres = 500
        else:
            limite_caracteres = 100

        # Lista de opções conhecidas do campo Pedidos para filtrar
        opcoes_pedidos_conhecidas = [
            'acúmulo de função', 'adicional de insalubridade', 'adicional de periculosidade',
            'adicional noturno', 'aviso prévio', 'benefício cct', 'comissões',
            'contribuições previdenciárias', 'correção monetária', 'desvio de função',
            'diferença salarial', 'entrega/retificação/indenização - ppp', 'equiparação salarial',
            'férias + 1/3', 'fgts + 40%', 'honorários advocatícios sucumbenciais',
            'horas bip', 'horas extras', 'ilicitude terceirização',
            'indenização estabilidade acidentária/doença', 'indenização estabilidade cipa',
            'indenização estabilidade gravídica', 'indenização por danos estéticos',
            'indenização por danos materiais', 'indenização por danos morais',
            'intervalo interjornada', 'intervalo intrajornada', 'multa art. 479',
            'multas convencionais', 'multa do artigo 467 da clt', 'multa do artigo 477,  §8º da clt',
            'pensão vitalícia', 'plano de saúde', 'plr', 'salários', 'saldo de salário',
            'vale alimentação', 'vale cultura', 'vale transporte', 'verbas rescisórias',
            'vínculo', 'vínculo - pejotização', '13º salario'
        ]

        for resposta in respostas:
            resposta_limpa = resposta.strip()
            if not resposta_limpa:
                continue

            # Ignora linhas que são metadados ou instruções
            eh_ignorar = any(termo in resposta_limpa.lower() for termo in termos_ignorar)
            if not eh_ignorar:
                # Para campo Pedidos via texto, NÃO podemos confiar porque o texto
                # contém TODAS as opções (marcadas e não marcadas).
                # A extração de pedidos deve ser feita APENAS via DOM (checkboxes)
                if eh_campo_pedidos:
                    # CORREÇÃO: Não processa pedidos via texto - deixa para extração DOM
                    # O texto da página contém todas as opções, não só as marcadas
                    logger.debug(f"   [PEDIDOS] Ignorando extração via texto - será feita via DOM")
                    continue
                elif len(resposta_limpa) < limite_caracteres:
                    respostas_validas.append(resposta_limpa)

        # Determina a resposta final
        resposta_final = None
        if respostas_validas:
            if eh_texto_longo:
                # Para texto longo, junta todas as linhas
                resposta_final = ' '.join(respostas_validas)
            elif eh_campo_pedidos:
                # Campo Pedidos deve ser extraído via DOM, não via texto
                # Se chegou aqui com respostas, algo está errado
                logger.warning(f"   ⚠️ Campo Pedidos não deve ser processado via texto")
                return
            else:
                # Para opção única/curta, pega a última resposta válida
                resposta_final = respostas_validas[-1]

        # Mapeia para campo específico se houver (busca exata)
        campo_encontrado = None
        
        # Tratamento especial para campo Pedidos
        if eh_campo_pedidos:
            campo_encontrado = 'pedidos'
        elif pergunta in mapeamento_campos:
            campo_encontrado = mapeamento_campos[pergunta]
        else:
            # Busca parcial no mapeamento_parcial
            mapeamento_parcial = {
                'cidade/comarca': 'cidade_comarca',
                'valor da causa': 'valor_causa',
                'objetos': 'objetos',
                'pedido de vínculo trabalhista': 'vinculo_trabalhista',
                'vínculo trabalhista': 'vinculo_trabalhista',
                'há pedido de vínculo': 'vinculo_trabalhista',
                'descreva todos os pedidos': 'descricao_pedidos',
                'contingência': 'contingencia',
            }
            for termo, campo in mapeamento_parcial.items():
                if termo in pergunta_lower:
                    campo_encontrado = campo
                    break
        
        if campo_encontrado and resposta_final:
            # Só atualiza se o campo ainda não tem valor
            if not dados_extraidos.get(campo_encontrado):
                dados_extraidos[campo_encontrado] = resposta_final
                logger.info(f"   ✅ {campo_encontrado.upper()}: {resposta_final}")
            else:
                logger.info(f"   ℹ️ {campo_encontrado.upper()}: já preenchido, ignorando duplicata")

        # Sempre armazena nos outros dados para referência completa
        if eh_campo_pedidos and not resposta_final:
            resposta_final = dados_extraidos.get('pedidos')
        dados_extraidos.setdefault('outros_dados', {})[pergunta] = resposta_final if resposta_final else "Nenhuma resposta fornecida"

    def extrair_cnj(self, texto):
        """
        Extrai número CNJ do texto - versão aprimorada
        """
        # Padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
        patterns = [
            r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}',  # Formato padrão
            r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}',  # Com traços e pontos
            r'\d{20}',  # Sem formatação
            r'\d{7}\.\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}',  # Com pontos
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, texto)
            for match in matches:
                cnj = match
                # Normaliza para o formato padrão
                cnj_numeros = re.sub(r'[^0-9]', '', cnj)
                
                if len(cnj_numeros) == 20:
                    cnj_formatado = f"{cnj_numeros[0:7]}-{cnj_numeros[7:9]}.{cnj_numeros[9:13]}.{cnj_numeros[13:14]}.{cnj_numeros[14:16]}.{cnj_numeros[16:20]}"
                    logger.info(f"✅ CNJ encontrado: {cnj_formatado}")
                    return cnj_formatado
        
        # Fallback: procura por padrão mais flexível
        texto_sem_espacos = texto.replace(' ', '')
        cnj_match = re.search(r'(\d{7}[-.]?\d{2}[-.]?\d{4}[-.]?\d[-.]?\d{2}[-.]?\d{4})', texto_sem_espacos)
        if cnj_match:
            cnj = cnj_match.group(1)
            cnj_numeros = re.sub(r'[^0-9]', '', cnj)
            if len(cnj_numeros) == 20:
                cnj_formatado = f"{cnj_numeros[0:7]}-{cnj_numeros[7:9]}.{cnj_numeros[9:13]}.{cnj_numeros[13:14]}.{cnj_numeros[14:16]}.{cnj_numeros[16:20]}"
                logger.info(f"✅ CNJ encontrado (fallback): {cnj_formatado}")
                return cnj_formatado
        
        logger.warning("⚠ Número CNJ não encontrado")
        return None

    async def extrair_dados_forms(self, forms_url, timeout=60000, force_playwright=False):
        """
        Extrai dados da resposta do Microsoft Forms
        Tenta Firecrawl primeiro, depois Playwright como fallback

        Args:
            forms_url: URL da resposta do Forms
            timeout: Tempo máximo de espera em ms
            force_playwright: Se True, pula Firecrawl e usa apenas Playwright

        Returns:
            dict: Dicionário com dados extraídos
        """
        # MÉTODO 1: Firecrawl (rápido e inteligente)
        if self.use_firecrawl and self.firecrawl and not force_playwright:
            logger.info("[METODO 1] Tentando extracao com Firecrawl...")
            try:
                dados_firecrawl = self.firecrawl.extrair_com_llm(forms_url)
                if dados_firecrawl and dados_firecrawl.get('cnj'):
                    logger.info("[SUCESSO] Dados extraidos com Firecrawl!")
                    return dados_firecrawl
                else:
                    logger.warning("[FALLBACK] Firecrawl nao retornou CNJ, tentando Playwright...")
            except Exception as e:
                logger.warning(f"[FALLBACK] Erro no Firecrawl: {e}, tentando Playwright...")

        # MÉTODO 2: Playwright (navegação completa)
        logger.info("[METODO 2] Usando Playwright para extracao...")
        dados_extraidos = {
            'cnj': None,
            'autor': None,
            'reu': None,
            'tribunal': None,
            'vara': None,
            'comarca': None,
            'tipo_acao': None,
            'valor_causa': None,
            'tipo_cadastro': None,
            'fase': None,
            'instancia': None,
            'cliente': None,
            'contrario': None,
            'advogado': None,
            'procedimento': None,
            'data_distribuicao': None,
            'probabilidade': None,
            'grau_probabilidade': None,
            'risco': None,
            'contingencia': None,
            'descricao_pedidos': None,
            # Novos campos adicionados (campos 16, 17, 18, 22, 23, 24, 25)
            'cidade_comarca': None,        # Campo 16 - texto livre
            'objetos': None,               # Campo 18 - radio (Contrato de trabalho / Outra)
            'pedidos': None,               # Campo 22 - múltipla escolha (checkboxes)
            'vinculo_trabalhista': None,   # Campo 23 - radio (Não / Outra)
            # descricao_pedidos já existe  # Campo 24 - textarea
            # contingencia já existe       # Campo 25 - radio (Ativa / Passiva)
            'perguntas_forms': [],
            'outros_dados': {},
            'timestamp_extracao': datetime.now().isoformat()
        }

        # === NAVEGADOR PERSISTENTE (mantem Forms aberto entre extracoes) ===
        _forms_ok = await self._garantir_forms_aberto(forms_url, timeout)
        if not _forms_ok:
            return dados_extraidos
        page = self._page
        await self._ir_para_ultima_resposta()

        if True:  # Bloco de indentacao para codigo de extracao
            try:
                await asyncio.sleep(3)

                # SCROLL COMPLETO NA PAGINA PARA CARREGAR TODO CONTEUDO
                logger.info("[SCROLL] Fazendo scroll para carregar toda a pagina...")
                try:
                    # Scroll até o final da página
                    await page.evaluate("""
                        async () => {
                            // Scroll para o topo primeiro
                            window.scrollTo(0, 0);
                            await new Promise(resolve => setTimeout(resolve, 500));

                            // Scroll gradual até o final
                            const distance = 100;
                            const delay = 100;

                            while (window.scrollY + window.innerHeight < document.body.scrollHeight) {
                                window.scrollBy(0, distance);
                                await new Promise(resolve => setTimeout(resolve, delay));
                            }

                            // Scroll até o final absoluto
                            window.scrollTo(0, document.body.scrollHeight);
                            await new Promise(resolve => setTimeout(resolve, 1000));
                        }
                    """)
                    logger.info("[OK] Scroll completo realizado")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"[AVISO] Erro ao fazer scroll: {e}")

                # EXTRAÇÃO ESTRUTURADA COMPLETA: captura todas as perguntas visíveis
                try:
                    todas_perguntas = await self._extrair_todas_perguntas_forms()
                    if todas_perguntas:
                        dados_extraidos['perguntas_forms'] = todas_perguntas
                        logger.info(f"[FORMS] ✅ {len(todas_perguntas)} pergunta(s) capturada(s) de forma estruturada")

                        for item in todas_perguntas:
                            pergunta = self.limpar_texto(item.get('pergunta') or '')
                            resposta = self.limpar_texto(item.get('resposta') or '')
                            opcoes = item.get('opcoes') or []
                            marcadas = item.get('marcadas') or []
                            texto_completo = self.limpar_texto(item.get('texto_completo') or '')

                            # Log padronizado: CHAVE_NORMALIZADA: valor
                            if pergunta:
                                _chave_log = re.sub(r'^\s*\d+[\.)\-]?\s*', '', pergunta).strip()
                                _chave_log = re.sub(r'\s*Requer resposta.*$', '', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Opção única.*$', '', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Múltipla escolha.*$', '', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Texto (de linha única|[Mm]ultilinha|longo)\.?\s*', ' ', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Obrigatória\.?\s*', ' ', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Data\.?\s*$', '', _chave_log, flags=re.IGNORECASE).strip()
                                _chave_log = re.sub(r'\s*Número\.?\s*$', '', _chave_log, flags=re.IGNORECASE).strip()
                                _titulo_limpo = _chave_log
                                _chave_log = unicodedata.normalize('NFKD', _chave_log)
                                _chave_log = ''.join(c for c in _chave_log if not unicodedata.combining(c))
                                _chave_log = re.sub(r'[^a-zA-Z0-9]+', '_', _chave_log).strip('_').upper()

                                _val_log = ''
                                if marcadas:
                                    _val_log = ', '.join(marcadas[:5]) + ('...' if len(marcadas) > 5 else '')
                                else:
                                    _resp_texto = self.limpar_texto(item.get('resposta_texto') or '')
                                    _titulo_norm = _titulo_limpo.strip().lower()
                                    if _resp_texto:
                                        _resp_norm = re.sub(r'^\s*\d+[\.)\-]?\s*', '', _resp_texto).strip().lower()
                                        if _resp_norm != _titulo_norm and _resp_norm:
                                            _val_log = _resp_texto
                                    if not _val_log and resposta:
                                        _resp_norm = re.sub(r'^\s*\d+[\.)\-]?\s*', '', resposta).strip().lower()
                                        if _resp_norm != _titulo_norm and _resp_norm not in (_titulo_norm, pergunta.strip().lower()):
                                            _val_log = resposta
                                if _chave_log and _val_log:
                                    _val_log = re.sub(r'^\d+\.\s*', '', _val_log).strip()
                                    _val_log = re.sub(r'^' + re.escape(_titulo_limpo) + r'\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^Requer resposta\.?\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^Texto (de linha [uú]nica|[Mm]ultilinha|longo)\.?\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^Op[çc][aã]o [uú]nica\.?\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^M[uú]ltipla escolha\.?\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^Obrigat[oó]ria\.?\s*', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^Data\.?\s+', '', _val_log, flags=re.IGNORECASE).strip()
                                    _val_log = re.sub(r'^N[uú]mero\.?\s+', '', _val_log, flags=re.IGNORECASE).strip()
                                    if _val_log:
                                        _val_log = _val_log.replace('\n', ' | ')
                                        logger.info(f"   ✅ {_chave_log}: {_val_log}")

                                        # --- Popula campos principais a partir da extração estruturada ---
                                        # Usa _titulo_limpo (título limpo sem metadata) para matching
                                        # e _val_log (valor já limpo) para popular o campo.
                                        # Isso garante que DOM/texto posteriores NÃO sobrescrevam.
                                        _tl = unicodedata.normalize('NFKD', _titulo_limpo.lower())
                                        _tl = ''.join(c for c in _tl if not unicodedata.combining(c))
                                        if 'tipo de cadastro' in _tl and not dados_extraidos['tipo_cadastro']:
                                            dados_extraidos['tipo_cadastro'] = _val_log.upper()
                                        elif _tl == 'fase' and not dados_extraidos['fase']:
                                            dados_extraidos['fase'] = _val_log
                                        elif _tl == 'instancia' and not dados_extraidos['instancia']:
                                            dados_extraidos['instancia'] = _val_log
                                        elif 'valor da causa' in _tl and not dados_extraidos['valor_causa']:
                                            dados_extraidos['valor_causa'] = _val_log
                                        elif 'cidade' in _tl and 'comarca' in _tl and not dados_extraidos['cidade_comarca']:
                                            dados_extraidos['cidade_comarca'] = _val_log
                                            if not dados_extraidos.get('comarca'):
                                                dados_extraidos['comarca'] = _val_log
                                        elif _tl == 'objetos' and not dados_extraidos['objetos']:
                                            dados_extraidos['objetos'] = _val_log
                                        elif ('pedidos' in _tl and 'descreva' not in _tl
                                              and 'descri' not in _tl and marcadas and not dados_extraidos['pedidos']):
                                            dados_extraidos['pedidos'] = _val_log
                                        elif ('vinculo trabalhista' in _tl or 'pedido de vinculo' in _tl) and not dados_extraidos['vinculo_trabalhista']:
                                            dados_extraidos['vinculo_trabalhista'] = _val_log
                                        elif 'descreva todos os pedidos' in _tl and not dados_extraidos['descricao_pedidos']:
                                            dados_extraidos['descricao_pedidos'] = _val_log
                                        elif _tl == 'contingencia' and not dados_extraidos['contingencia']:
                                            dados_extraidos['contingencia'] = _val_log

                            if pergunta:
                                dados_extraidos['outros_dados'].setdefault(pergunta, resposta or texto_completo or '')
                                if texto_completo:
                                    dados_extraidos['outros_dados'].setdefault(f"{pergunta} - Texto completo", texto_completo)
                                if opcoes:
                                    dados_extraidos['outros_dados'].setdefault(f"{pergunta} - Opções", opcoes)
                                if marcadas:
                                    dados_extraidos['outros_dados'].setdefault(f"{pergunta} - Marcadas", marcadas)
                    else:
                        logger.warning("[FORMS] ⚠ Nenhuma pergunta estruturada foi capturada")
                except Exception as e:
                    logger.warning(f"[FORMS] Erro na extração estruturada completa: {e}")

                # DEBUG: Salva HTML da pergunta Pedidos para análise
                try:
                    html_pedidos = await page.evaluate("""
                        () => {
                            // Busca a pergunta que contém "Pedidos"
                            const questions = document.querySelectorAll('[data-automation-id="QuestionItem"], [class*="question"]');
                            for (const q of questions) {
                                if (q.innerText.includes('Pedidos') && q.innerText.includes('Múltipla')) {
                                    return q.outerHTML;
                                }
                            }
                            return null;
                        }
                    """)
                    if html_pedidos:
                        with open("debug_pedidos_html.html", "w", encoding="utf-8") as f:
                            f.write(html_pedidos)
                        logger.info("[DEBUG] HTML da pergunta Pedidos salvo em: debug_pedidos_html.html")
                except Exception as e:
                    logger.debug(f"[DEBUG] Erro ao salvar HTML Pedidos: {e}")

                # EXTRAÇÃO ESPECÍFICA PARA CAMPO "PEDIDOS" (22)
                # Busca diretamente os checkboxes marcados com aria-checked="true"
                try:
                    pergunta_pedidos_existe = any(
                        'pedidos' in str((item.get('pergunta') or '')).lower()
                        and 'descreva' not in str((item.get('pergunta') or '')).lower()
                        and 'descri' not in str((item.get('pergunta') or '')).lower()
                        for item in dados_extraidos.get('perguntas_forms', [])
                    )

                    if not pergunta_pedidos_existe:
                        logger.info("[PEDIDOS] ℹ Pergunta 'Pedidos' não existe neste tipo de cadastro. Pulando extração específica.")
                        pedidos_marcados = []
                    else:
                        logger.info("[PEDIDOS] Aguardando carregamento da pergunta 'Pedidos'...")
                        try:
                            # Tenta esperar pelo texto "Pedidos" ou "22" visível na página
                            await page.wait_for_selector('text=/Pedidos/i', timeout=30000)
                        except Exception:
                            logger.warning("[PEDIDOS] Timeout esperando texto 'Pedidos'. Tentando seletores genéricos...")
                            # Fallback: espera por qualquer item de formulário
                            try:
                                await page.wait_for_selector('[data-automation-id="questionContent"]', timeout=5000)
                            except Exception:
                                try:
                                    await page.wait_for_selector('[data-automation-id="QuestionItem"]', timeout=5000)
                                except Exception:
                                    pass

                        logger.info("[PEDIDOS] Extraindo campo Pedidos especificamente...")
                    
                        # Salva HTML para debug (agora apos o wait)
                        try:
                            html_content = await page.content()
                            with open("debug_forms_dump.html", "w", encoding="utf-8") as f:
                                f.write(html_content)
                            logger.info("[DEBUG] HTML dump salvo em debug_forms_dump.html")
                        except Exception as e:
                            logger.warning(f"[DEBUG] Erro ao salvar dump: {e}")

                        pedidos_marcados = await page.evaluate("""
                            () => {
                                // 1. Encontra a pergunta de Pedidos - Seletores expandidos
                                const normalizeText = (value) => {
                                    if (!value) return '';
                                    try {
                                        return value
                                            .normalize('NFD')
                                            .replace(/[\\u0300-\\u036f]/g, '')
                                            .toUpperCase();
                                    } catch (e) {
                                        return String(value).toUpperCase();
                                    }
                                };

                                const hasChoices = (el) => {
                                    if (!el) return false;
                                    return el.querySelector('[data-automation-id="questionChoiceOptionContainer"], [role="checkbox"], [role="radio"]');
                                };

                                let pedidosContainer = null;
                                const debugLog = [];

                                // 1a. Prioriza encontrar pelo titulo da pergunta
                                const titleSelectors = [
                                    '[data-automation-id="questionTitle"]',
                                    '[data-automation-id="QuestionText"]',
                                    '[data-automation-id="QuestionTitle"]'
                                ];

                                const titleNodes = document.querySelectorAll(titleSelectors.join(','));
                                for (const titleEl of titleNodes) {
                                    const text = normalizeText(titleEl.innerText || titleEl.textContent || '');
                                    if (!text) continue;
                                    if (text.includes('PEDIDOS') && !text.includes('DESCREVA')) {
                                        const container =
                                            titleEl.closest('[data-automation-id="questionContent"]') ||
                                            titleEl.closest('[data-automation-id="QuestionItem"]') ||
                                            titleEl.parentElement;

                                        if (hasChoices(container)) {
                                            pedidosContainer = container;
                                            break;
                                        }
                                    }
                                }

                                // 1b. Fallback: varre containers de pergunta
                                if (!pedidosContainer) {
                                    const questionSelectors = [
                                        '[data-automation-id="questionContent"]',
                                        '[data-automation-id="QuestionItem"]',
                                        '.question-container',
                                        '.office-form-question',
                                        '[class*="question"]',
                                        'div[role="listitem"]',
                                        'div[aria-label*="Pergunta"]'
                                    ];

                                    // Coleta todos os candidatos a pergunta
                                    const questions = new Set();
                                    questionSelectors.forEach(sel => {
                                        document.querySelectorAll(sel).forEach(el => questions.add(el));
                                    });

                                    // Debug: lista textos encontrados
                                    let i = 0;
                                    for (const q of questions) {
                                        if (i > 80) break; // Limite de log
                                        const text = normalizeText(q.innerText || q.textContent || '');
                                        if (text) {
                                            debugLog.push(`[${i}] ${text.substring(0, 120)}`);
                                        }
                                        i++;

                                        if (text.includes('PEDIDOS') && !text.includes('DESCREVA') && hasChoices(q)) {
                                            pedidosContainer = q;
                                            break;
                                        }
                                    }
                                }

                                if (!pedidosContainer) return ["DEBUG_NOT_FOUND", ...debugLog];

                                // 2. Busca checkboxes verificados DENTRO do container
                                // Usa múltiplos métodos para máxima cobertura
                                const marcados = [];
                                const seenNorm = new Set();

                                const addMarcado = (raw) => {
                                    if (!raw) return;
                                    const label = raw.replace(/\\s+/g, ' ').trim();
                                    if (label.length < 2 || label.length > 200) return;
                                    const key = label.toLowerCase();
                                    if (seenNorm.has(key)) return;
                                    seenNorm.add(key);
                                    marcados.push(label);
                                };

                                // Helper: verifica aria-checked subindo/descendo no DOM
                                const getAriaCheckedPedidos = (element) => {
                                    if (!element) return null;
                                    const direct = element.getAttribute('aria-checked');
                                    if (direct !== null) return direct === 'true';
                                    let parent = element.parentElement;
                                    for (let i = 0; i < 2 && parent; i++) {
                                        const pv = parent.getAttribute('aria-checked');
                                        if (pv !== null) return pv === 'true';
                                        parent = parent.parentElement;
                                    }
                                    const child = element.querySelector('[aria-checked]');
                                    if (child) return child.getAttribute('aria-checked') === 'true';
                                    return null;
                                };

                                // M1: aria-checked / aria-selected / input:checked direto
                                pedidosContainer.querySelectorAll('[aria-checked="true"], [aria-selected="true"], input:checked').forEach((el) => {
                                    const lbl = el.closest('label, [role="checkbox"], [role="radio"], [role="option"]') || el.parentElement || el;
                                    addMarcado(
                                        el.getAttribute('aria-label') ||
                                        lbl?.innerText ||
                                        lbl?.textContent ||
                                        el.value || ''
                                    );
                                });

                                // M2: questionChoiceOptionContainer com getAriaChecked
                                const choiceSels = [
                                    '[data-automation-id="questionChoiceOptionContainer"]',
                                    '[data-automation-id*="Choice"]',
                                    '[data-automation-id*="Option"]'
                                ];
                                for (const csel of choiceSels) {
                                    pedidosContainer.querySelectorAll(csel).forEach((el) => {
                                        let isChecked = getAriaCheckedPedidos(el);
                                        if (isChecked === null) {
                                            isChecked = el.querySelector('input:checked') !== null;
                                        }
                                        if (isChecked) {
                                            let text = el.getAttribute('aria-label');
                                            if (!text) {
                                                const span = el.querySelector('.text-format-content, [class*="text-format"], span');
                                                text = span ? span.innerText.trim() : el.innerText.trim().split('\\n')[0];
                                            }
                                            addMarcado(text);
                                        }
                                    });
                                }

                                // M3: classes dinâmicas do MS Forms
                                pedidosContainer.querySelectorAll('[class*="--cE-"], [class*="choice"], [class*="option"]').forEach((el) => {
                                    let isChecked = getAriaCheckedPedidos(el);
                                    if (isChecked === null) {
                                        isChecked = el.querySelector('input:checked') !== null;
                                    }
                                    if (isChecked) {
                                        let text = el.getAttribute('aria-label');
                                        if (!text) {
                                            const span = el.querySelector('.text-format-content, [class*="--yI-"], span[class*="-yJ-"]');
                                            text = span ? span.innerText.trim() : el.innerText.trim().split('\\n')[0];
                                        }
                                        addMarcado(text);
                                    }
                                });

                                // M4: role checkbox/radio/option
                                pedidosContainer.querySelectorAll('[role="checkbox"], [role="radio"], [role="option"]').forEach((item) => {
                                    const isChecked = item.getAttribute('aria-checked') === 'true' ||
                                                     item.getAttribute('aria-selected') === 'true';
                                    if (isChecked) {
                                        addMarcado(item.getAttribute('aria-label') || item.innerText.trim());
                                    }
                                });

                                // M5: inputs HTML nativos
                                pedidosContainer.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach((inp) => {
                                    if (inp.checked) {
                                        const lbl = inp.closest('label') ||
                                                    document.querySelector('label[for="' + inp.id + '"]') ||
                                                    inp.parentElement;
                                        if (lbl) addMarcado(lbl.innerText.trim());
                                    }
                                });
                            
                                return marcados;
                            }
                        """)

                        # Normaliza e mapeia para as opções oficiais de "Pedidos"
                        opcoes_pedidos_canonicas = [
                            'Acúmulo de função', 'Adicional de insalubridade', 'Adicional de periculosidade',
                            'Adicional noturno', 'Aviso prévio', 'Benefício CCT', 'Comissões',
                            'Contribuições previdenciárias', 'Correção monetária', 'Desvio de Função',
                            'Diferença salarial', 'Entrega/Retificação/Indenização - PPP', 'Equiparação Salarial',
                            'Férias + 1/3', 'FGTS + 40%', 'Honorários advocatícios sucumbenciais',
                            'Horas bip', 'Horas extras', 'Ilicitude terceirização',
                            'Indenização estabilidade acidentária/doença', 'Indenização estabilidade Cipa',
                            'Indenização estabilidade gravídica', 'Indenização por danos estéticos',
                            'Indenização por danos materiais', 'Indenização por danos morais',
                            'Intervalo interjornada', 'Intervalo intrajornada', 'Multa art. 479',
                            'Multas convencionais', 'Multa do artigo 467 da CLT', 'Multa do artigo 477,  §8º da CLT',
                            'Pensão vitalícia', 'Plano de saúde', 'PLR', 'Salários', 'Saldo de salário',
                            'Vale alimentação', 'Vale cultura', 'Vale transporte', 'Verbas rescisórias',
                            'Vínculo', 'Vínculo - Pejotização', '13º salario'
                        ]

                        def _normalize_pedido_text(value: str) -> str:
                            if not value:
                                return ""
                            normalized = unicodedata.normalize("NFD", value)
                            normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
                            normalized = re.sub(r"\s+", " ", normalized).strip().lower()
                            return normalized

                        opcoes_norm_map = { _normalize_pedido_text(opt): opt for opt in opcoes_pedidos_canonicas }

                        def _mapear_pedidos(pedidos):
                            if not pedidos:
                                return pedidos
                            mapeados = []
                            for item in pedidos:
                                item_norm = _normalize_pedido_text(item)
                                if not item_norm:
                                    continue
                                if item_norm in opcoes_norm_map:
                                    candidato = opcoes_norm_map[item_norm]
                                else:
                                    candidato = None
                                    for opt_norm, opt_val in opcoes_norm_map.items():
                                        if opt_norm in item_norm or item_norm in opt_norm:
                                            candidato = opt_val
                                            break
                                mapeados.append(candidato or item)

                            # Dedup preservando ordem
                            vistos = set()
                            resultado = []
                            for item in mapeados:
                                key = _normalize_pedido_text(item)
                                if key and key not in vistos:
                                    vistos.add(key)
                                    resultado.append(item)
                            return resultado
                    
                        if pedidos_marcados and len(pedidos_marcados) > 0:
                            if pedidos_marcados[0] == "DEBUG_NOT_FOUND":
                                logger.info(f"[PEDIDOS] ℹ Estrutura específica de 'Pedidos' não encontrada. A extração genérica seguirá válida. Exemplos: {pedidos_marcados[1:5]}")
                                # Salva log de perguntas visiveis
                                with open("debug_questions_list.txt", "w", encoding="utf-8") as f:
                                    f.write("\n".join(pedidos_marcados[1:]))
                            else:
                                pedidos_marcados = _mapear_pedidos(pedidos_marcados)
                                pedidos_str = ", ".join(pedidos_marcados)
                                dados_extraidos['pedidos'] = pedidos_str
                                logger.info(f"[PEDIDOS] ✅ Encontrados {len(pedidos_marcados)} pedidos: {pedidos_str}")
                        else:
                            # Fallback: usa marcadas da extração estruturada (_extrair_todas_perguntas_forms)
                            for item in (dados_extraidos.get('perguntas_forms') or []):
                                p = str(item.get('pergunta') or '').lower()
                                if 'pedidos' in p and 'descreva' not in p and 'descri' not in p:
                                    marcadas_fallback = item.get('marcadas') or []
                                    if marcadas_fallback:
                                        pedidos_marcados = _mapear_pedidos(marcadas_fallback)
                                        pedidos_str = ", ".join(pedidos_marcados)
                                        dados_extraidos['pedidos'] = pedidos_str
                                        logger.info(f"[PEDIDOS] ✅ (fallback estruturado) {len(pedidos_marcados)} pedidos: {pedidos_str}")
                                        break
                            else:
                                logger.info("[PEDIDOS] Estrutura encontrada mas nenhum item marcado")
                        
                except Exception as e:
                    logger.warning(f"[PEDIDOS] Erro ao extrair pedidos: {e}")

                # Extração DOM: opções e marcadas (prioriza seleção real)
                # IMPORTANTE: Na visualização de respostas do Forms, as opções marcadas
                # aparecem com ícones de check ou classes específicas
                try:
                    if VERBOSE_FORMS_LOGS:
                        logger.info("[DOM] Capturando perguntas e opcoes marcadas...")
                    dom_perguntas = await page.evaluate("""
                        () => {
                            const resultado = [];

                            // Tenta diferentes seletores para perguntas
                            const questionSelectors = [
                                '[data-automation-id="questionContent"]',
                                '[data-automation-id="QuestionItem"]',
                                '.question-container',
                                '.office-form-question',
                                '[class*="question"]'
                            ];

                            let perguntas = [];
                            for (const sel of questionSelectors) {
                                perguntas = Array.from(document.querySelectorAll(sel));
                                if (perguntas.length > 0) break;
                            }

                            // Se não encontrou estrutura de perguntas, tenta análise de texto
                            if (perguntas.length === 0) {
                                return [];
                            }

                            // Função auxiliar para verificar aria-checked em múltiplos níveis
                            const getAriaChecked = (element) => {
                                if (!element) return null;

                                const direct = element.getAttribute('aria-checked');
                                if (direct !== null) return direct === 'true';

                                let parent = element.parentElement;
                                for (let i = 0; i < 2 && parent; i++) {
                                    const parentVal = parent.getAttribute('aria-checked');
                                    if (parentVal !== null) return parentVal === 'true';
                                    parent = parent.parentElement;
                                }

                                const child = element.querySelector('[aria-checked]');
                                if (child) return child.getAttribute('aria-checked') === 'true';

                                return null;
                            };

                            return perguntas.map(q => {
                                // Busca título da pergunta
                                const titleSelectors = [
                                    '[data-automation-id="questionTitle"]',
                                    '[data-automation-id="QuestionText"]',
                                    '[data-automation-id="QuestionTitle"]',
                                    '.question-title',
                                    '.question-text',
                                    'h3',
                                    'h4',
                                    '[class*="title"]'
                                ];

                                let question = '';
                                for (const sel of titleSelectors) {
                                    const el = q.querySelector(sel);
                                    if (el) {
                                        question = el.innerText.trim();
                                        break;
                                    }
                                }

                                // Busca resposta direta (para campos de texto)
                                const answerSelectors = [
                                    '[data-automation-id="AnswerText"]',
                                    '.answer-text',
                                    '.response-text',
                                    '.answer-value',
                                    '[class*="answer"]',
                                    '[class*="response"]'
                                ];

                                let answerText = '';
                                for (const sel of answerSelectors) {
                                    const el = q.querySelector(sel);
                                    if (el) {
                                        answerText = el.innerText.trim();
                                        break;
                                    }
                                }

                                const options = [];
                                const selected = [];
                                const seen = new Set();
                                const seenNormalized = new Set();

                                // Função de adição com deduplicação normalizada
                                const normalize = (text) => text.trim().toLowerCase();
                                
                                const addOption = (text, isSelected) => {
                                    if (!text || text.length > 200 || text.length < 2) return;
                                    text = text.trim();
                                    const normalizedText = normalize(text);
                                    
                                    if (!seenNormalized.has(normalizedText)) {
                                        seenNormalized.add(normalizedText);
                                        seen.add(text);
                                        options.push(text);
                                    }
                                    
                                    if (isSelected) {
                                        // Verifica se já não está selecionado (com normalização)
                                        const alreadySelected = selected.some(s => normalize(s) === normalizedText);
                                        if (!alreadySelected) {
                                            selected.push(text);
                                        }
                                    }
                                };

                                // MÉTODO 1: Seletores robustos baseados em data-automation-id (prioridade máxima)
                                const primarySelectors = [
                                    '[data-automation-id="questionChoiceOptionContainer"]',
                                    '[data-automation-id*="Choice"]',
                                    '[data-automation-id*="Option"]'
                                ];
                                
                                for (const selector of primarySelectors) {
                                    const containers = q.querySelectorAll(selector);
                                    containers.forEach(container => {
                                        // Texto: prioriza aria-label, depois texto interno
                                        let text = container.getAttribute('aria-label');
                                        if (!text) {
                                            const textSpan = container.querySelector('.text-format-content, [class*="text-format"], span');
                                            text = textSpan ? textSpan.innerText.trim() : container.innerText.trim().split('\\n')[0];
                                        }
                                        
                                        if (!text || text.length > 200 || text.length < 2) return;
                                        
                                        // Detecção de seleção - aria-checked é prioridade máxima
                                        let isItemSelected = getAriaChecked(container);
                                        
                                        // Fallback: input checked (quando aria-checked não existir)
                                        if (isItemSelected === null) {
                                            isItemSelected = container.querySelector('input:checked') !== null;
                                        }
                                        
                                        addOption(text, isItemSelected);
                                    });
                                }
                                
                                // MÉTODO 2: Busca por classes dinâmicas do MS Forms (fallback)
                                const formsChoices = q.querySelectorAll('[class*="--cE-"], [class*="choice"], [class*="option"]');
                                formsChoices.forEach(container => {
                                    let text = container.getAttribute('aria-label');
                                    if (!text) {
                                        const textSpan = container.querySelector('.text-format-content, [class*="--yI-"], span[class*="-yJ-"]');
                                        text = textSpan ? textSpan.innerText.trim() : container.innerText.trim().split('\\n')[0];
                                    }
                                    
                                    if (!text || text.length > 200 || text.length < 2) return;
                                    
                                    let isItemSelected = getAriaChecked(container);
                                    if (isItemSelected === null) {
                                        isItemSelected = container.querySelector('input:checked') !== null;
                                    }
                                    
                                    addOption(text, isItemSelected);
                                });

                                // MÉTODO 3: Busca por role="checkbox" ou role="radio" com aria-checked
                                const roleItems = q.querySelectorAll('[role="checkbox"], [role="radio"], [role="option"]');
                                roleItems.forEach(item => {
                                    const text = item.getAttribute('aria-label') || item.innerText.trim();
                                    if (!text || text.length > 200 || text.length < 2) return;
                                    
                                    const isChecked = item.getAttribute('aria-checked') === 'true' ||
                                                     item.getAttribute('aria-selected') === 'true';
                                    addOption(text, isChecked);
                                });

                                // MÉTODO 4: Busca específica para checkboxes/radios HTML nativos
                                const inputs = q.querySelectorAll('input[type="checkbox"], input[type="radio"]');
                                inputs.forEach(input => {
                                    const label = input.closest('label') ||
                                                 document.querySelector(`label[for="${input.id}"]`) ||
                                                 input.parentElement;
                                    if (label) {
                                        const text = label.innerText.trim();
                                        addOption(text, input.checked);
                                    }
                                });
                                
                                // MÉTODO 5: Se não encontrou selecionadas mas tem answerText, usa ele
                                if (selected.length === 0 && answerText && answerText.length > 0) {
                                    const respostas = answerText.split(/[,\\n]/).map(r => r.trim()).filter(r => r.length > 0);
                                    respostas.forEach(r => {
                                        if (r.length < 100) {
                                            addOption(r, true);
                                        }
                                    });
                                }

                                return { question, options, selected, answerText };
                            });
                        }
                    """)

                    if dom_perguntas and VERBOSE_FORMS_LOGS:
                        logger.info(f"[DOM] Encontradas {len(dom_perguntas)} perguntas via DOM")
                        for item in dom_perguntas:
                            pergunta = (item.get('question') or '').strip()
                            if not pergunta:
                                continue

                            opcoes = item.get('options') or []
                            selecionadas = item.get('selected') or []
                            resposta_texto = (item.get('answerText') or '').strip()

                            # Debug: mostra o que foi encontrado para cada pergunta
                            if (opcoes or selecionadas) and VERBOSE_FORMS_LOGS:
                                logger.info(f"   [DOM] {pergunta[:50]}...")
                                logger.info(f"         Opções: {len(opcoes)}, Selecionadas: {len(selecionadas)}")
                                if selecionadas:
                                    logger.info(f"         Marcadas: {selecionadas}")

                            if opcoes:
                                dados_extraidos['outros_dados'][f"{pergunta} - Opções"] = opcoes

                            resposta_final = None
                            if selecionadas:
                                resposta_final = ", ".join([s for s in selecionadas if s])
                                if VERBOSE_FORMS_LOGS:
                                    logger.info(f"   📋 {pergunta}: {len(selecionadas)} opções marcadas: {resposta_final}")
                            elif resposta_texto and (not opcoes or resposta_texto not in opcoes):
                                resposta_final = resposta_texto

                            if resposta_final:
                                # Sobrescreve valor anterior se este for mais completo
                                valor_existente = dados_extraidos['outros_dados'].get(pergunta)
                                if not valor_existente or len(resposta_final) > len(str(valor_existente)):
                                    dados_extraidos['outros_dados'][pergunta] = resposta_final

                                self._sincronizar_pergunta_extraida(
                                    dados_extraidos,
                                    pergunta=pergunta,
                                    resposta=resposta_final,
                                    opcoes=opcoes,
                                    marcadas=selecionadas,
                                )

                                p_lower = pergunta.lower()
                                p_normalized = re.sub(r'^\\s*\\d+\\.\\s*', '', p_lower).strip()
                                if 'tipo de cadastro' in p_lower and not dados_extraidos['tipo_cadastro']:
                                    dados_extraidos['tipo_cadastro'] = resposta_final.upper()
                                elif 'fase' in p_lower and not dados_extraidos['fase']:
                                    dados_extraidos['fase'] = resposta_final
                                elif 'instância' in p_lower and not dados_extraidos['instancia']:
                                    dados_extraidos['instancia'] = resposta_final
                                elif 'valor da causa' in p_lower and not dados_extraidos['valor_causa']:
                                    dados_extraidos['valor_causa'] = resposta_final
                                # Campo 16 - Cidade/Comarca
                                elif 'cidade/comarca' in p_lower and not dados_extraidos['cidade_comarca']:
                                    dados_extraidos['cidade_comarca'] = resposta_final
                                    # Também preenche comarca para compatibilidade
                                    if not dados_extraidos.get('comarca'):
                                        dados_extraidos['comarca'] = resposta_final
                                # Campo 18 - Objetos (radio: Contrato de trabalho / Outra)
                                elif 'objetos' in p_lower and not dados_extraidos['objetos']:
                                    dados_extraidos['objetos'] = resposta_final
                                # Campo 22 - Pedidos (múltipla escolha - checkboxes)
                                elif 'pedidos' in p_normalized and 'descreva' not in p_normalized and 'descri' not in p_normalized:
                                    if selecionadas and not dados_extraidos['pedidos']:
                                        dados_extraidos['pedidos'] = resposta_final
                                        if VERBOSE_FORMS_LOGS:
                                            logger.info(f"   ✅ PEDIDOS CAPTURADOS: {resposta_final}")
                                # Campo 23 - Há pedido de vínculo trabalhista? (radio: Não / Outra)
                                elif ('vínculo trabalhista' in p_lower or 'pedido de vínculo' in p_lower) and not dados_extraidos['vinculo_trabalhista']:
                                    dados_extraidos['vinculo_trabalhista'] = resposta_final
                                # Campo 24 - Descrição dos pedidos (textarea)
                                elif 'descreva todos os pedidos' in p_lower and not dados_extraidos['descricao_pedidos']:
                                    dados_extraidos['descricao_pedidos'] = resposta_final
                                # Campo 25 - Contingência (radio: Ativa / Passiva)
                                elif 'contingência' in p_lower and not dados_extraidos['contingencia']:
                                    dados_extraidos['contingencia'] = resposta_final
                                elif 'probabilidade atual' in p_lower:
                                    dados_extraidos['outros_dados'].setdefault('Probabilidade', resposta_final)
                                elif 'grau de probabilidade' in p_lower:
                                    dados_extraidos['outros_dados'].setdefault('Grau Probabilidade', resposta_final)
                                elif p_lower == 'risco' or p_lower.endswith('risco'):
                                    dados_extraidos['outros_dados'].setdefault('Risco', resposta_final)
                            elif opcoes or selecionadas:
                                self._sincronizar_pergunta_extraida(
                                    dados_extraidos,
                                    pergunta=pergunta,
                                    resposta=resposta_texto or None,
                                    opcoes=opcoes,
                                    marcadas=selecionadas,
                                )

                except Exception as e:
                    logger.warning(f"[AVISO] Erro ao capturar DOM: {e}")

                # Sincroniza pedidos extraidos com outros_dados para log/consumo
                if dados_extraidos.get('pedidos'):
                    pedidos_valor = dados_extraidos['pedidos']
                    outros = dados_extraidos.setdefault('outros_dados', {})
                    for chave in list(outros.keys()):
                        chave_lower = str(chave).lower()
                        if (
                            'pedidos' in chave_lower
                            and 'descreva' not in chave_lower
                            and 'descri' not in chave_lower
                            and 'opção' not in chave_lower
                            and 'opcao' not in chave_lower
                            and 'opções' not in chave_lower
                            and 'opcoes' not in chave_lower
                        ):
                            outros[chave] = pedidos_valor
                    outros.setdefault('Pedidos', pedidos_valor)

                page_content = await page.content()

                # Extrai dados por seletores
                response_selectors = [
                    '.response-text',
                    '.answer-text',
                    '[data-automation-id="QuestionText"]',
                    '[data-automation-id="AnswerText"]',
                    '.question-title',
                    '.answer-container',
                ]

                for selector in response_selectors:
                    elements = await page.query_selector_all(selector)
                    for elem in elements:
                        try:
                            texto = await elem.inner_text()
                            texto = self.limpar_texto(texto)

                            if texto:
                                texto_lower = texto.lower()

                                # CNJ
                                if not dados_extraidos['cnj']:
                                    cnj = self.extrair_cnj(texto)
                                    if cnj:
                                        dados_extraidos['cnj'] = cnj

                                # Autor
                                if 'autor' in texto_lower or 'reclamante' in texto_lower:
                                    match = re.search(r'(?:autor|reclamante)[:\s]*(.*?)(?:\n|$)', texto, re.IGNORECASE)
                                    if match:
                                        dados_extraidos['autor'] = self.limpar_texto(match.group(1))

                                # Réu
                                if 'réu' in texto_lower or 'reclamado' in texto_lower:
                                    match = re.search(r'(?:réu|reclamado)[:\s]*(.*?)(?:\n|$)', texto, re.IGNORECASE)
                                    if match:
                                        dados_extraidos['reu'] = self.limpar_texto(match.group(1))

                                # Tribunal
                                if 'tribunal' in texto_lower or 'trt' in texto_lower:
                                    match = re.search(r'(?:tribunal|trt)[:\s]*(.*?)(?:\n|$)', texto, re.IGNORECASE)
                                    if match:
                                        dados_extraidos['tribunal'] = self.limpar_texto(match.group(1))

                                # Vara
                                if 'vara' in texto_lower:
                                    match = re.search(r'vara[:\s]*(.*?)(?:\n|$)', texto, re.IGNORECASE)
                                    if match:
                                        dados_extraidos['vara'] = self.limpar_texto(match.group(1))

                                # Comarca
                                if 'comarca' in texto_lower:
                                    match = re.search(r'comarca[:\s]*(.*?)(?:\n|$)', texto, re.IGNORECASE)
                                    if match:
                                        dados_extraidos['comarca'] = self.limpar_texto(match.group(1))

                        except Exception as e:
                            logger.debug(f"Erro ao processar elemento: {e}")
                            continue

                # Fallback 1: Extrai texto visível completo da página
                if VERBOSE_FORMS_LOGS:
                    logger.info("[EXTRACAO] Extraindo texto completo da pagina...")
                try:
                    texto_completo = await page.evaluate("""
                        () => {
                            return document.body.innerText;
                        }
                    """)

                    if texto_completo:
                        self._processar_texto_completo(texto_completo, dados_extraidos)

                except Exception as e:
                    logger.warning(f"[AVISO] Erro ao extrair texto completo: {e}")

                # Fallback 2: busca no HTML completo
                if not dados_extraidos['cnj']:
                    if VERBOSE_FORMS_LOGS:
                        logger.info("[FALLBACK] Buscando CNJ no HTML...")
                    dados_extraidos['cnj'] = self.extrair_cnj(page_content)

                dados_extraidos = self._aplicar_mapeamento_forms(dados_extraidos)

                # Screenshot removido para evitar timeout em páginas pesadas
                pass  # Navegador persistente: nao fecha o browser
                return dados_extraidos

            except Exception as e:
                logger.error(f"❌ Erro ao extrair dados: {e}")
                # Fallback: tenta Scrapling para capturar o texto bruto
                if SCRAPLING_DISPONIVEL:
                    try:
                        logger.info("[FALLBACK] Tentando extracao de texto com Scrapling...")
                        texto_scrapling = scrapling_fetch_text(forms_url)
                        if texto_scrapling:
                            self._processar_texto_completo(texto_scrapling, dados_extraidos)
                    except Exception as se:
                        logger.warning(f"[FALLBACK] Scrapling falhou: {se}")
                dados_extraidos = self._aplicar_mapeamento_forms(dados_extraidos)
                try:
                    pass  # Navegador persistente: nao fecha o browser
                except:
                    pass
                return dados_extraidos


async def teste_extrator():
    """Função de teste"""
    forms_url = input("Cole a URL do Forms: ").strip()
    if not forms_url:
        logger.error("❌ URL não fornecida")
        return

    extrator = FormsExtractor()
    try:
        dados = await extrator.extrair_dados_forms(forms_url)

        print("\n" + "="*60)
        print("RESULTADO:")
        print("="*60)
        for campo, valor in dados.items():
            if campo != 'outros_dados':
                print(f"{campo}: {valor}")
        print("="*60)
    finally:
        await extrator.fechar_forms()


if __name__ == "__main__":
    asyncio.run(teste_extrator())
