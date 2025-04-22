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
    LINHA_INICIAL,
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
            
            df_original = df.copy()  # Cópia para diagnóstico
            
            # Se apenas_dados for True, ignoramos o filtro de data
            if not apenas_dados:
                # Obtém os valores atualizados do ambiente (definidos no menu de seleção de mês)
                mes_atual = os.environ.get('MES_ATUAL', '04')
                ano_atual = os.environ.get('ANO_ATUAL', '2025')
                
                self.logger.info(f"Filtrando por período: {mes_atual}/{ano_atual}")
                
                # Certifica-se de que temos pelo menos 3 colunas
                if len(df.columns) > COLUNAS["data"]:
                    coluna_data = COLUNAS["data"]
                    # Verifica se a coluna existe no DataFrame
                    if coluna_data < len(df.columns):
                        # Examina os valores na coluna de data para diagnóstico
                        valores_unicos = df[coluna_data].astype(str).unique()
                        self.logger.info(f"Valores únicos na coluna data: {valores_unicos[:20]} {'...' if len(valores_unicos) > 20 else ''}")
                        
                        # Determina o padrão de data com base no formato configurado
                        formato = FORMATO_DATA.lower() if FORMATO_DATA else 'yyyy/mm'
                        
                        if formato == 'yyyy/mm':
                            padrao_data = f"{ano_atual}[/-]{mes_atual}"
                            self.logger.info(f"Buscando datas no formato YYYY/MM: {ano_atual}/{mes_atual}")
                        elif formato == 'yyyy-mm':
                            padrao_data = f"{ano_atual}-{mes_atual}"
                            self.logger.info(f"Buscando datas no formato YYYY-MM: {ano_atual}-{mes_atual}")
                        else:  # mm/yyyy ou padrão
                            padrao_data = f"{mes_atual}[/-]{ano_atual}"
                            self.logger.info(f"Buscando datas no formato MM/YYYY: {mes_atual}/{ano_atual}")
                        
                        try:
                            # Lista de padrões para tentar
                            padroes_a_tentar = [
                                (f"{ano_atual}[/-]{mes_atual}", "YYYY/MM (regex)"),
                                (f"{ano_atual}/{mes_atual}", "YYYY/MM (exato)"),
                                (f"{mes_atual}[/-]{ano_atual}", "MM/YYYY (regex)"),
                                (f"{mes_atual}/{ano_atual}", "MM/YYYY (exato)"),
                                (f"{ano_atual}-{mes_atual}", "YYYY-MM (exato)"),
                                (f"{mes_atual}-{ano_atual}", "MM-YYYY (exato)")
                            ]
                            
                            df_filtrado = None
                            
                            # Tenta cada padrão até encontrar registros
                            for padrao, descricao in padroes_a_tentar:
                                # Verifica se é regex ou string literal
                                if '[' in padrao or '\\' in padrao:
                                    mascara = df[coluna_data].astype(str).str.contains(padrao, regex=True, na=False)
                                else:
                                    mascara = df[coluna_data].astype(str).str.contains(padrao, regex=False, na=False)
                                    
                                temp_df = df[mascara]
                                
                                # Se encontrou registros, usa este padrão
                                if len(temp_df) > 0:
                                    df_filtrado = temp_df
                                    self.logger.info(f"Filtrado para {len(df_filtrado)} linhas usando formato {descricao}: '{padrao}'")
                                    break
                            
                            # Se nenhum padrão funcionou
                            if df_filtrado is None or len(df_filtrado) == 0:
                                self.logger.warning(f"Nenhuma linha encontrada para o período {mes_atual}/{ano_atual} em nenhum formato")
                                # Retornar DataFrame vazio em vez de todos os dados quando não encontra registros para o período
                                return pd.DataFrame()
                            else:
                                df = df_filtrado
                        except Exception as e:
                            self.logger.error(f"Erro ao filtrar por data: {e}")
                            self.logger.exception("Detalhes do erro:")
                            # Continua sem filtrar
                    else:
                        self.logger.warning(f"Coluna data (índice {coluna_data}) não encontrada. Continuando sem filtrar por data.")
            else:
                self.logger.info("Modo 'apenas_dados' ativado: retornando todos os dados sem filtrar por data")
            
            # Aplica limite de linhas se especificado
            if limite_linhas and len(df) > limite_linhas and not apenas_dados:
                df = df.iloc[:limite_linhas]
                self.logger.info(f"Leitura limitada a {limite_linhas} linhas")
            
            self.logger.info(f"Lidos {len(df)} registros da planilha de um total de {len(df_original)}")
            return df
        
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