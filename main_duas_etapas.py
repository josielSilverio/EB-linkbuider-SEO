# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import Counter
import json
import math

from src.utils import configurar_logging
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler
from src.docs_handler import DocsHandler
from src.menu_handler import MenuHandler
from src.processor import ContentProcessor
from src.config import config

def carregar_ultima_selecao() -> Dict:
    """Carrega a última seleção salva"""
    try:
        if os.path.exists(config.LAST_SELECTION_FILE):
            with open(config.LAST_SELECTION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Erro ao carregar última seleção: {e}")
    return {}

def salvar_ultima_selecao(selecao: Dict):
    """Salva a seleção atual"""
    try:
        os.makedirs(os.path.dirname(config.LAST_SELECTION_FILE), exist_ok=True)
        with open(config.LAST_SELECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(selecao, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar última seleção em {config.LAST_SELECTION_FILE}: {e}")

def apresentar_menu_planilha(sheets_handler: SheetsHandler, ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
    """Apresenta menu para seleção da planilha e pasta do Drive"""
    try:
        # Mostra última planilha e pasta utilizadas
        if ultima_selecao:
            print("\nÚltima configuração utilizada:")
            print(f"Planilha ID: {ultima_selecao.get('spreadsheet_id', 'Não disponível')}")
            print(f"Aba: {ultima_selecao.get('sheet_name', 'Não disponível')}")
            print(f"Pasta Drive ID: {ultima_selecao.get('drive_folder_id', 'Não disponível')}")
            usar_ultima = input("\nDeseja usar a última configuração? (S/N ou 0 para cancelar): ").upper()
            if usar_ultima == '0':
                return None
            if usar_ultima == 'S':
                spreadsheet_id = ultima_selecao.get('spreadsheet_id')
                sheet_name = ultima_selecao.get('sheet_name', 'Sheet1')
                drive_folder_id = ultima_selecao.get('drive_folder_id')
                
                if not spreadsheet_id or not drive_folder_id:
                    print("Configuração incompleta. Por favor, configure manualmente.")
                    return None
                    
                return (str(spreadsheet_id), str(sheet_name), str(drive_folder_id))

        # Lista todas as planilhas disponíveis
        planilhas = sheets_handler.obter_planilhas_disponiveis()
        if not planilhas:
            print("Nenhuma planilha encontrada.")
            return None

        print("\nPlanilhas disponíveis:")
        for i, planilha in enumerate(planilhas, 1):
            print(f"{i}. {planilha['name']}")
        print(f"{len(planilhas)+1}. Adicionar planilha manualmente pelo ID")
        print("0. Cancelar")

        while True:
            try:
                escolha = int(input("\nEscolha o número da planilha (ou 0 para sair): "))
                if escolha == 0:
                    return None
                if 1 <= escolha <= len(planilhas):
                    planilha_escolhida = planilhas[escolha - 1]
                    planilha_id = planilha_escolhida['id']
                    planilha_nome = planilha_escolhida['name']
                    # Buscar abas disponíveis
                    abas = sheets_handler.obter_abas_disponiveis(planilha_id)
                    if not abas:
                        print("Nenhuma aba encontrada nesta planilha.")
                        return None
                    print(f"\nAbas disponíveis na planilha '{planilha_nome}':")
                    for j, aba in enumerate(abas, 1):
                        print(f"{j}. {aba['titulo']}")
                    print("0. Cancelar")
                    while True:
                        try:
                            escolha_aba = int(input("\nEscolha o número da aba (ou 0 para cancelar): "))
                            if escolha_aba == 0:
                                return None
                            if 1 <= escolha_aba <= len(abas):
                                aba_nome = abas[escolha_aba - 1]['titulo']
                                # Sugerir último ID da pasta do Drive, se houver
                                drive_folder_id = '__SUGERIR__'
                                if ultima_selecao and ultima_selecao.get('drive_folder_id'):
                                    print(f"\nÚltima pasta do Drive utilizada: {ultima_selecao['drive_folder_id']}")
                                    drive_folder_id_input = input("Pressione Enter para usar a última pasta ou digite um novo ID: ").strip()
                                    if drive_folder_id_input:
                                        drive_folder_id = drive_folder_id_input
                                    else:
                                        drive_folder_id = ultima_selecao['drive_folder_id']
                                else:
                                    drive_folder_id = input("Digite o ID da pasta do Drive para salvar os documentos (ou 0 para cancelar): ").strip()
                                    if drive_folder_id == '0':
                                        return None
                                    if not drive_folder_id:
                                        print("ID da pasta do Drive é obrigatório.")
                                        continue
                                print(f"\nPlanilha selecionada: {planilha_nome} ({planilha_id}) | Aba: {aba_nome}")
                                return planilha_id, aba_nome, drive_folder_id
                            print("Opção de aba inválida. Tente novamente.")
                        except ValueError:
                            print("Por favor, digite um número válido.")
                elif escolha == len(planilhas) + 1:
                    # Adicionar manualmente
                    planilha_id = input("\nDigite o ID da planilha do Google Sheets (ou 0 para cancelar): ").strip()
                    if planilha_id == '0':
                        return None
                    if not planilha_id:
                        print("ID da planilha é obrigatório.")
                        continue
                    sheet_name = input("Digite o nome da aba (sheet) a ser utilizada (ou 0 para cancelar): ").strip()
                    if sheet_name == '0':
                        return None
                    if not sheet_name:
                        print("Nome da aba é obrigatório.")
                        continue
                    # Sugerir último ID da pasta do Drive, se houver
                    drive_folder_id = '__SUGERIR__'
                    if ultima_selecao and ultima_selecao.get('drive_folder_id'):
                        print(f"\nÚltima pasta do Drive utilizada: {ultima_selecao['drive_folder_id']}")
                        drive_folder_id_input = input("Pressione Enter para usar a última pasta ou digite um novo ID: ").strip()
                        if drive_folder_id_input:
                            drive_folder_id = drive_folder_id_input
                        else:
                            drive_folder_id = ultima_selecao['drive_folder_id']
                    else:
                        drive_folder_id = input("Digite o ID da pasta do Drive para salvar os documentos (ou 0 para cancelar): ").strip()
                        if drive_folder_id == '0':
                            return None
                        if not drive_folder_id:
                            print("ID da pasta do Drive é obrigatório.")
                            continue
                    print(f"\nPlanilha selecionada: {planilha_id} | Aba: {sheet_name}")
                    return planilha_id, sheet_name, drive_folder_id
                print("Opção inválida. Tente novamente.")
            except ValueError:
                print("Por favor, digite um número válido.")
    except Exception as e:
        logging.error(f"Erro ao apresentar menu de planilhas: {e}")
        return None

def apresentar_menu_processamento() -> str:
    """Apresenta menu para seleção do tipo de processamento"""
    print("\nOpções de processamento:")
    print("1. Gerar apenas títulos (use esta opção primeiro)")
    print("2. Gerar apenas conteúdos (use após ter títulos)")
    print("3. Gerar títulos e conteúdos (processo completo)")
    print("0. Sair/Cancelar")

    while True:
        escolha = input("\nEscolha uma opção (recomendado começar com 1): ")
        if escolha in ["0", "1", "2", "3"]:
            if escolha == "2":
                print("\nATENÇÃO: Modo 2 requer que as linhas já tenham títulos.")
                confirma = input("Tem certeza que deseja continuar? (S/N): ").upper()
                if confirma != "S":
                    continue
            return escolha
        print("Opção inválida. Tente novamente.")

def apresentar_menu_quantidade() -> Optional[int]:
    """Menu para escolher quantidade de linhas a processar."""
    print("\nQuantos itens deseja processar?")
    print("1. Gerar tudo (todos os não preenchidos)")
    print("2. Gerar número específico")
    print("3. Cancelar")
    while True:
        escolha = input("\nEscolha uma opção: ").strip()
        if escolha == '1':
            return -1  # Valor especial para indicar "processar tudo"
        elif escolha == '2':
            try:
                qtd = int(input("Digite o número de itens a processar: ").strip())
                if qtd > 0:
                    return qtd
                else:
                    print("Digite um número maior que zero.")
            except ValueError:
                print("Valor inválido. Tente novamente.")
        elif escolha == '3':
            return None  # None significa cancelar
        else:
            print("Opção inválida. Tente novamente.")

async def processar_linhas(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, df: pd.DataFrame, 
                    dynamic_column_map: Dict, modo_teste: bool = False, limite_linhas: Optional[int] = None,
                    modo_processamento: str = "3", id_inicial: Optional[str] = None,
                    spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
    """Processa as linhas da planilha"""
    logger = logging.getLogger('seo_linkbuilder')
    menu = MenuHandler()
    processor = ContentProcessor()

    try:
        # Configurações iniciais
        total_linhas = len(df)
        if limite_linhas:
            total_linhas = min(total_linhas, limite_linhas)
        
        linhas_processadas = 0
        erros = 0
        
        # Itera sobre as linhas
        for idx, row in df.iterrows():
            if limite_linhas and linhas_processadas >= limite_linhas:
                break

            try:
                # Verifica se deve processar esta linha
                if not processor.deve_processar_linha(row, dynamic_column_map, modo_processamento):
                    continue

                # Extrai dados da linha
                palavra_ancora = str(row[dynamic_column_map['palavra_ancora']])
                url_ancora = str(row[dynamic_column_map['url_ancora']])
                
                # Processa título se necessário
                if modo_processamento in ["1", "3"] and not row[dynamic_column_map['titulo']]:
                    prompt_titulo = gemini.carregar_prompt_template(tipo='titulos')
                    titulo = await gemini.gerar_titulo(palavra_ancora, prompt_titulo)
                    
                    if not modo_teste:
                        # Atualiza a planilha com o título
                        sheets.atualizar_celula(
                            spreadsheet_id,
                            sheet_name,
                            idx + 2,  # +2 porque idx é 0-based e planilha tem cabeçalho
                            dynamic_column_map['titulo'],
                            titulo
                        )
                        
                        # Solicita feedback do usuário
                        print(f"\nTítulo gerado para '{palavra_ancora}':")
                        print(titulo)
                        feedback = menu.avaliar_titulo(titulo)
                        
                        # Atualiza o sistema de aprendizado
                        # Aqui usamos uma métrica simples baseada no comprimento do título
                        # Em produção, você pode usar métricas reais de engajamento
                        performance_score = min(1.0, len(titulo) / 100)  # Exemplo simples
                        gemini.atualizar_desempenho_titulo(
                            titulo=titulo,
                            performance_score=performance_score,
                            feedback_score=feedback
                        )

                # Processa conteúdo se necessário
                if modo_processamento in ["2", "3"] and not row[dynamic_column_map['doc_id']]:
                    dados = {
                        'palavra_ancora': palavra_ancora,
                        'url_ancora': url_ancora,
                        'titulo': row[dynamic_column_map['titulo']] if 'titulo' in dynamic_column_map else None
                    }
                    
                    # Gera o conteúdo
                    conteudo = await gemini.gerar_conteudo(dados)
                    
                    if not modo_teste and conteudo:
                        # Cria o documento
                        doc_id = await docs.criar_documento(
                            titulo=dados['titulo'],
                            conteudo=conteudo,
                            pasta_id=row[dynamic_column_map['pasta_id']] if 'pasta_id' in dynamic_column_map else None
                        )
                        
                        if doc_id:
                            # Atualiza a planilha com o ID do documento
                            sheets.atualizar_celula(
                                spreadsheet_id,
                                sheet_name,
                                idx + 2,
                                dynamic_column_map['doc_id'],
                                doc_id
                            )

                linhas_processadas += 1
                
            except Exception as e:
                logger.error(f"Erro ao processar linha {idx + 2}: {str(e)}")
                erros += 1
                if erros >= 3:  # Limite de erros consecutivos
                    logger.error("Muitos erros consecutivos. Parando processamento.")
                    break
                continue

        return linhas_processadas

    except Exception as e:
        logger.error(f"Erro no processamento de linhas: {str(e)}")
        return 0

async def main(modo_teste: bool = False):
    """Função principal do script"""
    try:
        # Configuração inicial
        configurar_logging()
        logger = logging.getLogger('seo_linkbuilder.main')
        logger.info("Iniciando execução do script")

        # Inicialização dos handlers
        sheets_handler = SheetsHandler()
        gemini_handler = GeminiHandler()
        docs_handler = DocsHandler()
        menu_handler = MenuHandler(sheets_handler)
        processor = ContentProcessor(sheets_handler, gemini_handler, docs_handler)

        # Carrega última seleção
        ultima_selecao = carregar_ultima_selecao()

        # Menu de seleção da planilha
        selecao = menu_handler.apresentar_menu_planilha(ultima_selecao)
        if not selecao:
            logger.info("Operação cancelada pelo usuário")
            return

        spreadsheet_id, sheet_name, drive_folder_id = selecao

        # Menu de processamento
        modo_processamento = menu_handler.apresentar_menu_processamento()
        if modo_processamento == "0":
            logger.info("Operação cancelada pelo usuário")
            return

        # Menu de quantidade
        limite_linhas = menu_handler.apresentar_menu_quantidade()
        if limite_linhas is None:  # Verifica se foi cancelado
            logger.info("Operação cancelada pelo usuário")
            return
            
        # Converte -1 para None para processar tudo
        if limite_linhas == -1:
            limite_linhas = None

        # Perguntar se deseja começar de um ID específico
        id_inicial = None
        usar_id_inicial = input("Deseja começar a partir de um ID específico? (S/N): ").strip().upper()
        if usar_id_inicial == 'S':
            id_inicial = input("Digite o ID inicial: ").strip()
            if not id_inicial:
                id_inicial = None

        # Carrega dados da planilha
        df = sheets_handler.carregar_dados_planilha(spreadsheet_id, sheet_name)
        if df is None:
            logger.error("Erro ao carregar dados da planilha")
            return

        # Mapeamento dinâmico de colunas
        dynamic_column_map = sheets_handler.dynamic_column_map

        # Processa as linhas
        processor.processar_linhas(
            df=df,
            dynamic_column_map=dynamic_column_map,
            modo_teste=modo_teste,
            limite_linhas=limite_linhas,
            modo_processamento=modo_processamento,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            id_inicial=id_inicial
        )

        # Salva última seleção
        salvar_ultima_selecao({
            'spreadsheet_id': spreadsheet_id,
            'sheet_name': sheet_name,
            'drive_folder_id': drive_folder_id
        })

        logger.info("Processamento concluído com sucesso")

    except Exception as e:
        logger.error(f"Erro durante a execução: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())         