"""
Módulo para cadastro automático de processos no LegalOne
Versão Otimizada: Mantém navegador e sessão ativos
"""

import time
import os
import re
import json
import base64
import requests
import difflib
import subprocess
import sys
import tempfile
import unicodedata
import equipe
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import logging

load_dotenv()

try:
    import agentql
except Exception:
    agentql = None

try:
    from page_analyzer import get_analyzer as _get_page_analyzer
except ImportError:
    _get_page_analyzer = None  # type: ignore

try:
    import browser_use_fallback as _bu_fallback
except ImportError:
    _bu_fallback = None

try:
    from visual_guardian import VisualGuardian, guarded as _guarded
    _VISUAL_GUARDIAN_DISPONIVEL = True
except ImportError:
    VisualGuardian = None  # type: ignore
    _guarded = None
    _VISUAL_GUARDIAN_DISPONIVEL = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PEDIDOS_SINONIMOS = {
    "verbas rescisórias": ["verbas rescisorias", "rescisão", "rescisao contratual", "verbas trabalhistas"],
    "horas extras": ["hora extra", "he", "horas extraordinárias"],
    "adicional noturno": ["ad. noturno", "adic. noturno"],
    "férias": ["ferias", "ferias + 1/3", "férias vencidas"],
    "13º salário": ["13 salario", "decimo terceiro", "décimo terceiro", "13o"],
    "fgts": ["f.g.t.s.", "fundo de garantia", "multa fgts", "fgts + 40%"],
    "aviso prévio": ["aviso previo", "aviso prévio indenizado"],
    "danos morais": ["dano moral", "d. morais"],
}

PEDIDOS_CATALOGO_LEGALONE = (
    "Acúmulo de função", "Adicional de insalubridade", "Adicional de periculosidade",
    "Adicional noturno", "Aviso prévio", "Benefício CCT", "Comissões",
    "Contribuições previdenciárias", "Correção monetária", "Desvio de Função",
    "Diferença salarial", "Entrega/Retificação/Indenização - PPP", "Equiparação Salarial",
    "Férias + 1/3", "FGTS + 40%", "Honorários advocatícios sucumbenciais",
    "Horas bip", "Horas extras", "Ilicitude terceirização",
    "Indenização estabilidade acidentária/doença", "Indenização estabilidade Cipa",
    "Indenização estabilidade gravídica", "Indenização por danos estéticos",
    "Indenização por danos materiais", "Indenização por danos morais",
    "Intervalo interjornada", "Intervalo intrajornada", "Multa art. 479",
    "Multas convencionais", "Multa do artigo 467 da CLT", "Multa do artigo 477, §8º da CLT",
    "Pensão vitalícia", "Plano de saúde", "PLR", "Salários", "Saldo de salário",
    "Vale alimentação", "Vale cultura", "Vale transporte", "Verbas rescisórias",
    "Vínculo", "Vínculo - Pejotização", "13º salario",
    # Variações verificadas no lookup real do LegalOne.
    "13º Salario Proporcional", "Férias Proporcionais", "FGTS+40%",
    "Multa", "Multa artigo 467 clt", "Multa artigo 477 clt",
    "Entrega das guias CD/SD", "Entrega das guias TRCT",
    "Parcelas Seguro-desemprego", "Indenização adicional", "Saldo de salario",
)

PEDIDOS_ALIASES_CATALOGO = {
    "aviso previo": "Aviso prévio",
    "13 proporcional": "13º salario",
    "13 salario": "13º salario",
    "ferias proporcionais": "Férias Proporcionais",
    "fgts 40": "FGTS+40%",
    "multa 40 fgts": "FGTS+40%",
    "multa art 467": "Multa artigo 467 clt",
    "multa art 477": "Multa artigo 477 clt",
    "hora extra": "Horas extras",
    "honorarios": "Honorários advocatícios sucumbenciais",
    "verbas rescisorias": "Verbas rescisórias",
    "seguro desemprego": "Parcelas Seguro-desemprego",
    "liberacao de guias": "Entrega das guias CD/SD",
    "indenizacao": "Indenização adicional",
}


class NavegadorFechado(RuntimeError):
    """A pagina/contexto morreu no meio do cadastro (alguem fechou o Chrome).

    Existe para abortar o ciclo na hora: sem isso o bot seguia preenchendo campo
    por campo numa pagina morta, reabria o navegador e reportava erros falsos
    ('Posição nao localizado') que escondiam a causa real.
    """


def _pagina_morta(e: Exception) -> bool:
    """True quando a excecao do Playwright indica pagina/browser fechado."""
    msg = str(e)
    return 'has been closed' in msg or 'Target closed' in msg or 'Browser closed' in msg


ORIGENS_DA_BASE = ('existente na base', 'existente', 'interno', 'legalone',
                   'legal one', 'cadastro')


def _prioridade_origem(opcao: dict) -> int:
    """0 = contato da base, 1 = origem desconhecida, 2 = capturado no orgao.

    Contato capturado no orgao nao tem documento e exige adicao manual: so deve
    ser escolhido quando nao existe nenhum equivalente na base.
    """
    origem = unicodedata.normalize('NFKD', str((opcao or {}).get('origem') or ''))
    origem = origem.encode('ascii', 'ignore').decode().strip().lower()
    if any(p in origem for p in ORIGENS_DA_BASE):
        return 0
    if 'capturado' in origem:
        return 2
    return 1


def _eh_matriz(opcao: dict) -> bool:
    """CNPJ de matriz: o bloco de ordem e' 0001 (ex.: 60.701.190/0001-04)."""
    doc = re.sub(r'\D', '', str((opcao or {}).get('cpf_cnpj') or ''))
    return len(doc) == 14 and doc[8:12] == '0001'


def _campo_exige_match_forte(nome_campo: str) -> bool:
    """Campos de catalogo onde escolher 'o mais parecido' e' pior que nao preencher.

    Em 30/07 o valor pedido era 'Pro bono' — que nao existe na lista de contratos
    do escritorio — e o fuzzy de 45% casou com 'Proveito Economico...', gravando
    'Hon - 0000002/002' no processo. Nesses campos exigimos match exato/contido.
    """
    n = unicodedata.normalize('NFKD', (nome_campo or '')).encode('ascii', 'ignore').decode().lower()
    # Aceita rotulo em portugues (producao) e formcontrolname em ingles (testes,
    # e chamadas que passam o nome do controle em vez do label).
    return any(t in n for t in (
        'honorario', 'negociacao', 'centro de custo', 'contrato',
        'negotiation', 'contract', 'costcenter', 'cost center',
    ))


def eh_cadastro_inicial(dados_processo: dict) -> bool:
    """True quando o pedido e' um cadastro inicial (e nao decisao/recurso/pedidos).

    Usada para decidir que processo ja cadastrado = nada a fazer. Os dois campos
    convivem: 'tipo_cadastro' vem do Forms ('CADASTRO INICIAL') e
    'tipo_tarefa_identificada' da classificacao ('CADASTRO_INICIAL').
    """
    rotulos = (
        f"{(dados_processo or {}).get('tipo_cadastro') or ''} "
        f"{(dados_processo or {}).get('tipo_tarefa_identificada') or ''}"
    )
    return 'INICIAL' in rotulos.upper()


def _normalizar_pedido(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii')
    return s.strip().lower()


def _resolver_pedido_catalogo(nome: str) -> str:
    """Converte texto livre do Copilot/Forms para a opção canônica do LegalOne."""
    original = str(nome or "").strip()
    normalizado = _normalizar_pedido(original)
    if not normalizado:
        return original

    catalogo_normalizado = {
        _normalizar_pedido(opcao): opcao for opcao in PEDIDOS_CATALOGO_LEGALONE
    }
    if normalizado in catalogo_normalizado:
        return catalogo_normalizado[normalizado]

    for alias, opcao in PEDIDOS_ALIASES_CATALOGO.items():
        if alias in normalizado or normalizado in alias:
            return opcao

    for chave, sinonimos in PEDIDOS_SINONIMOS.items():
        if normalizado == _normalizar_pedido(chave) or any(
            normalizado == _normalizar_pedido(sinonimo) for sinonimo in sinonimos
        ):
            for opcao_norm, opcao in catalogo_normalizado.items():
                if _normalizar_pedido(chave) in opcao_norm or opcao_norm in _normalizar_pedido(chave):
                    return opcao

    candidatos = difflib.get_close_matches(
        normalizado, list(catalogo_normalizado), n=1, cutoff=0.78
    )
    return catalogo_normalizado[candidatos[0]] if candidatos else original


LOGIN_URL = os.getenv(
    'LEGALONE_LOGIN_URL',
    'https://carvalhofurtadoadv.novajus.com.br/',
)
USERNAME = os.getenv('LEGALONE_USERNAME', 'seu_email@exemplo.com')
PASSWORD = os.getenv('LEGALONE_PASSWORD', '')


class LegalOneCadastro:
    """Gerencia login e cadastro de processos no LegalOne"""

    def __init__(self, username=USERNAME, password=PASSWORD, use_agentql: bool | None = None, agentql_api_key: str | None = None):
        self.username = username
        self.password = password
        if use_agentql is None:
            env_flag = os.getenv("LEGALONE_USE_AGENTQL")
            if env_flag is None:
                use_agentql = False
            else:
                use_agentql = env_flag.strip().lower() in ("1", "true", "yes", "y")
        self.use_agentql = bool(use_agentql)
        self.agentql_api_key = agentql_api_key or os.getenv("AGENTQL_API_KEY", "")
        env_require = os.getenv("LEGALONE_REQUIRE_CONTEXT")
        if env_require is None:
            self.require_context = self.use_agentql
        else:
            self.require_context = env_require.strip().lower() in ("1", "true", "yes", "y")

        if self.use_agentql and not self.agentql_api_key:
            logger.warning("[AGENTQL] Ativo, mas sem API key. Defina AGENTQL_API_KEY.")
        elif self.use_agentql:
            logger.info("[AGENTQL] Ativo para análise de contexto.")
        self.user_data_dir = os.path.join(os.getcwd(), "browser_data")
        self.fallback_user_data_dir = os.path.join(os.getcwd(), "browser_data_fallback")
        self.state_file = os.path.join(self.user_data_dir, "legalone_state.json")
        os.makedirs(self.user_data_dir, exist_ok=True)
        os.makedirs(self.fallback_user_data_dir, exist_ok=True)

        # Persistência
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._captura_em_rascunhos = False
        self._rascunho_reiniciado = False
        self._fluxo_pre_cadastro = False
        self._processo_ja_cadastrado = False
        self.last_error_reason = None
        self.temp_user_data_dir = None
        self._guardian = None
        self._guardian_recovered = False

    def _get_guardian(self):
        """Inicializa ou atualiza o Visual Guardian (lazy)."""
        if self._guardian is None and _VISUAL_GUARDIAN_DISPONIVEL:
            try:
                from claude_brain import ClaudeBrain
                from config_automacao import VISUAL_GUARDIAN_CONFIG
                if not VISUAL_GUARDIAN_CONFIG.get('habilitado', True):
                    return None
                brain = ClaudeBrain()
                cfg = VISUAL_GUARDIAN_CONFIG
                self._guardian = VisualGuardian(
                    page=self.page,
                    brain=brain,
                    max_retries=cfg.get('max_retries', 3),
                    confidence_threshold=cfg.get('confidence_threshold', 0.5),
                    max_calls_per_cadastro=cfg.get('max_calls_per_cadastro', 10),
                    vision_model=cfg.get('vision_model', 'claude-sonnet-4-20250514'),
                    log_path=cfg.get('log_path', 'guardian_log.jsonl'),
                    screenshot_dir=cfg.get('screenshot_dir', 'guardian_screenshots'),
                    dry_run=cfg.get('dry_run', False),
                )
                logger.info("[GUARDIAN] Visual Guardian inicializado")
            except Exception as e:
                logger.debug(f"[GUARDIAN] Não foi possível inicializar: {e}")
                return None
        elif self._guardian and self.page:
            self._guardian.update_page(self.page)
        return self._guardian

    def _normalizar_cnj(self, cnj: str) -> str:
        return re.sub(r"\D", "", cnj or "")

    def _esta_na_pagina_processo(self) -> bool:
        """Verifica se a URL atual corresponde a uma tela de processo (edit/details/search)."""
        try:
            url = (self.page.url or '').lower()
            return any(p in url for p in [
                '/processos/processos/edit/',
                '/processos/processos/details/',
                '/processos/processos/search',
                '/processos/processos/create',
            ])
        except Exception:
            return False

    def _verificar_estado_pagina(self, esperado: str) -> bool:
        """Verifica URL + DOM para confirmar estado da página.

        Args:
            esperado: "pesquisa_processos", "cadastro_automatico_modal",
                      "pre_cadastro", "edicao_processo", "secao_pedidos"
        """
        if not self.page:
            return False
        try:
            url = (self.page.url or "").lower()
        except Exception:
            return False

        checks = {
            "pesquisa_processos": {
                "url": ["/processos/processos/search"],
                "dom": ["input#search-box-input", "input[name='Search']"],
            },
            "cadastro_automatico_modal": {
                "url": ["/processos"],
                "dom": ["#CNJNumberAutomaticModal"],
            },
            "pre_cadastro": {
                "url": ["/processos/importer", "/draft-litigation"],
                "dom": ["form"],
            },
            "edicao_processo": {
                "url": ["/processos/processos/edit/"],
                "dom": ["button[name='ButtonSave']", "#btnSave", "form[action*='processos']"],
            },
            "secao_pedidos": {
                "url": ["/processos/processos/edit/"],
                "dom": ["#pedidos", ".pedidos-section", "ul.pedidos-list", "input[id*='NomePedidoText']"],
            },
        }

        spec = checks.get(esperado)
        if not spec:
            logger.warning(f"[ESTADO] Estado desconhecido: {esperado}")
            return False

        url_ok = any(frag in url for frag in spec["url"])
        if not url_ok:
            logger.debug(f"[ESTADO] URL nao contem {spec['url']}: {url}")
            return False

        for sel in spec["dom"]:
            try:
                el = self.page.query_selector(sel)
                if el:
                    return True
            except Exception:
                continue

        logger.debug(f"[ESTADO] DOM sem elementos esperados para '{esperado}'")
        return False

    def _garantir_pagina_processo_edicao(self, numero_processo: str) -> bool:
        """Garante que estamos na tela de edição do processo. Se não, navega via busca."""
        try:
            url = (self.page.url or '').lower()
            if '/processos/processos/edit/' in url:
                return True
            logger.warning(f"   [GUARD] URL atual não é edição de processo: {self.page.url}")
            logger.info(f"   [GUARD] Recuperando: buscando processo {numero_processo}...")
            return self._abrir_edicao_processo_por_busca(numero_processo)
        except Exception as e:
            logger.warning(f"   [GUARD] Falha na verificação de página: {e}")
            return False

    def _normalizar_texto_busca(self, valor: str | None) -> str:
        if valor is None:
            return ""
        texto = unicodedata.normalize("NFKD", str(valor))
        texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
        texto = texto.lower().strip()
        texto = "".join(ch if ch.isalnum() else " " for ch in texto)
        return " ".join(texto.split())

    def _texto_forms_invalido(self, valor) -> bool:
        valor_norm = self._normalizar_texto_busca(valor)
        if not valor_norm:
            return True
        marcadores_invalidos = (
            'nenhuma resposta fornecida',
            'texto multilinha',
            'texto de linha unica',
            'texto linha unica',
            'requer resposta',
            'obrigatoria',
            'opcao unica',
            'multipla escolha',
        )
        return any(marcador in valor_norm for marcador in marcadores_invalidos)

    def _obter_outro_dado(self, dados: dict | None, *aliases: str, permitir_parcial: bool = True) -> str | None:
        outros = (dados or {}).get("outros_dados") or {}
        if not isinstance(outros, dict) or not outros:
            return None

        aliases_norm = []
        for alias in aliases:
            alias_norm = self._normalizar_texto_busca(alias)
            if alias_norm:
                aliases_norm.append(alias_norm)
        if not aliases_norm:
            return None

        for chave, valor in outros.items():
            if self._valor_eh_placeholder(valor) or self._texto_forms_invalido(valor):
                continue
            chave_norm = self._normalizar_texto_busca(chave)
            if chave_norm in aliases_norm:
                return str(valor).strip()

        if not permitir_parcial:
            return None

        for chave, valor in outros.items():
            if self._valor_eh_placeholder(valor) or self._texto_forms_invalido(valor):
                continue
            chave_norm = self._normalizar_texto_busca(chave)
            if any(
                chave_norm.startswith(alias_norm) or alias_norm in chave_norm
                for alias_norm in aliases_norm
            ):
                return str(valor).strip()

        return None

    def _switch_to_latest_page(self) -> bool:
        if not self.context:
            return False
        try:
            paginas = [p for p in self.context.pages if p and not p.is_closed()]
            if not paginas:
                return False
            self.page = paginas[-1]
            return True
        except Exception:
            return False

    def _ensure_page_active(self) -> bool:
        if self.page and not self.page.is_closed():
            return True
        if self._switch_to_latest_page():
            return True
        return self.inicializar_navegador()

    def _aguardar_carregamento(self, timeout_ms: int = 15000) -> None:
        if not self.page:
            return
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

    def _url_para_log(self, url: str | None) -> str:
        """Remove query string sensível (ex.: JWT) para evitar vazar tokens no log."""
        if not url:
            return "N/A"
        try:
            if "?" in url:
                return url.split("?", 1)[0] + "?<redacted>"
            return url
        except Exception:
            return url

    def _iniciar_contexto_persistente(self, user_data_dir: str, headless: bool, channel: str | None = "chrome"):
        """Cria contexto persistente com opções padronizadas."""
        if not self.playwright:
            raise RuntimeError("Playwright não inicializado")

        kwargs = {
            "user_data_dir": user_data_dir,
            "headless": headless,
            "slow_mo": 100,
            "viewport": {"width": 1400, "height": 900},
            "accept_downloads": True,
            "ignore_https_errors": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # expõe a árvore de acessibilidade (AT-SPI) p/ o cua-driver no servidor
                "--force-renderer-accessibility",
            ],
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
        }
        if channel:
            kwargs["channel"] = channel

        return self.playwright.chromium.launch_persistent_context(**kwargs)

    def _erro_indica_navegador_ausente(self, erro: Exception | str | None) -> bool:
        txt = str(erro or "").lower()
        indicadores = [
            "executable doesn't exist",
            "browser executable",
            "please run",
            "playwright install",
            "failed to launch",
        ]
        return any(i in txt for i in indicadores)

    def _instalar_chromium_playwright(self) -> bool:
        """Tenta instalar o Chromium do Playwright para evitar falhas de binário ausente."""
        try:
            logger.info("[INIT] Tentando instalar Chromium do Playwright...")
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if proc.returncode == 0:
                logger.info("[INIT] Chromium do Playwright instalado com sucesso")
                return True
            primeira_linha = (proc.stderr or proc.stdout or "").splitlines()
            msg = primeira_linha[0] if primeira_linha else "erro desconhecido"
            logger.warning(f"[INIT] Falha ao instalar Chromium: {msg}")
            return False
        except Exception as e:
            logger.warning(f"[INIT] Exceção ao instalar Chromium: {e}")
            return False

    def _detectar_indicio_bloqueio(self) -> str | None:
        """Detecta sinais comuns de bloqueio/autenticação na página atual."""
        if not self.page:
            return None

        try:
            url = (self.page.url or "").lower()
        except Exception:
            url = ""

        try:
            titulo = (self.page.title() or "").lower()
        except Exception:
            titulo = ""

        corpo = ""
        try:
            corpo = (self.page.inner_text("body") or "").lower()
        except Exception:
            try:
                corpo = (self.page.content() or "").lower()
            except Exception:
                corpo = ""

        candidatos = [
            ("authentication-error" in url, "sessao expirada (authentication-error)"),
            ("access denied" in corpo or "access denied" in titulo, "access denied"),
            ("forbidden" in corpo or "403" in corpo, "acesso proibido (403/forbidden)"),
            ("unauthorized" in corpo or "401" in corpo, "nao autorizado (401/unauthorized)"),
            ("too many requests" in corpo or "429" in corpo, "limite de requisicoes (429)"),
            ("captcha" in corpo or "captcha" in titulo, "captcha detectado"),
            ("verify you are human" in corpo, "verificacao humana detectada"),
            ("cloudflare" in corpo or "akamai" in corpo, "camada anti-bot detectada"),
            ("bloqueado" in corpo or "blocked" in corpo, "pagina indica bloqueio"),
        ]

        for condicao, descricao in candidatos:
            if condicao:
                return descricao
        return None

    def _registrar_diagnostico_falha(self, etapa: str, erro: str | None = None) -> None:
        """Registra contexto de falha para facilitar diagnóstico em produção."""
        url = "N/A"
        titulo = "N/A"

        if self.page:
            try:
                url = self._url_para_log(self.page.url or "N/A")
            except Exception:
                pass
            try:
                titulo = self.page.title() or "N/A"
            except Exception:
                pass

        indicio = self._detectar_indicio_bloqueio()
        base = f"{etapa} | URL={url} | Titulo={titulo}"
        if erro:
            base = f"{base} | Erro={erro}"

        if indicio:
            self.last_error_reason = f"{base} | Indicador={indicio}"
            logger.error(f"[DIAG] {self.last_error_reason}")
        else:
            self.last_error_reason = f"{base} | Indicador=sem bloqueio explicito"
            logger.warning(f"[DIAG] {self.last_error_reason}")

        try:
            if self.page:
                os.makedirs("logs", exist_ok=True)
                nome_arquivo = f"logs/legalone_diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.page.screenshot(path=nome_arquivo, full_page=False)
                logger.info(f"[DIAG] Screenshot salva em: {nome_arquivo}")
        except Exception:
            pass

        # Visual Guardian — tentativa de recuperação automática
        guardian = self._get_guardian()
        if guardian:
            try:
                recovered = guardian.rescue(etapa, f"URL={url}, Titulo={titulo}", Exception(erro or "unknown"))
                if recovered:
                    logger.info("[GUARDIAN] Recuperação bem-sucedida!")
                    self._guardian_recovered = True
                    return
            except Exception as ge:
                logger.debug(f"[GUARDIAN] Falha na recuperação: {ge}")

    def _ler_pasta_existente(self) -> str | None:
        """Le a pasta do aviso 'ja encontra-se cadastrado' (#success-content).

        Exemplo do HTML: 'O numero X ja encontra-se cadastrado na pasta
        <a href="/processos/Processos/Details/8982">Proc - 0007349</a>.'
        Devolve "Proc - 0007349 (/processos/Processos/Details/8982)".
        """
        if not self.page:
            return None
        try:
            return self.page.evaluate(
                """() => {
                    const box = document.querySelector('#success-content') ||
                                document.querySelector('[id*="success"]');
                    if (!box) return null;
                    const a = box.querySelector('a[href*="/Processos/Details/"], a[href*="/processos/"]');
                    if (a) return `${(a.textContent || '').trim()} (${a.getAttribute('href')})`;
                    return (box.textContent || '').trim().slice(0, 200) || null;
                }"""
            )
        except Exception:
            return None

    def _clicar_ver_rascunhos_se_disponivel(self, timeout_ms: int = 2500) -> bool:
        """Clica no botão 'Ver em rascunhos' quando o modal de captura aparece."""
        if not self.page:
            return False

        seletores_rascunhos = [
            "#see-automatic-process-id",
            'button[name="see-automatic-process"]',
            'button.btn-primary:has-text("Ver em rascunhos")',
        ]

        for seletor in seletores_rascunhos:
            try:
                botao = self.page.wait_for_selector(seletor, state="visible", timeout=timeout_ms)
                if botao:
                    botao.click()
                    logger.info("   ✓ Clicou em 'Ver em rascunhos'")
                    self._aguardar_carregamento(10000)
                    time.sleep(2)
                    self._switch_to_latest_page()
                    return True
            except Exception:
                continue

        return False

    def _ir_para_pre_cadastro(self) -> bool:
        """Navega para o menu de Pré-cadastro (/draft-litigation)."""
        if not self.page:
            return False

        logger.info("📂 Navegando para 'Pré-cadastro'...")

        seletores_pre_cadastro = [
            "#menuProcessosSubmenuImporter",
            'a[href="/processos/importer"]',
            'a[href*="/processos/importer"]',
            'a[href="/draft-litigation"]',
            'a[href*="/draft-litigation"]',
            'a:has-text("Pré-cadastro")',
            'a:has-text("Pre-cadastro")',
        ]

        def _tentar_clicar_pre_cadastro(timeout_ms: int = 2500) -> bool:
            for seletor in seletores_pre_cadastro:
                try:
                    el = self.page.wait_for_selector(seletor, state="visible", timeout=timeout_ms)
                    if el:
                        el.click()
                        self._aguardar_carregamento(15000)
                        time.sleep(2)
                        self._switch_to_latest_page()
                        return True
                except Exception:
                    continue
            return False

        if _tentar_clicar_pre_cadastro(2000):
            logger.info("   ✓ Clicou em 'Pré-cadastro'")
            return True

        # Se submenu não estiver visível, abre a área de Processos/Pastas e tenta de novo
        try:
            self.page.click('a[href*="/processos/processos"], a:has-text("Pastas"), a:has-text("Processos")', timeout=4000)
            time.sleep(2)
        except Exception:
            pass

        if _tentar_clicar_pre_cadastro(4000):
            logger.info("   ✓ Clicou em 'Pré-cadastro'")
            return True

        # Fallback por rota direta
        try:
            # "commit" resolve assim que a navegacao inicia; a VM nao aguenta
            # esperar todos os recursos do LegalOne (domcontentloaded estourava)
            self.page.goto("https://carvalhofurtadoadv.novajus.com.br/processos/importer", wait_until="commit", timeout=90000)
            time.sleep(12)
            pagina_erro = False
            try:
                pagina_erro = bool(self.page.evaluate(
                    "() => /não foi encontrada|not found/i.test(document.body.innerText || '')"
                ))
            except Exception:
                pass
            if pagina_erro:
                logger.error("   Rota de Pre-cadastro retornou pagina de erro")
                return False
            if "/processos/importer" in (self.page.url or "") or "/draft-litigation" in (self.page.url or ""):
                logger.info("   ✓ Acessou 'Pré-cadastro' por rota direta")
                return True
        except Exception:
            pass

        logger.error("   âŒ Não foi possível navegar para 'Pré-cadastro'")
        return False

    _JS_MARCAR = r"""
        (maxItens) => {
          document.querySelectorAll('.__ai_badge').forEach(b => b.remove());
          const sx = window.scrollX, sy = window.scrollY;
          // marca todo elemento renderizado (inclusive abaixo da dobra) -> screenshot full_page ve tudo
          const vis = e => { const r = e.getBoundingClientRect();
            return r.width > 4 && r.height > 6 && e.offsetParent !== null; };
          const sel = 'button, a, [role="button"], [role="menuitem"], input[type="submit"], [role="option"], input:not([type="hidden"]), textarea, select, [role="combobox"], [contenteditable="true"]';
          const els = [...document.querySelectorAll(sel)].filter(vis).slice(0, maxItens);
          const out = [];
          els.forEach((e, i) => {
            e.setAttribute('data-ai-idx', String(i));
            const r = e.getBoundingClientRect();
            const b = document.createElement('div');
            b.className = '__ai_badge';
            b.textContent = String(i);
            b.style.cssText = 'position:absolute;z-index:2147483647;left:' + (r.left + sx)
              + 'px;top:' + (r.top + sy) + 'px;background:#e11;color:#fff;'
              + 'font:bold 11px monospace;padding:0 3px;border-radius:3px;pointer-events:none;';
            document.body.appendChild(b);
            out.push({ i, txt: (e.innerText || e.value || '').replace(/\s+/g, ' ').trim().slice(0, 45),
                       cx: r.left + r.width / 2, cy: r.top + r.height / 2 });
          });
          return out;
        }
    """

    def _gemini_vision(self, prompt, png_bytes):
        """Manda screenshot + prompt para o Gemini (visao) e devolve o texto."""
        key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not key:
            return None
        model = os.getenv('LEGALONE_VISION_MODEL', 'gemini-2.5-flash')
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               + model + ":generateContent?key=" + key)
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png",
                             "data": base64.b64encode(png_bytes).decode()}},
        ]}]}
        try:
            r = requests.post(url, json=body, timeout=60)
        except Exception as e:
            logger.warning("   [VISAO] Gemini erro de rede: " + str(e)[:80])
            return None
        if r.status_code != 200:
            logger.warning("   [VISAO] Gemini " + str(r.status_code) + ": " + r.text[:120])
            return self._openai_vision(prompt, png_bytes)  # reserva quando Gemini estoura cota
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return self._openai_vision(prompt, png_bytes)

    def _openai_vision(self, prompt, png_bytes):
        """Reserva de visao: GPT-4o quando o Gemini falha/estoura cota."""
        key = os.getenv('OPENAI_API_KEY')
        if not key:
            return None
        b64 = base64.b64encode(png_bytes).decode()
        body = {
            "model": os.getenv('LEGALONE_VISION_MODEL_OPENAI', 'gpt-4o'),
            "max_tokens": 300,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            ]}],
        }
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": "Bearer " + key}, json=body, timeout=60)
        except Exception as e:
            logger.warning("   [VISAO] OpenAI erro de rede: " + str(e)[:80])
            return None
        if r.status_code != 200:
            logger.warning("   [VISAO] OpenAI " + str(r.status_code) + ": " + r.text[:120])
            return None
        try:
            logger.info("   [VISAO] usando reserva GPT-4o")
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    def _agente_visual(self, objetivo, max_passos=5):
        """Agente de VISAO estilo Claude-in-Chrome: marca clicaveis com numeros,
        tira screenshot, Gemini decide qual numero clicar, e clica. Repete ate concluir."""
        if not (os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')):
            logger.warning("   [VISAO] Sem GOOGLE_API_KEY - agente visual indisponivel")
            return False
        for passo in range(max_passos):
            try:
                els = self.page.evaluate(self._JS_MARCAR, 60)
                png = self.page.screenshot(type='png', full_page=True)
            except Exception as e:
                logger.warning("   [VISAO] Falha ao observar: " + str(e)[:80])
                return False
            if not els:
                return False
            legenda = "\n".join('[' + str(e["i"]) + '] ' + e["txt"] for e in els)
            prompt = (
                "Voce opera a tela do sistema juridico LegalOne clicando. Na imagem, cada "
                "elemento clicavel tem um numero vermelho no canto superior esquerdo.\n"
                "NUNCA clique na barra de navegacao do topo (Home, Contatos, Agenda, Publicacoes, "
                "Processos, Servicos, GED, Conteudo juridico, Time sheet, Legal Analytics, Opcoes) "
                "nem em Pesquisar - eles saem do fluxo. Foque no card e no menu do processo.\n"
                "OBJETIVO: " + objetivo + "\n\nLegenda (numero -> texto):\n" + legenda + "\n\n"
                "Escolha o proximo clique. Responda SOMENTE com JSON: "
                '{"i": N} para clicar no numero N; '
                '{"fim": true} se o objetivo JA foi cumprido (ex.: formulario de cadastro abriu); '
                '{"i": -1} se nenhum serve.'
            )
            resp = self._gemini_vision(prompt, png)
            try:
                self.page.evaluate("document.querySelectorAll('.__ai_badge').forEach(b => b.remove())")
            except Exception:
                pass
            if not resp:
                return False
            try:
                m = re.search(r'\{[^{}]*\}', resp)
                d = json.loads(m.group(0)) if m else {}
            except Exception:
                logger.warning("   [VISAO] resposta invalida: " + resp[:80])
                return False
            if d.get('fim'):
                logger.info("   [VISAO] Gemini sinalizou FIM no passo " + str(passo + 1))
                return True
            idx = d.get('i', -1)
            if idx is None or idx < 0:
                logger.info("   [VISAO] Gemini nao achou elemento (passo " + str(passo + 1) + ")")
                return False
            alvo = next((e for e in els if e['i'] == idx), None)
            logger.info("   [VISAO] passo " + str(passo + 1) + ": clicar [" + str(idx) + "] '"
                        + (alvo['txt'] if alvo else '?') + "'")
            try:
                self.page.click('[data-ai-idx="' + str(idx) + '"]', timeout=6000)
            except Exception:
                if alvo:
                    try:
                        self.page.mouse.click(alvo['cx'], alvo['cy'])
                    except Exception as e:
                        logger.warning("   [VISAO] clique falhou: " + str(e)[:60])
            time.sleep(5)
        logger.info("   [VISAO] max de passos atingido")
        return True

    def _preencher_campo_visual(self, label, valor, criar=False):
        """Preenche um campo via VISAO: Gemini localiza o campo pelo rotulo, digita o valor,
        e escolhe a opcao do dropdown (ou clica 'Adicionar' para criar contato novo)."""
        if not (os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')) or not valor:
            return False

        def _idx(txt):
            try:
                m = re.search(r'\{[^{}]*\}', txt or '')
                return json.loads(m.group(0)) if m else {}
            except Exception:
                return {}

        # 1) localizar o campo pelo rotulo
        try:
            els = self.page.evaluate(self._JS_MARCAR, 90)
            png = self.page.screenshot(type='png', full_page=True)
        except Exception as e:
            logger.warning("   [VISAO-FILL] observar falhou: " + str(e)[:70])
            return False
        try:
            self.page.evaluate("document.querySelectorAll('.__ai_badge').forEach(b => b.remove())")
        except Exception:
            pass
        if not els:
            return False
        legenda = "\n".join('[' + str(e["i"]) + '] ' + e["txt"] for e in els)
        p1 = ("Na imagem, cada campo tem um numero vermelho no canto. Qual numero e o CAMPO DE "
              "ENTRADA (input/combobox) rotulado '" + label + "'? Responda SO JSON {\"i\": N} "
              "ou {\"i\": -1} se nao existir.\n\nLegenda:\n" + legenda)
        try:
            with open('debug_visaofill_' + re.sub(r'\W+','_', label)[:20] + '.png', 'wb') as _f:
                _f.write(png)
        except Exception:
            pass
        d = _idx(self._gemini_vision(p1, png))
        idx = d.get('i', -1)
        if idx is None or idx < 0:
            logger.info("   [VISAO-FILL] campo '" + label + "' nao localizado")
            return False
        alvo = next((e for e in els if e['i'] == idx), None)

        # 2) clicar, limpar, digitar
        try:
            self.page.click('[data-ai-idx="' + str(idx) + '"]', timeout=6000)
        except Exception:
            if alvo:
                try:
                    self.page.mouse.click(alvo['cx'], alvo['cy'])
                except Exception:
                    return False
        try:
            self.page.keyboard.press('Control+A')
            self.page.keyboard.press('Delete')
            self.page.keyboard.type(str(valor)[:60], delay=45)
        except Exception:
            pass
        time.sleep(3)

        # 3) escolher a opcao do dropdown (ou criar contato)
        try:
            els2 = self.page.evaluate(self._JS_MARCAR, 90)
            png2 = self.page.screenshot(type='png', full_page=True)
        except Exception:
            return True
        try:
            self.page.evaluate("document.querySelectorAll('.__ai_badge').forEach(b => b.remove())")
        except Exception:
            pass
        leg2 = "\n".join('[' + str(e["i"]) + '] ' + e["txt"] for e in els2)
        extra = (" Se NENHUMA opcao casar com o nome e houver um botao 'Adicionar' ou 'Criar' para "
                 "cadastrar um contato novo, clique nele." if criar else "")
        p2 = ("O campo '" + label + "' foi preenchido com '" + str(valor) + "' e deve ter aberto um "
              "dropdown de opcoes. Clique na opcao que casa EXATAMENTE com '" + str(valor) + "'." + extra
              + " Responda SO JSON: {\"i\": N} para clicar; {\"fim\": true} se ja esta selecionado "
              "corretamente; {\"i\": -1} se nao ha o que fazer.\n\nLegenda:\n" + leg2)
        d2 = _idx(self._gemini_vision(p2, png2))
        if d2.get('fim'):
            return True
        i2 = d2.get('i', -1)
        if i2 is not None and i2 >= 0:
            alvo2 = next((e for e in els2 if e['i'] == i2), None)
            logger.info("   [VISAO-FILL] '" + label + "' -> opcao [" + str(i2) + "] '"
                        + (alvo2['txt'] if alvo2 else '?') + "'")
            try:
                self.page.click('[data-ai-idx="' + str(i2) + '"]', timeout=6000)
                time.sleep(2)
            except Exception:
                if alvo2:
                    try:
                        self.page.mouse.click(alvo2['cx'], alvo2['cy'])
                    except Exception:
                        pass
            # se abriu modal de criacao de contato, preenche pelo fluxo existente
            try:
                if criar and self._alerta_contato_exige_adicao_manual is not None:
                    pass
            except Exception:
                pass
        return True

    def _continuar_preenchimento_rascunho(self, cnj: str) -> bool:
        """Reabre o rascunho para continuar: agente de VISAO clica Editar > Continuar preenchimento.
        Pre-cadastro abre no filtro 'Sucesso' (onde o processo fica), entao nao precisa alternar filtros."""
        if not self._ir_para_pre_cadastro():
            return False
        time.sleep(6)

        # 1a opcao: cua-driver (UIA) clica Editar do CNJ e 'Continuar com o preenchimento'
        # deterministico, sem LLM, sem cota de visao
        try:
            import cua_win
            if cua_win.disponivel() and cua_win.clicar_editar_do_cnj(cnj):
                time.sleep(3)
                cua_win.clicar_label('continuar com o preenchimento') or cua_win.clicar_label('continuar')
                time.sleep(5)
                self._switch_to_latest_page()
                if 'draft-litigation/main' not in (self.page.url or ''):
                    logger.info(f"   [RASCUNHO] Formulario reaberto via cua: {self.page.url[:80]}")
                    return True
        except Exception as e:
            logger.warning(f"   [CUA] navegacao rascunho falhou: {str(e)[:80]}")

        # reserva: visao Gemini (se tiver cota). Nao gate no retorno: a fonte da verdade
        # e ter saido da lista de Pre-cadastro (o form abre na aba Processos/Pasta)
        objetivo = (
            f"Na lista de Pre-cadastro, reabrir para continuar o cadastro o processo de numero {cnj}. "
            "No card desse processo, clicar no botao 'Editar' (titulo 'Editar processo') e no menu "
            "clicar 'Continuar com o preenchimento'."
        )
        self._agente_visual(objetivo, max_passos=6)
        time.sleep(3)
        self._switch_to_latest_page()
        if 'draft-litigation/main' not in (self.page.url or ''):
            logger.info(f"   [RASCUNHO] Formulario reaberto: {self.page.url[:80]}")
            return True
        # fallback: clicar o botao direto (texto varia: 'Continuar com o preenchimento')
        for seletor in ('a:has-text("Continuar")', 'button:has-text("Continuar")'):
            try:
                el = self.page.wait_for_selector(seletor, state='visible', timeout=4000)
                if el:
                    el.click(); time.sleep(6); self._switch_to_latest_page()
                    return 'draft-litigation/main' not in (self.page.url or '')
            except Exception:
                continue
        return 'draft-litigation/main' not in (self.page.url or '')

    def _excluir_rascunho(self, cnj: str) -> bool:
        """Exclui o rascunho (AÇÃO DESTRUTIVA, opt-in). Agente de VISAO clica Excluir e confirma."""
        if os.getenv('LEGALONE_EXCLUIR_RASCUNHO', '').strip().lower() not in ('1', 'true', 'sim'):
            logger.info("   [RASCUNHO] Exclusao desativada (LEGALONE_EXCLUIR_RASCUNHO)")
            return False
        if not self._ir_para_pre_cadastro():
            return False
        time.sleep(6)
        objetivo = (
            f"Na lista de Pre-cadastro, excluir o processo de numero {cnj}: clicar no botao 'Excluir' "
            "(titulo 'Excluir processo') do card desse processo e confirmar na caixa de dialogo."
        )
        return self._agente_visual(objetivo, max_passos=6)

    def _clicar_continuar_cadastro_popup(self) -> bool:
        """Tenta clicar em 'Continuar cadastro' no pop-up que aparece após 'Pular etapa'.

        Este é o fluxo preferido: ao invés de fechar o popup e navegar
        para Pré-cadastro (que pode dar 'página não encontrada'), clica
        em 'Continuar cadastro' que leva direto ao formulário de edição.
        """
        if not self.page:
            return False

        logger.info("   ðŸ” Procurando 'Continuar cadastro' no pop-up...")

        seletores_continuar_popup = [
            'button:has-text("Continuar cadastro")',
            'a:has-text("Continuar cadastro")',
            'button.btn-primary:has-text("Continuar")',
            '#continue-button-id',
            'button[name="continue-button"]',
        ]

        for seletor in seletores_continuar_popup:
            try:
                botao = self.page.wait_for_selector(seletor, state='visible', timeout=3000)
                if botao:
                    botao.click()
                    logger.info("   ✓ Clicou em 'Continuar cadastro' no pop-up")
                    self._aguardar_carregamento(15000)
                    time.sleep(2)
                    self._switch_to_latest_page()
                    return True
            except Exception:
                continue

        # Fallback via JavaScript
        try:
            clicou = self.page.evaluate(
                """
                () => {
                    const btn = Array.from(document.querySelectorAll('button, a')).find(b => {
                        const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                        return t === 'continuar cadastro' || t === 'continuar';
                    });
                    if (btn) { btn.click(); return true; }
                    return false;
                }
                """
            )
            if clicou:
                logger.info("   ✓ Clicou em 'Continuar cadastro' via JavaScript")
                self._aguardar_carregamento(15000)
                time.sleep(2)
                self._switch_to_latest_page()
                return True
        except Exception:
            pass

        # Fallback via _click_by_text
        if self._click_by_text(["continuar cadastro"]):
            logger.info("   ✓ Clicou em 'Continuar cadastro' via crawler de texto")
            self._aguardar_carregamento(15000)
            time.sleep(2)
            self._switch_to_latest_page()
            return True

        logger.info("   ℹ 'Continuar cadastro' não encontrado no pop-up")
        return False

    def _fechar_popup_pos_pular_etapa(self) -> bool:
        """Fecha o pop-up após clicar em 'Pular etapa' (ícone i-Close-2).

        ATENÇÃO: só deve ser chamado se 'Continuar cadastro' não estiver disponível.
        """
        if not self.page:
            return False

        seletores_fechar = [
            '.close-button > span.i-Close-2',
            'span.i-Close-2',
            '.header .close-button',
            '.modal .close-button',
        ]

        for seletor in seletores_fechar:
            try:
                btn = self.page.wait_for_selector(seletor, state='visible', timeout=2000)
                if btn:
                    btn.click()
                    logger.info("   ✓ Pop-up fechado (i-Close-2)")
                    time.sleep(1)
                    return True
            except Exception:
                continue

        try:
            clicou = self.page.evaluate(
                """
                () => {
                    const el = document.querySelector('.close-button > span.i-Close-2')
                        || document.querySelector('span.i-Close-2')
                        || document.querySelector('.header .close-button')
                        || document.querySelector('.modal .close-button');
                    if (el) { el.click(); return true; }
                    return false;
                }
                """
            )
            if clicou:
                logger.info("   ✓ Pop-up fechado via JavaScript")
                time.sleep(1)
                return True
        except Exception:
            pass

        logger.info("   ℹ Pop-up de fechamento não encontrado após 'Pular etapa'")
        return False

    def _clicar_continuar_cadastro_fallback(self) -> bool:
        """Fallback legado: tenta clicar em 'Continuar cadastro' quando não há 'Pular etapa'."""
        if not self.page:
            return False

        seletores_continuar = [
            '#continue-button-id',
            'button[name="continue-button"]',
            'button:has-text("Continuar cadastro")',
            'button.btn-primary:has-text("Continuar")',
        ]

        for seletor in seletores_continuar:
            try:
                botao = self.page.wait_for_selector(seletor, state='visible', timeout=3000)
                if botao:
                    botao.click()
                    logger.info("   ✓ Fallback: clicou em 'Continuar cadastro'")
                    self._aguardar_carregamento(15000)
                    time.sleep(2)
                    self._switch_to_latest_page()
                    return True
            except Exception:
                continue

        try:
            clicou = self.page.evaluate(
                """
                () => {
                    const btn = document.querySelector('#continue-button-id')
                        || document.querySelector('button[name="continue-button"]')
                        || Array.from(document.querySelectorAll('button, a')).find(b => {
                            const t = (b.innerText || '').toLowerCase();
                            return t.includes('continuar cadastro') || t === 'continuar';
                        });
                    if (btn) { btn.click(); return true; }
                    return false;
                }
                """
            )
            if clicou:
                logger.info("   ✓ Fallback: clicou em 'Continuar cadastro' via JavaScript")
                self._aguardar_carregamento(15000)
                time.sleep(2)
                self._switch_to_latest_page()
                return True
        except Exception:
            pass

        if self._click_by_text(["continuar cadastro", "continuar", "avançar", "avancar"]):
            logger.info("   ✓ Fallback: clicou em 'Continuar cadastro' via texto")
            self._aguardar_carregamento(15000)
            time.sleep(2)
            self._switch_to_latest_page()
            return True

        return False

    def _click_by_text(self, textos: list[str]) -> bool:
        if not self.page:
            return False
        textos = [t.lower() for t in textos if t]
        if not textos:
            return False

        try:
            clicou = self.page.evaluate(
                """
                (texts) => {
                    const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                    for (const el of candidates) {
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (!txt) continue;
                        if (texts.some(t => txt.includes(t))) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """,
                textos,
            )
            return bool(clicou)
        except Exception:
            return False

    def _encontrar_input_por_label_exato(self, label_text: str) -> str | None:
        """Encontra o seletor CSS de um input associado a um label pelo texto exato.

        Usa o atributo 'for' do label para localizar o input correto,
        evitando preencher o campo errado quando há labels similares
        (ex: 'Responsável principal' vs 'Escritório responsável').
        Retorna o seletor '#id' do input ou None.
        """
        if not self.page or not label_text:
            return None
        try:
            input_id = self.page.evaluate(
                """
                (labelText) => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    // Busca label cujo texto "limpo" corresponde exatamente
                    const normalizar = (t) => (t || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[\\s*:]+/g, ' ').trim().toLowerCase();
                    const alvo = normalizar(labelText);

                    // Prioridade 1: match exato
                    let target = labels.find(l => normalizar(l.innerText) === alvo);

                    // Prioridade 2: label começa com o texto (ex: "Responsável principal *")
                    if (!target) {
                        target = labels.find(l => normalizar(l.innerText).startsWith(alvo));
                    }

                    if (!target) return null;

                    // Pega o id do input via atributo 'for'
                    const forId = target.getAttribute('for');
                    if (forId) {
                        const input = document.querySelector('#' + CSS.escape(forId));
                        if (input) return '#' + CSS.escape(forId);
                        // Tenta buscar input dentro do container com id similar
                        const inputCombo = document.querySelector('#' + CSS.escape(forId) + '-input');
                        if (inputCombo) return '#' + CSS.escape(forId) + '-input';
                    }

                    // Fallback: busca input no próximo sibling ou dentro do parent
                    const container = target.closest('.form-group, .field-group, .bento-form-group, [class*="form"]');
                    if (container) {
                        const input = container.querySelector('input');
                        if (input && input.id) return '#' + CSS.escape(input.id);
                    }

                    return null;
                }
                """,
                label_text,
            )
            if input_id:
                logger.debug(f"   ðŸ·ï¸ Label \"{label_text}\" → seletor: {input_id}")
            return input_id
        except Exception as e:
            logger.debug(f"   Erro ao buscar input por label \"{label_text}\": {e}")
            return None

    def _resolver_seletor_por_label(self, label_text: str) -> str | None:
        """Retorna o seletor CSS do input associado a um label pelo texto.

        Usa formato [id="..."] ao invés de #id para evitar erros com IDs
        que começam com número (UUID).
        """
        if not self.page or not label_text:
            return None
        try:
            input_id = self.page.evaluate(
                """
                (labelText) => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const target = labels.find(l =>
                        (l.innerText || '').toLowerCase().includes(labelText.toLowerCase())
                    );
                    if (!target) return null;
                    const forId = target.getAttribute('for');
                    if (forId) return '[id="' + forId + '"]';
                    const input = target.querySelector('input, textarea, select');
                    if (input && input.id) return '[id="' + input.id + '"]';
                    return null;
                }
                """,
                label_text,
            )
            return input_id
        except Exception:
            return None

    def _fill_by_label(self, label_text: str, valor: str) -> bool:
        if not self.page or not label_text or valor is None:
            return False
        try:
            return bool(
                self.page.evaluate(
                    """
                    (args) => {
                        const [labelText, value] = args;
                        const labels = Array.from(document.querySelectorAll('label'));
                        const target = labels.find(l => (l.innerText || '').toLowerCase().includes(labelText.toLowerCase()));
                        if (!target) return false;

                        let input = null;
                        const forId = target.getAttribute('for');
                        if (forId) {
                            input = document.querySelector('#' + CSS.escape(forId));
                        }
                        if (!input) {
                            input = target.querySelector('input, textarea, select');
                        }
                        if (!input && target.nextElementSibling) {
                            input = target.nextElementSibling.querySelector('input, textarea, select');
                        }
                        if (!input) return false;

                        input.focus();
                        input.value = '';
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    """,
                    [label_text, valor],
                )
            )
        except Exception:
            return False

    def _preencher_previsao_e_resultado(self, dados_processo: dict | None) -> bool:
        """Preenche previsão e resultado após os pedidos, quando informados.

        ``probabilidade`` (Êxito/Perda) e ``grau_probabilidade``
        (Provável/Possível/Remota) são campos distintos no LegalOne e não
        devem ser usados como alternativas um do outro.
        """
        dados = dados_processo or {}
        outros = dados.get('outros_dados') or {}

        def obter(campo: str) -> str:
            valor = self._valor_limpo(dados.get(campo) or outros.get(campo))
            if self._normalizar_texto_busca(valor) in {
                'nao localizado',
                'nao informada',
                'nao informado',
                'n a',
                'na',
            }:
                return ''
            return valor

        campos_lista = (
            ('Contingência', obter('contingencia')),
            ('Probabilidade atual', obter('probabilidade')),
            ('Faixa de probabilidade atual', obter('grau_probabilidade')),
            ('Risco', obter('risco')),
            ('Tipo de resultado', obter('tipo_resultado')),
            ('Resultado', obter('resultado')),
        )
        campos_texto = (
            ('Motivo do resultado', obter('motivo_resultado')),
        )
        data_resultado = self._normalizar_data_legalone(obter('data_resultado'))

        if not any(valor for _, valor in campos_lista + campos_texto) and not data_resultado:
            logger.info('   ℹ️ Previsão/resultado não informados; pulando etapa.')
            return True

        logger.info('4b️⃣ Preenchendo previsão e resultado...')
        falhas = []

        for label, valor in campos_lista:
            if not valor:
                continue
            seletor = self._encontrar_input_por_label_exato(label)
            preencheu = False
            if seletor:
                preencheu = self.preencher_campo_autocomplete(
                    seletor,
                    valor,
                    label,
                    permitir_adicionar=False,
                )
            if not preencheu:
                preencheu = self._fill_by_label(label, valor)
            if preencheu:
                logger.info(f'   ✓ {label}: {valor}')
            else:
                logger.warning(f'   ⚠️ Campo de previsão/resultado não encontrado: {label}')
                falhas.append(label)

        for label, valor in campos_texto:
            if not valor:
                continue
            if self._fill_by_label(label, valor):
                logger.info(f'   ✓ {label} preenchido')
            else:
                logger.warning(f'   ⚠️ Campo de previsão/resultado não encontrado: {label}')
                falhas.append(label)

        if data_resultado:
            if self._fill_by_label('Data do resultado', data_resultado):
                logger.info(f'   ✓ Data do resultado: {data_resultado}')
            else:
                logger.warning('   ⚠️ Campo de previsão/resultado não encontrado: Data do resultado')
                falhas.append('Data do resultado')

        if falhas:
            self.last_error_reason = (
                'Previsão/resultado informado, mas não preenchido no LegalOne: '
                + ', '.join(falhas)
            )
            return False
        return True

    # -------------------------------------------------------------------
    # Bento-combobox: dropdown grid do LegalOne
    # -------------------------------------------------------------------
    def _calcular_similaridade(self, texto1: str, texto2: str) -> float:
        """Calcula similaridade entre dois textos (0.0 a 1.0) usando SequenceMatcher."""
        # Sem tirar acento, 'Itau' (dado) casa melhor com a grafia capturada
        # 'Itau Unibanco S.A' do que com 'Itau Unibanco S.A.' da base — e o
        # contato errado ganhava por 2 pontos.
        _sa = lambda t: unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode()
        t1 = re.sub(r'[^\w\s]', '', _sa(texto1).lower().strip())
        t2 = re.sub(r'[^\w\s]', '', _sa(texto2).lower().strip())
        if not t1 or not t2:
            return 0.0
        return difflib.SequenceMatcher(None, t1, t2).ratio()

    def _valor_eh_placeholder(self, valor) -> bool:
        """Retorna True para valores vazios ou placeholders comuns."""
        if valor is None:
            return True
        txt = str(valor).strip()
        if not txt:
            return True
        txt_norm = re.sub(r'\s+', ' ', txt.lower())
        placeholders = {
            "nenhuma resposta fornecida",
            "não informado",
            "nao informado",
            "não informada",
            "nao informada",
            "n/a",
            "na",
            "-",
            "--",
            "null",
            "none",
            "undefined",
        }
        if txt_norm in placeholders:
            return True
        return self._texto_forms_invalido(txt_norm)

    def _valor_limpo(self, valor) -> str | None:
        if self._valor_eh_placeholder(valor):
            return None
        return str(valor).strip()

    @staticmethod
    def _sim_ou_nao(valor) -> str:
        """Campo so aceita Sim/Nao: qualquer outra coisa (inclusive 'NAO LOCALIZADO') vira Nao."""
        txt = unicodedata.normalize('NFD', str(valor or '')).lower()
        txt = ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()
        return 'Sim' if txt in ('sim', 's', 'true', '1', 'yes') else 'Não'

    @staticmethod
    def _nome_parte(valor) -> str:
        """Nome da parte como no Forms: sem anotacao de papel, so a parte principal.

        'Katia Bela dos Santos Souza (Reclamante/Autora)' -> 'Katia Bela dos Santos Souza'
        'Steel Ltda (Reclamado); Auristela; Rita'          -> 'Steel Ltda'
        A extracao por IA anexa papel/lista de partes; o campo do LegalOne aceita um nome so.
        """
        txt = str(valor or '')
        txt = txt.split(';')[0]
        txt = re.sub(r'\([^)]*\)', ' ', txt)          # (Reclamante/Autora)
        txt = re.sub(r'\s+[-–]\s+.*$', '', txt)       # " - Reclamado"
        txt = re.sub(r'[,\s]+$', '', txt)
        return re.sub(r'\s{2,}', ' ', txt).strip()

    def _resolver_tipo_pessoa(self, nome: str, documento: str | None, tipo_preferido: str | None) -> str:
        """Resolve PF/PJ com base no documento; sem documento, usa preferência/heurística.

        Prioridade: documento (CPF=PF, CNPJ=PJ) > tipo_preferido > heurística de nome.
        Heurística: se o nome tem marcadores empresariais → PJ, senão → PF.
        """
        digitos = re.sub(r'\D', '', documento or '')
        if len(digitos) == 11:
            return "Pessoa Fisica"
        if len(digitos) == 14:
            return "Pessoa Juridica"
        if tipo_preferido and not self._valor_eh_placeholder(tipo_preferido):
            tipo_norm = str(tipo_preferido).strip().lower()
            if tipo_norm in ("pessoa fisica", "pessoa física"):
                return "Pessoa Fisica"
            if tipo_norm in ("pessoa juridica", "pessoa jurídica"):
                return "Pessoa Juridica"

        nome_l = (nome or "").lower().strip()
        # Marcadores que indicam PJ
        marcadores_pj = [
            "ltda", "s/a", " sa ", "eireli", " mei ", " me ",
            "empresa", "banco", "associacao", "associação",
            "cooperativa", "fundação", "fundacao", "instituto",
            "prefeitura", "municipio", "município", "estado de ",
            "união", "uniao", "companhia", "cia ", "cia.",
            "comércio", "comercio", "indústria", "industria",
            "servicos", "serviços", "group", "holding",
            "distribuidora", "transportes", "construtora",
            "incorporadora", "financeira", "seguros", "seguradora",
        ]
        if any(m in nome_l for m in marcadores_pj):
            return "Pessoa Juridica"

        # Se não tem marcador PJ e parece nome de pessoa → PF
        # Nomes de pessoas normalmente têm 2+ palavras sem marcadores PJ
        palavras = nome_l.split()
        if len(palavras) >= 2:
            return "Pessoa Fisica"

        # Nome com 1 palavra é ambíguo → assume PF (mais comum em processos trabalhistas)
        return "Pessoa Fisica"

    def _extrair_opcoes_bento_combobox(self) -> list[dict]:
        """Extrai as opções visíveis do dropdown bento-combobox grid."""
        if not self.page:
            return []
        try:
            return self.page.evaluate(
                """
                () => {
                    const rows = document.querySelectorAll(
                        '.bento-list-row.bui-bento-combobox-container-item, ' +
                        '.bento-list-row.bento-combobox-container-item'
                    );
                    return Array.from(rows).map((row, idx) => {
                        const cells = row.querySelectorAll('.bento-list-cell');
                        return {
                            index: idx,
                            id: row.id || '',
                            cpf_cnpj: (cells[0]?.innerText || '').trim(),
                            nome: (cells[1]?.innerText || '').trim(),
                            origem: (cells[2]?.innerText || '').trim(),
                            // Fallback: se tem menos de 3 colunas, tenta pegar todo o texto
                            texto_completo: (row.innerText || '').trim(),
                        };
                    });
                }
                """
            )
        except Exception as e:
            logger.debug(f"Erro ao extrair opções bento-combobox: {e}")
            return []

    def _normalizar_documento(self, doc: str | None) -> str:
        """Remove formatação de CPF/CNPJ, retornando apenas dígitos."""
        if not doc:
            return ''
        return re.sub(r'\D', '', str(doc).strip())

    def _gerar_variantes_nome(self, nome: str) -> list[str]:
        """Gera variantes progressivamente mais curtas/genéricas de um nome.

        Ex: 'Banco Bradesco Financiamentos S/A'
          -> ['Banco Bradesco Financiamentos', 'Banco Bradesco', 'Bradesco']

        Útil quando o nome completo não tem match no autocomplete do LegalOne.
        """
        if not nome:
            return []

        # Sufixos empresariais a remover na primeira simplificação
        sufixos = [
            r'\s*[-–—]\s*em\s+recupera[çc][aã]o\s+judicial',
            r'\s*[-–—]\s*em\s+liquida[çc][aã]o',
            r'\s*\b(s[./]?a\.?|ltda\.?|me\.?|mei\.?|eireli|epp|s\.?c\.?)\b',
            r'\s*[-–—]{2,}.*$',
        ]

        variantes = []
        nome_limpo = nome.strip()

        # Variante 1: remove sufixos empresariais
        sem_sufixo = nome_limpo
        for sufixo in sufixos:
            sem_sufixo = re.sub(sufixo, '', sem_sufixo, flags=re.IGNORECASE).strip()
        sem_sufixo = re.sub(r'\s+', ' ', sem_sufixo).strip().rstrip(',').strip()
        if sem_sufixo and sem_sufixo.lower() != nome_limpo.lower():
            variantes.append(sem_sufixo)

        # Variante 2+: remove palavra por palavra do final
        palavras = sem_sufixo.split() if sem_sufixo else nome_limpo.split()
        while len(palavras) > 1:
            palavras = palavras[:-1]
            candidato = ' '.join(palavras).strip()
            # Evita variantes muito curtas (< 3 chars) ou com 1 palavra genérica
            if len(candidato) < 3:
                break
            # Não repete
            if candidato.lower() != nome_limpo.lower() and candidato not in variantes:
                variantes.append(candidato)

        # Remove duplicatas preservando ordem
        vistos = set()
        resultado = []
        for v in variantes:
            vl = v.lower()
            if vl not in vistos:
                vistos.add(vl)
                resultado.append(v)

        return resultado

    def _gerar_variantes_busca(self, valor: str) -> list[str]:
        """Gera variações semânticas simples para melhorar o match no autocomplete.

        Exemplos:
          - Reclamado <-> Reclamada
          - Autor <-> Autora
          - Réu <-> Ré
        """
        if not valor:
            return []

        original = str(valor).strip()
        if not original:
            return []

        def _aplicar_caixa(base: str, modelo: str) -> str:
            if modelo.isupper():
                return base.upper()
            if modelo.istitle():
                return base.title()
            return base

        variantes: list[str] = []
        vistos: set[str] = set()

        def _add(v: str):
            vv = (v or '').strip()
            if not vv:
                return
            key = vv.lower()
            if key == original.lower() or key in vistos:
                return
            vistos.add(key)
            variantes.append(vv)

        substituicoes_exatas = {
            'reclamado': 'reclamada',
            'reclamada': 'reclamado',
            'autor': 'autora',
            'autora': 'autor',
            'reu': 're',
            'réu': 'ré',
            're': 'reu',
            'ré': 'réu',
            'executado': 'executada',
            'executada': 'executado',
        }

        original_lower = original.lower()

        # Variações específicas para termos conhecidos do LegalOne
        variantes_especificas: dict[str, list[str]] = {
            'pro bono': ['Pro Bono', 'Pró bono', 'Pró Bono', 'pro-bono', 'Pro-Bono', 'probono', 'pro'],
            'pró bono': ['Pro Bono', 'Pro bono', 'Pró Bono', 'pro'],
            'sim': ['Sim', 'SIM', 'sim'],
            'nao': ['Não', 'NAO', 'não'],
            'não': ['Nao', 'NAO', 'nao'],
        }
        for key, alts in variantes_especificas.items():
            if original_lower == key:
                for alt in alts:
                    _add(alt)
        if original_lower in substituicoes_exatas:
            _add(_aplicar_caixa(substituicoes_exatas[original_lower], original))

        # Também tenta substituir a última palavra (útil para nomes compostos)
        palavras = original.split()
        if palavras:
            ultima = palavras[-1]
            ultima_lower = ultima.lower()
            if ultima_lower in substituicoes_exatas:
                nova = palavras[:-1] + [_aplicar_caixa(substituicoes_exatas[ultima_lower], ultima)]
                _add(' '.join(nova))

            # Fallback genérico de gênero para termos em -o/-a, -ado/-ada, -ido/-ida
            trocas_sufixo = [
                ('ado', 'ada'), ('ada', 'ado'),
                ('ido', 'ida'), ('ida', 'ido'),
                ('o', 'a'), ('a', 'o'),
            ]
            # À-ÿ = letras acentuadas; escapes evitam corromper o range se o
            # arquivo sofrer re-encoding (o range literal ja quebrou uma vez em producao)
            ultima_limpa = re.sub(r'[^\wÀ-ÿ-]', '', ultima, flags=re.UNICODE)
            ultima_limpa_lower = ultima_limpa.lower()
            for origem, destino in trocas_sufixo:
                if len(ultima_limpa_lower) > len(origem) + 2 and ultima_limpa_lower.endswith(origem):
                    base = ultima_limpa_lower[:-len(origem)] + destino
                    palavra_trocada = _aplicar_caixa(base, ultima_limpa)
                    _add(' '.join(palavras[:-1] + [palavra_trocada]))

        return variantes

    def _selecionar_melhor_opcao_combobox(self, valor_desejado: str, opcoes: list[dict],
                                          limiar: float = 0.45,
                                          documento_referencia: str | None = None,
                                          valor_original: str | None = None) -> dict | None:
        """Encontra a opção mais próxima do valor desejado usando fuzzy matching.

        Prioriza: match exato > contém > similaridade.
        Quando há homônimos (múltiplas opções com nomes muito similares),
        usa o CPF/CNPJ para desambiguar, depois tenta desambiguar pela
        similaridade com ``valor_original`` (nome completo antes de gerar
        variantes), e só então recorre à origem preferida.
        Retorna None se nenhuma opção atinge o limiar.
        """
        if not opcoes or not valor_desejado:
            return None

        val_lower = valor_desejado.lower().strip()
        val_clean = re.sub(r'[^\w\s]', '', val_lower)
        doc_ref = self._normalizar_documento(documento_referencia)

        # Catalogo: procura o valor em QUALQUER coluna da linha e exige texto literal.
        # A ordem das colunas muda de um combobox para outro (na grade de honorarios
        # a descricao ora e' a coluna 0, ora a 1), entao mapear por indice erra.
        # Havendo mais de uma linha (ex.: varios contratos 'Pro bono', um por
        # cliente), desempata pelo cliente do processo; sem desempate, recusa.
        if getattr(self, '_match_por_linha_inteira', False):
            def _norm(t):
                t = unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode()
                return re.sub(r'\s+', ' ', t).strip().lower()

            alvo = _norm(valor_desejado)
            achados = [o for o in opcoes if alvo and alvo in _norm(o.get('texto_completo'))]
            if not achados:
                logger.info(f"      ⚠ Nenhuma linha contem \"{valor_desejado}\" — nao vou escolher nada")
                return None
            if len(achados) > 1:
                cliente = _norm(getattr(self, '_cliente_ref', '') or '')
                por_cliente = [o for o in achados
                               if cliente and cliente in _norm(o.get('texto_completo'))]
                if len(por_cliente) == 1:
                    logger.info(f"      🎯 \"{valor_desejado}\" do cliente desambiguado")
                    return por_cliente[0]
                logger.warning(
                    f"      ⚠ {len(achados)} linhas com \"{valor_desejado}\" e nenhuma casa o "
                    f"cliente {getattr(self, '_cliente_ref', None)!r} — deixando vazio para conferencia"
                )
                return None
            return achados[0]

        # --- Fase 1: calcular scores de todas as opções ---
        candidatos = []  # lista de (opcao, score)

        for opcao in opcoes:
            nome = (opcao.get('nome') or opcao.get('texto_completo') or '').strip()
            if not nome:
                continue
            if self._valor_eh_placeholder(nome):
                continue
            if nome.lower() in ("adicionar", "novo", "novo contato", "add"):
                continue
            nome_lower = nome.lower()
            nome_clean = re.sub(r'[^\w\s]', '', nome_lower)

            # Match exato
            if val_clean == nome_clean:
                score = 1.0
            elif val_clean in nome_clean or nome_clean in val_clean:
                score = 0.85
            else:
                score = self._calcular_similaridade(val_clean, nome_clean)

            # Também compara com col0 (cpf_cnpj) quando não for CPF/CNPJ real.
            # Grids como Honorários têm: col0=NomeNegociação, col1=Tipo, col2=Status.
            col0 = (opcao.get('cpf_cnpj') or '').strip()
            if col0 and len(re.sub(r'\D', '', col0)) < 5:
                col0_clean = re.sub(r'[^\w\s]', '', col0.lower())
                if val_clean == col0_clean:
                    score = max(score, 1.0)
                elif val_clean in col0_clean or col0_clean in val_clean:
                    score = max(score, 0.85)
                else:
                    score = max(score, self._calcular_similaridade(val_clean, col0_clean))

            if score >= limiar:
                candidatos.append((opcao, score))

        if not candidatos:
            logger.info(f"      ⚠ Nenhuma opção com similaridade >= {limiar:.0%} para \"{valor_desejado}\"")
            return None

        # Ordena por origem primeiro, score depois. Score puro elegia a linha
        # 'Capturado no orgao' — que exige adicao manual e nao tem CNPJ — quando ela
        # vinha 2 pontos a frente por acaso de acentuacao (30/07: 'Itau Unibanco S.A'
        # capturado 85% ganhou de 'Itau Unibanco S.A.' da base, 83%, com CNPJ).
        # Ultimo criterio: entre filiais de mesmo nome e mesmo score (Itau tem 4),
        # a matriz e' a escolha previsivel quando os dados nao trazem CNPJ.
        candidatos.sort(key=lambda x: (_prioridade_origem(x[0]), -x[1],
                                       0 if _eh_matriz(x[0]) else 1))

        # --- Fase 2: detecção de homônimos ---
        melhor_score = candidatos[0][1]
        # Homônimos = opções com score muito próximo do melhor (diferença < 5%)
        homonimos = [c for c in candidatos if abs(c[1] - melhor_score) < 0.05]

        if len(homonimos) > 1:
            nomes_homonimos = [h[0].get('nome') or h[0].get('texto_completo', '?') for h in homonimos]
            logger.warning(f"      ⚠ HOMÔNIMOS DETECTADOS: {len(homonimos)} opções com nomes similares")
            for i, (op, sc) in enumerate(homonimos):
                doc_op = op.get('cpf_cnpj', '').strip()
                nome_op = op.get('nome') or op.get('texto_completo', '?')
                origem_op = op.get('origem', '').strip()
                logger.warning(f"         [{i}] {nome_op} | Doc: {doc_op or 'N/A'} | Origem: {origem_op or 'N/A'} | Score: {sc:.0%}")

            # --- Fase 2a-bis: preferir homônimo cujo NOME bate diretamente com o valor ---
            # Resolve o caso em que um CONTATO tem no campo "Doc" o mesmo texto que o
            # valor buscado (ex.: "Doc: Negociação padrão"), gerando empate espúrio com a
            # opção real cuja coluna Nome é "Negociação padrão".
            # ATENÇÃO: quando múltiplos homônimos têm o mesmo nome, aplica preferência de
            # origem antes de retornar (evita selecionar "Capturado no órgão" quando
            # "Existente na base" está disponível).
            val_busca_clean = re.sub(r'[^\w\s]', '', valor_desejado.strip().lower())
            _matches_nome_exato = []
            for opcao, score in homonimos:
                nome_op = (opcao.get('nome') or opcao.get('texto_completo') or '').strip()
                nome_op_clean = re.sub(r'[^\w\s]', '', nome_op.lower())
                if nome_op_clean == val_busca_clean:
                    _matches_nome_exato.append((opcao, score))
            if _matches_nome_exato:
                _origens_pref = ['existente na base', 'existente', 'interno', 'legalone', 'legal one', 'cadastro']
                for opcao, _ in _matches_nome_exato:
                    _orig = (opcao.get('origem') or '').strip().lower()
                    if any(p in _orig for p in _origens_pref):
                        nome_op = opcao.get('nome') or opcao.get('texto_completo', '?')
                        logger.info(
                            f"      🎯 Homônimo resolvido por match exato no Nome + origem preferida! "
                            f"Selecionado: \"{nome_op}\" (Origem: {opcao.get('origem', '')})"
                        )
                        return opcao
                # Nenhuma origem preferida — retorna primeiro match de nome
                opcao_nome = _matches_nome_exato[0][0]
                nome_op = opcao_nome.get('nome') or opcao_nome.get('texto_completo', '?')
                logger.info(
                    f"      🎯 Homônimo resolvido por match exato no Nome! "
                    f"Selecionado: \"{nome_op}\""
                )
                return opcao_nome

            # --- Fase 2a: desambiguação por CPF/CNPJ ---
            if doc_ref:
                logger.info(f"      🔎 Tentando desambiguar por documento: {documento_referencia}")
                for opcao, score in homonimos:
                    doc_opcao = self._normalizar_documento(opcao.get('cpf_cnpj', ''))
                    if doc_opcao and doc_opcao == doc_ref:
                        nome_sel = opcao.get('nome') or opcao.get('texto_completo', '?')
                        logger.info(f"      ✅ Homônimo resolvido por documento! Selecionado: \"{nome_sel}\" (Doc: {opcao.get('cpf_cnpj', '')})")
                        return opcao
                logger.warning(f"      ⚠ Documento {documento_referencia} não encontrado entre os homônimos")

            # --- Fase 2b: desambiguação por similaridade com valor original ---
            # Quando buscamos por variante (ex: "Banco Bradesco"), mas o nome
            # original era "Banco Bradesco Financiamentos S/A", preferimos o
            # homônimo cujo nome é mais próximo do valor original.
            val_orig = (valor_original or '').strip()
            if val_orig and val_orig.lower() != valor_desejado.lower():
                val_orig_clean = re.sub(r'[^\w\s]', '', val_orig.lower())
                scores_orig = []
                for opcao, score in homonimos:
                    nome_op = (opcao.get('nome') or opcao.get('texto_completo') or '').strip()
                    nome_op_clean = re.sub(r'[^\w\s]', '', nome_op.lower())
                    if val_orig_clean == nome_op_clean:
                        s = 1.0
                    elif val_orig_clean in nome_op_clean or nome_op_clean in val_orig_clean:
                        s = 0.85
                    else:
                        s = self._calcular_similaridade(val_orig_clean, nome_op_clean)
                    scores_orig.append((opcao, score, s))
                scores_orig.sort(key=lambda x: x[2], reverse=True)
                melhor_orig = scores_orig[0][2]
                segundo_orig = scores_orig[1][2] if len(scores_orig) > 1 else 0.0
                if melhor_orig - segundo_orig >= 0.05:
                    opcao_sel = scores_orig[0][0]
                    nome_sel = opcao_sel.get('nome') or opcao_sel.get('texto_completo', '?')
                    logger.info(
                        f"      🎯 Homônimo resolvido por similaridade com valor original! "
                        f"Selecionado: \"{nome_sel}\" (sim. original: {melhor_orig:.0%})"
                    )
                    return opcao_sel
                # Empate no topo nao invalida o criterio: descarta quem ficou pra tras e
                # deixa as fases seguintes desempatarem entre os que empataram. 30/07:
                # 'Itau Unibanco S.A.' tem 5 filiais (sim. 1.0) e o 'Holding' (0.8) so
                # ganhava porque o empate fazia esta fase desistir da lista inteira.
                sobreviventes = [(o, sc) for o, sc, s in scores_orig
                                 if melhor_orig - s < 0.05]
                if 1 <= len(sobreviventes) < len(homonimos):
                    descartados = len(homonimos) - len(sobreviventes)
                    logger.info(
                        f"      🎯 Similaridade com o valor original descartou {descartados} "
                        f"homônimo(s) mais distante(s); {len(sobreviventes)} seguem empatados"
                    )
                    homonimos = sobreviventes
                else:
                    logger.debug("      Similaridade com valor original não foi suficiente para desambiguar.")

            # --- Fase 2c: desambiguação por origem (preferir 'Existente na base' > 'Interno' > etc.) ---
            origens_preferidas = ['existente na base', 'existente', 'interno', 'legalone', 'legal one', 'cadastro']
            for opcao, score in homonimos:
                origem = (opcao.get('origem') or '').strip().lower()
                if any(pref in origem for pref in origens_preferidas):
                    nome_sel = opcao.get('nome') or opcao.get('texto_completo', '?')
                    logger.info(f"      🎯 Homônimo resolvido por origem preferida! Selecionado: \"{nome_sel}\" (Origem: {opcao.get('origem', '')})")
                    return opcao

            # --- Fase 2d: sem desambiguação possível → seleciona primeiro e alerta ---
            opcao_escolhida = homonimos[0][0]
            nome_sel = opcao_escolhida.get('nome') or opcao_escolhida.get('texto_completo', '?')
            doc_sel = opcao_escolhida.get('cpf_cnpj', 'N/A')
            logger.warning(f"      ⚠ ATENÇÃO: Homônimo não resolvido automaticamente!")
            logger.warning(f"         Selecionando primeiro da lista: \"{nome_sel}\" (Doc: {doc_sel})")
            logger.warning(f"         RECOMENDA-SE VERIFICAÇÃO MANUAL deste cadastro.")
            return opcao_escolhida

        # --- Sem homônimos: seleção normal ---
        melhor = candidatos[0][0]
        nome_sel = melhor.get('nome') or melhor.get('texto_completo', '?')
        logger.info(f"      🎯 Melhor match: \"{nome_sel}\" (similaridade {melhor_score:.0%})")
        return melhor

    def _combobox_commitou(self) -> bool | None:
        """O combobox em foco aceitou a selecao? None = nao deu para saber.

        Sinal confiavel: a classe 'bfm-invalid' no host. O texto do input NAO
        serve — ele mostra o que foi digitado mesmo quando nada foi escolhido,
        e foi por isso que o bot passou a vida logando '✓ selecionado' em campos
        que o LegalOne recusava.
        """
        if not self.page:
            return None
        try:
            return self.page.evaluate(
                """
                () => {
                    const el = document.activeElement;
                    const host = el && (el.closest('bento-combobox') || el.closest('.bento-select'));
                    if (!host) return null;
                    return !(host.classList.contains('bfm-invalid')
                             || host.classList.contains('ng-invalid'));
                }
                """
            )
        except Exception:
            return None

    def _confirmar_row_bento(self, valor: str) -> str | None:
        """Acha a row que casa com `valor` no dropdown aberto e confirma no teclado.

        Localiza o indice em JS (sem clicar, porque clicar nao commita — ver
        _clicar_opcao_bento_combobox) e desce com ArrowDown ate ele.
        Devolve o texto da row confirmada, ou None se nada casou.
        """
        if not self.page or not valor:
            return None
        achado = self.page.evaluate(
            """
            (val) => {
                const rows = Array.from(document.querySelectorAll(
                    '.bento-list-row.bui-bento-combobox-container-item, ' +
                    '.bento-list-row.bento-combobox-container-item, ' +
                    '.bento-list-row'
                )).filter(r => r.offsetHeight > 0);
                const lower = (val || '').toLowerCase();
                for (const modo of ['exact', 'partial']) {
                    for (let i = 0; i < rows.length; i++) {
                        const txt = (rows[i].innerText || rows[i].textContent || '').trim().toLowerCase();
                        if (modo === 'exact' ? txt === lower : txt.includes(lower)) {
                            return {indice: i, texto: txt};
                        }
                    }
                }
                return rows.length ? {indice: 0, texto: '__primeira__'} : null;
            }
            """,
            valor,
        )
        if not achado:
            return None
        if achado['texto'] == '__primeira__':
            # Nada casou com o valor pedido: melhor nao escolher do que escolher errado.
            logger.warning(f"   ⚠ Nenhuma opcao casa com {valor!r} — nao vou confirmar nada")
            return None
        confirmou = self._clicar_opcao_bento_combobox(
            {'index': achado['indice'], 'nome': achado['texto']}
        )
        return achado['texto'] if confirmou else None

    def _espionar_requests(self) -> None:
        """Anota os POSTs que o proprio LegalOne faz, para saber se da' para
        cadastrar por HTTP em vez de pelo formulario (como o dejt_headless).

        So grava metodo/URL/corpo; Cookie e Authorization saem redigidos — o
        arquivo e' um mapa do formato, nao um cofre de credencial.
        """
        if not self.context or os.getenv('LEGALONE_ESPIAR', '1') != '1':
            return
        destino = Path(__file__).parent / 'docs' / 'varredura' / 'requests_legalone.jsonl'
        destino.parent.mkdir(parents=True, exist_ok=True)

        def _anotar(req):
            try:
                if req.method not in ('POST', 'PUT', 'PATCH'):
                    return
                if 'legalone.com.br' not in req.url:
                    return
                cab = {k: ('<redigido>' if k.lower() in ('cookie', 'authorization') else v)
                       for k, v in req.headers.items()}
                linha = {'quando': datetime.now().isoformat(timespec='seconds'),
                         'metodo': req.method, 'url': req.url, 'headers': cab,
                         'corpo': (req.post_data or '')[:20000]}
                with destino.open('a', encoding='utf-8') as fh:
                    fh.write(json.dumps(linha, ensure_ascii=False) + '\n')
            except Exception:
                pass  # espiao nunca derruba o cadastro

        try:
            self.context.on('request', _anotar)
            logger.info(f"   🕵 Gravando POSTs do LegalOne em {destino}")
        except Exception as e:
            logger.debug(f"Nao consegui espionar requests: {e}")

    def _campo_confere_com(self, esperado: str) -> bool:
        """O input em foco esta com o valor esperado? Compara sem acento/caixa."""
        if not self.page or not esperado:
            return True
        try:
            atual = self.page.evaluate(
                """() => {
                    const el = document.activeElement;
                    const host = el && (el.closest('bento-combobox') || el.closest('.bento-select'));
                    const inp = host ? host.querySelector('input') : el;
                    return inp ? (inp.value || '') : '';
                }"""
            )
        except Exception:
            return True  # nao deu para ler: nao inventa falha

        def _n(t):
            t = unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode()
            return re.sub(r'[^a-z0-9]+', ' ', t.lower()).strip()

        atual_n, esperado_n = _n(atual), _n(esperado)
        if not atual_n:
            return False
        # Basta uma conter a outra: o grid mostra 'Nome | Doc | Origem' e o campo
        # fica so com o nome.
        return atual_n in esperado_n or esperado_n in atual_n

    def _limpar_campo_focado(self) -> None:
        """Esvazia o combobox em foco, para o Salvar barrar em vez de gravar errado."""
        if not self.page:
            return
        try:
            self.page.keyboard.press('Control+a')
            self.page.keyboard.press('Delete')
            self.page.keyboard.press('Escape')
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"Nao consegui limpar o campo: {e}")

    def _clicar_opcao_bento_combobox(self, opcao: dict) -> bool:
        """Confirma uma opcao do bento-combobox descendo com as setas + Enter.

        Clicar na row NAO commita — nem o MouseEvent sintetico nem o clique real
        do Playwright. O componente BFM fica com 'bfm-invalid' e o LegalOne trata
        o campo como vazio, deixando o Salvar desabilitado. Medido em 30/07 no
        mesmo campo e valor (ver scripts/dump_combobox.py):

            dispatchEvent  -> ng-invalid, bfm-invalid
            clique real    -> ng-invalid, bfm-invalid
            setas + Enter  -> ng-valid, ng-touched, ng-dirty

        O indice vem da escolha feita antes (fuzzy match / desempate de
        homonimos), entao descer 'index + 1' vezes preserva essa decisao.
        """
        if not self.page or not opcao:
            return False
        row_id = (opcao.get('id') or '').strip()
        alvo = (opcao.get('nome') or opcao.get('texto_completo') or '').strip()
        idx = int(opcao.get('index') or 0)
        try:
            # Desce conferindo qual row esta 'highlighted' — nao confia na contagem.
            # Contar setas commitou a linha errada em silencio (negotiationContract
            # virou 'Hon - 0000080/001' em 30/07), e valor errado no cadastro e' pior
            # que campo recusado.
            chegou = False
            for _ in range(idx + 8):
                self.page.keyboard.press('ArrowDown')
                time.sleep(0.06)
                ativa = self.page.evaluate(
                    """() => {
                        const r = document.querySelector('.bento-list-row.highlighted');
                        return r ? {id: r.id || '', texto: (r.innerText || '').trim()} : null;
                    }"""
                )
                if not ativa:
                    continue
                if row_id and ativa['id'] == row_id:
                    chegou = True
                    break
                if not row_id and alvo and alvo.lower() in (ativa['texto'] or '').lower():
                    chegou = True
                    break
            if not chegou:
                logger.warning(
                    f"   ⚠ Nao consegui destacar a opcao pretendida ({alvo or row_id!r}) — "
                    "abortando em vez de confirmar outra linha"
                )
                return False

            self.page.keyboard.press('Enter')
            time.sleep(0.8)

            if self._combobox_commitou() is False:
                logger.warning(
                    "   ⚠ Combobox recusou a selecao (bfm-invalid) — o LegalOne vai "
                    "tratar este campo como vazio"
                )
                return False

            # Pos-condicao: o campo tem que estar com a opcao PRETENDIDA. Sem isso o
            # bot aceitava qualquer selecao valida — em 30/07 o Contrario Principal
            # ficou 'Augusto Nasser Borges', pessoa sem relacao com o processo, porque
            # a navegacao por teclado continuou sobre uma lista ja trocada.
            # Confere contra a LINHA inteira, nao contra a coluna 'nome': o layout
            # muda por combobox e no Responsavel a coluna 1 e' o e-mail, entao o
            # campo ficava 'Monica Pinheiro' e a checagem esperava 'monica@...'.
            alvo_conf = (opcao.get('texto_completo') or alvo or '').strip()
            if alvo_conf and not self._campo_confere_com(alvo_conf):
                logger.warning(
                    f"   ⚠ Campo ficou com valor diferente do pretendido ({alvo_conf!r}) — "
                    "limpando para nao gravar parte errada"
                )
                self._limpar_campo_focado()
                return False
            return True
        except Exception as e:
            logger.debug(f"Erro ao confirmar opção combobox: {e}")
            return False

    def _preencher_natureza_bento(self, valor: str) -> bool:
        """Preenche o campo Natureza (bento-combobox simples com lista fixa).

        Estratégias em cascata:
          1. Clica no input → digita para filtrar → aguarda lista aparecer (wait_for_selector)
             → clica na .bento-list-row correspondente
          2. Limpa o campo e abre via caret button → aguarda lista → clica na row
          3. Abre via JS (dispatchEvent click) → clica na row
          4. Fallback: injeta o valor diretamente via ngModel/Angular
        """
        if not self.page or not valor:
            return False

        valor_lower = valor.strip().lower()

        # Seletores de opções visíveis no dropdown bento
        _SEL_ROWS = (
            '.bento-list-row.bui-bento-combobox-container-item, '
            '.bento-list-row.bento-combobox-container-item, '
            '.bento-list-row'
        )

        def _clicar_row_visivel(pagina) -> str | None:
            """Confirma a row correspondente ao valor; retorna o texto ou None.

            Nao clica: o clique na row nao commita no bento-combobox (ver
            _clicar_opcao_bento_combobox). Delega para o confirmador de teclado.
            """
            return self._confirmar_row_bento(valor_lower)

        try:
            # Scroll para garantir visibilidade
            self.page.evaluate("""
                () => {
                    const el = document.querySelector('#input-nature')
                        || document.querySelector('bento-combobox[formcontrolname="nature"] input');
                    if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            """)
            time.sleep(0.4)

            # Localiza o campo input
            campo = self.page.query_selector('#input-nature') \
                or self.page.query_selector(
                    'bento-combobox[formcontrolname="nature"] input[type="text"]'
                )
            if not campo:
                try:
                    campo = self.page.wait_for_selector(
                        '#input-nature, bento-combobox[formcontrolname="nature"] input',
                        state='visible', timeout=8000,
                    )
                except Exception:
                    pass
            if not campo:
                logger.warning("   ⚠ Campo #input-nature não encontrado na página")
                return False

            # ── Estratégia 1: digita para filtrar e aguarda lista ──────────────
            self.page.keyboard.press('Escape')  # fecha dropdown stale
            time.sleep(0.2)
            campo.scroll_into_view_if_needed()
            campo.click()
            time.sleep(0.3)
            campo.fill('')
            # Dispara eventos Angular no input para ativar o combobox
            self.page.evaluate(
                """(el) => {
                    el.dispatchEvent(new Event('focus',  {bubbles: true}));
                    el.dispatchEvent(new Event('input',  {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                campo,
            )
            time.sleep(0.2)
            campo.type(valor, delay=50)
            # Aguarda a lista abrir — até 3 s
            try:
                self.page.wait_for_selector(_SEL_ROWS, state='visible', timeout=3000)
            except Exception:
                pass  # lista pode não aparecer; tentamos clicar mesmo assim

            clicou = _clicar_row_visivel(self.page)
            if clicou:
                time.sleep(0.4)
                label = f'"{valor}"' if clicou != '__first__' else 'primeira opção disponível'
                logger.info(f"   ✓ Natureza selecionada (digitação): {label}")
                return True

            # ── Estratégia 2: limpa e abre via caret button ───────────────────
            try:
                campo.fill('')
                self.page.evaluate(
                    "(el) => el.dispatchEvent(new Event('input', {bubbles:true}))", campo
                )
                caret = self.page.query_selector(
                    'bento-combobox[formcontrolname="nature"] .bento-combobox-dropdown-button-icon, '
                    'bento-combobox[formcontrolname="nature"] button[aria-label*="pen"]'
                )
                if caret:
                    caret.click()
                else:
                    campo.click()
                try:
                    self.page.wait_for_selector(_SEL_ROWS, state='visible', timeout=3000)
                except Exception:
                    pass
                clicou2 = _clicar_row_visivel(self.page)
                if clicou2:
                    time.sleep(0.4)
                    label2 = f'"{valor}"' if clicou2 != '__first__' else 'primeira opção disponível'
                    logger.info(f"   ✓ Natureza selecionada (caret): {label2}")
                    return True
            except Exception:
                pass

            # ── Estratégia 3: JS puro — abre o dropdown via dispatchEvent ─────
            try:
                self.page.evaluate("""
                    () => {
                        const input = document.querySelector('#input-nature')
                            || document.querySelector('bento-combobox[formcontrolname="nature"] input');
                        if (!input) return;
                        ['focus','mousedown','click','input'].forEach(t =>
                            input.dispatchEvent(new Event(t, {bubbles:true}))
                        );
                    }
                """)
                time.sleep(0.8)
                clicou3 = _clicar_row_visivel(self.page)
                if clicou3:
                    time.sleep(0.4)
                    label3 = f'"{valor}"' if clicou3 != '__first__' else 'primeira opção disponível'
                    logger.info(f"   ✓ Natureza selecionada (JS dispatch): {label3}")
                    return True
            except Exception:
                pass

            logger.warning(f"   ⚠ Natureza '{valor}' não encontrada nas opções do dropdown")
            return False

        except Exception as e:
            logger.warning(f"   ⚠ Erro ao preencher Natureza: {e}")
            return False

    def _preencher_status_select(self, valor: str) -> bool:
        """Preenche o campo Status.

        Suporta dois casos do LegalOne:
          • <select> nativo  → page.select_option + dispatch de eventos Angular
          • bento-combobox   → mesma estratégia de _preencher_natureza_bento

        Mapa de labels → values nativos: Ativo=1, Suspenso=2, Baixado=3, Arquivado=4
        """
        if not self.page or not valor:
            return False

        valor_lower = valor.strip().lower()
        _mapa_labels = {
            'ativo': 'Ativo', 'active': 'Ativo', 'em andamento': 'Ativo',
            'suspenso': 'Suspenso', 'suspended': 'Suspenso',
            'baixado': 'Baixado', 'encerrado': 'Baixado', 'closed': 'Baixado',
            'arquivado': 'Arquivado', 'archived': 'Arquivado',
        }
        _valor_map = {'Ativo': '1', 'Suspenso': '2', 'Baixado': '3', 'Arquivado': '4'}
        label_alvo = _mapa_labels.get(valor_lower) or valor

        # Seletores para o <select> nativo
        _SEL_SELECT = (
            '#input-status, '
            'select[formcontrolname="statusId"], '
            'select[formcontrolname="status"], '
            'select[id*="status"]'
        )

        try:
            # Scroll para garantir visibilidade
            self.page.evaluate("""
                () => {
                    const el = document.querySelector('#input-status')
                        || document.querySelector('select[formcontrolname="statusId"]')
                        || document.querySelector('select[id*="status"]');
                    if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            """)
            time.sleep(0.3)

            # ── Caminho A: <select> nativo ────────────────────────────────────
            select_el = None
            try:
                select_el = self.page.wait_for_selector(
                    _SEL_SELECT, state='visible', timeout=6000
                )
            except Exception:
                pass

            if select_el:
                select_el.scroll_into_view_if_needed()
                selecionou = False

                # Tentativa 1: select_option por label
                try:
                    self.page.select_option(_SEL_SELECT, label=label_alvo)
                    selecionou = True
                except Exception:
                    pass

                # Tentativa 2: select_option por value numérico
                if not selecionou:
                    val_num = _valor_map.get(label_alvo)
                    if val_num:
                        try:
                            self.page.select_option(_SEL_SELECT, value=val_num)
                            selecionou = True
                        except Exception:
                            pass

                # Tentativa 3: JS direto — encontra <option> pelo texto e define o value
                if not selecionou:
                    selecionou = self.page.evaluate(
                        """([selCSS, lbl, valNum]) => {
                            const sel = document.querySelector(selCSS);
                            if (!sel) return false;
                            const opts = Array.from(sel.options);
                            const lower = lbl.toLowerCase();
                            let opt = opts.find(o => o.text.trim().toLowerCase() === lower)
                                   || opts.find(o => o.text.trim().toLowerCase().includes(lower))
                                   || (valNum ? opts.find(o => o.value === valNum) : null);
                            if (!opt) return false;
                            sel.value = opt.value;
                            return true;
                        }""",
                        [_SEL_SELECT, label_alvo, _valor_map.get(label_alvo, '')],
                    )

                if selecionou:
                    # Dispara os eventos que o Angular Reactive Forms precisa detectar a mudança
                    self.page.evaluate(
                        """(selCSS) => {
                            const sel = document.querySelector(selCSS);
                            if (!sel) return;
                            ['input', 'change'].forEach(t =>
                                sel.dispatchEvent(new Event(t, {bubbles: true}))
                            );
                        }""",
                        _SEL_SELECT,
                    )
                    time.sleep(0.3)
                    logger.info(f"   ✓ Status selecionado: {label_alvo}")
                    return True

            # ── Caminho B: bento-combobox customizado ─────────────────────────
            logger.info("   ℹ #input-status não é <select> nativo — tentando bento-combobox...")
            _SEL_ROWS = (
                '.bento-list-row.bui-bento-combobox-container-item, '
                '.bento-list-row.bento-combobox-container-item, '
                '.bento-list-row'
            )

            campo_b = None
            for sel in (
                'bento-combobox[formcontrolname="statusId"] input',
                'bento-combobox[formcontrolname="status"] input',
                'input[id*="status"]',
            ):
                try:
                    campo_b = self.page.wait_for_selector(sel, state='visible', timeout=3000)
                    if campo_b:
                        break
                except Exception:
                    continue

            if not campo_b:
                logger.warning("   ⚠ Campo Status não encontrado (nem <select> nem bento-combobox)")
                return False

            campo_b.scroll_into_view_if_needed()
            campo_b.click()
            time.sleep(0.3)
            campo_b.fill('')
            campo_b.type(valor, delay=50)
            try:
                self.page.wait_for_selector(_SEL_ROWS, state='visible', timeout=3000)
            except Exception:
                pass

            # Confirma no teclado: clicar na row nao commita no bento-combobox
            # (ver _clicar_opcao_bento_combobox).
            clicou = self._confirmar_row_bento(valor_lower)
            if clicou:
                time.sleep(0.4)
                logger.info(f"   ✓ Status selecionado (bento-combobox): {clicou}")
                return True

            logger.warning(f"   ⚠ Status '{valor}' não encontrado nas opções")
            return False

        except Exception as e:
            logger.warning(f"   ⚠ Erro ao preencher Status: {e}")
            return False

    def _selecionar_opcao_bento_tree(self, valor: str) -> bool:
        """Seleciona uma opção dentro de um componente bento-tree visível.

        Fluxo:
          1. Detecta se há um bento-tree visível na página
          2. Expande todos os nós (clica "Expand all")
          3. Procura um treeitem cujo texto corresponda ao valor
          4. Clica no item encontrado
        """
        if not self.page or not valor:
            return False
        try:
            tree = self.page.query_selector('bento-tree')
            if not tree or not tree.is_visible():
                return False

            logger.info(f"      🌳 Bento-tree detectado, buscando \"{valor}\"...")

            # Expande todos os nós para garantir visibilidade
            try:
                btn_expand = tree.query_selector(
                    'button[aria-label="Expand all"], '
                    'button[aria-label="Expandir todos"]'
                )
                if btn_expand and btn_expand.is_visible():
                    btn_expand.click()
                    time.sleep(1)
            except Exception:
                pass

            # Busca todos os itens da árvore pelo texto
            val_lower = valor.strip().lower()
            itens = tree.query_selector_all('.bento-tree-item-cta')
            melhor_el = None
            melhor_score = 0.0

            for item in itens:
                try:
                    if not item.is_visible():
                        continue
                    texto = item.inner_text().strip()
                    texto_lower = texto.lower()
                    if texto_lower == val_lower:
                        melhor_el = item
                        melhor_score = 1.0
                        break
                    if val_lower in texto_lower or texto_lower in val_lower:
                        score = 0.85
                    else:
                        score = self._calcular_similaridade(val_lower, texto_lower)
                    if score > melhor_score:
                        melhor_score = score
                        melhor_el = item
                except Exception:
                    continue

            if melhor_el and melhor_score >= 0.45:
                melhor_el.click()
                texto_sel = melhor_el.inner_text().strip()
                logger.info(f"      ✅ Selecionado na árvore: \"{texto_sel}\" ({melhor_score:.0%})")
                time.sleep(0.8)
                return True

            logger.warning(f"      ⚠ \"{valor}\" não encontrado na árvore")
            return False
        except Exception as e:
            logger.debug(f"Erro ao selecionar opção na bento-tree: {e}")
            return False

    def _buscar_cnpj_web(self, nome_empresa: str) -> str | None:
        """Busca o CNPJ de uma empresa na web usando o navegador existente.

        Abre uma aba, pesquisa no Google, extrai o padrão de CNPJ e fecha a aba.
        Retorna string do CNPJ (XX.XXX.XXX/XXXX-XX) ou None.
        """
        if not self.page or not nome_empresa:
            return None

        logger.info(f"      ðŸ” Buscando CNPJ de \"{nome_empresa}\" na web...")
        nova_aba = None
        try:
            nova_aba = self.context.new_page()
            query = f"{nome_empresa} CNPJ"
            nova_aba.goto(
                f"https://www.google.com/search?q={quote_plus(query)}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            time.sleep(2)

            # Extrai todo o texto da página e procura padrão de CNPJ
            texto = nova_aba.inner_text("body")
            # Padrão: XX.XXX.XXX/XXXX-XX
            match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
            if match:
                cnpj = match.group(0)
                logger.info(f"      ✓ CNPJ encontrado: {cnpj}")
                return cnpj

            # Padrão sem formatação: 14 dígitos seguidos
            match2 = re.search(r'\b(\d{14})\b', texto)
            if match2:
                d = match2.group(1)
                cnpj = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
                logger.info(f"      ✓ CNPJ encontrado (sem formato): {cnpj}")
                return cnpj

            logger.warning(f"      ⚠ CNPJ não encontrado na web para \"{nome_empresa}\"")
            return None

        except Exception as e:
            logger.warning(f"      ⚠ Erro ao buscar CNPJ na web: {e}")
            return None
        finally:
            if nova_aba and not nova_aba.is_closed():
                try:
                    nova_aba.close()
                except Exception:
                    pass
            # Garante que voltamos para a aba principal
            self._switch_to_latest_page()

    def _texto_indica_captura_orgao(self, texto: str | None) -> bool:
        """Retorna True quando o texto indica contato capturado no órgão."""
        txt = re.sub(r"\s+", " ", str(texto or "")).strip().lower()
        if not txt:
            return False
        # O LegalOne as vezes entrega "órgão" com codificação corrompida no
        # texto do combobox, então casa só por "capturado no", que é a parte
        # estável e exclusiva do aviso que exige criação manual.
        return "capturado no" in txt

    def _opcao_exige_adicao_manual(self, opcao: dict | None) -> bool:
        """Detecta se a opção do combobox exige criar contato manualmente."""
        if not opcao:
            return False
        origem = opcao.get('origem')
        texto = opcao.get('texto_completo')
        return (
            self._texto_indica_captura_orgao(origem)
            or self._texto_indica_captura_orgao(texto)
        )

    def _clicar_adicionar_no_dropdown(self, campo=None, valor: str = '') -> bool:
        """Clica no botão 'Adicionar' que aparece no fundo do dropdown bento-combobox.

        Se o dropdown estiver fechado e ``campo``/``valor`` forem fornecidos,
        re-abre o dropdown automaticamente antes de tentar novamente.
        """
        if not self.page:
            return False

        dropdown_ids: list[str] = []
        if campo:
            try:
                attrs = [
                    campo.get_attribute('aria-controls'),
                    campo.get_attribute('aria-describedby'),
                    campo.get_attribute('id'),
                ]
                for attr in attrs:
                    if not attr:
                        continue
                    for token in str(attr).split():
                        tok = token.strip().lstrip('#')
                        if not tok:
                            continue
                        dropdown_ids.append(tok)
                        if tok.endswith('-aria'):
                            dropdown_ids.append(tok[:-5])
            except Exception:
                pass

        # Dedup preservando ordem
        vistos_ids = set()
        dropdown_ids = [d for d in dropdown_ids if not (d in vistos_ids or vistos_ids.add(d))]

        js_click = """
            (dropdownIds) => {
                const isVisible = (el) => !!el && (
                    el.offsetWidth > 0 ||
                    el.offsetHeight > 0 ||
                    el.getClientRects().length > 0
                );
                const clickRobusto = (el) => {
                    if (!el) return false;
                    const alvo = el.closest('button, [role="button"], a') || el;
                    try {
                        alvo.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        alvo.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        alvo.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        if (typeof alvo.click === 'function') alvo.click();
                        return true;
                    } catch (_) {
                        return false;
                    }
                };

                const rootsGerais = Array.from(document.querySelectorAll(
                    '[id*="bui-combobox-list"], .bento-combobox-container, .bento-list, ' +
                    '[role="listbox"], [role="dialog"], .cdk-overlay-container, .cdk-overlay-pane'
                ));

                const rootsPreferidos = [];
                for (const raw of (dropdownIds || [])) {
                    const id = (raw || '').replace(/^#/, '').trim();
                    if (!id) continue;
                    const byId = document.getElementById(id);
                    if (byId) rootsPreferidos.push(byId);
                    const byPrefix = document.querySelector(`[id^="${CSS.escape(id)}"]`);
                    if (byPrefix) rootsPreferidos.push(byPrefix);
                }

                const roots = [...rootsPreferidos, ...rootsGerais];
                const rootsDedupe = [];
                const seen = new Set();
                for (const r of roots) {
                    if (!r) continue;
                    if (seen.has(r)) continue;
                    seen.add(r);
                    rootsDedupe.push(r);
                }

                for (const root of rootsDedupe) {
                    if (!isVisible(root)) continue;
                    const candidatos = Array.from(
                        root.querySelectorAll('button, [role="button"], a, span, div')
                    ).filter(el => {
                        if (!isVisible(el)) return false;
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        return txt === 'adicionar' || txt.startsWith('adicionar ');
                    });

                    // Prioriza controles clicáveis e o último visível (normalmente no rodapé do dropdown)
                    const addEl = candidatos
                        .sort((a, b) => {
                            const aScore = (a.matches('button, [role="button"], a') ? 1 : 0);
                            const bScore = (b.matches('button, [role="button"], a') ? 1 : 0);
                            return bScore - aScore;
                        })
                        .pop();

                    if (addEl) {
                        if (clickRobusto(addEl)) return true;
                    }
                }

                // Fallback global: procura qualquer ação visível "Adicionar" em overlay/lista
                const allCandidates = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'));
                for (const el of allCandidates) {
                    if (!isVisible(el)) continue;
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (!(txt === 'adicionar' || txt.startsWith('adicionar '))) continue;
                    const emOverlay = !!el.closest(
                        '[id*="bui-combobox-list"], .bento-combobox-container, .bento-list, ' +
                        '[role="listbox"], [role="dialog"], .cdk-overlay-container, .cdk-overlay-pane'
                    );
                    if (!emOverlay) continue;
                    if (clickRobusto(el)) return true;
                }
                return false;
            }
        """

        # Seletor do modal de contato — usado para aguardar aparição após clicar "Adicionar"
        _MODAL_SELETOR = (
            'app-add-contact-modal, #contact-form, #input-name, #input-cpf-cnpj, '
            '#naturalPerson-checkbox, [class*="add-contact"], [class*="contact-modal"]'
        )

        def _aguardar_modal(timeout_ms: int = 3000) -> bool:
            try:
                self.page.wait_for_selector(_MODAL_SELETOR, state='visible', timeout=timeout_ms)
                return True
            except Exception:
                return False

        for tentativa in range(4):
            # --- Tentativa via JS ---
            try:
                if bool(self.page.evaluate(js_click, dropdown_ids)):
                    logger.info("      ✅ Clicou em 'Adicionar' no dropdown")
                    # Aguarda modal aparecer em vez de dormir fixo
                    if _aguardar_modal(2500):
                        return True
                    time.sleep(0.3)
                    return True
            except Exception:
                pass

            # --- Fallback: Playwright selector ---
            try:
                seletores_adicionar = []
                for did in dropdown_ids:
                    seletores_adicionar.extend([
                        f'#{did} button:has-text("Adicionar")',
                        f'#{did} [role="button"]:has-text("Adicionar")',
                        f'#{did} a:has-text("Adicionar")',
                        f'#{did} *:has-text("Adicionar")',
                    ])

                seletores_adicionar.extend([
                    'button:has-text("Adicionar")',
                    '[role="button"]:has-text("Adicionar")',
                    'a:has-text("Adicionar")',
                    'span.ng-star-inserted:has-text("Adicionar")',
                    '[id*="bui-combobox-list"] *:has-text("Adicionar")',
                    '.bento-combobox-container *:has-text("Adicionar")',
                    '.bento-list *:has-text("Adicionar")',
                ])
                for seletor in seletores_adicionar:
                    btn = self.page.wait_for_selector(seletor, state='visible', timeout=1200)
                    if btn:
                        try:
                            btn.click(force=True)
                        except Exception:
                            btn.click()
                        logger.info(f"      ✅ Clicou em 'Adicionar' no dropdown (fallback: {seletor})")
                        if _aguardar_modal(2500):
                            return True
                        time.sleep(0.3)
                        return True
            except Exception:
                pass

            # --- Dropdown fechado: re-abre progressivamente ---
            # ANTES de re-abrir, verifica se o modal de contato já está aberto
            # (pode ter aberto depois de um clique anterior com delay de animação).
            if campo:
                try:
                    modal_aberto = self.page.query_selector(
                        'app-add-contact-modal, #contact-form, #input-name, #naturalPerson-checkbox, '
                        '[class*="add-contact"], [class*="contact-modal"]'
                    )
                    if modal_aberto and modal_aberto.is_visible():
                        logger.info("      ✅ Modal de contato já aberto (detectado antes do retry)")
                        return True
                except Exception:
                    pass
            if tentativa < 3 and campo:
                logger.info(f"      🔄 Dropdown fechado (tentativa {tentativa + 1}/4). Re-abrindo...")
                try:
                    if tentativa < 2:
                        # Tentativas 0-1: apenas clica no input para reabrir
                        campo.click()
                        time.sleep(0.5)
                        try:
                            campo.press('ArrowDown')
                        except Exception:
                            pass
                        time.sleep(1.0)
                    else:
                        # Tentativa 2: fallback pesado - limpa e redigita
                        campo.click()
                        time.sleep(0.3)
                        campo.fill('')
                        if valor:
                            campo.type(valor, delay=40)
                        try:
                            campo.press('ArrowDown')
                        except Exception:
                            pass
                        time.sleep(1.5)
                except Exception:
                    pass
            else:
                break

        logger.warning("      ⚠ Botão 'Adicionar' não encontrado no dropdown")
        return False

    def _alerta_contato_exige_adicao_manual(self, seletor: str | None = None) -> bool:
        """Retorna True quando o LegalOne exige adicionar contato manualmente.

        Com ``seletor``, olha só a vizinhança daquele input. Sem ele, varre o
        documento — o que inclui '.ng-star-inserted' (presente em quase todo
        elemento Angular) e portanto pega o alerta de OUTRO campo, gerando
        correção indevida. Prefira sempre passar o seletor do campo.
        """
        if not self.page:
            return False
        try:
            texto_alerta = None
            if seletor:
                # Medido no DOM real do LegalOne (litigation/create, 28/07): todo
                # [role="alert"] mora no '.form-group' do proprio campo, e o
                # form-group do Contrario Principal tem exatamente 1 input — nao
                # da pra pegar alerta do vizinho. A distancia do input ao alerta
                # varia (2 a 5 niveis), entao contar niveis erra; closest acerta.
                # ponytail: fallback de 5 niveis se a tela nao usar .form-group
                # (ex.: modal de contato).
                texto_alerta = self.page.evaluate(
                    """
                    (sel) => {
                        const inp = document.querySelector(sel);
                        if (!inp) return null;
                        const grupo = inp.closest('.form-group');
                        if (grupo) return (grupo.innerText || '').trim().toLowerCase();
                        let no = inp;
                        for (let i = 0; i < 5 && no.parentElement; i++) no = no.parentElement;
                        return (no.innerText || no.textContent || '').trim().toLowerCase();
                    }
                    """,
                    str(seletor).split(',')[0].strip(),
                )
            if texto_alerta is None:
                texto_alerta = self.page.evaluate(
                    """
                    () => {
                        const alerts = Array.from(document.querySelectorAll('[role="alert"], .ng-star-inserted'));
                        const textos = alerts.map(a => (a.innerText || a.textContent || '').trim().toLowerCase());
                        return textos.join(' | ');
                    }
                    """
                )
            texto_alerta = texto_alerta or ""
            if self._texto_indica_captura_orgao(texto_alerta):
                return True
            return (
                "foi capturado no órgão" in texto_alerta
                or "foi capturado no orgao" in texto_alerta
                or "capturado no órgão" in texto_alerta
                or "capturado no orgao" in texto_alerta
                or "deve ser adicionado manualmente" in texto_alerta
            )
        except Exception:
            return False

    def _obter_modal_contato_ativo(self):
        """Retorna o elemento do modal de contato mais recente (último na DOM = topmost).

        Quando há dois modais empilhados, o último na DOM é o que está no topo e deve
        receber o foco. Retorna None se nenhum modal de contato estiver aberto.
        """
        try:
            handle = self.page.evaluate_handle("""
                () => {
                    const seletores = [
                        // ngb-modal-window é o modal do Angular Bootstrap (ng-bootstrap)
                        'ngb-modal-window',
                        'app-add-contact-modal',
                        '#contact-form',
                        '[class*="add-contact"]',
                        '[class*="contact-modal"]',
                        'mat-dialog-container',
                    ];
                    let ultimo = null;
                    for (const sel of seletores) {
                        const todos = Array.from(document.querySelectorAll(sel));
                        const visiveis = todos.filter(el => el.offsetHeight > 0);
                        if (visiveis.length > 0) {
                            // O ÚLTIMO visível é o mais recente (topmost z-index)
                            ultimo = visiveis[visiveis.length - 1];
                        }
                    }
                    return ultimo;
                }
            """)
            return handle.as_element() if handle else None
        except Exception:
            return None

    def _preencher_no_modal(self, modal_el, seletores: list[str], valor: str, nome_campo: str) -> bool:
        """Preenche um input dentro de um modal específico.

        Estratégia (em ordem de confiabilidade para Angular):
        1. Playwright fill(force=True) — aciona eventos que Angular reconhece
        2. JS nativeInputValueSetter + InputEvent — fallback para casos bloqueados
        """
        valor_escaped = str(valor).replace("'", "\\'").replace('\\', '\\\\')
        for sel in seletores:
            try:
                sel_escaped = sel.replace("'", "\\'")

                # Passo 1: obtém o ElementHandle via JS scoped ao modal
                try:
                    el_handle = self.page.evaluate_handle(
                        f"""(modal) => {{
                            const root = modal || document;
                            let el = root.querySelector('{sel_escaped}');
                            if (!el) el = document.querySelector('{sel_escaped}');
                            if (!el || el.offsetHeight === 0 || el.disabled) return null;
                            return el;
                        }}""",
                        modal_el,
                    )
                    el = el_handle.as_element() if el_handle else None
                except Exception:
                    el = None

                if el:
                    # Verifica se já está preenchido
                    try:
                        val_atual = el.evaluate("el => el.value")
                        if val_atual and str(val_atual).strip():
                            logger.info(f"      ðŸ“ {nome_campo} já pré-preenchido: '{val_atual}'")
                            return True
                    except Exception:
                        pass

                    # Estratégia A: Playwright fill(force=True) — melhor para Angular
                    try:
                        el.fill(valor, force=True)
                        time.sleep(0.3)  # Aguarda re-render Angular
                        val_pos = el.evaluate("el => el.value")
                        if val_pos == valor:
                            logger.info(f"      ðŸ“ {nome_campo} preenchido via fill(force) '{sel}': '{valor}'")
                            return True
                        else:
                            logger.info(f"      ⚠ fill(force) valor DOM='{val_pos}' != '{valor}' — Angular pode ter resetado. Tentando pressSequentially...")
                    except Exception:
                        pass

                    # Estratégia A2: pressSequentially (teclado real) — Angular captura cada keypress
                    try:
                        el.click(force=True)
                        time.sleep(0.2)
                        # Limpa campo antes de digitar
                        el.fill('', force=True)
                        time.sleep(0.1)
                        el.press_sequentially(valor, delay=30)
                        time.sleep(0.3)
                        val_pos2 = el.evaluate("el => el.value")
                        if val_pos2 and valor.lower() in val_pos2.lower():
                            logger.info(f"      ðŸ“ {nome_campo} preenchido via pressSequentially '{sel}': '{val_pos2}'")
                            return True
                        else:
                            logger.info(f"      ⚠ pressSequentially valor DOM='{val_pos2}' — continuando fallbacks...")
                    except Exception as e_seq:
                        logger.debug(f"      pressSequentially falhou: {e_seq}")

                # Estratégia B: JS nativeInputValueSetter + InputEvent Angular-compatível
                preenchido = self.page.evaluate(
                    f"""
                    (modal) => {{
                        const root = modal || document;
                        let el = root.querySelector('{sel_escaped}');
                        if (!el) el = document.querySelector('{sel_escaped}');
                        if (!el || el.offsetHeight === 0 || el.disabled) return null;
                        const valorAtual = el.value || '';
                        if (valorAtual.trim()) return 'ja_preenchido:' + valorAtual;
                        el.focus();
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ) || Object.getOwnPropertyDescriptor(
                            window.HTMLTextAreaElement.prototype, 'value'
                        );
                        if (nativeInputValueSetter && nativeInputValueSetter.set) {{
                            nativeInputValueSetter.set.call(el, '{valor_escaped}');
                        }} else {{
                            el.value = '{valor_escaped}';
                        }}
                        // InputEvent com data é mais compatível com Angular que Event simples
                        try {{
                            el.dispatchEvent(new InputEvent('input', {{ bubbles: true, cancelable: true, data: '{valor_escaped}', inputType: 'insertText' }}));
                        }} catch(e) {{
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        }}
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, key: 'a' }}));
                        el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return 'preenchido:' + el.value;
                    }}
                    """,
                    modal_el,
                )
                if preenchido and str(preenchido).startswith('preenchido:'):
                    v_set = str(preenchido).split(':', 1)[1]
                    logger.info(f"      ðŸ“ {nome_campo} preenchido via JS '{sel}': '{v_set}'")
                    return True
                if preenchido and str(preenchido).startswith('ja_preenchido:'):
                    v_atual = str(preenchido).split(':', 1)[1]
                    logger.info(f"      ðŸ“ {nome_campo} já pré-preenchido: '{v_atual}'")
                    return True
            except Exception:
                continue
        return False

    def _corrigir_captura_orgao(self, seletor, nome, doc, label) -> bool:
        """Se o LegalOne acusa 'contato capturado no orgao / adicionar manualmente',
        cria o contato de verdade (o placeholder do tribunal nao pode ficar).
        Retorna True se, ao final, nao ha mais o alerta."""
        if not self._alerta_contato_exige_adicao_manual(seletor):
            return True
        logger.warning(f"   [CONTATO] '{label}' foi capturado do orgao - criando contato manualmente")
        campo_el = None
        try:
            sel1 = str(seletor).split(',')[0].strip() if seletor else ''
            if sel1:
                campo_el = self.page.query_selector(sel1)
            if campo_el:
                campo_el.click(); time.sleep(0.3)
                campo_el.fill(''); time.sleep(0.3)
                campo_el.type(str(nome)[:60], delay=30); time.sleep(2)
        except Exception as e:
            logger.warning(f"   [CONTATO] falha ao reabrir dropdown de '{label}': {str(e)[:80]}")
        try:
            self._adicionar_contato_novo(nome=nome, cnpj=doc, campo=campo_el)
        except Exception as e:
            logger.warning(f"   [CONTATO] _adicionar_contato_novo falhou: {str(e)[:80]}")
        time.sleep(2)
        resolvido = not self._alerta_contato_exige_adicao_manual(seletor)
        logger.info(f"   [CONTATO] '{label}' criado manualmente: {'OK' if resolvido else 'ainda com alerta'}")
        return resolvido

    def _adicionar_contato_novo(self, nome: str, cnpj: str | None = None,
                                 tipo_pessoa: str | None = None,
                                 dados_extra: dict | None = None,
                                 campo=None) -> bool:
        """Preenche o modal/formulário 'Criar novo contato' do LegalOne.

        Fluxo:
          1. Clica em 'Adicionar' no dropdown do campo autocomplete
          2. Aguarda formulário/modal aparecer (seletores amplos)
          3. Identifica o modal MAIS RECENTE (topmost) para evitar preencher modal errado
          4. Seleciona tipo de pessoa (PF/PJ) se o controle estiver visível
          5. Preenche nome/razão social se o campo estiver vazio
          6. Preenche CPF (PF) ou CNPJ (PJ); se ausente, preenche justificativa "Não fornecido"
          7. Clica Salvar
        """
        if not self.page:
            return False

        try:
            # 0. Fechar modais de CONTATO residuais de tentativas anteriores.
            # IMPORTANTE: NÃO incluir 'ngb-modal-window' aqui — o formulário principal
            # do processo também é um ngb-modal-window e não deve ser fechado.
            # Só fechar se houver mais de 1 ngb-modal-window (=1 além do form principal).
            try:
                resultado = self.page.evaluate(
                    """() => {
                        // Conta janelas ngb-modal além da primeira (form principal)
                        const janelas = Array.from(document.querySelectorAll('ngb-modal-window'))
                            .filter(el => el.offsetHeight > 0);
                        // Conta modais de contato específicos
                        const sels_contato = [
                            'app-add-contact-modal',
                            '[class*="contact-modal"]',
                            '[class*="add-contact"]'
                        ];
                        let contato_els = [];
                        for (const sel of sels_contato)
                            contato_els.push(...document.querySelectorAll(sel));
                        contato_els = [...new Set(contato_els)].filter(el => el.offsetHeight > 0);
                        return {janelas: janelas.length, contato: contato_els.length};
                    }"""
                )
                # Só fecha se tiver modal de contato específico OU mais de 1 ngb-modal-window
                n_extra = max(0, resultado.get('janelas', 0) - 1)  # modais além do form principal
                n_contato = resultado.get('contato', 0)
                n_fechar = max(n_extra, n_contato)
                if n_fechar > 0:
                    logger.warning(f"      ⚠ {n_fechar} modal(is) de contato residual(is) — fechando via Cancelar...")
                    # Usa "Cancelar" em vez de Escape para evitar confirmação do Angular
                    for tentativa in range(n_fechar + 2):
                        try:
                            # Clica "Cancelar" no modal de contato topmost
                            cancelar = self.page.locator('ngb-modal-window').last.get_by_role('button', name='Cancelar')
                            if cancelar.count() > 0 and cancelar.first.is_visible():
                                cancelar.first.click()
                                time.sleep(0.4)
                                # Se abriu confirmação de cancelamento, confirma
                                try:
                                    confirmar = self.page.get_by_role('button', name='Confirmar')
                                    if not confirmar.count():
                                        confirmar = self.page.get_by_role('button', name='Sim')
                                    if not confirmar.count():
                                        confirmar = self.page.get_by_role('button', name='OK')
                                    if confirmar.count() > 0 and confirmar.first.is_visible():
                                        confirmar.first.click()
                                        time.sleep(0.3)
                                except Exception:
                                    pass
                            else:
                                break  # sem mais modais de contato
                        except Exception:
                            break
                    time.sleep(0.4)
            except Exception:
                pass

            # 1. Clicar em "Adicionar" no dropdown
            logger.info(f"      ➕ Adicionando contato: {nome}")
            if not self._clicar_adicionar_no_dropdown(campo=campo, valor=nome):
                logger.error("      âŒ Botão 'Adicionar' não encontrado no dropdown")
                return False

            # 2. Aguarda formulário de adição aparecer
            #    Seletores amplos: IDs conhecidos + seletores genéricos de modal de contato
            seletores_form = [
                '#input-name',
                '#input-cpf-cnpj',
                'app-add-contact-modal',
                '#contact-form',
                '#naturalPerson-checkbox',
                '#legalPerson-checkbox',
                # Seletores genéricos para modal/dialog de criação de contato
                '[class*="add-contact"]',
                '[class*="contact-modal"]',
                '[class*="new-contact"]',
                'input[name="name"]',
                'input[name="razaoSocial"]',
                'input[name="cpfCnpj"]',
                'input[placeholder*="nome"]',
                'input[placeholder*="razão"]',
                'input[placeholder*="Nome"]',
                'input[placeholder*="Razão"]',
            ]
            seletor_form_str = ', '.join(seletores_form)

            form_ok = False
            for tentativa_form in range(3):
                try:
                    # Timeout generoso na 1ª tentativa — o modal pode demorar a animar
                    timeout = [8000, 5000, 3000][tentativa_form]
                    self.page.wait_for_selector(seletor_form_str, state='visible', timeout=timeout)
                    form_ok = True
                    break
                except Exception:
                    if tentativa_form < 2 and campo and nome:
                        # ANTES de clicar "Adicionar" de novo, verifica se o modal
                        # já está parcialmente aberto (animação em andamento).
                        # Se sim, aguarda mais em vez de criar um SEGUNDO popup.
                        modal_ja_existe = False
                        try:
                            # Usa querySelectorAll para capturar TODOS os modais—mesmo ocultos
                            modais_existentes = self.page.evaluate(
                                """
                                () => {
                                    const seletores = [
                                        'app-add-contact-modal',
                                        '#contact-form',
                                        '[class*="add-contact"]',
                                        '[class*="contact-modal"]',
                                        'ngb-modal-window'
                                    ];
                                    let todos = [];
                                    for (const sel of seletores) {
                                        todos = todos.concat(Array.from(document.querySelectorAll(sel)));
                                    }
                                    // Remove duplicatas
                                    todos = [...new Set(todos)];
                                    return todos.length;
                                }
                                """
                            )
                            if modais_existentes > 0:
                                modal_ja_existe = True
                                logger.info(
                                    f"      â³ {modais_existentes} modal(is) já presente(s) mas ainda carregando "
                                    f"(tentativa {tentativa_form + 1}). Aguardando mais tempo..."
                                )
                                time.sleep(2.0)  # Aumenta waittime para animação completar
                        except Exception:
                            pass

                        if not modal_ja_existe:
                            logger.warning(
                                f"      ⚠ Formulário não apareceu (tentativa {tentativa_form + 1}). "
                                "Reabrindo dropdown e clicando 'Adicionar' novamente..."
                            )
                            try:
                                campo.click()
                                time.sleep(0.3)
                                try:
                                    campo.press('ArrowDown')
                                except Exception:
                                    pass
                                time.sleep(0.5)
                            except Exception:
                                pass
                            self._clicar_adicionar_no_dropdown(campo=campo, valor=nome)
                    else:
                        break

            if not form_ok:
                logger.warning("      ⚠ Formulário de adição de contato não apareceu")
                return False

            logger.info("      ✅ Formulário de adição de contato detectado")

            # Identifica o modal mais recente (topmost) para escopar os próximos seletores
            modal_ativo = self._obter_modal_contato_ativo()
            if modal_ativo:
                logger.info("      🎯 Modal de contato ativo identificado (topmost)")
            else:
                logger.debug("      (modal_ativo não encontrado — usando seletores globais)")

            # 3. Selecionar tipo de pessoa (se controle visível)
            # resolve o tipo (documento > preferencia > heuristica de nome); nunca None
            tipo_pessoa = self._resolver_tipo_pessoa(nome, cnpj, tipo_pessoa)
            eh_pf = ('física' in tipo_pessoa.lower()) or ('fisica' in tipo_pessoa.lower())
            # Também detecta pelo documento: CPF = 11 dígitos
            digitos_doc = re.sub(r'\D', '', self._valor_limpo(cnpj) or '')
            if len(digitos_doc) == 11:
                eh_pf = True
            elif len(digitos_doc) == 14:
                eh_pf = False

            tipo_label = 'Pessoa Física' if eh_pf else 'Pessoa Jurídica'
            logger.info(f"      📋 Tipo: {tipo_label}")

            seletores_pf = ['#naturalPerson-checkbox', 'label:has-text("Pessoa Física")', 'input[value="PF"]', '[data-value="PF"]']
            seletores_pj = ['#legalPerson-checkbox', 'label:has-text("Pessoa Jurídica")', 'input[value="PJ"]', '[data-value="PJ"]']
            seletores_tipo = seletores_pf if eh_pf else seletores_pj
            tipo_confirmado = False

            for sel in seletores_tipo:
                try:
                    # Tenta dentro do modal ativo primeiro
                    el = None
                    if modal_ativo:
                        try:
                            el_h = self.page.evaluate_handle(
                                f"(modal) => modal.querySelector('{sel}')", modal_ativo
                            )
                            el = el_h.as_element() if el_h else None
                        except Exception:
                            pass
                    if not el:
                        el = self.page.wait_for_selector(sel, state='visible', timeout=1500)
                    if el and el.is_visible():
                        # force=True: ignora bloqueio de pointer events de modal externo
                        try:
                            el.click(force=True)
                        except Exception:
                            el.click()
                        logger.info(f"      ✓ Tipo selecionado: {tipo_label}")
                        break
                except Exception:
                    continue

            # O clique no controle customizado pode não trocar o radio de verdade.
            # Confirma o estado no DOM e tenta `check()` no input real antes de
            # preencher CPF/CNPJ; nunca continuar com máscara de CPF para uma PJ.
            tipo_id = '#naturalPerson-checkbox' if eh_pf else '#legalPerson-checkbox'
            try:
                modal_loc = self.page.locator('ngb-modal-window').last
                tipo_input = modal_loc.locator(tipo_id).first
                if tipo_input.count() > 0:
                    try:
                        tipo_input.check(force=True)
                    except Exception:
                        tipo_input.click(force=True)
                    time.sleep(0.4)
                    tipo_confirmado = bool(
                        self.page.evaluate(
                            f"(modal) => !!modal?.querySelector('{tipo_id}')?.checked",
                            self._obter_modal_contato_ativo() or modal_ativo,
                        )
                    )
            except Exception as e:
                logger.warning(f"      ⚠ Não foi possível confirmar {tipo_label}: {e}")

            if not tipo_confirmado:
                logger.error(
                    f"      âŒ {tipo_label} não ficou selecionada; cancelando criação "
                    "para não preencher documento no tipo incorreto."
                )
                return False

            # 4. Preencher nome/razão social (só se estiver vazio)
            # Re-adquire modal_ativo: o clique em PF/PJ pode ter causado re-render Angular.
            modal_ativo = self._obter_modal_contato_ativo() or modal_ativo

            # Verifica se o nome já está preenchido
            nome_ja_preenchido = False
            try:
                valor_atual = self.page.evaluate(
                    """
                    (modal) => {
                        const root = modal || document;
                        const el = root.querySelector('#input-name') ||
                                   root.querySelector('input[name="name"]') ||
                                   root.querySelector('input[placeholder*="nome" i]');
                        return el ? (el.value || '').trim() : '';
                    }
                    """,
                    modal_ativo
                )
                if valor_atual and nome.lower() in valor_atual.lower():
                    logger.info(f"      ℹ Nome já preenchido no modal: '{valor_atual}'")
                    nome_ja_preenchido = True
            except Exception:
                pass

            nome_preenchido = nome_ja_preenchido
            if not nome_preenchido:
                # Usa _preencher_no_modal para escopar ao modal ativo e evitar preencher modal errado.
                seletores_nome = [
                    '#input-name',
                    'input[formcontrolname="name"]',
                    'input[formcontrolname="nome"]',
                    'input[formcontrolname="razaoSocial"]',
                    'input[name="name"]',
                    'input[name="razaoSocial"]',
                    'input[aria-label*="Nome" i]',
                    'input[placeholder*="nome" i]',
                    'input[placeholder*="razão" i]',
                ]
                nome_preenchido = self._preencher_no_modal(modal_ativo, seletores_nome, nome, 'Nome')

                # Fallback JS: primeiro input de texto visível dentro do modal mais recente
                if not nome_preenchido:
                    try:
                        campo_nome = self.page.evaluate_handle("""() => {
                            // Usa o ÚLTIMO modal visível (topmost) para evitar preencher no modal errado
                            const candidatos = Array.from(document.querySelectorAll(
                                'app-add-contact-modal, [class*="add-contact"], [class*="contact-modal"], mat-dialog-container, .modal-dialog, dialog'
                            )).filter(el => el.offsetHeight > 0);
                            const root = candidatos.length > 0 ? candidatos[candidatos.length - 1] : document;
                            const inputs = Array.from(root.querySelectorAll('input[type="text"], input:not([type])'));
                            return inputs.find(el => {
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0 && !el.disabled && !el.readOnly;
                            }) || null;
                        }""")
                        if campo_nome:
                            el = campo_nome.as_element()
                            if el:
                                # force=True bypassa pointer event interception do modal externo
                                el.fill(nome, force=True)
                                logger.info(f"      ðŸ“ Nome preenchido via JS fallback (topmost modal): '{nome}'")
                                nome_preenchido = True
                    except Exception as e_js:
                        logger.debug(f"      JS fallback nome falhou: {e_js}")

            if not nome_preenchido:
                logger.warning(f"      ⚠ Campo de nome não encontrado no formulário")

            # 5. Preencher CPF/CNPJ
            documento = self._valor_limpo(cnpj)

            # Para PJ sem documento informado, tenta buscar CNPJ na web
            if not documento and not eh_pf:
                documento = self._buscar_cnpj_web(nome)

            # Helper: busca elemento dentro do modal_ativo primeiro, depois globalmente
            def _qs_modal(css: str):
                """query_selector escoped ao modal_ativo; fallback global."""
                if modal_ativo:
                    try:
                        h = self.page.evaluate_handle(
                            f"(m) => m.querySelector('{css}')", modal_ativo
                        )
                        el = h.as_element() if h else None
                        if el and el.is_visible():
                            return el
                    except Exception:
                        pass
                return self.page.query_selector(css)

            if documento:
                digitos_doc = re.sub(r'\D', '', documento)
                tipo_doc = 'CPF' if len(digitos_doc) == 11 else 'CNPJ'
                logger.info(f"      ðŸ“ {tipo_doc}: {documento}")

                # Antes de preencher, garante que o checkbox "não disponível" NÃO está marcado
                # — usa locator do modal para não tocar o checkbox do formulário externo
                try:
                    modal_loc_pre = self.page.locator('ngb-modal-window').last
                    for texto_cb in ['CPF não disponível', 'CNPJ não disponível', 'não disponível']:
                        lbl = modal_loc_pre.get_by_text(texto_cb, exact=False)
                        if lbl.count() > 0 and lbl.first.is_visible():
                            cb_i = lbl.first.locator('input[type="checkbox"]')
                            if cb_i.count() > 0 and cb_i.first.is_checked():
                                cb_i.first.click()
                                logger.info("      ↩ Desmarcando 'não disponível' para preencher documento")
                                time.sleep(0.3)
                            break
                except Exception:
                    pass

                seletores_doc = [
                    '#input-cpf-cnpj',
                    'input[formcontrolname="cpfCnpj"]',
                    'input[formcontrolname="cpf"]',
                    'input[formcontrolname="cnpj"]',
                    'input[name="cpfCnpj"]',
                    'input[placeholder*="CPF" i]',
                    'input[placeholder*="CNPJ" i]',
                    'input[placeholder*="documento" i]',
                ]
                doc_preenchido = self._preencher_no_modal(modal_ativo, seletores_doc, documento, tipo_doc)
                if doc_preenchido:
                    logger.info(f"      ✓ {tipo_doc} preenchido")
            else:
                # Marca checkbox "CPF não disponível" usando JavaScript puro no modal topmost.
                # JS evita problemas de encoding (ã, õ) em seletores Playwright/CSS.
                logger.info("      ☑ Marcando 'CPF não disponível'")
                marcado = False

                # Passo 1: clica no campo CPF para revelar o checkbox (Angular lazy render)
                try:
                    self.page.evaluate("""
                        () => {
                            const modals = document.querySelectorAll('ngb-modal-window');
                            const modal = modals[modals.length - 1];
                            if (!modal) return;
                            const cpf = modal.querySelector('#input-cpf-cnpj')
                                     || modal.querySelector('input[formcontrolname="cpfCnpj"]')
                                     || modal.querySelector('input[formcontrolname="cpf"]');
                            if (cpf) { cpf.focus(); cpf.click(); }
                        }
                    """)
                    time.sleep(0.7)
                except Exception:
                    time.sleep(0.3)

                # Passo 2: JS — encontra e clica o checkbox de "não disponível" no modal topmost
                marcado = self.page.evaluate("""
                    () => {
                        const modals = document.querySelectorAll('ngb-modal-window');
                        const modal = modals[modals.length - 1];
                        if (!modal) return false;

                        const checkboxes = Array.from(modal.querySelectorAll('input[type="checkbox"]'))
                            .filter(cb => cb.offsetParent !== null);  // apenas visíveis

                        for (const cb of checkboxes) {
                            // Busca label associada (filho, pai, ou for=id)
                            const lbl = cb.closest('label')
                                     || document.querySelector('label[for="' + cb.id + '"]')
                                     || cb.parentElement;
                            const txt = lbl ? (lbl.innerText || lbl.textContent || '').toLowerCase() : '';
                            if (txt.includes('n') && txt.includes('o dispon')) {
                                // "não disponível" / "nao disponivel"
                                if (!cb.checked) {
                                    cb.click();
                                }
                                return true;
                            }
                        }

                        // Fallback: clica o primeiro checkbox visível e desmarcado no modal
                        for (const cb of checkboxes) {
                            if (!cb.checked) {
                                cb.click();
                                return 'fallback';
                            }
                        }
                        return false;
                    }
                """)
                if marcado:
                    logger.info(f"      ✓ 'CPF não disponível' marcado via JS (resultado: {marcado})")
                    marcado = True
                    time.sleep(0.6)  # aguarda Angular renderizar campo Motivo
                else:
                    logger.warning("      ⚠ Não foi possível marcar 'CPF não disponível' via JS")

                # Fallback Playwright: checkbox via JS pode não disparar Angular change detection.
                # Verifica se realmente está checked; se não, usa Playwright click.
                if marcado:
                    try:
                        cb_real_checked = self.page.evaluate("""
                            () => {
                                const modals = document.querySelectorAll('ngb-modal-window');
                                const modal = modals[modals.length - 1];
                                if (!modal) return null;
                                const cbs = Array.from(modal.querySelectorAll('input[type="checkbox"]'))
                                    .filter(cb => cb.offsetParent !== null);
                                for (const cb of cbs) {
                                    const lbl = cb.closest('label')
                                             || document.querySelector('label[for="' + cb.id + '"]')
                                             || cb.parentElement;
                                    const txt = lbl ? (lbl.innerText || '').toLowerCase() : '';
                                    if (txt.includes('n') && txt.includes('o dispon')) {
                                        return cb.checked;
                                    }
                                }
                                return null;
                            }
                        """)
                        if cb_real_checked is False:
                            logger.info("      ↩ Checkbox não ficou marcado via JS. Tentando Playwright click...")
                            modal_loc = self.page.locator('ngb-modal-window').last
                            for txt_cb in ['CPF não disponível', 'CNPJ não disponível', 'não disponível']:
                                lbl_loc = modal_loc.get_by_text(txt_cb, exact=False)
                                if lbl_loc.count() > 0 and lbl_loc.first.is_visible():
                                    lbl_loc.first.click()
                                    time.sleep(0.5)
                                    logger.info("      ✓ Checkbox marcado via Playwright click no label")
                                    break
                    except Exception:
                        pass

                # Após marcar, preenche campo "Motivo *" que aparece dinamicamente
                if marcado:
                    # JS puro: preenche o campo Motivo (justificativa) do modal.
                    # Valor vem do Python em UTF-8 (evita mojibake); padrao = exemplo do usuario.
                    motivo_sem_cpf = os.getenv('LEGALONE_MOTIVO_SEM_CPF', 'Recusou-se a fornecer documentação')
                    preencheu_justif = self.page.evaluate("""
                        (VALOR) => {
                            const modals = document.querySelectorAll('ngb-modal-window');
                            const modal = modals[modals.length - 1];
                            if (!modal) return false;

                            const EXCLUIR_IDS = ['input-name', 'input-cpf-cnpj'];

                            // Tenta por formcontrolname ou placeholder conhecidos primeiro
                            const SELS = [
                                'input[formcontrolname="reason"]',
                                'input[formcontrolname="motivo"]',
                                'input[formcontrolname="justify"]',
                                'input[formcontrolname="justificativa"]',
                                'textarea[formcontrolname="reason"]',
                                'textarea[formcontrolname="motivo"]',
                                'textarea[formcontrolname="justify"]',
                            ];
                            for (const sel of SELS) {
                                const el = modal.querySelector(sel);
                                if (el && el.offsetParent !== null && !el.disabled) {
                                    const setter = Object.getOwnPropertyDescriptor(
                                        window.HTMLInputElement.prototype, 'value'
                                    ) || Object.getOwnPropertyDescriptor(
                                        window.HTMLTextAreaElement.prototype, 'value'
                                    );
                                    if (setter && setter.set) setter.set.call(el, VALOR);
                                    else el.value = VALOR;
                                    el.dispatchEvent(new InputEvent('input', {bubbles: true}));
                                    el.dispatchEvent(new Event('change', {bubbles: true}));
                                    return sel;
                                }
                            }

                            // Fallback: qualquer input/textarea vazio visível (exceto nome e cpf)
                            const inputs = Array.from(modal.querySelectorAll('input[type="text"], input:not([type]), textarea'))
                                .filter(el => el.offsetParent !== null
                                           && !el.disabled
                                           && !EXCLUIR_IDS.includes(el.id)
                                           && !(el.value || '').trim());
                            for (const el of inputs) {
                                const setter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ) || Object.getOwnPropertyDescriptor(
                                    window.HTMLTextAreaElement.prototype, 'value'
                                );
                                if (setter && setter.set) setter.set.call(el, VALOR);
                                else el.value = VALOR;
                                el.dispatchEvent(new InputEvent('input', {bubbles: true}));
                                el.dispatchEvent(new Event('change', {bubbles: true}));
                                return 'fallback:' + (el.id || el.name || el.className);
                            }
                            return false;
                        }
                    """, motivo_sem_cpf)
                    if preencheu_justif:
                        logger.info(f"      ✓ Motivo preenchido via JS ({preencheu_justif})")
                        time.sleep(0.3)
                    else:
                        logger.warning("      ⚠ Campo 'Motivo' não encontrado — tentando continuar")

            # 5.5. Verificação pré-Save: Angular pode ter ignorado JS/fill. Re-preenche campos vazios via teclado.
            try:
                modal_ativo_pre = self._obter_modal_contato_ativo() or modal_ativo
                campos_vazios = self.page.evaluate("""
                    (modal) => {
                        const root = modal || document;
                        const result = {};
                        const nameEl = root.querySelector('#input-name')
                                    || root.querySelector('input[formcontrolname="name"]')
                                    || root.querySelector('input[name="name"]');
                        if (nameEl && !(nameEl.value || '').trim()) result.nome = true;

                        // Verifica se campo de justificativa está vazio (quando visível)
                        const justSels = [
                            'input[formcontrolname="reason"]', 'input[formcontrolname="justificativa"]',
                            '#input-justification', 'input[id*="justif"]', 'input[id*="reason"]'
                        ];
                        for (const s of justSels) {
                            const el = root.querySelector(s);
                            if (el && el.offsetParent !== null && !el.disabled && !(el.value || '').trim()) {
                                result.justificativa = true;
                                break;
                            }
                        }
                        return result;
                    }
                """, modal_ativo_pre)

                if campos_vazios and campos_vazios.get('nome'):
                    logger.info("      ⚠ Nome vazio pré-Save! Re-preenchendo via teclado...")
                    nome_el = self.page.locator('ngb-modal-window').last.locator('#input-name, input[formcontrolname="name"], input[name="name"]').first
                    if nome_el.count() > 0 and nome_el.is_visible():
                        nome_el.click(force=True)
                        time.sleep(0.2)
                        nome_el.press_sequentially(nome, delay=30)
                        time.sleep(0.3)
                        logger.info(f"      ✓ Nome re-preenchido via teclado: '{nome}'")

                if campos_vazios and campos_vazios.get('justificativa'):
                    logger.info("      ⚠ Justificativa vazia pré-Save! Re-preenchendo via teclado...")
                    modal_loc2 = self.page.locator('ngb-modal-window').last
                    justif_sels = ['input[formcontrolname="reason"]', 'input[formcontrolname="justificativa"]',
                                   '#input-justification', 'input[id*="justif"]', 'input[id*="reason"]']
                    for js in justif_sels:
                        jel = modal_loc2.locator(js).first
                        if jel.count() > 0 and jel.is_visible():
                            jel.click(force=True)
                            time.sleep(0.1)
                            jel.press_sequentially('Não fornecido', delay=30)
                            time.sleep(0.3)
                            logger.info("      ✓ Justificativa re-preenchida via teclado")
                            break
            except Exception as e_pre:
                logger.debug(f"      Verificação pré-Save falhou: {e_pre}")

            # 6. Clicar Salvar — OBRIGATORIAMENTE dentro do modal de contato
            logger.info("      💾 Salvando contato...")

            # Verifica erros de validação SOMENTE dentro do modal ativo
            try:
                erros_validacao = self.page.evaluate(
                    """
                    (modal) => {
                        const root = modal || document;
                        const erros = [];
                        const seletores = [
                            '.error-message', '.field-error', '.validation-error',
                            '.bento-form-error', '.invalid-feedback', '.has-error .help-block',
                            '.alert-danger', '.text-danger',
                        ];
                        for (const sel of seletores) {
                            for (const el of root.querySelectorAll(sel)) {
                                const txt = (el.innerText || '').trim();
                                if (txt && el.offsetHeight > 0) erros.push(txt);
                            }
                        }
                        return erros;
                    }
                    """,
                    modal_ativo,
                )
                if erros_validacao:
                    for err in erros_validacao[:5]:
                        logger.warning(f"      ⚠ Validação (modal): {err}")
            except Exception:
                pass

            # Encontra o botão Salvar DENTRO DO MODAL para não clicar no botão do form externo
            btn_salvar_modal = None
            try:
                btn_salvar_modal = self.page.evaluate_handle(
                    """
                    (modal) => {
                        const root = modal || document;
                        const textos = ['salvar', 'cadastrar', 'confirmar', 'register'];
                        // Prioriza botões submit ou com texto específico dentro do modal
                        const candidatos = Array.from(root.querySelectorAll('button, [role="button"]'));
                        return candidatos.find(b => {
                            if (!b.offsetHeight) return false;
                            const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                            return textos.some(t => txt.includes(t)) || b.type === 'submit';
                        }) || null;
                    }
                    """,
                    modal_ativo,
                )
                btn_salvar_modal = btn_salvar_modal.as_element() if btn_salvar_modal else None
            except Exception:
                pass

            seletores_salvar = [
                '#modal-register',
                'button:has-text("Salvar")',
                'button:has-text("Cadastrar")',
                'button:has-text("Confirmar")',
                'button[type="submit"]',
                '[class*="save"]:has-text("Salvar")',
            ]
            salvo = False
            # Itera: primeiro tenta btn_salvar_modal (escoped), depois fallback lista
            candidatos_salvar = (
                [(btn_salvar_modal, 'modal-scoped')] if btn_salvar_modal
                else []
            )
            for sel_salvar in seletores_salvar:
                try:
                    b = _qs_modal(sel_salvar) or self.page.query_selector(sel_salvar)
                    if b:
                        candidatos_salvar.append((b, sel_salvar))
                except Exception:
                    pass

            for btn_salvar, origem_sel in candidatos_salvar:
                try:
                    # Aguarda o botão habilitar (até 5s)
                    habilitado = False
                    try:
                        for _ in range(10):
                            if btn_salvar.is_visible():
                                # Verifica se o botão tem a classe 'disabled' ou atributo 'disabled'
                                is_disabled = self.page.evaluate('(btn) => btn.disabled || btn.classList.contains("disabled")', btn_salvar)
                                if not is_disabled:
                                    habilitado = True
                                    break
                            time.sleep(0.5)
                    except Exception:
                        habilitado = True  # assume habilitado se não consegue verificar

                    if not habilitado:
                        logger.warning(f"      ⚠ Botão Salvar ({origem_sel}) está desabilitado")
                        
                        # Tenta forçar a habilitação do botão via JS
                        try:
                            self.page.evaluate('(btn) => { btn.disabled = false; btn.classList.remove("disabled"); }', btn_salvar)
                            logger.info(f"      ℹ Tentativa de forçar habilitação do botão Salvar via JS")
                        except Exception:
                            pass
                            
                        try:
                            os.makedirs("logs", exist_ok=True)
                            nome_arquivo = f"logs/contato_salvar_disabled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            self.page.screenshot(path=nome_arquivo, full_page=False)
                            logger.info(f"      📸 Screenshot salva: {nome_arquivo}")
                        except Exception:
                            pass
                        try:
                            btn_salvar.click(force=True)
                        except Exception:
                            pass
                        continue

                    # force=True: bypassa bloqueio de pointer events de modal externo empilhado
                    # ANTES de clicar, tenta fechar modais não-topmost para evitar conflitos
                    try:
                        modais_count = self.page.evaluate(
                            """
                            () => {
                                // Conta apenas ngb-modal-windows ALÉM do form principal (idx > 0)
                                const janelas = Array.from(document.querySelectorAll('ngb-modal-window'))
                                    .filter(el => el.offsetHeight > 0);
                                return janelas.length;
                            }
                            """
                        )
                        if modais_count > 2:  # >2 = mais de main-form + contact-form
                            logger.warning(
                                f"      ⚠ {modais_count} modais abertos! Tentando fechar os não-topmost..."
                            )
                            # Tenta fechar modais background clicando X ou Cancelar
                            try:
                                self.page.evaluate(
                                    """
                                    () => {
                                        const seletores_fechar = [
                                            'button:has-text("Cancelar")',
                                            'button:has-text("Fechar")',
                                            '[aria-label*="close" i]',
                                            '[aria-label*="Fechar" i]',
                                            '.modal-header button.close',
                                            'button.close',
                                        ];
                                        for (const sel of seletores_fechar) {
                                            const btns = Array.from(document.querySelectorAll(sel));
                                            // Clica em todos EXCETO o último (que é o topmost)
                                            for (let i = 0; i < btns.length - 1; i++) {
                                                if (btns[i].offsetHeight > 0) {
                                                    btns[i].click();
                                                }
                                            }
                                        }
                                    }
                                    """
                                )
                                time.sleep(0.5)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    try:
                        btn_salvar.click(force=True)
                    except Exception:
                        btn_salvar.click()

                    # Aguarda modal fechar
                    modal_fechou = False
                    try:
                        # Verifica de forma mais robusta: se o modal topmost desaparece OU fica hidden
                        topmost_modal = self.page.evaluate(
                            """
                            () => {
                                const seletores = [
                                    'app-add-contact-modal',
                                    '#contact-form',
                                    '[class*="add-contact"]',
                                    '[class*="contact-modal"]',
                                    'ngb-modal-window'
                                ];
                                let ultimo = null;
                                for (const sel of seletores) {
                                    const todos = Array.from(document.querySelectorAll(sel));
                                    const visiveis = todos.filter(el => el.offsetHeight > 0);
                                    if (visiveis.length > 0) {
                                        ultimo = visiveis[visiveis.length - 1];
                                    }
                                }
                                return ultimo ? true : false;
                            }
                            """
                        )
                        if not topmost_modal:
                            modal_fechou = True
                        else:
                            # Tenta aguardar com timeout menor
                            try:
                                self.page.wait_for_selector(
                                    'app-add-contact-modal, #contact-form, [class*="add-contact"], [class*="contact-modal"]',
                                    state='hidden',
                                    timeout=3000
                                )
                                modal_fechou = True
                            except Exception:
                                pass
                    except Exception:
                        pass

                    if modal_fechou:
                        logger.info("      ✅ Contato criado com sucesso!")
                        salvo = True
                        break
                    else:
                        # Modal ainda aberto — verifica erros DENTRO do modal ativo
                        logger.warning("      ⚠ Modal ainda aberto após clique em Salvar - verificando erros...")
                        try:
                            erros_pos = self.page.evaluate(
                                """
                                (modal) => {
                                    const root = modal || document;
                                    const erros = [];
                                    const seletores = [
                                        '.error-message', '.field-error', '.validation-error',
                                        '.bento-form-error', '.invalid-feedback',
                                        '.alert-danger', '.text-danger', '.toast-error',
                                    ];
                                    for (const sel of seletores) {
                                        for (const el of root.querySelectorAll(sel)) {
                                            const txt = (el.innerText || '').trim();
                                            if (txt && el.offsetHeight > 0) erros.push(txt);
                                        }
                                    }
                                    return erros;
                                }
                                """,
                                modal_ativo,
                            )
                            if erros_pos:
                                for err in erros_pos[:5]:
                                    logger.error(f"      âŒ Erro pós-salvar (modal): {err}")
                        except Exception:
                            pass
                        try:
                            os.makedirs("logs", exist_ok=True)
                            nome_arquivo = f"logs/contato_salvar_falha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            self.page.screenshot(path=nome_arquivo, full_page=False)
                            logger.info(f"      📸 Screenshot salva: {nome_arquivo}")
                        except Exception:
                            pass
                        continue
                except Exception:
                    continue

            if salvo:
                return True

            logger.error("      âŒ Botão Salvar do modal não encontrado ou não funcionou")
            # Screenshot final de diagnóstico
            try:
                os.makedirs("logs", exist_ok=True)
                nome_arquivo = f"logs/contato_salvar_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.page.screenshot(path=nome_arquivo, full_page=False)
                logger.info(f"      📸 Screenshot final: {nome_arquivo}")
            except Exception:
                pass

            # --- FALLBACK INTELIGENTE: browser-use ---
            if _bu_fallback and _bu_fallback.is_available():
                logger.info("      🤖 Acionando fallback inteligente (browser-use)...")
                if _bu_fallback.fallback_salvar_contato(
                    page=self.page,
                    nome=nome,
                    tipo_pessoa=tipo_label,
                    documento=documento,
                ):
                    return True
                logger.warning("      ⚠ Fallback inteligente também falhou")

            return False

        except Exception as e:
            logger.error(f"      âŒ Erro ao adicionar contato: {e}")
            # Fecha modal se aberto
            try:
                self.page.click('#modal-close-button, #modal-close-x, button:has-text("Fechar"), button:has-text("Cancelar")', timeout=2000)
            except Exception:
                pass
            return False

    def _verificar_contexto_cadastro(self, expected_cnj: str, etapa: str) -> bool:
        if not self.require_context:
            return True
        if not self.page:
            return False

        wait_ms = int(os.getenv("LEGALONE_CONTEXT_WAIT_MS", "30000"))
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=wait_ms)
        except Exception:
            pass

        try:
            objetivo = (
                f"Verificar se a página atual corresponde ao processo CNJ {expected_cnj} e está pronta para cadastro."
                f" Etapa: {etapa}."
            )
            if self.use_agentql and self.agentql_api_key and agentql is not None:
                self._agentql_context(objetivo)
            else:
                logger.debug("[CONTEXTO] Usando heurísticas locais (AgentQL não ativo).")
        except Exception:
            pass

        try:
            esperado = self._normalizar_cnj(expected_cnj)
            if not esperado:
                return True

            inicio = time.time()
            while (time.time() - inicio) * 1000 < wait_ms:
                try:
                    texto = self.page.inner_text("body")
                except Exception:
                    texto = self.page.content()

                if esperado in self._normalizar_cnj(texto):
                    return True

                # Fallback: se já estamos no formulário (campos do cadastro visíveis),
                # aceita o contexto mesmo sem CNJ no body.
                seletores_form = [
                    '#input-main-customer-3-input',
                    'input[id*="main-customer"]',
                    'input[id*="process"]',
                    'input[id*="customer"]',
                ]
                for sel in seletores_form:
                    try:
                        if self.page.is_visible(sel):
                            logger.warning(f"⚠ CNJ não apareceu, mas formulário detectado ({sel}). Continuando.")
                            return True
                    except Exception:
                        continue

                # Heurística adicional: busca botões e labels típicos do cadastro
                try:
                    heuristica = self.page.evaluate(
                        """
                        () => {
                            const labels = Array.from(document.querySelectorAll('label'))
                                .map(l => (l.innerText || '').toLowerCase());
                            const hasLabel = (txt) => labels.some(l => l.includes(txt));
                            const hasSalvar = Array.from(document.querySelectorAll('button, [role="button"], a'))
                                .some(b => (b.innerText || '').toLowerCase().includes('salvar'));
                            return hasLabel('cliente') || hasLabel('posição') || hasLabel('contrário') || hasSalvar;
                        }
                        """
                    )
                    if heuristica:
                        logger.warning("⚠ Contexto inferido por heurística (labels/botões). Continuando.")
                        return True
                except Exception:
                    pass

                time.sleep(1)

            logger.error(f"âŒ Contexto inválido: CNJ {expected_cnj} não encontrado na página ({etapa}).")
            return False
        except Exception as e:
            logger.warning(f"[CONTEXTO] Falha ao validar contexto: {e}")
            return False
        return True

    def _agentql_context(self, objetivo: str):
        if not self.use_agentql:
            return
        if not self.agentql_api_key:
            logger.warning("[AGENTQL] API key ausente. Defina AGENTQL_API_KEY.")
            return
        if not self.page:
            return
        try:
            html = self.page.content()
            url = self.page.url
            title = self.page.title()

            if agentql and hasattr(agentql, "AgentQL"):
                client = agentql.AgentQL(api_key=self.agentql_api_key)
                result = client.query(
                    {
                        "url": url,
                        "title": title,
                        "html": html,
                        "objective": objetivo,
                    }
                )
            elif agentql and hasattr(agentql, "query"):
                result = agentql.query(
                    api_key=self.agentql_api_key,
                    url=url,
                    title=title,
                    html=html,
                    objective=objetivo,
                )
            else:
                if not getattr(self, '_agentql_sdk_warned', False):
                    logger.debug("[AGENTQL] SDK não instalado. Usando heurísticas locais.")
                    self._agentql_sdk_warned = True
                return

            resumo = str(result)
            if len(resumo) > 2000:
                resumo = resumo[:2000] + "..."
            logger.info(f"[AGENTQL] Contexto: {resumo}")
        except Exception as e:
            logger.warning(f"[AGENTQL] Falha ao analisar contexto: {e}")

    def garantir_sessao_ativa(self):
        """Inicializa navegador ou recarrega se necessário"""
        if self.page and not self.page.is_closed():
            try:
                # Verifica se ainda está logado/ativo checando URL ou Title
                title = self.page.title()
                logger.info(f"[SESSAO] Navegador ativo. Título: {title}")
                return True
            except:
                logger.warning("[SESSAO] Página parece fechada, reiniciando...")

        return self.inicializar_navegador()

    def inicializar_navegador(self):
        """Abre navegador e faz login"""
        try:
            logger.info("[INIT] Inicializando navegador LegalOne...")

            # Garante limpeza de referências antigas
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            self.context = None
            self.browser = None
            self.page = None

            if self.playwright is None:
                self.playwright = sync_playwright().start()

            self.temp_user_data_dir = tempfile.mkdtemp(prefix="legalone_pw_")

            _headed = os.getenv("LEGALONE_HEADED", "").strip().lower() in ("1", "true", "sim")
            _topo = [
                # perfil principal (logado) com Chrome real e visivel; so funciona sem
                # outro chrome.exe segurando o perfil -> matar antes de rodar
                ("VISIVEL chrome (perfil principal)", self.user_data_dir, False, "chrome"),
            ] if _headed else []
            # LEGALONE_HEADLESS=1 poe as tentativas sem janela na frente. Sem isso a
            # primeira tentativa e' sempre visual, mesmo com LEGALONE_HEADED vazio.
            # ponytail: sem janela os campos bento-combobox podem nao commitar (foi o
            # que travou a VM Linux) — usar so quando a janela incomodar de verdade.
            _sem_janela = os.getenv("LEGALONE_HEADLESS", "").strip().lower() in ("1", "true", "sim")
            _ordem_headless = [
                ("perfil principal headless", self.user_data_dir, True, "chrome"),
                ("perfil alternativo headless", self.fallback_user_data_dir, True, None),
            ] if _sem_janela else []
            tentativas = _topo + _ordem_headless + [
                ("perfil principal visual", self.user_data_dir, False, "chrome"),
                ("perfil principal headless", self.user_data_dir, True, "chrome"),
                ("perfil alternativo visual", self.fallback_user_data_dir, False, None),
                ("perfil alternativo headless", self.fallback_user_data_dir, True, None),
                ("perfil temporario visual", self.temp_user_data_dir, False, None),
                ("perfil temporario headless", self.temp_user_data_dir, True, None),
            ]

            ultimo_erro = None
            erros = []
            for descricao, data_dir, headless, channel in tentativas:
                try:
                    logger.info(f"[INIT] Tentando iniciar ({descricao})...")
                    self.context = self._iniciar_contexto_persistente(
                        user_data_dir=data_dir,
                        headless=headless,
                        channel=channel,
                    )
                    logger.info(f"[INIT] Navegador iniciado com sucesso ({descricao})")
                    break
                except Exception as e:
                    ultimo_erro = e
                    erros.append(e)
                    primeira_linha = str(e).splitlines()[0] if str(e) else repr(e)
                    logger.warning(f"[INIT] Falha ({descricao}): {primeira_linha}")
                    continue

            # Retry automático quando o binário do navegador não está disponível
            if not self.context and any(self._erro_indica_navegador_ausente(e) for e in erros):
                if self._instalar_chromium_playwright():
                    try:
                        logger.info("[INIT] Retentando com Chromium após instalação...")
                        self.context = self._iniciar_contexto_persistente(
                            user_data_dir=self.temp_user_data_dir,
                            headless=True,
                            channel=None,
                        )
                        logger.info("[INIT] Navegador iniciado com sucesso (retry pós-instalação)")
                    except Exception as e:
                        ultimo_erro = e
                        primeira_linha = str(e).splitlines()[0] if str(e) else repr(e)
                        logger.warning(f"[INIT] Falha no retry pós-instalação: {primeira_linha}")

            if not self.context:
                raise RuntimeError(f"Falha em todas as tentativas de iniciar navegador: {ultimo_erro}")

            # Em persistent context, browser e context são o mesmo objeto
            self.browser = self.context
            paginas = [p for p in self.context.pages if p and not p.is_closed()]
            self.page = paginas[-1] if paginas else self.context.new_page()
            # VM pequena + LegalOne pesado: 30s (default) estoura na navegacao
            try:
                tmo = float(os.getenv('LEGALONE_TIMEOUT_MS', '90000'))
                self.context.set_default_navigation_timeout(tmo)
                self.context.set_default_timeout(tmo)
            except Exception:
                pass

            self._espionar_requests()

            # Tenta acessar URL simplificada para validar sessão
            logger.info("ðŸ” Acessando LegalOne...")
            self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
            time.sleep(3)
            self._agentql_context("Identificar a tela atual do LegalOne (login ou sessão ativa) e elementos principais.")

            # Verifica se caiu na tela de login
            if (
                "signon.thomsonreuters.com" in self.page.url
                or "auth.thomsonreuters.com" in self.page.url
                or "Sign In" in self.page.title()
            ):
                return self.fazer_login()
            else:
                logger.info("✅ Sessão recuperada com sucesso!")
                return True

        except Exception as e:
            logger.error(f"âŒ Erro ao inicializar: {e}")
            return False

    def _fazer_login_signon_legacy(self):
        username_field = self.page.wait_for_selector('input:visible', timeout=10000)
        if username_field:
            username_field.click()
            time.sleep(0.5)
            try:
                username_field.fill(self.username)
            except Exception:
                logger.info("   Login antigo redirecionou para Auth; tentando fluxo novo")
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                time.sleep(1)
                return self._fazer_login_auth_thomson()
            logger.info("   OK Usuario preenchido (Legal One Firm)")

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        time.sleep(2)

        # Auth0 re-renderiza o form após a navegação; page.fill re-localiza o
        # campo a cada tentativa (handle antigo fica "not attached to the DOM")
        pwd_sel = 'input#password, input[name="password"], input[type="password"]'
        self.page.wait_for_selector(pwd_sel, timeout=15000)
        ultimo_erro = None
        for _ in range(3):
            try:
                if hasattr(self.page, 'fill'):
                    self.page.fill(pwd_sel, self.password, timeout=10000)
                else:  # paginas sem API de fill (ex.: dubles de teste)
                    self.page.wait_for_selector(pwd_sel, timeout=10000).fill(self.password)
                ultimo_erro = None
                break
            except Exception as e:
                ultimo_erro = e
                time.sleep(1.5)
        if ultimo_erro:
            raise ultimo_erro
        logger.info("   OK Senha preenchida (Legal One Firm)")

        try:
            login_btn = self.page.wait_for_selector(
                'button._button-login-password, button[name="action"][type="submit"]',
                timeout=10000,
            )
        except Exception:
            login_btn = self.page.wait_for_selector(
                'button[type="submit"], input[type="submit"]',
                timeout=10000,
            )
        if login_btn:
            login_btn.click()
            logger.info("   OK Botao Login clicado (Legal One Firm)")

        logger.info("Aguardando autenticacao...")
        time.sleep(8)
        logger.info("Sessao sera mantida automaticamente")
        return True

    def _fazer_login_auth_thomson(self):
        try:
            username_field = self.page.wait_for_selector(
                'input#username, input[name="username"], input[type="email"]',
                timeout=15000,
            )
        except Exception:
            logger.info("   Campo de email ainda nao carregou; aguardando redirecionamento")
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            time.sleep(2)
            try:
                username_field = self.page.wait_for_selector(
                    'input#username, input[name="username"], input[type="email"]',
                    timeout=10000,
                )
            except Exception:
                logger.info("   Tela Legal One Firm detectada; usando login legado")
                return self._fazer_login_signon_legacy()
        if username_field:
            username_field.click()
            time.sleep(0.5)
            try:
                username_field.fill(self.username)
            except Exception:
                current_url = ""
                try:
                    current_url = self.page.url or ""
                except Exception:
                    pass
                if "/login/password" not in current_url.lower():
                    raise
                logger.info("   Email aceito; tela de senha carregou durante o preenchimento")
            logger.info("   OK Email preenchido")

        current_url = ""
        try:
            current_url = self.page.url or ""
        except Exception:
            pass
        if "/login/password" not in current_url.lower():
            email_btn = self.page.wait_for_selector(
                'button._button-login-id, button[name="action"][type="submit"]',
                timeout=10000,
            )
            if email_btn:
                email_btn.click()
                logger.info("   OK Botao Entrar do email clicado")

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

        time.sleep(1)

        password_field = self.page.wait_for_selector(
            'input#password, input[name="password"], input[type="password"]',
            timeout=15000,
        )
        if password_field:
            password_field.click()
            time.sleep(0.5)
            password_field.fill(self.password)
            logger.info("   OK Senha preenchida")

        time.sleep(1)

        login_btn = self.page.wait_for_selector(
            'button._button-login-password, button[name="action"][type="submit"]',
            timeout=10000,
        )
        if login_btn:
            login_btn.click()
            logger.info("   OK Botao Entrar da senha clicado")

        logger.info("Aguardando autenticacao...")
        time.sleep(8)
        logger.info("Sessao sera mantida automaticamente")
        return True

    def fazer_login(self):
        """Realiza login no LegalOne"""
        try:
            return self._fazer_login_auth_thomson()
            logger.info("🔑 Realizando login manual...")

            # Usuário
            try:
                username_field = self.page.wait_for_selector(
                    'input#username, input[name="username"], input[type="email"]',
                    timeout=15000,
                )
            except Exception:
                logger.info("   Tela Legal One Firm detectada; usando login legado")
                return self._fazer_login_signon_legacy()
            if username_field:
                username_field.click()
                time.sleep(0.5)
                username_field.fill(self.username)
                logger.info("   OK Email preenchido")

            email_btn = self.page.wait_for_selector(
                'button._button-login-id, button[name="action"][type="submit"]',
                timeout=10000,
            )
            if email_btn:
                email_btn.click()
                logger.info("   OK Botao Entrar do email clicado")

            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
                logger.info("   ✓ Usuário preenchido")

            time.sleep(1)

            # Senha
            password_field = self.page.wait_for_selector(
                'input#password, input[name="password"], input[type="password"]',
                timeout=15000,
            )
            if password_field:
                password_field.click()
                time.sleep(0.5)
                password_field.fill(self.password)
                logger.info("   ✓ Senha preenchida")

            time.sleep(1)

            # Login
            login_btn = self.page.wait_for_selector(
                'button._button-login-password, button[name="action"][type="submit"]',
                timeout=10000,
            )
            if login_btn:
                login_btn.click()
                logger.info("   ✓ Botão Sign In clicado")

            logger.info("â³ Aguardando autenticação...")
            time.sleep(8)

            # Persistent context salva cookies automaticamente no user_data_dir
            logger.info("💾 Sessão será mantida automaticamente")

            return True

        except Exception as e:
            logger.error(f"âŒ Erro no login: {e}")
            return False

    def navegar_cadastro_cnj(self):
        """Navega até cadastro automático por CNJ"""
        try:
            if not self._ensure_page_active():
                logger.error("âŒ Página inativa ao navegar para cadastro")
                return False

            logger.info("\n📂 Navegando para cadastro...")
            time.sleep(2)

            # 1. Garantir que estamos na lista de Processos
            if "processos/search" not in self.page.url and "processos" not in self.page.url:
                logger.info("1ï¸âƒ£  Indo para lista de Processos...")
                try:
                    self.page.click('a[href*="/processos/processos"]', timeout=4000)
                except:
                    logger.warning("   (Menu lateral não encontrado, tentando rota alternativa...)")
                    # Tenta ir para home primeiro se falhar
                    self.page.goto("https://carvalhofurtadoadv.novajus.com.br/processos/processos/search")

            time.sleep(4)
            self._agentql_context("Mapear a página de processos e localizar ações principais (Adicionar, filtros, lista).")

            # 2. Interagir com menu Adicionar
            logger.info("2ï¸âƒ£  Interagindo com menu 'Adicionar'...")

            seletores_adicionar = [
                'span.add-popover-menu:has-text("Adicionar")',
                '.add-popover-menu',
                'span:has-text("Adicionar")',
            ]

            menu_aberto = False
            for seletor in seletores_adicionar:
                try:
                    botao = self.page.wait_for_selector(seletor, state='visible', timeout=3000)
                    if botao:
                        logger.info(f"   ↪ Hover em '{seletor}'...")
                        botao.hover()
                        time.sleep(1)

                        if self.page.is_visible('#automatic-process-modal-link'):
                            menu_aberto = True
                            break

                        logger.info("   ↪ Click...")
                        botao.click()
                        time.sleep(1)
                        menu_aberto = True
                        break
                except:
                    continue

            if not menu_aberto:
                # Force via JS
                self.page.evaluate("document.querySelector('.add-popover-menu')?.click()")
                time.sleep(1)
                if self.page.is_visible('#automatic-process-modal-link'):
                    menu_aberto = True

            if not menu_aberto:
                logger.info("   Tentando abrir menu 'Adicionar' por texto...")
                if self._click_by_text(["adicionar", "novo", "+"]):
                    time.sleep(1)
                    if self.page.is_visible('#automatic-process-modal-link'):
                        menu_aberto = True

            time.sleep(1)

            # 3. Selecionar cadastro automático
            logger.info("3ï¸âƒ£  Selecionando 'Cadastro Automático'...")

            try:
                target_link = self.page.wait_for_selector('#automatic-process-modal-link', state='visible', timeout=5000)
                if target_link:
                    target_link.click()
                    time.sleep(3)
                    return True
                else:
                    raise Exception("Não achou link automatico")
            except Exception as e:
                logger.warning(f"   ⚠ Link direto não encontrado: {e}")
                logger.info("   Tentando clicar por texto 'Cadastro Automático'...")
                if self._click_by_text(["cadastro automático", "cadastro automatico", "automatico", "automático"]):
                    time.sleep(3)
                    return True
                logger.error("   âŒ Cancelado: link de cadastro automático não localizado")
                return False

        except Exception as e:
            logger.error(f"âŒ Erro na navegação: {e}")
            return False

    def preencher_cnj(self, cnj):
        """Preenche CNJ no modal"""
        try:
            if not self._ensure_page_active():
                logger.error("âŒ Página inativa ao preencher CNJ")
                return False

            logger.info(f"\nðŸ“ Preenchendo CNJ: {cnj}")

            # Seletores e eventos corrigidos
            selector = '#CNJNumberAutomaticModal'

            try:
                campo = self.page.wait_for_selector(selector, state='visible', timeout=5000)
                if campo:
                    campo.click()
                    time.sleep(0.5)
                    campo.fill(cnj)

                    # Dispara blur para validar
                    self.page.evaluate(f"document.querySelector('{selector}').blur()")
                    logger.info("   ✓ CNJ inserido e validado")
            except:
                logger.error("   âŒ Campo CNJ não encontrado")
                return False

            time.sleep(2)

            # Botão Capturar - múltiplos seletores
            logger.info("   Clicando em 'Capturar'...")

            seletores_capturar = [
                'button:has-text("Capturar")',
                'button.btn-primary:has-text("Capturar")',
                '#btnCapture',
                'button[id*="capture"]',
                'button[id*="Capture"]',
                '.btn:has-text("Capturar")',
            ]

            capturou = False
            for seletor in seletores_capturar:
                try:
                    botao = self.page.wait_for_selector(seletor, state='visible', timeout=2000)
                    if botao:
                        botao.click()
                        logger.info(f"   ✓ Botão Capturar clicado via: {seletor}")
                        capturou = True
                        break
                except:
                    continue

            # Fallback via JavaScript
            if not capturou:
                logger.info("   Tentando via JavaScript...")
                capturou = self.page.evaluate("""
                    () => {
                        const btn = Array.from(document.querySelectorAll('button')).find(b =>
                            b.innerText.toLowerCase().includes('capturar'));
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }
                """)
                if capturou:
                    logger.info("   ✓ Botão Capturar clicado via JavaScript")

            if not capturou:
                logger.error("   âŒ Botão Capturar não encontrado")
                return False

            time.sleep(5)
            logger.info("✅ CNJ processado!")
            return True

        except Exception as e:
            logger.error(f"âŒ Erro ao preencher CNJ: {e}")
            return False

    def aguardar_e_pular_etapa(self, cnj: str | None = None):
        """Após captura, clica em 'Continuar cadastro' no pop-up."""
        try:
            if not self._ensure_page_active():
                logger.error("âŒ Página inativa")
                return False

            self._captura_em_rascunhos = False
            self._fluxo_pre_cadastro = False
            self._processo_ja_cadastrado = False

            logger.info("\nâ³ Aguardando pop-up pós-captura...")
            time.sleep(3)

            try:
                if "authentication-error" in (self.page.url or ""):
                    logger.error(f"âŒ Sessão expirada. URL: {self.page.url}")
                    self.last_error_reason = f"Sessao expirada | URL={self.page.url}"
                    self.inicializar_navegador()
                    return False
            except Exception:
                pass

            if cnj:
                try:
                    mensagem = self.page.inner_text("body")
                except Exception:
                    mensagem = self.page.content()

                # Detecção robusta: grid de resultados mostrando a linha com ação "Alterar"
                try:
                    cnj_norm = self._normalizar_cnj(cnj)
                    tem_edit_row = self.page.evaluate(
                        """
                        (cnjNorm) => {
                            const limparNum = (t) => (t || '').replace(/\\D/g, '');
                            const links = Array.from(document.querySelectorAll('a.grid-edit-action-row'));
                            if (!links.length) return false;
                            if (!cnjNorm) return true;
                            return links.some(a => {
                                const href = a.getAttribute('href') || '';
                                if (limparNum(href).includes(cnjNorm)) return true;
                                const row = a.closest('tr, [role="row"], .grid-row');
                                if (row && limparNum(row.innerText || row.textContent || '').includes(cnjNorm)) return true;
                                return false;
                            });
                        }
                        """,
                        cnj_norm,
                    )
                except Exception:
                    tem_edit_row = False

                if tem_edit_row:
                    logger.warning(f"⚠ Processo já cadastrado no LegalOne (grid detectada): {cnj}")
                    self._processo_ja_cadastrado = True
                    self.last_error_reason = 'Processo já cadastrado no LegalOne'
                    if getattr(self, '_eh_cadastro_inicial', False):
                        # Mesma conclusao do aviso #success-content: cadastro inicial de
                        # processo existente nao se mexe.
                        self._pasta_existente = self._ler_pasta_existente() or 'pasta ja existente'
                        self._ja_cadastrado_nada_a_fazer = True
                    return False

                if "já encontra-se cadastrado" in (mensagem or "") and cnj in (mensagem or ""):
                    logger.warning(f"⚠ Processo já cadastrado: {cnj}")
                    self._processo_ja_cadastrado = True
                    self.last_error_reason = 'Processo já cadastrado no LegalOne'

                    # Cadastro inicial de processo que ja esta numa pasta: nada a mexer.
                    # Sai antes de clicar em rascunhos — abrir a alteracao aqui so cria
                    # rascunho orfao (foi o que aconteceu no ciclo de 29/07).
                    if getattr(self, '_eh_cadastro_inicial', False):
                        self._pasta_existente = self._ler_pasta_existente() or 'pasta nao identificada'
                        logger.info(
                            f"   ℹ Cadastro inicial e o processo ja esta em '{self._pasta_existente}' "
                            "— nada a fazer, encerrando sem alterar."
                        )
                        self._ja_cadastrado_nada_a_fazer = True
                        return False

                    try:
                        if self._clicar_ver_rascunhos_se_disponivel(timeout_ms=5000):
                            self._captura_em_rascunhos = True
                            return False
                    except Exception as e:
                        logger.warning(f"   ⚠ Botão 'Ver em rascunhos' não encontrado: {e}")
                        # Mesmo sem botão, segue para o fluxo de alteração por pesquisa.
                        return True

                    # Se não encontrou botão de rascunhos, segue para alteração por pesquisa.
                    return True

            # Tratamento do modal "Captura em andamento":
            if self._clicar_ver_rascunhos_se_disponivel(timeout_ms=3000):
                logger.info("ℹ Captura em andamento detectada; processo enviado para rascunhos.")
                self._captura_em_rascunhos = True
                return False

            # --- Clica em 'Continuar cadastro' no pop-up ---
            logger.info("🔘 Procurando botão 'Continuar cadastro'...")

            if self._clicar_continuar_cadastro_popup():
                logger.info("   ✓ Seguindo fluxo via 'Continuar cadastro'")
                return True

            # Retry: aguarda mais um pouco e tenta de novo
            logger.info("   â³ Aguardando pop-up carregar...")
            time.sleep(5)

            if self._clicar_continuar_cadastro_popup():
                logger.info("   ✓ Seguindo fluxo via 'Continuar cadastro' (2ª tentativa)")
                return True

            # Fallback: tenta via _clicar_continuar_cadastro_fallback (busca mais ampla)
            if self._clicar_continuar_cadastro_fallback():
                logger.info("   ✓ Seguindo fluxo via fallback 'Continuar cadastro'")
                return True

            logger.warning("   ⚠ 'Continuar cadastro' não encontrado.")

            # Se já estiver no contexto de pré-cadastro, aproveita.
            try:
                if "/processos/importer" in (self.page.url or "") or "/draft-litigation" in (self.page.url or ""):
                    self._fluxo_pre_cadastro = True
                    logger.info("   ✓ Já está em 'Pré-cadastro'")
                    return True
            except Exception:
                pass

            # Último recurso: fecha pop-up e segue fluxo
            popup_fechado = self._fechar_popup_pos_pular_etapa()

            if popup_fechado:
                logger.info("   ✓ Pop-up fechado; continuando fluxo")
                return True

            try:
                url_atual = (self.page.url or "").lower()
                if "/processos/processos/search" in url_atual:
                    self._processo_ja_cadastrado = True
                    logger.info("   ℹ Contexto permaneceu em Pesquisa de Processos; ativando fluxo de processo existente")
                    return True
            except Exception:
                pass

            logger.warning("   ⚠ Sem ação alternativa visível; seguindo fluxo mesmo assim.")
            return True

        except Exception as e:
            logger.error(f"âŒ Erro no fluxo pós-captura: {e}")
            self._registrar_diagnostico_falha("Aguardar e continuar cadastro", str(e))
            return False

    def preencher_campo_autocomplete(self, seletor_input, valor, nome_campo,
                                     cnpj: str | None = None,
                                     tipo_pessoa: str | None = None,
                                     permitir_adicionar: bool = True):
        """Preenche campo de autocomplete (bento-combobox) com o valor especificado.

        Fluxo completo:
          1. Clica no input e digita o valor
          2. Espera o dropdown bento-combobox grid aparecer
          3. Extrai as opções (CPF/CNPJ | Nome | Origem)
          4. Usa fuzzy matching para encontrar a melhor opção
          5. Se encontrou → clica na opção
          6. Se não encontrou → clica "Adicionar" e cria contato novo
        """
        try:
            if not self._ensure_page_active():
                logger.error(f"   âŒ Página inativa ao preencher {nome_campo}")
                return False

            valor = self._valor_limpo(valor)
            cnpj = self._valor_limpo(cnpj)

            if not valor:
                logger.info(f"   ⚠ {nome_campo}: valor vazio, pulando...")
                return False

            # Rola até o campo ficar visível
            self.page.evaluate(f"""
                () => {{
                    const input = document.querySelector('{seletor_input}');
                    if (input) input.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            """)
            time.sleep(1)

            # Clica no campo para abrir dropdown
            campo = self.page.wait_for_selector(seletor_input, state='visible', timeout=10000)
            if not campo:
                logger.warning(f"   ⚠ Campo {nome_campo} não encontrado pelo seletor, tentando por label...")
                if self._fill_by_label(nome_campo, valor):
                    logger.info(f"   ✓ {nome_campo}: preenchido via label")
                    return True
                logger.error(f"   âŒ Campo {nome_campo} não encontrado")
                return False

            # Regra crítica: nunca sobrescrever Negociação de contrato de honorários já preenchida
            nome_campo_norm = (nome_campo or '').strip().lower()
            if 'negociação de contrato de honorários' in nome_campo_norm or 'negociacao de contrato de honorarios' in nome_campo_norm:
                valor_atual = self.page.evaluate(
                    """
                    (el) => {
                        const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                        const invalido = (txt) => {
                            const t = limpar(txt).toLowerCase();
                            if (!t) return true;
                            if (['selecione', 'selecionar', 'digite', 'buscar', 'search'].includes(t)) return true;
                            if (t.includes('negociação de contrato de honorários') || t.includes('negociacao de contrato de honorarios')) return true;
                            return false;
                        };

                        const candidatos = [];
                        if (el && typeof el.value === 'string') candidatos.push(el.value);

                        const host = el?.closest('bento-combobox, .bento-combobox, [class*="combobox"], [class*="autocomplete"], .form-group, .field-group') || el?.parentElement;
                        if (host) {
                            const seletores = [
                                '.bento-chip__content',
                                '.bento-tag__label',
                                '.bento-combobox-selection-item',
                                '.selected-item',
                                '.mat-mdc-chip-action-label',
                                '.mat-chip',
                                '[aria-selected="true"]',
                                '.ng-value-label',
                            ];
                            for (const s of seletores) {
                                for (const node of host.querySelectorAll(s)) {
                                    const txt = limpar(node.innerText || node.textContent || '');
                                    if (txt) candidatos.push(txt);
                                }
                            }
                        }

                        for (const c of candidatos) {
                            if (!invalido(c)) return limpar(c);
                        }
                        return '';
                    }
                    """,
                    campo,
                ) or ''
                valor_atual = (valor_atual or '').strip()
                if valor_atual:
                    logger.info(f"   ✓ Negociação de contrato de honorários já preenchido: '{valor_atual}' — pulando")
                    return True

            logger.info(f"   ðŸ“ Preenchendo {nome_campo}: {valor}")

            # Fecha qualquer dropdown stale que possa estar aberto de campo anterior
            self.page.keyboard.press('Escape')
            time.sleep(0.3)

            campo.click()
            time.sleep(0.5)

            # --- Fast-path para valores curtos (Sim/Não/etc.) ---
            _valor_curto = len(valor.strip()) <= 4

            # Limpa e digita o valor (devagar para ativar autocomplete)
            campo.fill('')
            time.sleep(0.3)
            try:
                campo.type(valor, delay=50)
            except Exception:
                if self._fill_by_label(nome_campo, valor):
                    logger.info(f"   ✓ {nome_campo}: preenchido via label")
                    return True
                raise
            time.sleep(2)  # Aguarda sugestões aparecerem

            # ----------------------------------------------------------
            # Estratégia 0: Bento-tree (árvore hierárquica)
            # ----------------------------------------------------------
            if self._selecionar_opcao_bento_tree(valor):
                logger.info(f"   ✓ {nome_campo} selecionado via árvore")
                return True

            # ----------------------------------------------------------
            # Estratégia 1: Bento-combobox grid (LegalOne específico)
            # ----------------------------------------------------------
            opcoes_bento = self._extrair_opcoes_bento_combobox()
            if opcoes_bento:
                logger.info(f"      📋 Dropdown bento-combobox: {len(opcoes_bento)} opções encontradas")
                for i, op in enumerate(opcoes_bento[:5]):
                    logger.debug(f"         [{i}] {op.get('nome', '?')} | {op.get('origem', '?')}")

                # Tenta fuzzy matching
                # Campos de catalogo (contrato de honorarios, centro de custo) nao
                # aceitam fuzzy: escolher errado grava contrato de outro cliente no
                # processo. Nome de pessoa continua com 45%, que e' o que faz
                # 'Itau Unibanco S/A' casar com 'Itau Unibanco Holding S.A.'.
                # Catalogo: match literal na linha inteira; pessoa segue no fuzzy.
                self._match_por_linha_inteira = _campo_exige_match_forte(nome_campo)
                limiar_campo = 0.9 if self._match_por_linha_inteira else 0.45
                melhor = self._selecionar_melhor_opcao_combobox(
                    valor, opcoes_bento, limiar=limiar_campo, documento_referencia=cnpj)
                if melhor:
                    if permitir_adicionar and self._opcao_exige_adicao_manual(melhor):
                        origem = (melhor.get('origem') or '').strip()
                        logger.warning(
                            f"   ⚠ Opção marcada como '{origem or 'Capturado no órgão'}'. "
                            "Adicionando contato manualmente."
                        )
                        # Re-abre o dropdown: apenas clica no input
                        try:
                            campo.click()
                            time.sleep(0.5)
                        except Exception:
                            pass
                        tipo_resolvido = self._resolver_tipo_pessoa(valor, cnpj, tipo_pessoa)
                        doc_opcao = self._valor_limpo(melhor.get('cpf_cnpj'))
                        doc_para_adicao = cnpj or doc_opcao
                        return self._adicionar_contato_novo(
                            nome=valor,
                            cnpj=doc_para_adicao,
                            tipo_pessoa=tipo_resolvido,
                            campo=campo,
                        )
                    if self._clicar_opcao_bento_combobox(melhor):
                        nome_sel = melhor.get('nome') or melhor.get('texto_completo', '?')
                        logger.info(f"   ✓ {nome_campo} selecionado: {nome_sel}")
                        return True

                # --- Para valores curtos (Sim/Não), pula variantes (inútil para 3 chars) ---
                if _valor_curto:
                    logger.info(f"      â© Valor curto \"{valor}\" sem match no combobox ({len(opcoes_bento)} opções). Pulando variantes, tentando seleção direta...")
                else:
                    # Não encontrou match → tenta variações de busca (semânticas + genéricas)
                    variantes = self._gerar_variantes_busca(valor) + self._gerar_variantes_nome(valor)
                    variantes_dedup = []
                    vistos_var = set()
                    for v in variantes:
                        k = (v or '').strip().lower()
                        if not k or k in vistos_var:
                            continue
                        vistos_var.add(k)
                        variantes_dedup.append(v)
                    variantes = variantes_dedup
                    if variantes:
                        logger.info(f"      🔄 Tentando {len(variantes)} variação(ões) de busca...")
                        for variante in variantes:
                            logger.info(f"         🔎 Tentando: \"{variante}\"")
                            try:
                                campo.click()
                                time.sleep(0.3)
                                campo.fill('')
                                time.sleep(0.2)
                                campo.type(variante, delay=50)
                                time.sleep(2)
                            except Exception:
                                continue

                            opcoes_variante = self._extrair_opcoes_bento_combobox()
                            if opcoes_variante:
                                logger.info(f"         📋 {len(opcoes_variante)} opções para \"{variante}\"")
                                # Mesmo limiar da primeira passada: senao a busca por
                                # variantes reabilita o fuzzy num campo de catalogo e
                                # desfaz a protecao (visto em 30/07 com 'Pro bono').
                                melhor_v = self._selecionar_melhor_opcao_combobox(
                                    variante, opcoes_variante, limiar=limiar_campo,
                                    documento_referencia=cnpj,
                                    valor_original=valor,
                                )
                                if melhor_v:
                                    if permitir_adicionar and self._opcao_exige_adicao_manual(melhor_v):
                                        origem = (melhor_v.get('origem') or '').strip()
                                        logger.warning(
                                            f"   ⚠ Opção marcada como '{origem or 'Capturado no órgão'}'. "
                                            "Adicionando contato manualmente."
                                        )
                                        # Re-abre o dropdown: apenas clica no input
                                        try:
                                            campo.click()
                                            time.sleep(0.5)
                                        except Exception:
                                            pass
                                        tipo_resolvido = self._resolver_tipo_pessoa(valor, cnpj, tipo_pessoa)
                                        doc_opcao = self._valor_limpo(melhor_v.get('cpf_cnpj'))
                                        doc_para_adicao = cnpj or doc_opcao
                                        return self._adicionar_contato_novo(
                                            nome=valor,
                                            cnpj=doc_para_adicao,
                                            tipo_pessoa=tipo_resolvido,
                                            campo=campo,
                                        )
                                    if self._clicar_opcao_bento_combobox(melhor_v):
                                        nome_sel = melhor_v.get('nome') or melhor_v.get('texto_completo', '?')
                                        logger.info(f"   ✓ {nome_campo} selecionado via variante: {nome_sel}")
                                        return True

                        logger.info(f"      ⚠ Nenhuma variante teve match no dropdown.")

                # Não encontrou match → tenta adicionar contato novo
                if permitir_adicionar:
                    logger.info(f"      ⚠ \"{valor}\" não encontrado na lista. Tentando adicionar...")
                    tipo_resolvido = self._resolver_tipo_pessoa(valor, cnpj, tipo_pessoa)
                    if self._adicionar_contato_novo(
                        nome=valor,
                        cnpj=cnpj,
                        tipo_pessoa=tipo_resolvido,
                        campo=campo,
                    ):
                        return True
                    logger.warning(f"      ⚠ Falha ao criar contato para \"{valor}\". Tentando fallback...")
                    # --- FALLBACK INTELIGENTE: browser-use para dropdown ---
                    if _bu_fallback and _bu_fallback.is_available():
                        logger.info(f"      🤖 Acionando fallback inteligente para dropdown '{nome_campo}'...")
                        if _bu_fallback.fallback_preencher_campo_dropdown(
                            page=self.page,
                            nome_campo=nome_campo,
                            valor=valor,
                        ):
                            return True
                        logger.warning("      ⚠ Fallback inteligente para dropdown também falhou")
                else:
                    logger.warning(f"   ⚠ \"{valor}\" não encontrado e adicionar não permitido")

            # ----------------------------------------------------------
            # Estratégia 2: Dropdown genérico (role="option", etc.)
            # ----------------------------------------------------------
            seletores_opcao = [
                '[role="option"]',
                '[role="row"].bento-list-row',
                '.dropdown-item',
                '.bui-menu-item-text',
                'li.ng-star-inserted',
                '[class*="option"]',
                '[class*="suggestion"]',
            ]

            for seletor_opcao in seletores_opcao:
                try:
                    opcoes = self.page.query_selector_all(seletor_opcao)
                    if not opcoes:
                        continue

                    # Le todos os textos numa ida so ao browser. inner_text() elemento
                    # a elemento e' um round-trip CDP cada: com 116 opcoes vezes 7
                    # seletores, o campo Datacloud ficou 3 min parado aqui (30/07).
                    textos = self.page.evaluate(
                        "(sel) => Array.from(document.querySelectorAll(sel))"
                        ".map(e => (e.innerText || '').trim())",
                        seletor_opcao,
                    )
                    if len(textos) != len(opcoes):  # DOM mudou no meio: nao arrisca
                        continue

                    # Para valores curtos (Sim/Não): prioriza match EXATO antes de fuzzy
                    if _valor_curto:
                        for opcao, texto_opcao in zip(opcoes, textos):
                            if texto_opcao.lower() == valor.lower():
                                opcao.click()
                                logger.info(f"   ✓ {nome_campo} selecionado (match exato): {texto_opcao}")
                                time.sleep(1)
                                return True

                    # Procura match por similaridade
                    melhor_el = None
                    melhor_score = 0.0
                    for opcao, texto_opcao in zip(opcoes, textos):
                        score = self._calcular_similaridade(valor, texto_opcao)
                        # Também aceita "contém"
                        if valor.lower() in texto_opcao.lower() or texto_opcao.lower() in valor.lower():
                            score = max(score, 0.85)
                        if score > melhor_score:
                            melhor_score = score
                            melhor_el = opcao
                    if melhor_el and melhor_score >= 0.45:
                        melhor_el.click()
                        logger.info(f"   ✓ {nome_campo} selecionado: {melhor_el.inner_text().strip()} ({melhor_score:.0%})")
                        time.sleep(1)
                        return True
                except Exception:
                    continue

            # Para valores curtos, tenta digitar de novo e confirmar com Enter
            if _valor_curto:
                logger.info(f"   â© Confirmando \"{valor}\" com Enter (valor curto)")
                try:
                    campo.click()
                    campo.fill('')
                    time.sleep(0.2)
                    campo.type(valor, delay=30)
                    time.sleep(1)
                    self.page.keyboard.press('Enter')
                    time.sleep(1)
                    return True
                except Exception:
                    pass

            # ----------------------------------------------------------
            # Estratégia 3: Primeira opção ou Enter
            # ----------------------------------------------------------
            if permitir_adicionar:
                logger.info(f"      âš  Sem match no dropdown para \"{valor}\". Tentando criar contato...")
                tipo_resolvido = self._resolver_tipo_pessoa(valor, cnpj, tipo_pessoa)
                if self._adicionar_contato_novo(
                    nome=valor,
                    cnpj=cnpj,
                    tipo_pessoa=tipo_resolvido,
                    campo=campo,
                ):
                    return True
                logger.warning(f"      âš  Não foi possível criar contato para \"{valor}\". Seguindo fallback final.")

            # Fallback de desespero: pega a primeira opcao da lista. Em campo de
            # catalogo isso grava o contrato de outro cliente (em 30/07 saiu
            # 'Hon - 0000002/002' numa rodada e 'Hon - 0000080/001' noutra, para o
            # mesmo pedido) — melhor deixar vazio e o Salvar barrar.
            if getattr(self, '_match_por_linha_inteira', False):
                logger.warning(
                    f"   ⚠ {nome_campo}: nada casou com \"{valor}\" e este campo nao aceita "
                    "chute — deixando vazio para preenchimento manual"
                )
                return False

            try:
                primeira_opcao = self.page.wait_for_selector(
                    '[role="row"].bento-list-row, [role="option"]:first-child', timeout=2000
                )
                if primeira_opcao:
                    primeira_opcao.click()
                    logger.info(f"   ✓ {nome_campo}: selecionou primeira opção disponível")
                    time.sleep(1)
                    return True
            except Exception:
                pass

            self.page.keyboard.press('Enter')
            logger.info(f"   ✓ {nome_campo}: confirmado com Enter")
            time.sleep(1)
            return True

        except Exception as e:
            if _pagina_morta(e):
                raise NavegadorFechado(f"navegador fechado ao preencher '{nome_campo}'") from e
            logger.error(f"   âŒ Erro ao preencher {nome_campo}: {e}")
            return False

    def _detectar_campos_obrigatorios_vazios(self) -> list[dict]:
        """Escaneia o formulário e retorna lista de campos obrigatórios (asterisco *) que ainda estão vazios.

        Retorna lista de dicts com: {'label': str, 'id': str, 'vazio': bool}
        """
        try:
            resultado = self.page.evaluate("""
                () => {
                    const campos = [];
                    // Busca labels que contenham asterisco (campo obrigatório)
                    const labels = Array.from(document.querySelectorAll('label'));
                    for (const label of labels) {
                        const texto = label.innerText || label.textContent || '';
                        if (!texto.includes('*')) continue;
                        const nomeLabel = texto.replace(/[*:\\s]+$/g, '').trim();
                        const forId = label.getAttribute('for');
                        let input = forId ? document.getElementById(forId) : null;
                        if (!input) {
                            input = label.querySelector('input, select, textarea')
                                 || label.nextElementSibling?.querySelector('input, select, textarea');
                        }
                        if (!input) continue;
                        const valor = (input.value || '').trim();
                        campos.push({
                            label: nomeLabel,
                            id: input.id || '',
                            tipo: input.tagName.toLowerCase(),
                            vazio: valor === '' || valor === null
                        });
                    }
                    return campos;
                }
            """)
            if resultado:
                vazios = [c for c in resultado if c.get('vazio')]
                if vazios:
                    logger.warning(f"⚠ Campos obrigatórios ainda vazios: {[c['label'] for c in vazios]}")
                else:
                    logger.info("✅ Todos os campos obrigatórios preenchidos")
            return resultado or []
        except Exception as e:
            logger.debug(f"[campos_obrig] Erro ao escanear: {e}")
            return []

    def _fallback_cua_combobox(self, seletor, valor, nome_campo, label_form) -> bool:
        """Ultimo recurso p/ combobox que nao commita: Playwright digita p/ abrir o
        dropdown e o cua-driver clica na opcao via arvore de acessibilidade (AT-SPI)."""
        try:
            import cua_fallback
            if not cua_fallback.disponivel():
                logger.warning(f"   [CUA] Indisponivel (binario ausente) - sem fallback para {nome_campo}")
                return False
        except Exception as e:
            logger.warning(f"   [CUA] Import falhou ({e}) - sem fallback para {nome_campo}")
            return False
        logger.info(f"   [CUA] Fallback de acessibilidade para {nome_campo}...")
        # 1) foca o campo: preferencia pela arvore AT-SPI (UI nova nao tem os
        # seletores CSS antigos); seletor CSS fica como ultimo recurso
        focado = cua_fallback.clicar_campo(label_form)
        if not focado and seletor:
            try:
                campo = self.page.wait_for_selector(seletor, state='visible', timeout=4000)
                campo.click()
                focado = True
            except Exception as e:
                logger.warning(f"   [CUA] Nao focou {nome_campo}: {e}")
                return False
        time.sleep(1)
        try:
            self.page.keyboard.type(str(valor)[:40], delay=50)  # vai pro elemento focado
        except Exception:
            pass
        time.sleep(3)  # dropdown abrir e popular
        if not cua_fallback.clicar_opcao(str(valor)):
            # nome fora da base: cria o contato pela opcao Adicionar do dropdown
            logger.info(f"   [CUA] Sem match p/ '{str(valor)[:40]}' — tentando criar contato via Adicionar")
            if not cua_fallback.clicar_opcao('Adicionar'):
                return False
            time.sleep(2)
            try:
                self._tratar_modal_criacao_obrigatoria(nome=str(valor))
            except Exception as e:
                logger.warning(f"   [CUA] Modal de criacao: {e}")
        time.sleep(1.5)
        atual = self._valor_limpo(self._ler_valor_campo_formulario(label_form)) or ''
        if atual:
            logger.info(f"   [CUA] {nome_campo} commitou: '{atual}'")
            return True
        logger.warning(f"   [CUA] {nome_campo} continua vazio apos clique")
        return False

    def _ler_valor_campo_formulario(self, label_texto: str) -> str | None:
        """Lê o valor atual de um campo no formulário pelo texto do label.

        Útil para verificar se LegalOne já auto-preencheu campos como natureza/status
        após a captura do CNJ, antes de tentar sobrescrever.
        """
        try:
            valor = self.page.evaluate(f"""
                () => {{
                    const normalizar = (txt) => (txt || '')
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .replace(/[\\s*:]+/g, ' ')
                        .trim()
                        .toLowerCase();
                    const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                    const termo = normalizar('{label_texto}');
                    const labels = Array.from(document.querySelectorAll('label'));
                    const target = labels.find(l =>
                        normalizar(l.innerText || l.textContent || '').includes(termo)
                    );
                    if (!target) return null;
                    const forId = target.getAttribute('for');
                    let input = forId ? document.getElementById(forId) : null;
                    if (!input) {{
                        input = target.querySelector('input, select')
                             || target.nextElementSibling?.querySelector('input, select, textarea');
                    }}
                    const container = target.closest('.form-group, .field-group, .bento-form-group, [class*="form"]')
                        || target.parentElement
                        || input?.closest('bento-combobox, .bento-combobox, [class*="combobox"], [class*="autocomplete"]');

                    const candidatos = [];
                    if (input && typeof input.value === 'string') candidatos.push(input.value);
                    if (container) {{
                        const seletores = [
                            'input',
                            'select',
                            'textarea',
                            '.bento-chip__content',
                            '.bento-tag__label',
                            '.bento-combobox-selection-item',
                            '.selected-item',
                            '.mat-mdc-chip-action-label',
                            '.mat-chip',
                            '[aria-selected="true"]',
                            '.ng-value-label',
                            '.bento-list-selection-label',
                        ];
                        for (const seletor of seletores) {{
                            for (const node of container.querySelectorAll(seletor)) {{
                                if (node === input) continue;
                                const txt = 'value' in node ? node.value : (node.innerText || node.textContent || '');
                                if (txt) candidatos.push(txt);
                            }}
                        }}
                    }}

                    for (const candidato of candidatos) {{
                        const txt = limpar(candidato);
                        if (txt) return txt;
                    }}
                    return null;
                }}
            """)
            return valor if valor else None
        except Exception:
            return None

    def _ler_status_atual_formulario(self) -> str | None:
        """Lê o label atual do campo Status preservando valores já definidos."""
        if not self.page:
            return None
        try:
            valor = self.page.evaluate(
                """
                () => {
                    const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                    const normalizar = (txt) => limpar(txt)
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase();

                    const candidatos = [];
                    const select = document.querySelector('#input-status, select[formcontrolname="statusId"], select[formcontrolname="status"], select[id*="status"]');
                    if (select) {
                        if (select.selectedOptions && select.selectedOptions.length) {
                            candidatos.push(select.selectedOptions[0].textContent || '');
                        }
                        const opt = select.options?.[select.selectedIndex];
                        if (opt) candidatos.push(opt.textContent || '');
                    }

                    const label = Array.from(document.querySelectorAll('label')).find(l =>
                        normalizar(l.innerText || l.textContent || '').includes('status')
                    );
                    const host = label?.closest('.form-group, .field-group, .bento-form-group, [class*="form"]') || label?.parentElement;
                    if (host) {
                        const seletores = [
                            '.bento-chip__content',
                            '.bento-tag__label',
                            '.bento-combobox-selection-item',
                            '.selected-item',
                            '.mat-mdc-chip-action-label',
                            '.mat-chip',
                            '[aria-selected="true"]',
                            '.ng-value-label',
                            'input',
                            'select',
                        ];
                        for (const seletor of seletores) {
                            for (const node of host.querySelectorAll(seletor)) {
                                const txt = 'value' in node ? node.value : (node.innerText || node.textContent || '');
                                if (txt) candidatos.push(txt);
                            }
                        }
                    }

                    const validos = ['ativo', 'suspenso', 'baixado', 'arquivado'];
                    for (const candidato of candidatos) {
                        const txt = limpar(candidato);
                        const txtNorm = normalizar(candidato);
                        if (txt && validos.some(v => txtNorm === v || txtNorm.includes(v))) {
                            return txt;
                        }
                    }
                    return null;
                }
                """
            )
            return self._valor_limpo(valor)
        except Exception:
            return None

    def _garantir_preenchimento_campo_texto(self, label_texto: str, valor: str, seletor: str | None = None) -> bool:
        valor = self._valor_limpo(valor)
        if not self.page or not label_texto or not valor:
            return False

        try:
            if seletor:
                try:
                    campo = self.page.wait_for_selector(seletor, state='visible', timeout=4000)
                    if campo:
                        campo.scroll_into_view_if_needed()
                        campo.click()
                        campo.fill(valor)
                        self.page.keyboard.press('Tab')
                        time.sleep(0.5)
                except Exception:
                    pass

            atual = self._valor_limpo(self._ler_valor_campo_formulario(label_texto))
            if atual:
                return True

            if self._fill_by_label(label_texto, valor):
                time.sleep(0.5)
                atual = self._valor_limpo(self._ler_valor_campo_formulario(label_texto))
                if atual:
                    return True

            return bool(
                self.page.evaluate(
                    """
                    ([labelText, value]) => {
                        const normalizar = (txt) => (txt || '')
                            .normalize('NFD')
                            .replace(/[\\u0300-\\u036f]/g, '')
                            .replace(/[\\s*:]+/g, ' ')
                            .trim()
                            .toLowerCase();
                        const alvo = normalizar(labelText);
                        const labels = Array.from(document.querySelectorAll('label'));
                        const target = labels.find(l => normalizar(l.innerText || l.textContent || '').includes(alvo));
                        if (!target) return false;

                        const forId = target.getAttribute('for');
                        let input = forId ? document.getElementById(forId) : null;
                        if (!input) {
                            const container = target.closest('.form-group, .field-group, .bento-form-group, [class*="form"]') || target.parentElement;
                            input = container?.querySelector('input, textarea, select') || target.nextElementSibling?.querySelector('input, textarea, select');
                        }
                        if (!input) return false;

                        input.focus();
                        input.value = '';
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new Event('blur', { bubbles: true }));
                        return true;
                    }
                    """,
                    [label_texto, valor],
                )
            )
        except Exception:
            return False

    def _configurar_monitoramento_se_disponivel(self) -> bool:
        if not self.page:
            return False

        # Verifica se já solicitamos o monitoramento nesta execução para evitar cliques duplicados
        if getattr(self, '_monitoramento_solicitado', False):
            return True

        try:
            botao_visivel = self.page.evaluate(
                """
                () => {
                    const botao = document.querySelector('#litigation-number-monitoring-button');
                    return botao !== null;
                }
                """
            )
            if not botao_visivel:
                return False

            valor_tipo = self._valor_limpo(self._ler_valor_campo_formulario('Tipo de consulta'))
            if not valor_tipo:
                seletor_tipo = (
                    self._encontrar_input_por_label_exato('Tipo de consulta')
                    or self._resolver_seletor_por_label('Tipo de consulta')
                    or 'select[id*="consult"], input[id*="consult"], input[name*="consult"]'
                )
                try:
                    campo_tipo = self.page.wait_for_selector(seletor_tipo, state='visible', timeout=4000)
                    if campo_tipo:
                        campo_tipo.scroll_into_view_if_needed()
                        campo_tipo.click()
                        time.sleep(0.3)
                        self.page.keyboard.press('ArrowDown')
                        time.sleep(0.2)
                        self.page.keyboard.press('Enter')
                        time.sleep(0.8)
                except Exception:
                    pass

                if not self._valor_limpo(self._ler_valor_campo_formulario('Tipo de consulta')):
                    try:
                        self.page.evaluate(
                            """
                            () => {
                                const normalizar = (txt) => (txt || '')
                                    .normalize('NFD')
                                    .replace(/[\\u0300-\\u036f]/g, '')
                                    .replace(/[\\s*:]+/g, ' ')
                                    .trim()
                                    .toLowerCase();
                                const labels = Array.from(document.querySelectorAll('label'));
                                const target = labels.find(l => normalizar(l.innerText || l.textContent || '').includes('tipo de consulta'));
                                if (!target) return false;
                                const forId = target.getAttribute('for');
                                const input = (forId ? document.getElementById(forId) : null)
                                    || target.closest('.form-group, .field-group, .bento-form-group, [class*="form"]')?.querySelector('select, input')
                                    || target.nextElementSibling?.querySelector('select, input');
                                if (!input) return false;

                                if (input.tagName === 'SELECT') {
                                    const option = Array.from(input.options || []).find(opt => (opt.value || '').trim() && !(opt.disabled));
                                    if (!option) return false;
                                    input.value = option.value;
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                    return true;
                                }

                                input.focus();
                                input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                input.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                                return true;
                            }
                            """
                        )
                        time.sleep(0.8)
                        self.page.keyboard.press('ArrowDown')
                        time.sleep(0.2)
                        self.page.keyboard.press('Enter')
                        time.sleep(0.8)
                    except Exception:
                        pass
            clicou = self.page.evaluate(
                """
                () => {
                    const botao = document.querySelector('#litigation-number-monitoring-button');
                    if (!botao || botao.disabled) return false;
                    botao.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    botao.click();
                    return true;
                }
                """
            )
            if clicou:
                logger.info("   ✓ Monitoramento solicitado no bloco de consulta")
                self._monitoramento_solicitado = True
                time.sleep(1.5)
            return bool(clicou)
        except Exception as e:
            logger.debug(f"Falha ao configurar monitoramento: {e}")
            return False

    def preencher_campos_obrigatorios(self, dados):
        """Preenche os campos obrigatórios do formulário de cadastro.

        Estratégia em 2 camadas:
          1. Tenta via PageAnalyzer (LLM "vê" a página e decide)
          2. Fallback para seletores hardcoded se LLM indisponível ou falhou
        """
        try:
            logger.info("\n📋 Preenchendo campos obrigatórios...")
            time.sleep(3)

            # ---------------------------------------------------------------
            # CAMADA 1: LLM - bot "vê" a página e "pensa"
            # ---------------------------------------------------------------
            llm_ok = False
            usar_page_analyzer = os.getenv("LEGALONE_USE_PAGE_ANALYZER", "0").strip().lower() in ("1", "true", "yes", "y")
            if usar_page_analyzer and _get_page_analyzer is not None:
                try:
                    analyzer = _get_page_analyzer()
                    if analyzer.disponivel:
                        logger.info("🧠 Usando LLM para analisar a página...")
                        resultado = analyzer.ver_e_preencher(self.page, dados, confianca_minima=0.5)
                        res = resultado.get("resultado", {})
                        if res.get("sucesso", 0) > 0:
                            llm_ok = True
                            logger.info(f"🧠 LLM preencheu {res['sucesso']} campos com sucesso!")
                            # Se teve falhas, complementa com fallback
                            if res.get("falha", 0) > 0:
                                logger.info("🔄 Complementando com seletores hardcoded para campos que falharam...")
                            else:
                                logger.info("✅ LLM preencheu todos os campos!")
                                return True
                        else:
                            logger.warning("⚠ LLM não conseguiu preencher nenhum campo. Usando fallback...")
                    else:
                        logger.info("ℹ PageAnalyzer sem API key - usando seletores hardcoded.")
                except Exception as e:
                    logger.warning(f"⚠ Erro no PageAnalyzer: {e}. Usando fallback hardcoded...")

            # ---------------------------------------------------------------
            # CAMADA 2: Fallback hardcoded (original)
            # ---------------------------------------------------------------
            if not llm_ok:
                if not usar_page_analyzer:
                    logger.info("Modo deterministico ativo: preenchimento hardcoded dos campos obrigatorios.")
                logger.info("📋 Preenchendo via seletores hardcoded...")

            # Rola a página para ver os campos
            self.page.evaluate("window.scrollTo(0, 500)")
            time.sleep(1)

            # Se o bloco de monitoramento estiver visível, tenta solicitar antes de
            # seguir com o restante do formulário para evitar pendências na captura.
            self._configurar_monitoramento_se_disponivel()

            # Extrai documento (CPF/CNPJ) dos dados para uso nos contatos
            outros = dados.get('outros_dados', {}) or {}
            doc_cliente = (
                dados.get('cpf_cliente')
                or dados.get('cnpj_cliente')
                or dados.get('documento_cliente')
                or self._obter_outro_dado(
                    dados,
                    'CPF do cliente',
                    'CPF do Cliente',
                    'CPF/CNPJ do cliente',
                    'CPF/CNPJ Cliente',
                    'CNPJ do cliente',
                    'Documento do cliente',
                )
            )
            doc_contrario = (
                dados.get('cpf_contrario')
                or dados.get('cnpj_contrario')
                or dados.get('documento_contrario')
                or self._obter_outro_dado(
                    dados,
                    'CPF do contrário',
                    'CPF do contrario',
                    'CPF do Contrário',
                    'CPF/CNPJ do contrário',
                    'CPF/CNPJ do contrario',
                    'CNPJ do contrário',
                    'CNPJ do contrario',
                    'Documento do contrário',
                    'Documento do contrario',
                )
            )

            doc_cliente = self._valor_limpo(doc_cliente)
            doc_contrario = self._valor_limpo(doc_contrario)

            # Resolve cliente/contrário para reuso no título e honorários
            cliente_raw = self._valor_limpo(
                dados.get('cliente')
                or self._obter_outro_dado(dados, 'Cliente principal', 'Cliente')
            ) or ''
            # Usado para desempatar catalogos que repetem o mesmo nome por cliente
            # (a grade de honorarios tem um 'Pro bono' para cada cliente).
            self._cliente_ref = cliente_raw
            contrario_raw = self._valor_limpo(
                dados.get('contrario')
                or self._obter_outro_dado(
                    dados,
                    'Contrário principal',
                    'Contrario principal',
                    'Parte contrária',
                    'Parte contraria',
                    'Contrário',
                    'Contrario',
                )
            ) or ''

            # 0. Título do processo: usa 'titulo' dos dados; fallback "{cliente} x {contrário}"
            titulo_proc = self._valor_limpo(
                dados.get('titulo')
                or self._obter_outro_dado(dados, 'Título', 'Titulo', 'Título do processo', 'Titulo do processo')
            )
            if not titulo_proc and (cliente_raw or contrario_raw):
                titulo_proc = f"{cliente_raw.title()} x {contrario_raw.title()}".strip(' x')
            if titulo_proc:
                try:
                    titulo_seletor = (
                        self._encontrar_input_por_label_exato('Titulo')
                        or self._encontrar_input_por_label_exato('Titulo')
                        or self._resolver_seletor_por_label('Título')
                        or 'input[id*="title"]:not([type="hidden"]), input[id*="titulo"]:not([type="hidden"]), input[name*="title"]:not([type="hidden"]), input[name*="Title"]:not([type="hidden"]), input[placeholder*="ítulo" i]'
                    )
                    if self._garantir_preenchimento_campo_texto('Título', titulo_proc, titulo_seletor):
                        logger.info(f"   ✓ Título: {titulo_proc}")
                    elif self._fill_by_label('Título', titulo_proc):
                        logger.info(f"   ✓ Título (fallback label): {titulo_proc}")
                    else:
                        logger.info("   ⚠ Campo Título não encontrado")
                except Exception:
                    try:
                        if self._garantir_preenchimento_campo_texto('Título', titulo_proc):
                            logger.info(f"   ✓ Título: {titulo_proc}")
                        else:
                            logger.info("   ⚠ Campo Título não encontrado")
                    except Exception:
                        logger.info("   ⚠ Campo Título não encontrado")

            # 1. Cliente Principal *
            cliente = (
                dados.get('cliente')
                or self._obter_outro_dado(dados, 'Cliente principal', 'Cliente')
            )
            cliente = self._nome_parte(self._valor_limpo(cliente) or '') or None
            if cliente:
                cliente_seletor = (
                    self._encontrar_input_por_label_exato('Cliente principal')
                    or '#input-main-customer-3-input, input[id*="main-customer"]'
                )
                cliente_preenchido = self.preencher_campo_autocomplete(
                    cliente_seletor,
                    cliente,
                    'Cliente Principal',
                    cnpj=doc_cliente,
                )
                # LegalOne pode exibir modal obrigatório de criação de contato
                # imediatamente após o autocomplete se a parte não está cadastrada
                self._tratar_modal_criacao_obrigatoria(nome=cliente, documento=doc_cliente)

                # Captura do orgao pode deixar contato errado no campo (ex.: reclamada
                # no lugar da cliente); confere o que ficou e refaz uma vez se nao bater
                atual = self._valor_limpo(self._ler_valor_campo_formulario('Cliente principal')) or ''
                if atual and self._calcular_similaridade(cliente, atual) < 0.45:
                    logger.warning(f"   Cliente principal divergente: '{atual}' != '{cliente}' - refazendo")
                    self.preencher_campo_autocomplete(
                        cliente_seletor, cliente, 'Cliente Principal', cnpj=doc_cliente,
                    )
                    self._tratar_modal_criacao_obrigatoria(nome=cliente, documento=doc_cliente)
                    atual = self._valor_limpo(self._ler_valor_campo_formulario('Cliente principal')) or ''
                if (not atual) or self._calcular_similaridade(cliente, atual) < 0.45:
                    self._preencher_campo_visual('Cliente principal', cliente, criar=True)
                    atual = self._valor_limpo(self._ler_valor_campo_formulario('Cliente principal')) or ''
                    if (not atual) or self._calcular_similaridade(cliente, atual) < 0.45:
                        dados.setdefault('_qa_warnings', []).append(
                            f"Cliente principal pode estar ERRADO: formulario='{atual or 'VAZIO'}', esperado='{cliente}'"
                        )
                # A origem é validada dentro do dropdown, mas isso sozinho não
                # basta: em 27/07 o placeholder passou e o LegalOne desabilitou o
                # Salvar. Última rede: se o alerta AINDA estiver no campo, cria o
                # contato de verdade. O alerta é lido escopado ao input — global
                # pegaria o alerta de outro campo e geraria um segundo modal.
                captura_ok = self._corrigir_captura_orgao(
                    cliente_seletor, cliente, doc_cliente, 'Cliente principal'
                )
                if not cliente_preenchido or not captura_ok:
                    dados.setdefault('_qa_warnings', []).append(
                        "Cliente principal capturado do orgao - conferir/adicionar manualmente"
                    )

            # 2. Posição * (Autor/Réu/Reclamado/Reclamante)
            posicao = (
                dados.get('posicao')
                or self._obter_outro_dado(
                    dados,
                    'Posição',
                    'Posicao',
                    'Posição nos autos',
                    'Posicao nos autos',
                    permitir_parcial=False,
                )
            )
            posicao = self._valor_limpo(posicao)
            if not posicao:
                funcao_rcte = self._obter_outro_dado(dados, 'Função exercida pelo RCTE', 'Funcao exercida pelo RCTE') or ''
                funcao_rcte = self._valor_limpo(funcao_rcte) or ''
                if 'reclamado' in funcao_rcte.lower() or 'réu' in funcao_rcte.lower():
                    posicao = 'Reclamado'
                elif 'reclamante' in funcao_rcte.lower() or 'autor' in funcao_rcte.lower():
                    posicao = 'Reclamante'
                else:
                    posicao = 'Reclamado'  # Default para processos trabalhistas

            if posicao:
                # campo Posicao aceita so o termo base, sem status entre parenteses
                posicao = re.sub(r"\s*\([^)]*\)", "", str(posicao)).strip() or posicao
                logger.info(f"   ↪ Posição resolvida: {posicao}")
                posicao_seletor = (
                    self._encontrar_input_por_label_exato('Posicao')
                    or '#input-position, input[id*="position"]'
                )
                self.preencher_campo_autocomplete(
                    posicao_seletor,
                    posicao,
                    'Posição',
                    permitir_adicionar=False,
                )
                if not self._valor_limpo(self._ler_valor_campo_formulario('Posição')):
                    self.preencher_campo_autocomplete(
                        posicao_seletor,
                        posicao,
                        'Posição',
                        permitir_adicionar=False,
                    )
                if not self._valor_limpo(self._ler_valor_campo_formulario('Posição')):
                    self._preencher_campo_visual('Posição', posicao)
                    if not self._valor_limpo(self._ler_valor_campo_formulario('Posição')):
                        dados.setdefault('_qa_warnings', []).append(
                            f"Posição pode ter ficado VAZIA (esperado '{posicao}')"
                        )

            # 3. Contrário Principal *
            contrario = (
                dados.get('contrario')
                or self._obter_outro_dado(
                    dados,
                    'Contrário principal',
                    'Contrario principal',
                    'Parte contrária',
                    'Parte contraria',
                    'Contrário',
                    'Contrario',
                )
            )
            contrario = self._nome_parte(self._valor_limpo(contrario) or '') or None
            if contrario:
                # Busca o input pelo label exato (ASCII: normalizar remove acentos dos dois lados;
                # a string mojibake 'Contrário' nunca casava com o label 'Contrário' da tela)
                contrario_seletor = self._encontrar_input_por_label_exato('Contrario principal')
                if not contrario_seletor:
                    # O sufixo numérico é gerado dinamicamente pelo LegalOne
                    # (por exemplo, input-main-opposite-29-input).
                    contrario_seletor = (
                        'input[id^="input-main-opposite-"][id$="-input"], '
                        '#input-main-opposite-11-input'
                    )
                contrario_preenchido = self.preencher_campo_autocomplete(
                    contrario_seletor,
                    contrario,
                    'Contrário Principal',
                    cnpj=doc_contrario,
                )
                # Idem: verifica modal obrigatório após preencher o contrário
                self._tratar_modal_criacao_obrigatoria(nome=contrario, documento=doc_contrario)

                # Não basta o campo estar preenchido: o LegalOne pode manter um
                # homônimo ou um contato capturado pelo órgão no autocomplete.
                principal = str(contrario).split(';')[0].strip()
                atual = self._valor_limpo(
                    self._ler_valor_campo_formulario('Contrário Principal')
                ) or ''
                if atual and self._calcular_similaridade(principal, atual) < 0.45:
                    logger.warning(
                        f"   Contrário principal divergente: '{atual}' != '{principal}' - refazendo"
                    )
                    self.preencher_campo_autocomplete(
                        contrario_seletor,
                        principal,
                        'Contrário Principal',
                        cnpj=doc_contrario,
                    )
                    self._tratar_modal_criacao_obrigatoria(
                        nome=principal,
                        documento=doc_contrario,
                    )
                    atual = self._valor_limpo(
                        self._ler_valor_campo_formulario('Contrário Principal')
                    ) or ''
                if not atual or self._calcular_similaridade(principal, atual) < 0.45:
                    self._preencher_campo_visual('Contrário Principal', principal, criar=True)
                    atual = self._valor_limpo(
                        self._ler_valor_campo_formulario('Contrário Principal')
                    ) or ''
                    if not atual or self._calcular_similaridade(principal, atual) < 0.45:
                        dados.setdefault('_qa_warnings', []).append(
                            f"Contrário Principal pode estar ERRADO: "
                            f"formulario='{atual or 'VAZIO'}', esperado='{principal}'"
                        )
                # Mesma rede final do Cliente principal: foi exatamente aqui que
                # o placeholder "Itau Unibanco S.A" (Capturado no órgão) travou o
                # Salvar em 27/07 (CNJ 0000283-33.2024.5.08.0002).
                captura_ok = self._corrigir_captura_orgao(
                    contrario_seletor, principal, doc_contrario, 'Contrário principal'
                )
                if not contrario_preenchido or not captura_ok:
                    dados.setdefault('_qa_warnings', []).append(
                        "Contrário principal capturado do orgao - conferir/adicionar manualmente"
                    )

            # 4. Responsável principal * (default: Paollo Sanchez)
            # A chave 'advogado' do Forms mapeia para o Responsável principal no LegalOne.
            responsavel = (
                dados.get('responsavel')
                or dados.get('advogado')                                          # Forms → Responsável
                or self._obter_outro_dado(
                    dados,
                    'Responsável principal',
                    'Responsavel principal',
                    'Advogado responsável',
                    'Advogado responsavel',
                    # O Copilot manda a chave como 'advogado' dentro de outros_dados;
                    # sem esse alias caia-se no default e o responsavel saia errado.
                    'Advogado',
                )
            )
            responsavel = self._valor_limpo(responsavel)
            if not responsavel:
                responsavel = 'Paollo Sanchez'  # Default
            # O nome que a peticao traz nao e' o cadastrado ('Monica Pinheiro' vs
            # 'Monica Furtado Pinheiro Chagas'); o e-mail e' unico e nao confunde
            # Marcela/Marcello/Marcelo.
            _pessoa = equipe.resolver(responsavel)
            if _pessoa:
                logger.info(f"   👤 Responsável: {responsavel!r} → {_pessoa[0]} ({_pessoa[1]})")
                responsavel = _pessoa[1]
            else:
                logger.warning(
                    f"   ⚠ Responsável {responsavel!r} nao bate com ninguem da equipe "
                    "(ou bate com mais de um) — buscando pelo nome como veio"
                )
            try:
                # Busca o input pelo label exato para não confundir com 'Escritório responsável'
                responsavel_seletor = self._encontrar_input_por_label_exato('Responsavel principal')
                if not responsavel_seletor:
                    responsavel_seletor = self._encontrar_input_por_label_exato('Responsavel')
                if not responsavel_seletor:
                    responsavel_seletor = '#input-main-responsible-input'
                self.preencher_campo_autocomplete(
                    responsavel_seletor,
                    responsavel,
                    'Responsável principal',
                    permitir_adicionar=False,
                )
            except Exception:
                logger.info("   ⚠ Campo Responsável principal não encontrado")

            # 5. Negociação de contrato de honorários *
            negociacao = (
                dados.get('negociacao_contrato')
                or self._obter_outro_dado(
                    dados,
                    'Negociação de contrato de honorários',
                    'Negociacao de contrato de honorarios',
                    'Negociação honorários',
                    'Negociacao honorarios',
                )
            )
            negociacao = self._valor_limpo(negociacao)
            if not negociacao:
                # Campo e obrigatorio: sem ele o LegalOne rejeita o salvar
                negociacao = os.getenv('LEGALONE_NEGOCIACAO_PADRAO', 'Negociação padrão')
                dados.setdefault('_qa_warnings', []).append(
                    f"Negociação de honorários não veio nos dados - usado padrão '{negociacao}'"
                )
            if negociacao:
                try:
                    seletor_negociacao = (
                        self._encontrar_input_por_label_exato('Negociacao de contrato de honorarios')
                        or '#input-negotiation-contract, input[id*="negotiation"]'
                    )
                    campo_negociacao = self.page.query_selector(seletor_negociacao)
                    valor_atual_negociacao = ''
                    if campo_negociacao:
                        valor_atual_negociacao = self.page.evaluate(
                            """
                            (el) => {
                                const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                                const invalido = (txt) => {
                                    const t = limpar(txt).toLowerCase();
                                    if (!t) return true;
                                    if (['selecione', 'selecionar', 'digite', 'buscar', 'search', ''].includes(t)) return true;
                                    if (t.includes('negociação de contrato de honorários') || t.includes('negociacao de contrato de honorarios')) return true;
                                    return false;
                                };

                                const candidatos = [];
                                if (el && typeof el.value === 'string') candidatos.push(el.value);

                                const host = el?.closest('bento-combobox, .bento-combobox, [class*="combobox"], [class*="autocomplete"], .form-group, .field-group') || el?.parentElement;
                                if (host) {
                                    const seletores = [
                                        '.bento-chip__content',
                                        '.bento-tag__label',
                                        '.bento-combobox-selection-item',
                                        '.selected-item',
                                        '.mat-mdc-chip-action-label',
                                        '.mat-chip',
                                        '[aria-selected="true"]',
                                        '.ng-value-label',
                                    ];
                                    for (const s of seletores) {
                                        for (const node of host.querySelectorAll(s)) {
                                            const txt = limpar(node.innerText || node.textContent || '');
                                            if (txt) candidatos.push(txt);
                                        }
                                    }
                                }

                                for (const c of candidatos) {
                                    if (!invalido(c)) return limpar(c);
                                }
                                return '';
                            }
                            """,
                            campo_negociacao,
                        ) or ''

                    valor_atual_negociacao = (valor_atual_negociacao or '').strip()
                    if valor_atual_negociacao:
                        logger.info(f"   ✓ Negociação de contrato de honorários já preenchido: '{valor_atual_negociacao}' — pulando")
                    else:
                        self.preencher_campo_autocomplete(
                            seletor_negociacao,
                            negociacao,
                            'Negociação de contrato de honorários',
                            permitir_adicionar=False,
                        )
                        if not self._valor_limpo(self._ler_valor_campo_formulario('Negociação de contrato de honorários')):
                            self.preencher_campo_autocomplete(
                                seletor_negociacao,
                                negociacao,
                                'Negociação de contrato de honorários',
                                permitir_adicionar=False,
                            )
                except Exception:
                    logger.info("   ⚠ Campo Negociação de contrato de honorários não encontrado")
            else:
                logger.info("   ℹ Negociação de contrato de honorários não informada; preenchendo com 'Negociação padrão'")
                try:
                    seletor_negociacao = (
                        self._encontrar_input_por_label_exato('Negociacao de contrato de honorarios')
                        or '#input-negotiation-contract, input[id*="negotiation"]'
                    )
                    campo_negociacao = self.page.query_selector(seletor_negociacao)
                    valor_atual_negociacao = ''
                    if campo_negociacao:
                        valor_atual_negociacao = self.page.evaluate(
                            """
                            (el) => {
                                const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                                const invalido = (txt) => {
                                    const t = limpar(txt).toLowerCase();
                                    if (!t) return true;
                                    if (['selecione', 'selecionar', 'digite', 'buscar', 'search', ''].includes(t)) return true;
                                    if (t.includes('negociação de contrato de honorários') || t.includes('negociacao de contrato de honorarios')) return true;
                                    return false;
                                };
                                const candidatos = [];
                                if (el && typeof el.value === 'string') candidatos.push(el.value);
                                const host = el?.closest('bento-combobox, .bento-combobox, [class*="combobox"], [class*="autocomplete"], .form-group, .field-group') || el?.parentElement;
                                if (host) {
                                    const seletores = ['.bento-chip__content', '.bento-tag__label', '.bento-combobox-selection-item', '.selected-item', '.mat-mdc-chip-action-label', '.mat-chip', '[aria-selected="true"]', '.ng-value-label'];
                                    for (const s of seletores) {
                                        for (const node of host.querySelectorAll(s)) {
                                            const txt = limpar(node.innerText || node.textContent || '');
                                            if (txt) candidatos.push(txt);
                                        }
                                    }
                                }
                                for (const c of candidatos) { if (!invalido(c)) return limpar(c); }
                                return '';
                            }
                            """,
                            campo_negociacao,
                        ) or ''
                    valor_atual_negociacao = (valor_atual_negociacao or '').strip()
                    if valor_atual_negociacao:
                        logger.info(f"   ✓ Negociação de contrato de honorários já preenchido: '{valor_atual_negociacao}' — pulando")
                    else:
                        self.preencher_campo_autocomplete(
                            seletor_negociacao,
                            'Negociação padrão',
                            'Negociação de contrato de honorários',
                            permitir_adicionar=False,
                        )
                        logger.info("   ✓ Negociação de contrato de honorários preenchida com 'Negociação padrão'")
                except Exception:
                    logger.info("   ⚠ Campo Negociação de contrato de honorários não encontrado")

            # 6. Data da baixa *
            data_baixa = (
                dados.get('data_baixa')
                or self._obter_outro_dado(dados, 'Data da baixa', 'Data de baixa', 'Baixa')
                # ponytail: default global; vira campo por processo quando o Copilot extrair a data
                or os.getenv('LEGALONE_DATA_BAIXA', '')
            )
            data_baixa = self._valor_limpo(data_baixa)
            if data_baixa:
                try:
                    seletor_data_baixa = (
                        self._encontrar_input_por_label_exato('Data da baixa')
                        or self._encontrar_input_por_label_exato('Data de baixa')
                        or self._resolver_seletor_por_label('Data da baixa')
                        or 'input[id*="data-baixa"], input[id*="date-discharge"], input[id*="baixa"], input[id*="Discharge"], input[name*="discharge" i], input[name*="DataBaixa"], input[placeholder*="baixa" i]'
                    )
                    if self._garantir_preenchimento_campo_texto('Data da baixa', data_baixa, seletor_data_baixa):
                        logger.info(f"   ✓ Data da baixa: {data_baixa}")
                    else:
                        self._fill_by_label('Data da baixa', data_baixa)
                except Exception:
                    self._fill_by_label('Data da baixa', data_baixa)

            # --- Scroll até o final do formulário para revelar campos restantes ---
            try:
                self.page.evaluate("""
                    () => {
                        // Tenta scroll no container do formulário ou na janela
                        const form = document.querySelector('form, [class*="form"], [class*="container"]');
                        if (form && form.scrollHeight > form.clientHeight) {
                            form.scrollTop = form.scrollHeight;
                        }
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                """)
                time.sleep(1)
                logger.info("   📜 Scroll até o final do formulário")
            except Exception:
                pass

            # 7. Centro de custo *
            centro_custo = dados.get('centro_custo') or dados.get('outros_dados', {}).get('Centro de custo')
            centro_custo = self._valor_limpo(centro_custo)
            if not centro_custo:
                objetos = str(dados.get('objetos', '')).lower()
                procedimento = str(dados.get('procedimento', '')).lower()
                if 'trabalho' in objetos or 'trabalhista' in objetos or 'sumaríssimo' in procedimento:
                    centro_custo = 'Trabalhista'
                elif 'civil' in objetos:
                    centro_custo = 'Civil'
                else:
                    centro_custo = 'Trabalhista'  # Default
            try:
                self.preencher_campo_autocomplete(
                    '#input-cost-center-id-0, input[id*="cost-center"]',
                    centro_custo,
                    'Centro de Custo',
                    permitir_adicionar=False,
                )
            except Exception:
                logger.info("   ⚠ Campo Centro de Custo não encontrado")

            # 8. Datacloud configurado? *
            datacloud = dados.get('datacloud_configurado') or dados.get('outros_dados', {}).get('Datacloud configurado')
            datacloud = self._sim_ou_nao(self._valor_limpo(datacloud))
            try:
                # UUID do input é dinâmico - resolve pelo label
                seletor_dc = self._resolver_seletor_por_label('Datacloud configurado')
                if seletor_dc:
                    self.preencher_campo_autocomplete(
                        seletor_dc,
                        datacloud,
                        'Datacloud configurado',
                        permitir_adicionar=False,
                    )
                else:
                    # Fallback: preenche via label diretamente
                    self._fill_by_label('Datacloud configurado', datacloud)
                    logger.info(f"   ✓ Datacloud configurado: {datacloud} (via label)")
            except Exception:
                # Último fallback: tenta via label
                try:
                    self._fill_by_label('Datacloud configurado', datacloud)
                except Exception:
                    logger.info("   ⚠ Campo Datacloud configurado não encontrado")

            # 9. Você cadastrou o Centro de Custo? *
            cadastrou_cc = dados.get('cadastrou_centro_custo') or dados.get('outros_dados', {}).get('Você cadastrou o Centro de Custo')
            cadastrou_cc = self._valor_limpo(cadastrou_cc)
            if not cadastrou_cc:
                cadastrou_cc = 'Sim'  # Default
            try:
                seletor_cc = self._resolver_seletor_por_label('cadastrou o Centro de Custo')
                if seletor_cc:
                    self.preencher_campo_autocomplete(
                        seletor_cc,
                        cadastrou_cc,
                        'Você cadastrou o Centro de Custo',
                        permitir_adicionar=False,
                    )
                else:
                    self._fill_by_label('Você cadastrou o Centro de Custo', cadastrou_cc)
                    logger.info(f"   ✓ Você cadastrou o Centro de Custo: {cadastrou_cc} (via label)")
            except Exception:
                # Tenta via label se seletor não funcionou
                self._fill_by_label('Você cadastrou o Centro de Custo', cadastrou_cc)

            # 10. Contrato de Honorários — busca por nome do cliente; fallback pro bono
            # Regra:
            #   - Se já preenchido → não mexe
            #   - Se vazio → busca por nome do cliente → seleciona 1ª opção
            #   - Se nenhum resultado com cliente → "Negociação padrão pro bono"
            try:
                honorar_seletor = (
                    self._encontrar_input_por_label_exato('Contrato de honorarios')
                    or 'input[id*="honorar"]'
                )
                campo_h = self.page.wait_for_selector(honorar_seletor, state='visible', timeout=5000)
                if campo_h:
                    # Verifica se já está preenchido (input + texto selecionado no combobox)
                    valor_atual_h = self.page.evaluate(
                        """
                        (el) => {
                            const limpar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                            const invalido = (txt) => {
                                const t = limpar(txt).toLowerCase();
                                if (!t) return true;
                                if (['selecione', 'selecionar', 'digite', 'buscar', 'search', ''].includes(t)) return true;
                                if (t.includes('contrato de honor')) return true;
                                return false;
                            };

                            const candidatos = [];
                            if (el && typeof el.value === 'string') candidatos.push(el.value);

                            const host = el?.closest('bento-combobox, .bento-combobox, [class*="combobox"], [class*="autocomplete"], .form-group, .field-group') || el?.parentElement;
                            if (host) {
                                const seletores = [
                                    '.bento-chip__content',
                                    '.bento-tag__label',
                                    '.bento-combobox-selection-item',
                                    '.selected-item',
                                    '.mat-mdc-chip-action-label',
                                    '.mat-chip',
                                    '[aria-selected="true"]',
                                    '.ng-value-label',
                                ];
                                for (const s of seletores) {
                                    for (const node of host.querySelectorAll(s)) {
                                        const txt = limpar(node.innerText || node.textContent || '');
                                        if (txt) candidatos.push(txt);
                                    }
                                }
                            }

                            for (const c of candidatos) {
                                if (!invalido(c)) return limpar(c);
                            }
                            return '';
                        }
                        """,
                        campo_h,
                    ) or ''
                    valor_atual_h = (valor_atual_h or '').strip()
                    if valor_atual_h:
                        logger.info(f"   ✓ Contrato honorários já preenchido: '{valor_atual_h}' — pulando")
                    else:
                        busca_honorar = cliente_raw or ''
                        opcoes_h = []
                        if busca_honorar:
                            campo_h.click()
                            campo_h.fill('')
                            campo_h.type(busca_honorar, delay=50)
                            time.sleep(2)
                            opcoes_h = self._extrair_opcoes_bento_combobox()
                        if opcoes_h:
                            # Seleciona primeira opção encontrada
                            self._clicar_opcao_bento_combobox(opcoes_h[0])
                            logger.info(f"   ✓ Contrato honorários: '{opcoes_h[0].get('nome', opcoes_h[0].get('texto_completo', '?'))}'")
                        else:
                            # Sem contrato com esse cliente (ou sem cliente) → pro bono
                            self.page.keyboard.press('Escape')
                            time.sleep(0.3)
                            campo_h.click()
                            campo_h.fill('')
                            campo_h.type('Negociação padrão pro bono', delay=50)
                            time.sleep(2)
                            opcoes_pb = self._extrair_opcoes_bento_combobox()
                            if opcoes_pb:
                                self._clicar_opcao_bento_combobox(opcoes_pb[0])
                            else:
                                self.page.keyboard.press('Escape')
                            logger.info("   ✓ Contrato honorários: Negociação padrão pro bono")
            except Exception:
                logger.info("   ⚠ Campo Contrato de Honorários não encontrado")

            # 11. Advogado Responsável (campo distinto do Responsável principal)
            # Usa chave dedicada 'advogado_responsavel'; NÃO usa 'advogado' pois essa
            # chave já foi consumida no step 4 (Responsável principal).
            advogado_resp = (
                dados.get('advogado_responsavel')
                or dados.get('outros_dados', {}).get('Advogado responsável')
            )
            advogado_resp = self._valor_limpo(advogado_resp)
            if advogado_resp:
                try:
                    self.preencher_campo_autocomplete(
                        'input[id*="advogado"], input[id*="lawyer"]',
                        advogado_resp,
                        'Advogado Responsável',
                        permitir_adicionar=False,
                    )
                except Exception:
                    logger.info("   ⚠ Campo Advogado Responsável não encontrado na página")

            # 12. Procedimento (se houver) — campo opcional; nem sempre presente no formulário
            procedimento_val = dados.get('procedimento') or dados.get('outros_dados', {}).get('Procedimento')
            procedimento_val = self._valor_limpo(procedimento_val)
            if procedimento_val:
                # Verifica existência com timeout curto antes de chamar preencher_campo_autocomplete
                # (que usa wait_for_selector 10 s internamente e travaria 10 s se o campo não existe)
                _campo_proc = self.page.query_selector(
                    'input[id*="procedimento"], input[id*="procedure"]'
                )
                if _campo_proc and _campo_proc.is_visible():
                    try:
                        self.preencher_campo_autocomplete(
                            'input[id*="procedimento"], input[id*="procedure"]',
                            procedimento_val,
                            'Procedimento',
                            permitir_adicionar=False,
                        )
                    except Exception:
                        logger.info("   ⚠ Campo Procedimento não encontrado na página")
                else:
                    logger.info(f"   ℹ Campo Procedimento ausente neste formulário — pulando")

            # Verificação defensiva: resolve qualquer modal de contato pendente antes de
            # preencher campos que não são autocomplete de partes (Natureza, Status).
            # Se um modal estiver aberto, seus overlays bloqueiam cliques nos campos abaixo.
            self._tratar_modal_criacao_obrigatoria()

            # 13. Natureza do processo
            # Rola até o campo ficar visível antes de preencher
            try:
                self.page.evaluate("""
                    () => {
                        const el = document.querySelector('#input-nature')
                            || document.querySelector('input[id*="nature"]')
                            || document.querySelector('bento-combobox[formcontrolname="nature"]');
                        if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    }
                """)
                time.sleep(0.5)
            except Exception:
                pass

            # Verifica se já tem texto selecionado (só pula se tiver texto não-vazio)
            natureza_atual = self._ler_valor_campo_formulario('natureza')
            if natureza_atual and len(natureza_atual.strip()) > 1 and not natureza_atual.strip().isdigit():
                logger.info(f"   ✓ Natureza já preenchida: {natureza_atual}")
                dados['natureza'] = natureza_atual
            else:
                natureza_val = self._valor_limpo(
                    dados.get('natureza')
                    or self._obter_outro_dado(
                        dados,
                        'Natureza do processo',
                        'Natureza',
                        'Natureza da ação',
                        'Natureza da acao',
                        'Natureza juridica',
                        'Natureza jurídica',
                        'Tipo da ação',
                        'Tipo da acao',
                    )
                    or 'Trabalhista'  # default para automação trabalhista
                )
                if natureza_val:
                    if not self._preencher_natureza_bento(natureza_val):
                        logger.warning("   ⚠ Não foi possível selecionar Natureza no bento-combobox")

            # 14. Status do processo — <select> nativo (id="input-status")
            # Rola até o campo ficar visível
            try:
                self.page.evaluate("""
                    () => {
                        const el = document.querySelector('#input-status');
                        if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    }
                """)
                time.sleep(0.3)
            except Exception:
                pass

            status_atual = self._ler_status_atual_formulario()
            if status_atual:
                logger.info(f"   ✓ Status já preenchido: {status_atual}")
            status_informado = self._valor_limpo(
                dados.get('status_processo')
                or self._obter_outro_dado(
                    dados,
                    'Status do processo',
                    'Status',
                    'Situação do processo',
                    'Situação',
                    'Situacao do processo',
                    'Situacao',
                )
            )
            if not status_atual:
                status_val = status_informado or 'Ativo'  # default para processos novos
                if status_val:
                    if not self._preencher_status_select(status_val):
                        logger.warning("   ⚠ Não foi possível selecionar Status")
            elif status_informado and self._normalizar_texto_busca(status_atual) != self._normalizar_texto_busca(status_informado):
                logger.info(
                    f"   ℹ Status informado '{status_informado}' ignorado porque o formulário já veio preenchido com '{status_atual}'"
                )

            # Auditoria final: detecta campos obrigatórios (*) que ainda estão vazios
            self._detectar_campos_obrigatorios_vazios()

            logger.info("\n✅ Campos obrigatórios preenchidos!")
            return True

        except NavegadorFechado:
            raise
        except Exception as e:
            logger.error(f"âŒ Erro ao preencher campos obrigatórios: {e}")
            return False

    def preencher_detalhes_faltantes(self, dados):
        """Preenche campos adicionais se estiverem vazios.

        Usa LLM para re-analisar a página após o preenchimento inicial
        e identificar campos que ainda estão vazios.
        """
        try:
            logger.info("ðŸ” Verificando lacunas no cadastro...")
            time.sleep(3) # Aguarda modal atualizar com dados da captura

            # ---------------------------------------------------------------
            # Tenta via LLM - re-analisa para preencher lacunas
            # ---------------------------------------------------------------
            if _get_page_analyzer is not None:
                try:
                    analyzer = _get_page_analyzer()
                    if analyzer.disponivel:
                        logger.info("🧠 Re-analisando página para lacunas...")
                        resultado = analyzer.ver_e_preencher(self.page, dados, confianca_minima=0.85)
                        res = resultado.get("resultado", {})
                        sucesso = res.get("sucesso", 0)
                        tentativas = res.get("tentativas", 0)
                        if tentativas > 0:
                            logger.info(
                                f"🧠 PageAnalyzer: {sucesso}/{tentativas} campos preenchidos"
                            )
                            # Se conseguiu pelo menos algum, considera resolvido
                            # e NÃO cai na heurística antiga (que quebra Kendo)
                            if sucesso > 0:
                                return True
                except Exception as e:
                    logger.debug(f"[PAGE_ANALYZER] Erro ao re-analisar: {e}")

            # ---------------------------------------------------------------
            # Fallback: preenchimento por heurística de labels
            # ---------------------------------------------------------------

            # 1. Campos Mapeados Diretamente
            campos_mapeados = {
                'Valor da Causa': dados.get('valor_causa'),
                'Fase': dados.get('fase'),
                'Instância': dados.get('instancia'),
                'Comarca': dados.get('comarca'),
                'Natureza': dados.get('natureza'),
                'Status': dados.get('status_processo'),
            }

            # 2. Campos Dinâmicos (Vindos da extração generica "outros_dados")
            # Tenta preencher qualquer campo que tenha vindo key/value do forms
            outros = dados.get('outros_dados', {})

            # Combina tudo em um dicionario para iterar
            todos_campos = {**campos_mapeados, **outros}

            for nome_campo, valor in todos_campos.items():
                if not valor: continue
                # Ignorar campos muito longos que provavelmente nao sao inputs simples
                if len(str(valor)) > 200: continue

                logger.info(f"   ↪ Tentando preencher '{nome_campo}': {valor}")

                # Tenta encontrar inputs vazios relacionados ao label
                # Como não tenho seletores exatos, uso heurística por label ou placeholder
                try:
                    # Limpa nome do campo para busca (ex: "4. Valor da Causa" -> "Valor da Causa")
                    termo_busca = nome_campo
                    if '.' in termo_busca:
                        termo_busca = termo_busca.split('.', 1)[1].strip()

                    script_busca = f"""
                        () => {{
                            const labels = Array.from(document.querySelectorAll('label'));
                            // Busca label que contenha o texto (case insensitive)
                            const target = labels.find(l => l.innerText.toLowerCase().includes('{termo_busca.lower()}'));
                            if(target) {{
                                const input = document.querySelector('#' + target.getAttribute('for')) ||
                                              target.querySelector('input') ||
                                              target.nextElementSibling?.querySelector('input');

                                if(input && (!input.value || input.value === '')) {{
                                    input.value = '{valor}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    """
                    preencheu = self.page.evaluate(script_busca)
                    if preencheu:
                        logger.info(f"      ✓ Preenchido via JS!")
                    else:
                        logger.info(f"      (Campo não encontrado ou já preenchido)")

                except Exception as e:
                    if _pagina_morta(e):
                        raise NavegadorFechado("navegador fechado ao preencher detalhes") from e
                    logger.debug(f"      Erro ao tentar preencher: {e}")

            time.sleep(1)
            return True

        except NavegadorFechado:
            raise
        except Exception as e:
            logger.error(f"âŒ Erro ao preencher detalhes: {e}")
            return False

    # ------------------------------------------------------------------
    # Fluxo de Decisão: atualiza fase de processo existente
    # ------------------------------------------------------------------
    def _fluxo_decisao(self, dados_processo):
        """Fluxo específico para Decisão: busca processo existente, abre
        edição e altera a fase conforme dados do Forms.

        Fluxo:
        1. Pesquisa CNJ na tela de busca
        2. Clica no número destacado (<span class="highlight">)
        3. Abre sidebar de ações (#sidebar-toggle)
        4. Clica "Alterar processo"
        5. Altera campo FaseText para o valor do forms
        6. Salva
        """
        try:
            logger.info("\n" + "=" * 60)
            logger.info("🔵 FLUXO DECISÃO: Atualizando fase do processo existente")
            logger.info("=" * 60)

            cnj = dados_processo.get('cnj', '')
            if not cnj:
                logger.error("[DECISÃO] CNJ não fornecido")
                self.last_error_reason = "CNJ nao fornecido para fluxo de decisao"
                return False

            # Fluxo DECISÃO sempre define fase "Decisória" no LegalOne,
            # ignorando o campo `fase` do Forms (que representa a fase
            # processual genérica - Conhecimento/Recursal/Execução).
            fase_desejada = 'Decisória'

            logger.info(f"[DECISÃO] CNJ: {cnj}")
            logger.info(f"[DECISÃO] Fase desejada: {fase_desejada}")

            # 1. Navegar para a tela de pesquisa de processos
            logger.info("[DECISÃO] 1ï¸âƒ£ Navegando para pesquisa de processos...")
            url_alvo = (
                'https://carvalhofurtadoadv.novajus.com.br/'
                'processos/processos/search'
            )
            for tentativa in range(2):
                url_atual = (self.page.url or '').lower()
                if '/processos/processos/search' in url_atual:
                    break
                try:
                    self.page.goto(
                        url_alvo,
                        wait_until='domcontentloaded',
                        timeout=25000,
                    )
                except Exception as e:
                    logger.warning(
                        f"   ⚠ goto falhou ({e}), tentando via menu..."
                    )
                    self._click_by_text(['processos', 'pastas'])
                    time.sleep(1.5)
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
                time.sleep(1.0)
            logger.info(f"   ↪ URL atual: {self.page.url}")

            # 2. Pesquisar pelo CNJ
            logger.info(f"[DECISÃO] 2ï¸âƒ£ Pesquisando CNJ: {cnj}...")
            campo = None
            seletores_busca = (
                '#Search, input[name="Search"], '
                'input[placeholder*="Pesquisar em processos"], '
                'input[placeholder*="pasta" i], '
                'input[placeholder*="Pesquisar" i][type="text"]'
            )
            for _ in range(2):
                try:
                    campo = self.page.wait_for_selector(
                        seletores_busca,
                        state='visible',
                        timeout=15000,
                    )
                    if campo:
                        break
                except Exception:
                    pass
                logger.warning(
                    "   ⚠ Campo Search não apareceu, recarregando..."
                )
                try:
                    self.page.goto(
                        url_alvo,
                        wait_until='networkidle',
                        timeout=25000,
                    )
                except Exception:
                    pass
                time.sleep(2.0)
            if not campo:
                logger.error("[DECISÃO] Campo de pesquisa não encontrado")
                self.last_error_reason = "Campo Search nao encontrado"
                return False

            campo.click()
            campo.fill('')
            campo.type(cnj, delay=40)
            time.sleep(0.3)

            btn_search = self.page.wait_for_selector(
                '#search-box-input-submit, input#search-box-input-submit, '
                'input[value="Pesquisar"], input.button[type="submit"]',
                state='visible',
                timeout=10000,
            )
            if not btn_search:
                campo.press('Enter')
            else:
                btn_search.click()

            self.page.wait_for_load_state('domcontentloaded')
            time.sleep(2.5)

            # 3. Clicar no número do processo destacado (span.highlight)
            logger.info("[DECISÃO] 3ï¸âƒ£ Clicando no processo destacado...")
            clicou_processo = self.page.evaluate(
                """
                (cnj) => {
                    const limparNum = (txt) => (txt || '').replace(/\\D/g, '');
                    const numNorm = limparNum(cnj);

                    // Procura span.highlight que contenha o CNJ
                    const highlights = Array.from(
                        document.querySelectorAll('span.highlight')
                    );
                    for (const hl of highlights) {
                        if (limparNum(hl.innerText || hl.textContent || '')
                                .includes(numNorm)) {
                            const link = hl.closest('a');
                            if (link) {
                                link.click();
                                return true;
                            }
                            hl.click();
                            return true;
                        }
                    }

                    // Fallback: qualquer elemento clicável com o CNJ
                    const rows = Array.from(
                        document.querySelectorAll('tr, .grid-row, [role="row"]')
                    );
                    for (const row of rows) {
                        if (limparNum(row.innerText || row.textContent || '')
                                .includes(numNorm)) {
                            const link = row.querySelector('a');
                            if (link) {
                                link.click();
                                return true;
                            }
                            row.click();
                            return true;
                        }
                    }
                    return false;
                }
                """,
                cnj,
            )

            if clicou_processo:
                logger.info("   ✓ Clicou no processo destacado")
                self.page.wait_for_load_state('domcontentloaded')
                time.sleep(2)
            else:
                logger.warning(
                    "[DECISÃO] Não foi possível clicar no processo destacado, "
                    "tentando via menu de ações..."
                )
                if not self._abrir_edicao_processo_por_busca(cnj):
                    logger.error("[DECISÃO] Não foi possível abrir o processo")
                    return False

            # 4. Clicar sidebar-toggle (Ver ações)
            logger.info("[DECISÃO] 4ï¸âƒ£ Abrindo sidebar de ações...")
            try:
                sidebar = self.page.wait_for_selector(
                    '#sidebar-toggle', state='visible', timeout=5000
                )
                if sidebar:
                    sidebar.click()
                    logger.info("   ✓ Sidebar aberta")
                    time.sleep(0.8)
            except Exception:
                logger.warning(
                    "   ⚠ Sidebar toggle não encontrado — prosseguindo..."
                )

            # 5. Clicar "Alterar processo"
            logger.info("[DECISÃO] 5ï¸âƒ£ Clicando 'Alterar processo'...")
            entrou_em_edicao = False
            seletores_alterar = [
                'a.command-edit:has-text("Alterar processo")',
                'a.command-link:has-text("Alterar processo")',
                'a.grid-edit-action-row:has-text("Alterar")',
                'a[href*="/processos/Processos/edit/"]:has-text("Alterar")',
                '[class*="command-edit"]:has-text("Alterar")',
                'button:has-text("Alterar processo")',
                'a:has-text("Alterar processo")',
            ]
            for sel in seletores_alterar:
                try:
                    btn = self.page.wait_for_selector(
                        sel, state='visible', timeout=3000
                    )
                    if btn:
                        btn.click()
                        logger.info(
                            f"   ✓ Clicou em 'Alterar processo' ({sel})"
                        )
                        try:
                            self.page.wait_for_load_state(
                                'domcontentloaded', timeout=8000
                            )
                        except Exception:
                            pass
                        time.sleep(1.5)
                        url_pos = (self.page.url or '').lower()
                        if '/processos/processos/edit/' in url_pos:
                            entrou_em_edicao = True
                            break
                except Exception:
                    continue

            if not entrou_em_edicao:
                logger.warning(
                    "[DECISÃO] 'Alterar processo' não encontrado na tela, "
                    "tentando fallback via busca..."
                )
                if not self._abrir_edicao_processo_por_busca(cnj):
                    logger.error(
                        "[DECISÃO] Não foi possível entrar em modo de edição"
                    )
                    return False
                entrou_em_edicao = True

            time.sleep(2)

            # 6. Alterar a fase do processo
            logger.info(
                f"[DECISÃO] 6ï¸âƒ£ Alterando fase para: {fase_desejada}..."
            )
            fase_alterada = self._alterar_fase_processo(fase_desejada)
            if not fase_alterada:
                logger.warning(
                    "[DECISÃO] Não foi possível alterar a fase automaticamente"
                )

            # 6.05 Limpa lixo de runs anteriores (campos de encerramento e
            # custom fields que foram setados indevidamente)
            logger.info(
                "[DECISÃO] 6.0ï¸âƒ£5 Limpando campos indevidos de runs anteriores..."
            )
            try:
                self._limpar_campos_indevidos_decisao()
            except Exception as e:
                logger.debug(f"[LIMPEZA] erro: {e}")

            # 6.1 Preencher demais campos da decisão (Resultado, Tipo de
            # resultado, Motivo resultado, Risco, Probabilidade, Data do
            # resultado, Data da sentença, Data da Citação, Cobrança de
            # honorários sucumbenciais, Justificativa, etc.) a partir do
            # Forms (campos vivem em `outros_dados`).
            logger.info(
                "[DECISÃO] 6.1ï¸âƒ£ Preenchendo demais campos da decisão "
                "(resultado, risco, probabilidade, datas, honorários)..."
            )
            try:
                self.preencher_detalhes_faltantes(dados_processo)
            except Exception as e:
                logger.warning(
                    f"[DECISÃO] Falha ao preencher campos adicionais: {e}"
                )

            # 7. Salvar
            logger.info("[DECISÃO] 7ï¸âƒ£ Salvando alterações...")
            salvo = self._clicar_salvar_decisao(dados_processo)
            if salvo:
                logger.info(
                    "\n✅ [DECISÃO] Fluxo de Decisão concluído com sucesso!"
                )
                return True
            else:
                logger.error("[DECISÃO] Falha ao salvar")
                self.last_error_reason = (
                    "Falha ao salvar no fluxo de decisao"
                )
                return False

        except Exception as e:
            logger.error(f"[DECISÃO] Erro no fluxo: {e}")
            self._registrar_diagnostico_falha("Fluxo Decisao", str(e))
            return False

    def _alterar_fase_processo(self, fase_desejada: str) -> bool:
        """Altera o campo FaseText no formulário de edição do processo."""
        if not fase_desejada:
            return False
        try:
            # Tenta pelo id FaseText
            fase_input = self.page.wait_for_selector(
                '#FaseText, input[name="FaseText"], input[id*="FaseText"]',
                state='visible',
                timeout=5000,
            )
            if fase_input:
                fase_input.click()
                fase_input.fill('')
                fase_input.type(fase_desejada, delay=30)
                time.sleep(0.6)
                # Tenta clicar na opção do popup do autocomplete (Kendo/dropdown)
                try:
                    self.page.wait_for_selector(
                        '.k-list-container:visible, .k-animation-container:visible, '
                        'ul.ui-autocomplete:visible',
                        timeout=2500,
                    )
                except Exception:
                    pass
                clicou_opcao = False
                try:
                    clicou_opcao = self.page.evaluate(
                        "(alvo) => {"
                        "const norm = s => (s||'').toLowerCase()"
                        ".normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').trim();"
                        "const desejado = norm(alvo);"
                        "const itens = Array.from(document.querySelectorAll("
                        "'.k-list-container .k-item, "
                        ".k-animation-container .k-item, "
                        "ul.k-list li, ul.ui-autocomplete li')"
                        ").filter(li => li.offsetParent !== null);"
                        "for (const li of itens) {"
                        "  const t = norm(li.innerText || li.textContent);"
                        "  if (t === desejado || t.startsWith(desejado)) {"
                        "    li.click(); return true;"
                        "  }"
                        "}"
                        "return false;"
                        "}",
                        fase_desejada,
                    )
                except Exception as e:
                    logger.debug(f"   (evaluate opção falhou: {e})")
                if not clicou_opcao:
                    fase_input.press('Enter')
                fase_input.evaluate(
                    "el => ['change','blur'].forEach("
                    "e => el.dispatchEvent(new Event(e, {bubbles:true})))"
                )
                logger.info(f"   ✓ Fase alterada para: {fase_desejada}")
                return True

            # Fallback: procura por label "Fase"
            if self._garantir_preenchimento_campo_texto(
                'Fase', fase_desejada
            ):
                logger.info(f"   ✓ Fase alterada via label: {fase_desejada}")
                return True

            if self._fill_by_label('Fase', fase_desejada):
                logger.info(
                    f"   ✓ Fase alterada via fill_by_label: {fase_desejada}"
                )
                return True

            logger.warning("   ⚠ Campo Fase não encontrado")
            return False
        except Exception as e:
            logger.warning(f"   ⚠ Erro ao alterar fase: {e}")
            return False

    def _limpar_campos_indevidos_decisao(self) -> int:
        """No fluxo DECISÃO, limpa campos que NÃO deveriam estar preenchidos
        (foram setados por runs anteriores quando o matching era largo).

        - Encerramento: DataBaixa, DataEncerramento, IsEncerrado, MotivoEncerramento
        - Custom fields incorretos: DataDaCitacao_*, Obra_*, NCliente_*,
          DataDoPagamento_*, Residencial_*, Supermercado*, Centro de Custo
        - Justificativas de não-cobrança quando Cobrança=Sim
        Retorna a quantidade de campos limpos.
        """
        try:
            limpos = self.page.evaluate(
                """
                () => {
                    const limpar = (input) => {
                        if (!input) return false;
                        const t = (input.type || input.tagName || '').toLowerCase();
                        if (t === 'checkbox' || t === 'radio') {
                            if (input.checked) {
                                input.checked = false;
                                input.dispatchEvent(new Event('change', {bubbles:true}));
                                return true;
                            }
                            return false;
                        }
                        if (input.value && input.value !== '') {
                            input.value = '';
                            input.dispatchEvent(new Event('input', {bubbles:true}));
                            input.dispatchEvent(new Event('change', {bubbles:true}));
                            input.dispatchEvent(new Event('blur', {bubbles:true}));
                            // Se for Kendo, limpa via API
                            if (typeof window.$ === 'function' && input.id) {
                                const $el = window.$('#' + input.id);
                                const w = $el.data('kendoComboBox')
                                    || $el.data('kendoDropDownList')
                                    || $el.data('kendoAutoComplete')
                                    || $el.data('kendoDatePicker')
                                    || $el.data('kendoNumericTextBox');
                                if (w) {
                                    try {
                                        if (typeof w.value === 'function') w.value('');
                                        if (typeof w.text === 'function') w.text('');
                                        if (typeof w.trigger === 'function') w.trigger('change');
                                    } catch(e) {}
                                }
                            }
                            return true;
                        }
                        return false;
                    };

                    let count = 0;
                    // 1.a) Desmarca IsEncerrado FORÇADAMENTE — clicando se
                    //      preciso (ASP.NET MVC só envia value=true quando
                    //      checkbox está checked; se ainda envia true,
                    //      DataBaixa fica obrigatório).
                    document.querySelectorAll(
                        'input[name="IsEncerrado"], #IsEncerrado'
                    ).forEach(el => {
                        if (el.type === 'checkbox') {
                            if (el.checked) {
                                // 1) tenta clicar (dispara handlers MVC/Kendo)
                                try { el.click(); } catch(e) {}
                                // 2) se ainda checked, força via prop+events
                                if (el.checked) {
                                    el.checked = false;
                                    el.removeAttribute('checked');
                                }
                                el.dispatchEvent(new Event('input', {bubbles:true}));
                                el.dispatchEvent(new Event('change', {bubbles:true}));
                                el.dispatchEvent(new Event('click', {bubbles:true}));
                                count++;
                            }
                        }
                    });

                    // 1.b) Demais campos de encerramento (datas e motivo)
                    const ids_exatos = [
                        'DataBaixa', 'DataEncerramento', 'MotivoEncerramento',
                    ];
                    for (const id of ids_exatos) {
                        const el = document.getElementById(id);
                        if (limpar(el)) count++;
                    }

                    // 2) Custom fields que não fazem sentido na Decisão
                    const padroes = [
                        /^DataDaCitacao_/i,
                        /^DataDoPagamento_/i,
                        /^Obra_/i,
                        /^NCliente_/i,
                        /^Residencial_/i,
                        /^Supermercado/i,
                        /^CentroDeCusto_/i,
                    ];
                    document.querySelectorAll('input, textarea, select').forEach(el => {
                        const id = el.id || '';
                        const name = el.name || '';
                        if (padroes.some(p => p.test(id) || p.test(name))) {
                            if (limpar(el)) count++;
                        }
                    });

                    // 3) Justifique a não cobrança... (só faz sentido quando Cobrança=Não)
                    document.querySelectorAll(
                        'input[id^="JustifiqueANaoCobranca"], '
                        + 'textarea[id^="JustifiqueANaoCobranca"]'
                    ).forEach(el => {
                        if (limpar(el)) count++;
                    });

                    return count;
                }
                """
            ) or 0
            if limpos:
                logger.info(
                    f"   🧹 Limpos {limpos} campos indevidos (lixo de runs anteriores)"
                )

            # Garantia extra: força uncheck do IsEncerrado via Playwright
            try:
                cb = self.page.query_selector('#IsEncerrado')
                if cb:
                    is_checked = cb.is_checked()
                    if is_checked:
                        try:
                            cb.uncheck(force=True)
                            logger.info("   🧹 IsEncerrado desmarcado via Playwright")
                        except Exception:
                            # último recurso: clica no label associado
                            lbl = self.page.query_selector(
                                'label[for="IsEncerrado"]'
                            )
                            if lbl:
                                lbl.click()
                    # Garante que o hidden seja apenas false
                    self.page.evaluate(
                        """
                        () => {
                            const cb = document.getElementById('IsEncerrado');
                            if (cb) {
                                cb.checked = false;
                                cb.removeAttribute('checked');
                                cb.dispatchEvent(new Event('change',{bubbles:true}));
                            }
                        }
                        """
                    )
            except Exception as e:
                logger.debug(f"[LIMPEZA] uncheck Playwright falhou: {e}")

            return int(limpos)
        except Exception as e:
            logger.debug(f"[LIMPEZA] falhou: {e}")
            return 0

    def _dump_form_pre_save(self) -> None:
        """Dumpa todos os inputs do form com label e value (visível e
        hidden). Logado em [DIAG] pra inspeção."""
        try:
            dados = self.page.evaluate(
                """
                () => {
                    const limpar = s => (s||'').replace(/\\s+/g,' ').trim();
                    const labelDe = (input) => {
                        if (input.id) {
                            const lbl = document.querySelector(`label[for="${input.id}"]`);
                            if (lbl) return limpar(lbl.innerText);
                        }
                        let p = input.parentElement;
                        while (p && p !== document.body) {
                            const cand = p.querySelector(':scope > label, :scope > .field-label');
                            if (cand) return limpar(cand.innerText);
                            p = p.parentElement;
                        }
                        return '';
                    };
                    const out = [];
                    const inputs = document.querySelectorAll(
                        'form input, form select, form textarea'
                    );
                    for (const i of inputs) {
                        const t = (i.type || i.tagName || '').toLowerCase();
                        if (t === 'hidden' && !i.value) continue;
                        if (t === 'button' || t === 'submit') continue;
                        const lbl = labelDe(i);
                        out.push({
                            label: lbl,
                            id: i.id || '',
                            name: i.name || '',
                            type: t,
                            value: (i.value || '').toString().slice(0, 80),
                        });
                    }
                    return out;
                }
                """
            ) or []
            preenchidos = [
                d for d in dados
                if d.get("value") and d.get("label")
            ]
            logger.info(f"[DIAG-FORM] {len(preenchidos)} campos com valor e label:")
            for d in preenchidos[:60]:
                logger.info(
                    f"   [DIAG] label='{d['label'][:40]}' "
                    f"id='{d['id']}' value='{d['value']}'"
                )
        except Exception as e:
            logger.debug(f"[DIAG-FORM] falhou: {e}")

    def _coletar_erros_validacao(self) -> list[str]:
        """Lê mensagens de erro do form (ASP.NET MVC + Kendo)."""
        try:
            erros = self.page.evaluate(
                """
                () => {
                    const out = new Set();
                    const seletores = [
                        '.field-validation-error',
                        '.validation-summary-errors li',
                        '.validation-summary-errors span',
                        '.k-tooltip-validation .k-tooltip-content',
                        '.input-validation-error + .field-validation-error',
                        '[data-valmsg-summary="true"] li',
                        '.alert-danger',
                    ];
                    for (const sel of seletores) {
                        for (const el of document.querySelectorAll(sel)) {
                            const t = (el.innerText || '').trim();
                            if (t && t.length < 300) out.add(t);
                        }
                    }
                    return Array.from(out);
                }
                """
            ) or []
            return [e for e in erros if e]
        except Exception:
            return []

    def _coletar_labels_com_erro(self) -> list[str]:
        """Para cada erro de validação, descobre o LABEL do campo que falhou.
        Sobe a árvore DOM a partir da .field-validation-error até achar um
        label visível.
        """
        try:
            return self.page.evaluate(
                """
                () => {
                    const limpar = s => (s||'').replace(/\\s+/g,' ').trim();
                    const out = new Set();
                    const erros = document.querySelectorAll(
                        '.field-validation-error, .input-validation-error, '
                        + '.k-tooltip-validation, '
                        + '[data-valmsg-summary="true"] li'
                    );
                    for (const err of erros) {
                        let p = err;
                        let lbl = null;
                        for (let i = 0; i < 10 && p; i++) {
                            const cand = p.querySelector
                                && p.querySelector('label, .field-label, .control-label');
                            if (cand) {
                                const t = limpar(cand.innerText);
                                if (t && t.length < 80) { lbl = t; break; }
                            }
                            p = p.parentElement;
                        }
                        if (lbl) out.add(lbl);
                    }
                    return Array.from(out);
                }
                """
            ) or []
        except Exception:
            return []

    def _tentar_corrigir_erros_e_resalvar(
        self,
        dados_processo: dict,
        max_tentativas: int = 2,
    ) -> bool:
        """Loop de auto-correção: lê labels com erro, repreenche só esses
        e tenta salvar de novo."""
        try:
            from page_analyzer import get_analyzer  # type: ignore
        except Exception:
            return False
        analyzer = get_analyzer()
        for tentativa in range(1, max_tentativas + 1):
            erros = self._coletar_erros_validacao()
            labels_erro = self._coletar_labels_com_erro()
            if not erros and not labels_erro:
                return False
            logger.warning(
                f"[CORREÇÃO {tentativa}/{max_tentativas}] Erros: {erros}"
            )
            logger.warning(
                f"[CORREÇÃO {tentativa}/{max_tentativas}] Labels com erro: {labels_erro}"
            )

            # Heurística específica: se o erro é em campos da seção
            # de Encerramento (Data da baixa, Data do encerramento,
            # Motivo do encerramento), a causa é IsEncerrado=true.
            # A correção é DESMARCAR IsEncerrado (e zerar essas datas),
            # NÃO preencher a data.
            labels_norm = {l.lower() for l in labels_erro}
            keywords_encerramento = (
                'data da baixa', 'data do encerramento',
                'motivo do encerramento', 'data baixa',
            )
            if any(any(k in ln for k in keywords_encerramento) for ln in labels_norm):
                logger.warning(
                    "[CORREÇÃO] Erro relacionado a Encerramento → "
                    "nukeando IsEncerrado"
                )
                try:
                    # 1) Diagnóstico inicial
                    estado_inicial = self.page.evaluate(
                        """
                        () => {
                            const out = [];
                            document.querySelectorAll(
                                '[name="IsEncerrado"], #IsEncerrado'
                            ).forEach(el => {
                                out.push({
                                    id: el.id, name: el.name, type: el.type,
                                    value: el.value, checked: el.checked,
                                    has_attr_checked: el.hasAttribute('checked'),
                                });
                            });
                            return out;
                        }
                        """
                    )
                    logger.info(f"[DIAG] IsEncerrado antes: {estado_inicial}")

                    # 2) Tenta clicar no label/wrapper visível
                    for sel in (
                        'label[for="IsEncerrado"]',
                        '.k-checkbox-label[for="IsEncerrado"]',
                        '.k-switch[data-name="IsEncerrado"]',
                        'span.k-checkbox-wrap input#IsEncerrado',
                    ):
                        try:
                            el = self.page.query_selector(sel)
                            if el and el.is_visible():
                                el.click(force=True)
                                logger.info(f"[CORREÇÃO] cliquei em {sel}")
                                time.sleep(0.2)
                                break
                        except Exception:
                            continue

                    # 3) Força via Kendo widget API + DOM crú
                    self.page.evaluate(
                        """
                        () => {
                            // Destrói Kendo widget e reseta o input
                            if (typeof window.$ === 'function') {
                                const $cb = window.$('#IsEncerrado');
                                if ($cb.length) {
                                    const w = $cb.data('kendoCheckBox')
                                        || $cb.data('kendoSwitch');
                                    if (w) {
                                        try {
                                            if (typeof w.check === 'function') w.check(false);
                                            if (typeof w.value === 'function') w.value(false);
                                            if (typeof w.trigger === 'function') w.trigger('change');
                                        } catch(e){}
                                    }
                                }
                            }
                            // Remove TODOS os inputs IsEncerrado e recria um
                            // único input hidden com value=false. O ASP.NET
                            // MVC só envia value=true se houver checkbox
                            // checked com nome IsEncerrado. Removendo todos
                            // garantimos que só o hidden=false seja enviado.
                            const todos = Array.from(document.querySelectorAll(
                                '[name="IsEncerrado"], #IsEncerrado'
                            ));
                            let form = null;
                            todos.forEach(el => {
                                form = form || el.form;
                                if (el.type === 'checkbox') {
                                    el.checked = false;
                                    el.removeAttribute('checked');
                                    el.value = 'false';
                                    el.dispatchEvent(new Event('input',{bubbles:true}));
                                    el.dispatchEvent(new Event('change',{bubbles:true}));
                                } else if (el.type === 'hidden') {
                                    el.value = 'false';
                                }
                            });

                            // Limpa datas/motivo de encerramento
                            ['DataBaixa','DataEncerramento','MotivoEncerramento'].forEach(id => {
                                const el = document.getElementById(id);
                                if (el) {
                                    el.value = '';
                                    el.dispatchEvent(new Event('input',{bubbles:true}));
                                    el.dispatchEvent(new Event('change',{bubbles:true}));
                                    el.dispatchEvent(new Event('blur',{bubbles:true}));
                                    if (typeof window.$ === 'function') {
                                        const $el = window.$('#' + id);
                                        const w = $el.data('kendoDatePicker')
                                            || $el.data('kendoDateTimePicker')
                                            || $el.data('kendoComboBox');
                                        if (w) {
                                            try {
                                                if (typeof w.value === 'function') w.value(null);
                                                if (typeof w.trigger === 'function') w.trigger('change');
                                            } catch(e){}
                                        }
                                    }
                                }
                            });
                        }
                        """
                    )
                    # 4) Diagnóstico final + sanity hook
                    estado_final = self.page.evaluate(
                        """
                        () => {
                            const out = [];
                            document.querySelectorAll(
                                '[name="IsEncerrado"], #IsEncerrado'
                            ).forEach(el => {
                                out.push({
                                    id: el.id, type: el.type,
                                    value: el.value, checked: el.checked,
                                });
                            });
                            return out;
                        }
                        """
                    )
                    logger.info(f"[DIAG] IsEncerrado depois: {estado_final}")

                    # 5) Hook submit para forçar value=false antes do POST
                    self.page.evaluate(
                        """
                        () => {
                            const form = document.querySelector(
                                'form[action*="/Edit/"]'
                            ) || document.querySelector('form');
                            if (!form || form.dataset.__isencerrado_hook) return;
                            form.dataset.__isencerrado_hook = '1';
                            form.addEventListener('submit', () => {
                                document.querySelectorAll(
                                    '[name="IsEncerrado"]'
                                ).forEach(el => {
                                    if (el.type === 'checkbox') {
                                        el.checked = false;
                                    } else {
                                        el.value = 'false';
                                    }
                                });
                            }, true);
                        }
                        """
                    )

                    time.sleep(0.5)
                    btn = self.page.query_selector(
                        'button[name="ButtonSave"][value="0"], '
                        'button[type="submit"][name="ButtonSave"], #btnSave'
                    )
                    if btn:
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        time.sleep(3)
                        try:
                            self.page.wait_for_load_state(
                                'domcontentloaded', timeout=10000
                            )
                        except Exception:
                            pass
                        if '/edit/' not in (self.page.url or '').lower():
                            logger.info("   ✓ Salvo após desmarcar IsEncerrado")
                            return True
                except Exception as e:
                    logger.warning(f"[CORREÇÃO encerramento] erro: {e}")
                # Continue to next iteration if still failed
                continue

            if not labels_erro:
                return False
            try:
                resultado = analyzer.ver_e_preencher(
                    self.page,
                    dados_processo,
                    confianca_minima=0.85,
                    labels_alvo=labels_erro,
                )
                res = resultado.get("resultado", {})
                logger.info(
                    f"[CORREÇÃO] {res.get('sucesso',0)}/{res.get('tentativas',0)} "
                    f"campos repreenchidos"
                )
            except Exception as e:
                logger.warning(f"[CORREÇÃO] falha ao re-preencher: {e}")
                return False
            time.sleep(1.0)
            # Re-clica salvar
            try:
                btn = self.page.query_selector(
                    'button[name="ButtonSave"][value="0"], '
                    'button[type="submit"][name="ButtonSave"], #btnSave'
                )
                if btn:
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(3)
                    try:
                        self.page.wait_for_load_state(
                            'domcontentloaded', timeout=10000
                        )
                    except Exception:
                        pass
                    if '/edit/' not in (self.page.url or '').lower():
                        return True
            except Exception as e:
                logger.warning(f"[CORREÇÃO] Erro ao re-clicar Salvar: {e}")
        return False

    def _clicar_salvar_decisao(self, dados_processo: dict | None = None) -> bool:
        """Clica no botão Salvar após alterações no fluxo de Decisão.
        Também verifica se ocorreu erro de validação (que mantém a página
        no modo edição e não persiste os valores)."""
        try:
            url_antes = self.page.url
            # Dump diagnóstico — ajuda a entender se valores estão no form
            self._dump_form_pre_save()
            # Captura POST do form para confirmar payload
            try:
                self.page.on(
                    "request",
                    lambda req: (
                        logger.info(
                            f"[DIAG-NET] POST {req.url} "
                            f"len(post_data)="
                            f"{len(req.post_data or '') if req.method == 'POST' else 0}"
                        )
                        if req.method == "POST" else None
                    ),
                )
            except Exception:
                pass
            seletores_salvar = [
                'button[name="ButtonSave"][value="0"]',
                'button[type="submit"][name="ButtonSave"]',
                '#btnSave',
                'button:has-text("Salvar e fechar")',
                'button:has-text("Salvar")',
                'input[type="submit"][value*="Salvar"]',
            ]
            for sel in seletores_salvar:
                try:
                    btn = self.page.wait_for_selector(
                        sel, state='visible', timeout=5000
                    )
                    if btn:
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        time.sleep(3)
                        try:
                            self.page.wait_for_load_state(
                                'domcontentloaded', timeout=15000
                            )
                        except Exception:
                            pass
                        # Verifica se ainda estamos em /edit/ — indício de
                        # erro de validação (form não submeteu)
                        url_depois = (self.page.url or '').lower()
                        if '/edit/' in url_depois:
                            erros = self._coletar_erros_validacao()
                            labels_erro = self._coletar_labels_com_erro()
                            if erros or labels_erro:
                                logger.warning(
                                    f"   ⚠ Erros após Salvar: {erros}"
                                )
                                logger.warning(
                                    f"   ⚠ Campos em erro: {labels_erro}"
                                )
                                # Tenta corrigir automaticamente
                                if dados_processo and self._tentar_corrigir_erros_e_resalvar(
                                    dados_processo
                                ):
                                    logger.info(
                                        "   ✓ Salvo com sucesso após correção automática"
                                    )
                                    return True
                                logger.error(
                                    f"   âŒ Salvar falhou — erros não corrigidos: {erros}"
                                )
                                self.last_error_reason = (
                                    f"Erros de validacao: {erros or labels_erro}"
                                )
                                return False
                            logger.warning(
                                "   ⚠ Página continua em /edit/ após Salvar — "
                                "valores podem não ter sido persistidos"
                            )
                            # Sem erros visíveis e ainda em edit — provavelmente
                            # widget Kendo não comitou. Tenta novamente.
                            time.sleep(1)
                            try:
                                btn.click()
                                time.sleep(3)
                                self.page.wait_for_load_state(
                                    'domcontentloaded', timeout=10000
                                )
                            except Exception:
                                pass
                            url_final = (self.page.url or '').lower()
                            if '/edit/' in url_final:
                                logger.error(
                                    "   âŒ Salvar não saiu de /edit/ na 2ª tentativa"
                                )
                                self.last_error_reason = (
                                    "Form de edicao nao foi submetido"
                                )
                                return False
                        logger.info("   ✓ Salvo com sucesso")
                        return True
                except Exception:
                    continue

            # Fallback JS
            try:
                self.page.evaluate(
                    """
                    () => {
                        const btn =
                            document.querySelector(
                                'button[name="ButtonSave"]'
                            ) ||
                            Array.from(
                                document.querySelectorAll(
                                    'button[type="submit"]'
                                )
                            ).find(b =>
                                (b.textContent || '').includes('Salvar')
                            );
                        if (btn) { btn.click(); return true; }
                        return false;
                    }
                    """
                )
                logger.info("   ✓ Salvo via JS")
                time.sleep(3)
                return True
            except Exception as e:
                logger.error(f"   âŒ Falha ao salvar: {e}")
                return False
        except Exception as e:
            logger.error(f"   âŒ Erro ao salvar: {e}")
            return False

    def cadastrar_processo(self, dados_processo):
        """Fluxo de cadastro usando sessão persistente"""
        self._monitoramento_solicitado = False
        self._guardian_recovered = False
        # Reset guardian call count para este cadastro
        guardian = self._get_guardian()
        if guardian:
            guardian.reset_call_count()
        logger.info("\n" + "="*60)
        logger.info("🚀 CADASTRANDO NO LEGALONE (Sessão Persistente)")
        logger.info("="*60)
        logger.info(f"CNJ: {dados_processo.get('cnj', 'N/A')}")
        logger.info(f"Cliente: {dados_processo.get('cliente') or dados_processo.get('outros_dados', {}).get('Cliente principal', 'N/A')}")
        logger.info(f"Contrário: {dados_processo.get('contrario') or dados_processo.get('outros_dados', {}).get('Contrário principal', 'N/A')}")
        logger.info(f"AgentQL: {'ATIVO' if self.use_agentql else 'INATIVO'} | Contexto obrigatório: {'SIM' if self.require_context else 'NAO'}")
        logger.info("="*60)

        self.last_error_reason = None
        # 1. Garante que navegador está aberto
        if not self.garantir_sessao_ativa():
            logger.error("âŒ Não foi possível iniciar navegador")
            self._registrar_diagnostico_falha("Garantir sessao ativa")
            return False

        # Despacho: fluxo específico para Decisão
        tipo_tarefa = dados_processo.get('tipo_tarefa_identificada', '')
        if tipo_tarefa == 'DECISAO':
            logger.info("\n[ROTEADOR] 🔵 Tipo DECISÃO detectado → Fluxo de Decisão")
            return self._fluxo_decisao(dados_processo)

        try:
            self._captura_em_rascunhos = False
            self._fluxo_pre_cadastro = False
            self._processo_ja_cadastrado = False
            # Cadastro inicial de processo que ja existe = nada a fazer. Precisa ser
            # decidido aqui porque aguardar_e_pular_etapa nao recebe dados_processo.
            self._eh_cadastro_inicial = eh_cadastro_inicial(dados_processo)
            self._pasta_existente = None
            self._ja_cadastrado_nada_a_fazer = False
            # 2. Navega até cadastro automático
            if not self.navegar_cadastro_cnj():
                self._registrar_diagnostico_falha("Navegar para cadastro CNJ")
                return False

            # 3. Preenche CNJ e captura
            if not dados_processo.get('cnj'):
                logger.error("âŒ CNJ não fornecido")
                self.last_error_reason = "CNJ nao fornecido para cadastro"
                return False

            if not self.preencher_cnj(dados_processo['cnj']):
                self._registrar_diagnostico_falha("Preencher CNJ")
                return False

            # 4. Após captura, clica em "Pular etapa" e abre "Pré-cadastro"
            if not self.aguardar_e_pular_etapa(dados_processo.get('cnj')):
                if getattr(self, '_ja_cadastrado_nada_a_fazer', False):
                    logger.info(
                        f"✅ Nada a fazer: cadastro inicial e o processo ja esta em "
                        f"'{self._pasta_existente}'. Encerrando sem alterar."
                    )
                    self.last_error_reason = None
                    return True
                if self._processo_ja_cadastrado:
                    logger.info("🔄 Processo já cadastrado no LegalOne — abrindo para alteração e cadastro de pedidos...")
                    if self.realizar_acoes_pos_cadastro(dados_processo):
                        logger.info("✅ Pedidos preenchidos no processo existente.")
                        return self._confirmar_no_acervo(dados_processo)
                    logger.error("âŒ Falha ao abrir/alterar processo existente para pedidos.")
                    if not self.last_error_reason:
                        self.last_error_reason = 'Processo já cadastrado no LegalOne'
                    return False
                if self._captura_em_rascunhos:
                    logger.info("✅ Processo enviado para rascunhos no LegalOne.")
                    # Rascunho so avanca por Editar > Continuar preenchimento
                    cnj_rasc = dados_processo.get('cnj')
                    if self._continuar_preenchimento_rascunho(cnj_rasc):
                        logger.info("Rascunho reaberto - completando cadastro...")
                        self.preencher_campos_obrigatorios(dados_processo)
                        self.preencher_detalhes_faltantes(dados_processo)
                        if self.clicar_salvar():
                            if self.realizar_acoes_pos_cadastro(dados_processo):
                                return self._confirmar_no_acervo(dados_processo)
                        return False
                    # Nao reabriu o rascunho: exclui e refaz do zero (uma vez); senao FALHA limpa.
                    # NUNCA redigitar o CNJ e clicar 'Alterar' aqui -> isso levava a tela de PERFIL.
                    if not getattr(self, '_rascunho_reiniciado', False):
                        self._rascunho_reiniciado = True
                        if self._excluir_rascunho(cnj_rasc):
                            logger.info("Rascunho excluido - refazendo o cadastro do zero...")
                            self._captura_em_rascunhos = False
                            self._processo_ja_cadastrado = False
                            return self.cadastrar_processo(dados_processo)
                    self.last_error_reason = (
                        "Nao foi possivel reabrir o rascunho em Pre-cadastro "
                        "(Editar > Continuar com o preenchimento)"
                    )
                    logger.error("   [RASCUNHO] " + self.last_error_reason)
                    return False
                logger.warning("⚠ Não foi possível executar o fluxo 'Pular etapa' -> 'Pré-cadastro'")
                return False

            if self._fluxo_pre_cadastro:
                logger.info("✅ Fluxo direcionado para 'Pré-cadastro' finalizado.")
                logger.info("ðŸ–¥ï¸  Navegador mantido aberto para conferência.")
                return True

            # Guarda defensiva: se estamos na tela de pesquisa, trate como processo existente
            # e siga para o fluxo de alteração/pedidos antes da validação de contexto de cadastro.
            try:
                url_atual = (self.page.url or "").lower()
                if "/processos/processos/search" in url_atual:
                    self._processo_ja_cadastrado = True
            except Exception:
                pass

            if self._processo_ja_cadastrado:
                logger.info("🔄 Processo já cadastrado (detectado na URL) — abrindo para alteração e pedidos...")
                if self.realizar_acoes_pos_cadastro(dados_processo):
                    logger.info("✅ Pedidos preenchidos no processo existente.")
                    return self._confirmar_no_acervo(dados_processo)
                logger.error("âŒ Falha ao abrir/alterar processo existente para pedidos.")
                if not self.last_error_reason:
                    self.last_error_reason = 'Processo já cadastrado no LegalOne'
                return False

            if not self._verificar_contexto_cadastro(dados_processo['cnj'], "antes de preencher campos"):
                logger.error("âŒ Contexto incorreto. Abortando preenchimento para evitar erro.")
                self._registrar_diagnostico_falha("Validar contexto do cadastro")
                return False

            # 5. Preenche campos obrigatórios com dados do Forms
            self.preencher_campos_obrigatorios(dados_processo)

            # 6. Preenche detalhes adicionais
            self.preencher_detalhes_faltantes(dados_processo)

            # 6b. Tenta novamente solicitar monitoramento (bloco pode ter aparecido após preencher campos)
            try:
                self._configurar_monitoramento_se_disponivel()
            except Exception:
                pass

            # 6c. QA Validator — valida em tempo real (apenas warnings, não aborta)
            try:
                from qa_validator import QAValidator
                qa = QAValidator(self.page, dados_processo, cadastro=self)
                qa_warnings = qa.validar_antes_de_salvar()
                if qa_warnings:
                    dados_processo.setdefault('_qa_warnings', []).extend(qa_warnings)
            except Exception as _qa_err:
                logger.warning(f"[QA] Validador indisponível: {_qa_err}")

            # Numero da pasta (ex.: "Proc - 0007344") ja aparece no formulario - captura p/ email
            try:
                pasta = self._valor_limpo(self._ler_valor_campo_formulario('Pasta'))
                if pasta:
                    dados_processo['numero_pasta'] = pasta
                    logger.info(f"   [PASTA] {pasta}")
            except Exception:
                pass

            # 6c. LegalOne ainda acusa obrigatorios vazios? resolve via cua-driver
            restantes = self._resolver_pendentes_com_cua(dados_processo)
            if restantes:
                dados_processo.setdefault('_qa_warnings', []).append(
                    'Campos obrigatorios seguiram vazios: ' + ', '.join(restantes)
                )

            # 7. Clica no botao Salvar
            if self.clicar_salvar():
                # O rascunho já foi convertido em processo salvo. Não tente
                # preencher novamente os campos do formulário de pré-cadastro
                # na página de edição antes de adicionar os pedidos.
                self._captura_em_rascunhos = False
                # 8. Realiza ações pós-cadastro (Clicar Proc -> Alterar -> Add Pedido)
                pos_ok = self.realizar_acoes_pos_cadastro(dados_processo)
                if not pos_ok:
                    logger.error("Acoes pos-cadastro falharam (pedidos nao cadastrados)")
                    self.last_error_reason = self.last_error_reason or "Pos-cadastro falhou (pedidos)"
                    return False

            logger.info("\n✅ Fluxo de cadastro finalizado!")
            logger.info("ðŸ–¥ï¸  Navegador mantido aberto para conferência.")

            return self._confirmar_no_acervo(dados_processo)

        except NavegadorFechado as e:
            # Aborta o ciclo em vez de reabrir o navegador e seguir as cegas.
            logger.error(f"⛔ Cadastro abortado: {e}")
            self.last_error_reason = (
                f"{e} — o cadastro precisa do Chrome aberto do inicio ao fim; "
                "rode em maquina dedicada ou nao feche o navegador durante o ciclo"
            )
            self._registrar_diagnostico_falha("Navegador fechado durante o cadastro", str(e))
            return False

        except Exception as e:
            logger.error(f"âŒ Erro no fluxo: {e}")
            self._registrar_diagnostico_falha("Fluxo de cadastro", str(e))
            if self._guardian_recovered:
                logger.info("[GUARDIAN] Retomando após recuperação bem-sucedida")
                return True
            return False

    def _tratar_modal_criacao_obrigatoria(self, nome: str = '', documento: str | None = None) -> bool:
        """Detecta e trata o modal de criação obrigatória de contato que o LegalOne
        exibe quando uma das partes não está cadastrada no sistema.

        Diferente de ``_adicionar_contato_novo`` (que é chamado intencionalmente via
        botão "Adicionar" no dropdown), este método é chamado de forma preventiva após
        ações que podem disparar o modal automaticamente (ex.: salvar o formulário
        principal com uma parte não cadastrada).

        Fluxo:
          1. Verifica se o modal está aberto (timeout curto — não bloqueia se ausente)
          2. Lê o nome já pré-preenchido pelo LegalOne (ou usa ``nome`` como fallback)
          3. Preenche CPF/CNPJ com ``documento`` — ou marca 'CPF indisponível' se ausente
          4. Clica em Salvar dentro do modal
          5. Aguarda fechamento

        Retorna True se o modal foi detectado e tratado (ou não estava aberto).
        """
        if not self.page:
            return False

        _SEL_MODAL = (
            'ngb-modal-window app-add-contact-modal, '
            '#contact-form, '
            'ngb-modal-window #input-name, '
            '[class*="add-contact"], [class*="contact-modal"]'
        )

        # 1. Verifica se o modal está visível (timeout curto para não bloquear o fluxo)
        try:
            self.page.wait_for_selector(_SEL_MODAL, state='visible', timeout=3000)
        except Exception:
            return False  # Nenhum modal obrigatório aberto — comportamento normal

        logger.info("   🔔 Modal de criação obrigatória de contato detectado!")

        # 2. Identifica o modal topmost (Angular pode empilhar ngb-modal-window)
        modal_ativo = self._obter_modal_contato_ativo()

        # 3. Lê nome pré-preenchido pelo LegalOne; usa ``nome`` como fallback
        try:
            nome_no_campo = self.page.evaluate(
                """(modal) => {
                    const root = modal || document;
                    const el = root.querySelector('#input-name')
                             || root.querySelector('input[name="name"]')
                             || root.querySelector('input[placeholder*="Nome"]')
                             || root.querySelector('input[placeholder*="nome"]');
                    return el ? (el.value || '').trim() : '';
                }""",
                modal_ativo,
            )
        except Exception:
            nome_no_campo = ''

        nome_efetivo = nome_no_campo or nome
        if nome_efetivo:
            logger.info(f"   📋 Contato no modal obrigatório: '{nome_efetivo}'")

        # Se o campo de nome estiver vazio e temos um nome para preencher, preenche
        if nome and not nome_no_campo:
            self._preencher_no_modal(
                modal_ativo,
                ['#input-name', 'input[name="name"]', 'input[placeholder*="Nome"]',
                 'input[placeholder*="nome"]', 'input[formcontrolname="name"]'],
                nome,
                'Nome',
            )

        # 4. Define Pessoa Física/Jurídica antes de preencher o documento.
        # O modal obrigatório nasce como PF, mesmo quando o contrário é uma empresa.
        documento = self._valor_limpo(documento)
        tipo_pessoa = self._resolver_tipo_pessoa(nome_efetivo, documento, None)
        eh_pf = tipo_pessoa == 'Pessoa Fisica'
        tipo_id = '#naturalPerson-checkbox' if eh_pf else '#legalPerson-checkbox'
        try:
            tipo_selecionado = self.page.evaluate(
                """(modal) => {
                    const root = modal || document;
                    const input = root.querySelector('__TIPO_ID__');
                    if (!input) return false;
                    if (!input.checked) input.click();
                    return input.checked;
                }""".replace('__TIPO_ID__', tipo_id),
                modal_ativo,
            )
            if tipo_selecionado:
                logger.info(
                    f"   ✓ Tipo do contato no modal obrigatório: "
                    f"{'Pessoa Física' if eh_pf else 'Pessoa Jurídica'}"
                )
                time.sleep(0.4)
                modal_ativo = self._obter_modal_contato_ativo() or modal_ativo
        except Exception as e:
            logger.warning(f"   ⚠ Não foi possível selecionar o tipo de pessoa: {e}")

        # Para PJ sem CNPJ informado, aplica a mesma busca usada no fluxo "Adicionar".
        if not documento and not eh_pf:
            documento = self._buscar_cnpj_web(nome_efetivo)

        # 5. CPF/CNPJ: preenche com documento se disponível, senão marca como indisponível.
        doc_preenchido = False
        if documento:
            doc_preenchido = self._preencher_no_modal(
                modal_ativo,
                ['#input-cpf-cnpj', 'input[formcontrolname="cpfCnpj"]',
                 'input[formcontrolname="cpf"]', 'input[name="cpfCnpj"]'],
                documento,
                'CPF' if eh_pf else 'CNPJ',
            )
            if not doc_preenchido:
                logger.warning("   ⚠ Não foi possível preencher o documento — marcando como indisponível")

        if not doc_preenchido:
            # Limpa o campo CPF/CNPJ e marca o checkbox de documento indisponível.
            try:
                marcou = self.page.evaluate(
                    """(modal) => {
                        const modals = document.querySelectorAll('ngb-modal-window');
                        const root = modals[modals.length - 1] || modal || document;
                        // Limpa o campo CPF
                        const cpf = root.querySelector('#input-cpf-cnpj')
                                 || root.querySelector('input[formcontrolname="cpfCnpj"]')
                                 || root.querySelector('input[formcontrolname="cpf"]');
                        if (cpf && cpf.value) {
                            cpf.value = '';
                            cpf.dispatchEvent(new Event('input', {bubbles: true}));
                        }
                        // Encontra e clica o checkbox de 'CPF não disponível'
                        const checkboxes = Array.from(
                            root.querySelectorAll('input[type="checkbox"]')
                        ).filter(cb => cb.offsetHeight > 0 && !cb.checked);
                        for (const cb of checkboxes) {
                            const lbl = cb.closest('label')
                                     || root.querySelector(`label[for="${cb.id}"]`);
                            const txt = ((lbl ? lbl.innerText : '') + ' ' + (cb.name || '')).toLowerCase();
                            if (txt.includes('disponív') || txt.includes('disponib') || txt.includes('cpf')) {
                                cb.click();
                                return true;
                            }
                        }
                        // Fallback: primeiro checkbox visível e desmarcado
                        if (checkboxes.length > 0) {
                            checkboxes[0].click();
                            return true;
                        }
                        return false;
                    }""",
                    modal_ativo,
                )
                if marcou:
                    logger.info("   ✓ Checkbox de documento indisponível marcado")
                    motivo = os.getenv(
                        'LEGALONE_MOTIVO_SEM_CPF',
                        'Recusou-se a fornecer documentação',
                    )
                    motivo_preenchido = self.page.evaluate(
                        """(modal) => {
                            const valor = __MOTIVO__;
                            const root = modal || document;
                            const seletores = [
                                'input[formcontrolname="reason"]',
                                'input[formcontrolname="motivo"]',
                                'input[formcontrolname="justificativa"]',
                                'textarea[formcontrolname="reason"]',
                                'textarea[formcontrolname="motivo"]',
                                '#input-justification',
                                'input[id*="reason"]',
                                'input[id*="motivo"]',
                            ];
                            let campo = seletores.map(s => root.querySelector(s)).find(Boolean);
                            if (!campo) {
                                const rotulo = Array.from(root.querySelectorAll('label, span, p'))
                                    .find(el => /motivo/i.test(el.textContent || ''));
                                campo = rotulo?.parentElement?.querySelector('input, textarea')
                                    || rotulo?.nextElementSibling?.querySelector?.('input, textarea');
                            }
                            if (!campo || campo.disabled) return false;
                            const proto = campo.tagName === 'TEXTAREA'
                                ? HTMLTextAreaElement.prototype
                                : HTMLInputElement.prototype;
                            Object.getOwnPropertyDescriptor(proto, 'value').set.call(campo, valor);
                            campo.dispatchEvent(new InputEvent('input', {bubbles: true}));
                            campo.dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }""".replace('__MOTIVO__', json.dumps(motivo)),
                        modal_ativo,
                    )
                    if not motivo_preenchido:
                        logger.warning("   ⚠ Campo Motivo não encontrado no modal obrigatório")
            except Exception as e:
                logger.warning(f"   ⚠ Erro ao marcar documento indisponível: {e}")

        # Aguarda Angular processar as mudanças
        time.sleep(0.6)

        # 6. Clica em Salvar dentro do modal (escoped ao modal topmost)
        salvo = False
        # Tentativa 1: botão scoped ao modal_ativo via JS
        try:
            btn_js = self.page.evaluate_handle(
                """(modal) => {
                    const root = modal || document;
                    const candidatos = Array.from(
                        root.querySelectorAll('button, [role="button"]')
                    ).filter(el => el.offsetHeight > 0 && !el.disabled);
                    return candidatos.find(b => {
                        const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                        return t === 'salvar' || t === 'save' || b.type === 'submit';
                    }) || null;
                }""",
                modal_ativo,
            )
            btn_el = btn_js.as_element() if btn_js else None
            if btn_el:
                try:
                    btn_el.click(force=True)
                except Exception:
                    btn_el.click()
                logger.info("   💾 Salvar clicado no modal obrigatório (scoped)")
                salvo = True
        except Exception:
            pass

        # Tentativa 2: locator do último ngb-modal-window
        if not salvo:
            try:
                self.page.locator('ngb-modal-window').last.get_by_role('button', name='Salvar').click()
                logger.info("   💾 Salvar clicado no modal obrigatório (locator)")
                salvo = True
            except Exception:
                pass

        # Tentativa 3: seletor global com force
        if not salvo:
            try:
                self.page.click('button:has-text("Salvar")', force=True, timeout=3000)
                logger.info("   💾 Salvar clicado no modal obrigatório (global)")
                salvo = True
            except Exception as e:
                logger.error(f"   âŒ Não foi possível clicar em Salvar no modal obrigatório: {e}")
                return False

        # 6. Aguarda o modal fechar (máx 5 s)
        for _ in range(10):
            time.sleep(0.5)
            try:
                ainda_visivel = self.page.is_visible(_SEL_MODAL)
            except Exception:
                ainda_visivel = False
            if not ainda_visivel:
                logger.info("   ✅ Modal obrigatório fechado — contato criado!")
                return True

        logger.warning("   ⚠ Modal obrigatório ainda visível após Salvar — continuando fluxo")
        return True  # Não bloqueia: tentamos tratar; o fluxo principal continua

    def _confirmar_no_acervo(self, dados_processo) -> bool:
        """Prova FINAL de sucesso: o CNJ aparece na pesquisa de processos (Pastas).

        Rascunho em Pré-cadastro não aparece na pesquisa — isso impede o email de
        sucesso falso quando o salvar só gravou o rascunho.
        """
        cnj = (dados_processo or {}).get('cnj') if isinstance(dados_processo, dict) else None
        if not cnj or 'localizado' in str(cnj).lower():
            return True  # sem CNJ pesquisável, mantém o resultado do fluxo
        texto = ''
        for tentativa in (1, 2):
            try:
                self.page.goto(
                    'https://carvalhofurtadoadv.novajus.com.br/processos/processos/search',
                    wait_until='domcontentloaded', timeout=60000,
                )
                time.sleep(6)
                campo = self.page.wait_for_selector(
                    '#Search, input[name="Search"], input[placeholder*="Pesquisar em processos"]',
                    timeout=30000,
                )
                campo.fill(str(cnj))
                self.page.keyboard.press('Enter')
                time.sleep(10)
                texto = self.page.evaluate('() => document.body.innerText') or ''
                break
            except Exception as e:
                logger.warning(f"   [ACERVO] Tentativa {tentativa} falhou: {str(e)[:120]}")
                time.sleep(5)
        try:
            if not texto:
                raise RuntimeError('nao foi possivel ler a pesquisa')
            if str(cnj) in texto and 'encontrados: 0' not in texto.lower():
                logger.info(f"   [ACERVO] Processo {cnj} confirmado na pesquisa de Pastas")
                m = re.search(r'Proc\s*-\s*\d+', texto)
                if m and isinstance(dados_processo, dict):
                    dados_processo['numero_pasta'] = m.group(0)
                return True
            self.last_error_reason = (
                f'Processo {cnj} NAO aparece na pesquisa de Pastas - provavelmente continua em Pre-cadastro (rascunho)'
            )
            logger.error(f"   [ACERVO] {self.last_error_reason}")
            return False
        except Exception as e:
            logger.warning(f"   [ACERVO] Verificacao INCONCLUSIVA ({str(e)[:120]})")
            if isinstance(dados_processo, dict):
                dados_processo.setdefault('_qa_warnings', []).append(
                    f"NAO foi possivel confirmar na pesquisa se o processo {cnj} saiu do rascunho - conferir no LegalOne"
                )
            return True

    def _confirmar_salvamento(self, timeout_s: int = 30) -> bool:
        # guarda: se estamos na tela de PERFIL/config, salvar ali nao cadastra processo
        _u = (self.page.url or "").lower()
        if "/config/" in _u or "editprofile" in _u or "usuarios" in _u:
            self.last_error_reason = "Bot caiu na tela de perfil do usuario, nao no cadastro do processo"
            logger.error("   [SALVAR] " + self.last_error_reason)
            return False
        """Confirma que o LegalOne ACEITOU o salvar (sai da tela de edicao, sem 'Campo obrigatorio').

        Clicar em Salvar com obrigatorios vazios mantem o formulario aberto (vira rascunho)
        - antes disso o robo declarava sucesso sem o processo existir.
        """
        fim = time.time() + timeout_s
        while time.time() < fim:
            time.sleep(2)
            try:
                info = self.page.evaluate(
                    """
                    () => {
                        const texto = document.body.innerText || '';
                        const erros = (texto.match(/campo obrigat/gi) || []).length;
                        const aindaNoForm = !!document.querySelector('#btnSave')
                            || /Adicionar processo/i.test(texto.slice(0, 3000));
                        return {erros, aindaNoForm};
                    }
                    """
                )
            except Exception:
                continue  # navegacao em curso
            if info.get('erros'):
                self.last_error_reason = (
                    f"Salvar REJEITADO pelo LegalOne: {info['erros']} campo(s) obrigatorio(s) vazio(s) - processo ficou em rascunho"
                )
                logger.error(f"   [SALVAR] {self.last_error_reason}")
                self._registrar_diagnostico_falha("Salvar rejeitado - campos obrigatorios")
                return False
            if not info.get('aindaNoForm'):
                logger.info("   [SALVAR] Salvamento confirmado (saiu da tela de edicao)")
                return True
        self.last_error_reason = "Salvar NAO confirmado: formulario continuou aberto apos o clique"
        logger.error(f"   [SALVAR] {self.last_error_reason}")
        return False

    _JS_PENDENTES = """
        () => {
          const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
          const labels = [];
          const add = (r) => { r = (r || '').replace(/[*\\s]+$/, '').trim(); if (r && !labels.includes(r)) labels.push(r); };
          // 1) mensagens 'Campo obrigatorio' visiveis
          const msgs = [...document.querySelectorAll('*')].filter(e =>
            vis(e) && e.children.length === 0 && /campo obrigat/i.test(e.innerText || '')
          );
          for (const m of msgs) {
            let n = m, rotulo = '';
            for (let i = 0; i < 6 && n; i++) {
              n = n.parentElement;
              if (!n) break;
              const lb = n.querySelector('label');
              if (lb && (lb.innerText || '').trim()) { rotulo = lb.innerText; break; }
            }
            if (rotulo) add(rotulo);
          }
          // 2) labels obrigatorios (com *) cujo campo esta vazio
          for (const lb of document.querySelectorAll('label')) {
            if (!vis(lb)) continue;
            const txt = (lb.innerText || '');
            if (!txt.includes('*')) continue;
            const grp = lb.closest('.form-group, .field, [class*="field"], [class*="form-"]') || lb.parentElement;
            if (!grp) continue;
            const inp = grp.querySelector('input:not([type=hidden]), select, textarea, [role="combobox"]');
            if (!inp) continue;
            let vazio;
            if (inp.tagName === 'SELECT') vazio = !inp.value;
            else vazio = !((inp.value || '').trim());
            const chip = grp.querySelector('.bento-chip, .bento-tag, .selected-item, [aria-selected="true"], .ng-value, .k-input-value-text');
            if (chip && (chip.innerText || '').trim()) vazio = false;
            if (vazio) add(txt);
          }
          const btn = document.querySelector('#btnSave')
            || [...document.querySelectorAll('button')].find(b => /salvar/i.test(b.innerText || '') && !/rascunho/i.test(b.innerText || ''));
          return {pendentes: labels, salvar_desabilitado: !!(btn && btn.disabled)};
        }
    """

    def _campos_obrigatorios_pendentes(self) -> dict:
        """Le do proprio LegalOne quais obrigatorios seguem vazios ('Campo obrigatorio') e se Salvar esta travado."""
        try:
            return self.page.evaluate(self._JS_PENDENTES) or {}
        except Exception as e:
            logger.warning(f"   [PENDENTES] Falha ao ler: {str(e)[:100]}")
            return {}

    def _resolver_pendentes_com_cua(self, dados: dict) -> list:
        """Ultima linha de defesa: cada obrigatorio ainda vazio e commitado via cua-driver (AT-SPI)."""
        estado = self._campos_obrigatorios_pendentes()
        pendentes = estado.get('pendentes') or []
        if not pendentes:
            return []
        logger.warning(f"   [PENDENTES] LegalOne acusa vazios: {pendentes}")
        dados = dados or {}
        mapa = {
            'cliente principal': self._nome_parte(dados.get('cliente') or ''),
            'contrário principal': self._nome_parte(dados.get('contrario') or ''),
            'contrario principal': self._nome_parte(dados.get('contrario') or ''),
            'posição': dados.get('posicao') or 'Reclamante',
            'posicao': dados.get('posicao') or 'Reclamante',
            'natureza': dados.get('natureza') or 'Trabalhista',
            'negociação de contrato de honorários': os.getenv('LEGALONE_NEGOCIACAO_PADRAO', 'Negociação padrão'),
            'datacloud configurado?': self._sim_ou_nao(dados.get('datacloud_configurado')),
        }
        for rotulo in pendentes:
            valor = mapa.get(rotulo.strip().lower())
            if not valor:
                logger.info(f"   [PENDENTES] Sem valor de origem para '{rotulo}'")
                continue
            self._fallback_cua_combobox(None, valor, rotulo, rotulo)
            time.sleep(1)
        restantes = (self._campos_obrigatorios_pendentes() or {}).get('pendentes') or []
        logger.info(f"   [PENDENTES] Apos cua-driver ainda vazios: {restantes or 'nenhum'}")
        return restantes

    def clicar_salvar(self):
        """Clica no botão Salvar ao final do formulário"""
        try:
            logger.info("\n💾 Salvando cadastro...")
            estado = self._campos_obrigatorios_pendentes()
            if estado.get('salvar_desabilitado'):
                pend = estado.get('pendentes') or []
                self.last_error_reason = (
                    'Salvar DESABILITADO pelo LegalOne - obrigatorios vazios: '
                    + (', '.join(pend) if pend else 'nao identificados')
                )
                logger.error(f"   [SALVAR] {self.last_error_reason}")
                self._registrar_diagnostico_falha("Salvar desabilitado")
                return False

            # Rola até o final da página para ver o botão
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # Tenta encontrar e clicar no botão Salvar
            seletores_salvar = [
                '#btnSave',
                'button:has-text("Salvar"):not(:has-text("rascunho"))',
                'button.btn-primary:has-text("Salvar")',
                'button[type="submit"]:has-text("Salvar")',
            ]

            for seletor in seletores_salvar:
                try:
                    botao = self.page.wait_for_selector(seletor, state='visible', timeout=5000)
                    if botao:
                        # Verifica se o botão está habilitado
                        is_disabled = botao.get_attribute('disabled')
                        if is_disabled:
                            logger.info("   â³ Botão Salvar desabilitado, aguardando...")
                            # Aguarda até 10 segundos para o botão ficar habilitado
                            for i in range(10):
                                time.sleep(1)
                                is_disabled = botao.get_attribute('disabled')
                                if not is_disabled:
                                    break

                        if not is_disabled:
                            botao.click()
                            logger.info("   ✅ Botão Salvar clicado!")
                            time.sleep(1)
                            try:
                                self._tratar_modal_criacao_obrigatoria()
                            except Exception as e:
                                logger.error(f"   âŒ Erro em _tratar_modal_criacao_obrigatoria: {e}")
                            time.sleep(1)
                            return self._confirmar_salvamento()
                        else:
                            logger.warning("   ⚠ Botão Salvar ainda desabilitado - campos obrigatórios faltando?")
                            return False
                except Exception as e:
                    logger.error(f"   âŒ Erro no loop de seletores_salvar: {e}")
                    continue

            # Fallback via JavaScript
            logger.info("   Tentando salvar via JavaScript...")
            try:
                clicou = self.page.evaluate("""
                    () => {
                        const btn = document.querySelector('#btnSave') ||
                                    Array.from(document.querySelectorAll('button')).find(b =>
                                        b.innerText.includes('Salvar') && !b.innerText.includes('rascunho'));
                        if (btn && !btn.disabled) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }
                """)
            except Exception as e:
                logger.error(f"   âŒ Erro no fallback JS: {e}")
                clicou = False

            if clicou:
                logger.info("   ✅ Salvo via JavaScript!")
                time.sleep(1)
                try:
                    self._tratar_modal_criacao_obrigatoria()
                except Exception as e:
                    logger.error(f"   âŒ Erro em _tratar_modal_criacao_obrigatoria (JS): {e}")
                time.sleep(1)
                return self._confirmar_salvamento()

            logger.warning("   ⚠ Não foi possível clicar em Salvar")
            return False

        except Exception as e:
            logger.error(f"âŒ Erro ao salvar: {e}")
            return False

    def _extrair_texto_detalhes_pedidos(self, dados_processo: dict | None) -> str:
        if not isinstance(dados_processo, dict):
            return ''
        outros = dados_processo.get('outros_dados', {}) or {}
        candidatos = [
            dados_processo.get('descricao_pedidos'),
            dados_processo.get('pedidos'),
            outros.get('descricao_pedidos'),
            outros.get('pedidos'),
            outros.get('Descreva todos os pedidos com as respectivas informações: pedido, valor, probabilidade atual (êxito ou perda - possível, provável, remota)'),
            outros.get('Descreva todos os pedidos com as respectivas informações'),
            outros.get('Descreva todos os pedidos'),
            outros.get('DESCREVA_TODOS_OS_PEDIDOS_COM_AS_RESPECTIVAS_INFORMACOES_PEDIDO_VALOR_PROBABILIDADE_ATUAL_EXITO_OU_PERDA_POSSIVEL_PROVAVEL_REMOTA'),
        ]
        for k, v in outros.items():
            if isinstance(k, str) and 'descreva todos os pedidos' in k.lower() and v:
                candidatos.append(v)
        for c in candidatos:
            if c:
                if isinstance(c, (list, tuple, set)):
                    return '; '.join(str(item).strip() for item in c if str(item).strip())
                return str(c).strip()
        return ''

    @staticmethod
    def _normalizar_data_legalone(valor) -> str | None:
        """Retorna data válida no formato dd/mm/yyyy ou None.

        Ano isolado (ex.: 2015 inferido do CNJ) não é uma data e nunca deve ser
        lançado como Data do Pedido/Data de Julgamento.
        """
        texto = str(valor or '').strip()
        if not texto or re.fullmatch(r'\d{4}', texto):
            return None
        texto_norm = _normalizar_pedido(texto)
        if any(marcador in texto_norm for marcador in ('nao localizado', 'n a', 'none', 'null')):
            return None

        texto = texto.split('T', 1)[0].strip()
        for formato in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(texto, formato).strftime('%d/%m/%Y')
            except ValueError:
                continue
        return None

    def _parse_pedidos_detalhados(self, texto: str) -> list[dict]:
        if not texto:
            return []

        # Mapa de sinônimos para adequar nomes do Forms ao LegalOne
        mapa_sinonimos = {
            'verbas rescisórias': 'Verbas Rescisórias',
            'verbas rescisorias': 'Verbas Rescisórias',
            '13º salario': '13º Salário',
            '13° salario': '13º Salário',
            'fgts + 40%': 'FGTS e Multa de 40%',
            'férias + 1/3': 'Férias Proporcionais + 1/3',
            'multa art. 479': 'Multa do Art. 479 da CLT',
            'benefícios-gratificações': 'Benefícios-Gratificações',
            'beneficios-gratificacoes': 'Benefícios-Gratificações',
        }
        mapa_grau = {
            'possível': 'Poss\u00edvel', 'possivel': 'Poss\u00edvel',
            'provável': 'Prov\u00e1vel', 'provavel': 'Prov\u00e1vel',
            'remota': 'Remota', 'remoto': 'Remota',
        }

        # Regex para componentes individuais (ordem-agnostic)
        re_valor = re.compile(r'R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', re.IGNORECASE)
        re_tipo = re.compile(r'\b(êxito|exito|perda)\b', re.IGNORECASE)
        re_grau = re.compile(r'\b(possível|possivel|provável|provavel|remota|remoto)\b', re.IGNORECASE)

        # Separar linhas: por \n, ; ou ponto-e-vírgula
        raw = str(texto).strip()
        linhas = re.split(r'[\n;]+', raw)
        linhas = [l.strip() for l in linhas if l.strip()]

        # O Copilot pode agrupar pedidos diferentes numa única frase. Expande
        # apenas combinações inequívocas para os nomes existentes no LegalOne.
        linhas_expandidas = []
        for linha in linhas:
            linha_norm = _normalizar_pedido(linha)
            if 'multa' in linha_norm and any(
                marcador in linha_norm for marcador in ('467', '477', '475', 'fgts')
            ):
                if '477' in linha_norm:
                    linhas_expandidas.append('Multa artigo 477 clt')
                if '467' in linha_norm:
                    linhas_expandidas.append('Multa artigo 467 clt')
                if '475' in linha_norm:
                    linhas_expandidas.append('Multa')
                if 'fgts' in linha_norm:
                    linhas_expandidas.append('FGTS+40%')
            elif '13' in linha_norm and 'ferias proporcionais' in linha_norm:
                linhas_expandidas.extend(('13º Salario Proporcional', 'Férias Proporcionais'))
            elif 'liberacao' in linha_norm and 'guia' in linha_norm:
                linhas_expandidas.extend(('Entrega das guias CD/SD', 'Entrega das guias TRCT'))
            else:
                linhas_expandidas.append(linha)
        linhas = linhas_expandidas

        itens = []
        for linha in linhas:
            m_valor = re_valor.search(linha)
            m_tipo = re_tipo.search(linha)
            m_grau = re_grau.search(linha)

            # Quando o Forms informa apenas a lista de pedidos, cadastra cada
            # item com os defaults acordados: R$ 0,00, Êxito e Possível.
            # Valores e probabilidades explícitos continuam tendo prioridade.
            valor = m_valor.group(1) if m_valor else '0,00'
            tipo_raw = (m_tipo.group(1) if m_tipo else 'êxito').lower()
            grau_raw = (m_grau.group(1) if m_grau else 'possível').lower()

            # Nome = tudo que sobra após remover valor, tipo, grau, separadores
            nome = linha
            for pattern in [re_valor, re_tipo, re_grau]:
                nome = pattern.sub('', nome)
            # Limpar R$, separadores residuais
            nome = re.sub(r'R\$', '', nome)
            nome = nome.strip(' ,;./-–—\t')
            nome = re.sub(r'\s+', ' ', nome).strip()

            if not nome:
                continue

            # Alinha o texto livre do Copilot ao catálogo canônico do LegalOne.
            nome = _resolver_pedido_catalogo(nome)

            tipo_norm = 'Perda' if tipo_raw == 'perda' else '\u00caxito'
            itens.append({
                'pedido': nome,
                'tipo': tipo_norm,
                'tipo_id': '1' if tipo_norm == 'Perda' else '0',
                'grau': mapa_grau.get(grau_raw, 'Poss\u00edvel'),
                'valor': valor,
            })

        if itens:
            logger.info(f"   [PEDIDOS] Parsed {len(itens)} pedido(s): {[i['pedido'] for i in itens]}")
        return itens

    def _abrir_edicao_processo_por_busca(self, numero_processo: str) -> bool:
        numero = self._valor_limpo(numero_processo)
        if not numero:
            return False
        try:
            logger.info(f"🔎 Fallback: pesquisando processo pelo número {numero}...")

            # Garante que estamos na tela de pesquisa de processos antes de procurar o campo Search
            url_atual = (self.page.url or '').lower()
            if '/processos/processos/search' not in url_atual:
                logger.info("   ↪ Navegando para tela de pesquisa de processos...")
                try:
                    self.page.goto(
                        'https://carvalhofurtadoadv.novajus.com.br/processos/processos/search',
                        wait_until='domcontentloaded',
                        timeout=20000,
                    )
                except Exception:
                    # fallback: tenta por menu/texto se o goto direto falhar
                    self._click_by_text(['processos', 'pastas'])
                    time.sleep(1.5)

            campo = self.page.wait_for_selector(
                '#Search, input[name="Search"], input[placeholder*="Pesquisar em processos"], input[placeholder*="pasta" i]',
                state='visible',
                timeout=15000,
            )
            if not campo:
                logger.warning("   ⚠ Campo Search não encontrado")
                return False

            campo.click()
            campo.fill('')
            campo.type(numero, delay=40)
            time.sleep(0.3)

            btn_search = self.page.wait_for_selector(
                '#search-box-input-submit, input#search-box-input-submit, input[value="Pesquisar"], input.button[type="submit"]',
                state='visible',
                timeout=10000,
            )
            if not btn_search:
                logger.warning("   ⚠ Botão Pesquisar não encontrado")
                return False
            btn_search.click()
            self.page.wait_for_load_state('domcontentloaded')
            time.sleep(2.5)

            # Tenta abrir o menu de ações da linha correspondente ao CNJ pesquisado
            num_norm = re.sub(r'\D', '', numero)

            # Passo 1: hover na linha para tornar .grid-overflow-icon visível (só aparece no hover)
            self.page.evaluate(
                """
                (numNorm) => {
                    const limparNum = (txt) => (txt || '').replace(/\\D/g, '');
                    const rows = Array.from(document.querySelectorAll('tr, .grid-row, [role="row"]'));
                    let alvo = rows.find(r => {
                        const tnorm = limparNum(r.innerText || r.textContent || '');
                        return numNorm && tnorm.includes(numNorm);
                    }) || rows.find(r => r.querySelector('.grid-overflow-icon, span.popover-menu-button'));
                    if (!alvo) return;
                    alvo.scrollIntoView({block: 'center'});
                    ['mouseover', 'mouseenter', 'mousemove'].forEach(ev =>
                        alvo.dispatchEvent(new MouseEvent(ev, { bubbles: true }))
                    );
                }
                """,
                num_norm,
            )
            time.sleep(0.5)

            # Passo 2: clica no botão de ações (agora visível após hover)
            abriu_menu = self.page.evaluate(
                """
                (numNorm) => {
                    const limparNum = (txt) => (txt || '').replace(/\\D/g, '');
                    const rows = Array.from(document.querySelectorAll('tr, .grid-row, [role="row"]'));

                    let alvo = rows.find(r => {
                        const tnorm = limparNum(r.innerText || r.textContent || '');
                        return numNorm && tnorm.includes(numNorm);
                    });
                    if (!alvo) {
                        alvo = rows.find(r => r.querySelector('.grid-overflow-icon, span.legalone-row-actions, span.popover-menu-button'));
                    }
                    if (!alvo) return false;

                    const btn = alvo.querySelector('.grid-overflow-icon')
                        || alvo.querySelector('span.legalone-row-actions.popover-menu-button')
                        || alvo.querySelector('span.popover-menu-button')
                        || alvo.querySelector('[class*="row-actions"], [class*="overflow-icon"]');
                    if (!btn) return false;

                    btn.scrollIntoView({block: 'center'});
                    ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(ev =>
                        btn.dispatchEvent(new MouseEvent(ev, { bubbles: true }))
                    );
                    if (typeof btn.click === 'function') btn.click();
                    return true;
                }
                """,
                num_norm,
            )

            if not abriu_menu:
                # Fallback Playwright: hover via mouse real depois clica
                try:
                    linha_loc = self.page.locator('tr, .grid-row').filter(has_text=numero[:20]).first
                    if linha_loc.count() > 0:
                        linha_loc.hover()
                        time.sleep(0.4)
                    menu_acoes = self.page.wait_for_selector(
                        '.grid-overflow-icon, span.legalone-row-actions.popover-menu-button, span.popover-menu-button',
                        state='attached', timeout=6000,
                    )
                    if menu_acoes:
                        menu_acoes.hover()
                        time.sleep(0.2)
                        menu_acoes.click()
                        abriu_menu = True
                except Exception:
                    pass

            if not abriu_menu:
                logger.warning("   ⚠ Menu de ações da linha não encontrado")
                return False

            time.sleep(1.2)

            # Log de debug: mostra o que o popover contem
            popover_html = self.page.evaluate("""
                () => {
                    const pop = document.querySelector('.popover, .popover-content, .dropdown-menu, [class*="popover"]');
                    if (pop) return pop.outerHTML.substring(0, 500);
                    // Tenta achar links de Alterar na pagina toda
                    const links = Array.from(document.querySelectorAll('a')).filter(a => {
                        const txt = (a.innerText || '').toLowerCase();
                        const href = (a.getAttribute('href') || '').toLowerCase();
                        return txt.includes('alterar') || href.includes('/edit/');
                    });
                    return links.map(a => `${a.className} | ${a.getAttribute('href')} | ${a.innerText.trim()}`).join('\\n') || 'nenhum link alterar encontrado';
                }
            """)
            logger.debug(f"   [DBG] Popover/links encontrados: {popover_html}")

            seletores_alterar = [
                'a.grid-edit-action-row:has-text("Alterar")',
                'a.grid-edit-action-row[href*="/processos/Processos/edit/"]',
                'a[href*="/processos/Processos/edit/"]:has-text("Alterar")',
                'a:has-text("Alterar Processo")',
            ]
            for sel in seletores_alterar:
                try:
                    el = self.page.wait_for_selector(sel, state='visible', timeout=5000)
                    if el:
                        href = el.get_attribute('href') or ''
                        if 'usuarios' in href.lower() or 'editprofile' in href.lower() or '/config/' in href.lower():
                            continue  # esse 'Alterar' vai pro PERFIL do usuario, nao pro processo
                        el.click()
                        self.page.wait_for_load_state('domcontentloaded')
                        time.sleep(2)
                        if '/config/' in (self.page.url or '').lower() or 'editprofile' in (self.page.url or '').lower():
                            logger.warning('   [ALTERAR] caiu na tela de perfil - ignorando')
                            continue
                        logger.info(f"   OK Processo aberto em modo Alterar via busca ({sel})")
                        return True
                except Exception:
                    continue

            # Fallback JS: tenta clicar em qualquer link visível de edição dentro do popover/menu
            clicou_js = self.page.evaluate(
                """
                () => {
                    const candidatos = Array.from(document.querySelectorAll('a'));
                    const alvo = candidatos.find(a => {
                        if (a.offsetHeight === 0) return false;
                        const href = (a.getAttribute('href') || '').toLowerCase();
                        const txt = (a.innerText || a.textContent || '').trim().toLowerCase();
                        return href.includes('/processos/processos/edit/') || txt === 'alterar' || txt.includes('alterar processo');
                    });
                    if (!alvo) return false;
                    alvo.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    alvo.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    alvo.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    if (typeof alvo.click === 'function') alvo.click();
                    return true;
                }
                """
            )
            if clicou_js:
                logger.info("   OK Processo aberto em modo Alterar via busca (fallback JS)")
                self.page.wait_for_load_state('domcontentloaded')
                time.sleep(2)
                return True

            # Fallback final: extrai href de edição do resultado da busca e navega direto
            edit_href = self.page.evaluate(
                """
                () => {
                    const link = document.querySelector('a[href*="/processos/Processos/edit/"]');
                    return link ? link.getAttribute('href') : null;
                }
                """
            )
            if edit_href:
                base_url = self.page.url.split('/processos')[0] if '/processos' in self.page.url else 'https://carvalhofurtadoadv.novajus.com.br'
                full_url = edit_href if edit_href.startswith('http') else base_url + edit_href
                logger.info(f"   OK Navegando direto para URL de edicao: {full_url}")
                self.page.goto(full_url, wait_until='domcontentloaded', timeout=20000)
                time.sleep(2)
                return True

            logger.warning("   WARN Link 'Alterar' nao encontrado apos busca")
            return False
        except Exception as e:
            logger.warning(f"   ⚠ Falha no fallback de busca do processo: {e}")
            return False

    def _abrir_secao_pedidos(self) -> bool:
        try:
            # Clica no header/toggle para expandir a seção de pedidos (a lista começa hidden)
            clicou_header = self.page.evaluate("""
                () => {
                    const seletores = [
                        'a[href="#pedidos"], a[data-target="#pedidos"]',
                        '.panel-heading a[href*="pedidos"], .panel-heading a[data-toggle]',
                        'h3.panel-title a, h4.panel-title a',
                        '[data-toggle="collapse"][href*="pedido"]',
                        'a.collapsed[data-toggle], a[data-toggle="collapse"]',
                        '.collection-panel-header a, .panel-header a',
                    ];
                    for (const sel of seletores) {
                        try {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                const txt = (el.innerText || el.textContent || '').toLowerCase();
                                if (txt.includes('pedido') || el.closest('[id*="pedido"], [class*="pedido"]')) {
                                    el.scrollIntoView({block: 'center'});
                                    el.click();
                                    return true;
                                }
                            }
                        } catch(e) {}
                    }
                    // Fallback: toggle mais próximo do ul.pedidos-list
                    const ul = document.querySelector('ul.pedidos-list');
                    if (ul) {
                        const panel = ul.closest('.panel, .card, .collection-panel, section');
                        if (panel) {
                            const toggle = panel.querySelector('a[data-toggle], button[data-toggle], .panel-title a, .panel-heading a');
                            if (toggle) { toggle.click(); return true; }
                        }
                        ul.scrollIntoView({block: 'center'});
                    }
                    return false;
                }
            """)
            if clicou_header:
                logger.info("   ✓ Header da seção de pedidos clicado")
                time.sleep(1.2)

            # Verifica visibilidade sem depender de wait_for_selector
            visivel = self.page.evaluate("""
                () => {
                    const ul = document.querySelector('ul.pedidos-list.edit-list.collection-panel-item, ul.pedidos-list');
                    if (!ul) return false;
                    const style = window.getComputedStyle(ul);
                    return style.display !== 'none' && style.visibility !== 'hidden' && ul.offsetHeight > 0;
                }
            """)

            if not visivel:
                # Força exibição via JS
                self.page.evaluate("""
                    () => {
                        const ul = document.querySelector('ul.pedidos-list');
                        if (ul) {
                            ul.style.display = '';
                            ul.style.visibility = 'visible';
                            ul.classList.remove('hidden', 'collapse');
                            ul.scrollIntoView({block: 'center'});
                        }
                    }
                """)
                time.sleep(0.5)

            logger.info("   ✓ Seção de pedidos aberta")
            return True

        except Exception as e:
            logger.warning(f"   ⚠ Não foi possível abrir seção de pedidos: {e}")
            return False

    def _clicar_adicionar_pedido(self) -> bool:
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
                    logger.info(f"   + 'Adicionar pedido' clicado via: {sel}")
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
                logger.info("   + 'Adicionar pedido' clicado via JS fallback")
                return True
        except Exception:
            pass

        # Guardian rescue
        guardian = self._get_guardian()
        if guardian:
            rescued = guardian.rescue(
                "adicionar_pedido",
                "Botao 'Adicionar pedido' nao encontrado por nenhum seletor",
                Exception("Todos os seletores falharam para #add_pedido")
            )
            if rescued:
                time.sleep(1.0)
                return True

        return False

    def _selecionar_pedido_no_dropdown(self, inp_nome, nome_pedido: str) -> bool:
        """Digita texto parcial no campo NomePedido, espera dropdown e seleciona match.

        Estratégia:
        1. Digita primeiras palavras do pedido para acionar busca no dropdown
        2. Aguarda opções aparecerem no dropdown (listbox/combobox)
        3. Verifica se alguma opção contém o nome do pedido
        4. Clica na opção correta
        5. Se não encontrar → retorna False (caller deve parar)
        """
        nome_pedido = _resolver_pedido_catalogo(nome_pedido)
        # O lookup do LegalOne filtra sua treeTable pelo texto completo. Usar
        # apenas as primeiras palavras deixa itens ambíguos como "Multa".
        texto_busca = nome_pedido

        try:
            inp_nome.click(timeout=5000)
            inp_nome.fill('', timeout=5000)
            inp_nome.type(texto_busca, delay=30, timeout=5000)
        except Exception as e:
            logger.error(f"      ❌ Campo do pedido não respondeu em 5s: {e}")
            return False
        time.sleep(1.0)  # Esperar dropdown carregar resultados

        # Tentar localizar dropdown com opções
        seletores_dropdown = [
            # Estrutura real do LegalOne: lookup dropdown com uma tabela de árvore.
            '.lookup-dropdown[style*="display: block"] .treeTable tbody tr.initialized',
            '.lookup-dropdown[style*="display: block"] .treeTable tbody tr[data-val-level]',
            '.lookup-dropdown .treeTable tbody tr.initialized',
            '.lookup-dropdown .treeTable tbody tr[data-val-level]',
            '[id$="_dropdown"] .treeTable tbody tr.initialized',
            '[id$="_dropdown"] .treeTable tbody tr[data-val-level]',
            '[role="listbox"] [role="option"]',
            '.bento-combobox-container [role="option"]',
            '.bento-list [role="option"]',
            '[id*="bui-combobox-list"] [role="option"]',
            '.lookup-list li',
            '.dropdown-menu li',
            '.autocomplete-items div',
            '[role="listbox"] li',
        ]

        opcoes_encontradas = []
        # A tabela do lookup é carregada assincronamente após a digitação.
        # Não pressionar Enter nem aceitar o texto livre enquanto ela não aparecer.
        for _ in range(6):
            for sel in seletores_dropdown:
                try:
                    opcoes = self.page.locator(sel)
                    count = opcoes.count()
                    if count > 0:
                        for i in range(count):
                            opt = opcoes.nth(i)
                            try:
                                txt = (opt.inner_text() or '').strip()
                                if txt:
                                    opcoes_encontradas.append((opt, txt))
                            except Exception:
                                continue
                        if opcoes_encontradas:
                            break
                except Exception:
                    continue
            if opcoes_encontradas:
                break
            time.sleep(0.5)

        if not opcoes_encontradas:
            logger.error(
                f"      âŒ Pedido NÃO encontrado no dropdown: '{nome_pedido}' "
                f"(buscou: '{texto_busca}'). Nenhuma opção disponível."
            )
            return False

        # Buscar match no dropdown — comparação case-insensitive e sem acentos
        import unicodedata
        def remover_acentos(txt):
            return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

        nome_lower = remover_acentos(nome_pedido.lower())
        melhor_match = None
        for opt, txt in opcoes_encontradas:
            txt_lower = remover_acentos(txt.lower())
            # Match exato ou parcial (nome do pedido contido na opção ou vice-versa)
            if nome_lower in txt_lower or txt_lower in nome_lower:
                melhor_match = (opt, txt)
                break

        if not melhor_match:
            # Tentar match por primeiras palavras
            busca_lower = remover_acentos(texto_busca.lower())
            for opt, txt in opcoes_encontradas:
                if busca_lower in remover_acentos(txt.lower()):
                    melhor_match = (opt, txt)
                    break

        if not melhor_match:
            # Fallback: tentar sinônimos do dicionário PEDIDOS_SINONIMOS
            try:
                chave_norm = _normalizar_pedido(nome_pedido)
                candidatos_sin = []
                for chave, sinonimos in PEDIDOS_SINONIMOS.items():
                    if _normalizar_pedido(chave) == chave_norm or chave_norm in _normalizar_pedido(chave):
                        candidatos_sin.extend([chave] + list(sinonimos))
                    else:
                        for sn in sinonimos:
                            if _normalizar_pedido(sn) == chave_norm:
                                candidatos_sin.extend([chave] + list(sinonimos))
                                break
                for cand in candidatos_sin:
                    cand_norm = _normalizar_pedido(cand)
                    for opt, txt in opcoes_encontradas:
                        txt_norm = _normalizar_pedido(txt)
                        if cand_norm in txt_norm or txt_norm in cand_norm:
                            melhor_match = (opt, txt)
                            logger.info(f"      ℹ Match via sinônimo '{cand}' → '{txt}'")
                            break
                    if melhor_match:
                        break
            except Exception:
                pass

        if not melhor_match:
            # Última tentativa: o catálogo da interface pode ter variações que
            # não existem no Copilot. Escolhe somente um resultado bem próximo.
            candidatos = [
                (self._calcular_similaridade(nome_pedido, txt), opt, txt)
                for opt, txt in opcoes_encontradas
            ]
            if candidatos:
                score, opt, txt = max(candidatos, key=lambda item: item[0])
                if score >= 0.78:
                    melhor_match = (opt, txt)
                    logger.info(
                        f"      ℹ Match aproximado do catálogo: '{nome_pedido}' → '{txt}' ({score:.0%})"
                    )

        if not melhor_match:
            nomes_disponiveis = [txt for _, txt in opcoes_encontradas[:10]]
            logger.error(
                f"      âŒ Pedido NÃO encontrado no dropdown: '{nome_pedido}'. "
                f"Opções disponíveis: {nomes_disponiveis}"
            )
            # Fechar dropdown sem selecionar
            self.page.keyboard.press('Escape')
            time.sleep(0.3)
            inp_nome.fill('')
            return False

        # Selecionar opção encontrada
        opt_element, opt_texto = melhor_match
        try:
            opt_element.scroll_into_view_if_needed()
            opt_element.click(timeout=5000)
            time.sleep(0.5)
            logger.info(f"      ✓ Pedido selecionado no dropdown: '{opt_texto}'")
            return True
        except Exception as e:
            logger.error(f"      âŒ Falha ao clicar opção '{opt_texto}' no dropdown: {e}")
            return False

    def _localizar_linha_pedido(self):
        """Localiza a última linha/item de pedido na seção de pedidos.

        LegalOne pode usar <ul class="pedidos-list"><li> ou <tbody><tr>.
        Tenta ambos seletores.
        """
        # Seletores em ordem de prioridade (ul/li primeiro, depois table/tr)
        seletores_row = [
            'ul.pedidos-list li:has(input[id*="NomePedidoText"])',
            'ul.pedidos-list li:has(input[name*="NomePedidoText"])',
            '.collection-panel-item li:has(input[id*="NomePedidoText"])',
            'li:has(input[id*="NomePedidoText"])',
            'tbody tr:has(input[id*="__NomePedidoText"])',
            'tbody tr:has(input[name*=".NomePedidoText"])',
        ]
        for sel in seletores_row:
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0:
                    logger.info(f"      ℹ Linha de pedido encontrada via: {sel} ({loc.count()} linhas)")
                    return loc.last
            except Exception:
                continue

        # Fallback: buscar diretamente o input de nome e subir pro container pai
        try:
            inp = self.page.locator('input[id*="NomePedidoText"], input[name*="NomePedidoText"]').last
            if inp.count() > 0:
                # Retorna o elemento pai mais próximo que seja li ou tr
                parent = inp.locator('xpath=ancestor::li[1] | ancestor::tr[1]')
                if parent.count() > 0:
                    logger.info("      ℹ Linha de pedido encontrada via xpath ancestor do input")
                    return parent.last
        except Exception:
            pass

        return None

    def _preencher_linha_pedido_atual(self, item: dict) -> bool:
        try:
            row = self._localizar_linha_pedido()
            if not row:
                # Fallback 1: tentar clicar em "Adicionar pedido" antes de desistir
                try:
                    self.page.locator(
                        'button:has-text("Adicionar pedido"), button:has-text("Novo pedido"), a:has-text("Adicionar pedido")'
                    ).first.click(timeout=3000)
                    time.sleep(1.0)
                    row = self._localizar_linha_pedido()
                except Exception:
                    pass

            if not row:
                # Debug: logar estrutura do DOM na seção pedidos
                try:
                    html_pedidos = self.page.evaluate(
                        "document.querySelector('ul.pedidos-list, .pedidos-section, #pedidos')?.outerHTML?.substring(0, 800) || 'SECAO_PEDIDOS_NAO_ENCONTRADA'"
                    )
                    logger.warning(f"      ⚠ [QA] 📸 DOM pedidos: {html_pedidos}")
                except Exception:
                    pass
                # Dump adicional de qualquer elemento com classe contendo 'pedido'
                try:
                    logger.error(
                        f"[DOM-DUMP] {self.page.locator('[class*=pedido]').first.inner_html()[:3000]}"
                    )
                except Exception:
                    pass
                # Screenshot QA
                try:
                    from qa_validator import QAValidator
                    QAValidator(self.page, {})._tirar_screenshot("pedidos_secao_nao_encontrada")
                except Exception:
                    pass
                logger.warning("      ⚠ [QA] 📸 Linha de pedido não localizada (nem ul>li nem tbody>tr)")
                return False

            campos_preenchidos = 0
            campos_esperados = 0

            # --- Campo Nome do Pedido (com validação de dropdown) ---
            inp_nome = row.locator('input[id*="NomePedidoText"], input[name*="NomePedidoText"]').first
            if inp_nome.count() == 0:
                # Fallback: buscar qualquer input de texto na row que pareça ser nome
                inp_nome = row.locator('input[type="text"]').first
                logger.warning("      ⚠ Campo NomePedidoText não encontrado, usando primeiro input de texto")

            if not self._selecionar_pedido_no_dropdown(inp_nome, item['pedido']):
                logger.error(
                    f"      âŒ ERRO CRÃTICO: Pedido '{item['pedido']}' não encontrado no sistema. "
                    f"Cadastro de pedidos INTERROMPIDO."
                )
                return False
            campos_preenchidos += 1

            # --- Campo Tipo (Êxito/Perda) ---
            campos_esperados += 1
            sel_tipo = row.locator('select[id*="ProbabilidadeTipoId"], select[name*="ProbabilidadeTipoId"]').first
            if sel_tipo.count() > 0:
                sel_tipo.select_option(item['tipo_id'])
                campos_preenchidos += 1
                logger.info(f"      ✓ Tipo: {item['tipo']} (value={item['tipo_id']})")
            else:
                logger.warning("      ⚠ Campo ProbabilidadeTipoId (select) NÃO encontrado na linha")

            # --- Campo Probabilidade (Possível/Provável/Remota) ---
            campos_esperados += 1
            inp_prob = row.locator('input[id*="ProbabilidadeText"], input[name*="ProbabilidadeText"]').first
            if inp_prob.count() > 0:
                inp_prob.click()
                inp_prob.fill('')
                inp_prob.type(item['grau'], delay=30)
                time.sleep(0.4)
                self.page.keyboard.press('Enter')
                campos_preenchidos += 1
                logger.info(f"      ✓ Probabilidade: {item['grau']}")
            else:
                logger.warning("      ⚠ Campo ProbabilidadeText NÃO encontrado na linha")

            # --- Campo Contingência (Ativa/Passiva/Sem Contingência) ---
            contingencia_id = item.get('contingencia_id', '')
            if contingencia_id:
                campos_esperados += 1
                sel_conting = row.locator('select[id*="ContingenciaId"], select[name*="ContingenciaId"]').first
                if sel_conting.count() > 0:
                    try:
                        sel_conting.select_option(contingencia_id)
                        campos_preenchidos += 1
                        logger.info(f"      ✓ Contingência: value={contingencia_id}")
                    except Exception as e:
                        logger.warning(f"      ⚠ Falha ao selecionar contingência: {e}")
                else:
                    logger.warning("      ⚠ Campo ContingenciaId (select) NÃO encontrado na linha")

            # --- Campo Data do Pedido (dd/mm/yyyy) ---
            data_pedido = item.get('data_pedido', '')
            if data_pedido:
                campos_esperados += 1
                inp_data_ped = row.locator(
                    'input[id^="Pedidos_"][id$="__DataPedido"], '
                    'input[name^="Pedidos["][name$="].DataPedido"], '
                    'input[id*="DataPedido"], input[name*="DataPedido"]'
                ).first
                if inp_data_ped.count() > 0:
                    try:
                        inp_data_ped.click()
                        inp_data_ped.fill('')
                        inp_data_ped.type(data_pedido, delay=20)
                        self.page.keyboard.press('Tab')
                        time.sleep(0.3)
                        campos_preenchidos += 1
                        logger.info(f"      ✓ Data do pedido: {data_pedido}")
                    except Exception as e:
                        logger.warning(f"      ⚠ Falha data pedido: {e}")
                else:
                    logger.warning("      ⚠ Campo DataPedido NÃO encontrado na linha")

            # --- Campo Data do Julgamento (dd/mm/yyyy) - opcional ---
            data_julgamento = item.get('data_julgamento', '')
            if data_julgamento:
                campos_esperados += 1
                inp_data_julg = row.locator('input[id*="DataJulgamento"], input[name*="DataJulgamento"]').first
                if inp_data_julg.count() > 0:
                    try:
                        inp_data_julg.click()
                        inp_data_julg.fill('')
                        inp_data_julg.type(data_julgamento, delay=20)
                        self.page.keyboard.press('Tab')
                        time.sleep(0.3)
                        campos_preenchidos += 1
                        logger.info(f"      ✓ Data julgamento: {data_julgamento}")
                    except Exception as e:
                        logger.warning(f"      ⚠ Falha data julgamento: {e}")
                else:
                    logger.warning("      ⚠ Campo DataJulgamento NÃO encontrado na linha")

            # --- Campo Valor ---
            campos_esperados += 1
            inp_valor = row.locator('input[id*="ValorPedido_Value"], input[id*="ValorPedido.Value"], input[name*="ValorPedido.Value"], input[name*="ValorPedido_Value"]').first
            if inp_valor.count() > 0:
                inp_valor.click()
                inp_valor.fill('')
                inp_valor.type(item['valor'], delay=20)
                self.page.keyboard.press('Tab')
                campos_preenchidos += 1
                logger.info(f"      ✓ Valor: R$ {item['valor']}")
            else:
                logger.warning("      ⚠ Campo ValorPedido NÃO encontrado na linha")

            # --- Log final com contagem real ---
            if campos_preenchidos < campos_esperados:
                logger.warning(
                    f"      ⚠ Pedido '{item['pedido']}': {campos_preenchidos}/{campos_esperados} campos extras preenchidos"
                )
            logger.info(
                f"      ✓ Pedido: {item['pedido']} | {item['tipo']} / {item['grau']} | R$ {item['valor']}"
                f" | Conting={contingencia_id or 'N/A'} | Data={data_pedido or 'N/A'}"
                f" | Campos: {campos_preenchidos}/{campos_esperados}"
            )
            return True
        except Exception as e:
            logger.warning(f"      ⚠ Falha ao preencher pedido '{item.get('pedido', '?')}': {e}")
            return False

    def _preencher_pedidos_forms(self, dados_processo: dict | None) -> tuple[int, int]:
        texto = self._extrair_texto_detalhes_pedidos(dados_processo or {})
        logger.info(f"   [DEBUG-PEDIDOS] Texto extraído: {repr(texto[:300]) if texto else '(vazio)'}")
        itens = self._parse_pedidos_detalhados(texto)
        if not itens:
            logger.info("   ℹ Sem detalhes de pedidos no Forms para preencher")
            return 0, 0

        # Extrair contingência e data dos pedidos do Forms (campos globais, aplicam a todos os pedidos)
        dp = dados_processo or {}
        outros = dp.get('outros_dados', {}) or {}

        # Contingência: Ativa / Passiva / Sem Contingência
        contingencia_raw = (
            dp.get('contingencia')
            or outros.get('Contingência')
            or outros.get('contingencia')
            or ''
        )
        contingencia_lower = str(contingencia_raw).strip().lower()
        # Mapear para value do select: 0=Ativa, 1=Passiva, 2=Sem Contingência
        if 'passiva' in contingencia_lower:
            contingencia_id = '1'
        elif 'ativa' in contingencia_lower:
            contingencia_id = '0'
        elif 'sem' in contingencia_lower:
            contingencia_id = '2'
        else:
            contingencia_id = ''  # Não preenche se não veio do Forms

        def resolver_data(*candidatos):
            for bruto in candidatos:
                if bruto in (None, ''):
                    continue
                data_normalizada = self._normalizar_data_legalone(bruto)
                if data_normalizada:
                    return data_normalizada
                logger.warning(
                    f"   ⚠ Data inválida descartada para pedido: '{bruto}'. "
                    "Esperado dd/mm/aaaa ou aaaa-mm-dd."
                )
            return ''

        # Data do pedido não deve receber apenas o ano de distribuição do CNJ.
        data_pedido = resolver_data(
            dp.get('data_pedido'),
            outros.get('Data dos pedidos'),
            outros.get('data_pedido'),
            dp.get('data_distribuicao'),
            outros.get('Data de distribuição'),
            outros.get('Data de distribuicao'),
            outros.get('data_distribuicao'),
        )

        # Data do julgamento (dd/mm/yyyy) - opcional
        data_julgamento = resolver_data(
            dp.get('data_julgamento'),
            outros.get('Data do julgamento'),
            outros.get('data_julgamento'),
        )

        if contingencia_id:
            logger.info(f"   ℹ Contingência do Forms: '{contingencia_raw}' → value={contingencia_id}")
        if data_pedido:
            logger.info(f"   ℹ Data dos pedidos do Forms: {data_pedido}")
        if data_julgamento:
            logger.info(f"   ℹ Data do julgamento do Forms: {data_julgamento}")

        # Injetar dados globais em cada item de pedido
        for item in itens:
            item['contingencia_id'] = contingencia_id
            item['data_pedido'] = data_pedido
            item['data_julgamento'] = data_julgamento

        logger.info(f"4ï¸âƒ£  Preenchendo pedidos do Forms ({len(itens)} itens)...")
        preenchidos = 0
        guardian = self._get_guardian()
        max_retries_pedido = 2

        for idx, item in enumerate(itens):
            # --- Adicionar pedido (exceto primeiro) ---
            if idx > 0:
                if not self._clicar_adicionar_pedido():
                    logger.warning(f"      ⚠ Botao 'Adicionar pedido' falhou para item {idx + 1}")
                    # Vision retry: popup/overlay pode estar bloqueando
                    if guardian:
                        rescued = guardian.rescue(
                            "adicionar_pedido_bloqueado",
                            f"Item {idx+1}/{len(itens)}, pedido: {item.get('pedido','')}",
                            Exception("Botao adicionar pedido nao encontrado/clicavel")
                        )
                        if rescued and self._clicar_adicionar_pedido():
                            pass  # Recuperado com sucesso
                        else:
                            logger.error(f"      Mesmo apos guardian, botao 'Adicionar pedido' falhou")
                            break
                    else:
                        break

            # --- Preencher linha com retry inteligente ---
            ok = False
            for attempt in range(1, max_retries_pedido + 1):
                ok = self._preencher_linha_pedido_atual(item)
                if ok:
                    break

                if attempt < max_retries_pedido and guardian:
                    logger.info(f"      Retry {attempt} para pedido '{item['pedido']}' via Vision...")

                    # Verificar se ainda estamos na pagina certa
                    if not self._verificar_estado_pagina("secao_pedidos"):
                        logger.warning("      [GUARD] Saiu da secao de pedidos durante preenchimento")
                        rescued = guardian.rescue(
                            "pedido_pagina_errada",
                            f"Pedido: {item.get('pedido','')}, tentativa {attempt}",
                            Exception("Pagina nao esta na secao de pedidos")
                        )
                        if not rescued:
                            break
                        time.sleep(1)
                        continue

                    # Vision analisa estado atual — pode dismiss popup/scroll
                    rescued = guardian.rescue(
                        "preencher_pedido_falha",
                        f"Pedido: {item.get('pedido','')}, dropdown nao encontrou match",
                        Exception(f"Pedido '{item['pedido']}' nao selecionado no dropdown")
                    )
                    if not rescued:
                        break
                    time.sleep(1)

            if not ok:
                logger.error(
                    f"   Pedido '{item['pedido']}' falhou apos {max_retries_pedido} tentativas. "
                    f"Cadastro PARADO no item {idx + 1}/{len(itens)}."
                )
                break

            preenchidos += 1
            time.sleep(0.4)

        logger.info(f"   ✅ Pedidos preenchidos: {preenchidos}/{len(itens)}")
        if preenchidos < len(itens):
            logger.error(
                f"   âŒ ATENÇÃO: {len(itens) - preenchidos} pedido(s) NÃO cadastrado(s). "
                f"Verifique se os nomes dos pedidos correspondem ao menu suspenso do LegalOne."
            )
        return preenchidos, len(itens)

    def _abrir_processo_pela_tela_atual(self, numero_processo: str | None = None) -> bool:
        numero = self._valor_limpo(numero_processo) or ''
        num_norm = re.sub(r'\D', '', numero)
        try:
            logger.info("1ï¸âƒ£  Procurando link do processo ('Proc')...")

            # Prioriza seletores por href (precisos) antes de text-based (genéricos)
            seletores = [
                'a[href*="/processos/processos/details/"]',
                'a[href*="/processos/Processos/details/"]',
                'a[href*="/processos/processos/edit/"]',
                'a[href*="/processos/Processos/edit/"]',
            ]

            # Seletores text-based são arriscados (podem pegar navbar) — usados só como último recurso
            seletores_texto = [
                'a:has-text("Proc")',
            ]

            url_antes = self.page.url

            for sel in seletores + seletores_texto:
                try:
                    elementos = self.page.query_selector_all(sel)
                except Exception:
                    elementos = []
                for el in elementos:
                    try:
                        if not el or not el.is_visible():
                            continue
                        txt = (el.inner_text() or '').strip()
                        href = (el.get_attribute('href') or '').strip()

                        # Rejeitar links de navbar/menu genérico (não tem href de processo)
                        if sel in seletores_texto:
                            href_lower = href.lower()
                            if not any(p in href_lower for p in ['/processos/processos/', '/processos/processos']):
                                # Link text-based sem href de processo — skip
                                continue

                        combinado = f"{txt} {href}"
                        combinado_norm = re.sub(r'\D', '', combinado)
                        if num_norm and combinado_norm and num_norm not in combinado_norm:
                            if '/processos/processos/' not in href.lower():
                                continue
                        logger.info(f"   ✓ Link encontrado: {txt or href or sel}")
                        el.scroll_into_view_if_needed()
                        el.click()
                        logger.info("   ✓ Clicou no link do processo")
                        logger.info("   Aguardando navegacao...")
                        try:
                            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                        except Exception:
                            pass
                        time.sleep(2.5)

                        # VALIDACAO: confirma que navegou para pagina de processo
                        if self._esta_na_pagina_processo():
                            return True
                        logger.warning(f"   [GUARD] Clique levou para URL errada: {self.page.url}")
                        # Tenta voltar e continuar tentando
                        try:
                            self.page.go_back()
                            self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                            time.sleep(1)
                        except Exception:
                            pass
                    except Exception:
                        continue

            clicou_js = self.page.evaluate(
                """
                (numNorm) => {
                    const limparNum = (txt) => (txt || '').replace(/\\D/g, '');
                    const candidatos = Array.from(document.querySelectorAll('a, [role="link"]'));
                    const alvo = candidatos.find(el => {
                        if (el.offsetHeight === 0) return false;
                        const txt = (el.innerText || el.textContent || '').trim();
                        const href = (el.getAttribute('href') || '').trim();
                        const combinado = `${txt} ${href}`;
                        const combinadoNorm = limparNum(combinado);
                        const matchNumero = !numNorm || (combinadoNorm && combinadoNorm.includes(numNorm));
                        const matchProcesso = href.toLowerCase().includes('/processos/processos/')
                            || txt.toLowerCase().includes('proc')
                            || txt.toLowerCase().includes('processo');
                        return matchNumero && matchProcesso;
                    });
                    if (!alvo) return null;
                    const label = (alvo.innerText || alvo.textContent || alvo.getAttribute('href') || 'Processo').trim();
                    alvo.scrollIntoView({block: 'center'});
                    alvo.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    alvo.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    alvo.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    if (typeof alvo.click === 'function') alvo.click();
                    return label;
                }
                """,
                num_norm,
            )
            if clicou_js:
                logger.info(f"   ✓ Link encontrado (JS): {clicou_js}")
                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception:
                    pass
                time.sleep(2.5)

                # VALIDACAO: confirma que navegou para pagina de processo
                if self._esta_na_pagina_processo():
                    return True
                logger.warning(f"   [GUARD] Clique JS levou para URL errada: {self.page.url}")

            logger.warning("   ⚠ Link do processo não encontrado na tela atual")
            return False
        except Exception as e:
            logger.warning(f"   ⚠ Falha ao abrir processo pela tela atual: {e}")
            return False

    def realizar_acoes_pos_cadastro(self, dados_processo: dict | None = None):
        """Executa ações após o salvamento: abrir processo, entrar em Alterar e preencher pedidos do Forms."""
        try:
            logger.info("\n🔄 Executando ações pós-cadastro...")
            
            # Aguarda o carregamento da página após o salvamento
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                time.sleep(2)
            except Exception:
                pass
                
            numero_processo = self._valor_limpo((dados_processo or {}).get('cnj')) or os.getenv('LEGALONE_TARGET_CNJ', '0010307-23.2026.5.03.0089').strip()
            entrou_em_edicao = False

            # 1. Primeiro tenta abrir o processo pela tela atual recém-salva.
            # Se não achar o link, faz o fallback para a busca por número.
            abriu_processo = self._abrir_processo_pela_tela_atual(numero_processo)
            try:
                url_atual = (self.page.url or '').lower()
                if '/processos/processos/edit/' in url_atual:
                    entrou_em_edicao = True
            except Exception:
                pass
            if not abriu_processo:
                logger.info(f"1ï¸âƒ£  Fallback: indo direto para o processo {numero_processo} pela busca...")
                entrou_em_edicao = self._abrir_edicao_processo_por_busca(numero_processo)

            # 2. Sidebar
            logger.info("2ï¸âƒ£  Fechando Sidebar...")
            try:
                sidebar_toggle = self.page.wait_for_selector('#sidebar-toggle', state='visible', timeout=5000)
                if sidebar_toggle:
                    sidebar_toggle.click()
                    logger.info("   ✓ Sidebar fechada")
                    time.sleep(0.8)
                else:
                    logger.info("   (Sidebar toggle não visível ou já fechado)")
            except Exception:
                logger.info("   (Sidebar toggle não encontrado - prosseguindo)")

            # 3. Tenta clicar em Alterar na tela atual, caso o fallback não tenha aberto em edição
            logger.info("3ï¸âƒ£  Clicando em 'Alterar processo'...")
            _seletores_alterar = [
                'a.command-edit:has-text("Alterar processo")',
                'a.command-link:has-text("Alterar processo")',
                'a.grid-edit-action-row:has-text("Alterar")',
                'a[href*="/processos/Processos/edit/"]:has-text("Alterar")',
                '[class*="command-edit"]:has-text("Alterar")',
                'button:has-text("Alterar processo")',
                'a:has-text("Alterar processo")',
            ]
            for _sel in _seletores_alterar:
                try:
                    btn = self.page.wait_for_selector(_sel, state='visible', timeout=3000)
                    if btn:
                        btn.click()
                        logger.info("   ✓ Clicou em 'Alterar processo'")
                        try:
                            self.page.wait_for_load_state('domcontentloaded', timeout=8000)
                        except Exception:
                            pass
                        time.sleep(1.5)
                        # Validar que realmente entrou em edição
                        url_pos = (self.page.url or '').lower()
                        if '/processos/processos/edit/' in url_pos:
                            entrou_em_edicao = True
                            break
                        else:
                            logger.warning(f"   [GUARD] 'Alterar' levou para URL inesperada: {self.page.url}")
                            continue
                except Exception:
                    continue

            # 3b. Fallback: busca pelo número do processo e entra em Alterar pelo menu da grid
            if not entrou_em_edicao:
                logger.warning("   ⚠ Botão 'Alterar processo' não encontrado na tela atual")
                if numero_processo and self._abrir_edicao_processo_por_busca(numero_processo):
                    entrou_em_edicao = True

            if not entrou_em_edicao:
                logger.error("   âŒ Não foi possível abrir a tela de alteração do processo")
                return False

            time.sleep(2)

            # GUARD: Verificar se realmente estamos na página de edição do processo
            if not self._esta_na_pagina_processo():
                logger.warning(f"   [GUARD] Antes de pedidos, URL incorreta: {self.page.url}")
                if not self._garantir_pagina_processo_edicao(numero_processo):
                    logger.error("   [GUARD] Não foi possível navegar para edição do processo. Abortando pedidos.")
                    return False
                entrou_em_edicao = True
                time.sleep(2)

            # 4. Seção de pedidos + preenchimento completo pelo Forms
            # Rascunho aberto p/ alteração costuma ter obrigatórios vazios (cadastro
            # anterior rejeitado) — completa antes dos pedidos, senão o Salvar e fechar
            # é rejeitado e o processo nunca sai do Pré-cadastro
            try:
                vazios = []
                try:
                    vazios = self._detectar_campos_obrigatorios_vazios()
                except Exception:
                    pass
                # detector não enxerga os combobox da UI nova — rascunho completa SEMPRE
                veio_de_rascunho = bool(getattr(self, '_captura_em_rascunhos', False))
                if dados_processo and (vazios or veio_de_rascunho):
                    logger.warning(
                        f"   [ALTERAR] Completando obrigatórios (vazios detectados: {len(vazios)}; rascunho: {veio_de_rascunho})"
                    )
                    self.preencher_campos_obrigatorios(dados_processo)
            except Exception as e:
                logger.warning(f"   [ALTERAR] Falha ao completar obrigatórios: {e}")

            if not self._abrir_secao_pedidos():
                logger.warning("   ⚠ Não foi possível abrir seção de pedidos")
            else:
                try:
                    html_pedidos = self.page.evaluate(
                        "document.querySelector('#pedidos, .pedidos-section, ul.pedidos-list')?.outerHTML?.substring(0, 1500) || 'SECAO_PEDIDOS_NAO_ENCONTRADA'"
                    )
                    logger.info(f"   [QA] 📸 DOM da Seção de Pedidos após abrir: {html_pedidos}")
                except Exception:
                    pass

            preenchidos, total_itens = self._preencher_pedidos_forms(dados_processo or {})
            # Populate stats ANTES de qualquer retorno
            if isinstance(dados_processo, dict):
                dados_processo.setdefault('_pedidos_stats', {'preenchidos': preenchidos, 'total': total_itens})

            # A origem trouxe pedidos mas nenhum entrou (ex.: parser nao reconheceu o
            # formato)? Nao pode virar email de sucesso - o cadastro esta incompleto.
            dp_ = dados_processo or {}
            origem_pedidos = ' '.join(
                str(v) for v in (
                    self._extrair_texto_detalhes_pedidos(dp_),
                    dp_.get('pedidos'),
                    dp_.get('descricao_pedidos'),
                ) if v
            )
            if preenchidos == 0 and self._valor_limpo(origem_pedidos):
                logger.error("   [PEDIDOS] Origem tem pedidos mas NENHUM foi cadastrado - cadastro incompleto")
                self.last_error_reason = (
                    'Pedidos vieram nos dados mas nenhum foi cadastrado no LegalOne (cadastro incompleto)'
                )
                return False
            if total_itens > 0 and preenchidos == 0:
                logger.error("   âŒ Nenhum pedido foi preenchido com sucesso. Abortando salvamento para não sobrescrever estado prévio.")
                self.last_error_reason = "Nenhum pedido foi cadastrado"
                return False
            if total_itens > 0 and preenchidos < total_itens:
                self.last_error_reason = (
                    f"Cadastro incompleto: {preenchidos}/{total_itens} pedidos foram encontrados"
                )
                logger.error(f"   ❌ {self.last_error_reason}. Abortando salvamento.")
                return False
            elif total_itens == 0:
                logger.info("   ℹ Nenhum pedido para preencher.")

            # 4b. Previsão e resultado ficam no formulário de edição e só
            # são preenchidos depois que todos os pedidos foram incluídos.
            # Se vierem na origem e não forem gravados, não salva parcialmente.
            if not self._preencher_previsao_e_resultado(dados_processo):
                logger.error(
                    '   ❌ Previsão/resultado não foram preenchidos. '
                    'Abortando salvamento para evitar dados incompletos.'
                )
                return False

            # 5. Clicar em "Salvar e fechar" (somente se houver ao menos 1 pedido preenchido, quando havia pedidos)
            if total_itens > 0 and preenchidos == 0:
                logger.error("[PEDIDOS] Abortando Salvar — nenhum pedido preenchido")
                self.last_error_reason = "Nenhum pedido foi cadastrado"
                return False

            logger.info("5ï¸âƒ£  Clicando em 'Salvar e fechar'...")
            salvo = False
            seletores_salvar = [
                'button[name="ButtonSave"][value="0"]',
                'button[type="submit"][name="ButtonSave"]',
                '#btnSave',
                'button:has-text("Salvar e fechar")',
                'button:has-text("Salvar")',
                'input[type="submit"][value*="Salvar"]',
            ]
            for sel_salvar in seletores_salvar:
                try:
                    btn_salvar = self.page.wait_for_selector(sel_salvar, state='visible', timeout=5000)
                    if btn_salvar:
                        btn_salvar.scroll_into_view_if_needed()
                        btn_salvar.click()
                        logger.info("   ✓ 'Salvar e fechar' clicado")
                        salvo = True
                        break
                except Exception:
                    continue

            if not salvo:
                logger.warning("   ⚠ Botão 'Salvar e fechar' não encontrado — tentando via JS...")
                try:
                    salvo = bool(self.page.evaluate("""
                        () => {
                            const btn = document.querySelector('button[name="ButtonSave"]')
                                || Array.from(document.querySelectorAll('button[type="submit"]'))
                                    .find(b => b.textContent.includes('Salvar'));
                            if (btn) { btn.click(); return true; }
                            return false;
                        }
                    """))
                    if salvo:
                        logger.info("   ✓ 'Salvar e fechar' clicado via JS")
                except Exception as e:
                    logger.error(f"   âŒ Falha ao salvar: {e}")

            if not salvo:
                self.last_error_reason = "Pedidos não foram salvos: botão Salvar e fechar indisponível"
                return False

            if salvo:
                time.sleep(3)
                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=15000)
                except Exception:
                    pass
                if not self._confirmar_salvamento(timeout_s=20):
                    return False

            # 6. Resolver monitoramento pendente (best-effort, nunca propaga erro)
            try:
                self._resolver_monitoramento_pendente(dados_processo or {})
            except Exception as e_mon:
                logger.warning(f"   ⚠ Monitoramento: {e_mon}")

            logger.info("\n✅ Ações pós-cadastro concluídas com sucesso!")
            return True

        except Exception as e:
            logger.error(f"âŒ Erro nas ações pós-cadastro: {e}")
            return False

    # ------------------------------------------------------------------
    # Monitoramento pendente (Datajud + JusBrasil + Claude Brain)
    # ------------------------------------------------------------------
    def _resolver_monitoramento_pendente(self, dados: dict) -> None:
        """Tenta resolver o card de 'Necessita ação' do monitoramento.

        Nunca propaga exceção. Registra resultado em dados['_monitoramento'].
        """
        SEL_PESQUISA_INPUT = 'input#search-box-input, input[name="Search"]'
        SEL_PESQUISA_BTN = '#search-box-input-submit, input[value="Pesquisar"]'
        SEL_BADGE = 'a.warning.webgrid-cell-link-button[title="Necessita ação"]'
        SEL_USAR = 'a:has-text("Usar este processo")'

        cnj = (dados or {}).get('cnj') or ''
        if not cnj:
            return

        try:
            logger.info("🔎 [MON] Verificando monitoramento pendente...")
            # 1. Pesquisar CNJ
            try:
                inp = self.page.locator(SEL_PESQUISA_INPUT).first
                if inp.count() > 0:
                    inp.click()
                    inp.fill('')
                    inp.type(cnj, delay=20)
                    time.sleep(0.3)
                    try:
                        self.page.locator(SEL_PESQUISA_BTN).first.click(timeout=3000)
                    except Exception:
                        self.page.keyboard.press('Enter')
                    time.sleep(2.0)
            except Exception as e:
                logger.info(f"   [MON] busca não disponível: {e}")

            # 2. Verificar badge
            try:
                badge = self.page.locator(SEL_BADGE).first
                if badge.count() == 0:
                    dados['_monitoramento'] = {'status': 'OK', 'fonte': 'N/A'}
                    logger.info("   [MON] Sem badge 'Necessita ação' — monitoramento OK")
                    return
            except Exception:
                dados['_monitoramento'] = {'status': 'OK', 'fonte': 'N/A'}
                return

            # 3. Abrir tela de cards
            try:
                badge.click()
                time.sleep(1.5)
                try:
                    self.page.wait_for_selector(SEL_USAR, timeout=8000)
                except Exception:
                    pass
            except Exception as e:
                logger.info(f"   [MON] falha clicar badge: {e}")
                dados['_monitoramento'] = {'status': 'PENDENTE', 'erro': str(e)}
                return

            # 4. Extrair cards
            cards_text: list[str] = []
            try:
                usars = self.page.locator(SEL_USAR)
                n_cards = usars.count()
                for i in range(n_cards):
                    try:
                        card = usars.nth(i).locator(
                            'xpath=ancestor::*[self::div or self::li or self::article][1]'
                        ).first
                        txt = (card.inner_text(timeout=1500) or '').strip()
                        if txt:
                            cards_text.append(txt[:2000])
                    except Exception:
                        continue
            except Exception:
                pass

            # 5. Datajud
            datajud_hits: list = []
            try:
                from datajud_client import DatajudClient
                datajud_hits = DatajudClient().consultar(cnj)
            except Exception as e:
                logger.info(f"   [MON] Datajud: {e}")

            # 6. JusBrasil
            jusbrasil_info = None
            try:
                from jusbrasil_scraper import JusBrasilScraper
                jusbrasil_info = JusBrasilScraper().consultar_fase(cnj, self.page)
            except Exception as e:
                logger.info(f"   [MON] JusBrasil: {e}")

            # 7. Claude Brain
            sugestao = {'indice_escolhido': -1, 'confianca': 0.0, 'justificativa': 'brain_indisponivel'}
            try:
                from claude_brain import get_brain
                brain = get_brain()
                sugestao = brain.escolher_monitoramento(
                    cnj, cards_text, datajud_hits, jusbrasil_info, dados or {}
                )
            except Exception as e:
                logger.info(f"   [MON] Brain indisponível: {e}")

            idx = int(sugestao.get('indice_escolhido', -1))
            conf = float(sugestao.get('confianca', 0.0))

            if idx >= 0 and conf >= 0.70:
                try:
                    self.page.locator(SEL_USAR).nth(idx).click(timeout=5000)
                    time.sleep(1.5)
                    dados['_monitoramento'] = {
                        'status': 'RESOLVIDO',
                        'indice': idx,
                        'confianca': conf,
                        'justificativa': sugestao.get('justificativa', ''),
                        'cards_total': len(cards_text),
                    }
                    logger.info(f"   [MON] ✅ Card {idx} selecionado (confiança={conf:.2f})")
                    return
                except Exception as e:
                    logger.warning(f"   [MON] Falha ao clicar 'Usar este processo' #{idx}: {e}")

            # 8. Fallback A: não clicar, registrar pendência
            dados['_monitoramento'] = {
                'status': 'PENDENTE',
                'cards': cards_text,
                'sugestao': sugestao,
                'datajud': datajud_hits,
                'jusbrasil': jusbrasil_info,
            }
            logger.warning("   [MON] ⚠ Monitoramento PENDENTE (confiança insuficiente) — ação manual necessária")
        except Exception as e:
            logger.warning(f"   [MON] erro inesperado: {e}")
            try:
                dados['_monitoramento'] = {'status': 'PENDENTE', 'erro': str(e)}
            except Exception:
                pass


def teste_manual():
    cadastrador = LegalOneCadastro()
    cnj_teste = os.getenv('LEGALONE_TEST_CNJ', '0010307-23.2026.5.03.0089').strip()
    dados = {
        'cnj': cnj_teste,
        'cliente': os.getenv('LEGALONE_TEST_CLIENTE', 'Teste Manual Cliente'),
        'contrario': os.getenv('LEGALONE_TEST_CONTRARIO', 'Teste Manual Contrario'),
    }
    cadastrador.cadastrar_processo(dados)

if __name__ == "__main__":
    teste_manual()
