#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script para corrigir as permissões de documentos existentes no Google Drive
"""

import os
import sys
import logging
from typing import List, Dict, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.auth_handler import obter_credenciais
from src.config import DRIVE_FOLDER_ID

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_permissions')

def listar_documentos_pasta(service, folder_id: str) -> List[Dict[str, Any]]:
    """
    Lista todos os documentos em uma pasta do Google Drive.
    
    Args:
        service: Serviço do Google Drive
        folder_id: ID da pasta a listar
        
    Returns:
        Lista de dicionários com informações dos documentos
    """
    try:
        # Consulta para encontrar todos os documentos na pasta
        query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document'"
        
        results = service.files().list(
            q=query,
            pageSize=100,  # Ajuste conforme necessário
            fields="nextPageToken, files(id, name, webViewLink, permissions)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return results.get('files', [])
        
    except HttpError as error:
        logger.error(f"Erro ao listar documentos da pasta {folder_id}: {error}")
        return []

def corrigir_permissoes_documento(service, file_id: str) -> bool:
    """
    Corrige as permissões de um documento para permitir acesso via link.
    
    Args:
        service: Serviço do Google Drive
        file_id: ID do documento
        
    Returns:
        True se as permissões foram atualizadas com sucesso, False caso contrário
    """
    try:
        # Verifica permissões atuais
        file_info = service.files().get(
            fileId=file_id,
            fields='name,permissions',
            supportsAllDrives=True
        ).execute()
        
        nome_arquivo = file_info.get('name', 'Documento sem nome')
        
        # Define permissão para qualquer pessoa com o link poder visualizar
        permission = {
            'type': 'anyone',
            'role': 'reader',
            'allowFileDiscovery': False
        }
        
        # Verifica se já existe uma permissão similar
        permissoes_existentes = file_info.get('permissions', [])
        for perm in permissoes_existentes:
            if perm.get('type') == 'anyone' and perm.get('role') == 'reader':
                logger.info(f"Documento '{nome_arquivo}' já possui permissão de acesso via link")
                return True
        
        # Adiciona a nova permissão
        result = service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id',
            sendNotificationEmail=False
        ).execute()
        
        logger.info(f"Permissão de acesso via link adicionada ao documento '{nome_arquivo}'")
        return True
        
    except HttpError as error:
        logger.error(f"Erro ao corrigir permissões do documento {file_id}: {error}")
        return False

def corrigir_permissoes_pasta(folder_id: str) -> int:
    """
    Corrige as permissões de todos os documentos em uma pasta.
    
    Args:
        folder_id: ID da pasta a processar
        
    Returns:
        Número de documentos corrigidos
    """
    try:
        # Obtém credenciais
        credenciais = obter_credenciais()
        logger.info("✓ Credenciais obtidas com sucesso")
        
        # Cria o serviço do Google Drive
        service = build('drive', 'v3', credentials=credenciais)
        logger.info("✓ Serviço do Google Drive criado com sucesso")
        
        # Verifica se a pasta existe
        try:
            pasta = service.files().get(
                fileId=folder_id,
                fields='name,mimeType',
                supportsAllDrives=True
            ).execute()
            
            # Verifica se é uma pasta
            if pasta.get('mimeType') != 'application/vnd.google-apps.folder':
                logger.error(f"O ID {folder_id} não corresponde a uma pasta!")
                return 0
                
            logger.info(f"Processando pasta: {pasta.get('name')} (ID: {folder_id})")
            
        except HttpError:
            logger.error(f"A pasta com ID {folder_id} não existe ou você não tem acesso a ela")
            return 0
        
        # Lista todos os documentos na pasta
        documentos = listar_documentos_pasta(service, folder_id)
        
        if not documentos:
            logger.warning(f"Nenhum documento encontrado na pasta {folder_id}")
            return 0
            
        logger.info(f"Encontrados {len(documentos)} documentos para processar")
        
        # Processa cada documento
        documentos_corrigidos = 0
        for doc in documentos:
            doc_id = doc.get('id')
            doc_nome = doc.get('name')
            
            logger.info(f"Processando documento: {doc_nome} (ID: {doc_id})")
            
            if corrigir_permissoes_documento(service, doc_id):
                documentos_corrigidos += 1
        
        return documentos_corrigidos
        
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        return 0

def verificar_pastas_recentes():
    """
    Verifica e lista pastas recentes no Google Drive relacionadas ao SEO-LinkBuilder.
    
    Returns:
        Lista de IDs de pastas encontradas
    """
    try:
        # Obtém credenciais
        credenciais = obter_credenciais()
        
        # Cria o serviço do Google Drive
        service = build('drive', 'v3', credentials=credenciais)
        
        # Busca pastas criadas pelo aplicativo
        query = "mimeType = 'application/vnd.google-apps.folder' and name contains 'SEO-LinkBuilder'"
        
        results = service.files().list(
            q=query,
            pageSize=10,
            fields="nextPageToken, files(id, name, createdTime, webViewLink)"
        ).execute()
        
        pastas = results.get('files', [])
        
        if not pastas:
            logger.info("Nenhuma pasta SEO-LinkBuilder encontrada recentemente")
            return []
            
        logger.info(f"Encontradas {len(pastas)} pastas SEO-LinkBuilder:")
        
        pasta_ids = []
        for pasta in pastas:
            logger.info(f"  - {pasta.get('name')} (ID: {pasta.get('id')})")
            logger.info(f"    Criada em: {pasta.get('createdTime')}")
            logger.info(f"    Link: {pasta.get('webViewLink')}")
            pasta_ids.append(pasta.get('id'))
            
        return pasta_ids
        
    except Exception as e:
        logger.error(f"Erro ao verificar pastas recentes: {e}")
        return []

if __name__ == "__main__":
    print("\n==== CORREÇÃO DE PERMISSÕES DE DOCUMENTOS ====\n")
    
    if len(sys.argv) > 1:
        # Usar o ID da pasta fornecido como argumento
        folder_id = sys.argv[1]
        print(f"Usando o ID de pasta fornecido: {folder_id}")
    else:
        # Utilizar o ID configurado por padrão
        folder_id = DRIVE_FOLDER_ID
        
        # Verificar se o usuário quer ver pastas recentes
        resposta = input("Deseja verificar pastas SEO-LinkBuilder recentes? (S/N): ")
        if resposta.lower() in ('s', 'sim', 'y', 'yes'):
            print("\nBuscando pastas SEO-LinkBuilder recentes...\n")
            pastas_recentes = verificar_pastas_recentes()
            
            if pastas_recentes:
                print("\nPastas encontradas. Deseja processar uma pasta específica?")
                print("Digite o número da pasta ou 'P' para processar a pasta padrão:")
                
                for i, pasta_id in enumerate(pastas_recentes, 1):
                    print(f"{i}) {pasta_id}")
                print(f"P) Usar pasta padrão: {folder_id}")
                
                escolha = input("\nSua escolha: ")
                
                if escolha.lower() == 'p':
                    # Continuar com a pasta padrão
                    pass
                elif escolha.isdigit() and 1 <= int(escolha) <= len(pastas_recentes):
                    folder_id = pastas_recentes[int(escolha) - 1]
                    print(f"Usando pasta selecionada: {folder_id}")
                else:
                    print("Escolha inválida. Usando pasta padrão.")
    
    print(f"\nProcessando pasta com ID: {folder_id}\n")
    
    # Corrige as permissões dos documentos
    docs_corrigidos = corrigir_permissoes_pasta(folder_id)
    
    print(f"\n✅ {docs_corrigidos} documentos processados e corrigidos com sucesso!")
    print("\nAgora os documentos devem estar acessíveis via link sem necessidade de solicitar permissão.")
    print("\n==== PROCESSAMENTO CONCLUÍDO ====\n") 