# Módulo para carregar configurações (ex: do .env)
import os
import dotenv
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

# Tenta carregar as variáveis de ambiente do arquivo .env
try:
    dotenv.load_dotenv(encoding='utf-8')
except Exception as e:
    logging.warning(f"Não foi possível carregar o arquivo .env: {e}. Usando valores padrão/hardcoded.")

# === VALORES PADRÃO / HARDCODED (usados se .env falhar ou não definir) ===
DEFAULT_GOOGLE_API_KEY = "AIzaSyCK8kLwIdwK-MKTrt-JEQ5eTQUB_Ryw9ws"
DEFAULT_GEMINI_API_KEY = "AIzaSyB-rrVr5TMdLgFYROocyQRFJ21bONrOjHE"
DEFAULT_CREDENTIALS_PATH = "credentials/credentials.json"
DEFAULT_DRIVE_FOLDER_ID = "15B0tBT8UP6kyl7FxvVmuh4VBYZ9f48UG" # Pasta de Documentos josiel.nascimento@estrelabet.com
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_LAST_SELECTION_FILE = "data/last_selection.json"
# Adicione SPREADSHEET_ID e SHEET_NAME padrão se necessário
# DEFAULT_SPREADSHEET_ID = "SEU_SPREADSHEET_ID_PADRAO"
# DEFAULT_SHEET_NAME = "SEU_SHEET_NAME_PADRAO"
# === FIM VALORES PADRÃO ===

# Configurações da API do Google
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", DEFAULT_GOOGLE_API_KEY)
GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY") # Pode ser None
CREDENTIALS_FILE_PATH = os.getenv("CREDENTIALS_FILE_PATH", DEFAULT_CREDENTIALS_PATH)

# Configurações do Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") # Deixar None se não houver padrão
SHEET_NAME = os.getenv("SHEET_NAME")       # Deixar None se não houver padrão
# RANGE_ABRIL = os.getenv("RANGE_ABRIL", "Abril 2024") # Remover se não usar mais
# RANGE_MAIO = os.getenv("RANGE_MAIO", "Maio 2024")   # Remover se não usar mais

# Configurações do Google Drive
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID)
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json") # Provavelmente redundante com CREDENTIALS_FILE_PATH
FOLDER_ID = os.getenv("FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID) # Pode ser redundante com DRIVE_FOLDER_ID

# Configurações de formatação
TITULO_TAMANHO = int(os.getenv("TITULO_TAMANHO", 17))
SUBTITULOS_ESTILO = os.getenv("SUBTITULOS_ESTILO", "NEGRITO")
# CONTEUDO_COLUNA_DRIVE = os.getenv("CONTEUDO_COLUNA_DRIVE", "L") # Remover se não usar

# Padrão de nome para os arquivos
NOME_ARQUIVO_PADRAO = os.getenv("NOME_ARQUIVO_PADRAO", "{id} - {site} - {ancora}")

# Configurações do Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) # Usa o padrão definido acima
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", 8192))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", 0.3))

# Delay entre chamadas da API Gemini (em segundos)
DELAY_ENTRE_CHAMADAS_GEMINI = float(os.getenv("DELAY_ENTRE_CHAMADAS_GEMINI", 1.0)) # Padrão de 1 segundo

# Preços do Gemini (manter apenas se for usar estimativa de custo)
GEMINI_PRECO_ENTRADA = float(os.getenv("GEMINI_PRECO_ENTRADA", 0.00025))
GEMINI_PRECO_SAIDA = float(os.getenv("GEMINI_PRECO_SAIDA", 0.0005))

# Taxa de Câmbio (pode ser ajustada ou carregada do .env se necessário no futuro)
USD_TO_BRL_RATE = float(os.getenv("USD_TO_BRL_RATE", 5.0)) # Valor padrão de 5.0

