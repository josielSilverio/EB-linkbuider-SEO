# Módulo para carregar configurações (ex: do .env)
import os
import dotenv
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import re

# Carrega as variáveis de ambiente do arquivo .env
dotenv.load_dotenv()

# Configurações da API do Google
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY")
CREDENTIALS_FILE_PATH = os.getenv("CREDENTIALS_FILE_PATH")

# Configurações do Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME")
RANGE_ABRIL = os.getenv("RANGE_ABRIL", "Abril 2024")
RANGE_MAIO = os.getenv("RANGE_MAIO", "Maio 2024")

# Configurações do Google Drive
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credenciais.json")
FOLDER_ID = os.getenv("FOLDER_ID")

# Configurações de formatação
TITULO_TAMANHO = int(os.getenv("TITULO_TAMANHO", 17))
SUBTITULOS_ESTILO = os.getenv("SUBTITULOS_ESTILO", "NEGRITO")
CONTEUDO_COLUNA_DRIVE = os.getenv("CONTEUDO_COLUNA_DRIVE", "L")

# Padrão de nome para os arquivos
NOME_ARQUIVO_PADRAO = os.getenv("NOME_ARQUIVO_PADRAO", "{id} - {site} - {ancora}")

# Configurações do Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))

# Preços do Gemini por milhão de tokens (em USD)
GEMINI_PRECO_ENTRADA = float(os.getenv("GEMINI_PRECO_ENTRADA", "0.00025"))  # $0.00025 por 1K tokens de entrada
GEMINI_PRECO_SAIDA = float(os.getenv("GEMINI_PRECO_SAIDA", "0.0005"))      # $0.0005 por 1K tokens de saída

# Configurações de colunas da planilha (ajustado com base na estrutura real)
COLUNAS = {
    'id': 1,                 # B
    'data': 2,               # C 
    'site': 3,               # D
    'quantidade_palavras': 5, # F
    'valor': 7,              # H
    'palavra_ancora': 8,     # I
    'url_ancora': 9,         # J
    'titulo': 10,            # K
    'url_documento': 11,     # L
    'tema': None,            # Não tem coluna de tema na estrutura atual
}

# Configurações de filtragem
LINHA_INICIAL = 674       # Linha inicial para processamento
MES_ATUAL = os.getenv('MES_ATUAL', '04')  # Mês atual no formato MM
ANO_ATUAL = os.getenv('ANO_ATUAL', '2025')  # Ano atual no formato YYYY
FORMATO_DATA = os.getenv('FORMATO_DATA', 'yyyy/mm')  # Formato: yyyy/mm, mm/yyyy, ou mm-yyyy

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