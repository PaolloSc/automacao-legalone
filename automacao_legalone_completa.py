"""
Automação Completa: Outlook + Microsoft Forms + LegalOne
Monitora emails do Forms e cadastra automaticamente no LegalOne
"""

import asyncio
import logging
import sys
import threading
import concurrent.futures
import os
import smtplib
import traceback
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import requests

# Forçar encoding UTF-8 no stdout/stderr em Windows (evita UnicodeEncodeError em prints)
import sys as _sys
if _sys.platform == "win32":
    try:
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Carrega variáveis do .env antes de qualquer import que use os.getenv
load_dotenv()
try:
    from outlook_monitor import OutlookMonitor as OutlookMonitorDesktop
    OUTLOOK_DESKTOP_DISPONIVEL = True
except ImportError:
    OutlookMonitorDesktop = None
    OUTLOOK_DESKTOP_DISPONIVEL = False

try:
    from outlook_monitor_graph import OutlookMonitorGraph
    OUTLOOK_GRAPH_DISPONIVEL = True
except ImportError:
    OutlookMonitorGraph = None
    OUTLOOK_GRAPH_DISPONIVEL = False
from forms_extractor import FormsExtractor
from utils.log_formatter import setup_logging
from config_automacao import LOGGING_CONFIG

try:
    from forms_extractor_enhanced import EnhancedFormsExtractor
    ENHANCED_DISPONIVEL = True
except Exception:
    ENHANCED_DISPONIVEL = False

from legalone_cadastro import LegalOneCadastro

try:
    from claude_brain import ClaudeBrain
    CLAUDE_BRAIN_DISPONIVEL = True
except Exception as _brain_err:
    CLAUDE_BRAIN_DISPONIVEL = False

# Configurar logging com novo sistema
logger, formatter = setup_logging(
    verbosity=LOGGING_CONFIG.get('nivel', 'NORMAL'),
    log_file=LOGGING_CONFIG.get('arquivo_geral', 'automacao_legalone.log'),
    show_empty_fields=LOGGING_CONFIG.get('mostrar_campos_vazios', False)
)


def escolher_cadastro() -> str:
    """Decide o backend de cadastro: 'api' se a flag estiver ligada, senao 'browser'."""
    from config_automacao import LEGALONE_API_CONFIG
    return "api" if LEGALONE_API_CONFIG.get("use_api") else "browser"


def _id_opcional(valor):
    if valor in (None, ""):
        return None
    return int(valor)