# Novo: Mapeamento de nomes de coluna esperados para flexibilizar a leitura de planilhas
# As chaves são os identificadores internos usados pelo script.
# Os valores são listas de possíveis nomes de cabeçalho que podem ser encontrados na planilha.
# A ordem na lista pode indicar preferência, mas o sistema tentará encontrar qualquer um deles.
COLUNAS_MAPEAMENTO_NOMES = {
    'id': {'nomes': ['ID', 'Id', 'id', 'ID da Campanha']},
    'site': {'nomes': ['Site', 'site', 'Website', 'Domínio']},
    'as': {'nomes': ['AS', 'Authority Score', 'AS (Semrush)']},
    'da': {'nomes': ['DA', 'Domain Authority']},
    'trafego': {'nomes': ['Tráfego', 'Trafego', 'Tráfego Estimado', 'Tráfego Estimado (Semrush)']},
    'valor': {'nomes': ['Preço (R$)', 'Preço', 'Valor', 'Custo']},
    'palavra_ancora': {'nomes': ['Âncora', 'Ancora', 'Palavra-chave', 'Palavra Chave', 'Keyword', 'KW']},
    'url_ancora': {'nomes': ['URL de Destino', 'URL Destino', 'Link de Destino', 'URL Âncora', 'URL Ancora', 'URL Alvo']},
    'titulo': {'nomes': ['Tema', 'Título', 'Titulo', 'Título do Artigo', 'Título Gerado']},
    'url_documento': {'nomes': ['Conteúdo (Drive)', 'URL Conteúdo', 'URL Documento', 'Link Documento', 'URL Drive']},
    'observacao': {'nomes': ['Observação', 'Observacoes', 'Obs', 'Comentários']},
    'url_publicada': {'nomes': ['URL Publicada', 'Link Publicado', 'URL Final']},
    'data_publicacao': {'nomes': ['Data Publicação', 'YYYY/MM', 'Data Prevista', 'Mês/Ano']}
}

# Configurações de colunas da planilha (ajustado conforme a estrutura real da planilha)
# COLUNAS = {
#     'id': 0,                 # A - ID
#     'site': 1,               # B - Site
#     'as': 2,                 # C - AS
#     'da': 3,                 # D - DA
#     'trafego': 4,            # E - Tráfego
#     'valor': 5,               # F - Preço (R$)
#     'palavra_ancora': 6,     # G - Âncora
#     'url_ancora': 7,         # H - URL de Destino
#     'titulo': 8,             # I - Tema
#     'url_documento': 9,      # J - Conteúdo (Drive)
#     'observacao': 11,        # L - Observação
#     'url_publicada': 12      # M - URL Publicada
# }

# Dicionário com nomes de meses
MESES = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro"
}

# Configurações de filtragem
# LINHA_INICIAL = 0       # Inicia da primeira linha (antes era 674)

# Função para gerar o nome do arquivo
def gerar_nome_arquivo(id: str, site: str, ancora: str, titulo: Optional[str] = None) -> str:
    """
    Gera um nome de arquivo baseado nos parâmetros fornecidos e no padrão definido no .env.
    
    Args:
        id: ID da campanha ou linha da planilha
        site: Nome do site
        ancora: Palavra âncora
        titulo: Título opcional
        
    Returns:
        Nome de arquivo formatado
    """
    # Substitui caracteres inválidos em nomes de arquivo
    ancora_sanitizada = re.sub(r'[\\/:"*?<>|]+', '_', ancora)
    
    # Aplica o padrão definido no .env
    nome = NOME_ARQUIVO_PADRAO.format(
        id=id,
        site=site,
        ancora=ancora_sanitizada,
        titulo=titulo if titulo else ''
    )
    
    return nome.strip()

# Função para estimar custos do Gemini
def estimar_custo_gemini(tokens_entrada: int, tokens_saida: int) -> float:
    """
    Estima o custo de uso do Gemini com base nos tokens de entrada e saída.
    
    Args:
        tokens_entrada: Número de tokens de entrada (prompt)
        tokens_saida: Número de tokens de saída (resposta)
        
    Returns:
        Custo estimado em USD
    """
    custo_entrada = (tokens_entrada / 1000) * GEMINI_PRECO_ENTRADA
    custo_saida = (tokens_saida / 1000) * GEMINI_PRECO_SAIDA
    return custo_entrada + custo_saida 

# Configuração do arquivo de última seleção
LAST_SELECTION_FILE = os.getenv("LAST_SELECTION_FILE", DEFAULT_LAST_SELECTION_FILE) 

