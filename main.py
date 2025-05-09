# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Set
from datetime import datetime
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import dotenv
import json

from src.utils import configurar_logging
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler, verificar_conteudo_proibido
from src.docs_handler import DocsHandler
from src.config import (
    gerar_nome_arquivo, 
    COLUNAS, 
    estimar_custo_gemini, 
    GEMINI_MAX_OUTPUT_TOKENS, 
    MESES,
    SPREADSHEET_ID,
    SHEET_NAME,
    DRIVE_FOLDER_ID
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
                time.sleep(1)
                
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
        titulo = extrair_titulo(conteudo_gerado)
        
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

def extrair_titulo(conteudo):
    """
    Extrai o título do conteúdo gerado (primeira linha não vazia).
    """
    linhas = conteudo.strip().split('\n')
    for linha in linhas:
        linha_limpa = linha.strip()
        if linha_limpa and not linha_limpa.startswith('#'):
            # Remove marcadores de formatação (** para negrito, etc)
            return re.sub(r'[*_#]', '', linha_limpa)
    
    # Se não encontrar um título claro, usa as primeiras palavras
    palavras = conteudo.split()[:5]
    titulo_padrao = ' '.join(palavras) + '...'
    return titulo_padrao

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

def processar_planilha(limite_linhas=None, modo_teste=False, spreadsheet_id=None, sheet_name=None):
    """
    Processa a planilha, gerando conteúdo para cada linha.
    
    Args:
        limite_linhas: Número máximo de linhas a processar
        modo_teste: Se True, não salva os documentos no Google Drive
        spreadsheet_id: ID da planilha (opcional)
        sheet_name: Nome da aba (opcional)
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Inicializa handlers
    sheets = SheetsHandler()
    gemini = GeminiHandler()
    docs = DocsHandler()
    
    # Lê a planilha
    df = sheets.ler_planilha(limite_linhas=limite_linhas, spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    
    # ADICIONE ESTE LOG PARA VERIFICAR AS LINHAS QUE SERÃO PROCESSADAS
    logger.info(f"Linhas que serão processadas em ordem: {df['sheet_row_num'].tolist()}")
    logger.info(f"Índices do DataFrame que serão processados: {df.index.tolist()}")
    
    # Continua com o processamento...
    # ... existing code ...

def main(limite_linhas: int = None, modo_teste: bool = False, categorias_selecionadas: Dict = None, quantidade_especifica: int = None):
    """
    Função principal que orquestra a leitura da planilha, geração de conteúdo e criação de documentos.
    """
    logger = configurar_logging(logging.INFO)
    logger.info(f"Iniciando script SEO-LinkBuilder - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if modo_teste:
        logger.warning("=== MODO DE TESTE ATIVADO ===")
        logger.warning("Nenhuma alteração será feita na planilha ou nos documentos do Google Drive.")
    
    try:
        # Inicializa handlers
        sheets = SheetsHandler()
        gemini = GeminiHandler()
        docs = DocsHandler()
        
        # NOVO: Apresenta menu para selecionar pasta do Drive
        target_drive_folder_id = apresentar_menu_pasta_drive()
        if not target_drive_folder_id: # Segurança caso algo dê errado no menu
             logger.error("ID da pasta do Drive não foi obtido. Encerrando.")
             return
        
        # 1. Apresenta o menu para selecionar Planilha e Aba
        spreadsheet_id_selecionado, sheet_name_selecionado = apresentar_menu_planilha(sheets)
        
        # Atualiza as configurações globais (opcional, mas pode ser útil)
        global SPREADSHEET_ID, SHEET_NAME
        SPREADSHEET_ID = spreadsheet_id_selecionado
        SHEET_NAME = sheet_name_selecionado
        logger.info(f"Processando Planilha: {SPREADSHEET_ID}, Aba: {SHEET_NAME}")

        # 5. Lê a planilha com base na seleção
        logger.info(f"Lendo dados da planilha '{SHEET_NAME}' ({SPREADSHEET_ID})...")
        # A função ler_planilha já filtra por IDs válidos e URLs vazias,
        # e já retorna o DataFrame ordenado por 'sheet_row_num'.
        # O argumento 'limite_linhas' para ler_planilha pode ser usado se quisermos limitar a leitura inicial,
        # mas a lógica de "processar N itens" geralmente é melhor aplicada depois.
        # Por enquanto, vamos deixar ler_planilha carregar todos os itens disponíveis (não processados e com ID válido).
        df_disponivel_para_processar = sheets.ler_planilha(
            spreadsheet_id=SPREADSHEET_ID,
            sheet_name=SHEET_NAME
            # Não passaremos limite_linhas aqui para que o menu de categorias veja todos os disponíveis.
        )

        if df_disponivel_para_processar.empty:
            logger.warning(f"Nenhuma linha disponível para processamento (sem ID válido ou já com URL) encontrada na planilha!")
            print(f"\n⚠️ AVISO: Nenhuma linha disponível para processamento encontrada.")
            print("Verifique se a planilha contém dados com IDs válidos e sem URL de documento preenchida.")
            return

        total_linhas_disponiveis = len(df_disponivel_para_processar)
        logger.info(f"Planilha lida com {total_linhas_disponiveis} linhas disponíveis para processamento (ordenadas por linha da planilha).")
        if 'sheet_row_num' in df_disponivel_para_processar.columns:
            logger.info(f"Próximas linhas disponíveis para processamento (sheet_row_num): {df_disponivel_para_processar['sheet_row_num'].head().tolist()}")

        # Estimar custos por categoria usando apenas as linhas realmente disponíveis
        categorias = estimar_custo_por_categoria(sheets, df_disponivel_para_processar)

        # DataFrame final que será processado
        df_para_processar_final = df_disponivel_para_processar.copy()

        # Se não foram fornecidas categorias/quantidade na chamada da função, apresentar menu
        num_itens_do_menu = None
        if categorias_selecionadas is None and quantidade_especifica is None:
            selecao_menu = apresentar_menu_categorias(categorias) # Esta função precisa ser ajustada

            if selecao_menu is None: # Usuário cancelou
                logger.info("Operação cancelada pelo usuário. Encerrando.")
                return

            if 'quantidade_especifica' in selecao_menu:
                num_itens_do_menu = selecao_menu['quantidade_especifica']
                # Não filtramos por categoria se quantidade específica foi escolhida no menu principal.
                # O df_para_processar_final já contém todos os disponíveis e ordenados.
            else:
                # Filtra por categoria se uma ou mais categorias foram selecionadas
                df_para_processar_final = filtrar_dataframe_por_categorias(df_para_processar_final, sheets, selecao_menu)
                # filtrar_dataframe_por_categorias deve manter a ordem se o df de entrada estiver ordenado.
                # Reordenar por 'sheet_row_num' por segurança, caso a função interna não garanta.
                if 'sheet_row_num' in df_para_processar_final.columns:
                     df_para_processar_final.sort_values(by='sheet_row_num', inplace=True)

        elif categorias_selecionadas is not None: # Categorias fornecidas como argumento
            df_para_processar_final = filtrar_dataframe_por_categorias(df_para_processar_final, sheets, categorias_selecionadas)
            if 'sheet_row_num' in df_para_processar_final.columns:
                 df_para_processar_final.sort_values(by='sheet_row_num', inplace=True)
        
        # Determinar o número final de linhas a processar
        # Prioridade: argumento da função 'quantidade_especifica', depois 'num_itens_do_menu', depois 'limite_linhas' (CLI)
        limite_final_linhas = None
        if quantidade_especifica is not None: # Argumento da função main()
            limite_final_linhas = quantidade_especifica
        elif num_itens_do_menu is not None: # Escolha 'Q' no menu
            limite_final_linhas = num_itens_do_menu
        elif limite_linhas is not None: # Argumento --limite da CLI
            limite_final_linhas = limite_linhas
        
        # Aplicar o limite final ao df_para_processar_final
        if limite_final_linhas is not None:
            if limite_final_linhas <= 0:
                logger.warning("Número de itens para processar é zero ou negativo. Nada a fazer.")
                return
            if limite_final_linhas < len(df_para_processar_final):
                logger.info(f"Limitando o processamento às primeiras {limite_final_linhas} das {len(df_para_processar_final)} linhas filtradas e ordenadas.")
                df_para_processar_final = df_para_processar_final.head(limite_final_linhas)
            else:
                logger.info(f"Número solicitado ({limite_final_linhas}) é maior ou igual ao disponível ({len(df_para_processar_final)}). Processando todos os {len(df_para_processar_final)} itens.")
                # Nenhuma ação necessária, já estamos usando todo o df_para_processar_final
        
        # Verificar se ainda há linhas após toda a filtragem e limitação
        total_linhas_a_processar = len(df_para_processar_final)
        if total_linhas_a_processar == 0:
            logger.warning("Nenhuma linha restante para processar após todas as filtragens e limites. Encerrando.")
            return

        logger.info(f"Serão processadas {total_linhas_a_processar} linhas.")
        if 'sheet_row_num' in df_para_processar_final.columns:
             logger.info(f"Linhas da planilha que serão efetivamente processadas (sheet_row_num): {df_para_processar_final['sheet_row_num'].tolist()}")


        # Estimar custo total com base nas linhas que serão efetivamente processadas
        tokens_entrada_medio_estimado = 1700
        tokens_saida_medio_estimado = 500
        custo_estimado_por_item_final = estimar_custo_gemini(tokens_entrada_medio_estimado, tokens_saida_medio_estimado)
        custo_estimado_total_final = custo_estimado_por_item_final * total_linhas_a_processar

        logger.info(f"Custo estimado total para processar {total_linhas_a_processar} itens: ${custo_estimado_total_final:.4f} USD (aproximadamente R${custo_estimado_total_final*5:.2f})")

        # Confirmar execução
        if not modo_teste: # Não pedir confirmação em modo teste se for processar apenas 1 linha
             confirmacao = input(f"\nProcessar {total_linhas_a_processar} itens com custo estimado de R${custo_estimado_total_final*5:.2f}? (S/N): ").strip().upper()
             if confirmacao != 'S':
                 logger.info("Operação cancelada pelo usuário antes do processamento. Encerrando.")
                 return
        
        # Modo teste (se ativado via CLI) usa apenas a primeira linha do df_para_processar_final
        # Esta lógica de modo teste via CLI pode ser redundante se a função main já recebe modo_teste=True
        if modo_teste and total_linhas_a_processar > 0: # Garante que há pelo menos uma linha
            # Se o modo_teste já está limitando a 1 linha, esta re-fatiamento é segura.
            # Se o modo_teste é apenas para não salvar, mas processar o 'limite_linhas' do CLI, então não re-fatiar aqui.
            # A definição original do --teste era "Executa apenas para a primeira linha sem atualizar a planilha"
            # então, se modo_teste é True, pegamos apenas a primeira linha do que quer que tenha sido selecionado.
            df_para_processar_final = df_para_processar_final.head(1)
            total_linhas_a_processar = len(df_para_processar_final) # Atualiza a contagem
            logger.info(f"EXECUTANDO EM MODO DE TESTE - Apenas a primeira linha selecionada será processada (Sheet Row Num: {df_para_processar_final['sheet_row_num'].iloc[0] if not df_para_processar_final.empty and 'sheet_row_num' in df_para_processar_final.columns else 'N/A'})")
        elif modo_teste and total_linhas_a_processar == 0:
            logger.warning("MODO DE TESTE ATIVADO, mas nenhuma linha selecionada para processar.")
            return

        # Métricas de custo
        custo_total = 0.0
        tokens_entrada_total = 0
        tokens_saida_total = 0
        
        # Processa cada linha
        for i, (idx, linha) in enumerate(df_para_processar_final.iterrows()):
            try:
                # Acesso direto às colunas ao invés de extrair_dados_linha
                id_campanha = str(linha[COLUNAS['id']]) if COLUNAS['id'] < len(linha) else 'Sem-ID'
                site = str(linha[COLUNAS['site']]) if COLUNAS['site'] < len(linha) else 'Sem site'
                palavra_ancora = str(linha[COLUNAS['palavra_ancora']]) if COLUNAS['palavra_ancora'] < len(linha) else 'Sem palavra-âncora'
                url_ancora = str(linha[COLUNAS['url_ancora']]) if COLUNAS['url_ancora'] < len(linha) else 'Sem URL'
                titulo_original = str(linha[COLUNAS['titulo']]) if COLUNAS['titulo'] < len(linha) and linha[COLUNAS['titulo']] else 'Sem título'

                # Obter o número real da linha da planilha
                if 'sheet_row_num' not in linha:
                     logger.error(f"Coluna 'sheet_row_num' não encontrada na linha com ID {id_campanha}. Pulando atualização da planilha.")
                     continue
                sheet_row_num = int(linha['sheet_row_num'])
                
                # Cria um dicionário de dados para passar para o Gemini
                dados = {
                    'id': id_campanha,
                    'site': site,
                    'palavra_ancora': palavra_ancora,
                    'url_ancora': url_ancora,
                    'titulo': titulo_original, # Usar o título original aqui
                    'tema': 'Sem tema',  # Tema não existe na estrutura atual
                }
                
                logger.info(f"Processando linha {i+1}/{len(df_para_processar_final)}: ID {id_campanha} - {titulo_original} (Sheet Row: {sheet_row_num})")
                
                # LOG ADICIONAL: Verifica os dados enviados ao Gemini
                logger.debug(f"Enviando para Gemini - ID: {dados.get('id')}, Ancora: '{dados.get('palavra_ancora')}', Titulo Original: '{dados.get('titulo')}'")
                
                # Gera o conteúdo usando o Gemini
                logger.info(f"Gerando conteúdo com o Gemini para '{palavra_ancora}'...")
                conteudo, metricas, info_link = gemini.gerar_conteudo(dados)
                
                # Atualiza métricas
                custo_total += metricas['custo_estimado']
                tokens_entrada_total += metricas['tokens_entrada']
                tokens_saida_total += metricas['tokens_saida']
                
                # Extrai o título real do conteúdo gerado (primeira linha)
                titulo_gerado = extrair_titulo(conteudo) # Usar função para extrair título
                logger.info(f"Título gerado: {titulo_gerado}")
                
                # Gera o nome do arquivo usando o ID em vez da data
                try:
                    nome_arquivo = gerar_nome_arquivo(id_campanha, site, palavra_ancora)
                except Exception as e:
                    logger.error(f"Erro ao gerar nome de arquivo: {e}")
                    # Fallback para um nome simples
                    nome_arquivo = f"{id_campanha} - {site} - Artigo"
                
                # Cria o documento no Google Docs, PASSANDO O ID DA PASTA SELECIONADO
                logger.info(f"Criando documento '{nome_arquivo}' na pasta {target_drive_folder_id}...")
                document_id, document_url = docs.criar_documento(
                    titulo_gerado,
                    conteudo,
                    nome_arquivo,
                    info_link,
                    target_folder_id=target_drive_folder_id # Passa o ID selecionado
                )
                
                # Atualiza a URL e o título na planilha (se não estiver em modo de teste)
                if not modo_teste:
                    try:
                        # Usa sheet_row_num diretamente
                        linha_planilha = sheet_row_num
                        
                        # Imprime detalhes de diagnóstico ANTES de atualizar
                        logger.info(f"==== INFORMAÇÕES DE ATUALIZAÇÃO DA PLANILHA ====")
                        logger.info(f"ID da Planilha: {SPREADSHEET_ID}")
                        logger.info(f"Nome da Aba: {SHEET_NAME}")
                        logger.info(f"Índice Original da Linha (0-based data): {linha.name}") # Log do índice do DF
                        logger.info(f"Linha na planilha a ser atualizada (1-based): {linha_planilha}")
                        
                        # Atualiza o título (coluna I)
                        coluna_titulo = 'I' # Coluna do título
                        titulo_range = f"{SHEET_NAME}!{coluna_titulo}{linha_planilha}"
                        logger.info(f"Tentando atualizar Título na célula {coluna_titulo}{linha_planilha} (Range: {titulo_range}) com valor: '{titulo_gerado}'")
                        
                        atualizado_titulo = sheets.atualizar_titulo_documento(
                            sheet_row_num=linha_planilha, # Passa o número correto
                            titulo=titulo_gerado,
                            spreadsheet_id=SPREADSHEET_ID,
                            sheet_name=SHEET_NAME
                        )
                        
                        logger.info(f"✓ Título atualizado com sucesso em {titulo_range}!")
                        
                        # Atualiza a URL (coluna J)
                        coluna_url = 'J' # Coluna da URL
                        url_range = f"{SHEET_NAME}!{coluna_url}{linha_planilha}"
                        logger.info(f"Tentando atualizar URL na célula {coluna_url}{linha_planilha} (Range: {url_range}) com valor: '{document_url}'")
                        
                        atualizado_url = sheets.atualizar_url_documento(
                            sheet_row_num=linha_planilha, # Passa o número correto
                            url_documento=document_url,
                            spreadsheet_id=SPREADSHEET_ID,
                            sheet_name=SHEET_NAME
                        )
                        
                        logger.info(f"✓ URL atualizada com sucesso em {url_range}!")
                        logger.info(f"==== FIM DA ATUALIZAÇÃO DA PLANILHA ====")
                        
                    except Exception as e:
                        logger.error(f"Erro ao atualizar planilha para linha {sheet_row_num}: {e}")
                        logger.exception("Detalhes do erro:")
                else:
                    logger.info(f"[MODO TESTE] URL gerada (não atualizada na planilha): {document_url}")
                    logger.info(f"[MODO TESTE] Título gerado (não atualizado na planilha): {titulo_gerado}")
                
                # Pausa para não sobrecarregar as APIs
                time.sleep(1)
                
            except Exception as e:
                # Log do erro incluindo o número da linha da planilha, se disponível
                sheet_row_num_erro = linha.get('sheet_row_num', 'N/A')
                logger.error(f"Erro ao processar linha {i+1} (Sheet Row: {sheet_row_num_erro}): {e}")
                logger.exception("Detalhes completos do erro:")
                continue # Continua para a próxima linha em caso de erro
        
        # Exibe resumo
        logger.info(f"\n{'='*50}")
        logger.info(f"RESUMO DE EXECUÇÃO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Total de artigos processados: {len(df_para_processar_final)}")
        logger.info(f"Tokens de entrada: {tokens_entrada_total}")
        logger.info(f"Tokens de saída: {tokens_saida_total}")
        logger.info(f"Custo total estimado: ${custo_total:.4f} USD (aproximadamente R${custo_total*5:.2f})")
        logger.info(f"{'='*50}")
        
        # Verifica e corrige títulos duplicados, similaridade e termos proibidos (somente se não estiver em modo de teste)
        if not modo_teste and limite_linhas is None:
            logger.info("Iniciando verificação de títulos duplicados...")
            verificar_titulos_duplicados(sheets, gemini, docs, modo_teste=False)
            
            logger.info("Iniciando verificação de similaridade entre conteúdos...")
            verificar_similaridade_conteudos(sheets, gemini, docs, limiar_similaridade=0.4, modo_teste=False)
            
            logger.info("Iniciando verificação de termos proibidos...")
            corrigir_termos_proibidos(sheets, docs, modo_teste=False)
        elif not modo_teste:
            logger.info("Processamento com limite de linhas. Verificações de duplicidade, similaridade e termos proibidos serão ignoradas.")
        else:
            logger.info("Modo de teste ativo. Verificações de duplicidade, similaridade e termos proibidos serão ignoradas.")
    except Exception as e:
        logger.error(f"Erro durante a execução do script: {e}")
        logger.exception("Detalhes do erro:")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SEO-LinkBuilder - Gerador de conteúdo para SEO')
    parser.add_argument('--limite', type=int, default=None, # Mudar default para None
                        help='Número máximo de linhas a processar (padrão: processar todas)') # Atualizar help
    parser.add_argument('--teste', action='store_true',
                        help='Executa apenas para a primeira linha sem atualizar a planilha')
    parser.add_argument('--todos', action='store_true',
                        help='Processa todas as linhas da planilha')
    
    args = parser.parse_args()
    
    # Define o limite de linhas
    if args.todos:
        limite = None  # Sem limite
    else:
        limite = args.limite
    
    # Executa o script principal com o menu interativo
    main(limite_linhas=limite, modo_teste=args.teste)