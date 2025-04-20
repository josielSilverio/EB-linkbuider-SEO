# Módulo para interagir com a API do Google Sheets
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
import re

from src.config import (
    SPREADSHEET_ID, 
    SHEET_NAME, 
    COLUNAS, 
    LINHA_INICIAL,
    MES_ATUAL,
    ANO_ATUAL,
    FORMATO_DATA
)
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
    
    def ler_planilha(self, limite_linhas: Optional[int] = None, apenas_dados: bool = False) -> pd.DataFrame:
        """
        Lê a planilha do Google Sheets e retorna os dados como um DataFrame pandas.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas.
            apenas_dados: Se True, retorna todos os dados sem filtrar por data.
        
        Returns:
            DataFrame com os dados da planilha
        """
        try:
            # Obtém a planilha - lemos até a coluna O
            resultado = self.service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:O"
            ).execute()
            
            # Extrai os valores
            valores = resultado.get('values', [])
            
            if not valores:
                self.logger.warning("Nenhum dado encontrado na planilha")
                return pd.DataFrame()
            
            # Converte para DataFrame pandas
            df = pd.DataFrame(valores)
            
            # Começa a partir da linha específica
            if len(df) > LINHA_INICIAL:
                df = df.iloc[LINHA_INICIAL:]
                self.logger.info(f"Começando a partir da linha {LINHA_INICIAL}")
            
            # Se apenas_dados for True, ignoramos o filtro de data
            if not apenas_dados and MES_ATUAL and ANO_ATUAL:
                # Certifica-se de que temos pelo menos 3 colunas
                if len(df.columns) > COLUNAS["DATA"]:
                    coluna_data = COLUNAS["DATA"]
                    # Verifica se a coluna existe no DataFrame
                    if coluna_data < len(df.columns):
                        # Determina o padrão de data com base no formato configurado
                        formato = FORMATO_DATA.lower() if 'FORMATO_DATA' in globals() else 'mm/yyyy'
                        
                        if formato == 'yyyy/mm':
                            padrao_data = f"{ANO_ATUAL}[/-]{MES_ATUAL}"
                            self.logger.info(f"Buscando datas no formato YYYY/MM: {ANO_ATUAL}/{MES_ATUAL}")
                        elif formato == 'yyyy-mm':
                            padrao_data = f"{ANO_ATUAL}-{MES_ATUAL}"
                            self.logger.info(f"Buscando datas no formato YYYY-MM: {ANO_ATUAL}-{MES_ATUAL}")
                        else:  # mm/yyyy ou padrão
                            padrao_data = f"{MES_ATUAL}[/-]{ANO_ATUAL}"
                            self.logger.info(f"Buscando datas no formato MM/YYYY: {MES_ATUAL}/{ANO_ATUAL}")
                        
                        try:
                            # Cria uma máscara booleana para filtrar
                            mascara_mes = df[coluna_data].astype(str).str.contains(padrao_data, regex=True, na=False)
                            df_filtrado = df[mascara_mes]
                            
                            if len(df_filtrado) > 0:
                                df = df_filtrado
                                self.logger.info(f"Filtrado para {len(df)} linhas do período {padrao_data}")
                            else:
                                self.logger.warning(f"Nenhuma linha encontrada para o período {padrao_data}")
                                # IMPORTANTE: Se não achar pelo padrão, vamos procurar por substring simples
                                alternativa = f"{ANO_ATUAL}/{MES_ATUAL}"
                                mascara_alternativa = df[coluna_data].astype(str).str.contains(alternativa, regex=False, na=False)
                                df_alternativo = df[mascara_alternativa]
                                
                                if len(df_alternativo) > 0:
                                    df = df_alternativo
                                    self.logger.info(f"Filtrado para {len(df)} linhas usando busca simples por '{alternativa}'")
                        except Exception as e:
                            self.logger.error(f"Erro ao filtrar por data: {e}")
                            # Continua sem filtrar
                    else:
                        self.logger.warning(f"Coluna DATA (índice {coluna_data}) não encontrada. Continuando sem filtrar por data.")
            elif apenas_dados:
                self.logger.info("Modo 'apenas_dados' ativado: retornando todos os dados sem filtrar por data")
            
            # Aplica limite de linhas se especificado
            if limite_linhas and len(df) > limite_linhas and not apenas_dados:
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
            # Mapeamento usando os índices numéricos das colunas
            # Se o índice existe no DataFrame, usa o valor, senão None
            dados = {
                'id': linha_df.get(COLUNAS["ID"]) if COLUNAS["ID"] in linha_df.index else None,
                'tema': linha_df.get(COLUNAS["TEMA"]) if COLUNAS["TEMA"] in linha_df.index else None,
                'site': linha_df.get(COLUNAS["SITE"]) if COLUNAS["SITE"] in linha_df.index else None,
                'palavra_ancora': linha_df.get(COLUNAS["PALAVRA_ANCORA"]) if COLUNAS["PALAVRA_ANCORA"] in linha_df.index else None,
                'url_ancora': linha_df.get(COLUNAS["URL_ANCORA"]) if COLUNAS["URL_ANCORA"] in linha_df.index else None,
                'titulo': linha_df.get(COLUNAS["TITULO"]) if COLUNAS["TITULO"] in linha_df.index else None
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
    
    def atualizar_url_documento(self, indice_linha: int, url_documento: str) -> bool:
        """
        Atualiza a URL do documento criado na coluna L da planilha.
        
        Args:
            indice_linha: Índice da linha a ser atualizada (relativo ao DataFrame filtrado)
            url_documento: URL do documento do Google Docs
        
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Índice na planilha original é LINHA_INICIAL + índice no DataFrame + 1 (para o cabeçalho)
            linha_sheets = LINHA_INICIAL + indice_linha + 1
            
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

    def atualizar_titulo_documento(self, indice_linha: int, titulo: str) -> bool:
        """
        Atualiza o título do documento na coluna K da planilha.
        
        Args:
            indice_linha: Índice da linha a ser atualizada (relativo ao DataFrame filtrado)
            titulo: Título do documento gerado
        
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Índice na planilha original é LINHA_INICIAL + índice no DataFrame + 1 (para o cabeçalho)
            linha_sheets = LINHA_INICIAL + indice_linha + 1
            
            # Prepara o range para atualização (coluna K)
            range_atualizacao = f"{SHEET_NAME}!K{linha_sheets}"
            
            # Atualiza a célula
            self.service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_atualizacao,
                valueInputOption="RAW",
                body={"values": [[titulo]]}
            ).execute()
            
            self.logger.info(f"Título do documento atualizado na linha {linha_sheets}: {titulo}")
            return True
        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar título do documento na linha {indice_linha}: {e}")
            return False 