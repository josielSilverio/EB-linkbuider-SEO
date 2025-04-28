#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script para testar o acesso ao Google Drive e verificar se uma pasta específica existe
"""

import os
import sys
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.auth_handler import obter_credenciais
from src.config import DRIVE_FOLDER_ID

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('drive_test')

def testar_acesso_drive(folder_id=DRIVE_FOLDER_ID):
    """
    Testa se é possível acessar a pasta especificada no Google Drive.
    
    Args:
        folder_id: ID da pasta para testar
    """
    logger.info(f"Testando acesso ao Google Drive para a pasta com ID: {folder_id}")
    
    try:
        # Obtém credenciais
        credenciais = obter_credenciais()
        logger.info("✓ Credenciais obtidas com sucesso")
        
        # Cria o serviço do Google Drive
        service = build('drive', 'v3', credentials=credenciais)
        logger.info("✓ Serviço do Google Drive criado com sucesso")
        
        # Tenta obter informações sobre a pasta
        pasta = service.files().get(
            fileId=folder_id,
            fields='id,name,mimeType,capabilities,owners,shared,parents,teamDriveId',
            supportsAllDrives=True
        ).execute()
        
        logger.info("✓ Pasta encontrada no Google Drive:")
        logger.info(f"  - Nome: {pasta.get('name', 'N/A')}")
        logger.info(f"  - ID: {pasta.get('id', 'N/A')}")
        logger.info(f"  - Tipo: {pasta.get('mimeType', 'N/A')}")
        logger.info(f"  - É compartilhada: {pasta.get('shared', False)}")
        logger.info(f"  - TeamDrive ID: {pasta.get('teamDriveId', 'Não é um shared drive')}")
        
        # Verificar capacidades do usuário na pasta
        capacidades = pasta.get('capabilities', {})
        logger.info("  - Capacidades do usuário nesta pasta:")
        for cap, valor in capacidades.items():
            logger.info(f"    * {cap}: {valor}")
        
        # Verificar se é realmente uma pasta
        if pasta.get('mimeType') != 'application/vnd.google-apps.folder':
            logger.warning(f"⚠️ O ID {folder_id} não é uma pasta! É um: {pasta.get('mimeType')}")
            return False
        
        # Listar arquivos na pasta
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            pageSize=10,
            fields="nextPageToken, files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            logger.info("✓ A pasta existe mas está vazia")
        else:
            logger.info(f"✓ A pasta contém {len(items)} item(s):")
            for item in items:
                logger.info(f"  - {item['name']} ({item['mimeType']})")
        
        # Testar criação de um arquivo de teste
        logger.info("Tentando criar um documento de teste na pasta...")
        file_metadata = {
            'name': 'Teste de acesso ao Drive',
            'mimeType': 'application/vnd.google-apps.document',
            'parents': [folder_id]
        }
        
        arquivo = service.files().create(
            body=file_metadata,
            fields='id,name,webViewLink',
            supportsAllDrives=True
        ).execute()
        
        logger.info(f"✓ Documento de teste criado com sucesso:")
        logger.info(f"  - Nome: {arquivo.get('name')}")
        logger.info(f"  - ID: {arquivo.get('id')}")
        logger.info(f"  - Link: {arquivo.get('webViewLink', 'N/A')}")
        
        # Limpar arquivo de teste após verificação
        logger.info("Removendo documento de teste...")
        service.files().delete(
            fileId=arquivo.get('id'),
            supportsAllDrives=True
        ).execute()
        
        logger.info("✓ Documento de teste removido")
        
        return True
    
    except HttpError as error:
        logger.error(f"❌ Erro ao acessar o Google Drive: {error}")
        logger.error(f"Detalhes do erro: {error.content.decode('utf-8')}")
        return False
    
    except Exception as e:
        logger.error(f"❌ Erro inesperado: {e}")
        return False

if __name__ == "__main__":
    # Permite passar um ID de pasta como argumento
    folder_id = sys.argv[1] if len(sys.argv) > 1 else DRIVE_FOLDER_ID
    
    print(f"\n==== TESTANDO ACESSO AO GOOGLE DRIVE ====")
    print(f"ID da pasta: {folder_id}\n")
    
    if testar_acesso_drive(folder_id):
        print("\n✅ TESTE CONCLUÍDO COM SUCESSO: A pasta existe e você tem acesso a ela.")
    else:
        print("\n❌ TESTE FALHOU: Verifique os logs acima para mais detalhes.") 