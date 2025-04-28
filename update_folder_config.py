#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script para atualizar o ID de pasta no arquivo de configuração
"""

import os
import sys
import re
from typing import Optional

from src.docs_handler import DocsHandler

def atualizar_config(novo_folder_id: str) -> bool:
    """
    Atualiza o ID da pasta de destino no arquivo de configuração.
    
    Args:
        novo_folder_id: Novo ID de pasta a ser definido
        
    Returns:
        True se atualizado com sucesso, False caso contrário
    """
    caminho_config = os.path.join('src', 'config.py')
    
    if not os.path.exists(caminho_config):
        print(f"Erro: Arquivo de configuração não encontrado em {caminho_config}")
        return False
    
    try:
        # Lê o arquivo de configuração
        with open(caminho_config, 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        # Padrão para encontrar a linha do DEFAULT_DRIVE_FOLDER_ID
        padrao = r'(DEFAULT_DRIVE_FOLDER_ID\s*=\s*["\'])([^"\']+)(["\'].*)'
        
        # Substitui o ID antigo pelo novo
        novo_conteudo = re.sub(padrao, fr'\1{novo_folder_id}\3', config_content)
        
        # Verifica se houve alteração
        if novo_conteudo == config_content:
            print("Aviso: Não foi possível encontrar a linha de configuração do folder ID para substituir.")
            return False
        
        # Escreve o novo conteúdo no arquivo
        with open(caminho_config, 'w', encoding='utf-8') as f:
            f.write(novo_conteudo)
        
        print(f"O ID da pasta foi atualizado com sucesso para: {novo_folder_id}")
        return True
        
    except Exception as e:
        print(f"Erro ao atualizar arquivo de configuração: {e}")
        return False

def extrair_id_da_url(url: str) -> str:
    """
    Extrai o ID de um documento ou pasta a partir da URL.
    """
    return DocsHandler.extrair_id_da_url(url)

def main():
    """Função principal"""
    print("\n==== ATUALIZAÇÃO DO ID DE PASTA ====\n")
    
    # Verifica se o ID foi fornecido como argumento
    if len(sys.argv) > 1:
        url_ou_id = sys.argv[1]
        print(f"Usando input do argumento: {url_ou_id}")
    else:
        # Solicita a URL ou ID
        url_ou_id = input("Informe a URL ou ID da pasta do Google Drive: ").strip()
    
    # Extrai o ID
    folder_id = extrair_id_da_url(url_ou_id)
    
    if not folder_id:
        print("Não foi possível extrair um ID válido da entrada fornecida.")
        return
    
    print(f"ID extraído: {folder_id}")
    
    # Confirma antes de prosseguir
    confirmacao = input(f"Deseja atualizar o ID da pasta para {folder_id}? (S/N): ").strip().lower()
    
    if confirmacao not in ['s', 'sim', 'y', 'yes']:
        print("Operação cancelada pelo usuário.")
        return
    
    # Atualiza o arquivo de configuração
    if atualizar_config(folder_id):
        print("\nA configuração foi atualizada com sucesso!")
        print("Agora o programa usará esta pasta por padrão para salvar os documentos.")
    else:
        print("\nHouve um problema ao atualizar a configuração.")
        print("Verifique se o arquivo 'src/config.py' existe e está acessível.")
    
    print("\n==== PROCESSO CONCLUÍDO ====\n")

if __name__ == "__main__":
    main() 