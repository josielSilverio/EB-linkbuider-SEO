# Módulo para interagir com a API do Google Sheets
import logging
import pandas as pd
from typing import List, Dict, Any, Optional

from src.config import SPREADSHEET_ID, SHEET_NAME, COLUNAS
from src.auth_handler import obter_credenciais, criar_servico_sheets

class SheetsHandler:
    def __init__(self):
        # Inicializa o logger
        self.logger = logging.getLogger('seo_linkbuilder.sheets')
        
        # Obtém credenciais e inicializa o serviço
        try:
            self.credenciais = obter_credenciais()
            self.service = criar_servico_sheets(self.credenciais)
            self.logger.info("Serviço do Google Sheets inicializado com sucesso")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar o serviço do Sheets: {e}")
            raise
    
    def ler_planilha(self, limite_linhas: Optional[int] = None) -> pd.DataFrame:
        """
        Lê a planilha do Google Sheets e retorna os dados como um DataFrame pandas.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas.
        
        Returns:
            DataFrame com os dados da planilha
        """
        try:
            # Obtém a planilha
            resultado = self.service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:L"  # Use a faixa de colunas conforme necessário
            ).execute()
            
            # Extrai os valores
            valores = resultado.get('values', [])
            
            if not valores:
                self.logger.warning("Nenhum dado encontrado na planilha")
                return pd.DataFrame()
            
            # Converte para DataFrame pandas
            df = pd.DataFrame(valores)
            
            # Assume a primeira linha como cabeçalho
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            # Aplica limite de linhas se especificado
            if limite_linhas and len(df) > limite_linhas:
                df = df.iloc[:limite_linhas]
                self.logger.info(f"Leitura limitada a {limite_linhas} linhas")
            
            self.logger.info(f"Lidos {len(df)} registros da planilha")
            return df
        
        except Exception as e:
            self.logger.error(f"Erro ao ler a planilha: {e}")
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
            # Mapeamento usando as constantes de colunas
            dados = {
                'tema': linha_df.get(COLUNAS["TEMA"]),
                'site': linha_df.get(COLUNAS["SITE"]),
                'palavra_ancora': linha_df.get(COLUNAS["PALAVRA_ANCORA"]),
                'url_ancora': linha_df.get(COLUNAS["URL_ANCORA"]),
                'titulo': linha_df.get(COLUNAS["TITULO"])
            }
            
            # Verifica se algum dado obrigatório está nulo
            campos_obrigatorios = ['tema', 'palavra_ancora', 'url_ancora', 'titulo']
            campos_nulos = [campo for campo in campos_obrigatorios if not dados.get(campo)]
            
            if campos_nulos:
                self.logger.warning(f"Campos obrigatórios nulos: {', '.join(campos_nulos)}")
            
            return dados
        
        except Exception as e:
            self.logger.error(f"Erro ao extrair dados da linha: {e}")
            raise
    
    def atualizar_url_documento(self, indice_linha: int, url_documento: str) -> bool:
        """
        Atualiza a URL do documento criado na coluna L da planilha.
        
        Args:
            indice_linha: Índice da linha a ser atualizada (1-indexed, conforme o Google Sheets)
            url_documento: URL do documento do Google Docs
        
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Índice na planilha é 1-indexed, mas o DataFrame é 0-indexed
            # Adicione 2 para compensar (1 para o header + 1 para o índice 1-based)
            linha_sheets = indice_linha + 2
            
            # Prepara o range para atualização (coluna L)
            range_atualizacao = f"{SHEET_NAME}!{COLUNAS['CONTEUDO_DRIVE']}{linha_sheets}"
            
            # Atualiza a célula
            self.service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_atualizacao,
                valueInputOption="RAW",
                body={"values": [[url_documento]]}
            ).execute()
            
            self.logger.info(f"URL do documento atualizada na linha {linha_sheets}: {url_documento}")
            return True
        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar URL do documento na linha {indice_linha}: {e}")
            return False 