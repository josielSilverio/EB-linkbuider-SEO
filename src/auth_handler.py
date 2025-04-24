# Módulo para lidar com a autenticação das APIs do Google
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import logging

from src.config import CREDENTIALS_FILE_PATH

# Se modifica essas permissões, delete o arquivo token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',           # Ler e escrever nas planilhas
    'https://www.googleapis.com/auth/documents',              # Criar e editar documentos
    'https://www.googleapis.com/auth/drive.file',             # Acessar arquivos criados pelo app
    'https://www.googleapis.com/auth/drive',                  # Acesso completo aos arquivos e metadados do Drive
    'https://www.googleapis.com/auth/drive.metadata.readonly' # Ler metadados dos arquivos do Drive
]

def obter_credenciais():
    """
    Obtém as credenciais do OAuth para acessar as APIs do Google.
    Fluxo:
    1. Verifica se há um token.json
    2. Se token.json existir e for válido, usa esse token
    3. Se token.json existir mas estiver expirado, atualiza o token
    4. Se token.json não existir, abre o navegador para autorização
    """
    creds = None
    token_path = 'credentials/token.json'
    
    # Verifica se já existe um arquivo de token
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_info(
                json.load(open(token_path, 'r')), SCOPES)
        except Exception as e:
            logging.warning(f"Erro ao carregar token existente: {e}")
    
    # Se não há credenciais ou elas estão inválidas
    if not creds or not creds.valid:
        # Se as credenciais estão expiradas mas têm refresh token
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Erro ao atualizar token: {e}")
                # Se falhar o refresh, realizamos uma nova autenticação
                creds = nova_autenticacao()
        else:
            # Caso não tenha credenciais ou não seja possível atualizar
            creds = nova_autenticacao()
        
        # Salva as credenciais para a próxima execução
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    
    return creds

def nova_autenticacao():
    """
    Realiza o fluxo de autenticação OAuth completo.
    """
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE_PATH, SCOPES)
        creds = flow.run_local_server(port=8080)
        return creds
    except Exception as e:
        logging.error(f"Erro durante autenticação: {e}")
        raise Exception(f"Falha na autenticação OAuth: {e}")

def criar_servico_sheets(creds):
    """
    Cria e retorna um serviço para interagir com o Google Sheets.
    """
    try:
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Erro ao criar serviço do Sheets: {e}")
        raise Exception(f"Falha ao criar serviço do Sheets: {e}")

def criar_servico_docs(creds):
    """
    Cria e retorna um serviço para interagir com o Google Docs.
    """
    try:
        service = build('docs', 'v1', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Erro ao criar serviço do Docs: {e}")
        raise Exception(f"Falha ao criar serviço do Docs: {e}")

def criar_servico_drive(creds):
    """
    Cria e retorna um serviço para interagir com o Google Drive.
    """
    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Erro ao criar serviço do Drive: {e}")
        raise Exception(f"Falha ao criar serviço do Drive: {e}") 