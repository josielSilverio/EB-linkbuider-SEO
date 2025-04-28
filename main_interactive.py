#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Versão interativa do gerador de documentos para SEO LinkBuilder
Permite escolher a pasta de destino no Google Drive antes de executar
"""

import os
import sys
import logging
import datetime
from typing import Optional, List, Dict, Any

from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler
from src.docs_handler import DocsHandler
from src.config import DRIVE_FOLDER_ID, estimar_custo_gemini

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('seo_linkbuilder')

def selecionar_pasta_destino() -> str:
    """
    Pergunta ao usuário qual pasta do Google Drive usar para salvar os documentos.
    
    Returns:
        ID da pasta de destino
    """
    print("\n==== SELEÇÃO DE PASTA DE DESTINO ====\n")
    print("Onde você deseja salvar os documentos gerados?")
    print("1) Usar pasta padrão configurada no sistema")
    print("2) Criar uma nova pasta com a data e hora atual")
    print("3) Informar URL ou ID de uma pasta específica do Google Drive")
    
    while True:
        opcao = input("\nEscolha uma opção (1-3): ").strip()
        
        if opcao in ['1', '2', '3']:
            break
        else:
            print("Opção inválida! Por favor, digite 1, 2 ou 3.")
    
    # Obtém instância do manipulador de documentos
    docs_handler = DocsHandler()
    
    if opcao == '1':
        print(f"\nUsando pasta padrão: {DRIVE_FOLDER_ID}")
        return DRIVE_FOLDER_ID
    
    elif opcao == '2':
        # Criar pasta com data e hora
        agora = datetime.datetime.now()
        data_hora = agora.strftime("%Y-%m-%d_%H-%M-%S")
        nome_pasta = f"SEO-LinkBuilder_{data_hora}"
        
        print(f"\nCriando nova pasta: {nome_pasta}")
        
        # Cria metadados da pasta
        file_metadata = {
            'name': nome_pasta,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # Cria a pasta
        try:
            pasta = docs_handler.service_drive.files().create(
                body=file_metadata,
                fields='id,name,webViewLink'
            ).execute()
            
            pasta_id = pasta.get('id')
            print(f"Pasta criada com sucesso!")
            print(f"Nome: {pasta.get('name')}")
            print(f"ID: {pasta_id}")
            print(f"Link: {pasta.get('webViewLink')}")
            
            return pasta_id
            
        except Exception as e:
            print(f"Erro ao criar pasta: {e}")
            print("Usando pasta padrão como alternativa.")
            return DRIVE_FOLDER_ID
    
    elif opcao == '3':
        # Solicitar URL ou ID
        url_input = input("\nInforme a URL ou ID da pasta do Google Drive: ")
        
        # Extrai o ID da URL
        pasta_id = docs_handler.extrair_id_da_url(url_input)
        
        if not pasta_id:
            print("Não foi possível extrair um ID válido da entrada fornecida.")
            print("Usando pasta padrão como alternativa.")
            return DRIVE_FOLDER_ID
        
        # Verifica se a pasta existe
        try:
            pasta = docs_handler.service_drive.files().get(
                fileId=pasta_id,
                fields='id,name,mimeType',
                supportsAllDrives=True
            ).execute()
            
            # Verifica se é uma pasta
            if pasta.get('mimeType') != 'application/vnd.google-apps.folder':
                print(f"AVISO: O ID {pasta_id} não corresponde a uma pasta!")
                confirmacao = input("Deseja continuar mesmo assim? (S/N): ")
                if confirmacao.lower() not in ('s', 'sim', 'y', 'yes'):
                    print("Operação cancelada. Usando pasta padrão.")
                    return DRIVE_FOLDER_ID
            
            print(f"\nPasta selecionada: {pasta.get('name')} (ID: {pasta_id})")
            return pasta_id
            
        except Exception as e:
            print(f"Erro ao verificar a pasta: {e}")
            print("A pasta pode não existir ou você não tem acesso a ela.")
            print("Usando pasta padrão como alternativa.")
            return DRIVE_FOLDER_ID
    
    else:
        print("Opção inválida. Usando pasta padrão.")
        return DRIVE_FOLDER_ID

def main():
    """Função principal do programa"""
    print("\n====== SEO LinkBuilder - Gerador de Conteúdo ======\n")
    
    # Solicita a pasta de destino
    folder_id = selecionar_pasta_destino()
    
    # Confirma antes de prosseguir
    print("\nO programa irá gerar conteúdos e salvá-los na pasta especificada.")
    confirmacao = input("Deseja continuar? (S/N): ")
    
    if confirmacao.lower() not in ('s', 'sim', 'y', 'yes'):
        print("\nOperação cancelada pelo usuário.")
        return
    
    # Inicializa contadores e métricas
    total_tokens_entrada = 0
    total_tokens_saida = 0
    total_artigos = 0
    
    try:
        # Inicializa os handlers
        sheets_handler = SheetsHandler()
        gemini_handler = GeminiHandler()
        docs_handler = DocsHandler()
        
        # Busca os dados da planilha
        linhas = sheets_handler.buscar_dados()
        logger.info(f"Obtidas {len(linhas)} linhas de dados da planilha")
        
        # Itera sobre as linhas de dados
        for linha in linhas:
            try:
                # Gera o conteúdo usando Gemini
                prompt, conteudo, tokens_entrada, tokens_saida = gemini_handler.gerar_conteudo(linha)
                
                # Atualiza contadores
                total_tokens_entrada += tokens_entrada
                total_tokens_saida += tokens_saida
                total_artigos += 1
                
                # Gera nome e cria documento
                nome_arquivo = f"{linha['id']} - {linha['site']} - {linha['palavra_ancora']}"
                info_link = {'palavra': linha['palavra_ancora'], 'url': linha['url_ancora']}
                
                document_id, document_url = docs_handler.criar_documento(
                    titulo=linha['titulo'],
                    conteudo=conteudo,
                    nome_arquivo=nome_arquivo,
                    info_link=info_link,
                    target_folder_id=folder_id  # Usa a pasta selecionada pelo usuário
                )
                
                # Atualiza a URL do documento na planilha
                sheets_handler.atualizar_url_documento(linha['linha_indice'], document_url)
                
                logger.info(f"Documento criado: {document_url}")
                print(f"✓ Criado: {nome_arquivo}")
                
            except Exception as e:
                logger.error(f"Erro ao processar linha {linha['id']}: {e}")
                print(f"✗ Erro ao processar: {linha['id']} - {e}")
    
    except Exception as e:
        logger.error(f"Erro geral na execução: {e}")
        print(f"\nErro: {e}")
    
    finally:
        # Exibe resumo
        custo_estimado = estimar_custo_gemini(total_tokens_entrada, total_tokens_saida)
        
        print("\n====== Resumo da Execução ======")
        print(f"Total de artigos processados: {total_artigos}")
        print(f"Total de tokens de entrada: {total_tokens_entrada}")
        print(f"Total de tokens de saída: {total_tokens_saida}")
        print(f"Custo estimado: ${custo_estimado:.4f} USD")
        
        print("\nDocumentos salvos na pasta:")
        if folder_id != DRIVE_FOLDER_ID:
            print(f"ID da pasta: {folder_id}")
            try:
                pasta = docs_handler.service_drive.files().get(
                    fileId=folder_id,
                    fields='webViewLink',
                    supportsAllDrives=True
                ).execute()
                print(f"Link da pasta: {pasta.get('webViewLink', 'N/A')}")
            except:
                print("Não foi possível obter o link da pasta.")
        else:
            print("Pasta padrão do sistema")
        
        print("\n====== Processo Concluído ======\n")

if __name__ == "__main__":
    main() 