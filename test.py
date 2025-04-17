#!/usr/bin/env python3
"""
Script para testar a funcionalidade básica do SEO-LinkBuilder
Este script executa o projeto em modo de teste com apenas uma linha,
sem atualizar a planilha.
"""

import logging
from src.utils import configurar_logging
from main import main

if __name__ == "__main__":
    logger = configurar_logging(logging.INFO)
    logger.info("Iniciando teste do SEO-LinkBuilder")
    
    try:
        # Executa o main em modo de teste (processa apenas uma linha e não atualiza a planilha)
        main(limite_linhas=1, modo_teste=True)
        logger.info("Teste concluído com sucesso!")
    except Exception as e:
        logger.error(f"Erro durante o teste: {e}")
        raise 