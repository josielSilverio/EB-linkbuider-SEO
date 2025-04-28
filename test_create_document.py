#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script para testar a criação de um documento no Google Drive
"""

import logging
from src.docs_handler import DocsHandler
from src.config import DRIVE_FOLDER_ID

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_create_doc')

def testar_criacao_documento():
    """
    Testa a criação de um documento no Google Drive.
    """
    # Conteúdo de exemplo para o documento
    titulo = "Documento de Teste SEO-LinkBuilder"
    conteudo = f"""# {titulo}

Este é um documento de teste gerado pelo sistema SEO-LinkBuilder.

## Teste de Formatação

Este documento serve para testar a criação e movimentação de documentos 
para pastas específicas no Google Drive.

## Características do Teste

- Criação de documentos
- Formatação do conteúdo
- Movimentação para pasta específica
- Tratamento de erros

## Resultado Esperado

O documento deve ser criado e movido para a pasta correta no Google Drive,
ou para uma nova pasta criada automaticamente caso a pasta configurada não exista.
"""
    
    nome_arquivo = "Teste - Documento SEO-LinkBuilder"
    
    logger.info("Inicializando o DocsHandler...")
    docs_handler = DocsHandler()
    
    logger.info(f"Tentando criar documento '{nome_arquivo}' e salvá-lo na pasta configurada...")
    logger.info(f"ID da pasta configurada: {DRIVE_FOLDER_ID}")
    
    try:
        document_id, document_url = docs_handler.criar_documento(
            titulo=titulo,
            conteudo=conteudo,
            nome_arquivo=nome_arquivo
        )
        
        logger.info("✅ Documento criado com sucesso!")
        logger.info(f"ID do documento: {document_id}")
        logger.info(f"URL do documento: {document_url}")
        logger.info("Verifique se o documento foi criado corretamente no Google Drive.")
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar o documento: {e}")

if __name__ == "__main__":
    print("\n==== TESTANDO CRIAÇÃO DE DOCUMENTO ====\n")
    testar_criacao_documento()
    print("\n==== TESTE CONCLUÍDO ====\n") 