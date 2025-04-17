# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
from typing import Dict, List
from datetime import datetime

from src.utils import configurar_logging
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler
from src.docs_handler import DocsHandler
from src.config import gerar_nome_arquivo

def main(limite_linhas: int = None, modo_teste: bool = False):
    """
    Função principal que orquestra o fluxo de trabalho.
    
    Args:
        limite_linhas: Opcional. Limita o processamento a este número de linhas.
                      Se for None, processa todas as linhas.
        modo_teste: Se True, executa apenas para a primeira linha e não atualiza a planilha.
    """
    # Configura logging
    logger = configurar_logging()
    logger.info(f"Iniciando script SEO-LinkBuilder - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if modo_teste:
        logger.info("EXECUTANDO EM MODO DE TESTE - Apenas a primeira linha será processada")
    
    if limite_linhas:
        logger.info(f"Processamento limitado a {limite_linhas} linhas")
    
    # Inicializa os handlers
    try:
        sheets = SheetsHandler()
        gemini = GeminiHandler()
        docs = DocsHandler()
        logger.info("Serviços inicializados com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar serviços: {e}")
        return
    
    # Lê a planilha
    try:
        df = sheets.ler_planilha(limite_linhas)
        total_linhas = len(df)
        logger.info(f"Planilha lida com sucesso. Total de {total_linhas} linhas")
        
        if total_linhas == 0:
            logger.warning("Nenhum dado encontrado na planilha. Encerrando.")
            return
        
        if modo_teste:
            df = df.iloc[:1]  # Pega apenas a primeira linha em modo de teste
    except Exception as e:
        logger.error(f"Erro ao ler planilha: {e}")
        return
    
    # Métricas de custo
    custo_total = 0.0
    tokens_entrada_total = 0
    tokens_saida_total = 0
    
    # Processa cada linha
    for i, (_, linha) in enumerate(df.iterrows()):
        try:
            # Extrai dados da linha
            dados = sheets.extrair_dados_linha(linha)
            id_campanha = dados.get('id', 'Sem-ID')
            tema = dados.get('tema', 'Sem tema')
            site = dados.get('site', 'Sem site')
            palavra_ancora = dados.get('palavra_ancora', 'Sem palavra-âncora')
            url_ancora = dados.get('url_ancora', 'Sem URL')
            titulo = dados.get('titulo', 'Sem título')
            
            logger.info(f"Processando linha {i+1}/{len(df)}: ID {id_campanha} - {titulo}")
            
            # Gera o conteúdo usando o Gemini
            logger.info(f"Gerando conteúdo com o Gemini para '{tema}'...")
            conteudo, metricas, info_link = gemini.gerar_conteudo(dados)
            
            # Atualiza métricas
            custo_total += metricas['custo_estimado']
            tokens_entrada_total += metricas['tokens_entrada']
            tokens_saida_total += metricas['tokens_saida']
            
            # Gera o nome do arquivo usando o ID em vez da data
            try:
                nome_arquivo = gerar_nome_arquivo(id_campanha, site, palavra_ancora)
            except Exception as e:
                logger.error(f"Erro ao gerar nome de arquivo: {e}")
                # Fallback para um nome simples
                nome_arquivo = f"{id_campanha} - {site} - Artigo"
            
            # Cria o documento no Google Docs
            logger.info(f"Criando documento '{nome_arquivo}'...")
            document_id, document_url = docs.criar_documento(titulo, conteudo, nome_arquivo, info_link)
            
            # Atualiza a URL na planilha (se não estiver em modo de teste)
            if not modo_teste:
                sheets.atualizar_url_documento(i, document_url)
                logger.info(f"URL atualizada na planilha: {document_url}")
            else:
                logger.info(f"[MODO TESTE] URL gerada (não atualizada na planilha): {document_url}")
            
            # Pausa para não sobrecarregar as APIs
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Erro ao processar linha {i+1}: {e}")
            continue
    
    # Exibe resumo
    logger.info(f"\n{'='*50}")
    logger.info(f"RESUMO DE EXECUÇÃO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total de artigos processados: {len(df)}")
    logger.info(f"Tokens de entrada: {tokens_entrada_total}")
    logger.info(f"Tokens de saída: {tokens_saida_total}")
    logger.info(f"Custo total estimado: ${custo_total:.4f} USD")
    logger.info(f"{'='*50}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SEO-LinkBuilder - Gerador de conteúdo para SEO')
    parser.add_argument('--limite', type=int, default=10,
                        help='Número máximo de linhas a processar (padrão: 10)')
    parser.add_argument('--teste', action='store_true',
                        help='Executa apenas para a primeira linha sem atualizar a planilha')
    parser.add_argument('--todos', action='store_true',
                        help='Processa todas as linhas da planilha')
    parser.add_argument('--abril', action='store_true',
                        help='Processa apenas as linhas de abril/2024 (já é o padrão)')
    
    args = parser.parse_args()
    
    # Define o limite de linhas
    if args.todos:
        limite = None  # Sem limite
    else:
        limite = args.limite
    
    # Executa o script
    main(limite_linhas=limite, modo_teste=args.teste) 