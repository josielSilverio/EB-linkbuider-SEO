# Módulo para carregar configurações (ex: do .env)
import os
import dotenv
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import re
import logging

# Tenta carregar as variáveis de ambiente do arquivo .env
try:
    dotenv.load_dotenv(encoding='utf-8')
except Exception as e:
    logging.warning(f"Não foi possível carregar o arquivo .env: {e}. Usando valores padrão/hardcoded.")

# === VALORES PADRÃO / HARDCODED (usados se .env falhar ou não definir) ===
DEFAULT_GOOGLE_API_KEY = "AIzaSyCK8kLwIdwK-MKTrt-JEQ5eTQUB_Ryw9ws"
DEFAULT_GEMINI_API_KEY = "AIzaSyB-rrVr5TMdLgFYROocyQRFJ21bONrOjHE"
DEFAULT_CREDENTIALS_PATH = "credentials/credentials.json"
DEFAULT_DRIVE_FOLDER_ID = "1kYydkHTzlkAujferCVU5NXnnlxvVsB4j"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
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

# Preços do Gemini (manter apenas se for usar estimativa de custo)
GEMINI_PRECO_ENTRADA = float(os.getenv("GEMINI_PRECO_ENTRADA", 0.00025))
GEMINI_PRECO_SAIDA = float(os.getenv("GEMINI_PRECO_SAIDA", 0.0005))

# Configurações de colunas da planilha (ajustado conforme a estrutura real da planilha)
COLUNAS = {
    'id': 0,                 # A - ID
    'site': 1,               # B - Site
    'as': 2,                 # C - AS
    'da': 3,                 # D - DA
    'trafego': 4,            # E - Tráfego
    'valor': 5,              # F - Preço (R$)
    'palavra_ancora': 6,     # G - Âncora
    'url_ancora': 7,         # H - URL de Destino
    'titulo': 8,             # I - Tema 
    'url_documento': 9,      # J - Conteúdo (Drive)
    'observacao': 11,        # L - Observação
    'url_publicada': 12      # M - URL Publicada
}

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
LINHA_INICIAL = 0       # Inicia da primeira linha (antes era 674)

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