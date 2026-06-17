"""
Configuração para Automação LegalOne
"""
import os

# ==================== OUTLOOK ====================
OUTLOOK_CONFIG = {
    'assunto_filtro': 'Cadastro de processos NOVOS LegalOne trabalhista',
    'remetente_filtro': 'microsoft.com',  # Emails do Forms vem de @microsoft.com
    'intervalo_checagem': 300,  # 5 minutos
}

# ==================== LEGALONE ====================
# Credenciais lidas de variáveis de ambiente (ou edite os valores de fallback)
LEGALONE_CONFIG = {
    'username': os.getenv('LEGALONE_USERNAME', 'seu_email@exemplo.com'),   # ← Defina em .env ou variável de ambiente
    'password': os.getenv('LEGALONE_PASSWORD', ''),   # ← Defina em .env ou variável de ambiente
    'login_url': os.getenv('LEGALONE_LOGIN_URL', 'https://carvalhofurtadoadv.novajus.com.br/'),
}

# ==================== AUTOMAÇÃO ====================
AUTOMACAO_CONFIG = {
    'modo_automatico': True,  # True = auto, False = pede confirmação
    'salvar_screenshots': True,
    'timeout_default': 30000,  # 30 segundos
}

# ==================== LOGGING ====================
# Níveis de verbosidade: MINIMAL, NORMAL, DETAILED, VERBOSE
# - MINIMAL: apenas essencial (começou, terminou, erros)
# - NORMAL: resumo de operações (padrão)
# - DETAILED: todas as operações com categorização
# - VERBOSE: tudo, incluindo debug
LOGGING_CONFIG = {
    'nivel': 'NORMAL',  # MINIMAL | NORMAL | DETAILED | VERBOSE
    'verbosity': 'NORMAL',  # Alias para 'nivel'
    'arquivo_geral': 'automacao_legalone.log',
    'arquivo_sucesso': 'processos_cadastrados.log',
    'arquivo_erro': 'processos_erro.log',
    'mostrar_campos_vazios': False,  # Mostrar campos sem valores extraídos
    'agrupar_por_categoria': True,  # Agrupar campos por tipo (identification, partes, etc)
    'usar_cores': True,  # Usar cores no console (ANSI)
    'formato': 'categorizado',  # 'simples' | 'categorizado' | 'detalhado'
}

# ==================== FORMS ====================
FORMS_CONFIG = {
    'timeout': 30000,
    'campos_obrigatorios': ['cnj'],
    'campos_opcionais': ['autor', 'reu', 'tribunal', 'vara', 'comarca'],
}

# ==================== VISUAL GUARDIAN ====================
# Sistema de recuperação inteligente por Visão + LLM
# Ativado quando os fallbacks normais falham
VISUAL_GUARDIAN_CONFIG = {
    'habilitado': True,
    'dry_run': False,           # True = loga mas não executa ações
    'max_retries': 3,
    'confidence_threshold': 0.5,
    'max_calls_per_cadastro': 10,
    'vision_model': 'claude-sonnet-4-20250514',
    'screenshot_dir': 'guardian_screenshots',
    'log_path': 'guardian_log.jsonl',
}

# ==================== LEGALONE API REST ====================
LEGALONE_API_CONFIG = {
    'use_api': os.getenv('LEGALONE_USE_API', 'false').strip().lower() in ('1', 'true', 'yes', 'y'),
    'client_id': os.getenv('LEGALONE_API_CLIENT_ID', ''),
    'client_secret': os.getenv('LEGALONE_API_CLIENT_SECRET', ''),
    'token_url': os.getenv('LEGALONE_API_TOKEN_URL', 'https://api.thomsonreuters.com/legalone/oauth?grant_type=client_credentials'),
    'base_url': os.getenv('LEGALONE_API_BASE', 'https://api.thomsonreuters.com/legalone/lawsuit/v1/api/rest/v1'),
    'default_status_id': os.getenv('LEGALONE_DEFAULT_STATUS_ID', ''),
    'default_area_id': os.getenv('LEGALONE_DEFAULT_AREA_ID', ''),
    'timeout': 30,
}
