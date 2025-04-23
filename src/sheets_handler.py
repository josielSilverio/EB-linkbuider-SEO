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
    
    def obter_planilhas_disponiveis(self):
        """
        Obtém a lista de planilhas disponíveis na conta do usuário.
        
        Returns:
            Lista de dicionários com informações das planilhas (id, nome)
        """
        try:
            # Lista todas as planilhas
            resultado = self.service.files().list(
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
        Filtra apenas linhas que tenham IDs válidos.
        
        Args:
            limite_linhas: Opcional. Limita o número de linhas a serem lidas.
            apenas_dados: Se True, retorna todos os dados sem aplicar filtros adicionais.
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
        
        Returns:
            DataFrame com os dados da planilha
        """
        try:
            # Usa os IDs fornecidos ou os configurados
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            
            self.logger.info(f"Tentando ler planilha {id_planilha}, aba {nome_aba}")
            
            # Obtém a planilha - lemos até a coluna O
            resultado = self.service.spreadsheets().values().get(
                spreadsheetId=id_planilha,
                range=f"{nome_aba}!A:O"
            ).execute()
            
            # Extrai os valores
            valores = resultado.get('values', [])
            
            if not valores:
                self.logger.warning(f"Nenhum dado encontrado na planilha {id_planilha}, aba {nome_aba}")
                return pd.DataFrame()
            
            # Exibe informação sobre a quantidade de linhas lidas
            self.logger.info(f"Lidas {len(valores)} linhas da planilha no total")
            
            # Converte para DataFrame pandas
            df = pd.DataFrame(valores)
            
            # Preserva a primeira linha como cabeçalho para referência
            cabecalho = df.iloc[0].copy() if len(df) > 0 else None
            self.logger.info(f"Cabeçalho identificado: {cabecalho.values.tolist() if cabecalho is not None else 'Nenhum'}")
            
            # Remove a linha de cabeçalho (sempre primeiro depois da conversão para DataFrame)
            if len(df) > 1:
                df = df.iloc[1:]
                self.logger.info(f"Removendo linha de cabeçalho, restam {len(df)} linhas")
            
            # Garante que as linhas mantenham seus índices originais
            df = df.reset_index(drop=True)
            df_original = df.copy()  # Cópia para diagnóstico
            
            # Se apenas_dados for False, aplicamos o filtro para linhas com ID válido
            if not apenas_dados and len(df.columns) > 0:
                # Verifica se a coluna ID existe no DataFrame
                if len(df.columns) > COLUNAS["id"]:
                    coluna_id = COLUNAS["id"]
                    
                    # Filtra linhas que tenham um ID válido (não vazio e não um cabeçalho)
                    def is_valid_id(id_value):
                        if not id_value:  # Se for None ou string vazia
                            return False
                        id_str = str(id_value).strip().lower()
                        # Verifica se não é um cabeçalho ou valor inválido
                        if not id_str or id_str in ['id', 'identificador', 'código', 'code', 'none', 'nan', '#n/a', 'n/a']:
                            return False
                        return True
                    
                    # Aplica o filtro de ID
                    if len(df) > 0:
                        mascara = df[coluna_id].apply(is_valid_id)
                        df_filtrado = df[mascara]
                        
                        # Preserva os índices originais
                        df_filtrado = df_filtrado.reset_index(drop=False).rename(columns={'index': 'linha_original'})
                        
                        self.logger.info(f"Filtrado para {len(df_filtrado)} linhas com IDs válidos de {len(df)} linhas")
                        
                        # Exibe as primeiras linhas filtradas para diagnóstico
                        if len(df_filtrado) > 0:
                            primeiras_linhas = df_filtrado.head(3)
                            self.logger.info(f"Primeiras linhas filtradas (com índices originais): \n{primeiras_linhas}")
                        
                        df = df_filtrado
                else:
                    self.logger.warning(f"Coluna ID (índice {COLUNAS['id']}) não encontrada. Continuando sem filtrar.")
            else:
                self.logger.info("Modo 'apenas_dados' ativado: retornando todos os dados sem filtrar")
            
            # Aplica limite de linhas se especificado
            if limite_linhas and len(df) > limite_linhas and not apenas_dados:
                df = df.iloc[:limite_linhas]
                self.logger.info(f"Leitura limitada a {limite_linhas} linhas")
            
            self.logger.info(f"Lidos {len(df)} registros filtrados da planilha de um total de {len(df_original)}")
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
    
    def atualizar_url_documento(self, indice_linha: int, url_documento: str, spreadsheet_id=None, sheet_name=None) -> bool:
        """
        Atualiza a URL do documento criado na coluna correspondente da planilha.
        
        Args:
            indice_linha: Índice da linha a ser atualizada (relativo ao DataFrame filtrado)
            url_documento: URL do documento do Google Docs
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
            
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Usa os IDs fornecidos ou os configurados
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            
            # Verificamos se o índice pode já ser real (baseado em 0)
            # Na maioria dos casos, estamos recebendo o índice_real, que corresponde à linha na planilha
            # O índice na planilha é o índice + 2 (1 para linha de cabeçalho + 1 para índice baseado em 1)
            linha_sheets = indice_linha + 2
            
            # Mapeia diretamente para a coluna J (URL do documento)
            coluna_url = 'J'
            
            # Prepara o range para atualização 
            range_atualizacao = f"{nome_aba}!{coluna_url}{linha_sheets}"
            
            self.logger.info(f"Atualizando URL do documento na planilha {id_planilha}, aba '{nome_aba}'")
            self.logger.info(f"Range: {range_atualizacao} (célula {coluna_url}{linha_sheets})")
            self.logger.info(f"Índice original: {indice_linha}, índice ajustado: {linha_sheets}")
            self.logger.info(f"URL a ser inserida: {url_documento}")
            
            # Verifica se a aba existe antes de tentar atualizar
            abas = self.obter_abas_disponiveis(id_planilha)
            aba_encontrada = False
            nomes_abas = []
            
            for aba in abas:
                nome_aba_atual = aba.get('titulo', '')
                nomes_abas.append(nome_aba_atual)
                if nome_aba_atual == nome_aba:
                    aba_encontrada = True
            
            if not aba_encontrada:
                self.logger.error(f"Aba '{nome_aba}' não encontrada na planilha. Abas disponíveis: {nomes_abas}")
                return False
            
            # Atualiza a célula
            resultado = self.service.spreadsheets().values().update(
                spreadsheetId=id_planilha,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",  # Alterado para USER_ENTERED para processar links corretamente
                body={"values": [[url_documento]]}
            ).execute()
            
            if 'updatedRange' in resultado:
                self.logger.info(f"URL atualizada com sucesso na range: {resultado['updatedRange']}")
            else:
                self.logger.warning(f"URL atualizada, mas sem confirmação da range específica.")
            
            self.logger.info(f"URL do documento atualizada com sucesso na planilha")
            self.logger.debug(f"Detalhes do resultado da atualização: {resultado}")
            return True
        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar URL do documento na linha {indice_linha}: {e}")
            self.logger.exception("Detalhes do erro:")
            return False

    def atualizar_titulo_documento(self, indice_linha: int, titulo: str, spreadsheet_id=None, sheet_name=None) -> bool:
        """
        Atualiza o título do documento na coluna correspondente da planilha.
        
        Args:
            indice_linha: Índice da linha a ser atualizada (relativo ao DataFrame filtrado)
            titulo: Título do documento gerado
            spreadsheet_id: ID da planilha. Se None, usa o ID configurado no .env
            sheet_name: Nome da aba. Se None, usa o nome configurado no .env
            
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Usa os IDs fornecidos ou os configurados
            id_planilha = spreadsheet_id or SPREADSHEET_ID
            nome_aba = sheet_name or SHEET_NAME
            
            # Verificamos se o índice pode já ser real (baseado em 0)
            # Na maioria dos casos, estamos recebendo o índice_real, que corresponde à linha na planilha
            # O índice na planilha é o índice + 2 (1 para linha de cabeçalho + 1 para índice baseado em 1)
            linha_sheets = indice_linha + 2
            
            # Mapeia diretamente para a coluna I (Tema/Título)
            coluna_titulo = 'I'
            
            # Prepara o range para atualização
            range_atualizacao = f"{nome_aba}!{coluna_titulo}{linha_sheets}"
            
            self.logger.info(f"Atualizando título do documento na planilha {id_planilha}, aba '{nome_aba}'")
            self.logger.info(f"Range: {range_atualizacao} (célula {coluna_titulo}{linha_sheets})")
            self.logger.info(f"Índice original: {indice_linha}, índice ajustado: {linha_sheets}")
            self.logger.info(f"Título a ser inserido: {titulo}")
            
            # Verifica se a aba existe antes de tentar atualizar
            abas = self.obter_abas_disponiveis(id_planilha)
            aba_encontrada = False
            nomes_abas = []
            
            for aba in abas:
                nome_aba_atual = aba.get('titulo', '')
                nomes_abas.append(nome_aba_atual)
                if nome_aba_atual == nome_aba:
                    aba_encontrada = True
            
            if not aba_encontrada:
                self.logger.error(f"Aba '{nome_aba}' não encontrada na planilha. Abas disponíveis: {nomes_abas}")
                return False
            
            # Atualiza a célula
            resultado = self.service.spreadsheets().values().update(
                spreadsheetId=id_planilha,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",  # Alterado para USER_ENTERED para garantir formatação correta
                body={"values": [[titulo]]}
            ).execute()
            
            if 'updatedRange' in resultado:
                self.logger.info(f"Título atualizado com sucesso na range: {resultado['updatedRange']}")
            else:
                self.logger.warning(f"Título atualizado, mas sem confirmação da range específica.")
            
            self.logger.info(f"Título do documento atualizado com sucesso na planilha")
            self.logger.debug(f"Detalhes do resultado da atualização: {resultado}")
            return True
        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar título do documento na linha {indice_linha}: {e}")
            self.logger.exception("Detalhes do erro:")
            return False 