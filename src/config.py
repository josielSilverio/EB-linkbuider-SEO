# Módulo para carregar configurações (ex: do .env)
import os
import dotenv
from datetime import datetime

# Carrega as variáveis de ambiente do arquivo .env
dotenv.load_dotenv()

# Configurações da API do Google
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY")
CREDENTIALS_FILE_PATH = os.getenv("CREDENTIALS_FILE_PATH")

# Configurações do Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME")

# Configurações do Google Drive
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")

# Configurações de formatação
TITULO_TAMANHO = int(os.getenv("TITULO_TAMANHO", 17))
SUBTITULOS_ESTILO = os.getenv("SUBTITULOS_ESTILO", "NEGRITO")
CONTEUDO_COLUNA_DRIVE = os.getenv("CONTEUDO_COLUNA_DRIVE", "L")

# Padrão de nome para os arquivos
NOME_ARQUIVO_PADRAO = os.getenv("NOME_ARQUIVO_PADRAO", "{id} - {site} - {ancora} - {titulo}")

# Constantes para o Gemini
GEMINI_MODEL = "gemini-1.5-flash"  # Opções: gemini-1.5-flash, gemini-1.5-pro
GEMINI_MAX_OUTPUT_TOKENS = 8192
GEMINI_TEMPERATURE = 0.7

# Configurações de colunas da planilha (ajustado com base na estrutura real)
COLUNAS = {
    "ID": 1,               # Coluna B (índice 1 no DataFrame)
    "DATA": 2,             # Coluna C (índice 2 no DataFrame)
    "TEMA": 13,            # Coluna N (índice 13 no DataFrame) 
    "SITE": 3,             # Coluna D (índice 3 no DataFrame)
    "PALAVRA_ANCORA": 8,   # Coluna I (índice 8 no DataFrame)
    "URL_ANCORA": 9,       # Coluna J (índice 9 no DataFrame)
    "TITULO": 10,          # Coluna K (índice 10 no DataFrame)
    "CONTEUDO_DRIVE": "L"  # Para atualização, mantém o formato de letra
}

# Configurações de filtragem
LINHA_INICIAL = 675       # Linha inicial para processamento
MES_ATUAL = "04"          # Abril (formato: MM)
ANO_ATUAL = "2024"        # Ano atual (formato: YYYY)

# Função para gerar o nome do arquivo
def gerar_nome_arquivo(id, site, ancora, titulo=None):
    """
    Gera o nome do arquivo seguindo o padrão definido no .env
    Formato simplificado: ID - Site - âncora
    """
    # Substitui caracteres inválidos para nomes de arquivo
    ancora_seguro = ancora.replace('/', '-').replace('\\', '-').replace(':', '-')
    
    # Usa o formato definido no .env (que não inclui mais o título)
    return NOME_ARQUIVO_PADRAO.format(
        id=id,
        site=site,
        ancora=ancora_seguro
    )

# Função para estimar custos do Gemini
def estimar_custo_gemini(tokens_entrada, tokens_saida):
    """
    Estima o custo em USD com base nos tokens de entrada e saída
    Para o Gemini 1.5 Flash (valores de maio/2024)
    Entrada: $0.00035 / 1K tokens
    Saída: $0.00105 / 1K tokens
    """
    custo_entrada = (tokens_entrada / 1000) * 0.00035
    custo_saida = (tokens_saida / 1000) * 0.00105
    return custo_entrada + custo_saida 