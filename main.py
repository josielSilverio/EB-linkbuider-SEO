# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import dotenv
import json

from src.utils import (
    configurar_logging, 
    limpar_nome_arquivo, 
    identificar_palavras_frequentes_em_titulos, # Importar a nova função
    contar_tokens, # Adicionar contar_tokens
    extrair_titulos_por_ancora,
    identificar_padroes_por_ancora
)
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler, verificar_conteudo_proibido, verificar_e_corrigir_titulo
from src.docs_handler import DocsHandler
from src.config import (
    gerar_nome_arquivo, 
    COLUNAS, 
    estimar_custo_gemini, 
    GEMINI_MAX_OUTPUT_TOKENS, 
    MESES,
    SPREADSHEET_ID,
    SHEET_NAME,
    DRIVE_FOLDER_ID,
    USD_TO_BRL_RATE,
    DELAY_ENTRE_CHAMADAS_GEMINI # Adicionar esta importação
)

# Caminho para salvar a última seleção
LAST_SELECTION_FILE = "data/.last_selection.json"

def carregar_ultima_selecao() -> Dict:
    """Carrega a última seleção de planilha/aba do arquivo JSON."""
    if os.path.exists(LAST_SELECTION_FILE):
        try:
            with open(LAST_SELECTION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Erro ao carregar última seleção de {LAST_SELECTION_FILE}: {e}")
    return {}

def salvar_ultima_selecao(selecao: Dict):
    """Salva a seleção atual no arquivo JSON."""
    try:
        # Cria o diretório data se não existir
        os.makedirs(os.path.dirname(LAST_SELECTION_FILE), exist_ok=True)
        with open(LAST_SELECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(selecao, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar última seleção em {LAST_SELECTION_FILE}: {e}")

def verificar_titulos_duplicados(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, modo_teste: bool = False):
    """
    Verifica se existem títulos duplicados na planilha e gera novos conteúdos para substituí-los.
    
    Args:
        sheets: Instância de SheetsHandler
        gemini: Instância de GeminiHandler
        docs: Instância de DocsHandler
        modo_teste: Se True, apenas identifica duplicatas sem corrigi-las
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Verificando títulos duplicados na planilha...")
    
    try:
        # Lê a planilha completa sem filtrar por data
        df = sheets.ler_planilha(apenas_dados=True)
        
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar títulos duplicados")
            return
        
        # Obtém a coluna de títulos
        # Verifica se a coluna titulo existe no DataFrame
        if COLUNAS["titulo"] < len(df.columns):
            coluna_titulo = COLUNAS["titulo"]
            titulos = df[coluna_titulo].tolist()
            
            # Identifica os títulos duplicados (ignorando vazios e "Sem titulo")
            titulos_validos = [t for t in titulos if t and str(t).strip() and str(t).strip() != "Sem titulo"]
            contagem = Counter(titulos_validos)
            duplicados = [titulo for titulo, count in contagem.items() if count > 1]
            
            if not duplicados:
                logger.info("✓ Não foram encontrados títulos duplicados!")
                return
            
            logger.warning(f"Foram encontrados {len(duplicados)} títulos duplicados: {duplicados}")
            
            if modo_teste:
                logger.info("[MODO TESTE] Identificação de duplicatas concluída. Não serão feitas correções.")
                return
            
            # Para cada título duplicado, encontre as linhas correspondentes
            for titulo_duplicado in duplicados:
                indices = df[df[coluna_titulo] == titulo_duplicado].index.tolist()
                
                if len(indices) <= 1:
                    continue  # Não deveria acontecer, mas é uma salvaguarda
                
                # Mantém o primeiro, gera novos para os demais
                logger.info(f"Encontrado título duplicado: '{titulo_duplicado}' em {len(indices)} documentos")
                
                for idx in indices[1:]:
                    linha = df.iloc[idx]
                    try:
                        dados = sheets.extrair_dados_linha(linha)
                        
                        logger.info(f"Gerando novo conteúdo para substituir título duplicado: '{titulo_duplicado}' (ID {dados.get('id', 'Sem-ID')})")
                        
                        # Aumenta a criatividade definindo uma temperatura mais alta
                        temperatura_original = gemini.temperatura_atual
                        gemini.temperatura_atual = min(0.9, temperatura_original + 0.3)  # Aumenta significativamente a temperatura
                        
                        # Gera o conteúdo com ênfase em título único
                        try:
                            conteudo, metricas, info_link = gemini.gerar_conteudo(
                                dados, 
                                instrucao_adicional="\n\nIMPORTANTE: Crie um título COMPLETAMENTE ÚNICO e ORIGINAL, muito diferente dos títulos típicos para esse tema."
                            )
                            
                            # Restaura a temperatura original
                            gemini.temperatura_atual = temperatura_original
                            
                            # Extrai o título real do conteúdo gerado (primeira linha)
                            linhas = conteudo.split('\n')
                            titulo_gerado = linhas[0].strip() if linhas else "Artigo sem título"
                            logger.info(f"Novo título gerado: {titulo_gerado}")
                            
                            # Gera o nome do arquivo
                            try:
                                nome_arquivo = gerar_nome_arquivo(dados.get('id', 'Sem-ID'), 
                                                                dados.get('site', 'Sem-site'), 
                                                                dados.get('palavra_ancora', 'Sem-ancora'))
                            except Exception as e:
                                logger.error(f"Erro ao gerar nome de arquivo: {e}")
                                # Fallback para um nome simples
                                nome_arquivo = f"{dados.get('id', 'Sem-ID')} - {dados.get('site', 'Sem-site')} - Artigo Revisado"
                            
                            # Cria o documento no Google Docs (ou atualiza se já existir)
                            document_id, document_url = docs.criar_documento(titulo_gerado, conteudo, nome_arquivo, info_link)
                            
                            # Atualiza a URL e o título na planilha
                            sheets.atualizar_url_documento(idx, document_url)
                            sheets.atualizar_titulo_documento(idx, titulo_gerado)
                            logger.info(f"URL e título atualizados na planilha: {document_url}")
                            
                        except Exception as e:
                            logger.error(f"Erro ao gerar novo conteúdo para substituir título duplicado: {e}")
                            continue
                    except Exception as e:
                        logger.error(f"Erro ao processar linha {idx} para título duplicado: {e}")
                        continue
            
            logger.info("Verificação e correção de títulos duplicados concluída com sucesso!")
        else:
            logger.error(f"Coluna titulo (índice {COLUNAS['titulo']}) não encontrada no DataFrame")
                
    except Exception as e:
        logger.error(f"Erro ao verificar títulos duplicados: {e}")
        logger.exception("Detalhes do erro:")

def verificar_similaridade_conteudos(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, 
                                    limiar_similaridade: float = 0.4, modo_teste: bool = False):
    """
    Verifica a similaridade entre conteúdos gerados e reescreve aqueles que são muito similares.
    
    Args:
        sheets: Instância de SheetsHandler
        gemini: Instância de GeminiHandler
        docs: Instância de DocsHandler
        limiar_similaridade: Percentual acima do qual os conteúdos são considerados muito similares (0.0 a 1.0)
        modo_teste: Se True, apenas identifica conteúdos similares sem corrigi-los
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info(f"Verificando similaridade entre conteúdos (limiar: {limiar_similaridade*100:.0f}%)...")
    
    try:
        # Lê a planilha completa sem filtrar por data
        df = sheets.ler_planilha(apenas_dados=True)
        
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar similaridade")
            return

        # Inicializa lista de documentos a serem processados - queremos apenas documentos com URL (que foram gerados)
        documentos_processados = []
        coluna_url = COLUNAS["url_documento"]
        coluna_titulo = COLUNAS["titulo"]

        # Verifica se as colunas existem
        if coluna_url >= len(df.columns) or coluna_titulo >= len(df.columns):
            logger.error(f"Colunas necessárias não encontradas no DataFrame")
            return
            
        # Cria uma lista de documentos com seus índices
        for idx, row in df.iterrows():
            # Verifica se há URL (documento gerado) e título
            url = row.get(coluna_url)
            titulo = row.get(coluna_titulo)
            
            if url and str(url).strip() and titulo and str(titulo).strip() != "Sem titulo":
                try:
                    # Obtém o ID do documento do Google Docs a partir da URL
                    doc_id = None
                    if isinstance(url, str) and '/document/d/' in url:
                        doc_id = url.split('/document/d/')[1].split('/')[0]
                    
                    if doc_id:
                        # Obtém o conteúdo do documento para análise
                        conteudo = docs.obter_conteudo_documento(doc_id)
                        
                        # Adiciona à lista de documentos com informações para processamento
                        documentos_processados.append({
                            'indice': idx,
                            'id_doc': doc_id,
                            'titulo': titulo,
                            'conteudo': conteudo,
                            'url': url,
                            'linha': df.iloc[idx] if idx < len(df) else None
                        })
                except Exception as e:
                    logger.error(f"Erro ao processar documento {url}: {e}")
        
        if len(documentos_processados) < 2:
            logger.info("Menos de 2 documentos encontrados para comparação. Encerrando verificação de similaridade.")
            return
            
        # Extrai títulos e conteúdos para análise
        titulos = [doc['titulo'] for doc in documentos_processados]
        conteudos = [doc['conteudo'] for doc in documentos_processados]
        
        # Calcula similaridade de títulos usando TF-IDF
        titulo_vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        titulo_tfidf = titulo_vectorizer.fit_transform(titulos)
        titulo_similarity = cosine_similarity(titulo_tfidf)
        
        # Calcula similaridade de conteúdos usando TF-IDF
        conteudo_vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        conteudo_tfidf = conteudo_vectorizer.fit_transform(conteudos)
        conteudo_similarity = cosine_similarity(conteudo_tfidf)
        
        # Combina as similaridades (média ponderada: 40% título, 60% conteúdo)
        combined_similarity = 0.4 * titulo_similarity + 0.6 * conteudo_similarity
        
        # Identifica pares similares acima do limiar
        pares_similares = []
        documentos_ja_selecionados = set()  # Evita reprocessar o mesmo documento
        
        for i in range(len(documentos_processados)):
            for j in range(i+1, len(documentos_processados)):
                if combined_similarity[i, j] > limiar_similaridade:
                    # Adiciona o par e a similaridade
                    pares_similares.append((i, j, combined_similarity[i, j]))
        
        # Ordena por similaridade (do maior para o menor)
        pares_similares.sort(key=lambda x: x[2], reverse=True)
        
        if not pares_similares:
            logger.info(f"✓ Não foram encontrados conteúdos com similaridade acima de {limiar_similaridade*100:.0f}%!")
            return
        
        logger.warning(f"Foram encontrados {len(pares_similares)} pares de conteúdos com similaridade acima de {limiar_similaridade*100:.0f}%")
        
        if modo_teste:
            # No modo teste, apenas lista os documentos similares
            for i, j, similarity in pares_similares:
                doc1 = documentos_processados[i]
                doc2 = documentos_processados[j]
                logger.info(f"[MODO TESTE] Similaridade {similarity*100:.1f}% entre:")
                logger.info(f"  - {doc1['titulo']} (ID: {doc1['id_doc']})")
                logger.info(f"  - {doc2['titulo']} (ID: {doc2['id_doc']})")
            return
        
        # Processa cada par similar
        for i, j, similarity in pares_similares:
            # Só reescreve se o documento não foi processado anteriormente
            if i in documentos_ja_selecionados or j in documentos_ja_selecionados:
                continue
                
            # Decide qual documento reescrever (escolhe o mais recente/maior índice)
            idx_a_reescrever = j if j > i else i
            documentos_ja_selecionados.add(idx_a_reescrever)
            
            doc_original = documentos_processados[i if idx_a_reescrever == j else j]
            doc_reescrever = documentos_processados[idx_a_reescrever]
            
            logger.info(f"Reescrevendo documento com similaridade {similarity*100:.1f}%:")
            logger.info(f"  - Original: {doc_original['titulo']}")
            logger.info(f"  - A reescrever: {doc_reescrever['titulo']}")
            
            try:
                # Obtém os dados da linha para reescrever
                linha = doc_reescrever['linha']
                dados = sheets.extrair_dados_linha(linha)
                
                # Instrução para reescrever com alta criatividade
                instrucao = (
                    f"\n\nREESCRITA CRIATIVA NECESSÁRIA!\n"
                    f"O conteúdo anterior foi considerado muito similar ({similarity*100:.1f}%) a outro artigo."
                    f"Por favor, reescreva COMPLETAMENTE com:\n"
                    f"1. Um título TOTALMENTE ÚNICO E CRIATIVO que se destaque\n"
                    f"2. Uma abordagem COMPLETAMENTE DIFERENTE do tema\n"
                    f"3. Exemplos e casos EXCLUSIVOS que não foram usados antes\n"
                    f"4. Uma estrutura de PARÁGRAFOS DIFERENTE\n"
                    f"5. Use ANALOGIAS INCOMUNS e PERSPECTIVAS SURPREENDENTES\n"
                    f"6. TEMPERATURA CRIATIVA MÁXIMA - seja ousado e inovador!\n"
                    f"7. Inclua no título algo verdadeiramente único e especial sobre este tema.\n\n"
                    f"IMPORTANTE: Mantenha a palavra-âncora '{dados.get('palavra_ancora', '')}' no segundo ou terceiro parágrafo de forma natural."
                )
                
                # Aumenta significativamente a temperatura
                temperatura_original = gemini.temperatura_atual
                gemini.temperatura_atual = 0.95  # Temperatura máxima para criatividade
                
                # Gera o conteúdo com ênfase em total originalidade
                logger.info(f"Gerando conteúdo totalmente novo para o documento {doc_reescrever['id_doc']}...")
                conteudo, metricas, info_link = gemini.gerar_conteudo(dados, instrucao_adicional=instrucao)
                
                # Restaura a temperatura
                gemini.temperatura_atual = temperatura_original
                
                # Extrai o título e verifica se é realmente diferente
                linhas = conteudo.split('\n')
                titulo_novo = linhas[0].strip() if linhas else "Artigo reescrito"
                
                # Verifica se o título novo é significativamente diferente do original
                titulo_similarity = cosine_similarity(
                    titulo_vectorizer.transform([titulo_novo]), 
                    titulo_vectorizer.transform([doc_reescrever['titulo']])
                )[0][0]
                
                if titulo_similarity > 0.5:
                    logger.warning(f"Novo título ainda similar ao original ({titulo_similarity*100:.1f}%). Adicionando prefixo.")
                    prefixos = ["Novas perspectivas: ", "Repensando: ", "Além do convencional: ", 
                                "Uma abordagem inovadora para ", "Revelando segredos: "]
                    import random
                    prefixo = random.choice(prefixos)
                    titulo_novo = f"{prefixo}{titulo_novo}"
                
                logger.info(f"Novo título gerado: {titulo_novo}")
                
                # Gera nome do arquivo
                try:
                    nome_arquivo = gerar_nome_arquivo(dados.get('id', 'Sem-ID'), 
                                                     dados.get('site', 'Sem-site'), 
                                                     dados.get('palavra_ancora', 'Sem-ancora'))
                except Exception as e:
                    logger.error(f"Erro ao gerar nome de arquivo: {e}")
                    nome_arquivo = f"{dados.get('id', 'Sem-ID')} - {dados.get('site', 'Sem-site')} - Reescrito"
                
                # Cria o documento no Google Docs
                logger.info(f"Criando documento '{nome_arquivo}'...")
                document_id, document_url = docs.atualizar_documento(doc_reescrever['id_doc'], 
                                                                    titulo_novo, 
                                                                    conteudo, 
                                                                    nome_arquivo, 
                                                                    info_link)
                
                # Atualiza a URL e o título na planilha (INDEPENDENTE DO MODO TESTE)
                try:
                    # Calcula o número da linha na planilha (índice original + 2 para offset de cabeçalho e base 1)
                    linha_planilha = doc_reescrever['indice'] + 2
                    
                    # Imprime detalhes de diagnóstico ANTES de atualizar
                    logger.info(f"==== INFORMAÇÕES DE ATUALIZAÇÃO DA PLANILHA ====")
                    logger.info(f"ID da Planilha: {SPREADSHEET_ID}")
                    logger.info(f"Nome da Aba: {SHEET_NAME}")
                    logger.info(f"Índice Original da Linha (base 0): {doc_reescrever['indice']}")
                    logger.info(f"Linha na planilha a ser atualizada (base 1): {linha_planilha}")
                    
                    # Atualiza Título (Coluna I)
                    coluna_titulo = 'I'
                    titulo_range = f"{SHEET_NAME}!{coluna_titulo}{linha_planilha}"
                    logger.info(f"Tentando atualizar Título na célula {coluna_titulo}{linha_planilha} (Range: {titulo_range}) com valor: '{titulo_novo}'")
                    sheets.service.spreadsheets().values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=titulo_range,
                        valueInputOption="USER_ENTERED", 
                        body={"values": [[titulo_novo]]}
                    ).execute()
                    logger.info(f"✓ Título atualizado com sucesso em {titulo_range}!")
                    
                    # Atualiza a URL (coluna J)
                    coluna_url = 'J'
                    url_range = f"{SHEET_NAME}!{coluna_url}{linha_planilha}"
                    logger.info(f"Tentando atualizar URL na célula {coluna_url}{linha_planilha} (Range: {url_range}) com valor: '{document_url}'")
                    sheets.service.spreadsheets().values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=url_range,
                        valueInputOption="USER_ENTERED",
                        body={"values": [[document_url]]}
                    ).execute()
                    logger.info(f"✓ URL atualizada com sucesso em {url_range}!")
                    logger.info(f"==== FIM DA ATUALIZAÇÃO DA PLANILHA ====")
                    
                except Exception as e: # Except correspondente ao try da atualização da planilha
                    # Usa doc_reescrever['indice'] que está disponível neste escopo
                    logger.error(f"Erro ao atualizar planilha para linha original {doc_reescrever['indice']} (linha sheet {linha_planilha}): {e}")
                    logger.exception("Detalhes do erro:")
                
                # Pausa para não sobrecarregar as APIs
                time.sleep(DELAY_ENTRE_CHAMADAS_GEMINI) # Pausa configurável
                
            except Exception as e: # Except correspondente ao try principal do processamento do par
                # Log do erro incluindo o índice original se disponível
                indice_orig_erro = doc_reescrever.get('indice', 'N/A') if 'doc_reescrever' in locals() else 'N/A'
                logger.error(f"Erro ao reescrever documento similar (Índice Original: {indice_orig_erro}): {e}")
                logger.exception("Detalhes completos do erro:")
        
        logger.info(f"Verificação e correção de similaridade concluída! Reescritos {len(documentos_ja_selecionados)} documentos.")
                
    except Exception as e:
        logger.error(f"Erro ao verificar similaridade entre conteúdos: {e}")
        logger.exception("Detalhes do erro:")

def corrigir_termos_proibidos(sheets: SheetsHandler, docs: DocsHandler, modo_teste: bool = False):
    """
    Verifica todos os documentos já gerados em busca de termos proibidos e os corrige.
    
    Args:
        sheets: Instância de SheetsHandler
        docs: Instância de DocsHandler
        modo_teste: Se True, apenas identifica os termos proibidos sem corrigi-los
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Verificando termos proibidos em todos os documentos gerados...")
    
    try:
        # Lê a planilha completa sem filtrar por data
        df = sheets.ler_planilha(apenas_dados=True)
        
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar termos proibidos")
            return
        
        # Inicializa lista de documentos a serem processados - queremos apenas documentos com URL (que foram gerados)
        documentos_processados = []
        coluna_url = COLUNAS["url_documento"]
        
        # Verifica se a coluna existe
        if coluna_url >= len(df.columns):
            logger.error(f"Coluna url_documento (índice {coluna_url}) não encontrada no DataFrame")
            return
            
        # Cria uma lista de documentos com seus índices
        for idx, row in df.iterrows():
            # Verifica se há URL (documento gerado)
            url = row.get(coluna_url)
            
            if url and str(url).strip():
                try:
                    # Obtém o ID do documento do Google Docs a partir da URL
                    doc_id = None
                    if isinstance(url, str) and '/document/d/' in url:
                        doc_id = url.split('/document/d/')[1].split('/')[0]
                    
                    if doc_id:
                        # Obtém o conteúdo do documento para análise
                        conteudo = docs.obter_conteudo_documento(doc_id)
                        
                        # Adiciona à lista de documentos com informações para processamento
                        documentos_processados.append({
                            'indice': idx,
                            'id_doc': doc_id,
                            'conteudo': conteudo,
                            'url': url,
                            'linha': df.iloc[idx] if idx < len(df) else None
                        })
                except Exception as e:
                    logger.error(f"Erro ao processar documento {url}: {e}")
        
        if not documentos_processados:
            logger.info("Nenhum documento encontrado para verificação de termos proibidos.")
            return
            
        # Inicializa contadores
        docs_com_termos_proibidos = 0
        docs_corrigidos = 0
        total_termos_substituidos = 0
        
        # Verifica cada documento
        for doc in documentos_processados:
            # Verifica termos proibidos
            conteudo_filtrado, termos_substituidos = verificar_conteudo_proibido(doc['conteudo'])
            
            if termos_substituidos:
                docs_com_termos_proibidos += 1
                total_termos_substituidos += len(termos_substituidos)
                
                logger.warning(f"Documento {doc['id_doc']}: {len(termos_substituidos)} termos proibidos encontrados: {', '.join(termos_substituidos)}")
                
                if not modo_teste:
                    try:
                        # Atualiza o conteúdo do documento
                        # Precisamos extrair o título (primeira linha) e o restante do conteúdo
                        linhas = doc['conteudo'].split('\n')
                        titulo = linhas[0] if linhas else "Sem título"
                        
                        # Verifica se o título também contém termos proibidos
                        titulo_filtrado, termos_titulo = verificar_conteudo_proibido(titulo)
                        if termos_titulo:
                            logger.warning(f"Título contém termos proibidos: {', '.join(termos_titulo)}")
                            titulo = titulo_filtrado
                        
                        # Atualiza o documento
                        nome_arquivo = doc['url'].split('/')[-2] if '/edit' in doc['url'] else f"Documento {doc['id_doc']}"
                        docs.atualizar_documento(doc['id_doc'], titulo, conteudo_filtrado, nome_arquivo)
                        
                        docs_corrigidos += 1
                        logger.info(f"✓ Documento {doc['id_doc']} corrigido com sucesso")
                    except Exception as e:
                        logger.error(f"Erro ao atualizar documento {doc['id_doc']}: {e}")
                else:
                    logger.info(f"[MODO TESTE] Documento {doc['id_doc']} seria corrigido (encontrados {len(termos_substituidos)} termos proibidos)")
        
        # Resumo
        if docs_com_termos_proibidos > 0:
            logger.warning(f"Foram encontrados {total_termos_substituidos} termos proibidos em {docs_com_termos_proibidos} documentos")
            if not modo_teste:
                logger.info(f"✓ Corrigidos {docs_corrigidos} documentos com termos proibidos")
        else:
            logger.info("✓ Não foram encontrados termos proibidos nos documentos analisados!")
        
    except Exception as e:
        logger.error(f"Erro ao verificar termos proibidos: {e}")
        logger.exception("Detalhes do erro:")

def estimar_custo_por_categoria(sheets: SheetsHandler, df: pd.DataFrame = None) -> Dict[str, Dict]:
    """
    Estima o custo médio por categoria de jogo com base na palavra-âncora.
    
    Args:
        sheets: Instância de SheetsHandler
        df: DataFrame opcional com os dados da planilha
        
    Returns:
        Dicionário com estatísticas por categoria (custo estimado, contagem, etc.)
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Estimando custos por categoria...")
    
    try:
        # Se não foi fornecido um DataFrame, lê a planilha
        if df is None:
            df = sheets.ler_planilha(apenas_dados=True)
            
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para estimar custos")
            return {}
            
        # Dicionário para armazenar estatísticas por categoria
        categorias = {
            'apostas esportivas': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'cassino': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'blackjack': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'roleta': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'aviator': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'fortune tiger': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'fortune rabbit': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'demo': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'casa de apostas': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'site de apostas': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'aposta online': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'bet': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
            'outros': {'count': 0, 'tokens_entrada_medio': 0, 'custo_estimado': 0},
        }
        
        # Definir valores médios aproximados de tokens por categoria
        # Estes são valores estimados que podem ser ajustados com base em dados reais
        tokens_entrada_por_categoria = {
            'apostas esportivas': 1800,
            'cassino': 1750,
            'blackjack': 1700,
            'roleta': 1650,
            'aviator': 1700,
            'fortune tiger': 1750,
            'fortune rabbit': 1750,
            'demo': 1600,
            'casa de apostas': 1850,
            'site de apostas': 1850,
            'aposta online': 1800,
            'bet': 1700,
            'outros': 1700,
        }
        
        # Valor médio de tokens de saída (conteúdo gerado)
        tokens_saida_medio = 500  # Aproximadamente 500 tokens para um artigo de 500 palavras
        
        # Usar índice direto da coluna palavra_ancora ao invés de extrair_dados_linha
        if COLUNAS["palavra_ancora"] < len(df.columns):
            coluna_palavra_ancora = COLUNAS["palavra_ancora"]
            
            # Pular a linha de cabeçalho ou linhas com dados inválidos
            linhas_validas = 0
            
            # Processar cada linha para classificar em categorias
            for _, linha in df.iterrows():
                try:
                    # Verificar se a linha tem o índice da palavra-âncora e se não é cabeçalho
                    if coluna_palavra_ancora < len(linha) and linha[coluna_palavra_ancora]:
                        palavra_ancora = str(linha[coluna_palavra_ancora]).lower().strip()
                        
                        # Pular se for cabeçalho ou valor vazio
                        if not palavra_ancora or palavra_ancora == "palavra_ancora" or palavra_ancora == "palavra ancora":
                            continue
                            
                        linhas_validas += 1
                        
                        # Encontrar categoria correspondente
                        categoria_encontrada = 'outros'
                        for categoria in categorias.keys():
                            if categoria != 'outros' and categoria in palavra_ancora:
                                categoria_encontrada = categoria
                                break
                        
                        # Incrementar contagem para a categoria
                        categorias[categoria_encontrada]['count'] += 1
                except Exception as e:
                    # Registra o erro, mas continua processando as próximas linhas
                    logger.debug(f"Erro ao processar linha para categorização: {e}")
                    continue
            
            logger.info(f"Processadas {linhas_validas} linhas válidas para categorização")
            
            if linhas_validas == 0:
                logger.warning("Nenhuma linha válida encontrada para categorização")
                return {}
        else:
            logger.error(f"Coluna palavra_ancora (índice {COLUNAS['palavra_ancora']}) não encontrada no DataFrame")
            return {}
        
        # Calcular custos estimados por categoria
        for categoria, stats in categorias.items():
            if stats['count'] > 0:
                # Usar valores médios estimados
                tokens_entrada_medio = tokens_entrada_por_categoria.get(categoria, 1700)
                
                # Estimar custo com base nos tokens médios
                custo_estimado = estimar_custo_gemini(tokens_entrada_medio, tokens_saida_medio)
                
                # Atualizar estatísticas
                stats['tokens_entrada_medio'] = tokens_entrada_medio
                stats['tokens_saida_medio'] = tokens_saida_medio
                stats['custo_por_item'] = custo_estimado
                stats['custo_total'] = custo_estimado * stats['count']
        
        return categorias
    
    except Exception as e:
        logger.error(f"Erro ao estimar custos por categoria: {e}")
        return {}

def apresentar_menu_categorias(categorias: Dict[str, Dict]) -> Dict:
    """
    Apresenta um menu interativo para o usuário escolher quais categorias processar.
    
    Args:
        categorias: Dicionário com estatísticas por categoria (já filtradas para itens disponíveis)
        
    Returns:
        Dicionário com as categorias selecionadas (valor booleano) ou {'quantidade_especifica': N} ou None se cancelado.
    """
    logger = logging.getLogger('seo_linkbuilder')

    # Filtrar apenas categorias com pelo menos um item (deveria já vir assim de estimar_custo_por_categoria)
    categorias_com_itens = {k: v for k, v in categorias.items() if v.get('count', 0) > 0}

    if not categorias_com_itens:
        logger.warning("Nenhuma categoria com itens disponíveis para processamento encontrada para o menu.")
        print("\nAVISO: Nenhuma categoria com itens disponíveis para seleção no menu.")
        # Retorna um dicionário que indica "processar nada" ou pode ser tratado como "todas (vazias)"
        # Para evitar erros, é melhor retornar algo que a lógica principal entenda como "nada a fazer por categoria"
        # ou talvez a lógica principal nem chame o menu se 'categorias' estiver vazio.
        # Se chamado, e estiver vazio, retornar um dict vazio pode ser uma opção.
        return {}


    # Ordenar por contagem (do maior para o menor)
    categorias_ordenadas = sorted(categorias_com_itens.items(), key=lambda x: x[1]['count'], reverse=True)

    # Dicionário para armazenar seleção
    selecao = {}

    print("\n" + "="*60)
    print("MENU DE SELEÇÃO DE CATEGORIAS/QUANTIDADE".center(60))
    print("="*60)

    # Mostrar contagem total de itens DISPONÍVEIS
    total_itens_disponiveis = sum(v['count'] for v in categorias_com_itens.values())
    total_custo_estimado_disponiveis = sum(v.get('custo_total', 0) for v in categorias_com_itens.values())
    print(f"\nTotal de itens disponíveis para processamento: {total_itens_disponiveis} | Custo estimado total (disponíveis): R${total_custo_estimado_disponiveis*5:.2f}")
    print("\nCategorias disponíveis (baseado em itens não processados):")

    # Apresentar opções
    print("\nCódigo | Categoria              | Quantidade | Custo estimado (R$)")
    print("-"*60)

    # Adicionar TODOS OS JOGOS como a primeira opção
    print(f"0      | TODOS OS ITENS          | {total_itens_disponiveis:^10} | R${total_custo_estimado_disponiveis*5:.2f}")
    print("-"*60)

    for i, (categoria, stats) in enumerate(categorias_ordenadas, 1):
        cat_formatada = f"{categoria[:20]:<20}"
        custo_total_cat = stats.get('custo_total', 0) * 5
        print(f"{i:^6} | {cat_formatada} | {stats['count']:^10} | R${custo_total_cat:.2f}")

    print("-"*60)
    print(f"T      | TODOS OS ITENS          | {total_itens_disponiveis:^10} | R${total_custo_estimado_disponiveis*5:.2f} (Mesmo que 0)")
    print(f"Q      | QUANTIDADE ESPECÍFICA   | -          | - (Das primeiras disponíveis)")
    print("-"*60)

    while True:
        escolha = input("\nEscolha uma opção (número da categoria, T/0 para todos, Q para quantidade específica, ou X para sair): ").strip().upper()

        if escolha == 'X':
            logger.info("Operação cancelada pelo usuário no menu.")
            return None # Indica cancelamento

        elif escolha == 'T' or escolha == '0':
            # Selecionar todos os itens disponíveis (não significa todas as categorias, mas sim processar sem filtro de categoria)
            # A lógica principal interpretará um dict vazio ou um com todas as categorias como "sem filtro de categoria"
            # Para simplificar, podemos retornar um marcador especial ou um dict que inclui todas as categorias listadas.
            selecao_final = {cat_nome: True for cat_nome in categorias_com_itens.keys()}
            logger.info(f"Opção 'Todos os Itens' selecionada. Serão considerados {total_itens_disponiveis} itens disponíveis (antes de outros limites).")
            return selecao_final

        elif escolha == 'Q':
            try:
                quantidade = int(input(f"Digite a quantidade de itens a processar (serão pegos os primeiros disponíveis, até {total_itens_disponiveis}): "))
                if quantidade <= 0:
                    print("Por favor, digite um número maior que zero.")
                    continue
                
                # Não limitar pela quantidade total aqui, a lógica principal fará isso.
                # Apenas informa a estimativa baseada no que foi pedido.
                custo_medio_item = total_custo_estimado_disponiveis / total_itens_disponiveis if total_itens_disponiveis > 0 else 0
                custo_estimado_para_qtd = custo_medio_item * min(quantidade, total_itens_disponiveis) # Estima para o mínimo entre pedido e disponível
                
                logger.info(f"Opção de processar {quantidade} itens selecionada. Serão processadas as primeiras linhas disponíveis até esta quantidade, se houver.")
                logger.info(f"Custo estimado para processar até {min(quantidade, total_itens_disponiveis)} itens: R${custo_estimado_para_qtd*5:.2f}")
                # Retorna a quantidade desejada para a lógica principal decidir
                return {'quantidade_especifica': quantidade}

            except ValueError:
                print("Por favor, digite um número válido.")
                continue

        else: # Escolha de categoria específica
            try:
                indice = int(escolha)
                if 1 <= indice <= len(categorias_ordenadas):
                    categoria_selecionada_nome = categorias_ordenadas[indice - 1][0]
                    stats = categorias_ordenadas[indice - 1][1]
                    
                    logger.info(f"Selecionada categoria '{categoria_selecionada_nome}' com {stats['count']} itens disponíveis (custo estimado: R${stats.get('custo_total', 0)*5:.2f})")
                    
                    # Marcar apenas a categoria selecionada
                    selecao_final = {cat: (cat == categoria_selecionada_nome) for cat in categorias_com_itens.keys()}
                    return selecao_final
                else:
                    print(f"Por favor, digite um número entre 1 e {len(categorias_ordenadas)}, T/0, Q ou X.")
            except ValueError:
                print("Opção inválida. Por favor, tente novamente (número da categoria, T/0, Q ou X).")
    # Este return não deveria ser alcançado devido ao loop infinito e returns internos.
    # Mas para garantir, podemos retornar um dict vazio ou None.
    return None

def filtrar_dataframe_por_categorias(df: pd.DataFrame, sheets: SheetsHandler, selecao: Dict) -> pd.DataFrame:
    """
    Filtra o DataFrame com base nas categorias selecionadas pelo usuário.
    
    Args:
        df: DataFrame original com todos os dados
        sheets: Instância de SheetsHandler
        selecao: Dicionário com as categorias selecionadas
        
    Returns:
        DataFrame filtrado
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Verificar se há uma quantidade específica solicitada
    if selecao and 'quantidade_especifica' in selecao:
        quantidade = selecao['quantidade_especifica']
        # Selecionar aleatoriamente a quantidade solicitada
        if quantidade >= len(df):
            logger.info(f"A quantidade solicitada ({quantidade}) é maior ou igual ao total disponível ({len(df)}). Usando todo o DataFrame.")
            df_filtrado = df
        else:
            logger.info(f"Selecionando {quantidade} itens aleatoriamente.")
            df_filtrado = df.sample(n=quantidade, random_state=42)
    
    # Se nenhuma seleção foi feita ou está vazia, retornar DataFrame vazio
    if not selecao:
        logger.warning("Nenhuma categoria selecionada. Retornando DataFrame vazio.")
        return pd.DataFrame()
        
    # Se TODOS os itens foram selecionados, retornar o DataFrame inteiro
    todas_selecionadas = all(selecionado for selecionado in selecao.values())
    if todas_selecionadas:
        logger.info("Todas as categorias foram selecionadas. Retornando DataFrame completo.")
        return df
    
    # Verificar se temos a coluna palavra_ancora
    if COLUNAS["palavra_ancora"] >= len(df.columns):
        logger.error(f"Coluna palavra_ancora (índice {COLUNAS['palavra_ancora']}) não encontrada no DataFrame")
        return pd.DataFrame()
    
    # Lista para armazenar índices selecionados
    indices_selecionados = []
    
    # Processar cada linha para verificar se pertence a alguma categoria selecionada
    for idx, linha in df.iterrows():
        if COLUNAS["palavra_ancora"] < len(linha) and linha[COLUNAS["palavra_ancora"]]:
            palavra_ancora = str(linha[COLUNAS["palavra_ancora"]]).lower().strip()
            
            # Pular linhas de cabeçalho ou valores vazios
            if not palavra_ancora or palavra_ancora == "palavra_ancora" or palavra_ancora == "palavra ancora":
                continue
            
            # Verificar se a palavra âncora pertence a alguma categoria selecionada
            for categoria, selecionado in selecao.items():
                if selecionado and categoria in palavra_ancora:
                    indices_selecionados.append(idx)
                    break
    
    # Criar DataFrame filtrado
    df_filtrado = df.loc[indices_selecionados]
    
    logger.info(f"DataFrame filtrado com {len(df_filtrado)} linhas de {len(df)} originais.")
    return df_filtrado

def apresentar_menu_meses(sheets: SheetsHandler = None) -> Tuple[str, str]:
    """
    Apresenta um menu interativo para o usuário escolher qual mês processar.
    
    Args:
        sheets: Instância opcional de SheetsHandler para verificar disponibilidade de dados
        
    Returns:
        Tupla com (ano, mês) selecionados no formato (YYYY, MM)
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    try:
        # Usar o dicionário de meses da configuração
        meses = MESES
        
        # Criar um mapeamento inverso (nome do mês para código)
        meses_invertido = {nome.lower(): codigo for codigo, nome in meses.items()}
        
        # Definir anos disponíveis (ano atual e próximo)
        ano_atual_sistema = datetime.now().year
        anos = [str(ano_atual_sistema), str(ano_atual_sistema + 1)]
        
        print("\n" + "="*60)
        print("MENU DE SELEÇÃO DE MÊS".center(60))
        print("="*60)
        
        # Solicitar escolha do ano
        while True:
            print("\nSelecione o ano:")
            for i, ano in enumerate(anos):
                print(f"{i+1}. {ano}")
                
            escolha_ano = input("\nDigite o número da opção ou o ano completo: ").strip()
            
            # Verificar se o usuário digitou o ano completo
            if escolha_ano in anos:
                ano_selecionado = escolha_ano
                break
                
            # Verificar se o usuário digitou o número da opção
            try:
                indice_ano = int(escolha_ano) - 1
                if 0 <= indice_ano < len(anos):
                    ano_selecionado = anos[indice_ano]
                    break
                else:
                    print(f"Por favor, digite um número entre 1 e {len(anos)}.")
            except ValueError:
                print(f"Por favor, digite um número válido ou o ano completo ({anos[0]} ou {anos[1]}).")
        
        # Solicitar escolha do mês
        while True:
            print("\nSelecione o mês:")
            for codigo, nome in meses.items():
                print(f"{codigo}. {nome}")
                
            escolha_mes = input("\nDigite o código do mês (01-12) ou o nome: ").strip()
            
            # Verificar pelo código do mês
            if escolha_mes in meses:
                mes_selecionado = escolha_mes
                nome_mes = meses[mes_selecionado]
                break
                
            # Verificar pelo nome do mês
            elif escolha_mes.lower() in meses_invertido:
                mes_selecionado = meses_invertido[escolha_mes.lower()]
                nome_mes = meses[mes_selecionado]
                break
                
            # Verificar se foi digitado um número sem o zero à esquerda
            elif escolha_mes.isdigit() and 1 <= int(escolha_mes) <= 12:
                mes_selecionado = f"{int(escolha_mes):02d}"  # Formata com zero à esquerda
                nome_mes = meses[mes_selecionado]
                break
                
            else:
                print("Por favor, digite um código de mês válido (01-12) ou o nome do mês.")
        
        logger.info(f"Selecionado: {nome_mes} de {ano_selecionado}")
        print(f"\nVocê selecionou: {nome_mes} de {ano_selecionado}")
        
        return (ano_selecionado, mes_selecionado)
    
    except Exception as e:
        logger.error(f"Erro durante a seleção do mês: {e}")
        logger.exception("Detalhes do erro:")
        
        # Em caso de erro, retornar valores padrão
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        mes_codigo = f"{mes_atual:02d}"
        
        logger.warning(f"Usando valores padrão: {MESES.get(mes_codigo, 'Mês atual')} de {ano_atual}")
        print(f"\nOcorreu um erro na seleção. Usando: {MESES.get(mes_codigo, 'Mês atual')} de {ano_atual}")
        
        return (str(ano_atual), mes_codigo)

def apresentar_menu_planilha(sheets: SheetsHandler = None) -> Tuple[str, str]:
    """
    Seleciona a aba a ser processada na planilha fixa definida.
    Usa a última seleção salva como padrão.
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Define o ID da planilha fixa
    spreadsheet_id_selecionado = "12NxIBzKhNdxCMm2ggGQdPmlKWAFYuLUzvA6N0cDP1Fo"
    logger.info(f"Usando planilha fixa com ID: {spreadsheet_id_selecionado}")

    if sheets is None:
        try:
            sheets = SheetsHandler(spreadsheet_id=spreadsheet_id_selecionado) # Passa o ID fixo
        except Exception as e:
            logger.error(f"Erro ao inicializar SheetsHandler para menu: {e}")
            # Tenta retornar o ID fixo e o nome padrão do .env em caso de erro grave
            return spreadsheet_id_selecionado, SHEET_NAME 

    # Carrega a última seleção (apenas para a aba)
    ultima_selecao = carregar_ultima_selecao()
    # Verifica se a última seleção era da mesma planilha fixa
    if ultima_selecao.get("spreadsheet_id") == spreadsheet_id_selecionado:
        ultima_sheet_name = ultima_selecao.get("sheet_name", SHEET_NAME)
    else:
        # Se a última seleção era de outra planilha, usa o padrão do .env
        ultima_sheet_name = SHEET_NAME 

    # Selecionar Aba (forma padronizada)
    while True:
        try:
            logger.info(f"Buscando abas na planilha {spreadsheet_id_selecionado}...")
            abas = sheets.obter_abas_disponiveis(spreadsheet_id_selecionado)
            if not abas:
                logger.error(f"Nenhuma aba encontrada ou erro ao buscar na planilha {spreadsheet_id_selecionado}. Verifique o ID e as permissões.")
                # Se não encontrar abas, não há como continuar
                raise ValueError(f"Nenhuma aba encontrada na planilha {spreadsheet_id_selecionado}")

            print(f"\n=== Selecione a Aba na Planilha '{spreadsheet_id_selecionado}' ===")
            abas_dict = {str(i+1): a for i, a in enumerate(abas)}

            # Mostra as opções numeradas
            for idx, a_info in abas_dict.items():
                # Indica qual era a última selecionada
                indicador_padrao = " (Última selecionada)" if a_info['titulo'] == ultima_sheet_name else ""
                print(f"[{idx}] {a_info['titulo']}{indicador_padrao}")

            escolha_aba = input(f"\nDigite o número da aba desejada (1-{len(abas)}): ").strip()

            if escolha_aba.isdigit() and escolha_aba in abas_dict:
                sheet_name_selecionado = abas_dict[escolha_aba]['titulo']
                logger.info(f"Aba selecionada: {sheet_name_selecionado}")
                break
            else:
                print(f"Seleção inválida. Por favor, digite um número entre 1 e {len(abas)}.")
                logger.warning(f"Seleção de aba inválida: '{escolha_aba}'")

        except Exception as e:
            logger.error(f"Erro ao selecionar aba: {e}")
            # Em caso de erro, tenta usar o nome padrão, mas avisa
            sheet_name_selecionado = SHEET_NAME
            logger.warning(f"Usando nome de aba padrão do .env devido a erro: {SHEET_NAME}")
            # Verifica se o nome padrão existe na lista, se a lista foi carregada
            if abas and not any(a['titulo'] == sheet_name_selecionado for a in abas):
                 logger.warning(f"Nome padrão '{sheet_name_selecionado}' não encontrado na lista de abas disponíveis.")
            break # Sai do loop em caso de erro

    # Salva a seleção atual (planilha fixa + aba selecionada)
    salvar_ultima_selecao({
        "spreadsheet_id": spreadsheet_id_selecionado,
        "sheet_name": sheet_name_selecionado
    })

    return spreadsheet_id_selecionado, sheet_name_selecionado

def processar_linha(linha, indice, df, df_original, modo_teste, spreadsheet_id, sheet_name):
    """
    Processa uma linha específica da planilha.
    Extrai dados, gera o conteúdo com a API e salva no Google Drive.
    """
    logger = logging.getLogger('seo_linkbuilder') # Get the logger instance
    try:
        # ADICIONE ESTE LOG PARA VERIFICAR QUAL LINHA ESTÁ SENDO PROCESSADA
        indice_real = int(df.iloc[indice]["sheet_row_num"]) if "sheet_row_num" in df.columns else indice
        logger.info(f"Processando linha {indice} do DataFrame (linha {indice_real} na planilha original)")
        
        # Extrai os dados da linha
        id_campanha = str(df.iloc[indice][COLUNAS["id"]])
        site = str(df.iloc[indice][COLUNAS["site"]])
        ancora = str(df.iloc[indice][COLUNAS["ancora"]])
        assunto = str(df.iloc[indice][COLUNAS["assunto"]])
        contexto = str(df.iloc[indice][COLUNAS["contexto"]])
        instrucoes = str(df.iloc[indice][COLUNAS["instrucoes"]])
        
        # Obtém a linha original na planilha usando a coluna sheet_row_num
        logger.info(f"Processando ID {id_campanha} (índice {indice}, índice real na planilha: {indice_real})")
        
        # Chama a API para gerar o conteúdo
        gemini_handler = GeminiHandler()
        conteudo_gerado = gemini_handler.gerar_conteudo(
            site=site,
            ancora=ancora,
            assunto=assunto,
            contexto=contexto,
            instrucoes=instrucoes
        )
        
        # Extrai o título do conteúdo gerado (primeira linha não vazia)
        titulo = extrair_titulo(conteudo_gerado, ancora) # Passar a palavra_ancora aqui
        
        # Gera o nome do arquivo baseado no padrão definido
        nome_arquivo = gerar_nome_arquivo(id=id_campanha, site=site, ancora=ancora)
        
        # Apenas gera o documento no Drive se não estiver em modo teste
        if not modo_teste:
            # Cria o documento no Google Docs e obtém a URL
            docs_handler = DocsHandler()
            url_documento = docs_handler.criar_documento(
                titulo=titulo,
                conteudo=conteudo_gerado,
                nome_arquivo=nome_arquivo
            )
            
            # Inicializa o handler de planilhas para atualização
            sheets_handler = SheetsHandler()
            
            # Atualiza o título na planilha usando o método específico do SheetsHandler
            atualizado_titulo = sheets_handler.atualizar_titulo_documento(
                indice_linha=indice_real,
                titulo=titulo,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            )
            
            if atualizado_titulo:
                logger.info(f"Título atualizado na planilha com sucesso: {titulo}")
            else:
                logger.error("Falha ao atualizar o título na planilha")
            
            # Atualiza a URL na planilha usando o método específico do SheetsHandler
            atualizado_url = sheets_handler.atualizar_url_documento(
                indice_linha=indice_real,
                url_documento=url_documento,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            )
            
            if atualizado_url:
                logger.info(f"URL atualizada na planilha com sucesso: {url_documento}")
            else:
                logger.error("Falha ao atualizar a URL na planilha")
        else:
            logger.info("Modo teste ativado: não atualizando a planilha ou criando documento no Drive")
            
        logger.info(f"Processamento do ID {id_campanha} concluído com sucesso.")
        return True
        
    except Exception as e:
        # Log do erro incluindo o número da linha da planilha, se disponível
        sheet_row_num_erro = linha.get('sheet_row_num', 'N/A')
        logger.error(f"Erro ao processar linha {indice_real} (Sheet Row: {sheet_row_num_erro}): {e}")
        logger.exception("Detalhes completos do erro:")
        return False

def extrair_titulo(conteudo, palavra_ancora: str):
    """
    Extrai o título do conteúdo gerado, priorizando H1 (#) ou H2 (##).
    Aplica validações e correções subsequentes.
    """
    from src.gemini_handler import verificar_e_corrigir_titulo # Importa aqui para clareza
    logger = logging.getLogger('seo_linkbuilder.main') # Usar o logger apropriado

    linhas = conteudo.strip().split('\n')
    titulo_markdown_h1 = None
    titulo_markdown_h2 = None
    primeira_linha_nao_vazia = None

    for linha_atual in linhas:
        linha_limpa = linha_atual.strip()
        if not linha_limpa:
            continue

        if not primeira_linha_nao_vazia:
            primeira_linha_nao_vazia = linha_limpa

        if linha_limpa.startswith("# "):
            if titulo_markdown_h1 is None: # Pega o primeiro H1
                titulo_markdown_h1 = linha_limpa[2:].strip()
        elif linha_limpa.startswith("## "):
            if titulo_markdown_h2 is None: # Pega o primeiro H2
                titulo_markdown_h2 = linha_limpa[3:].strip()
    
    titulo_bruto_selecionado = None
    if titulo_markdown_h1:
        logger.info(f"Título H1 detectado: '{titulo_markdown_h1}'")
        titulo_bruto_selecionado = titulo_markdown_h1
    elif titulo_markdown_h2:
        logger.info(f"Título H2 detectado (H1 ausente): '{titulo_markdown_h2}'")
        titulo_bruto_selecionado = titulo_markdown_h2
    elif primeira_linha_nao_vazia:
        # Fallback para a primeira linha não vazia SOMENTE se não for um H1/H2 já processado
        # e se não começar com outros # (H3, H4 etc) que não queremos como título principal.
        if not (primeira_linha_nao_vazia.startswith("#") and primeira_linha_nao_vazia not in [titulo_markdown_h1, titulo_markdown_h2]):
             logger.warning(f"Nenhum H1 ou H2 encontrado. Usando primeira linha não vazia como fallback: '{primeira_linha_nao_vazia}'")
             titulo_bruto_selecionado = primeira_linha_nao_vazia
        else:
            logger.warning(f"Primeira linha é um H3+ ('{primeira_linha_nao_vazia}'). Não usando como título principal. Tentando fallback mais robusto.")

    if titulo_bruto_selecionado:
        titulo_verificado = verificar_e_corrigir_titulo(titulo_bruto_selecionado, palavra_ancora)
        if titulo_verificado:
            logger.info(f"Título bruto '{titulo_bruto_selecionado}' verificado para '{titulo_verificado}'")
            return titulo_verificado
        else:
            logger.warning(f"Título bruto '{titulo_bruto_selecionado}' foi rejeitado por verificar_e_corrigir_titulo. Tentando fallback.")

    # Fallback final se nada acima funcionou ou foi rejeitado
    logger.warning("Nenhum título claro encontrado ou todos foram rejeitados. Construindo fallback.")
    palavras_conteudo = [p for p in conteudo.split() if p.strip()][:10] # Pega as primeiras 10 palavras significativas
    titulo_fallback_bruto = ' '.join(palavras_conteudo).strip()
    
    # Garante que a âncora esteja no fallback se possível, sem duplicar
    if palavra_ancora.lower() not in titulo_fallback_bruto.lower():
        titulo_fallback_bruto = f"{palavra_ancora}: {titulo_fallback_bruto}"
    
    # Tenta verificar o fallback construído
    titulo_fallback_verificado = verificar_e_corrigir_titulo(titulo_fallback_bruto, palavra_ancora)
    if titulo_fallback_verificado:
        logger.info(f"Usando título de fallback verificado: '{titulo_fallback_verificado}'")
        return titulo_fallback_verificado
    
    # Último recurso se até o fallback verificado falhar (raro, mas para segurança)
    fallback_final_seguro = f"Artigo sobre {palavra_ancora}"
    # Tenta dar um tamanho mínimo, se possível, com base na âncora e algumas palavras
    if len(fallback_final_seguro) < 30 and palavras_conteudo:
        complemento = ' '.join(palavras_conteudo[:max(0, 9 - len(fallback_final_seguro.split()))]) # Tenta chegar a ~9 palavras
        if complemento:
            fallback_final_seguro = f"{fallback_final_seguro} - {complemento}"

    logger.error(f"Todos os métodos de extração de título falharam. Usando fallback genérico final: '{fallback_final_seguro}'")
    return fallback_final_seguro.strip()

def apresentar_menu_pasta_drive() -> str:
    """
    Apresenta um menu para confirmar ou alterar a pasta de destino no Google Drive.
    """
    logger = logging.getLogger('seo_linkbuilder')
    # Obtém o ID da pasta configurado atualmente (via .env ou padrão do config.py)
    current_folder_id = DRIVE_FOLDER_ID

    print("\n" + "="*60)
    print("SELEÇÃO DA PASTA DE DESTINO NO GOOGLE DRIVE".center(60))
    print("="*60)
    
    if not current_folder_id:
        logger.warning("Nenhum DRIVE_FOLDER_ID configurado no .env ou config.py!")
        print("\n⚠️ AVISO: Nenhuma pasta de destino padrão está configurada.")
        while True:
            novo_id = input("Por favor, insira o ID da pasta do Google Drive onde deseja salvar os documentos: ").strip()
            if novo_id:
                logger.info(f"Usando pasta do Drive com ID inserido: {novo_id}")
                return novo_id
            else:
                print("ID da pasta não pode ser vazio.")
    else:
        print(f"\nA pasta configurada para salvar os documentos é: {current_folder_id}")
        
        while True:
            confirmacao = input("Deseja usar esta pasta? (S para Sim / N para inserir outro ID): ").strip().upper()
            if confirmacao == 'S':
                logger.info(f"Usando pasta do Drive configurada: {current_folder_id}")
                return current_folder_id
            elif confirmacao == 'N':
                while True:
                    novo_id = input("Insira o novo ID da pasta do Google Drive: ").strip()
                    if novo_id:
                        logger.info(f"Usando pasta do Drive com ID inserido: {novo_id}")
                        return novo_id
                    else:
                        print("ID da pasta não pode ser vazio.")
            else:
                print("Opção inválida. Digite S ou N.")

def processar_planilha(limite_linhas: Optional[int] = None, 
                         linha_inicial_desejada: Optional[int] = None, # Novo parâmetro
                         modo_teste: bool = False, 
                         spreadsheet_id: Optional[str] = None, 
                         sheet_name: Optional[str] = None):
    """
    Processa a planilha, gerando conteúdo para cada linha, 
    considerando um limite de linhas e uma linha inicial desejada.
    
    Args:
        limite_linhas: Número máximo de linhas a processar (após filtro de linha inicial).
        linha_inicial_desejada: Número da linha da planilha a partir da qual começar.
        modo_teste: Se True, não salva os documentos no Google Drive nem atualiza planilha.
        spreadsheet_id: ID da planilha.
        sheet_name: Nome da aba.
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Inicializa handlers DENTRO da função para garantir que usem SPREADSHEET_ID e SHEET_NAME corretos
    # que foram definidos globalmente após seleção no menu.
    sheets = SheetsHandler() 
    gemini = GeminiHandler()
    docs = DocsHandler()

    # ANÁLISE DE PALAVRAS FREQUENTES E PADRÕES EM TÍTULOS EXISTENTES
    palavras_a_evitar_no_titulo = []
    todos_os_titulos_da_planilha = []
    padroes_por_ancora = {}
    try:
        logger.info("Analisando todos os títulos existentes na planilha para identificar palavras frequentes e padrões...")
        df_todos_os_dados = sheets.ler_planilha(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            filtrar_processados=False, # Pega todos os dados para análise completa
            apenas_dados=False # Retorna DataFrame
        )
        
        if not df_todos_os_dados.empty and COLUNAS['titulo'] < len(df_todos_os_dados.columns):
            titulos_existentes = df_todos_os_dados[COLUNAS['titulo']].dropna().astype(str).tolist()
            todos_os_titulos_da_planilha = titulos_existentes if titulos_existentes else []
            
            if titulos_existentes:
                palavras_a_evitar_no_titulo = identificar_palavras_frequentes_em_titulos(
                    titulos_existentes,
                    limiar_percentual=0.5, 
                    min_titulos_para_analise=10,
                    min_palavra_len=4 
                )
                if palavras_a_evitar_no_titulo:
                    logger.info(f"Novos títulos tentarão EVITAR as palavras (normalizadas): {palavras_a_evitar_no_titulo}")

                logger.info("Analisando títulos por palavra-âncora para identificar padrões repetitivos...")
                titulos_por_ancora_map = extrair_titulos_por_ancora(
                    df_todos_os_dados, 
                    COLUNAS['titulo'], 
                    COLUNAS['palavra_ancora']
                )
                padroes_por_ancora = identificar_padroes_por_ancora(titulos_por_ancora_map)
                logger.info(f"Identificados padrões repetitivos para {len(padroes_por_ancora)} palavras-âncora.")
        else:
            logger.info("DataFrame de todos os dados está vazio ou coluna de título não encontrada. Pulando análise de frequência/padrões.")
    except Exception as e:
        logger.error(f"Erro durante a análise de títulos existentes: {e}")
        logger.exception("Detalhes do erro na análise de títulos:")

    # LER DADOS PARA PROCESSAMENTO (considerando linha inicial e filtros de processados)
    logger.info(f"Lendo dados da planilha '{sheet_name}' ({spreadsheet_id}) para processamento...")
    df_para_processar = sheets.ler_planilha(
        limite_linhas=None, # O limite de linhas será aplicado DEPOIS do filtro de linha inicial
        linha_inicial=linha_inicial_desejada, # Novo parâmetro passado para sheets.ler_planilha
        filtrar_processados=True, # Mantém o filtro de itens já processados
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        apenas_dados=False # Queremos o DataFrame
    )

    if df_para_processar.empty:
        logger.warning(f"Nenhuma linha disponível para processamento após filtros iniciais (linha inicial, IDs, URLs existentes). Verifique as configurações e a planilha.")
        print("\n⚠️ AVISO: Nenhuma linha encontrada para processar com os critérios atuais.")
        return

    # Aplicar o limite de linhas DESEJADO APÓS o filtro de linha inicial
    if limite_linhas is not None and isinstance(limite_linhas, int) and limite_linhas > 0:
        if limite_linhas < len(df_para_processar):
            logger.info(f"Limitando o processamento às primeiras {limite_linhas} das {len(df_para_processar)} linhas disponíveis após o filtro de linha inicial.")
            df_para_processar = df_para_processar.head(limite_linhas)
        # else: o df já é menor ou igual ao limite, nada a fazer.
    
    total_linhas_a_processar = len(df_para_processar)
    if total_linhas_a_processar == 0:
        logger.warning("Nenhuma linha restante para processar após todas as filtragens e limites. Encerrando.")
        print("\n⚠️ Nenhuma linha selecionada para processamento final.")
        return

    logger.info(f"Serão processadas {total_linhas_a_processar} linhas.")
    if 'sheet_row_num' in df_para_processar.columns:
         logger.info(f"Linhas da planilha que serão efetivamente processadas (sheet_row_num): {df_para_processar['sheet_row_num'].tolist()}")

    # Estimativa de custo e confirmação (adaptado)
    prompt_template_texto = gemini.carregar_prompt_template()
    tokens_prompt_base = contar_tokens(prompt_template_texto)
    tokens_entrada_medio_estimado = tokens_prompt_base + 200 
    tokens_saida_medio_estimado = int(GEMINI_MAX_OUTPUT_TOKENS * 0.5) 
    custo_estimado_por_item_final = estimar_custo_gemini(tokens_entrada_medio_estimado, tokens_saida_medio_estimado)
    custo_estimado_total_final = custo_estimado_por_item_final * total_linhas_a_processar

    logger.info(f"Custo estimado total para processar {total_linhas_a_processar} itens: ${custo_estimado_total_final:.4f} USD (aproximadamente R${custo_estimado_total_final * USD_TO_BRL_RATE:.2f})")

    if not modo_teste:
         confirmacao = input(f"\nProcessar {total_linhas_a_processar} itens com custo estimado de R${custo_estimado_total_final * USD_TO_BRL_RATE:.2f}? (S/N): ").strip().upper()
         if confirmacao != 'S':
             logger.info("Operação cancelada pelo usuário antes do processamento. Encerrando.")
             return
    
    if modo_teste and total_linhas_a_processar > 0:
        logger.warning(f"MODO DE TESTE: Apenas a primeira linha selecionada (Sheet Row Num: {df_para_processar['sheet_row_num'].iloc[0] if 'sheet_row_num' in df_para_processar.columns else 'N/A'}) será efetivamente processada para geração de conteúdo. Nenhuma alteração será salva na planilha ou Drive.")
        # Processa apenas a primeira linha para teste de fluxo, mas não limita o df aqui para que o loop abaixo seja simples
    elif modo_teste and total_linhas_a_processar == 0:
        logger.warning("MODO DE TESTE ATIVADO, mas nenhuma linha selecionada para processar.")
        return

    custo_total_real = 0.0
    tokens_entrada_total_real = 0
    tokens_saida_total_real = 0
    artigos_processados_sucesso = 0

    for i, (idx_df, linha_series) in enumerate(df_para_processar.iterrows()):
        # Em modo teste, só executa a geração para a primeira linha do df_para_processar
        if modo_teste and i > 0:
            logger.info(f"[MODO TESTE] Pulando processamento da linha {i+1}/{total_linhas_a_processar} (Sheet Row: {linha_series.get('sheet_row_num', 'N/A')})")
            continue

        id_campanha = str(linha_series.get(COLUNAS['id'], 'Sem-ID'))
        site = str(linha_series.get(COLUNAS['site'], 'Sem site'))
        palavra_ancora = str(linha_series.get(COLUNAS['palavra_ancora'], 'Sem palavra-âncora'))
        url_ancora = str(linha_series.get(COLUNAS['url_ancora'], 'Sem URL'))
        titulo_original_da_planilha = str(linha_series.get(COLUNAS['titulo'], ''))
        if pd.isna(titulo_original_da_planilha) or not titulo_original_da_planilha.strip():
            titulo_original_da_planilha = ''
        
        sheet_row_num_original = linha_series.get('sheet_row_num', -1)
        if sheet_row_num_original == -1:
            logger.error(f"Coluna 'sheet_row_num' não encontrada na linha com ID {id_campanha}. Pulando atualização da planilha.")
            continue

        dados_gemini = {
            'id': id_campanha,
            'site': site,
            'palavra_ancora': palavra_ancora,
            'url_ancora': url_ancora,
            'titulo': titulo_original_da_planilha if titulo_original_da_planilha else f"Artigo sobre {palavra_ancora}", 
        }
        
        logger.info(f"Processando linha {i+1}/{total_linhas_a_processar}: ID {id_campanha} - Âncora: '{palavra_ancora}' (Sheet Row: {sheet_row_num_original})")
        logger.debug(f"Dados para Gemini: {dados_gemini}")
        
        instrucao_adicional_para_gemini = ""
        palavra_ancora_lower = palavra_ancora.lower().strip()
        if palavra_ancora_lower in padroes_por_ancora:
            # ... (lógica de instrução adicional para padrões específicos)
            padroes_especificos = padroes_por_ancora[palavra_ancora_lower]
            instrucao_padroes_especificos = f"\\n\\nREGRAS CRÍTICAS PARA ESTA PALAVRA-ÂNCORA ('{palavra_ancora}'):\\nNUNCA use os seguintes padrões já utilizados: {", ".join([f'\'{p}\'' for p in padroes_especificos])}.\\nUSE UMA ABORDAGEM COMPLETAMENTE NOVA."
            instrucao_adicional_para_gemini += instrucao_padroes_especificos

        if palavras_a_evitar_no_titulo:
            # ... (lógica de instrução para palavras a evitar)
            palavras_str = ", ".join([f"'{p}'" for p in palavras_a_evitar_no_titulo if ' ' not in p])
            frases_str = ", ".join([f"'{p}'" for p in palavras_a_evitar_no_titulo if ' ' in p])
            instrucao_evitar = "\\n\\nCRÍTICO PARA O TÍTULO:"
            if palavras_str: instrucao_evitar += f"\\n- EVITE PALAVRAS: {palavras_str}."
            if frases_str: instrucao_evitar += f"\\n- NUNCA USE PADRÕES/SEQUÊNCIAS: {frases_str}."
            instrucao_evitar += "\\n- Foque em originalidade."
            instrucao_adicional_para_gemini += instrucao_evitar
            
        logger.info(f"Gerando conteúdo com o Gemini para '{palavra_ancora}'...")
        
        titulos_anteriores_mesma_ancora = []
        if 'titulos_por_ancora_map' in locals() and palavra_ancora_lower in titulos_por_ancora_map:
            titulos_anteriores_mesma_ancora = titulos_por_ancora_map[palavra_ancora_lower]

        try:
            conteudo, metricas, info_link = gemini.gerar_conteudo(
                dados_gemini,
                instrucao_adicional=instrucao_adicional_para_gemini,
                titulos_existentes=todos_os_titulos_da_planilha
            )
            
            titulo_gerado = extrair_titulo(conteudo, palavra_ancora) # extrair_titulo já chama verificar_e_corrigir_titulo
            logger.info(f"Título final para artigo: '{titulo_gerado}'")

            # Atualiza métricas reais
            custo_total_real += metricas['custo_estimado']
            tokens_entrada_total_real += metricas['tokens_entrada']
            tokens_saida_total_real += metricas['tokens_saida']

            if not modo_teste:
                nome_arquivo = gerar_nome_arquivo(id_campanha, site, palavra_ancora, titulo_gerado)
                logger.info(f"Criando documento '{nome_arquivo}' na pasta {DRIVE_FOLDER_ID}...")
                document_id, document_url = docs.criar_documento(
                    titulo_gerado,
                    conteudo,
                    nome_arquivo,
                    info_link,
                    target_folder_id=DRIVE_FOLDER_ID
                )
                logger.info(f"Documento criado: {document_url}")
                
                sheets.atualizar_titulo_documento(
                    sheet_row_num=sheet_row_num_original,
                    titulo=titulo_gerado,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name
                )
                sheets.atualizar_url_documento(
                    sheet_row_num=sheet_row_num_original,
                    url_documento=document_url,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name
                )
                logger.info(f"✓ Planilha atualizada para ID {id_campanha} (linha {sheet_row_num_original}).")
                artigos_processados_sucesso += 1
            else:
                logger.info(f"[MODO TESTE] Conteúdo gerado para ID {id_campanha}. Título: '{titulo_gerado}'. (Simulação, nada salvo)")
                artigos_processados_sucesso += 1 # Conta como processado em modo teste para o resumo

        except Exception as e:
            logger.error(f"Erro crítico ao processar linha ID {id_campanha} (Sheet Row: {sheet_row_num_original}): {e}")
            logger.exception("Detalhes do erro no processamento da linha:")
            # TODO: Adicionar uma coluna "Erro" na planilha e registrar a falha?
        
        if not modo_teste: # Só pausa se não for modo teste e se não for a última linha
             if i < total_linhas_a_processar -1:
                 logger.info(f"Aguardando {DELAY_ENTRE_CHAMADAS_GEMINI} segundos antes da próxima chamada...")
                 time.sleep(DELAY_ENTRE_CHAMADAS_GEMINI)
             else:
                 logger.info("Última linha processada, sem delay final.")

    logger.info(f"\n{'='*50}")
    logger.info(f"RESUMO FINAL DA EXECUÇÃO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total de artigos que deveriam ser processados: {total_linhas_a_processar}")
    logger.info(f"Total de artigos efetivamente processados (ou simulados em modo teste): {artigos_processados_sucesso}")
    logger.info(f"Tokens de entrada (real): {tokens_entrada_total_real}")
    logger.info(f"Tokens de saída (real): {tokens_saida_total_real}")
    logger.info(f"Custo total (real): ${custo_total_real:.4f} USD (aproximadamente R${custo_total_real * USD_TO_BRL_RATE:.2f})")
    logger.info(f"{'='*50}")

    # Ações pós-processamento (descomentar e ajustar se necessário)
    # if not modo_teste and artigos_processados_sucesso > 0: 
    # logger.info("Iniciando verificações de qualidade pós-processamento...")
    # verificar_titulos_duplicados(sheets, gemini, docs, modo_teste=False, spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    # verificar_similaridade_conteudos(sheets, gemini, docs, limiar_similaridade=0.4, modo_teste=False, spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    # corrigir_termos_proibidos(sheets, docs, modo_teste=False, spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)

def main(modo_teste: bool = False): # Removido argumentos não utilizados diretamente no novo menu
    logger = configurar_logging(logging.INFO)
    logger.info(f"Iniciando script SEO-LinkBuilder - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if modo_teste:
        logger.warning("=== MODO DE TESTE ATIVADO === Geração de documentos e escrita na planilha podem ser pulados.")

    try:
        sheets = SheetsHandler()
        # gemini = GeminiHandler() # Inicializado dentro de processar_planilha se necessário
        # docs = DocsHandler()   # Inicializado dentro de processar_planilha se necessário
        
        target_drive_folder_id = apresentar_menu_pasta_drive()
        if not target_drive_folder_id:
             logger.error("ID da pasta do Drive não foi obtido. Encerrando.")
             return
        
        spreadsheet_id_selecionado, sheet_name_selecionado = apresentar_menu_planilha(sheets)
        if not spreadsheet_id_selecionado or not sheet_name_selecionado:
            logger.error("ID da planilha ou nome da aba não selecionado. Encerrando.")
            return

        global SPREADSHEET_ID, SHEET_NAME, DRIVE_FOLDER_ID
        SPREADSHEET_ID = spreadsheet_id_selecionado
        SHEET_NAME = sheet_name_selecionado
        DRIVE_FOLDER_ID = target_drive_folder_id
        logger.info(f"Configurações: Planilha '{SPREADSHEET_ID}', Aba '{SHEET_NAME}', Pasta Destino '{DRIVE_FOLDER_ID}'")

        # Menu de seleção de quantidade e linha inicial
        linha_inicial_desejada: Optional[int] = None
        quantidade_linhas_a_processar: Optional[int] = None

        while True:
            print("\\nComo deseja processar as linhas da planilha?")
            print("  T - Processar todas as linhas pendentes")
            print("  Q - Processar uma quantidade específica de linhas pendentes")
            print("  L - Processar a partir de uma linha específica da planilha")
            print("  X - Sair")
            escolha_processamento = input("Escolha uma opção: ").strip().upper()

            if escolha_processamento == 'T':
                linha_inicial_desejada = None
                quantidade_linhas_a_processar = None
                logger.info("Opção selecionada: Processar todas as linhas pendentes.")
                break
            elif escolha_processamento == 'Q':
                linha_inicial_desejada = None
                while True:
                    try:
                        num = input("Digite a quantidade de linhas pendentes que deseja processar: ").strip()
                        if not num: # Usuário apenas apertou Enter
                             quantidade_linhas_a_processar = None # Interpretar como todas
                             logger.info("Nenhuma quantidade especificada, processando todas as linhas pendentes.")
                             break
                        quantidade_linhas_a_processar = int(num)
                        if quantidade_linhas_a_processar <= 0:
                            print("A quantidade deve ser um número positivo.")
                        else:
                            logger.info(f"Opção selecionada: Processar {quantidade_linhas_a_processar} linhas pendentes.")
                            break
                    except ValueError:
                        print("Entrada inválida. Por favor, digite um número.")
                break
            elif escolha_processamento == 'L':
                while True:
                    try:
                        num_linha_str = input("Digite o número da linha da planilha a partir da qual deseja começar (ex: 10): ").strip()
                        linha_inicial_desejada = int(num_linha_str)
                        if linha_inicial_desejada <= 1: # Linha 1 é geralmente cabeçalho
                            print("O número da linha inicial deve ser maior que 1.")
                        else:
                            logger.info(f"Opção selecionada: Processar a partir da linha {linha_inicial_desejada} da planilha.")
                            break
                    except ValueError:
                        print("Entrada inválida. Por favor, digite um número de linha válido.")
                
                # Submenu para "L"
                while True:
                    print(f"\\nA partir da linha {linha_inicial_desejada}, deseja processar:")
                    print("  T - Todas as linhas subsequentes pendentes")
                    print("  Q - Uma quantidade específica de linhas")
                    escolha_sub_l = input("Escolha uma opção (T/Q): ").strip().upper()

                    if escolha_sub_l == 'T':
                        quantidade_linhas_a_processar = None
                        logger.info(f"Processando todas as linhas pendentes a partir da linha {linha_inicial_desejada}.")
                        break
                    elif escolha_sub_l == 'Q':
                        while True:
                            try:
                                num_qtd_str = input(f"Digite a quantidade de linhas que deseja processar a partir da linha {linha_inicial_desejada}: ").strip()
                                if not num_qtd_str: # Usuário apenas apertou Enter
                                    quantidade_linhas_a_processar = None # Interpretar como todas a partir da linha inicial
                                    logger.info(f"Nenhuma quantidade especificada, processando todas as linhas pendentes a partir da linha {linha_inicial_desejada}.")
                                    break
                                quantidade_linhas_a_processar = int(num_qtd_str)
                                if quantidade_linhas_a_processar <= 0:
                                    print("A quantidade deve ser um número positivo.")
                                else:
                                    logger.info(f"Processando {quantidade_linhas_a_processar} linhas a partir da linha {linha_inicial_desejada}.")
                                    break
                            except ValueError:
                                print("Entrada inválida. Por favor, digite um número.")
                        break
                    else:
                        print("Opção inválida. Escolha T ou Q.")
                break
            elif escolha_processamento == 'X':
                logger.info("Processamento cancelado pelo usuário.")
                return
            else:
                print("Opção inválida. Por favor, tente novamente.")
        
        # VERIFICAÇÕES PRELIMINARES (exemplo: verificar duplicados, similaridade, termos proibidos)
        # Estas funções podem ser chamadas aqui, ANTES do processamento principal linha a linha,
        # se fizer sentido executá-las no escopo da planilha inteira (ou na seleção atual).
        # Elas precisam ser ajustadas para receberem spreadsheet_id e sheet_name.

        # Exemplo de chamada (descomentar e ajustar conforme necessário):
        # logger.info("Executando verificações preliminares...")
        # verificar_titulos_duplicados(sheets, gemini, docs, modo_teste=modo_teste, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME)
        # verificar_similaridade_conteudos(sheets, gemini, docs, modo_teste=modo_teste, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME)
        # corrigir_termos_proibidos(sheets, docs, modo_teste=modo_teste, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME)
        # logger.info("Verificações preliminares concluídas.")

        # Iniciar o processamento da planilha com os parâmetros definidos
        processar_planilha(
            limite_linhas=quantidade_linhas_a_processar, 
            linha_inicial_desejada=linha_inicial_desejada, # Novo parâmetro
            modo_teste=modo_teste,
            spreadsheet_id=SPREADSHEET_ID, 
            sheet_name=SHEET_NAME
        )

    except Exception as e:
        logger.error(f"Erro GERAL durante a execução do script: {e}")
        logger.exception("Detalhes do erro GERAL:")
    finally:
        logger.info(f"Script SEO-LinkBuilder finalizado - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SEO-LinkBuilder - Gerador de conteúdo para SEO')
    parser.add_argument('--teste', action='store_true',
                        help='Executa apenas para a primeira linha sem atualizar a planilha e simula interações com APIs.')
    
    args = parser.parse_args()
    
    # Os argumentos 'limite' e 'todos' foram removidos. 
    # A lógica para determinar o número de linhas e a partir de qual linha começar
    # agora está dentro da função main() através de um menu interativo.
    
    # Executa o script principal, passando apenas o modo_teste
    main(modo_teste=args.teste)