class AutomacaoLegalOne:
    """Orquestra todo o fluxo de automação"""

    DESTINATARIO_ERRO_PADRAO = 'seu_email@exemplo.com'

    def __init__(self, config=None):
        self.config = {
            'outlook': {
                'assunto_filtro': 'Cadastro de processos NOVOS LegalOne trabalhista',
                'remetente_filtro': 'microsoft.com',
                'intervalo_checagem': 300,
                'fonte_email': os.getenv('EMAIL_SOURCE', 'auto'),
            },
            'legalone': {
                'username': os.getenv('LEGALONE_USERNAME', 'seu_email@exemplo.com'),
                'password': os.getenv('LEGALONE_PASSWORD', ''),
            },
            'modo_automatico': True,
        }

        # Merge config personalizado (suporta dicionarios aninhados)
        if config:
            for key, value in config.items():
                if isinstance(value, dict) and key in self.config:
                    self.config[key].update(value)
                else:
                    self.config[key] = value

        # Armazena o formatter para uso posterior
        global formatter
        self.formatter = formatter

        self.skip_email = self.config.get('skip_email', False)
        self.monitor_outlook = None

        if not self.skip_email:
            self.email_mode = self._resolver_modo_email(self.config.get('outlook'))
            if self.email_mode == 'graph':
                if not OUTLOOK_GRAPH_DISPONIVEL:
                    raise RuntimeError("Modo Graph API selecionado, mas outlook_monitor_graph não está disponível.")
                faltando = self._validar_graph_envs()
                if faltando:
                    raise RuntimeError(
                        "Modo Graph API selecionado, mas faltam variáveis de ambiente: "
                        + ', '.join(faltando)
                    )
            else:
                if not OUTLOOK_DESKTOP_DISPONIVEL:
                    raise RuntimeError("Modo Desktop selecionado, mas pywin32 não está instalado. Instale com: pip install pywin32")

            monitor_class = OutlookMonitorGraph if self.email_mode == 'graph' else OutlookMonitorDesktop
            self.monitor_outlook = monitor_class(
                assunto_filtro=self.config['outlook']['assunto_filtro'],
                remetente_filtro=self.config['outlook']['remetente_filtro'],
                intervalo_checagem=self.config['outlook']['intervalo_checagem']
            )
        else:
            self.email_mode = None

        self.forms_extractor = FormsExtractor()

        self.forms_extractor_enhanced = EnhancedFormsExtractor() if ENHANCED_DISPONIVEL else None

        agentql_api_key = os.getenv("AGENTQL_API_KEY", "")
        env_flag = os.getenv("LEGALONE_USE_AGENTQL")
        if env_flag is None:
            use_agentql = bool(agentql_api_key)
        else:
            use_agentql = env_flag.strip().lower() in ("1", "true", "yes", "y")

        self.legalone = LegalOneCadastro(
            username=self.config['legalone']['username'],
            password=self.config['legalone']['password'],
            use_agentql=use_agentql,
            agentql_api_key=agentql_api_key,
        )

        self.stats = {
            'emails_recebidos': 0,
            'processos_cadastrados': 0,
            'erros': 0,
            'inicio': datetime.now()
        }

        # --- Event loop persistente em thread dedicada ---
        # O Playwright async precisa que o event loop permaneça vivo entre
        # chamadas para que os objetos (browser, context, page) não fiquem
        # vinculados a um loop morto.
        self._async_loop = asyncio.new_event_loop()
        self._async_thread = threading.Thread(
            target=self._async_loop.run_forever,
            daemon=True,
            name="forms-async-loop",
        )
        self._async_thread.start()

        # --- Claude Brain (cérebro IA) ---
        self.brain = None
        if CLAUDE_BRAIN_DISPONIVEL:
            try:
                self.brain = ClaudeBrain()
                logger.info(f"{formatter.SYMBOLS['star']} Claude Brain ativo — IA como cérebro da automação")
            except Exception as e:
                logger.warning(f"[BRAIN] Claude Brain indisponível: {e}")
        
        logger.info(f"{formatter.SYMBOLS['star']} Automação LegalOne Inicializada")
        logger.info(f"{formatter.SYMBOLS['arrow']} Nível de log: {LOGGING_CONFIG.get('nivel', 'NORMAL')}")
        logger.info(f"{formatter.SYMBOLS['arrow']} Fonte de emails: {'Graph API' if self.email_mode == 'graph' else 'Outlook Desktop (COM)'}")

    @staticmethod
    def _resolver_modo_email(config_outlook):
        """Define se o monitor de emails será desktop (COM) ou Graph API."""
        modo = str((config_outlook or {}).get('fonte_email') or os.getenv('EMAIL_SOURCE') or 'auto').strip().lower()

        if modo in {'graph', 'api', 'cloud'}:
            return 'graph'
        if modo in {'desktop', 'outlook', 'com'}:
            return 'desktop'

        graph_envs = [
            os.getenv('AZURE_TENANT_ID'),
            os.getenv('AZURE_CLIENT_ID'),
            os.getenv('AZURE_CLIENT_SECRET'),
            os.getenv('GRAPH_USER_EMAIL'),
        ]
        return 'graph' if all(graph_envs) else 'desktop'

    @staticmethod
    def _validar_graph_envs():
        faltando = [
            nome for nome in (
                'AZURE_TENANT_ID',
                'AZURE_CLIENT_ID',
                'AZURE_CLIENT_SECRET',
                'GRAPH_USER_EMAIL',
            ) if not os.getenv(nome)
        ]
        return faltando

    @staticmethod
    def _normalizar_chave_campo(valor):
        if valor is None:
            return ''
        texto = unicodedata.normalize('NFKD', str(valor))
        texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
        texto = texto.lower().strip()
        texto = ''.join(ch if ch.isalnum() else ' ' for ch in texto)
        return ' '.join(texto.split())

    @classmethod
    def _valor_outro_dado_valido(cls, valor):
        valor_norm = cls._normalizar_chave_campo(valor)
        if not valor_norm:
            return False
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
        return not any(marcador in valor_norm for marcador in marcadores_invalidos)

    @classmethod
    def _obter_outro_dado(cls, dados_processo, *aliases, permitir_parcial=True):
        outros = (dados_processo or {}).get('outros_dados') or {}
        if not isinstance(outros, dict) or not outros:
            return None

        aliases_norm = [
            cls._normalizar_chave_campo(alias)
            for alias in aliases
            if cls._normalizar_chave_campo(alias)
        ]
        if not aliases_norm:
            return None

        for chave, valor in outros.items():
            if not cls._valor_outro_dado_valido(valor):
                continue
            chave_norm = cls._normalizar_chave_campo(chave)
            if chave_norm in aliases_norm:
                return valor

        if not permitir_parcial:
            return None

        for chave, valor in outros.items():
            if not cls._valor_outro_dado_valido(valor):
                continue
            chave_norm = cls._normalizar_chave_campo(chave)
            if any(
                chave_norm.startswith(alias_norm)
                or alias_norm in chave_norm
                for alias_norm in aliases_norm
            ):
                return valor

        return None

    def _merge_enhanced_data(self, dados_base, dados_enhanced):
        """Mescla dados do extrator enhanced sem sobrescrever valores já existentes"""
        if not isinstance(dados_enhanced, dict):
            return dados_base

        # Campos diretos
        campos = [
            'cnj', 'tipo_cadastro', 'fase', 'instancia', 'cliente',
            'contrario', 'advogado', 'comarca', 'valor_causa',
            'procedimento', 'data_distribuicao', 'risco', 'probabilidade'
        ]

        for campo in campos:
            if not dados_base.get(campo) and dados_enhanced.get(campo):
                dados_base[campo] = dados_enhanced.get(campo)

        # Outros dados
        outros = dados_base.get('outros_dados') or {}
        enhanced_outros = dados_enhanced.get('outros_dados') or {}
        if isinstance(enhanced_outros, dict):
            for k, v in enhanced_outros.items():
                if k not in outros and v:
                    outros[k] = v

        dados_base['outros_dados'] = outros
        return dados_base

    def _destinatarios_erro(self) -> list[str]:
        bruto = (
            os.getenv('LEGALONE_ERROR_EMAIL_TO')
            or os.getenv('ERROR_NOTIFICATION_EMAILS')
            or self.DESTINATARIO_ERRO_PADRAO
        )
        destinos = []
        for item in str(bruto).replace(';', ',').split(','):
            email = item.strip()
            if email:
                destinos.append(email)
        return destinos or [self.DESTINATARIO_ERRO_PADRAO]

    def _montar_notificacao_erro(self, email_data: dict | None, dados_processo: dict | None) -> dict:
        email_data = email_data or {}
        dados_processo = dados_processo or {}

        cnj = dados_processo.get('cnj', 'N/A')
        motivo = (
            dados_processo.get('motivo_falha_legalone')
            or dados_processo.get('erro')
            or dados_processo.get('motivo')
            or 'N/A'
        )
        assunto_original = email_data.get('subject', 'N/A')
        remetente_original = email_data.get('sender', 'N/A')
        link = email_data.get('forms_link', 'N/A')
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        contexto = dados_processo.get('contexto', 'processamento')
        detalhe_extra = dados_processo.get('traceback') or dados_processo.get('detalhes') or ''
        destinatarios = self._destinatarios_erro()

        corpo_texto = (
            "Falha no cadastro automático - LegalOne\n\n"
            f"Data/Hora: {timestamp}\n"
            f"Contexto: {contexto}\n"
            f"CNJ: {cnj}\n"
            f"Motivo: {motivo}\n"
            f"Email origem: {assunto_original}\n"
            f"Remetente origem: {remetente_original}\n"
            f"Link Forms: {link}\n"
        )
        if detalhe_extra:
            corpo_texto += f"\nDetalhes:\n{detalhe_extra}\n"

        corpo_html = f"""
<html><body>
<h2 style="color:#cc0000;">Falha no cadastro automático - LegalOne</h2>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;">
  <tr><th align="left">Data/Hora</th><td>{timestamp}</td></tr>
  <tr><th align="left">Contexto</th><td>{contexto}</td></tr>
  <tr><th align="left">CNJ</th><td>{cnj}</td></tr>
  <tr><th align="left">Motivo</th><td>{motivo}</td></tr>
  <tr><th align="left">Email origem</th><td>{assunto_original}</td></tr>
  <tr><th align="left">Remetente origem</th><td>{remetente_original}</td></tr>
  <tr><th align="left">Link Forms</th><td><a href="{link}">{link}</a></td></tr>
</table>
"""
        if detalhe_extra:
            corpo_html += (
                "<p><strong>Detalhes:</strong></p>"
                f"<pre style=\"white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;\">{detalhe_extra}</pre>"
            )
        corpo_html += """
<p style="font-size:12px;color:#666;">Este email foi gerado automaticamente pela automação LegalOne.</p>
</body></html>
"""

        return {
            'cnj': cnj,
            'subject': f"[ERRO CADASTRO] CNJ {cnj} - falha na automação LegalOne",
            'text': corpo_texto,
            'html': corpo_html,
            'to': destinatarios,
        }

    def processar_email(self, email_data):
        """Processa email recebido"""
        try:
            self.stats['emails_recebidos'] += 1

            logger.info("\n" + "="*80)
            logger.info("[EMAIL] NOVO EMAIL!")
            logger.info("="*80)
            eh_copilot = bool(email_data.get('dados_diretos'))
            logger.info(f"Assunto: {email_data['subject']}")
            logger.info(f"De: {email_data['sender']}")
            logger.info(f"Origem: {'Power Automate / Copilot' if eh_copilot else 'Microsoft Forms'}")
            if not eh_copilot:
                logger.info(f"Link: {email_data['forms_link']}")
            logger.info("="*80)

            # Runner seguro: envia a corrotina ao event loop persistente para
            # que os objetos Playwright sobrevivam entre chamadas.
            def _run_coro_blocking(coro):
                future = asyncio.run_coroutine_threadsafe(coro, self._async_loop)
                return future.result()  # bloqueia até terminar

            if eh_copilot:
                # Dados já extraídos pelo Copilot — pula o Forms completamente
                logger.info("\n[COPILOT] Usando dados extraídos pelo Copilot Studio...")
                dados_processo = email_data['dados_diretos']
                # Garante estrutura mínima esperada pelo restante do pipeline
                if 'outros_dados' not in dados_processo:
                    dados_processo['outros_dados'] = {}
                # Campos extras do Copilot (além dos 10 base) vão pra outros_dados
                # pra que forms_mapping.py e LegalOneCadastro consigam processar
                _campos_base = {
                    'cnj', 'cliente', 'contrario', 'natureza', 'tribunal',
                    'comarca', 'instancia', 'posicao', 'fase', 'tipo_cadastro',
                    'outros_dados',
                }
                for chave, valor in list(dados_processo.items()):
                    if chave not in _campos_base and valor:
                        dados_processo['outros_dados'][chave] = valor
            else:
                # Fluxo original: raspa o Forms via Playwright
                logger.info("\n🔍 Extraindo dados do Forms...")
                dados_processo = _run_coro_blocking(
                    self.forms_extractor.extrair_dados_forms(email_data['forms_link'])
                )

                # Fallback: usa extrator enhanced se faltar CNJ ou dados principais
                if self.forms_extractor_enhanced and (
                    not dados_processo.get('cnj') or not dados_processo.get('outros_dados')
                ):
                    logger.info("[FALLBACK] Usando FormsExtractor Enhanced...")
                    dados_enhanced = _run_coro_blocking(
                        self.forms_extractor_enhanced.extract_with_playwright_soup(email_data['forms_link'])
                    )
                    dados_processo = self._merge_enhanced_data(dados_processo, dados_enhanced)

            # ----- START missing field mapping -----
            # Ensure required fields are present at top level for LegalOneCadastro
            if not dados_processo.get('cliente'):
                dados_processo['cliente'] = self._obter_outro_dado(
                    dados_processo,
                    'Cliente principal',
                    'Cliente',
                )
            if not dados_processo.get('contrario'):
                dados_processo['contrario'] = self._obter_outro_dado(
                    dados_processo,
                    'Contrário principal',
                    'Contrario principal',
                    'Parte contrária',
                    'Parte contraria',
                    'Contrário',
                    'Contrario',
                )
            if not dados_processo.get('posicao'):
                dados_processo['posicao'] = self._obter_outro_dado(
                    dados_processo,
                    'Posição',
                    'Posicao',
                    'Posição nos autos',
                    'Posicao nos autos',
                    permitir_parcial=False,
                )
            if not dados_processo.get('negociacao_contrato'):
                dados_processo['negociacao_contrato'] = self._obter_outro_dado(
                    dados_processo,
                    'Negociação de contrato de honorários',
                    'Negociacao de contrato de honorarios',
                    'Negociação honorários',
                    'Negociacao honorarios',
                )
            if not dados_processo.get('data_baixa'):
                dados_processo['data_baixa'] = self._obter_outro_dado(
                    dados_processo,
                    'Data da baixa',
                    'Data de baixa',
                    'Baixa',
                )
            if not dados_processo.get('centro_custo'):
                dados_processo['centro_custo'] = self._obter_outro_dado(
                    dados_processo,
                    'Centro de custo',
                )
            if not dados_processo.get('datacloud_configurado'):
                dados_processo['datacloud_configurado'] = self._obter_outro_dado(
                    dados_processo,
                    'Datacloud configurado',
                )
            if not dados_processo.get('natureza'):
                dados_processo['natureza'] = self._obter_outro_dado(
                    dados_processo,
                    'Natureza do processo',
                    'Natureza',
                    'Natureza da ação',
                    'Natureza da acao',
                    'Natureza juridica',
                    'Natureza jurídica',
                    'Tipo da ação',
                    'Tipo da acao',
                )
            if not dados_processo.get('status_processo'):
                dados_processo['status_processo'] = self._obter_outro_dado(
                    dados_processo,
                    'Status do processo',
                    'Status',
                    'Situação do processo',
                    'Situação',
                    'Situacao do processo',
                    'Situacao',
                )
            # Documento do cliente/empresa (ajuda o fluxo de "Adicionar contato" no popup)
            documento_cliente = (
                self._obter_outro_dado(
                    dados_processo,
                    'CPF do cliente',
                    'CPF do Cliente',
                    'CNPJ do cliente',
                    'CNPJ Cliente',
                    'CNPJ da empresa',
                    'CNPJ da Empresa',
                    'CPF/CNPJ do cliente',
                    'CPF/CNPJ Cliente',
                )
            )
            documento_contrario = (
                self._obter_outro_dado(
                    dados_processo,
                    'CPF do contrário',
                    'CPF do contrario',
                    'CPF do Contrário',
                    'CNPJ do contrário',
                    'CNPJ do contrario',
                    'CNPJ Contrário',
                    'CNPJ Contrario',
                    'CPF/CNPJ do contrário',
                    'CPF/CNPJ do contrario',
                )
            )

            if 'documento_cliente' not in dados_processo:
                dados_processo['documento_cliente'] = documento_cliente
            if 'documento_contrario' not in dados_processo:
                dados_processo['documento_contrario'] = documento_contrario

            if 'cpf_cliente' not in dados_processo and documento_cliente:
                digitos = ''.join(ch for ch in str(documento_cliente) if ch.isdigit())
                if len(digitos) == 11:
                    dados_processo['cpf_cliente'] = documento_cliente
            if 'cnpj_cliente' not in dados_processo:
                digitos = ''.join(ch for ch in str(documento_cliente or '') if ch.isdigit())
                dados_processo['cnpj_cliente'] = documento_cliente if len(digitos) == 14 else None

            if 'cpf_contrario' not in dados_processo and documento_contrario:
                digitos = ''.join(ch for ch in str(documento_contrario) if ch.isdigit())
                if len(digitos) == 11:
                    dados_processo['cpf_contrario'] = documento_contrario
            if 'cnpj_contrario' not in dados_processo:
                digitos = ''.join(ch for ch in str(documento_contrario or '') if ch.isdigit())
                dados_processo['cnpj_contrario'] = documento_contrario if len(digitos) == 14 else None
            # ----- END missing field mapping -----

            if not dados_processo.get('cnj'):
                logger.error("[ERRO] CNJ não encontrado!")
                if email_data.get('forms_link'):
                    logger.error(f"   Verifique: {email_data['forms_link']}")
                self.stats['erros'] += 1
                self.salvar_log_erro(
                    email_data,
                    {
                        **(dados_processo or {}),
                        'erro': 'CNJ não encontrado na extração',
                        'contexto': 'extracao_copilot' if eh_copilot else 'extracao_forms',
                    },
                )
                return

            # Mostra resumo simples
            logger.info(f"✅ Processo extraído: CNJ {dados_processo.get('cnj', 'N/A')}")

            # --- INTELIGÊNCIA DE CLASSIFICAÇÃO (Claude Brain) ---
            tipo_tarefa = "GENERICO"
            classificacao_ia = None

            if self.brain:
                try:
                    logger.info("\n🧠 Claude Brain analisando processo...")
                    classificacao_ia = self.brain.classificar_processo(dados_processo)
                    tipo_tarefa = classificacao_ia.get('tipo_tarefa', 'GENERICO')
                    prioridade = classificacao_ia.get('prioridade', 'MEDIA')
                    confianca = classificacao_ia.get('confianca', 0)

                    logger.info(f"[BRAIN] Tipo: {tipo_tarefa} | Prioridade: {prioridade} | Confiança: {confianca:.0%}")
                    logger.info(f"[BRAIN] {classificacao_ia.get('classificacao', '')}")

                    faltando = classificacao_ia.get('campos_obrigatorios_faltando', [])
                    if faltando:
                        logger.warning(f"[BRAIN] Campos faltando: {', '.join(faltando)}")

                    for rec in classificacao_ia.get('recomendacoes', []):
                        logger.info(f"[BRAIN] 💡 {rec}")

                except Exception as e:
                    logger.warning(f"[BRAIN] Erro na classificação IA: {e} — usando fallback regras")

            # Fallback: classificação por regras simples
            if tipo_tarefa == "GENERICO" and not classificacao_ia:
                tipo_cadastro = str(dados_processo.get('tipo_cadastro', '')).upper()
                fase = str(dados_processo.get('fase', '')).upper()

                if 'CADASTRO INICIAL' in tipo_cadastro:
                    tipo_tarefa = "CADASTRO_INICIAL"
                    logger.info("\n[REGRAS] 🟢 Identificado: CADASTRO INICIAL")
                elif 'RECURSO' in tipo_cadastro or 'RECURSAL' in fase:
                    tipo_tarefa = "RECURSO"
                    logger.info("\n[REGRAS] 🟡 Identificado: RECURSO")
                elif 'DECISÃO' in tipo_cadastro or 'DECISÓRIA' in fase:
                    tipo_tarefa = "DECISAO"
                    logger.info("\n[REGRAS] 🔵 Identificado: DECISÃO")
                elif 'ARQUIVAMENTO' in tipo_cadastro or 'ARQUIVADO' in fase:
                    tipo_tarefa = "ARQUIVAMENTO"
                    logger.info("\n[REGRAS] ⚫ Identificado: ARQUIVAMENTO")
                else:
                    logger.info(f"\n[REGRAS] ⚪ Não classificado. (Tipo: {tipo_cadastro}, Fase: {fase})")

            # Adiciona classificação aos dados para uso no LegalOne
            dados_processo['tipo_tarefa_identificada'] = tipo_tarefa
            if classificacao_ia:
                dados_processo['classificacao_ia'] = classificacao_ia
            # -------------------------------------

            # Modo manual: pede confirmação
            if not self.config['modo_automatico']:
                logger.info("\n[AVISO]  MODO MANUAL")
                resposta = input("Cadastrar no LegalOne? (s/n): ").strip().lower()
                if resposta != 's':
                    logger.info("[ERRO] Cancelado pelo usuário")
                    return

            # Cadastra
            logger.info("\n[INICIO] Cadastrando no LegalOne...")
            
            # ATENÇÃO: Método agora é síncrono para manter navegador aberto!
            # Antes: sucesso = asyncio.run(self.legalone.cadastrar_processo(dados_processo))
            sucesso = False
            if escolher_cadastro() == "api":
                from config_automacao import LEGALONE_API_CONFIG as _api_cfg
                from legalone_api_cadastro import LegalOneApiCadastro

                cad_api = LegalOneApiCadastro(
                    default_status_id=_id_opcional(_api_cfg.get("default_status_id")),
                    default_area_id=_id_opcional(_api_cfg.get("default_area_id")),
                )
                resultado_api = cad_api.cadastrar_processo(dados_processo)
                if resultado_api["sucesso"]:
                    logger.info("[API] Cadastro OK id=%s", resultado_api["id"])
                    dados_processo["legalone_api_id"] = resultado_api["id"]
                    sucesso = True
                else:
                    logger.error(
                        "[API] Cadastro falhou: %s - fazendo fallback para navegador.",
                        resultado_api["erro"],
                    )

            if not sucesso:
                sucesso = self.legalone.cadastrar_processo(dados_processo)

            if sucesso:
                self.stats['processos_cadastrados'] += 1
                logger.info("\n[OK] PROCESSO CADASTRADO!")
                self.salvar_log_sucesso(email_data, dados_processo)
                try:
                    self._enviar_email_sucesso(email_data, dados_processo)
                except Exception as _e_ok:
                    logger.warning(f"[EMAIL-OK] Falha ao enviar email de sucesso: {_e_ok}")
            else:
                self.stats['erros'] += 1
                logger.error("\n[ERRO] FALHA NO CADASTRO!")
                dados_erro = dict(dados_processo)
                motivo_legalone = getattr(self.legalone, 'last_error_reason', None)
                if motivo_legalone:
                    logger.error(f"[LEGALONE] Motivo provável da falha: {motivo_legalone}")
                    dados_erro['motivo_falha_legalone'] = motivo_legalone
                self.salvar_log_erro(email_data, dados_erro)

        except Exception as e:
            self.stats['erros'] += 1
            logger.error(f"\n[ERRO] ERRO: {e}")
            logger.exception(e)
            self.salvar_log_erro(
                email_data,
                {
                    'erro': str(e),
                    'contexto': 'processar_email',
                    'traceback': traceback.format_exc(),
                },
            )

    def salvar_log_sucesso(self, email_data, dados_processo):
        """Salva log de sucesso"""
        try:
            with open('processos_cadastrados.log', 'a', encoding='utf-8') as f:
                f.write("\n" + "="*80 + "\n")
                f.write(f"Data: {datetime.now().isoformat()}\n")
                f.write(f"Email: {email_data['subject']}\n")
                f.write(f"CNJ: {dados_processo.get('cnj', 'N/A')}\n")
                f.write(f"Autor: {dados_processo.get('autor', 'N/A')}\n")
                f.write(f"Réu: {dados_processo.get('reu', 'N/A')}\n")
                f.write("Status: SUCESSO\n")
                f.write("="*80 + "\n")
        except Exception as e:
            logger.error(f"Erro ao salvar log: {e}")

    def salvar_log_erro(self, email_data, dados_processo):
        """Salva log de erro e envia email de notificação"""
        email_data = email_data or {}
        dados_processo = dados_processo or {}
        try:
            with open('processos_erro.log', 'a', encoding='utf-8') as f:
                f.write("\n" + "="*80 + "\n")
                f.write(f"Data: {datetime.now().isoformat()}\n")
                f.write(f"Email: {email_data.get('subject', 'N/A')}\n")
                f.write(f"Fonte: {'Copilot' if email_data.get('dados_diretos') else 'Forms'}\n")
                f.write(f"Link: {email_data.get('forms_link', 'N/A')}\n")
                f.write(f"Dados: {dados_processo}\n")
                f.write("Status: ERRO\n")
                f.write("="*80 + "\n")
        except Exception as e:
            logger.error(f"Erro ao salvar log: {e}")

        self._enviar_email_erro(email_data, dados_processo)

    # ------------------------------------------------------------------
    # Notificação de erros por email (Microsoft Graph API)
    # ------------------------------------------------------------------
    _graph_token: str | None = None
    _graph_token_expires: datetime = datetime.min.replace(tzinfo=timezone.utc)

    def _graph_obter_token(self) -> str | None:
        """Obtém token client_credentials para envio de email via Graph."""
        tenant = os.getenv('AZURE_TENANT_ID')
        client_id = os.getenv('AZURE_CLIENT_ID')
        client_secret = os.getenv('AZURE_CLIENT_SECRET')
        if not all([tenant, client_id, client_secret]):
            return None
        agora = datetime.now(timezone.utc)
        if self._graph_token and agora < self._graph_token_expires:
            return self._graph_token
        try:
            url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            resp = requests.post(url, data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            }, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            AutomacaoLegalOne._graph_token = body["access_token"]
            AutomacaoLegalOne._graph_token_expires = agora + timedelta(
                seconds=body.get("expires_in", 3500) - 60
            )
            return AutomacaoLegalOne._graph_token
        except Exception as e:
            logger.error(f"[EMAIL-ERRO] Falha ao obter token Graph: {e}")
            return None

    def _enviar_email_erro_graph(self, notificacao: dict) -> tuple[bool, str]:
        token = self._graph_obter_token()
        remetente = os.getenv('GRAPH_USER_EMAIL')
        if not token or not remetente:
            return False, "Credenciais Graph ausentes"

        payload = {
            "message": {
                "subject": notificacao['subject'],
                "body": {"contentType": "HTML", "content": notificacao['html']},
                "toRecipients": [
                    {"emailAddress": {"address": destino}}
                    for destino in notificacao['to']
                ],
            },
            "saveToSentItems": False,
        }

        try:
            url = f"https://graph.microsoft.com/v1.0/users/{remetente}/sendMail"
            logger.debug(f"[GRAPH] POST {url} | destinatarios: {notificacao['to']} | assunto: {notificacao['subject']}")
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            logger.debug(f"[GRAPH] Response: status={resp.status_code} headers={dict(resp.headers)} body={resp.text[:500]}")
            if resp.status_code == 202:
                return True, f"Enviado via Graph (de={remetente})"
            return False, f"Graph retornou {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            return False, f"Falha no Graph: {e}"

    def _enviar_email_erro_smtp(self, notificacao: dict) -> tuple[bool, str]:
        host = os.getenv('SMTP_HOST')
        porta = int(os.getenv('SMTP_PORT', '587') or '587')
        usuario = os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER')
        senha = os.getenv('SMTP_PASSWORD')
        remetente = (
            os.getenv('SMTP_FROM')
            or os.getenv('SMTP_SENDER')
            or usuario
        )
        usar_tls = str(os.getenv('SMTP_USE_TLS', '1')).strip().lower() in ('1', 'true', 'yes', 'y')
        usar_ssl = str(os.getenv('SMTP_USE_SSL', '0')).strip().lower() in ('1', 'true', 'yes', 'y')

        if not host or not remetente:
            return False, "Configuração SMTP ausente"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = notificacao['subject']
        msg['From'] = remetente
        msg['To'] = ', '.join(notificacao['to'])
        msg.attach(MIMEText(notificacao['text'], 'plain', 'utf-8'))
        msg.attach(MIMEText(notificacao['html'], 'html', 'utf-8'))

        try:
            if usar_ssl:
                servidor = smtplib.SMTP_SSL(host, porta, timeout=30)
            else:
                servidor = smtplib.SMTP(host, porta, timeout=30)
            with servidor:
                servidor.ehlo()
                if usar_tls and not usar_ssl:
                    servidor.starttls()
                    servidor.ehlo()
                if usuario and senha:
                    servidor.login(usuario, senha)
                servidor.sendmail(remetente, notificacao['to'], msg.as_string())
            return True, "Enviado via SMTP"
        except Exception as e:
            return False, f"Falha no SMTP: {e}"

    def _enviar_email_erro_outlook(self, notificacao: dict) -> tuple[bool, str]:
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except Exception as e:
            return False, f"Outlook COM indisponível: {e}"

        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = '; '.join(notificacao['to'])
            mail.Subject = notificacao['subject']
            mail.HTMLBody = notificacao['html']
            mail.Send()
            return True, "Enviado via Outlook Desktop"
        except Exception as e:
            return False, f"Falha no Outlook Desktop: {e}"

    def _enviar_email_erro(self, email_data: dict, dados_processo: dict) -> None:
        """Envia email de notificação de erro com fallback automático."""
        notificacao = self._montar_notificacao_erro(email_data, dados_processo)
        tentativas = [
            ("Graph", self._enviar_email_erro_graph),
            ("SMTP", self._enviar_email_erro_smtp),
            ("Outlook", self._enviar_email_erro_outlook),
        ]
        erros = []

        for nome, metodo in tentativas:
            ok, detalhe = metodo(notificacao)
            if ok:
                logger.info(
                    f"[EMAIL-ERRO] Notificação enviada -> {', '.join(notificacao['to'])} "
                    f"(CNJ {notificacao['cnj']}) via {nome}"
                )
                return
            erros.append(f"{nome}: {detalhe}")
            logger.warning(f"[EMAIL-ERRO] {nome} indisponível: {detalhe}")

        logger.error(
            "[EMAIL-ERRO] Nenhum método conseguiu enviar a notificação. "
            + " | ".join(erros)
        )

    # ------------------------------------------------------------------
    # Notificação de SUCESSO por email (espelho de _enviar_email_erro)
    # ------------------------------------------------------------------
    def _enviar_email_sucesso(self, email_data: dict, dados_processo: dict) -> None:
        """Envia email de confirmação de cadastro bem-sucedido."""
        email_data = email_data or {}
        dados_processo = dados_processo or {}

        cnj = dados_processo.get('cnj', 'N/A')
        cliente = dados_processo.get('cliente') or dados_processo.get('autor') or 'N/A'
        contrario = dados_processo.get('contrario') or dados_processo.get('reu') or 'N/A'
        link = email_data.get('forms_link', 'N/A')
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        qa_warnings = dados_processo.get('_qa_warnings', []) or []
        pedidos_stats = dados_processo.get('_pedidos_stats', {}) or {}
        preenchidos = pedidos_stats.get('preenchidos', 0)
        total = pedidos_stats.get('total', 0)
        mon = dados_processo.get('_monitoramento') or {}

        # Seção Monitoramento (item 11)
        mon_html = ""
        status_mon = (mon.get('status') or '').upper()
        if status_mon == 'OK' or status_mon == 'RESOLVIDO':
            cor = "#0a7a28"
            msg_mon = "Monitoramento configurado automaticamente."
            if status_mon == 'RESOLVIDO':
                msg_mon += f" (card #{mon.get('indice')}, confiança={mon.get('confianca'):.2f})"
            mon_html = (
                f'<div style="margin-top:12px;padding:10px;border-left:4px solid {cor};'
                f'background:#eafaf0;color:{cor};"><strong>Monitoramento:</strong> {msg_mon}</div>'
            )
        elif status_mon == 'PENDENTE':
            cards = mon.get('cards') or []
            sug = mon.get('sugestao') or {}
            dj = mon.get('datajud') or []
            jb = mon.get('jusbrasil') or {}
            cards_html = "".join(
                f"<li><pre style='white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;'>"
                f"{str(c)[:800]}</pre></li>" for c in cards[:5]
            )
            dj_resumo = "; ".join(
                f"classe={h.get('classe',{}).get('nome','?')} / tribunal={h.get('tribunal','?')}"
                for h in (dj[:3] if isinstance(dj, list) else [])
            ) or "sem hits"
            jb_fase = (jb or {}).get('fase') or 'N/A'
            mon_html = f"""
<div style="margin-top:12px;padding:12px;border-left:4px solid #cc0000;background:#fdecec;color:#8b0000;">
  <strong>⚠ Monitoramento PENDENTE</strong>
  <p>O sistema não conseguiu escolher automaticamente o processo correto para monitoramento.</p>
  <p><strong>Cards disponíveis ({len(cards)}):</strong></p>
  <ul>{cards_html}</ul>
  <p><strong>Datajud:</strong> {dj_resumo}</p>
  <p><strong>JusBrasil (fase):</strong> {jb_fase}</p>
  <p><strong>Sugestão do Brain:</strong> índice={sug.get('indice_escolhido','-')},
     confiança={sug.get('confianca','-')}, justificativa: {sug.get('justificativa','-')}</p>
  <p><strong>Ação necessária:</strong> acesse LegalOne &gt; clique em <em>Necessita ação</em>
     &gt; selecione o card correto.</p>
</div>
"""

        qa_html = ""
        if qa_warnings:
            lis = "".join(f"<li>{w}</li>" for w in qa_warnings[:30])
            qa_html = f"<p><strong>QA Warnings ({len(qa_warnings)}):</strong></p><ul>{lis}</ul>"

        ped_cor = "#0a7a28" if total == 0 or preenchidos == total else "#b36b00"
        ped_html = (
            f'<p style="color:{ped_cor};"><strong>Pedidos:</strong> {preenchidos}/{total}</p>'
        )

        html = f"""
<html><body style="font-family:Arial,sans-serif;font-size:14px;">
<h2 style="color:#0a7a28;">✅ Cadastro concluído — LegalOne</h2>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr><th align="left">Data/Hora</th><td>{timestamp}</td></tr>
  <tr><th align="left">CNJ</th><td>{cnj}</td></tr>
  <tr><th align="left">Cliente</th><td>{cliente}</td></tr>
  <tr><th align="left">Contrário</th><td>{contrario}</td></tr>
  <tr><th align="left">Forms</th><td><a href="{link}">{link}</a></td></tr>
</table>
{ped_html}
{qa_html}
{mon_html}
<p style="font-size:12px;color:#666;">Email automático — automação LegalOne.</p>
</body></html>
"""

        texto = (
            f"Cadastro concluído - LegalOne\n\n"
            f"Data/Hora: {timestamp}\nCNJ: {cnj}\nCliente: {cliente}\n"
            f"Contrário: {contrario}\nForms: {link}\n"
            f"Pedidos: {preenchidos}/{total}\n"
            f"QA Warnings: {len(qa_warnings)}\n"
            f"Monitoramento: {status_mon or 'N/A'}\n"
        )

        notificacao = {
            'cnj': cnj,
            'subject': f"[OK CADASTRO] CNJ {cnj} — cadastro concluído",
            'text': texto,
            'html': html,
            'to': self._destinatarios_erro(),
        }

        tentativas = [
            ("Graph", self._enviar_email_erro_graph),
            ("SMTP", self._enviar_email_erro_smtp),
            ("Outlook", self._enviar_email_erro_outlook),
        ]
        for nome, metodo in tentativas:
            try:
                ok, detalhe = metodo(notificacao)
                if ok:
                    logger.info(f"[EMAIL-OK] Sucesso enviado via {nome} — {detalhe}")
                    return
                logger.warning(f"[EMAIL-OK] {nome} indisponível: {detalhe}")
            except Exception as e:
                logger.warning(f"[EMAIL-OK] {nome} exceção: {e}")
        logger.error("[EMAIL-OK] Nenhum método conseguiu enviar o email de sucesso.")

    def mostrar_estatisticas(self):
        """Mostra estatísticas com formatação visual"""
        resumo = self.formatter.format_statistics(self.stats)
        logger.info(resumo)

    def iniciar(self):
        """Inicia monitoramento"""
        try:
            logger.info(f"\n{formatter.SYMBOLS['star']} INICIANDO AUTOMAÇÃO LEGALONE")
            logger.info(f"{formatter._get_separator('=', 80)}")
            logger.info(f"{formatter.SYMBOLS['arrow']} Monitorando: {self.config['outlook']['assunto_filtro']}")
            logger.info(f"{formatter.SYMBOLS['arrow']} Intervalo: {self.config['outlook']['intervalo_checagem']}s")
            logger.info(f"{formatter.SYMBOLS['arrow']} Modo: {'AUTOMÁTICO' if self.config['modo_automatico'] else 'MANUAL'}")
            logger.info(f"{formatter._get_separator('=', 80)}")
            logger.info(f"\n{formatter.SYMBOLS['info']} Pressione Ctrl+C para parar\n")

            self.monitor_outlook.monitorar_continuamente(self.processar_email)

        except KeyboardInterrupt:
            logger.info(f"\n{formatter.SYMBOLS['warning']} Automação interrompida pelo usuário")
            self._shutdown_async_loop()
            self.mostrar_estatisticas()
        except Exception as e:
            error_info = formatter.format_error_details(str(e), source='iniciar')
            logger.error(error_info)
            logger.exception(e)
            self.salvar_log_erro(
                {'subject': 'Falha ao iniciar automação', 'sender': 'sistema', 'forms_link': 'N/A'},
                {
                    'erro': str(e),
                    'contexto': 'iniciar_automacao',
                    'traceback': traceback.format_exc(),
                },
            )
            self._shutdown_async_loop()
            self.mostrar_estatisticas()

    def _shutdown_async_loop(self):
        """Fecha o forms_extractor e desliga o event loop persistente."""
        try:
            if hasattr(self, '_async_loop') and self._async_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.forms_extractor.fechar_forms(), self._async_loop
                )
                try:
                    future.result(timeout=10)
                except Exception:
                    pass
                self._async_loop.call_soon_threadsafe(self._async_loop.stop)
                self._async_thread.join(timeout=5)
        except Exception:
            pass


