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

from src.utils import configurar_logging
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler, verificar_conteudo_proibido
from src.docs_handler import DocsHandler
from src.config import gerar_nome_arquivo, COLUNAS, estimar_custo_gemini, GEMINI_MAX_OUTPUT_TOKENS, MESES

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
                
                # Atualiza o documento
                document_id, document_url = docs.atualizar_documento(doc_reescrever['id_doc'], 
                                                                    titulo_novo, 
                                                                    conteudo, 
                                                                    nome_arquivo, 
                                                                    info_link)
                
                # Atualiza a URL e o título na planilha, se necessário
                if document_url != doc_reescrever['url']:
                    sheets.atualizar_url_documento(doc_reescrever['indice'], document_url)
                
                # Sempre atualiza o título, pois deve ter mudado
                sheets.atualizar_titulo_documento(doc_reescrever['indice'], titulo_novo)
                
                logger.info(f"✓ Documento reescrito com sucesso: {titulo_novo}")
                
            except Exception as e:
                logger.error(f"Erro ao reescrever documento: {e}")
                logger.exception("Detalhes do erro:")
        
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
        categorias: Dicionário com estatísticas por categoria
        
    Returns:
        Dicionário com as categorias selecionadas (valor booleano)
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Filtrar apenas categorias com pelo menos um item
    categorias_com_itens = {k: v for k, v in categorias.items() if v['count'] > 0}
    
    if not categorias_com_itens:
        logger.warning("Nenhuma categoria com itens encontrada")
        return {}
    
    # Ordenar por contagem (do maior para o menor)
    categorias_ordenadas = sorted(categorias_com_itens.items(), key=lambda x: x[1]['count'], reverse=True)
    
    # Dicionário para armazenar seleção
    selecao = {}
    
    print("\n" + "="*60)
    print("MENU DE SELEÇÃO DE CATEGORIAS".center(60))
    print("="*60)
    
    # Mostrar contagem total
    total_itens = sum(v['count'] for v in categorias_com_itens.values())
    total_custo = sum(v.get('custo_total', 0) for v in categorias_com_itens.values())
    print(f"\nTotal de itens: {total_itens} | Custo estimado total: R${total_custo*5:.2f}")
    print("\nCategorias disponíveis:")
    
    # Apresentar opções
    print("\nCódigo | Categoria              | Quantidade | Custo estimado (R$)")
    print("-"*60)
    
    # Adicionar TODOS OS JOGOS como a primeira opção
    print(f"0      | TODOS OS JOGOS          | {total_itens:^10} | R${total_custo*5:.2f}")
    print("-"*60)
    
    for i, (categoria, stats) in enumerate(categorias_ordenadas, 1):
        # Formatar para alinhamento
        cat_formatada = f"{categoria[:20]:<20}"
        custo_total = stats.get('custo_total', 0) * 5  # Converter para reais
        print(f"{i:^6} | {cat_formatada} | {stats['count']:^10} | R${custo_total:.2f}")
    
    # Opções adicionais
    print("-"*60)
    print(f"T      | TODOS OS ITENS          | {total_itens:^10} | R${total_custo*5:.2f}")
    print(f"Q      | QUANTIDADE ESPECÍFICA   | -          | -")
    print("-"*60)
    
    # Solicitar escolha do usuário
    while True:
        escolha = input("\nEscolha uma opção (número, T para todos, Q para quantidade, ou X para sair): ").strip().upper()
        
        if escolha == 'X':
            logger.info("Operação cancelada pelo usuário")
            return None
            
        elif escolha == 'T' or escolha == '0':
            # Selecionar todos
            for categoria in categorias_com_itens:
                selecao[categoria] = True
            logger.info(f"Selecionados todos os {total_itens} itens (custo estimado: R${total_custo*5:.2f})")
            break
            
        elif escolha == 'Q':
            # Quantidade específica
            try:
                quantidade = int(input("Digite a quantidade de itens a processar: "))
                if quantidade <= 0:
                    print("Por favor, digite um número maior que zero.")
                    continue
                    
                if quantidade > total_itens:
                    print(f"A quantidade solicitada ({quantidade}) é maior que o total disponível ({total_itens}). Usando o total disponível.")
                    quantidade = total_itens
                
                custo_medio = total_custo / total_itens if total_itens > 0 else 0
                custo_estimado = custo_medio * quantidade
                
                logger.info(f"Selecionados {quantidade} itens aleatórios (custo estimado: R${custo_estimado*5:.2f})")
                
                # Retornar quantidade como um parâmetro especial
                return {'quantidade_especifica': quantidade}
                
            except ValueError:
                print("Por favor, digite um número válido.")
                continue
                
        else:
            # Tentar converter para número
            try:
                indice = int(escolha)
                if 1 <= indice <= len(categorias_ordenadas):
                    categoria_selecionada = categorias_ordenadas[indice - 1][0]
                    stats = categorias_ordenadas[indice - 1][1]
                    
                    logger.info(f"Selecionada categoria '{categoria_selecionada}' com {stats['count']} itens (custo estimado: R${stats.get('custo_total', 0)*5:.2f})")
                    
                    # Marcar apenas a categoria selecionada
                    for categoria in categorias_com_itens:
                        selecao[categoria] = (categoria == categoria_selecionada)
                    
                    break
                else:
                    print(f"Por favor, digite um número entre 0 e {len(categorias_ordenadas)}.")
            except ValueError:
                print("Opção inválida. Por favor, tente novamente.")
    
    return selecao

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
            return df
        else:
            logger.info(f"Selecionando {quantidade} itens aleatoriamente.")
            return df.sample(n=quantidade, random_state=42)
    
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
    Verifica se existem dados para o período selecionado.
    
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
        
        # Verificar quais períodos têm dados disponíveis se o sheets foi fornecido
        periodos_disponiveis = {}
        if sheets is not None:
            logger.info("Verificando períodos disponíveis na planilha...")
            try:
                df_completo = sheets.ler_planilha(None, apenas_dados=True)
                
                if not df_completo.empty and COLUNAS["data"] < len(df_completo.columns):
                    # Analisar a coluna de data para identificar períodos disponíveis
                    for ano in anos:
                        for mes_codigo in meses.keys():
                            # Verificar o formato da data
                            formato = FORMATO_DATA.lower() if FORMATO_DATA else 'yyyy/mm'
                            
                            if formato == 'yyyy/mm':
                                padrao = f"{ano}[/-]{mes_codigo}"
                            elif formato == 'yyyy-mm':
                                padrao = f"{ano}-{mes_codigo}"
                            else:  # mm/yyyy ou padrão
                                padrao = f"{mes_codigo}[/-]{ano}"
                            
                            # Verificar se há dados para este período
                            mascara = df_completo[COLUNAS["data"]].astype(str).str.contains(padrao, regex=True, na=False)
                            contagem = mascara.sum()
                            
                            if contagem > 0:
                                periodos_disponiveis[(ano, mes_codigo)] = contagem
                                logger.info(f"Encontrados {contagem} registros para {meses[mes_codigo]} de {ano}")
            except Exception as e:
                logger.error(f"Erro ao verificar períodos disponíveis: {e}")
        
        print("\n" + "="*60)
        print("MENU DE SELEÇÃO DE MÊS".center(60))
        print("="*60)
        
        if periodos_disponiveis:
            print("\nPeríodos com dados disponíveis:")
            print("-"*60)
            print("Ano | Mês             | Quantidade de registros")
            print("-"*60)
            
            # Ordenar períodos por data (mais recente primeiro)
            periodos_ordenados = sorted(periodos_disponiveis.items(), 
                                       key=lambda x: (x[0][0], x[0][1]), 
                                       reverse=True)
            
            for (ano, mes_codigo), contagem in periodos_ordenados:
                print(f"{ano} | {meses[mes_codigo]:<15} | {contagem}")
            
            print("-"*60)
        
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
        
        # Verificar se o período selecionado tem dados
        periodo_selecionado = (ano_selecionado, mes_selecionado)
        if periodos_disponiveis and periodo_selecionado not in periodos_disponiveis:
            print(f"\n⚠️ AVISO: Não foram encontrados dados para {nome_mes} de {ano_selecionado}!")
            
            if len(periodos_disponiveis) > 0:
                print("Períodos disponíveis:", end=" ")
                for (ano, mes), _ in sorted(periodos_disponiveis.items()):
                    print(f"{meses[mes]} de {ano}", end=", ")
                print("\n")
                
                # Perguntar se deseja continuar mesmo assim
                continuar = input("Deseja continuar mesmo assim? (S/N): ").strip().upper()
                if continuar != 'S':
                    # Oferecer para selecionar um período disponível
                    usar_disponivel = input("Deseja selecionar um período disponível? (S/N): ").strip().upper()
                    if usar_disponivel == 'S':
                        # Pegar o período mais recente disponível
                        periodo_mais_recente = sorted(periodos_disponiveis.keys(), 
                                                    key=lambda x: (x[0], x[1]), 
                                                    reverse=True)[0]
                        
                        ano_selecionado, mes_selecionado = periodo_mais_recente
                        nome_mes = meses[mes_selecionado]
                        print(f"\nUsando período disponível: {nome_mes} de {ano_selecionado}")
                    else:
                        # Continuar com a seleção atual mesmo sem dados
                        print("\nContinuando com a seleção atual mesmo sem dados.")
        
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

