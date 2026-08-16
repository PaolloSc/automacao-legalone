"""
Modulo para monitorar emails do Outlook vindos do Microsoft Forms
ou do Power Automate (via Copilot Studio) sobre cadastro de processos LegalOne
"""

import win32com.client
import pythoncom
import time
import json
from datetime import datetime, timedelta
import re
import logging
import sys

# Configuracao de logging (SEM EMOJIS para evitar erro Windows)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('outlook_monitor.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class OutlookMonitor:
    """Monitora emails do Outlook buscando respostas do Microsoft Forms"""

    def __init__(self,
                 assunto_filtro="Cadastro de processos NOVOS LegalOne trabalhista",
                 remetente_filtro="microsoft.com",
                 intervalo_checagem=300):
        """
        Inicializa o monitor do Outlook

        Args:
            assunto_filtro: Parte do assunto (str) ou lista de assuntos para filtrar emails
            remetente_filtro: Dominio ou email do remetente
            intervalo_checagem: Intervalo em segundos entre verificacoes
        """
        if isinstance(assunto_filtro, str):
            self.assunto_filtro = [assunto_filtro]
        else:
            self.assunto_filtro = list(assunto_filtro)
        self.remetente_filtro = remetente_filtro
        self.intervalo_checagem = intervalo_checagem
        self.emails_processados = set()

    def conectar_outlook(self):
        """Conecta ao Outlook via COM"""
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)  # 6 = caixa de entrada
            logger.info("[OK] Conectado ao Outlook com sucesso!")
            return inbox
        except Exception as e:
            logger.error(f"[ERRO] Erro ao conectar ao Outlook: {e}")
            raise

    # Tag usada pelo Power Automate para identificar e-mails com dados diretos
    COPILOT_TAG = "[COPILOT]"
    # Marcadores do bloco JSON no corpo do e-mail
    JSON_INICIO = "##DADOS_PROCESSO##"
    JSON_FIM    = "##FIM_DADOS##"

    def extrair_dados_direto(self, corpo_email):
        """
        Extrai dados estruturados do corpo do e-mail quando enviado pelo
        Power Automate (sem URL do Forms). Espera o formato:

            ##DADOS_PROCESSO##
            { ... JSON com os campos do processo ... }
            ##FIM_DADOS##
        """
        try:
            # Remove tags HTML para trabalhar com texto puro
            texto = re.sub(r'<[^>]+>', ' ', corpo_email)
            texto = re.sub(r'&nbsp;', ' ', texto)
            texto = re.sub(r'&#\d+;', '', texto)

            inicio = texto.find(self.JSON_INICIO)
            fim    = texto.find(self.JSON_FIM)

            if inicio == -1 or fim == -1:
                return None

            json_str = texto[inicio + len(self.JSON_INICIO):fim].strip()
            dados = json.loads(json_str)
            logger.info("[COPILOT] Dados diretos extraidos do e-mail com sucesso")
            return dados
        except Exception as e:
            logger.error(f"[ERRO] Falha ao extrair dados diretos do e-mail: {e}")
            return None

    def extrair_link_forms(self, corpo_email):
        """Extrai o link do Microsoft Forms do corpo do email"""
        patterns = [
            r'https://forms\.office\.com/[^\s<>"]+',
            r'https://forms\.microsoft\.com/[^\s<>"]+',
        ]

        for pattern in patterns:
            match = re.search(pattern, corpo_email)
            if match:
                url = match.group(0)
                url = re.sub(r'[.,;!?\)]+$', '', url)
                logger.info(f"[LINK] Forms encontrado: {url}")
                return url

        logger.warning("[AVISO] Nenhum link do Forms encontrado no email")
        return None

    def extrair_dados_email(self, email, assunto_detectado=None):
        """Extrai dados relevantes do email"""
        try:
            corpo = ""
            try:
                corpo = email.HTMLBody
            except:
                try:
                    corpo = email.Body
                except:
                    pass

            eh_copilot = self.COPILOT_TAG in email.Subject
            dados = {
                'subject': email.Subject,
                'sender': email.SenderEmailAddress,
                'received_time': email.ReceivedTime,
                'body': corpo,
                'entry_id': email.EntryID,
                'forms_link': None if eh_copilot else self.extrair_link_forms(corpo),
                'dados_diretos': self.extrair_dados_direto(corpo) if eh_copilot else None,
                'assunto_detectado': assunto_detectado,
            }

            logger.info(f"[EMAIL] Extraido:")
            logger.info(f"  Assunto: {dados['subject']}")
            logger.info(f"  De: {dados['sender']}")
            logger.info(f"  Recebido: {dados['received_time']}")

            return dados

        except Exception as e:
            logger.error(f"[ERRO] Erro ao extrair dados do email: {e}")
            return None

    def buscar_novos_emails(self, inbox, minutos_atras=30):
        """Busca emails que correspondem aos filtros"""
        try:
            messages = inbox.Items
            messages.Sort("[ReceivedTime]", True)

            # Limita a busca aos ultimos N emails para evitar sobrecarga
            limite_emails = 50

            emails_encontrados = []
            contador = 0
            data_limite = datetime.now() - timedelta(minutes=minutos_atras)

            logger.info(f"[BUSCA] Buscando emails desde {data_limite.strftime('%d/%m/%Y %H:%M')}")

            for message in messages:
                try:
                    contador += 1
                    if contador > limite_emails:
                        break

                    # Verifica data
                    try:
                        received_time = message.ReceivedTime
                        if received_time < data_limite:
                            continue
                    except:
                        pass

                    # Verifica se ja foi processado
                    try:
                        if message.EntryID in self.emails_processados:
                            continue
                    except:
                        continue

                    # Verifica assunto (aceita lista de assuntos)
                    try:
                        if self.assunto_filtro:
                            assunto_detectado = next(
                                (a for a in self.assunto_filtro if a in message.Subject),
                                None,
                            )
                            if not assunto_detectado:
                                continue
                        else:
                            assunto_detectado = ""
                    except:
                        continue

                    # Verifica remetente (e-mails [COPILOT] dispensam filtro de remetente)
                    try:
                        eh_copilot = self.COPILOT_TAG in message.Subject
                        if not eh_copilot:
                            if self.remetente_filtro and self.remetente_filtro not in message.SenderEmailAddress:
                                continue
                    except:
                        continue

                    dados = self.extrair_dados_email(message, assunto_detectado)
                    # Aceita e-mail se tiver link do Forms OU dados diretos do Copilot
                    if dados and (dados['forms_link'] or dados['dados_diretos']):
                        emails_encontrados.append(dados)
                        self.emails_processados.add(message.EntryID)

                        # Marca como lido
                        try:
                            message.UnRead = False
                            message.Save()
                        except:
                            pass

                except Exception as e:
                    logger.debug(f"Erro ao processar mensagem: {e}")
                    continue

            if emails_encontrados:
                logger.info(f"[OK] {len(emails_encontrados)} novo(s) email(s) encontrado(s)!")
            else:
                logger.info("[INFO] Nenhum email novo encontrado")

            return emails_encontrados

        except Exception as e:
            logger.error(f"[ERRO] Erro ao buscar emails: {e}")
            return []

    def monitorar_continuamente(self, callback_func):
        """Monitora continuamente novos emails"""
        logger.info("="*60)
        logger.info("[INICIO] Monitoramento continuo do Outlook")
        logger.info(f"[CONFIG] Assunto contem: {self.assunto_filtro}")
        logger.info(f"[CONFIG] Remetente contem: '{self.remetente_filtro}'")
        logger.info(f"[CONFIG] Intervalo: {self.intervalo_checagem}s")
        logger.info("="*60)

        inbox = self.conectar_outlook()

        try:
            while True:
                hora_atual = datetime.now().strftime('%H:%M:%S')
                logger.info(f"\n[VERIFICA] Verificando emails... [{hora_atual}]")

                emails = self.buscar_novos_emails(inbox, minutos_atras=30)

                for email_data in emails:
                    try:
                        logger.info(f"\n[PROCESSA] Processando: {email_data['subject']}")
                        callback_func(email_data)
                    except Exception as e:
                        logger.error(f"[ERRO] Erro no callback: {e}")

                logger.info(f"[AGUARDA] Aguardando {self.intervalo_checagem}s ate proxima verificacao...")
                time.sleep(self.intervalo_checagem)

        except KeyboardInterrupt:
            logger.info("\n\n[PARADO] Monitoramento interrompido (Ctrl+C)")
        except Exception as e:
            logger.error(f"\n\n[ERRO] Erro fatal: {e}")
            raise
        finally:
            pythoncom.CoUninitialize()
            logger.info("[FIM] Conexao com Outlook fechada")


def teste_monitor():
    """Funcao de teste do monitor"""
    def callback_teste(email_data):
        print("\n" + "="*60)
        print("[EMAIL RECEBIDO]")
        print("="*60)
        print(f"Assunto: {email_data['subject']}")
        print(f"De: {email_data['sender']}")
        print(f"Link Forms: {email_data['forms_link']}")
        print("="*60)

    monitor = OutlookMonitor(
        assunto_filtro="Cadastro de processos NOVOS LegalOne trabalhista",
        remetente_filtro="microsoft.com",
        intervalo_checagem=60
    )

    monitor.monitorar_continuamente(callback_teste)


if __name__ == "__main__":
    teste_monitor()