def main():
    """Função principal"""
    print(f"""
    {formatter._get_separator('=', 80)}
    {formatter.SYMBOLS['star']} AUTOMAÇÃO LEGALONE - OUTLOOK + FORMS
    
    {formatter.SYMBOLS['arrow']} Monitora emails e cadastra processos automaticamente
    {formatter._get_separator('=', 80)}
    """)

    print("\n[MENU] Modo de operação:")
    print("   1. Automático (cadastra sem confirmação)")
    print("   2. Manual (pede confirmação)")
    print("   3. Teste (apenas monitora, não cadastra)")
    print("   4. Forms Direto (pula Outlook, insere link do Forms)")

    while True:
        escolha = input("\nOpção (1/2/3/4): ").strip()
        if escolha in ['1', '2', '3', '4']:
            break
        print("[ERRO] Opção inválida!")

    config = {}
    if escolha == '1':
        config['modo_automatico'] = True
        print("\n[OK] Modo AUTOMÁTICO")
    elif escolha == '2':
        config['modo_automatico'] = False
        print("\n[OK] Modo MANUAL")
    else:
        print("\n[OK] Modo TESTE")
        config['modo_automatico'] = False

    if escolha == '4':
        print("\n[OK] Modo FORMS DIRETO - Pula monitoramento do Outlook")
        config['modo_automatico'] = True
        config['skip_email'] = True
        automacao = AutomacaoLegalOne(config)

        while True:
            link = input("\nCole o link do Forms (ou 'sair' para encerrar): ").strip()
            if link.lower() in ('sair', 'exit', 'q', 'quit'):
                print("\n[FIM] Encerrando.")
                automacao._shutdown_async_loop()
                automacao.mostrar_estatisticas()
                break
            if not link:
                print("[ERRO] Link vazio!")
                continue

            email_fake = {
                'subject': 'Forms Direto (manual)',
                'sender': 'usuario@manual',
                'forms_link': link,
            }
            automacao.processar_email(email_fake)

            continuar = input("\nProcessar outro link? (s/n): ").strip().lower()
            if continuar != 's':
                print("\n[FIM] Encerrando.")
                automacao._shutdown_async_loop()
                automacao.mostrar_estatisticas()
                break
        return

    intervalo = input("\nIntervalo em segundos (padrão 300): ").strip()
    if intervalo.isdigit():
        if 'outlook' not in config:
            config['outlook'] = {}
        config['outlook']['intervalo_checagem'] = int(intervalo)

    automacao = AutomacaoLegalOne(config)

    if escolha == '3':
        print("\n[TESTE] MODO TESTE - Apenas monitorando")

        def callback_teste(email_data):
            print("\n" + "="*80)
            print("[EMAIL] EMAIL DETECTADO (TESTE):")
            print("="*80)
            eh_copilot = bool(email_data.get('dados_diretos'))
            print(f"Assunto: {email_data['subject']}")
            print(f"Fonte: {'Power Automate / Copilot' if eh_copilot else 'Microsoft Forms'}")
            if eh_copilot:
                dados = email_data['dados_diretos']
                print(f"CNJ: {dados.get('cnj', 'N/A')}")
                print(f"Cliente: {dados.get('cliente', 'N/A')}")
            else:
                print(f"Link: {email_data.get('forms_link', 'N/A')}")
            print("="*80)
            print("[AVISO]  Em modo normal, seria cadastrado automaticamente")

        automacao.monitor_outlook.monitorar_continuamente(callback_teste)
    else:
        automacao.iniciar()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        logger.exception(e)
        input("\nEnter para sair...")
        sys.exit(1)
