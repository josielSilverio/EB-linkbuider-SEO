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
from src.db_handler import DBHandler

logger = logging.getLogger('seo_linkbuilder.processor')

class ContentProcessor:
    def __init__(self, sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler):
        self.sheets = sheets
        self.gemini = gemini
        self.docs = docs
        self.titulos_gerados = []
        self.linhas_processadas = 0
        self.logger = logging.getLogger('seo_linkbuilder.processor')

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
        
        linhas_sem_titulo = 0
        for idx, row in df.iterrows():
            if not row[col_titulo]:
                linhas_sem_titulo += 1
                
        if linhas_sem_titulo == 0:
            logger.info("Todas as linhas já possuem títulos. Nada a processar.")
            return
            
        logger.info(f"Encontradas {linhas_sem_titulo} linhas sem título para processar.")
        
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
                
            # Verifica se atingiu o limite de linhas
            if limite_linhas and self.linhas_processadas >= limite_linhas:
                logger.info(f"Limite de {limite_linhas} linhas atingido. Parando processamento.")
                break

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
                    # Extrair informações para o banco de dados
                    main_theme = self.gemini._extrair_tema_principal(titulo)
                    structure_type = self.gemini._extrair_estrutura(titulo)
                    themes = self.gemini._extrair_temas_secundarios(titulo)
                    
                    # Adicionar ao banco de dados
                    try:
                        db = DBHandler()
                        title_id = db.add_title(
                            title=titulo,
                            anchor_word=dados.get('palavra_ancora', ''),
                            main_theme=main_theme,
                            structure_type=structure_type,
                            themes=themes
                        )
                        logger.info(f"Título salvo no banco de dados com ID {title_id}")
                    except Exception as e:
                        logger.error(f"Erro ao salvar título no banco de dados: {e}")
                    
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

    def _calcular_pontuacao_titulo(self, titulo: str, dados: Dict) -> float:
        """
        Calcula a pontuação do título baseado em critérios objetivos.
        
        Critérios:
        - Presença da palavra-âncora: +0.1
        - Comprimento adequado (50-100 caracteres): +0.2
        - Uso de números ou estatísticas: +0.1
        - Tema atraente de entretenimento: +0.3
        - Estrutura clara (começa com palavra de ação ou número): +0.1
        - Relevância ao tema/site: +0.2
        
        Returns:
            Pontuação entre 0 e 1
        """
        pontuacao = 0.0
        titulo_lower = titulo.lower()
        palavra_ancora = dados.get('palavra_ancora', '').lower()
        site = dados.get('site', '').lower()
        
        # Presença da palavra-âncora (+0.1)
        if palavra_ancora and palavra_ancora in titulo_lower:
            pontuacao += 0.1
        
        # Comprimento adequado (+0.2)
        if 50 <= len(titulo) <= 100:
            pontuacao += 0.2
        
        # Uso de números (+0.1)
        if re.search(r'\d+', titulo):
            pontuacao += 0.1
        
        # Tema atraente de entretenimento (+0.3)
        temas_entretenimento = {
            'jogos': ['game', 'jogo', 'jogar', 'gaming', 'gameplay', 'player'],
            'apostas': ['aposta', 'bet', 'odds', 'palpite', 'prognóstico'],
            'esportes': ['futebol', 'basquete', 'esporte', 'campeonato', 'time', 'atleta'],
            'diversão': ['diversão', 'entretenimento', 'lazer', 'hobby', 'passatempo'],
            'tecnologia': ['tech', 'tecnologia', 'digital', 'online', 'virtual'],
            'cultura': ['filme', 'série', 'música', 'arte', 'cultura', 'show']
        }
        
        palavras_titulo = set(titulo_lower.split())
        for categoria, palavras in temas_entretenimento.items():
            if any(palavra in titulo_lower for palavra in palavras):
                pontuacao += 0.3
                break
        
        # Estrutura clara (+0.1)
        palavras_acao = ['como', 'descubra', 'conheça', 'saiba', 'veja', 'aprenda', 'entenda', 'confira',
                        'explore', 'domine', 'melhore', 'aumente', 'maximize', 'potencialize']
        primeira_palavra = titulo_lower.split()[0]
        if primeira_palavra in palavras_acao or re.match(r'\d+', primeira_palavra):
            pontuacao += 0.1
        
        # Relevância ao tema/site (+0.2)
        if site:
            # Remove domínio e extensão para focar no nome do site
            nome_site = re.sub(r'\.com.*$', '', site.split('/')[-1])
            temas_site = nome_site.split('-')
            
            # Verifica se palavras do título são relacionadas ao tema do site
            if any(tema in palavras_titulo for tema in temas_site):
                pontuacao += 0.2
        
        # Garante que a pontuação não ultrapasse 1.0
        return min(1.0, pontuacao)

    def _salvar_titulo(self, titulo: str, row: pd.Series, col_titulo: str, spreadsheet_id: Optional[str] = None, sheet_name: Optional[str] = None):
        """Salva título na planilha"""
        try:
            sheet_row_num = row['sheet_row_num'] if 'sheet_row_num' in row else row.name + 2
            self.sheets.atualizar_titulo_documento(sheet_row_num, titulo, spreadsheet_id, sheet_name)
            
            # Calcula e atualiza o desempenho do título no banco de dados
            try:
                dados = self.sheets.extrair_dados_linha(row, self.sheets.dynamic_column_map)
                performance_score = self._calcular_pontuacao_titulo(titulo, dados)
                self.gemini.atualizar_desempenho_titulo(titulo, performance_score)
                logger.info(f"Desempenho do título atualizado no banco de dados (pontuação: {performance_score:.2f})")
            except Exception as e:
                logger.error(f"Erro ao atualizar desempenho do título no banco: {e}")
            
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

    def deve_processar_linha(self, row: pd.Series, dynamic_column_map: Dict, modo_processamento: str) -> bool:
        """
        Verifica se uma linha deve ser processada com base no modo de processamento.
        """
        try:
            # Verifica se tem palavra-âncora e URL
            if not row[dynamic_column_map['palavra_ancora']] or not row[dynamic_column_map['url_ancora']]:
                self.logger.debug(f"Linha pulada: falta palavra-âncora ou URL")
                return False
                
            # Modo 1: Apenas títulos
            if modo_processamento == "1":
                if not row[dynamic_column_map['titulo']]:
                    self.logger.info(f"Gerando título para palavra-âncora: {row[dynamic_column_map['palavra_ancora']]}")
                    return True
                self.logger.debug(f"Linha pulada: já tem título")
                return False
                
            # Modo 2: Apenas conteúdo
            elif modo_processamento == "2":
                if not row[dynamic_column_map['titulo']]:
                    self.logger.warning(f"Linha pulada: não tem título para gerar conteúdo")
                    return False
                if not row[dynamic_column_map['doc_id']]:
                    self.logger.info(f"Gerando conteúdo para título: {row[dynamic_column_map['titulo']]}")
                    return True
                self.logger.debug(f"Linha pulada: já tem documento")
                return False
                
            # Modo 3: Títulos e conteúdo
            elif modo_processamento == "3":
                if not row[dynamic_column_map['titulo']]:
                    self.logger.info(f"Gerando título para palavra-âncora: {row[dynamic_column_map['palavra_ancora']]}")
                    return True
                if not row[dynamic_column_map['doc_id']]:
                    self.logger.info(f"Gerando conteúdo para título: {row[dynamic_column_map['titulo']]}")
                    return True
                self.logger.debug(f"Linha pulada: já tem título e documento")
                return False
                
            return False
            
        except Exception as e:
            self.logger.error(f"Erro ao verificar se deve processar linha: {e}")
            return False 