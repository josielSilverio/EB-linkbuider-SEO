# Módulo para interagir com a API do Google Sheets
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
import re
import os

from src.config import (
    SPREADSHEET_ID, 
    SHEET_NAME, 
    COLUNAS, 
    LINHA_INICIAL
)
from src.auth_handler import obter_credenciais, criar_servico_sheets, criar_servico_drive

class SheetsHandler:
    def __init__(self):
        # Inicializa o logger
        self.logger = logging.getLogger('seo_linkbuilder.sheets')
        
        # Obtém credenciais e inicializa os serviços
        try:
            self.credenciais = obter_credenciais()
            self.service = criar_servico_sheets(self.credenciais)
            self.service_drive = criar_servico_drive(self.credenciais)
            self.logger.info("Serviços do Google Sheets e Drive inicializados com sucesso para SheetsHandler")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar serviços para SheetsHandler: {e}")
            raise
    
    def get_column_letter(self, column_index: int) -> str:
        """
        Converte um índice de coluna (0-based) para a letra da coluna do Google Sheets (A, B, ..., Z, AA, AB, ...).
        Args:
            column_index: O índice da coluna (0 para A, 1 para B, etc.).
        Returns:
            A letra da coluna correspondente.
        """
        if not isinstance(column_index, int) or column_index < 0:
            self.logger.error(f"Índice de coluna inválido fornecido para get_column_letter: {column_index}")
            # Retorna um fallback ou levanta um erro, dependendo da política de erro desejada.
            # Por segurança, vamos retornar uma coluna padrão alta para evitar erros de range, mas logar.
            return "Z" # Ou poderia ser "AMJ" (coluna 1023, limite comum) se preferir.

        letter = ''
        while column_index >= 0:
            remainder = column_index % 26
            letter = chr(ord('A') + remainder) + letter
            column_index = (column_index // 26) - 1
            if column_index < -1: # Pequena correção para o loop quando column_index se torna -1
                break
        return letter
    
    def obter_planilhas_disponiveis(self):
        """
        Obtém a lista de planilhas disponíveis na conta do usuário.
        
        Returns:
            Lista de dicionários com informações das planilhas (id, nome)
        """
        try:
            # Lista todas as planilhas usando o service_drive
            resultado = self.service_drive.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            # Extrai os arquivos retornados
            planilhas = resultado.get('files', [])
            
            if not planilhas:
                self.logger.warning("Nenhuma planilha encontrada")
                return []
                
            self.logger.info(f"Encontradas {len(planilhas)} planilhas")
            return planilhas
            
        except Exception as e:
            self.logger.error(f"Erro ao listar planilhas disponíveis: {e}")
            return []
            
    def obter_abas_disponiveis(self, spreadsheet_id=None):
        """
        Obtém a lista de abas disponíveis em uma planilha específica.
        
        Args:
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            
        Returns:
            Lista de dicionários com informações das abas (título, índice)
        """
        try:
            # Usa o ID fornecido ou o configurado
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            
            # Obtém informações da planilha, incluindo suas abas
            resultado = self.service.spreadsheets().get(
                spreadsheetId=id_planilha
            ).execute()
            
            # Extrai as abas (sheets)
            abas = resultado.get('sheets', [])
            
            if not abas:
                self.logger.warning(f"Nenhuma aba encontrada na planilha {id_planilha}")
                return []
                
            # Formata os resultados para incluir apenas o que precisamos
            abas_formatadas = []
            for aba in abas:
                props = aba.get('properties', {})
                abas_formatadas.append({
                    'titulo': props.get('title', 'Sem título'),
                    'indice': props.get('index', 0)
                })
                
            self.logger.info(f"Encontradas {len(abas_formatadas)} abas na planilha {id_planilha}")
            return abas_formatadas
            
        except Exception as e:
            self.logger.error(f"Erro ao listar abas da planilha {spreadsheet_id}: {e}")
            return []
    
    def ler_planilha(self, 
                     limite_linhas: Optional[int] = None, 
                     apenas_dados: bool = False, 
                     spreadsheet_id: Optional[str] = None, 
                     sheet_name: Optional[str] = None, 
                     filtrar_processados: bool = True,
                     linha_inicial: Optional[int] = None):
        """
        Lê a planilha do Google Sheets e retorna os dados como um DataFrame pandas.
        Adiciona uma coluna 'sheet_row_num' com o número original da linha na planilha.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas (APÓS filtro de linha_inicial).
            apenas_dados: Se True, retorna todos os dados sem aplicar filtros adicionais de ID.
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
            filtrar_processados: Se True, filtra linhas que já foram processadas (têm URL de documento).
            linha_inicial: Opcional. Número da linha da planilha a partir da qual começar (1-based).
        
        Returns:
            DataFrame com os dados da planilha e a coluna 'sheet_row_num'.
        """
        self.logger.debug(f"Iniciando leitura da planilha. Limite: {limite_linhas}, Linha Inicial: {linha_inicial}, Apenas Dados: {apenas_dados}, Filtrar Processados: {filtrar_processados}")

        current_spreadsheet_id = spreadsheet_id if spreadsheet_id else SPREADSHEET_ID
        current_sheet_name = sheet_name if sheet_name else SHEET_NAME

        if not current_spreadsheet_id or not current_sheet_name:
            self.logger.error("ID da planilha ou nome da aba não especificados.")
            return pd.DataFrame() if not apenas_dados else []

        try:
            self.logger.info(f"Lendo dados da planilha: '{current_spreadsheet_id}', Aba: '{current_sheet_name}'")
            max_col_index = 0
            if isinstance(COLUNAS, dict):
                max_col_index = max(COLUNAS.values()) if COLUNAS else 0
            
            ultima_coluna_letra = self.get_column_letter(max_col_index + 5)
            range_para_ler = f"{current_sheet_name}!A:{ultima_coluna_letra}"
            self.logger.debug(f"Range de leitura definido para: {range_para_ler}")

            result = self.service.spreadsheets().values().get(
                spreadsheetId=current_spreadsheet_id,
                range=range_para_ler
            ).execute()
            data_rows = result.get('values', [])

            if not data_rows:
                self.logger.warning(f"Nenhum dado encontrado na aba '{current_sheet_name}' da planilha '{current_spreadsheet_id}'.")
                return pd.DataFrame() if not apenas_dados else []

            self.logger.info(f"Recebidos {len(data_rows)} linhas da API do Google Sheets.")
            
            if data_rows: # Somente processa se houver alguma linha (incluindo cabeçalho)
                header = data_rows[0]
                num_header_cols = len(header)
                
                # Normaliza as linhas de dados para terem o mesmo número de colunas que o cabeçalho
                processed_data_rows = []
                for row in data_rows[1:]:
                    # Garante que a linha tenha o mesmo número de colunas que o cabeçalho,
                    # preenchendo com strings vazias se for mais curta.
                    # Se for mais longa, trunca para o tamanho do cabeçalho (menos provável, mas seguro)
                    normalized_row = (row + [''] * num_header_cols)[:num_header_cols]
                    processed_data_rows.append(normalized_row)
                
                if processed_data_rows: # Se houver linhas de dados após o cabeçalho
                    df = pd.DataFrame(processed_data_rows, columns=header)
                else: # Só havia cabeçalho, ou nenhuma linha de dados real
                    df = pd.DataFrame(columns=header) # DataFrame vazio com colunas do cabeçalho
                
                # Como COLUNAS usa índices numéricos, resetamos as colunas do df para índices numéricos.
                # Isso mantém a consistência com o restante do código que espera df.columns ser numérico.
                df.columns = range(df.shape[1]) # df.shape[1] dará o número de colunas do cabeçalho
            else:
                # Nenhuma linha recebida da API, nem mesmo cabeçalho
                df = pd.DataFrame()
            
            coluna_id_idx = COLUNAS.get('id', -1)
            coluna_url_idx = COLUNAS.get('url_documento', -1)

            if coluna_id_idx != -1 and coluna_id_idx < len(df.columns):
                df[coluna_id_idx] = df[coluna_id_idx].astype(str)
                original_row_count = len(df)
                df = df[df[coluna_id_idx].notna() & (df[coluna_id_idx].str.strip() != '')]
                self.logger.info(f"{original_row_count - len(df)} linhas removidas por ID inválido/vazio. {len(df)} linhas restantes.")
            else:
                self.logger.warning(f"Coluna ID (índice {coluna_id_idx}) não encontrada. Não foi possível filtrar por IDs válidos.")

            if filtrar_processados:
                if coluna_url_idx != -1 and coluna_url_idx < len(df.columns):
                    df[coluna_url_idx] = df[coluna_url_idx].astype(str) # Converte a coluna para string
                    original_row_count = len(df)

                    # Mantém linhas onde a URL é NaN (pandas considera nulo) OU a string está vazia.
                    # pd.NA não é pego por isna() em colunas de objeto, então converter para string e checar é mais robusto.
                    df = df[df[coluna_url_idx].fillna('').str.strip() == '']
                    self.logger.info(f"{original_row_count - len(df)} linhas removidas por já terem URL. {len(df)} linhas restantes para processamento.")
                else:
                    self.logger.warning(f"Coluna URL (índice {coluna_url_idx}) não encontrada. Não foi possível filtrar por itens já processados.")
            else:
                self.logger.info("Filtragem de itens já processados foi pulada (filtrar_processados=False).")
            
            if df.empty:
                self.logger.warning("Nenhuma linha restante após as filtragens.")
                return pd.DataFrame() if not apenas_dados else []

            # Adicionar 'sheet_row_num' APÓS as filtragens que podem alterar o número de linhas,
            # mas ANTES de qualquer ordenação que possa bagunçar a correspondência com a planilha original se o índice for resetado.
            # O df.index neste ponto ainda deve corresponder aos índices da leitura original (0-based).
            # Adicionamos 2: 1 para converter para 1-based e 1 porque a linha 1 da planilha é geralmente cabeçalho.
            # Esta coluna é crucial para atualizar a célula correta na planilha.
            df['sheet_row_num'] = df.index + 2 

            # Ordenar por 'sheet_row_num' para garantir que processamos na ordem da planilha
            # Isso é importante se o limite_linhas for aplicado.
            df = df.sort_values(by='sheet_row_num').reset_index(drop=True)
                                                                        
            self.logger.info(f"DataFrame preparado com {len(df)} linhas antes do filtro de linha inicial. Próximas (sheet_row_num): {df['sheet_row_num'].head().tolist() if not df.empty else 'N/A'}")

            # Aplicar filtro de linha_inicial, se especificado
            if linha_inicial is not None and isinstance(linha_inicial, int) and linha_inicial > 1: # Deve ser > 1 pois linha 1 é cabeçalho
                self.logger.info(f"Aplicando filtro para começar a partir da linha da planilha: {linha_inicial}")
                df = df[df['sheet_row_num'] >= linha_inicial]
                df = df.reset_index(drop=True) # Resetar índice após esta filtragem crucial
                if df.empty:
                    self.logger.warning(f"Nenhuma linha restante após filtrar pela linha inicial {linha_inicial}.")
                else:
                    self.logger.info(f"{len(df)} linhas restantes após filtro de linha inicial. Próximas (sheet_row_num): {df['sheet_row_num'].head().tolist()}")
            elif linha_inicial is not None:
                 self.logger.warning(f"Parâmetro 'linha_inicial' ({linha_inicial}) é inválido ou <= 1. Ignorando filtro de linha inicial.")

            # Aplicar limite_linhas APÓS o filtro de linha_inicial
            if limite_linhas is not None and isinstance(limite_linhas, int) and limite_linhas > 0:
                if not df.empty:
                    if limite_linhas < len(df):
                        self.logger.info(f"Aplicando limite de {limite_linhas} linhas ao DataFrame resultante.")
                        df = df.head(limite_linhas)
                    # else: o df já é menor ou igual ao limite, nada a fazer
                    self.logger.info(f"{len(df)} linhas no DataFrame final após todos os filtros e limites.")
            
            return df if not apenas_dados else df.values.tolist()

        except Exception as e:
            self.logger.error(f"Erro ao ler a planilha: {e}")
            self.logger.exception("Detalhes do erro:")
            raise
    
    def extrair_dados_linha(self, linha_df: pd.Series) -> Dict[str, str]:
        """
        Extrai os dados relevantes de uma linha do DataFrame.
        
        Args:
            linha_df: Uma linha do DataFrame (como Series)
        
        Returns:
            Dicionário com os dados extraídos
        """
        try:
            # Mapeamento usando os índices numéricos das colunas
            # Se o índice existe no DataFrame, usa o valor, senão None
            dados = {
                'id': linha_df.get(COLUNAS["id"]) if COLUNAS["id"] in linha_df.index else None,
                'tema': linha_df.get(COLUNAS["tema"]) if COLUNAS["tema"] and COLUNAS["tema"] in linha_df.index else None,
                'site': linha_df.get(COLUNAS["site"]) if COLUNAS["site"] in linha_df.index else None,
                'palavra_ancora': linha_df.get(COLUNAS["palavra_ancora"]) if COLUNAS["palavra_ancora"] in linha_df.index else None,
                'url_ancora': linha_df.get(COLUNAS["url_ancora"]) if COLUNAS["url_ancora"] in linha_df.index else None,
                'titulo': linha_df.get(COLUNAS["titulo"]) if COLUNAS["titulo"] in linha_df.index else None
            }
            
            # Limpa os valores None ou vazios
            dados = {k: v if v and str(v).strip() else f"Sem {k}" for k, v in dados.items()}
            
            # Não precisamos mais verificar campos nulos, já que sabemos que tema e título geralmente são vazios
            # e serão gerados automaticamente
            
            return dados
        
        except Exception as e:
            self.logger.error(f"Erro ao extrair dados da linha: {e}")
            self.logger.error(f"Índices disponíveis: {linha_df.index.tolist()}")
            self.logger.error(f"Valores: {linha_df.values}")
            raise
    
    def atualizar_url_documento(self, sheet_row_num: int, url_documento: str, spreadsheet_id=None, sheet_name=None) -> bool:
        """
        Atualiza a URL do documento criado na coluna correspondente da planilha.
        
        Args:
            sheet_row_num: Número da linha na planilha (1-based) a ser atualizada.
            url_documento: URL do documento do Google Docs
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
            
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            linha_sheets = sheet_row_num # Usa o número da linha diretamente
            coluna_url = 'J' # Assume que é sempre a coluna J
            range_atualizacao = f"{nome_aba}!{coluna_url}{linha_sheets}"
            
            self.logger.info(f"Preparando para atualizar URL na Planilha: {id_planilha}")
            self.logger.info(f"Aba: '{nome_aba}', Célula: {coluna_url}{linha_sheets} (Range: {range_atualizacao})")
            self.logger.info(f"Sheet Row Number: {sheet_row_num}")
            self.logger.info(f"URL a ser inserida: {url_documento}")
            
            # (Opcional, mas recomendado) Verificar se a aba existe (código omitido para brevidade, mas estava presente antes)
            # ... (código de verificação da aba) ...
            
            resultado = self.service.spreadsheets().values().update(
                spreadsheetId=id_planilha,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",
                body={"values": [[url_documento]]}
            ).execute()
            
            # ... (logging do resultado) ...
            return True
        except Exception as e:
            self.logger.error(f"Erro ao atualizar URL na linha {sheet_row_num} (Planilha {id_planilha}, Aba '{nome_aba}', Célula {coluna_url}{linha_sheets}): {e}")
            # ... (logging da exceção) ...
            return False

    def atualizar_titulo_documento(self, sheet_row_num: int, titulo: str, spreadsheet_id=None, sheet_name=None) -> bool:
        """
        Atualiza o título do documento na coluna correspondente da planilha.
        
        Args:
            sheet_row_num: Número da linha na planilha (1-based) a ser atualizada.
            titulo: Título do documento gerado
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
            
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            linha_sheets = sheet_row_num # Usa o número da linha diretamente
            coluna_titulo = 'I' # Assume que é sempre a coluna I
            range_atualizacao = f"{nome_aba}!{coluna_titulo}{linha_sheets}"

            self.logger.info(f"Preparando para atualizar Título na Planilha: {id_planilha}")
            self.logger.info(f"Aba: '{nome_aba}', Célula: {coluna_titulo}{linha_sheets} (Range: {range_atualizacao})")
            self.logger.info(f"Sheet Row Number: {sheet_row_num}")
            self.logger.info(f"Título a ser inserido: '{titulo}'")

            # (Opcional, mas recomendado) Verificar se a aba existe (código omitido para brevidade)
            # ... (código de verificação da aba) ...

            resultado = self.service.spreadsheets().values().update(
                spreadsheetId=id_planilha,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",
                body={"values": [[titulo]]}
            ).execute()

            # ... (logging do resultado) ...
            return True
        except Exception as e:
            self.logger.error(f"Erro ao atualizar título na linha {sheet_row_num} (Planilha {id_planilha}, Aba '{nome_aba}', Célula {coluna_titulo}{linha_sheets}): {e}")
            # ... (logging da exceção) ...
            return False