def main(limite_linhas: int = None, modo_teste: bool = False, categorias_selecionadas: Dict = None, quantidade_especifica: int = None):
    """
    Função principal que orquestra o fluxo de trabalho.
    
    Args:
        limite_linhas: Opcional. Limita o processamento a este número de linhas.
                      Se for None, processa todas as linhas.
        modo_teste: Se True, executa apenas para a primeira linha e não atualiza a planilha.
        categorias_selecionadas: Dicionário com as categorias selecionadas pelo usuário.
        quantidade_especifica: Quantidade específica de itens a processar.
    """
    # Configura logging
    logger = configurar_logging()
    logger.info(f"Iniciando script SEO-LinkBuilder - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Inicializa o sheets handler antes do menu para verificar períodos disponíveis
    try:
        sheets = SheetsHandler()
        logger.info("SheetsHandler inicializado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar SheetsHandler: {e}")
        logger.exception("Detalhes do erro:")
        sheets = None
    
    # Selecionar o mês e ano a processar
    ano_selecionado, mes_selecionado = apresentar_menu_meses(sheets)
    
    # Configura as variáveis de ambiente para o mês selecionado
    os.environ['ANO_ATUAL'] = ano_selecionado
    os.environ['MES_ATUAL'] = mes_selecionado
    
    # Inicializa os handlers restantes
    try:
        if sheets is None:  # Se falhou na inicialização anterior
            sheets = SheetsHandler()
        
        gemini = GeminiHandler()
        docs = DocsHandler()
        
        logger.info("Handlers inicializados com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar handlers: {e}")
        logger.exception("Detalhes do erro:")
        return
    
    # Lê a planilha com filtro de data aplicado
    try:
        # Primeiro tentamos ler aplicando o filtro de data para verificar se existem dados
        df = sheets.ler_planilha()
        
        if df.empty:
            logger.warning(f"Nenhum dado encontrado para o período {mes_selecionado}/{ano_selecionado}!")
            print(f"\n⚠️ AVISO: Não foram encontrados dados para o período {MESES[mes_selecionado]} de {ano_selecionado}")
            
            # Vamos verificar quais períodos têm dados disponíveis
            df_completo = sheets.ler_planilha(None, apenas_dados=True)
            periodos_disponiveis = {}
            
            if not df_completo.empty and COLUNAS["data"] < len(df_completo.columns):
                # Verificar todos os meses nos dois anos
                anos = [str(datetime.now().year), str(datetime.now().year + 1)]
                
                for ano in anos:
                    for mes_codigo in MESES.keys():
                        # Verificar pelo formato exato
                        mascara1 = df_completo[COLUNAS["data"]].astype(str).str.contains(f"{ano}/{mes_codigo}", regex=False)
                        mascara2 = df_completo[COLUNAS["data"]].astype(str).str.contains(f"{mes_codigo}/{ano}", regex=False)
                        
                        contagem = mascara1.sum() + mascara2.sum()
                        if contagem > 0:
                            periodos_disponiveis[(ano, mes_codigo)] = contagem
            
            if periodos_disponiveis:
                print("\nPeríodos com dados disponíveis:")
                print("-" * 50)
                for (ano, mes), count in sorted(periodos_disponiveis.items()):
                    print(f"{MESES[mes]} de {ano}: {count} registros")
                print("-" * 50)
                
                # Perguntar se quer selecionar outro período
                continuar = input("\nDeseja selecionar outro período? (S/N): ").strip().upper()
                if continuar == 'S':
                    # Reiniciar o script
                    print("\nReiniciando o script...\n")
                    return main(limite_linhas, modo_teste, categorias_selecionadas, quantidade_especifica)
            
            print("Encerrando o script.")
            return
            
        total_linhas = len(df)
        logger.info(f"Planilha filtrada para {mes_selecionado}/{ano_selecionado} lida com sucesso. Total de {total_linhas} linhas")
            
    except Exception as e:
        logger.error(f"Erro ao ler planilha: {e}")
        logger.exception("Detalhes do erro:")
        return
    
    # Agora que temos certeza de que existem dados para o período, lemos novamente para processar
    # Lê a planilha completa para estimar custos por categoria (sem filtro de data)
    try:
        df_completo = sheets.ler_planilha(None, apenas_dados=True)
        total_linhas_completo = len(df_completo)
        logger.info(f"Planilha completa lida com sucesso. Total de {total_linhas_completo} linhas")
            
    except Exception as e:
        logger.error(f"Erro ao ler planilha completa: {e}")
        logger.exception("Detalhes do erro:")
        return
    
    # Estimar custos por categoria
    categorias = estimar_custo_por_categoria(sheets, df)  # Usar o dataframe filtrado, não o completo
    
    # Se não foram fornecidas categorias, apresentar menu para seleção
    if categorias_selecionadas is None:
        categorias_selecionadas = apresentar_menu_categorias(categorias)
        
        # Se o usuário cancelou a operação
        if categorias_selecionadas is None:
            logger.info("Operação cancelada pelo usuário. Encerrando.")
            return
    
    # Filtrar DataFrame com base nas categorias selecionadas
    if 'quantidade_especifica' in categorias_selecionadas:
        quantidade_especifica = categorias_selecionadas['quantidade_especifica']
        # Selecionar aleatoriamente a quantidade solicitada
        if quantidade_especifica >= len(df):
            logger.info(f"A quantidade solicitada ({quantidade_especifica}) é maior ou igual ao total disponível ({len(df)}). Usando todo o DataFrame.")
            df_filtrado = df
        else:
            logger.info(f"Selecionando {quantidade_especifica} itens aleatoriamente.")
            df_filtrado = df.sample(n=quantidade_especifica, random_state=42)
    else:
        df_filtrado = filtrar_dataframe_por_categorias(df, sheets, categorias_selecionadas)
    
    # Aplicar limite de linhas se fornecido
    if limite_linhas is not None:
        df_filtrado = df_filtrado.head(limite_linhas)
    
    # Verificar se ainda há linhas após a filtragem
    total_linhas = len(df_filtrado)
    if total_linhas == 0:
        logger.warning("Nenhuma linha restante após filtragem. Encerrando.")
        return
    
    logger.info(f"Serão processadas {total_linhas} linhas")
    
    # Estimar custo total
    tokens_entrada_medio = 1700  # Valor médio aproximado
    tokens_saida_medio = 500  # Valor médio aproximado para 500 palavras
    custo_estimado_por_item = estimar_custo_gemini(tokens_entrada_medio, tokens_saida_medio)
    custo_estimado_total = custo_estimado_por_item * total_linhas
    
    logger.info(f"Custo estimado total: ${custo_estimado_total:.4f} USD (aproximadamente R${custo_estimado_total*5:.2f})")
    
    # Confirmar execução
    confirmacao = input(f"\nProcessar {total_linhas} itens com custo estimado de R${custo_estimado_total*5:.2f}? (S/N): ").strip().upper()
    if confirmacao != 'S':
        logger.info("Operação cancelada pelo usuário. Encerrando.")
        return
    
    # Modo teste usa apenas a primeira linha
    if modo_teste:
        df_filtrado = df_filtrado.iloc[:1]
        logger.info("EXECUTANDO EM MODO DE TESTE - Apenas a primeira linha será processada")
    
    # Métricas de custo
    custo_total = 0.0
    tokens_entrada_total = 0
    tokens_saida_total = 0
    
    # Processa cada linha
    for i, (idx, linha) in enumerate(df_filtrado.iterrows()):
        try:
            # Acesso direto às colunas ao invés de extrair_dados_linha
            id_campanha = str(linha[COLUNAS['id']]) if COLUNAS['id'] < len(linha) else 'Sem-ID'
            site = str(linha[COLUNAS['site']]) if COLUNAS['site'] < len(linha) else 'Sem site'
            palavra_ancora = str(linha[COLUNAS['palavra_ancora']]) if COLUNAS['palavra_ancora'] < len(linha) else 'Sem palavra-âncora'
            url_ancora = str(linha[COLUNAS['url_ancora']]) if COLUNAS['url_ancora'] < len(linha) else 'Sem URL'
            titulo = str(linha[COLUNAS['titulo']]) if COLUNAS['titulo'] < len(linha) and linha[COLUNAS['titulo']] else 'Sem título'
            
            # Cria um dicionário de dados para passar para o Gemini
            dados = {
                'id': id_campanha,
                'site': site,
                'palavra_ancora': palavra_ancora,
                'url_ancora': url_ancora,
                'titulo': titulo,
                'tema': 'Sem tema',  # Tema não existe na estrutura atual
            }
            
            # Pula linhas que parecem ser cabeçalho
            if palavra_ancora.lower() in ('palavra_ancora', 'palavra ancora', ''):
                logger.info(f"Pulando linha {i+1}/{len(df_filtrado)} que parece ser cabeçalho ou está vazia")
                continue
            
            logger.info(f"Processando linha {i+1}/{len(df_filtrado)}: ID {id_campanha} - {titulo}")
            
            # Gera o conteúdo usando o Gemini
            logger.info(f"Gerando conteúdo com o Gemini para '{palavra_ancora}'...")
            conteudo, metricas, info_link = gemini.gerar_conteudo(dados)
            
            # Atualiza métricas
            custo_total += metricas['custo_estimado']
            tokens_entrada_total += metricas['tokens_entrada']
            tokens_saida_total += metricas['tokens_saida']
            
            # Extrai o título real do conteúdo gerado (primeira linha)
            linhas = conteudo.split('\n')
            titulo_gerado = linhas[0].strip() if linhas else "Artigo sem título"
            logger.info(f"Título gerado: {titulo_gerado}")
            
            # Gera o nome do arquivo usando o ID em vez da data
            try:
                nome_arquivo = gerar_nome_arquivo(id_campanha, site, palavra_ancora)
            except Exception as e:
                logger.error(f"Erro ao gerar nome de arquivo: {e}")
                # Fallback para um nome simples
                nome_arquivo = f"{id_campanha} - {site} - Artigo"
            
            # Cria o documento no Google Docs
            logger.info(f"Criando documento '{nome_arquivo}'...")
            document_id, document_url = docs.criar_documento(titulo_gerado, conteudo, nome_arquivo, info_link)
            
            # Atualiza a URL e o título na planilha (se não estiver em modo de teste)
            if not modo_teste:
                sheets.atualizar_url_documento(i, document_url)
                sheets.atualizar_titulo_documento(i, titulo_gerado)
                logger.info(f"URL e título atualizados na planilha: {document_url}")
            else:
                logger.info(f"[MODO TESTE] URL gerada (não atualizada na planilha): {document_url}")
                logger.info(f"[MODO TESTE] Título gerado (não atualizado na planilha): {titulo_gerado}")
            
            # Pausa para não sobrecarregar as APIs
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Erro ao processar linha {i+1}: {e}")
            continue
    
    # Exibe resumo
    logger.info(f"\n{'='*50}")
    logger.info(f"RESUMO DE EXECUÇÃO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total de artigos processados: {len(df_filtrado)}")
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

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SEO-LinkBuilder - Gerador de conteúdo para SEO')
    parser.add_argument('--limite', type=int, default=10,
                        help='Número máximo de linhas a processar (padrão: 10)')
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