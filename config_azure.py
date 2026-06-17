"""
Configuração Azure para Opção B — Document Intelligence + OpenAI
"""
import os

AZURE_OPENAI_CONFIG = {
    'endpoint': os.getenv('AZURE_OPENAI_ENDPOINT', ''),
    'api_key': os.getenv('AZURE_OPENAI_API_KEY', ''),
    'deployment': os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o'),
    'api_version': os.getenv('AZURE_OPENAI_API_VERSION', '2024-08-01-preview'),
}

AZURE_DOC_INTELLIGENCE_CONFIG = {
    'endpoint': os.getenv('AZURE_DOC_INTELLIGENCE_ENDPOINT', ''),
    'api_key': os.getenv('AZURE_DOC_INTELLIGENCE_KEY', ''),
}

PETICAO_API_CONFIG = {
    'host': os.getenv('PETICAO_API_HOST', '0.0.0.0'),
    'port': int(os.getenv('PETICAO_API_PORT', '8000')),
    'webhook_secret': os.getenv('PETICAO_WEBHOOK_SECRET', ''),
}

CAMPOS_OBRIGATORIOS = [
    'cnj', 'cliente', 'contrario', 'natureza', 'tribunal',
    'comarca', 'instancia', 'posicao', 'fase', 'tipo_cadastro',
]

TIPOS_CADASTRO_VALIDOS = [
    'CADASTRO INICIAL',
    'DECISÕES',
    'RECURSO',
    'ARQUIVAMENTO COMPLETO',
    'ARQUIVAMENTO SIMPLES',
]
