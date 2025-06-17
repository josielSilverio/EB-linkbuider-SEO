# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import Counter
import json

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
                return (
                    ultima_selecao.get('spreadsheet_id'),
                    ultima_selecao.get('sheet_name', 'Sheet1'),
                    ultima_selecao.get('drive_folder_id')
                )

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
    print("1. Gerar apenas títulos")
    print("2. Gerar apenas conteúdos")
    print("3. Gerar títulos e conteúdos")
    print("0. Sair/Cancelar")

    while True:
        escolha = input("\nEscolha uma opção: ")
        if escolha in ["0", "1", "2", "3"]:
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
            return None  # None = processar tudo
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
            return 'cancelar'
        else:
            print("Opção inválida. Tente novamente.")

def processar_linhas(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, df: pd.DataFrame, 
                    dynamic_column_map: Dict, modo_teste: bool = False, limite_linhas: Optional[int] = None,
                    modo_processamento: str = "3", id_inicial: Optional[str] = None,
                    spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
    """
    Processa as linhas selecionadas de acordo com o modo escolhido:
    - modo_processamento: "1" para apenas títulos, "2" para apenas conteúdos, "3" para ambos
    - id_inicial: ID específico para começar o processamento
    """
    logger = logging.getLogger('seo_linkbuilder.main')
    
    # Contador para linhas processadas
    linhas_processadas = 0
    
    # Lista para armazenar títulos gerados
    titulos_gerados = []
    
    # Filtra o DataFrame se houver ID inicial
    if id_inicial:
        col_id = dynamic_column_map['id']['name'] if isinstance(dynamic_column_map['id'], dict) else dynamic_column_map['id']
        # Garante que o DataFrame está ordenado pela ordem original
        df = df.reset_index(drop=True)
        idx_inicio = df.index[df[col_id] == id_inicial].tolist()
        if not idx_inicio:
            logger.warning(f"Nenhuma linha encontrada com ID {id_inicial}")
            return
        idx_inicio = idx_inicio[0]
        df = df.iloc[idx_inicio:]
    
    # Primeira etapa: Geração de títulos (se necessário)
    if modo_processamento in ["1", "3"]:
        logger.info("Iniciando primeira etapa: Geração de títulos")
        col_titulo = dynamic_column_map['titulo']['name'] if isinstance(dynamic_column_map['titulo'], dict) else dynamic_column_map['titulo']
        for idx, row in df.iterrows():
            titulo_atual = row.get(col_titulo)
            if titulo_atual and str(titulo_atual).strip() and str(titulo_atual).strip().lower() != "sem titulo":
                continue  # Pula linhas já preenchidas com tema/título
            if limite_linhas and linhas_processadas >= limite_linhas:
                break
            dados = sheets.extrair_dados_linha(row, dynamic_column_map)
            titulo_escolhido = None
            tentativas = 0
            temperatura_original = getattr(gemini, 'temperatura_atual', 0.7)
            while not titulo_escolhido:
                tentativas += 1
                # Aumenta a temperatura a cada tentativa para forçar mais criatividade
                if hasattr(gemini, 'temperatura_atual'):
                    gemini.temperatura_atual = min(1.0, temperatura_original + 0.1 * tentativas)
                titulos = gemini.gerar_titulos(dados, quantidade=3)
                for titulo in titulos:
                    titulo_norm = titulo.strip().lower()
                    if titulo_norm in titulos_gerados:
                        continue
                    titulo_escolhido = titulo
                    break
                if tentativas > 10:
                    logger.warning(f"Não foi possível gerar título original para ID {dados['id']} após 10 tentativas. Pulando linha.")
                    break
            # Restaura temperatura original
            if hasattr(gemini, 'temperatura_atual'):
                gemini.temperatura_atual = temperatura_original
            if not titulo_escolhido:
                continue
            sheet_row_num = row['sheet_row_num'] if 'sheet_row_num' in row else row.name + 2
            sheets.atualizar_titulo_documento(sheet_row_num, titulo_escolhido, spreadsheet_id, sheet_name)
            print(f"Título gerado para ID {dados['id']}: {titulo_escolhido}")
            titulos_gerados.append((dados['id'], titulo_escolhido))
            linhas_processadas += 1
    
    # Recarrega o DataFrame após gerar títulos, se for modo 3
    if modo_processamento == "3":
        df = sheets.carregar_dados_planilha(spreadsheet_id, sheet_name)

    # Segunda etapa: Geração de conteúdo (se necessário)
    if modo_processamento in ["2", "3"]:
        logger.info("Iniciando segunda etapa: Geração de conteúdo")
        conteudos_lote = []
        linhas_processadas_lote = 0
        col_titulo = dynamic_column_map['titulo']['name'] if isinstance(dynamic_column_map['titulo'], dict) else dynamic_column_map['titulo']
        col_url_doc = dynamic_column_map['url_documento']['name'] if isinstance(dynamic_column_map['url_documento'], dict) else dynamic_column_map['url_documento']
        for _, row in df.iterrows():
            titulo_atual = row.get(col_titulo)
            url_doc_atual = row.get(col_url_doc)
            if titulo_atual and str(titulo_atual).strip() and str(titulo_atual).strip().lower() != "sem titulo" and url_doc_atual and str(url_doc_atual).strip():
                continue  # Pula linhas já preenchidas com tema e conteúdo
            if limite_linhas and linhas_processadas_lote >= limite_linhas:
                break
            dados = sheets.extrair_dados_linha(row, dynamic_column_map)
            conteudo, metricas, info_link = gemini.gerar_conteudo_por_titulo(dados, dados['titulo'])
            if not conteudo:
                logger.warning(f"Falha ao gerar conteúdo para ID {dados['id']}")
                continue
            conteudos_lote.append({
                'dados': dados,
                'conteudo': conteudo,
                'metricas': metricas,
                'row': row
            })
            linhas_processadas_lote += 1
        # Soma métricas
        total_tokens_entrada = sum(c['metricas'].get('input_token_count', 0) for c in conteudos_lote)
        total_tokens_saida = sum(c['metricas'].get('output_token_count', 0) for c in conteudos_lote)
        total_custo = sum(c['metricas'].get('cost_usd', 0) for c in conteudos_lote)
        total_palavras = sum(c['metricas'].get('num_palavras', 0) for c in conteudos_lote)
        total_caracteres = sum(c['metricas'].get('num_caracteres', 0) for c in conteudos_lote)
        print(f"\nResumo do lote de conteúdos gerados ({linhas_processadas_lote}):")
        for c in conteudos_lote:
            dados = c['dados']
            print(f"ID: {dados.get('id', '')} | Título: {dados.get('titulo', '')} | Palavra-âncora: {dados.get('palavra_ancora', '')} | Site: {dados.get('site', '')}")
        print(f"Tokens de entrada: {total_tokens_entrada}")
        print(f"Tokens de saída: {total_tokens_saida}")
        print(f"Custo estimado (USD): {total_custo:.6f}")
        print(f"Palavras: {total_palavras}")
        print(f"Caracteres: {total_caracteres}")
        # Confirmação automática no modo 3
        if modo_processamento == '3':
            confirm = 'S'
        else:
            confirm = input("\nDeseja criar os documentos e atualizar a planilha para este lote? (S/N): ").strip().upper()
        if confirm != 'S':
            print("Lote descartado pelo usuário. Nenhum documento será criado.")
            return
        # Cria documentos e atualiza planilha
        for c in conteudos_lote:
            dados = c['dados']
            conteudo = c['conteudo']
            row = c['row']
            # Nome do documento no padrão correto
            nome_arquivo = f"{dados['id']} - {dados['site']} - {dados['palavra_ancora']}"
            doc_id, doc_url = docs.criar_documento(
                dados['titulo'],
                conteudo,
                nome_arquivo
            )
            # Atualiza a planilha apenas com a URL do documento
            sheet_row_num = row['sheet_row_num'] if 'sheet_row_num' in row else row.name + 2
            sheets.atualizar_url_documento(sheet_row_num, doc_url, spreadsheet_id, sheet_name)
            print(f"Documento criado para ID {dados['id']}: {doc_url}")

def main(modo_teste: bool = False):
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
        if limite_linhas == 'cancelar':
            logger.info("Operação cancelada pelo usuário")
            return

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
    main() 