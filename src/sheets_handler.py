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
    
    def ler_planilha(self, limite_linhas: Optional[int] = None, apenas_dados: bool = False, spreadsheet_id=None, sheet_name=None) -> pd.DataFrame:
        """
        Lê a planilha do Google Sheets e retorna os dados como um DataFrame pandas.
        Adiciona uma coluna 'sheet_row_num' com o número original da linha na planilha.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas.
            apenas_dados: Se True, retorna todos os dados sem aplicar filtros adicionais de ID.
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
        
        Returns:
            DataFrame com os dados da planilha e a coluna 'sheet_row_num'.
        """
        try:
            # Usa os IDs fornecidos ou os configurados
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            
            self.logger.info(f"Tentando ler planilha {id_planilha}, aba {nome_aba}")
            
            # Obtém a planilha - lemos até a coluna O
            resultado = self.service.spreadsheets().values().get(
                spreadsheetId=id_planilha,
                range=f"{nome_aba}!A:O" # Assume que os dados começam na linha 1
            ).execute()
            
            valores = resultado.get('values', [])
            
            if not valores:
                self.logger.warning(f"Nenhum dado encontrado na planilha {id_planilha}, aba {nome_aba}")
                return pd.DataFrame()
            
            self.logger.info(f"Lidas {len(valores)} linhas da planilha no total")
            
            df = pd.DataFrame(valores)
            
            # Verifica se a primeira linha parece ser um cabeçalho (Lógica Refinada)
            header_detected = False
            header_offset = 0
            if len(df) > 0 and df.iloc[0] is not None:
                first_row = df.iloc[0]
                # Verifica se colunas específicas contêm os nomes de cabeçalho esperados (case-insensitive)
                is_id_header = COLUNAS['id'] < len(first_row) and str(first_row[COLUNAS['id']]).strip().lower() == 'id'
                is_site_header = COLUNAS['site'] < len(first_row) and str(first_row[COLUNAS['site']]).strip().lower() == 'site'
                # Permite variações para 'ancora'
                is_ancora_header = COLUNAS['palavra_ancora'] < len(first_row) and str(first_row[COLUNAS['palavra_ancora']]).strip().lower() in ['palavra_ancora', 'palavra ancora', 'ancora', 'âncora']

                # Considera cabeçalho se pelo menos duas colunas chave corresponderem
                if (is_id_header and is_site_header) or (is_id_header and is_ancora_header) or (is_site_header and is_ancora_header):
                    header_detected = True
                    header_offset = 1
                    self.logger.info(f"Cabeçalho detectado (baseado nas colunas ID, Site, Âncora): {first_row.tolist()}")
                    df_data = df.iloc[header_offset:] # Remove cabeçalho
                else:
                    self.logger.info("Primeira linha não detectada como cabeçalho (verificação específica de colunas).")
                    df_data = df # Não remove nada
                    header_offset = 0 # Garante que o offset seja 0 se não for detectado cabeçalho
            else:
                 self.logger.warning("DataFrame vazio ou primeira linha nula após leitura.")
                 df_data = df # Continua com o DataFrame original (provavelmente vazio)
                 header_offset = 0 # Garante que o offset seja 0

            # Adiciona o número da linha original da planilha (1-based)
            # O índice preservado de df_data já reflete a posição original na leitura (0-based se sem header, 1-based se header foi removido)
            # Apenas adicionamos 1 para obter a numeração de linha da planilha (1-based)
            df_data = df_data.copy() # Para evitar SettingWithCopyWarning
            df_data['sheet_row_num'] = df_data.index + 1 # Correção: Simplesmente índice + 1
            self.logger.debug(f"Coluna 'sheet_row_num' adicionada. Exemplo (primeiras 5 linhas de dados): {df_data[['sheet_row_num']].head().to_string()}")
            
            df_a_filtrar_id = df_data.copy() # Copia antes de qualquer filtro
            coluna_id = COLUNAS.get("id", -1)
            if not apenas_dados and coluna_id != -1 and coluna_id < len(df_a_filtrar_id.columns):
                def is_valid_id(id_value):
                    if not id_value: return False
                    id_str = str(id_value).strip().lower()
                    return bool(id_str and id_str not in ['id', 'identificador', 'código', 'code', 'none', 'nan', '#n/a', 'n/a'])

                if not df_a_filtrar_id.empty:
                    mascara_id = df_a_filtrar_id[coluna_id].apply(is_valid_id)
                    df_filtrado_id = df_a_filtrar_id[mascara_id]
                    self.logger.info(f"Filtrado para {len(df_filtrado_id)} linhas com IDs válidos de {len(df_a_filtrar_id)} linhas de dados")
                    df_para_filtrar_url = df_filtrado_id
                else:
                    df_para_filtrar_url = df_a_filtrar_id # Dataframe já estava vazio
            else:
                self.logger.info("Modo 'apenas_dados' ativado OU coluna ID não configurada/encontrada. Pulando filtro de ID.")
                df_para_filtrar_url = df_a_filtrar_id

            # Aplica filtro para pular linhas com URL já preenchida (Coluna J)
            df_final = df_para_filtrar_url.copy() # Copia antes do filtro de URL
            coluna_url = COLUNAS.get("url_documento", -1)
            if coluna_url != -1 and coluna_url < len(df_final.columns):
                # Mantém linhas onde a coluna URL está vazia ou nula
                mascara_url = df_final[coluna_url].isnull() | (df_final[coluna_url].astype(str).str.strip() == '')
                df_filtrado_url = df_final[mascara_url]
                linhas_puladas = len(df_final) - len(df_filtrado_url)
                if linhas_puladas > 0:
                    self.logger.info(f"Puladas {linhas_puladas} linhas que já possuem URL na coluna {coluna_url}.")
                df_final = df_filtrado_url
            else:
                 self.logger.warning(f"Coluna url_documento (índice {coluna_url}) não configurada ou fora dos limites. Não foi possível pular linhas já processadas.")

            # GARANTE ORDEM: Ordena por número de linha ANTES de aplicar o limite
            df_final = df_final.sort_values('sheet_row_num').reset_index(drop=True)

            # Aplica limite de linhas, se especificado, sempre pegando as primeiras disponíveis
            if limite_linhas and len(df_final) > limite_linhas:
                df_final = df_final.iloc[:limite_linhas]
                self.logger.info(f"Leitura limitada a {limite_linhas} linhas, começando da linha {df_final['sheet_row_num'].min()}")
            
            self.logger.info(f"Retornando {len(df_final)} registros para processamento (com coluna sheet_row_num)")
            if not df_final.empty:
                self.logger.info(f"Linhas a serem processadas: {df_final['sheet_row_num'].tolist()}")
            return df_final
        
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