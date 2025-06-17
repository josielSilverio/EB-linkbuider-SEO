import logging
import time
from typing import Dict, List, Optional, Tuple
import pandas as pd
from src.config import config
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler
from src.docs_handler import DocsHandler
from src.utils import substituir_links_markdown
import re

logger = logging.getLogger('seo_linkbuilder.processor')

class ContentProcessor:
    def __init__(self, sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler):
        self.sheets = sheets
        self.gemini = gemini
        self.docs = docs
        self.titulos_gerados = []
        self.linhas_processadas = 0

    def processar_linhas(self, df: pd.DataFrame, dynamic_column_map: Dict, 
                        modo_teste: bool = False, limite_linhas: Optional[int] = None,
                        modo_processamento: str = "3", id_inicial: Optional[str] = None,
                        spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
        """Processa as linhas selecionadas de acordo com o modo escolhido"""
        try:
            # Filtra o DataFrame se houver ID inicial
            if id_inicial:
                df = self._filtrar_por_id_inicial(df, id_inicial, dynamic_column_map)
                if df is None:
                    return

            # Primeira etapa: Geração de títulos
            if modo_processamento in ["1", "3"]:
                self._processar_titulos(df, dynamic_column_map, limite_linhas, spreadsheet_id, sheet_name)

            # Segunda etapa: Geração de conteúdos
            if modo_processamento in ["2", "3"]:
                self._processar_conteudos(df, dynamic_column_map, limite_linhas, spreadsheet_id, sheet_name)

        except Exception as e:
            logger.error(f"Erro durante o processamento: {e}")
            raise

    def _filtrar_por_id_inicial(self, df: pd.DataFrame, id_inicial: str, 
                              dynamic_column_map: Dict) -> Optional[pd.DataFrame]:
        """Filtra DataFrame por ID inicial"""
        col_id = dynamic_column_map['id']['name'] if isinstance(dynamic_column_map['id'], dict) else dynamic_column_map['id']
        df = df.reset_index(drop=True)
        idx_inicio = df.index[df[col_id] == id_inicial].tolist()
        if not idx_inicio:
            logger.warning(f"Nenhuma linha encontrada com ID {id_inicial}")
            return None
        return df.iloc[idx_inicio[0]:]

    def _processar_titulos(self, df: pd.DataFrame, dynamic_column_map: Dict, 
                          limite_linhas: Optional[int] = None, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
        """Processa geração de títulos"""
        logger.info("Iniciando primeira etapa: Geração de títulos")
        col_titulo = dynamic_column_map['titulo']['name'] if isinstance(dynamic_column_map['titulo'], dict) else dynamic_column_map['titulo']
        
        for idx, row in df.iterrows():
            if self._deve_pular_linha(row, col_titulo, limite_linhas):
                continue

            dados = self.sheets.extrair_dados_linha(row, dynamic_column_map)
            titulo_escolhido = self._gerar_titulo(dados)
            
            if titulo_escolhido:
                self._salvar_titulo(titulo_escolhido, row, col_titulo, spreadsheet_id, sheet_name)
                self.titulos_gerados.append(titulo_escolhido)
                self.linhas_processadas += 1
                time.sleep(config.DELAY_ENTRE_CHAMADAS_GEMINI)

    def _processar_conteudos(self, df: pd.DataFrame, dynamic_column_map: Dict, 
                           limite_linhas: Optional[int] = None, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
        """Processa geração de conteúdos em lote, com confirmação única"""
        logger.info("Iniciando segunda etapa: Geração de conteúdos")
        col_conteudo = dynamic_column_map['url_documento']['name'] if isinstance(dynamic_column_map['url_documento'], dict) else dynamic_column_map['url_documento']
        col_titulo = dynamic_column_map['titulo']['name'] if isinstance(dynamic_column_map['titulo'], dict) else dynamic_column_map['titulo']
        conteudos_lote = []
        linhas_processadas_lote = 0
        for idx, row in df.iterrows():
            if self._deve_pular_linha(row, col_conteudo, limite_linhas):
                continue
            if not row.get(col_titulo):
                logger.warning(f"Linha {idx} não tem título. Pulando geração de conteúdo.")
                continue
            dados = self.sheets.extrair_dados_linha(row, dynamic_column_map)
            conteudo, metricas, info_link = self.gemini.gerar_conteudo_por_titulo(dados, dados.get('titulo', ''))
            if not conteudo:
                print(f"Falha ao gerar conteúdo para ID {dados.get('id', '')}")
                continue
            conteudos_lote.append({
                'dados': dados,
                'conteudo': conteudo,
                'metricas': metricas,
                'row': row
            })
            linhas_processadas_lote += 1
            if limite_linhas and linhas_processadas_lote >= limite_linhas:
                break
        # Resumo do lote
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
        confirm = input("\nDeseja salvar os conteúdos e atualizar a planilha para este lote? (S/N): ").strip().upper()
        if confirm != 'S':
            print("Lote descartado pelo usuário. Nenhum documento será criado.")
            return
        # Salvar todos os conteúdos
        for c in conteudos_lote:
            dados = c['dados']
            conteudo = c['conteudo']
            row = c['row']
            # Remover todos os '**' do texto antes de criar o documento
            conteudo_sem_asteriscos = conteudo.replace('**', '')
            # Remover qualquer ocorrência da URL crua do texto
            url_ancora = dados.get('url_ancora', '')
            if url_ancora:
                conteudo_sem_asteriscos = conteudo_sem_asteriscos.replace(url_ancora, '')
            # Remover links Markdown ([palavra]() ou [palavra](url))
            conteudo_sem_asteriscos = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', conteudo_sem_asteriscos)
            # Aplicar hyperlink na palavra-âncora
            texto_final, info_link = substituir_links_markdown(conteudo_sem_asteriscos, dados.get('palavra_ancora', ''), url_ancora)
            sheet_row_num = row['sheet_row_num'] if 'sheet_row_num' in row else row.name + 2
            nome_arquivo = f"{dados.get('id', '')} - {dados.get('site', '')} - {dados.get('palavra_ancora', '')}"
            doc_id, doc_url = self.docs.criar_documento(
                dados.get('titulo', ''),
                texto_final,
                nome_arquivo,
                info_link=info_link,
                target_folder_id=dados.get('drive_folder_id', None)
            )
            self.sheets.atualizar_url_documento(
                sheet_row_num,
                doc_url,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            )
            print(f"Documento criado e link salvo para ID {dados.get('id', '')}: {doc_url}")
            self.linhas_processadas += 1
            time.sleep(config.DELAY_ENTRE_CHAMADAS_GEMINI)

    def _deve_pular_linha(self, row: pd.Series, coluna: str, limite_linhas: Optional[int]) -> bool:
        """Verifica se deve pular a linha atual"""
        if limite_linhas and self.linhas_processadas >= limite_linhas:
            return True
            
        valor_atual = row.get(coluna)
        if valor_atual and str(valor_atual).strip() and str(valor_atual).strip().lower() != "sem titulo":
            return True
            
        return False

    def _gerar_titulo(self, dados: Dict) -> Optional[str]:
        """Gera título usando Gemini"""
        tentativas = 0
        temperatura_original = getattr(self.gemini, 'temperatura_atual', 0.7)
        
        while tentativas < 3:
            tentativas += 1
            if hasattr(self.gemini, 'temperatura_atual'):
                self.gemini.temperatura_atual = min(1.0, temperatura_original + 0.1 * tentativas)
                
            titulos = self.gemini.gerar_titulos(dados, quantidade=3)
            for titulo in titulos:
                if titulo not in self.titulos_gerados:
                    return titulo
                    
        logger.warning(f"Não foi possível gerar um título único após {tentativas} tentativas")
        return None

    def _gerar_conteudo(self, dados: Dict) -> Optional[str]:
        """Gera conteúdo usando Gemini"""
        try:
            return self.gemini.gerar_conteudo(dados)
        except Exception as e:
            logger.error(f"Erro ao gerar conteúdo: {e}")
            return None

    def _salvar_titulo(self, titulo: str, row: pd.Series, col_titulo: str, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
        """Salva título na planilha"""
        try:
            sheet_row_num = row['sheet_row_num'] if 'sheet_row_num' in row else row.name + 2
            self.sheets.atualizar_titulo_documento(sheet_row_num, titulo, spreadsheet_id, sheet_name)
            logger.info(f"Título salvo: {titulo}")
        except Exception as e:
            logger.error(f"Erro ao salvar título: {e}")

    def _salvar_conteudo(self, conteudo: str, row: pd.Series, col_conteudo: str):
        """Salva conteúdo na planilha"""
        try:
            self.sheets.atualizar_celula(row.name, col_conteudo, conteudo)
            logger.info(f"Conteúdo salvo para linha {row.name}")
        except Exception as e:
            logger.error(f"Erro ao salvar conteúdo: {e}") 