@dataclass
class Config:
    # API Settings
    GEMINI_MAX_OUTPUT_TOKENS: int = 2048
    DELAY_ENTRE_CHAMADAS_GEMINI: float = 1.0
    USD_TO_BRL_RATE: float = 5.0
    GEMINI_TEMPERATURE: float = 0.3
    
    # File Paths
    BASE_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    LOGS_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs")
    DATA_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data")
    CREDENTIALS_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent / "credentials")
    LAST_SELECTION_FILE: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "last_selection.json")
    
    # Google Services
    SPREADSHEET_ID: str = ""
    SHEET_NAME: str = "Sheet1"
    DRIVE_FOLDER_ID: str = ""
    GOOGLE_API_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", "AIzaSyCK8kLwIdwK-MKTrt-JEQ5eTQUB_Ryw9ws"))
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "AIzaSyB-rrVr5TMdLgFYROocyQRFJ21bONrOjHE"))
    CREDENTIALS_FILE_PATH: str = field(default_factory=lambda: os.getenv("CREDENTIALS_FILE_PATH", "credentials/credentials.json"))
    
    # Processing Settings
    MESES: Dict[str, str] = field(default_factory=lambda: {
        "01": "janeiro", "02": "fevereiro", "03": "março",
        "04": "abril", "05": "maio", "06": "junho",
        "07": "julho", "08": "agosto", "09": "setembro",
        "10": "outubro", "11": "novembro", "12": "dezembro"
    })
    
    # Column Mappings
    DEFAULT_COLUMN_MAP: Dict[str, Any] = field(default_factory=lambda: {
        "id": "ID",
        "titulo": "Título",
        "conteudo": "Conteúdo",
        "palavra_ancora": "Palavra-âncora",
        "url_ancora": "URL da âncora"
    })
    
    # Gemini Settings
    GEMINI_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    GEMINI_PRECO_ENTRADA: float = field(default_factory=lambda: float(os.getenv("GEMINI_PRECO_ENTRADA", "0.00025")))
    GEMINI_PRECO_SAIDA: float = field(default_factory=lambda: float(os.getenv("GEMINI_PRECO_SAIDA", "0.0005")))
    
    # File Naming
    NOME_ARQUIVO_PADRAO: str = field(default_factory=lambda: os.getenv("NOME_ARQUIVO_PADRAO", "{id} - {site} - {ancora}"))
    
    @classmethod
    def load_from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        config = cls()
        
        # Load from environment variables if they exist
        if os.getenv('GEMINI_MAX_OUTPUT_TOKENS'):
            config.GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv('GEMINI_MAX_OUTPUT_TOKENS'))
        if os.getenv('DELAY_ENTRE_CHAMADAS_GEMINI'):
            config.DELAY_ENTRE_CHAMADAS_GEMINI = float(os.getenv('DELAY_ENTRE_CHAMADAS_GEMINI'))
        if os.getenv('USD_TO_BRL_RATE'):
            config.USD_TO_BRL_RATE = float(os.getenv('USD_TO_BRL_RATE'))
        if os.getenv('SPREADSHEET_ID'):
            config.SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
        if os.getenv('SHEET_NAME'):
            config.SHEET_NAME = os.getenv('SHEET_NAME')
        if os.getenv('DRIVE_FOLDER_ID'):
            config.DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
        if os.getenv('GEMINI_TEMPERATURE'):
            config.GEMINI_TEMPERATURE = float(os.getenv('GEMINI_TEMPERATURE'))
            
        return config

def gerar_nome_arquivo(tipo: str, palavra_ancora: str) -> str:
    """Generate a standardized filename based on type and anchor word"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{tipo}_{palavra_ancora}_{timestamp}.txt"

def estimar_custo_gemini(tokens_input: int, tokens_output: int) -> float:
    """Estimate the cost of a Gemini API call in USD"""
    config = Config.load_from_env()
    input_cost = (tokens_input / 1000) * config.GEMINI_PRECO_ENTRADA
    output_cost = (tokens_output / 1000) * config.GEMINI_PRECO_SAIDA
    return input_cost + output_cost

# Create a global config instance
config = Config.load_from_env() 