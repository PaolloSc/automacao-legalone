"""
Infraestrutura avançada de logging com suporte a múltiplos níveis de verbosidade
"""

import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def _supports_unicode() -> bool:
    """Detecta se stdout suporta caracteres Unicode (emojis)"""
    try:
        encoding = getattr(sys.stdout, 'encoding', '') or ''
        if encoding.lower().replace('-', '') in ('utf8', 'utf16', 'utf32'):
            return True
        # Testa se emoji encoda sem erro
        '⭐'.encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class LogFormatter:
    """Gerencia formatação de logs com diferentes níveis de verbosidade"""

    _SYMBOLS_UNICODE = {
        'success': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': 'ℹ️',
        'debug': '🔍',
        'list': '📋',
        'green': '🟢',
        'yellow': '🟡',
        'blue': '🔵',
        'black': '⚫',
        'arrow': '→',
        'star': '⭐',
        'clock': '⏱️',
    }

    _SYMBOLS_ASCII = {
        'success': '[OK]',
        'error': '[ERRO]',
        'warning': '[WARN]',
        'info': '[i]',
        'debug': '[DBG]',
        'list': '[*]',
        'green': '[+]',
        'yellow': '[~]',
        'blue': '[.]',
        'black': '[-]',
        'arrow': '->',
        'star': '*',
        'clock': '[T]',
    }

    SYMBOLS = _SYMBOLS_UNICODE if _supports_unicode() else _SYMBOLS_ASCII

    # Níveis de verbosidade
    LEVELS = {
        'MINIMAL': 0,
        'NORMAL': 1,
        'DETAILED': 2,
        'VERBOSE': 3,
    }

    # Categorizações de campos
    FIELD_CATEGORIES = {
        'identification': ['cnj', 'numero_cnj', 'numero_processo'],
        'partes': ['cliente', 'contrario', 'autor', 'reu', 'reclamante', 'reclamado'],
        'classificacao': ['tipo_cadastro', 'fase', 'instancia', 'procedimento', 'tribunal', 'vara', 'comarca'],
        'pedidos': ['pedidos', 'objetos', 'vinculo_trabalhista', 'contingencia'],
        'datas': ['data_distribuicao', 'data_julgamento', 'data_citacao', 'data_pedidos'],
        'valores': ['valor_causa', 'valor', 'salario'],
        'responsaveis': ['advogado', 'funcao_rcte', 'outros_envolvidos'],
        'descricoes': ['descricao_pedidos', 'observacoes', 'outros_dados'],
    }

    def __init__(self, verbosity_level: str = 'NORMAL'):
        """Inicializa o formatador com o nível de verbosidade desejado"""
        self.verbosity_level = self.LEVELS.get(verbosity_level.upper(), self.LEVELS['NORMAL'])
        self.verbosity_name = verbosity_level.upper()

    @staticmethod
    def _get_separator(char: str = '=', width: int = 80) -> str:
        """Cria separador visual"""
        return char * width

    @staticmethod
    def _get_mini_separator(width: int = 40) -> str:
        """Cria mini separador"""
        return '-' * width

    @staticmethod
    def _colorize_text(text: str, level: str = 'info') -> str:
        """Adiciona cores ao texto baseado no nível"""
        if level == 'success':
            return f"\033[92m{text}\033[0m"  # Verde
        elif level == 'error':
            return f"\033[91m{text}\033[0m"  # Vermelho
        elif level == 'warning':
            return f"\033[93m{text}\033[0m"  # Amarelo
        elif level == 'info':
            return f"\033[94m{text}\033[0m"  # Azul
        elif level == 'debug':
            return f"\033[96m{text}\033[0m"  # Ciano
        return text

    @staticmethod
    def categorize_field(field_name: str) -> Optional[str]:
        """Retorna a categoria de um campo"""
        field_lower = field_name.lower()
        for category, fields in LogFormatter.FIELD_CATEGORIES.items():
            if field_lower in fields or any(f in field_lower for f in fields):
                return category
        return None

    @staticmethod
    def format_field_value(value, max_length: int = 80) -> str:
        """Formata o valor de um campo para exibição"""
        if value is None:
            return "N/A"
        
        value_str = str(value)
        
        # Trunca valores longos
        if len(value_str) > max_length:
            value_str = value_str[:max_length] + "..."
        
        # Remove quebras de linha múltiplas
        value_str = value_str.replace('\n', ' | ')
        
        return value_str

    def format_extraction_data(self, data: Dict, show_empty: bool = False) -> str:
        """Formata dados de extração de forma legível"""
        if not data:
            return "Sem dados para exibir"

        lines = []
        
        if self.verbosity_level >= self.LEVELS['DETAILED']:
            lines.append(self._get_separator())
            lines.append(f"📊 DADOS EXTRAÍDOS - Nível: {self.verbosity_name}")
            lines.append(self._get_separator())
        
        # Agrupa campos por categoria
        categorized = {}
        uncategorized = {}
        
        for field, value in data.items():
            if field == 'outros_dados':
                continue
            
            # Pula campos vazios se não configurado para mostrar
            if not show_empty and not value:
                continue
            
            category = self.categorize_field(field)
            if category:
                if category not in categorized:
                    categorized[category] = {}
                categorized[category][field] = value
            else:
                uncategorized[field] = value
        
        # Exibe categorias
        category_labels = {
            'identification': 'Identificação',
            'partes': 'Partes',
            'classificacao': 'Classificação',
            'pedidos': 'Pedidos',
            'datas': 'Datas',
            'valores': 'Valores',
            'responsaveis': 'Responsáveis',
            'descricoes': 'Descrições',
        }
        
        # Ordem de exibição
        category_order = ['identification', 'partes', 'classificacao', 'pedidos', 'datas', 'valores', 'responsaveis', 'descricoes']
        
        for category in category_order:
            if category in categorized:
                fields = categorized[category]
                if fields:
                    lines.append(f"\n{self.SYMBOLS['list']} {category_labels.get(category, category).upper()}")
                    lines.append(self._get_mini_separator())
                    
                    for field, value in fields.items():
                        symbol = self.SYMBOLS['arrow']
                        formatted_value = self.format_field_value(value)
                        lines.append(f"  {symbol} {field}: {formatted_value}")
        
        # Campos não categorizados
        if uncategorized:
            lines.append(f"\n{self.SYMBOLS['list']} OUTROS")
            lines.append(self._get_mini_separator())
            for field, value in uncategorized.items():
                symbol = self.SYMBOLS['arrow']
                formatted_value = self.format_field_value(value)
                lines.append(f"  {symbol} {field}: {formatted_value}")
        
        # Dados adicionais
        if data.get('outros_dados'):
            outros = data['outros_dados']
            if outros and (show_empty or any(outros.values())):
                lines.append(f"\n{self.SYMBOLS['list']} DADOS ADICIONAIS")
                lines.append(self._get_mini_separator())
                for field, value in outros.items():
                    if show_empty or value:
                        symbol = self.SYMBOLS['arrow']
                        formatted_value = self.format_field_value(value, max_length=60)
                        lines.append(f"  {symbol} {field}: {formatted_value}")
        
        if self.verbosity_level >= self.LEVELS['DETAILED']:
            lines.append(self._get_separator())
        
        return '\n'.join(lines)

    def format_statistics(self, stats: Dict) -> str:
        """Formata estatísticas de execução"""
        lines = []
        
        lines.append(self._get_separator('=', 80))
        lines.append(f"{self.SYMBOLS['star']} ESTATÍSTICAS DE EXECUÇÃO")
        lines.append(self._get_separator('=', 80))
        
        for key, value in stats.items():
            if key == 'inicio':
                try:
                    duracao = datetime.now() - value
                    lines.append(f"{self.SYMBOLS['clock']} Tempo decorrido: {duracao}")
                except:
                    pass
            else:
                symbol = self.SYMBOLS['green'] if 'cadastrados' in key.lower() or 'sucesso' in key.lower() else self.SYMBOLS['warning']
                formatted_key = key.replace('_', ' ').title()
                lines.append(f"{symbol} {formatted_key}: {value}")
        
        lines.append(self._get_separator('=', 80))
        
        return '\n'.join(lines)

    def format_process_info(self, cnj: str, cliente: str, contrario: str, tipo_cadastro: str = None) -> str:
        """Formata informações resumidas de um processo"""
        lines = []
        
        lines.append(self._get_mini_separator())
        if cnj:
            lines.append(f"{self.SYMBOLS['blue']} CNJ: {cnj}")
        if cliente:
            lines.append(f"{self.SYMBOLS['arrow']} Cliente: {cliente}")
        if contrario:
            lines.append(f"{self.SYMBOLS['arrow']} Contrário: {contrario}")
        if tipo_cadastro:
            lines.append(f"{self.SYMBOLS['arrow']} Tipo: {tipo_cadastro}")
        lines.append(self._get_mini_separator())
        
        return '\n'.join(lines)

    def format_error_details(self, error_msg: str, source: str = None) -> str:
        """Formata detalhes de erro"""
        lines = []
        
        lines.append(f"\n{self.SYMBOLS['error']} ERRO DETECTADO")
        lines.append(self._get_mini_separator())
        
        if source:
            lines.append(f"Origem: {source}")
        
        lines.append(f"Mensagem: {error_msg}")
        lines.append(self._get_mini_separator())
        
        return '\n'.join(lines)


