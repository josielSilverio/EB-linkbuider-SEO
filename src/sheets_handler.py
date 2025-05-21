# Módulo para interagir com a API do Google Sheets
import logging
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple

from src.config import (
    SPREADSHEET_ID, 
    SHEET_NAME, 
    COLUNAS_MAPEAMENTO_NOMES
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
            self.sheet_metadata_cache: Dict[Tuple[str, str], Optional[Tuple[int, List[str], Dict[str, Dict[str, Any]]]]] = {}
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

        header_info = self._find_header_and_map_columns(current_spreadsheet_id, current_sheet_name)
        if not header_info:
            self.logger.error(f"Não foi possível obter metadados do cabeçalho para {current_spreadsheet_id}/{current_sheet_name}. Impossível ler a planilha.")
            return pd.DataFrame()
        
        header_row_index_on_sheet, actual_header_content, dynamic_column_map = header_info
        
        # A linha de início para leitura dos DADOS é a linha seguinte ao cabeçalho
        data_start_row_on_sheet = header_row_index_on_sheet + 1 + 1 # +1 para 0-based -> 1-based, +1 para próxima linha

        try:
            # Determinar a última coluna a ser lida com base no cabeçalho encontrado
            num_header_cols = len(actual_header_content)
            if num_header_cols == 0:
                self.logger.error(f"Cabeçalho encontrado em {current_spreadsheet_id}/{current_sheet_name} está vazio. Impossível determinar range.")
                return pd.DataFrame()

            ultima_coluna_letra_header = self.get_column_letter(num_header_cols -1)
            range_para_ler_dados = f"{current_sheet_name}!A{data_start_row_on_sheet}:{ultima_coluna_letra_header}"
            self.logger.info(f"Lendo dados da planilha: '{current_spreadsheet_id}', Aba: '{current_sheet_name}', Range: '{range_para_ler_dados}'")

            result = self.service.spreadsheets().values().get(
                spreadsheetId=current_spreadsheet_id,
                range=range_para_ler_dados
            ).execute()
            data_rows_list = result.get('values', [])

            if not data_rows_list:
                self.logger.warning(f"Nenhum dado encontrado (após cabeçalho) na aba '{current_sheet_name}'.")
                return pd.DataFrame()

            self.logger.info(f"Recebidas {len(data_rows_list)} linhas de dados da API do Google Sheets.")
            
            # Criar DataFrame com os nomes de coluna do cabeçalho real
            df = pd.DataFrame(data_rows_list, columns=actual_header_content)

            # --- FILTRAGENS ---
            # Filtrar por ID válido (se a coluna ID foi mapeada)
            id_col_map_info = dynamic_column_map.get('id')
            if id_col_map_info and id_col_map_info['name'] in df.columns:
                id_col_name = id_col_map_info['name']
                df[id_col_name] = df[id_col_name].astype(str)
                original_row_count = len(df)
                df = df[df[id_col_name].notna() & (df[id_col_name].str.strip() != '')]
                self.logger.info(f"{original_row_count - len(df)} linhas removidas por ID inválido/vazio (coluna '{id_col_name}'). {len(df)} linhas restantes.")
            else:
                self.logger.warning("Coluna 'id' não mapeada ou não encontrada no DataFrame. Não foi possível filtrar por IDs válidos.")

            # Filtrar itens já processados (se a coluna url_documento foi mapeada)
            if filtrar_processados:
                url_doc_col_map_info = dynamic_column_map.get('url_documento')
                if url_doc_col_map_info and url_doc_col_map_info['name'] in df.columns:
                    url_doc_col_name = url_doc_col_map_info['name']
                    df[url_doc_col_name] = df[url_doc_col_name].astype(str)
                    original_row_count = len(df)
                    df = df[df[url_doc_col_name].fillna('').str.strip() == '']
                    self.logger.info(f"{original_row_count - len(df)} linhas removidas por já terem URL (coluna '{url_doc_col_name}'). {len(df)} linhas restantes.")
                else:
                    self.logger.warning("Coluna 'url_documento' não mapeada ou não encontrada. Não foi possível filtrar por itens já processados.")
            else:
                self.logger.info("Filtragem de itens já processados foi pulada.")
            
            if df.empty:
                self.logger.warning("Nenhuma linha restante após as filtragens de ID e URL.")
                return pd.DataFrame()

            # Adicionar 'sheet_row_num' (1-based, número da linha original na planilha)
            # df.index é 0-based para as linhas de DADOS lidas.
            # data_start_row_on_sheet é 1-based e é a primeira linha de DADOS na planilha.
            df['sheet_row_num'] = df.index + data_start_row_on_sheet
            df = df.sort_values(by='sheet_row_num').reset_index(drop=True) # Garante ordem e reseta índice
                                                                        
            self.logger.info(f"DataFrame preparado com {len(df)} linhas antes do filtro de 'linha_inicial' da planilha. Próximas (sheet_row_num): {df['sheet_row_num'].head().tolist() if not df.empty else 'N/A'}")

            # Aplicar filtro de linha_inicial (1-based, da planilha), se especificado
            if linha_inicial is not None and isinstance(linha_inicial, int) and linha_inicial >= data_start_row_on_sheet:
                self.logger.info(f"Aplicando filtro para começar a partir da linha da planilha: {linha_inicial}")
                df = df[df['sheet_row_num'] >= linha_inicial]
                df = df.reset_index(drop=True) 
                if df.empty:
                    self.logger.warning(f"Nenhuma linha restante após filtrar pela linha inicial da planilha {linha_inicial}.")
                else:
                    self.logger.info(f"{len(df)} linhas restantes após filtro de linha inicial da planilha. Próximas (sheet_row_num): {df['sheet_row_num'].head().tolist()}")
            elif linha_inicial is not None:
                 self.logger.warning(f"Parâmetro 'linha_inicial' ({linha_inicial}) é inválido ou anterior ao início dos dados ({data_start_row_on_sheet}). Ignorando.")

            # Aplicar limite_linhas
            if limite_linhas is not None and isinstance(limite_linhas, int) and limite_linhas > 0:
                if not df.empty and limite_linhas < len(df):
                    self.logger.info(f"Aplicando limite de {limite_linhas} linhas ao DataFrame resultante.")
                    df = df.head(limite_linhas)
                self.logger.info(f"{len(df)} linhas no DataFrame final após todos os filtros e limites.")
            
            # O argumento 'apenas_dados' parece não fazer mais sentido com o retorno de DataFrame
            # Se precisar de uma lista de listas, pode ser df.values.tolist() no final.
            # Por ora, a função sempre retorna um DataFrame.
            return df

        except Exception as e:
            self.logger.error(f"Erro ao ler a planilha '{current_spreadsheet_id}/{current_sheet_name}': {e}")
            self.logger.exception("Detalhes do erro em ler_planilha:")
            return pd.DataFrame() # Retorna DataFrame vazio em caso de erro

    def extrair_dados_linha(self, linha_df: pd.Series, dynamic_column_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extrai os dados relevantes de uma linha do DataFrame, usando o mapeamento dinâmico de colunas.
        """
        dados: Dict[str, Any] = {}
        try:
            for internal_key, map_info in dynamic_column_map.items():
                actual_col_name = map_info['name']
                if actual_col_name in linha_df.index:
                    dados[internal_key] = linha_df[actual_col_name]
                else:
                    # Se a coluna esperada (mesmo que mapeada) não estiver na linha_df (pouco provável se linha_df vem de ler_planilha)
                    dados[internal_key] = None 
                    self.logger.debug(f"Coluna '{actual_col_name}' (para chave interna '{internal_key}') não encontrada na linha_df fornecida.")
            
            # Limpeza básica ou preenchimento de defaults
            # As chaves em 'dados' agora são as chaves internas do script
            cleaned_dados: Dict[str, str] = {}
            for internal_key in COLUNAS_MAPEAMENTO_NOMES.keys(): # Iterar sobre todas as chaves internas esperadas
                value = dados.get(internal_key)
                cleaned_dados[internal_key] = str(value).strip() if value and str(value).strip() else "" # "" em vez de "Sem {k}"
                                
            return cleaned_dados
        
        except Exception as e:
            self.logger.error(f"Erro ao extrair dados da linha com mapeamento dinâmico: {e}")
            self.logger.error(f"Linha fornecida (índices): {linha_df.index.tolist() if isinstance(linha_df, pd.Series) else 'Não é Series'}")
            self.logger.error(f"Mapeamento dinâmico: {dynamic_column_map}")
            # Retorna um dict parcialmente preenchido ou vazio para evitar quebrar o fluxo, mas loga o erro.
            # É importante que as chaves internas existam, mesmo que com valor vazio.
            fallback_dados = {key: "" for key in COLUNAS_MAPEAMENTO_NOMES.keys()}
            return fallback_dados

    def _find_header_and_map_columns(self, spreadsheet_id: str, sheet_name: str) -> Optional[Tuple[int, List[str], Dict[str, Dict[str, Any]]]]:
        cache_key = (spreadsheet_id, sheet_name)
        if cache_key in self.sheet_metadata_cache:
            self.logger.info(f"Metadados do cabeçalho encontrados no cache para {spreadsheet_id}/{sheet_name}.")
            return self.sheet_metadata_cache[cache_key]

        self.logger.info(f"Procurando cabeçalho em {spreadsheet_id}/{sheet_name}...")
        try:
            # Ler um bloco inicial da planilha para encontrar o cabeçalho (ex: primeiras 20 linhas)
            # O range A:Z é uma simplificação, idealmente seria até a última coluna com dados, mas para achar o header costuma ser suficiente.
            # Limitamos a 20 linhas para não ler a planilha inteira só para achar o header.
            range_to_scan_header = f"{sheet_name}!A1:Z20" 
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_to_scan_header
            ).execute()
            rows_for_header_scan = result.get('values', [])

            if not rows_for_header_scan:
                self.logger.error(f"Nenhuma linha encontrada na planilha {spreadsheet_id}/{sheet_name} para escanear o cabeçalho.")
                return None

            best_header_row_index = -1
            best_header_row_content: List[str] = []
            max_score = 0
            temp_dynamic_column_map: Dict[str, Dict[str, Any]] = {}

            MIN_MATCHING_HEADERS = 3 # Pelo menos 3 colunas conhecidas devem bater

            for i, row_list in enumerate(rows_for_header_scan):
                current_score = 0
                current_temp_map: Dict[str, Dict[str, Any]] = {}
                # Preencher com strings vazias se a linha for mais curta que outras, para consistência
                # Isso é importante se algumas linhas de cabeçalho candidatas tiverem menos colunas que outras.
                # No entanto, a linha de cabeçalho REAL deve ter todos os seus nomes.
                # A normalização de tamanho não é feita aqui, mas sim ao construir o DF.
                
                # Limpar e normalizar os nomes na linha atual para comparação
                cleaned_row_headers = [str(h).strip().lower() for h in row_list if str(h).strip()] # Ignora vazios na contagem/comparação
                
                # Não considera linhas com poucas colunas preenchidas como cabeçalho potencial
                if len(cleaned_row_headers) < MIN_MATCHING_HEADERS:
                    continue

                # Verifica quantas colunas da nossa configuração batem com esta linha
                possible_internal_keys_found = set()
                for internal_key, config_info in COLUNAS_MAPEAMENTO_NOMES.items():
                    possible_names_for_key = config_info.get('nomes', [])
                    # Encontrar a primeira correspondência para esta internal_key na linha atual da planilha
                    found_match_for_this_internal_key = False
                    for header_idx, header_name_on_sheet_raw in enumerate(row_list):
                        header_name_on_sheet = str(header_name_on_sheet_raw).strip()
                        if not header_name_on_sheet: # Pula células de cabeçalho vazias
                            continue
                        
                        for pn_config in possible_names_for_key:
                            if pn_config.lower() == header_name_on_sheet.lower():
                                # Match! Se já mapeamos essa internal_key com outra coluna, não sobrescrever.
                                # A prioridade é dada pela ordem em COLUNAS_MAPEAMENTO_NOMES e a primeira coluna correspondente.
                                if internal_key not in current_temp_map: 
                                    current_temp_map[internal_key] = {
                                        'name': header_name_on_sheet, # Nome original da planilha
                                        'index_in_header': header_idx # Índice 0-based na linha do cabeçalho
                                    }
                                    possible_internal_keys_found.add(internal_key)
                                    found_match_for_this_internal_key = True
                                    break # Passa para a próxima internal_key
                        if found_match_for_this_internal_key:
                            break # Já achou esta internal_key na linha, vai para a próxima internal_key
                
                current_score = len(possible_internal_keys_found)

                if current_score >= MIN_MATCHING_HEADERS and current_score > max_score:
                    max_score = current_score
                    best_header_row_index = i
                    best_header_row_content = [str(h).strip() for h in row_list] # Conteúdo original, com strip
                    temp_dynamic_column_map = current_temp_map
            
            if best_header_row_index == -1:
                self.logger.error(f"Nenhuma linha de cabeçalho válida encontrada em {spreadsheet_id}/{sheet_name} com pelo menos {MIN_MATCHING_HEADERS} colunas correspondentes.")
                return None

            self.logger.info(f"Cabeçalho encontrado na linha {best_header_row_index + 1} da planilha (índice 0-based: {best_header_row_index}) com pontuação {max_score}.")

            # Garantir nomes de coluna únicos para o DataFrame e atualizar o mapa
            # best_header_row_content pode ter menos colunas que o DataFrame final se houver colunas vazias à direita no cabeçalho
            # mas dados abaixo. `pd.DataFrame` lidará com isso, mas é bom ter os nomes exatos que serão usados.
            
            final_unique_header_names: List[str] = []
            name_counts: Dict[str, int] = {}
            # Pad o best_header_row_content para o número máximo de colunas que podem existir, se soubermos.
            # Por enquanto, vamos apenas unificar o que temos em best_header_row_content.
            # Se a linha de cabeçalho for curta, colunas de dados sem nome de cabeçalho serão numeradas pelo pandas.
            
            for original_header_name in best_header_row_content:
                if not original_header_name: # Tratar nomes de cabeçalho vazios como "Unnamed_X"
                    col_idx_for_unnamed = len(final_unique_header_names)
                    unique_name = f"Unnamed_{col_idx_for_unnamed}"
                    while unique_name in name_counts: # Garantir que até o Unnamed seja único
                        col_idx_for_unnamed +=1
                        unique_name = f"Unnamed_{col_idx_for_unnamed}"
                    name_counts[unique_name] = 1
                    final_unique_header_names.append(unique_name)
                    continue

                if original_header_name in name_counts:
                    name_counts[original_header_name] += 1
                    unique_name = f"{original_header_name}.{name_counts[original_header_name]-1}"
                    # Garantir que o nome gerado (ex: Col.1) também não colida se "Col.1" já existir como nome original
                    while unique_name in name_counts:
                         unique_name = f"{unique_name}.dup"
                else:
                    name_counts[original_header_name] = 1
                    unique_name = original_header_name
                final_unique_header_names.append(unique_name)
            
            # Atualizar o `temp_dynamic_column_map` para usar os nomes unificados
            final_dynamic_column_map: Dict[str, Dict[str, Any]] = {}
            for internal_key, map_info in temp_dynamic_column_map.items():
                original_index = map_info['index_in_header']
                if 0 <= original_index < len(final_unique_header_names):
                    map_info['name'] = final_unique_header_names[original_index]
                    final_dynamic_column_map[internal_key] = map_info
                else:
                    self.logger.warning(f"Erro de índice ao tentar mapear nome único para {internal_key}. Índice {original_index} fora do range de cabeçalhos únicos {len(final_unique_header_names)}.")

            self.logger.info(f"Mapeamento de colunas dinâmico criado para {spreadsheet_id}/{sheet_name}: {final_dynamic_column_map}")
            self.logger.debug(f"Conteúdo do cabeçalho (nomes únicos): {final_unique_header_names}")
            
            # Adiciona ao cache
            self.sheet_metadata_cache[cache_key] = (best_header_row_index, final_unique_header_names, final_dynamic_column_map)
            return best_header_row_index, final_unique_header_names, final_dynamic_column_map

        except Exception as e:
            self.logger.error(f"Erro ao tentar encontrar cabeçalho ou mapear colunas para {spreadsheet_id}/{sheet_name}: {e}")
            self.logger.exception("Detalhes do erro em _find_header_and_map_columns:")
            return None

    def _get_column_letter_for_internal_key(self, internal_key: str, spreadsheet_id: str, sheet_name: str) -> Optional[str]:
        """Helper para obter a letra da coluna para uma chave interna."""
        header_info = self._find_header_and_map_columns(spreadsheet_id, sheet_name)
        if not header_info:
            self.logger.error(f"Não foi possível obter metadados do cabeçalho para {spreadsheet_id}/{sheet_name} ao tentar encontrar a letra da coluna para '{internal_key}'.")
            return None
        _, _, dynamic_column_map = header_info
        
        col_info = dynamic_column_map.get(internal_key)
        if not col_info or 'index_in_header' not in col_info:
            self.logger.error(f"Chave interna '{internal_key}' não encontrada no mapeamento de colunas ou falta 'index_in_header' para {spreadsheet_id}/{sheet_name}.")
            return None
        
        try:
            return self.get_column_letter(col_info['index_in_header'])
        except ValueError as e:
            self.logger.error(f"Erro ao converter índice de coluna para letra para '{internal_key}': {e}")
            return None

    def atualizar_url_documento(self, sheet_row_num: int, url_documento: str, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None) -> bool:
        current_spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
        current_sheet_name = sheet_name or SHEET_NAME

        if not current_spreadsheet_id or not current_sheet_name:
            self.logger.error("ID da planilha ou nome da aba não especificados para atualizar_url_documento.")
            return False

        col_letter = self._get_column_letter_for_internal_key('url_documento', current_spreadsheet_id, current_sheet_name)
        if not col_letter:
            self.logger.error(f"Não foi possível determinar a coluna para 'url_documento' em {current_spreadsheet_id}/{current_sheet_name}.")
            return False
            
        range_atualizacao = f"{current_sheet_name}!{col_letter}{sheet_row_num}"
        self.logger.info(f"Preparando para atualizar URL na Planilha: {current_spreadsheet_id}, Aba: '{current_sheet_name}', Célula: {col_letter}{sheet_row_num}, URL: '{url_documento}'")
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=current_spreadsheet_id,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",
                body={"values": [[url_documento]]}
            ).execute()
            self.logger.info(f"✓ URL atualizada com sucesso em {range_atualizacao}.")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao atualizar URL na linha {sheet_row_num} (Range: {range_atualizacao}): {e}")
            return False

    def atualizar_titulo_documento(self, sheet_row_num: int, titulo: str, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None) -> bool:
        current_spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
        current_sheet_name = sheet_name or SHEET_NAME

        if not current_spreadsheet_id or not current_sheet_name:
            self.logger.error("ID da planilha ou nome da aba não especificados para atualizar_titulo_documento.")
            return False

        col_letter = self._get_column_letter_for_internal_key('titulo', current_spreadsheet_id, current_sheet_name)
        if not col_letter:
            self.logger.error(f"Não foi possível determinar a coluna para 'titulo' em {current_spreadsheet_id}/{current_sheet_name}.")
            return False

        range_atualizacao = f"{current_sheet_name}!{col_letter}{sheet_row_num}"
        self.logger.info(f"Preparando para atualizar Título na Planilha: {current_spreadsheet_id}, Aba: '{current_sheet_name}', Célula: {col_letter}{sheet_row_num}, Título: '{titulo}'")
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=current_spreadsheet_id,
                range=range_atualizacao,
                valueInputOption="USER_ENTERED",
                body={"values": [[titulo]]}
            ).execute()
            self.logger.info(f"✓ Título atualizado com sucesso em {range_atualizacao}.")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao atualizar título na linha {sheet_row_num} (Range: {range_atualizacao}): {e}")
            return False

    def carregar_dados_planilha(self, spreadsheet_id: str, sheet_name: str) -> Optional[pd.DataFrame]:
        """
        Carrega dados da planilha do Google Sheets.
        
        Args:
            spreadsheet_id: ID da planilha
            sheet_name: Nome da aba
            
        Returns:
            DataFrame com os dados da planilha ou None em caso de erro
        """
        try:
            # Obtém os dados da planilha
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:Z"  # Lê todas as colunas de A até Z
            ).execute()
            
            values = result.get('values', [])
            if not values:
                self.logger.warning("Nenhum dado encontrado na planilha")
                return None
                
            # Encontra o cabeçalho e mapeia as colunas
            header_info = self._find_header_and_map_columns(spreadsheet_id, sheet_name)
            if not header_info:
                self.logger.error("Não foi possível encontrar o cabeçalho da planilha")
                return None
                
            header_row, header_values, self.dynamic_column_map = header_info
            
            # Cria o DataFrame
            df = pd.DataFrame(values[header_row + 1:], columns=header_values)
            
            # Adiciona número da linha na planilha para referência
            df['sheet_row_num'] = range(header_row + 2, len(values) + 1)
            
            self.logger.info(f"Dados carregados com sucesso: {len(df)} linhas")
            return df
            
        except Exception as e:
            self.logger.error(f"Erro ao carregar dados da planilha: {e}")
            return None