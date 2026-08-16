"""
Monitor de emails via Microsoft Graph API (cloud-compatible).
Substitui o outlook_monitor.py (que usa COM/pywin32) para rodar na nuvem.

Usa OAuth2 com client_credentials (sem interação do usuário)
para ler emails de uma caixa de entrada do Microsoft 365.
"""

import os
import re
import time
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("outlook_monitor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arquivo de estado — guarda IDs dos emails já processados entre reinícios
# ---------------------------------------------------------------------------
STATE_FILE = os.getenv("GRAPH_STATE_FILE", "graph_processed_emails.json")


def _load_state() -> set:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_state(ids: set):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)


class OutlookMonitorGraph:
    """
    Monitora emails do Microsoft 365 via Graph API.

    Requer um App Registration no Azure AD com:
        - Application permission: Mail.Read  (ou Mail.ReadWrite)
        - Admin consent concedido

    Variáveis de ambiente necessárias:
        AZURE_TENANT_ID     – ID do tenant Azure AD
        AZURE_CLIENT_ID     – App (client) ID
        AZURE_CLIENT_SECRET – Client secret
        GRAPH_USER_EMAIL    – Email da caixa a monitorar (ex: usuario@empresa.com)
    """

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    # Assunto usado pelo fluxo Power Automate do Copilot Studio
    COPILOT_ASSUNTO = "LegalOne - Dados Extraidos de Peticao"

    def __init__(
        self,
        assunto_filtro: str | list[str] = "Cadastro de processos NOVOS LegalOne trabalhista",
        remetente_filtro: str = "microsoft.com",
        intervalo_checagem: int = 300,
    ):
        # Suporta um único assunto (compatibilidade) ou lista de assuntos (multinatureza)
        if isinstance(assunto_filtro, str):
            self.assunto_filtro = [assunto_filtro]
        else:
            self.assunto_filtro = list(assunto_filtro)
        self.remetente_filtro = remetente_filtro
        self.intervalo_checagem = intervalo_checagem
        # Ate onde olhar para tras a cada ciclo. Era fixo em 120 min, o que perdia
        # email em silencio quando a maquina dormia mais que isso (o PC suspende).
        # Alargar e' seguro: a dedupe e' por ID em graph_processed_emails.json,
        # nao por tempo — a janela so define o alcance da busca.
        self.janela_minutos = int(os.getenv("GRAPH_JANELA_MINUTOS", "1440"))

        # Azure AD
        self.tenant_id = os.environ["AZURE_TENANT_ID"]
        self.client_id = os.environ["AZURE_CLIENT_ID"]
        self.client_secret = os.environ["AZURE_CLIENT_SECRET"]
        self.user_email = os.environ["GRAPH_USER_EMAIL"]

        self._access_token: str | None = None
        self._token_expires: datetime = datetime.min.replace(tzinfo=timezone.utc)

        # Emails já processados (persistidos em disco)
        self.emails_processados: set = _load_state()

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------
    def _obter_token(self) -> str:
        """Obtém ou renova o access token (client_credentials)."""
        agora = datetime.now(timezone.utc)
        if self._access_token and agora < self._token_expires:
            return self._access_token

        url = self.TOKEN_URL.format(tenant=self.tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        resp = requests.post(url, data=data, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        self._access_token = body["access_token"]
        self._token_expires = agora + timedelta(seconds=body.get("expires_in", 3500) - 60)
        logger.info("[AUTH] Token Graph API obtido/renovado com sucesso.")
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._obter_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Leitura de emails
    # ------------------------------------------------------------------
    def extrair_link_forms(self, corpo_email: str) -> str | None:
        """Extrai o link do Microsoft Forms do corpo do email."""
        patterns = [
            r"https://forms\.office\.com/[^\s<>\"]+",
            r"https://forms\.microsoft\.com/[^\s<>\"]+",
        ]
        for pattern in patterns:
            match = re.search(pattern, corpo_email)
            if match:
                url = match.group(0)
                url = re.sub(r'[.,;!?\)]+$', "", url)
                logger.info(f"[LINK] Forms encontrado: {url}")
                return url
        logger.warning("[AVISO] Nenhum link do Forms encontrado no email")
        return None

    @staticmethod
    def extrair_respondente(corpo_email: str) -> str | None:
        """'Voce recebeu uma nova resposta de Marcela Leite Kato.' -> o nome.

        E' o unico lugar onde o Forms diz QUEM respondeu: a resposta em si so'
        traz as perguntas do formulario, sem identificar quem preencheu.
        """
        import html as html_mod
        texto = html_mod.unescape(re.sub(r'<[^>]+>', ' ', corpo_email or ''))
        m = re.search(r'nova resposta de\s+([^.<\n]{3,80})', texto, re.IGNORECASE)
        return re.sub(r'\s+', ' ', m.group(1)).strip(' .') if m else None

    def _extrair_json_do_corpo(self, corpo_html: str) -> dict | None:
        """Tenta extrair JSON estruturado do corpo do email (emails do Copilot)."""
        import html as html_mod
        texto = re.sub(r'<[^>]+>', ' ', corpo_html)
        texto = html_mod.unescape(texto).strip()

        # Tenta encontrar JSON no texto
        match = re.search(r'\{[^{}]*"cnj"[^{}]*\}', texto, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # JSON com objetos aninhados (ex.: "outros_dados") e/ou texto em volta:
        # pega do primeiro '{' ao ultimo '}'. A regex acima so casa JSON plano.
        inicio, fim = texto.find('{'), texto.rfind('}')
        if inicio != -1 and fim > inicio:
            try:
                dados = json.loads(texto[inicio:fim + 1])
                if isinstance(dados, dict) and 'cnj' in dados:
                    return dados
            except (json.JSONDecodeError, ValueError):
                pass

        # Tenta o texto inteiro como JSON
        try:
            dados = json.loads(texto)
            if isinstance(dados, dict) and 'cnj' in dados:
                return dados
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    def buscar_novos_emails(self, minutos_atras: int = 30) -> list[dict]:
        """Busca emails recentes — aceita Forms (link) E Copilot (JSON direto)."""
        data_limite = (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # OData filter: aceita TODOS os assuntos de Forms OU Copilot
        assuntos_forms = " or ".join(
            f"contains(subject, '{assunto}')" for assunto in self.assunto_filtro
        )
        filtro_str = (
            f"receivedDateTime ge {data_limite}"
            f" and (({assuntos_forms})"
            f" or contains(subject, '{self.COPILOT_ASSUNTO}'))"
        )

        url = (
            f"{self.GRAPH_BASE}/users/{self.user_email}/messages"
            f"?$filter={filtro_str}"
            f"&$top=50"
            f"&$orderby=receivedDateTime desc"
            f"&$select=id,internetMessageId,subject,from,receivedDateTime,body"
        )

        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f"[ERRO] Graph API retornou erro: {e}")
            return []

        mensagens = resp.json().get("value", [])
        emails_encontrados = []

        for msg in mensagens:
            msg_id = msg["id"]
            # O Power Automate manda do proprio usuario para o proprio usuario:
            # a mesma mensagem existe em Itens Enviados E na Caixa de Entrada, e
            # /messages varre todas as pastas. Cada copia tem `id` proprio — so'
            # o internetMessageId e' igual. Dedupar por `id` fazia o bot
            # processar a peticao duas vezes (e mandar dois e-mails de erro).
            chave = msg.get("internetMessageId") or msg_id

            # Já processado? `msg_id` tambem conta: o estado gravado antes de
            # 13/08/2026 guardava id de mensagem, e sem essa segunda checagem a
            # primeira rodada apos o deploy reprocessaria a janela inteira.
            if chave in self.emails_processados or msg_id in self.emails_processados:
                continue

            sender_addr = (
                msg.get("from", {}).get("emailAddress", {}).get("address", "")
            )
            subject = msg.get("subject", "")
            corpo = msg.get("body", {}).get("content", "")

            # Detecta se é email do Copilot (JSON) ou do Forms (link)
            is_copilot = self.COPILOT_ASSUNTO.lower() in subject.lower()

            if is_copilot:
                # Email do Copilot: corpo contém JSON, sem filtro de remetente
                json_data = self._extrair_json_do_corpo(corpo)
                if not json_data:
                    logger.warning(f"[COPILOT] Email '{subject}' sem JSON válido no corpo — ignorado")
                    continue

                dados = {
                    "subject": subject,
                    "sender": sender_addr,
                    "received_time": msg.get("receivedDateTime", ""),
                    "body": corpo,
                    "entry_id": msg_id,
                    "forms_link": None,
                    "dados_diretos": json_data,
                }
                emails_encontrados.append(dados)
                self.emails_processados.add(chave)
                logger.info(f"[COPILOT] Email do Copilot detectado: CNJ={json_data.get('cnj', '?')}")

            else:
                # Email do Forms: filtro de remetente + link obrigatório
                if self.remetente_filtro and self.remetente_filtro not in sender_addr:
                    continue

                link = self.extrair_link_forms(corpo)
                # Identifica qual assunto de Forms casou (usado pelo fluxo principal
                # para escolher o mapeador correto)
                assunto_detectado = next(
                    (a for a in self.assunto_filtro if a.lower() in subject.lower()),
                    self.assunto_filtro[0] if self.assunto_filtro else "",
                )
                dados = {
                    "subject": subject,
                    "sender": sender_addr,
                    "received_time": msg.get("receivedDateTime", ""),
                    "body": corpo,
                    "entry_id": msg_id,
                    "forms_link": link,
                    "assunto_detectado": assunto_detectado,
                    # Quem preencheu — vira destinatario do e-mail de sucesso.
                    "respondente": self.extrair_respondente(corpo),
                }

                if dados["forms_link"]:
                    emails_encontrados.append(dados)
                    self.emails_processados.add(chave)

            # Marca como lido
            try:
                patch_url = f"{self.GRAPH_BASE}/users/{self.user_email}/messages/{msg_id}"
                requests.patch(
                    patch_url,
                    headers=self._headers(),
                    json={"isRead": True},
                    timeout=10,
                )
            except Exception:
                pass

        # Persiste estado
        _save_state(self.emails_processados)

        if emails_encontrados:
            logger.info(f"[OK] {len(emails_encontrados)} novo(s) email(s) encontrado(s)!")
        else:
            logger.info("[INFO] Nenhum email novo encontrado")

        return emails_encontrados

    # ------------------------------------------------------------------
    # Loop contínuo
    # ------------------------------------------------------------------
    def monitorar_continuamente(self, callback_func):
        """Monitora continuamente novos emails (loop infinito)."""
        logger.info("=" * 60)
        logger.info("[INICIO] Monitoramento contínuo via Graph API")
        logger.info(f"[CONFIG] Caixa: {self.user_email}")
        logger.info(f"[CONFIG] Assunto Forms: {self.assunto_filtro}")
        logger.info(f"[CONFIG] Assunto Copilot: '{self.COPILOT_ASSUNTO}'")
        logger.info(f"[CONFIG] Remetente contém: '{self.remetente_filtro}'")
        logger.info(f"[CONFIG] Intervalo: {self.intervalo_checagem}s")
        logger.info("=" * 60)

        try:
            while True:
                hora_atual = datetime.now().strftime("%H:%M:%S")
                logger.info(f"\n[VERIFICA] Verificando emails... [{hora_atual}]")

                # ponytail: erro de rede so pula o ciclo — antes um reset de TCP
                # (WinError 10054) na Graph matava a automacao inteira.
                try:
                    emails = self.buscar_novos_emails(minutos_atras=self.janela_minutos)
                except requests.RequestException as e:
                    logger.warning(f"[REDE] Falha ao consultar Graph, tentando de novo no proximo ciclo: {e}")
                    emails = []

                for email_data in emails:
                    try:
                        logger.info(f"\n[PROCESSA] Processando: {email_data['subject']}")
                        callback_func(email_data)
                    except Exception as e:
                        logger.error(f"[ERRO] Erro no callback: {e}")

                logger.info(
                    f"[AGUARDA] Aguardando {self.intervalo_checagem}s até próxima verificação..."
                )
                time.sleep(self.intervalo_checagem)

        except KeyboardInterrupt:
            logger.info("\n\n[PARADO] Monitoramento interrompido (Ctrl+C)")
        except Exception as e:
            logger.error(f"\n\n[ERRO] Erro fatal: {e}")
            raise


# Alias para compatibilidade — basta trocar o import
OutlookMonitor = OutlookMonitorGraph