class CustomFormatter(logging.Formatter):
    """Formatador customizado para logging com suporte a blocos multi-linha"""

    def __init__(self, formatter: LogFormatter, use_color: bool = True):
        self.log_formatter = formatter
        self.use_color = use_color
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Formata um registro de log"""
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Mapeia o nível de log para símbolo
        level_symbols = {
            'DEBUG': self.log_formatter.SYMBOLS['debug'],
            'INFO': self.log_formatter.SYMBOLS['info'],
            'WARNING': self.log_formatter.SYMBOLS['warning'],
            'ERROR': self.log_formatter.SYMBOLS['error'],
            'CRITICAL': self.log_formatter.SYMBOLS['error'],
        }
        
        symbol = level_symbols.get(record.levelname, '')
        
        # Formata a mensagem
        msg = record.getMessage()
        
        # Para blocos multi-linha, adiciona timestamp apenas na primeira linha
        if '\n' in msg:
            lines = msg.split('\n')
            formatted_lines = [f"[{timestamp}] {symbol} {lines[0]}"]
            for line in lines[1:]:
                if line.strip():
                    formatted_lines.append(f"{'':14} {line}")  # Indentação para alinhar
            return '\n'.join(formatted_lines)
        else:
            return f"[{timestamp}] {symbol} {msg}"


def setup_logging(verbosity: str = 'NORMAL', log_file: str = None, show_empty_fields: bool = False) -> Tuple[logging.Logger, LogFormatter]:
    """Configura o sistema de logging de forma otimizada"""
    
    # Cria o formatador
    formatter = LogFormatter(verbosity_level=verbosity)
    
    # Configura o logger
    logger = logging.getLogger('AutomacaoLegalOne')
    logger.setLevel(logging.DEBUG)
    
    # Remove handlers antigos
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Handler para console (com proteção contra UnicodeEncodeError no Windows)
    try:
        import io
        if hasattr(sys.stdout, 'buffer'):
            console_stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        else:
            console_stream = sys.stdout
    except Exception:
        console_stream = sys.stdout

    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(logging.DEBUG)
    custom_formatter = CustomFormatter(formatter, use_color=True)
    console_handler.setFormatter(custom_formatter)
    logger.addHandler(console_handler)
    
    # Handler para arquivo (se especificado)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = CustomFormatter(formatter, use_color=False)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Não foi possível criar arquivo de log: {e}")
    
    return logger, formatter
