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
    ANO_ATUAL
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
    
    def ler_planilha(self, limite_linhas: Optional[int] = None) -> pd.DataFrame:
        """
        Lê a planilha do Google Sheets e retorna os dados como um DataFrame pandas.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas.
        
        Returns:
            DataFrame com os dados da planilha
        """
        try:
            # Obtém a planilha - agora lemos mais colunas (até N)
            resultado = self.service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:O"  # Ampliado para incluir coluna N (tema)
            ).execute()
            
            # Extrai os valores
            valores = resultado.get('values', [])
            
            if not valores:
                self.logger.warning("Nenhum dado encontrado na planilha")
                return pd.DataFrame()
            
            # Converte para DataFrame pandas
            df = pd.DataFrame(valores)
            
            # Inicializa as colunas com índices numéricos
            # (não usamos os nomes das colunas porque vamos trabalhar com índices)
            
            # Começa a partir da linha específica
            if len(df) > LINHA_INICIAL:
                df = df.iloc[LINHA_INICIAL:]
                self.logger.info(f"Começando a partir da linha {LINHA_INICIAL}")
            
            # Filtra apenas as linhas do mês atual (usando a coluna C - DATA)
            if MES_ATUAL and ANO_ATUAL:
                # Certifica-se de que temos pelo menos 3 colunas
                if len(df.columns) > COLUNAS["DATA"]:
                    # Filtra por padrão de data (MM/YYYY ou MM-YYYY ou YYYY-MM)
                    padrao_data = f"{MES_ATUAL}[/-]{ANO_ATUAL}|{ANO_ATUAL}[/-]{MES_ATUAL}"
                    
                    # Cria uma máscara booleana para filtrar
                    mascara_mes = df[COLUNAS["DATA"]].astype(str).str.contains(padrao_data, regex=True, na=False)
                    df_filtrado = df[mascara_mes]
                    
                    if len(df_filtrado) > 0:
                        df = df_filtrado
                        self.logger.info(f"Filtrado para {len(df)} linhas do mês {MES_ATUAL}/{ANO_ATUAL}")
                    else:
                        self.logger.warning(f"Nenhuma linha encontrada para o mês {MES_ATUAL}/{ANO_ATUAL}")
            
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
            
            # Verifica se algum dado obrigatório está sem valor significativo
            campos_obrigatorios = ['tema', 'palavra_ancora', 'url_ancora', 'titulo']
            campos_nulos = [campo for campo in campos_obrigatorios if dados.get(campo).startswith("Sem ")]
            
            if campos_nulos:
                self.logger.warning(f"Campos obrigatórios nulos: {', '.join(campos_nulos)}")
            
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