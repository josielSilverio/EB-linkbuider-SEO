# Ponto de entrada principal do script
import os
import time
import logging
import pandas as pd
# import numpy as np # numpy não parece estar sendo usado diretamente.
from typing import Dict, List, Tuple, Optional # Removido Set e Counter por enquanto
from datetime import datetime
from collections import Counter # MOVING Counter import here
from sklearn.feature_extraction.text import TfidfVectorizer # Ensuring TfidfVectorizer is imported
from sklearn.metrics.pairwise import cosine_similarity # Ensuring cosine_similarity is imported
import re
# import dotenv # dotenv é carregado em config.py
import json

from src.utils import (
    configurar_logging, 
    limpar_nome_arquivo, 
    identificar_palavras_frequentes_em_titulos,
    contar_tokens,
    extrair_titulos_por_ancora, # Esta função precisará ser adaptada ou o DataFrame passado de forma diferente
    identificar_padroes_por_ancora # Similarmente, esta função
)
from src.sheets_handler import SheetsHandler
from src.gemini_handler import GeminiHandler, verificar_conteudo_proibido, verificar_e_corrigir_titulo
from src.docs_handler import DocsHandler
from src.config import (
    gerar_nome_arquivo, 
    # COLUNAS, # REMOVIDO
    estimar_custo_gemini, 
    GEMINI_MAX_OUTPUT_TOKENS, 
    MESES,
    SPREADSHEET_ID, # Usado para atualizar globalmente
    SHEET_NAME,     # Usado para atualizar globalmente
    DRIVE_FOLDER_ID,# Usado para atualizar globalmente
    USD_TO_BRL_RATE,
    DELAY_ENTRE_CHAMADAS_GEMINI,
    COLUNAS_MAPEAMENTO_NOMES # Adicionado para referência, embora o mapa venha do sheets_handler
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

def verificar_titulos_duplicados(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, dynamic_column_map: Dict, modo_teste: bool = False):
    """
    Verifica se existem títulos duplicados na planilha e gera novos conteúdos para substituí-los.
    
    Args:
        sheets: Instância de SheetsHandler
        gemini: Instância de GeminiHandler
        docs: Instância de DocsHandler
        dynamic_column_map: Mapeamento dinâmico das colunas.
        modo_teste: Se True, apenas identifica duplicatas sem corrigi-las
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Verificando títulos duplicados na planilha...")
    
    try:
        # Lê a planilha completa sem filtrar por data
        # A função ler_planilha já usa o dynamic_column_map internamente para retornar o DataFrame com nomes de coluna corretos
        df, _ = sheets.ler_planilha(apenas_dados=True) # ler_planilha retorna df, header_row_index
        
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar títulos duplicados")
            return
        
        col_titulo_nome = dynamic_column_map.get('titulo', {}).get('header')
        col_url_nome = dynamic_column_map.get('url_documento', {}).get('header')

        if not col_titulo_nome or col_titulo_nome not in df.columns:
            logger.error(f"Coluna de título ('{col_titulo_nome or 'titulo'}') não encontrada no DataFrame. Verifique o mapeamento.")
            return
        if not col_url_nome: # Necessário para atualizar URL
            logger.error(f"Coluna de URL ('url_documento') não encontrada no mapeamento. Verifique o mapeamento.")
            return


        titulos = df[col_titulo_nome].tolist()
        
        # Identifica os títulos duplicados (ignorando vazios e "Sem titulo")
        # Importar Counter se for usado
        from collections import Counter
        titulos_validos = [str(t) for t in titulos if t and str(t).strip() and str(t).strip().lower() != "sem titulo"]
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
            # df.index contém os índices originais do DataFrame antes de qualquer filtragem em ler_planilha
            # Precisamos do sheet_row_num para atualizar a planilha
            linhas_duplicadas = df[df[col_titulo_nome] == titulo_duplicado]
            
            if len(linhas_duplicadas) <= 1:
                continue
            
            logger.info(f"Encontrado título duplicado: '{titulo_duplicado}' em {len(linhas_duplicadas)} documentos. Mantendo o primeiro, gerando novos para os demais.")
            
            # Mantém o primeiro, gera novos para os demais
            # Itera sobre as linhas duplicadas, exceto a primeira
            for _, linha_series in linhas_duplicadas.iloc[1:].iterrows():
                sheet_row_num_original = linha_series['sheet_row_num'] # Obter o número original da linha
                
                try:
                    # extrair_dados_linha usa o dynamic_column_map que é passado para SheetsHandler
                    dados = sheets.extrair_dados_linha(linha_series, dynamic_column_map) 
                    
                    id_original = dados.get('id', 'Sem-ID')
                    logger.info(f"Gerando novo conteúdo para substituir título duplicado: '{titulo_duplicado}' (ID {id_original}, Linha Planilha: {sheet_row_num_original})")
                    
                    temperatura_original = gemini.temperatura_atual
                    gemini.temperatura_atual = min(0.9, temperatura_original + 0.3)
                    
                    try:
                        conteudo, metricas, info_link = gemini.gerar_conteudo(
                            dados, 
                            instrucao_adicional="\n\nIMPORTANTE: Crie um título COMPLETAMENTE ÚNICO e ORIGINAL, muito diferente dos títulos típicos para esse tema."
                        )
                        gemini.temperatura_atual = temperatura_original
                        
                        novo_titulo_extraido = extrair_titulo(conteudo, dados.get('palavra_ancora', ''))
                        if not novo_titulo_extraido or novo_titulo_extraido.lower() == "sem titulo":
                            novo_titulo_extraido = f"Artigo Revisado para {dados.get('palavra_ancora', 'Tópico')}"
                        logger.info(f"Novo título gerado e extraído: {novo_titulo_extraido}")
                        
                        nome_arquivo = gerar_nome_arquivo(id_original, 
                                                          dados.get('site', 'Sem-site'), 
                                                          dados.get('palavra_ancora', 'Sem-ancora'),
                                                          sufixo="_revisado_duplicado")
                        
                        document_id, document_url = docs.criar_documento(novo_titulo_extraido, conteudo, nome_arquivo, info_link)
                        
                        # Corrigindo: As funções de atualização em SheetsHandler usam chaves internas, não nomes de coluna como parâmetro.
                        # O spreadsheet_id e sheet_name são opcionais e serão pegos do config se não passados.
                        sheets.atualizar_url_documento(sheet_row_num_original, document_url)
                        sheets.atualizar_titulo_documento(sheet_row_num_original, novo_titulo_extraido)
                        logger.info(f"URL e título atualizados na planilha para linha {sheet_row_num_original}: {document_url}")
                        
                    except Exception as e:
                        logger.error(f"Erro ao gerar novo conteúdo para ID {id_original} (Linha Planilha: {sheet_row_num_original}): {e}")
                        gemini.temperatura_atual = temperatura_original # Garante restauração
                        continue
                except Exception as e:
                    logger.error(f"Erro ao processar linha da planilha {sheet_row_num_original} para título duplicado: {e}")
                    continue
            
            logger.info("Verificação e correção de títulos duplicados concluída com sucesso!")
            
    except Exception as e:
        logger.error(f"Erro ao verificar títulos duplicados: {e}")
        logger.exception("Detalhes do erro:")

def verificar_similaridade_conteudos(sheets: SheetsHandler, gemini: GeminiHandler, docs: DocsHandler, 
                                    dynamic_column_map: Dict,
                                    limiar_similaridade: float = 0.4, modo_teste: bool = False):
    """
    Verifica a similaridade entre conteúdos gerados e reescreve aqueles que são muito similares.
    
    Args:
        sheets: Instância de SheetsHandler
        gemini: Instância de GeminiHandler
        docs: Instância de DocsHandler
        dynamic_column_map: Mapeamento dinâmico das colunas.
        limiar_similaridade: Percentual acima do qual os conteúdos são considerados muito similares (0.0 a 1.0)
        modo_teste: Se True, apenas identifica conteúdos similares sem corrigi-los
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info(f"Verificando similaridade entre conteúdos (limiar: {limiar_similaridade*100:.0f}%)...")
    
    try:
        df, _ = sheets.ler_planilha(apenas_dados=True) # ler_planilha retorna df, header_row_index
        
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar similaridade")
            return

        col_url_nome = dynamic_column_map.get('url_documento', {}).get('header')
        col_titulo_nome = dynamic_column_map.get('titulo', {}).get('header')
        col_id_nome = dynamic_column_map.get('id', {}).get('header') # Para logs e nome de arquivo
        col_site_nome = dynamic_column_map.get('site', {}).get('header') # Para nome de arquivo
        col_palavra_ancora_nome = dynamic_column_map.get('palavra_ancora', {}).get('header') # Para nome de arquivo e extrair_dados_linha

        if not col_url_nome or col_url_nome not in df.columns:
            logger.error(f"Coluna de URL ('{col_url_nome or 'url_documento'}') não encontrada no DataFrame.")
            return
        if not col_titulo_nome or col_titulo_nome not in df.columns:
            logger.error(f"Coluna de título ('{col_titulo_nome or 'titulo'}') não encontrada no DataFrame.")
            return
        if 'sheet_row_num' not in df.columns:
            logger.error("Coluna 'sheet_row_num' não encontrada no DataFrame. Necessária para atualizações.")
            return


        documentos_processados = []
        for _, row_series in df.iterrows(): # Iterar com row_series
            url = row_series.get(col_url_nome)
            titulo = row_series.get(col_titulo_nome)
            sheet_row_num = row_series.get('sheet_row_num')

            if url and str(url).strip() and titulo and str(titulo).strip().lower() != "sem titulo":
                try:
                    doc_id_gdocs = None
                    if isinstance(url, str) and '/document/d/' in url:
                        doc_id_gdocs = url.split('/document/d/')[1].split('/')[0]
                    
                    if doc_id_gdocs:
                        conteudo = docs.obter_conteudo_documento(doc_id_gdocs)
                        documentos_processados.append({
                            'sheet_row_num': sheet_row_num, # Usar para atualizar planilha
                            'gdocs_id': doc_id_gdocs,
                            'titulo': titulo,
                            'conteudo': conteudo,
                            'url': url,
                            'linha_original_series': row_series # Passar a Series original para extrair_dados_linha
                        })
                except Exception as e:
                    logger.warning(f"Erro ao processar documento {url} (Linha Planilha: {sheet_row_num}): {e}")
        
        if len(documentos_processados) < 2:
            logger.info("Menos de 2 documentos encontrados/processados para comparação. Encerrando verificação de similaridade.")
            return
            
        conteudos = [doc['conteudo'] for doc in documentos_processados]
        
        # Calcula similaridade de conteúdos usando TF-IDF
        conteudo_vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 3)) # Aumentado para trigrams
        conteudo_tfidf = conteudo_vectorizer.fit_transform(conteudos)
        conteudo_similarity_matrix = cosine_similarity(conteudo_tfidf)
        
        logger.info(f"Matriz de similaridade de conteúdo calculada para {len(documentos_processados)} documentos.")
        
        indices_para_regenerar = set() # Usar um set para evitar duplicatas

        for i in range(len(documentos_processados)):
            for j in range(i + 1, len(documentos_processados)):
                similaridade = conteudo_similarity_matrix[i, j]
                doc_i = documentos_processados[i]
                doc_j = documentos_processados[j]

                if similaridade >= limiar_similaridade:
                    logger.warning(
                        f"Similaridade ALTA ({similaridade*100:.2f}%) detectada entre: "
                        f"Doc 1 (Título: '{doc_i['titulo']}', Linha: {doc_i['sheet_row_num']}) e "
                        f"Doc 2 (Título: '{doc_j['titulo']}', Linha: {doc_j['sheet_row_num']})"
                    )
                    # Decide qual documento regenerar. Ex: o segundo, ou o mais recente, ou com base em algum critério.
                    # Aqui, vamos marcar o segundo (j) para regeneração para simplificar.
                    # Poderia ser mais sofisticado (ex: regenerar o que tem menos links, ou foi gerado depois).
                    indices_para_regenerar.add(j) 

        if modo_teste:
            if indices_para_regenerar:
                logger.info(f"[MODO TESTE] {len(indices_para_regenerar)} documentos seriam regenerados devido à alta similaridade.")
                for idx_doc in indices_para_regenerar:
                    logger.info(f"    - [MODO TESTE] Seria regenerado: Título '{documentos_processados[idx_doc]['titulo']}', Linha Planilha {documentos_processados[idx_doc]['sheet_row_num']}")
            else:
                logger.info("[MODO TESTE] Nenhuma similaridade acima do limiar encontrada.")
            return

        if not indices_para_regenerar:
            logger.info("✓ Nenhuma similaridade de conteúdo acima do limiar detectada.")
            return

        logger.info(f"{len(indices_para_regenerar)} documentos serão regenerados devido à alta similaridade.")

        for idx_doc_a_regenerar in indices_para_regenerar:
            doc_info = documentos_processados[idx_doc_a_regenerar]
            linha_original_series = doc_info['linha_original_series']
            sheet_row_num_original = doc_info['sheet_row_num']
            
            try:
                # extrair_dados_linha usa o dynamic_column_map que é passado para SheetsHandler
                dados = sheets.extrair_dados_linha(linha_original_series, dynamic_column_map)
                
                id_original = dados.get('id', 'Sem-ID')
                palavra_ancora = dados.get('palavra_ancora', 'Tópico')
                site = dados.get('site', 'Sem-site')

                logger.info(f"Regenerando conteúdo para Doc ID {id_original} (Título original: '{doc_info['titulo']}', Linha Planilha: {sheet_row_num_original}) devido à similaridade.")
                
                temperatura_original = gemini.temperatura_atual
                gemini.temperatura_atual = min(0.95, temperatura_original + 0.35) # Aumenta ainda mais para diversificar
                
                try:
                    novo_conteudo, metricas, info_link = gemini.gerar_conteudo(
                        dados,
                        instrucao_adicional="\n\nIMPORTANTE: O conteúdo anterior foi considerado muito similar a outro. Gere um texto com abordagem, estrutura e palavras-chave secundárias BEM DIFERENTES. Foque em originalidade máxima."
                    )
                    gemini.temperatura_atual = temperatura_original
                    
                    novo_titulo_extraido = extrair_titulo(novo_conteudo, palavra_ancora)
                    if not novo_titulo_extraido or novo_titulo_extraido.lower() == "sem titulo":
                        novo_titulo_extraido = f"Artigo Original sobre {palavra_ancora}"
                    logger.info(f"Novo título gerado e extraído para Doc ID {id_original}: {novo_titulo_extraido}")
                    
                    nome_arquivo = gerar_nome_arquivo(id_original, site, palavra_ancora, sufixo="_revisado_similaridade")
                    
                    # Deleta o documento antigo do Google Docs antes de criar um novo para evitar confusão e lixo
                    # No entanto, a API de docs_handler não tem um método delete.
                    # Por enquanto, vamos apenas criar um novo. Se o ID for o mesmo, ele atualiza.
                    # Se o nome do arquivo for o mesmo e a pasta for a mesma, o criar_documento pode sobrescrever ou criar com (1)
                    # Idealmente, docs.criar_documento deveria lidar com isso ou ter uma opção para atualizar por ID gdocs.
                    # O `docs.criar_documento` atual pode receber um `existing_document_id`
                    # Mas aqui o objetivo é um *novo* documento com conteúdo novo.
                    # Para evitar problemas, vamos tentar criar com nome ligeiramente diferente e não passar existing_doc_id.

                    document_id_novo, document_url_novo = docs.criar_documento(
                        novo_titulo_extraido, 
                        novo_conteudo, 
                        nome_arquivo, 
                        info_link
                        # existing_document_id=doc_info['gdocs_id'] # Não passar para forçar novo doc se necessário, ou atualizar se o nome for o mesmo.
                                                                    # Melhor: criar com nome único (sufixo já ajuda) e atualizar planilha.
                    )
                    
                    sheets.atualizar_url_documento(sheet_row_num_original, document_url_novo)
                    sheets.atualizar_titulo_documento(sheet_row_num_original, novo_titulo_extraido)
                    logger.info(f"Doc ID {id_original} (Linha Planilha {sheet_row_num_original}): URL e Título atualizados após regeneração.")
                    
                except Exception as e:
                    logger.error(f"Erro ao regenerar conteúdo para Doc ID {id_original} (Linha Planilha {sheet_row_num_original}): {e}")
                    gemini.temperatura_atual = temperatura_original # Garante restauração
                    continue
            except Exception as e:
                logger.error(f"Erro ao processar Doc ID {doc_info.get('linha_original_series', {}).get(col_id_nome, 'Desconhecido')} (Linha Planilha: {sheet_row_num_original}) para regeneração: {e}")
                continue
        
        logger.info("Verificação e regeneração por similaridade de conteúdo concluída.")
            
    except ImportError:
        logger.error("As bibliotecas 'scikit-learn' são necessárias para a verificação de similaridade. Instale-as com 'pip install scikit-learn'.")
        logger.info("Verificação de similaridade de conteúdo ignorada.")
    except Exception as e:
        logger.error(f"Erro geral ao verificar similaridade de conteúdos: {e}")
        logger.exception("Detalhes do erro:")

def corrigir_termos_proibidos(sheets: SheetsHandler, docs: DocsHandler, dynamic_column_map: Dict, modo_teste: bool = False):
    """
    Verifica todos os documentos já gerados em busca de termos proibidos e os corrige.
    
    Args:
        sheets: Instância de SheetsHandler
        docs: Instância de DocsHandler
        dynamic_column_map: Mapeamento dinâmico das colunas.
        modo_teste: Se True, apenas identifica os termos proibidos sem corrigi-los
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Iniciando verificação e correção de termos proibidos nos documentos...")

    try:
        df, _ = sheets.ler_planilha(apenas_dados=True) # ler_planilha retorna df, header_row_index
        if df.empty:
            logger.warning("Nenhum dado encontrado na planilha para verificar termos proibidos.")
            return

        col_url_nome = dynamic_column_map.get('url_documento', {}).get('header')
        col_titulo_nome = dynamic_column_map.get('titulo', {}).get('header')
        col_id_nome = dynamic_column_map.get('id', {}).get('header')
        col_palavra_ancora_nome = dynamic_column_map.get('palavra_ancora', {}).get('header')
        # col_status_nome = dynamic_column_map.get('status', {}).get('header') # Se precisar atualizar status

        if not col_url_nome or col_url_nome not in df.columns:
            logger.error(f"Coluna de URL ('{col_url_nome or 'url_documento'}') não encontrada no DataFrame.")
            return
        if not col_titulo_nome or col_titulo_nome not in df.columns:
            logger.error(f"Coluna de Título ('{col_titulo_nome or 'titulo'}') não encontrada no DataFrame.")
            return
        if 'sheet_row_num' not in df.columns:
            logger.error("Coluna 'sheet_row_num' não encontrada no DataFrame. Necessária para atualizações.")
            return
        
        correcoes_realizadas = 0
        documentos_verificados = 0

        for _, row_series in df.iterrows():
            url_documento = row_series.get(col_url_nome)
            titulo_atual = row_series.get(col_titulo_nome)
            sheet_row_num = row_series.get('sheet_row_num')
            id_original = row_series.get(col_id_nome, 'Sem ID')
            palavra_ancora = row_series.get(col_palavra_ancora_nome, 'N/A')

            if not url_documento or not isinstance(url_documento, str) or '/document/d/' not in url_documento:
                # logger.debug(f"URL inválida ou ausente para linha {sheet_row_num}. Pulando verificação de termos.")
                continue
            
            documentos_verificados += 1
            logger.info(f"Verificando termos proibidos no documento: ID {id_original}, Título '{titulo_atual}', Linha Planilha {sheet_row_num}")

            try:
                gdocs_id = url_documento.split('/document/d/')[1].split('/')[0]
                conteudo_original = docs.obter_conteudo_documento(gdocs_id)

                if not conteudo_original:
                    logger.warning(f"Não foi possível obter conteúdo para o documento ID {gdocs_id} (Linha Planilha {sheet_row_num}).")
                    continue

                termos_encontrados, conteudo_corrigido = verificar_conteudo_proibido(conteudo_original)

                if termos_encontrados:
                    logger.warning(f"Termos proibidos encontrados no Doc ID {id_original} (Linha {sheet_row_num}): {', '.join(termos_encontrados)}")
                    if modo_teste:
                        logger.info(f"[MODO TESTE] Doc ID {id_original}: Correção seria aplicada.")
                        continue

                    logger.info(f"Corrigindo Doc ID {id_original} (Linha {sheet_row_num})...")
                    
                    # O título também pode precisar de correção se contiver termos proibidos,
                    # ou pode ser regenerado se o conteúdo mudar muito.
                    # Por ora, vamos focar em corrigir o conteúdo e o título existente.
                    _, titulo_corrigido_fmt = verificar_e_corrigir_titulo(titulo_atual, palavra_ancora, is_document_title=True)
                    if titulo_corrigido_fmt != titulo_atual:
                         logger.info(f"Título também corrigido/reformatado de '{titulo_atual}' para '{titulo_corrigido_fmt}'.")
                    else:
                        titulo_corrigido_fmt = titulo_atual # Mantém o original se não houver mudança de formatação/termo proibido no titulo

                    # Atualiza o documento no Google Docs com o conteúdo corrigido
                    # A função `atualizar_documento` do DocsHandler recebe id, novo_titulo, novo_corpo, novo_nome_arquivo
                    # Precisamos do nome do arquivo. Vamos usar o nome existente ou gerar um novo.
                    # Para simplificar, vamos manter o nome do arquivo, pois o ID do doc é o que importa.
                    # docs.atualizar_documento não existe na API fornecida.
                    # Usamos criar_documento com existing_document_id para atualizar.
                    
                    # Gerar nome do arquivo para o caso de docs.criar_documento precisar dele.
                    # A API do DocsHandler.criar_documento tem: titulo, corpo, nome_arquivo_sem_ext, info_link, existing_document_id=None
                    # O nome do arquivo é usado para o nome do arquivo no Drive, não o título interno do Doc.
                    # Vamos manter o nome do arquivo no Drive, se possível. 
                    # Se `docs.criar_documento` for chamado com `existing_document_id`, ele atualiza o conteúdo e o título interno.
                    # O nome do arquivo no Drive permanece o mesmo, a menos que explicitamente renomeado.

                    # Como não temos o nome original do arquivo no Drive aqui facilmente,
                    # e `criar_documento` vai definir o título do doc (que já temos como `titulo_corrigido_fmt`)
                    # e também pode definir o nome do arquivo no Drive.
                    # Para evitar mudar o nome do arquivo no Drive desnecessariamente, o ideal seria uma função `docs.update_content_and_title(doc_id, new_title, new_content)`
                    # Como não temos, vamos usar `criar_documento` e passar `existing_document_id`.
                    # O `nome_arquivo` em `criar_documento` é `nome_arquivo_sem_ext`. 
                    # Se o nome do arquivo do Drive precisar ser preservado, essa lógica tem que ser mais esperta.
                    # Por ora, vamos passar None para nome_arquivo_sem_ext para que ele não tente renomear o arquivo no Drive.
                    # Ou melhor, vamos gerar um nome de arquivo padrão, pois é um parâmetro obrigatório.
                    nome_arquivo_drive = limpar_nome_arquivo(f"{id_original}_{palavra_ancora}_corrigido")

                    _, new_doc_url = docs.criar_documento(
                        titulo=titulo_corrigido_fmt, 
                        corpo=conteudo_corrigido, 
                        nome_arquivo_sem_ext=nome_arquivo_drive, # docs_handler espera nome SEM extensão.
                        info_link=None, # Não temos info_link aqui, passamos None
                        existing_document_id=gdocs_id
                    )

                    if new_doc_url != url_documento:
                        logger.info(f"URL do documento foi alterada para {new_doc_url} após correção. Atualizando planilha.")
                        # sheets.atualizar_url_documento precisa do nome da coluna
                        sheets.atualizar_url_documento(sheet_row_num, new_doc_url)
                    
                    # Atualiza o título na planilha se foi modificado
                    if titulo_corrigido_fmt != titulo_atual:
                        # sheets.atualizar_titulo_documento precisa do nome da coluna
                        sheets.atualizar_titulo_documento(sheet_row_num, titulo_corrigido_fmt)
                        logger.info(f"Título atualizado na planilha para linha {sheet_row_num} para: '{titulo_corrigido_fmt}'")
                    
                    correcoes_realizadas += 1
                    logger.info(f"Documento ID {id_original} (Linha {sheet_row_num}) corrigido e atualizado.")

                else:
                    logger.info(f"✓ Nenhum termo proibido encontrado em Doc ID {id_original} (Linha {sheet_row_num}).")

            except Exception as e:
                logger.error(f"Erro ao verificar/corrigir termos proibidos para Doc ID {id_original} (Linha {sheet_row_num}): {e}")
                logger.exception("Detalhes do erro:")
                continue
        
        logger.info(f"Verificação de termos proibidos concluída. Documentos verificados: {documentos_verificados}. Correções realizadas: {correcoes_realizadas}.")

    except Exception as e:
        logger.error(f"Erro geral na função corrigir_termos_proibidos: {e}")
        logger.exception("Detalhes do erro:")

def estimar_custo_por_categoria(sheets: SheetsHandler, dynamic_column_map: Dict, df: pd.DataFrame = None) -> Dict[str, Dict]:
    """
    Estima o custo médio por categoria de jogo com base na palavra-âncora.
    
    Args:
        sheets: Instância de SheetsHandler
        dynamic_column_map: Mapeamento dinâmico das colunas.
        df: DataFrame opcional com os dados da planilha
        
    Returns:
        Um dicionário onde as chaves são categorias e os valores são dicionários com 'custo_medio' e 'contagem'.
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info("Estimando custo por categoria...")
    
    if df is None:
        # Se o DataFrame não for fornecido, lê a planilha
        # ler_planilha já retorna o DataFrame com os nomes corretos das colunas
        df, _ = sheets.ler_planilha(apenas_dados=True)
        if df.empty:
            logger.warning("Planilha vazia. Não é possível estimar custos por categoria.")
            return {}

    col_palavra_ancora_nome = dynamic_column_map.get('palavra_ancora', {}).get('header')
    col_custo_total_reais_nome = dynamic_column_map.get('custo_total_reais', {}).get('header')

    if not col_palavra_ancora_nome or col_palavra_ancora_nome not in df.columns:
        logger.error(f"Coluna de Palavra Âncora ('{col_palavra_ancora_nome or 'palavra_ancora'}') não encontrada no DataFrame.")
        return {}
    if not col_custo_total_reais_nome or col_custo_total_reais_nome not in df.columns:
        logger.error(f"Coluna de Custo Total ('{col_custo_total_reais_nome or 'custo_total_reais'}') não encontrada no DataFrame.")
        return {}

    categorias_custo = {}
    # Tenta converter a coluna de custo para numérico, erros são coagidos para NaN
    df[col_custo_total_reais_nome] = pd.to_numeric(df[col_custo_total_reais_nome], errors='coerce')
    
    # Filtra NaNs que podem ter surgido da conversão ou já existiam
    df_custos_validos = df.dropna(subset=[col_custo_total_reais_nome])

    # Extrai categorias de forma simplificada (primeira palavra da âncora)
    # TODO: Melhorar a extração de categoria se necessário, usando regex ou mapeamento mais sofisticado.
    try:
        df_custos_validos['categoria_estimada'] = df_custos_validos[col_palavra_ancora_nome].apply(
            lambda x: str(x).split()[0].lower() if pd.notna(x) and str(x).strip() else "desconhecida"
        )
    except Exception as e:
        logger.error(f"Erro ao extrair categoria estimada da palavra-âncora: {e}. Verifique a coluna '{col_palavra_ancora_nome}'.")
        # Tenta prosseguir sem a coluna de categoria, ou retorna vazio
        # Por enquanto, vamos retornar vazio para evitar mais erros.
        return {}

    grouped = df_custos_validos.groupby('categoria_estimada')
    
    for categoria, group_df in grouped:
        if categoria == "desconhecida" and len(group_df) > 0:
            logger.warning(f"Encontrados {len(group_df)} itens com categoria 'desconhecida' ao estimar custos.")
        
        custo_medio = group_df[col_custo_total_reais_nome].mean()
        contagem = len(group_df)
        categorias_custo[categoria] = {
            "custo_medio": round(custo_medio, 2) if pd.notna(custo_medio) else 0,
            "contagem": contagem
        }
        logger.debug(f"Categoria: {categoria}, Custo Médio: R${custo_medio:.2f}, Contagem: {contagem}")

    if not categorias_custo:
        logger.info("Nenhuma categoria com custos válidos encontrada para estimativa.")
    else:
        logger.info("Estimativa de custo por categoria concluída.")
        
    return categorias_custo

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

def filtrar_dataframe_por_categorias(df: pd.DataFrame, sheets: SheetsHandler, dynamic_column_map: Dict, selecao: Dict) -> pd.DataFrame:
    """
    Filtra o DataFrame para incluir apenas linhas cujas palavras-chave correspondem às categorias selecionadas.

    Args:
        df: DataFrame original.
        sheets: Instância de SheetsHandler (usado para obter o mapeamento de colunas, se necessário no futuro, mas preferível passar dynamic_column_map).
        dynamic_column_map: Mapeamento dinâmico das colunas.
        selecao: Dicionário com as categorias selecionadas pelo usuário (chaves são nomes de categorias).

    Returns:
        DataFrame filtrado.
    """
    logger = logging.getLogger('seo_linkbuilder')
    logger.info(f"Filtrando DataFrame pelas categorias selecionadas: {list(selecao.keys())}")

    if not selecao or df.empty:
        logger.info("Nenhuma categoria selecionada ou DataFrame vazio. Retornando DataFrame original ou vazio.")
        return df 

    col_palavra_ancora_nome = dynamic_column_map.get('palavra_ancora', {}).get('header')

    if not col_palavra_ancora_nome or col_palavra_ancora_nome not in df.columns:
        logger.error(f"Coluna de Palavra Âncora ('{col_palavra_ancora_nome or 'palavra_ancora'}') não encontrada no DataFrame. Não é possível filtrar por categoria.")
        return pd.DataFrame() # Retorna DataFrame vazio para evitar erros posteriores

    # Cria uma lista de todas as palavras-chave (categorias) selecionadas
    selected_keywords = [cat.lower() for cat in selecao.keys()]
    logger.debug(f"Palavras-chave para filtro (categorias selecionadas): {selected_keywords}")

    # Função para verificar se alguma das palavras-chave selecionadas está na palavra_ancora da linha
    def categoria_matches(palavra_ancora_texto):
        if pd.isna(palavra_ancora_texto):
            return False
        palavra_ancora_lower = str(palavra_ancora_texto).lower()
        for keyword in selected_keywords:
            # Verifica se a keyword (categoria) está contida na palavra-âncora
            # Isso permite que 'cassino online' seja encontrado por 'cassino'
            if keyword in palavra_ancora_lower:
                return True
        return False

    try:
        mask = df[col_palavra_ancora_nome].apply(categoria_matches)
        df_filtrado = df[mask]
    except Exception as e:
        logger.error(f"Erro ao aplicar filtro de categorias na coluna '{col_palavra_ancora_nome}': {e}")
        return pd.DataFrame() # Retorna DataFrame vazio

    if df_filtrado.empty:
        logger.warning("Nenhuma linha correspondeu às categorias selecionadas após o filtro.")
    else:
        logger.info(f"{len(df_filtrado)} linhas retidas após filtro por categoria.")
        
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

def apresentar_menu_planilha(sheets_handler: SheetsHandler) -> Optional[Tuple[str, str]]:
    """
    Solicita ao usuário o ID da Planilha e, em seguida, seleciona a aba a ser processada.
    Usa a última seleção salva como padrão para ID e aba.
    """
    global SPREADSHEET_ID, SHEET_NAME # Movido para o início da função
    logger = logging.getLogger('seo_linkbuilder')
    
    ultima_selecao = carregar_ultima_selecao()
    default_spreadsheet_id = ultima_selecao.get("spreadsheet_id", SPREADSHEET_ID) 
    default_sheet_name = ultima_selecao.get("sheet_name", SHEET_NAME) 
    
    print("\n" + "="*60)
    print("SELEÇÃO DA PLANILHA GOOGLE SHEETS".center(60))
    print("="*60)

    spreadsheet_id_selecionado = None
    if default_spreadsheet_id:
        print(f"Último ID de planilha utilizado: {default_spreadsheet_id}")
        usar_default_id = input("Deseja usar este ID de planilha? (S/N, Enter para Sim): ").strip().upper()
        if usar_default_id == 'S' or usar_default_id == '':
            spreadsheet_id_selecionado = default_spreadsheet_id
        elif usar_default_id == 'N':
            spreadsheet_id_selecionado = input("Digite o ID da Planilha Google Sheets: ").strip()
        else:
            print("Opção inválida, usando ID padrão.")
            spreadsheet_id_selecionado = default_spreadsheet_id # ou pode sair, ou pedir de novo
    else:
        spreadsheet_id_selecionado = input("Digite o ID da Planilha Google Sheets: ").strip()

    if not spreadsheet_id_selecionado:
        logger.warning("Nenhum ID de planilha fornecido. Abortando seleção.")
        return None

    try:
        abas = sheets_handler.obter_abas_disponiveis(spreadsheet_id_selecionado)
        if not abas:
            logger.error(f"Nenhuma aba encontrada para a planilha ID: {spreadsheet_id_selecionado} ou erro ao acessá-la.")
            return None
        
        print("\nSelecione a aba (sheet) para processar:")
        for i, aba in enumerate(abas):
            print(f"{i+1}. {aba['titulo']}")
        
        # Sugere a última aba usada, se disponível e válida
        aba_sugerida_idx = -1
        if default_sheet_name:
            for i, aba_info in enumerate(abas): # Renomeado para aba_info para evitar conflito com aba externa
                if aba_info['titulo'] == default_sheet_name:
                    aba_sugerida_idx = i
                    print(f"(Enter para usar a última aba selecionada: '{default_sheet_name}')")
                    break
        
        while True:
            try:
                escolha_aba_str = input(f"Digite o número da aba (1-{len(abas)}): ").strip()
                if not escolha_aba_str and aba_sugerida_idx != -1: # Enter pressionado e há sugestão
                    sheet_name_selecionado = abas[aba_sugerida_idx]['titulo']
                    print(f"Aba '{sheet_name_selecionado}' selecionada (padrão).")
                    break
                
                escolha_aba_num = int(escolha_aba_str) # Renomeado para escolha_aba_num
                if 1 <= escolha_aba_num <= len(abas):
                    sheet_name_selecionado = abas[escolha_aba_num-1]['titulo']
                    print(f"Aba '{sheet_name_selecionado}' selecionada.")
                    break
                else:
                    print(f"Opção inválida. Por favor, escolha um número entre 1 e {len(abas)}.")
            except ValueError:
                print("Entrada inválida. Por favor, digite um número.")
        
        # Salva a seleção atual
        salvar_ultima_selecao({"spreadsheet_id": spreadsheet_id_selecionado, "sheet_name": sheet_name_selecionado})
        
        # Atualiza as variáveis globais (ou passá-las explicitamente para onde forem necessárias)
        # global SPREADSHEET_ID, SHEET_NAME # Removido daqui
        SPREADSHEET_ID = spreadsheet_id_selecionado
        SHEET_NAME = sheet_name_selecionado
        
        return spreadsheet_id_selecionado, sheet_name_selecionado
        
    except Exception as e:
        logger.error(f"Erro ao apresentar menu de planilhas: {e}")
        return None

def processar_planilha(limite_linhas: Optional[int] = None, 
                         linha_inicial_desejada: Optional[int] = None,
                         id_linha_especifica: Optional[str] = None, # Novo parâmetro
                         reprocessar_concluidos: bool = False, 
                         modo_teste: bool = False, 
                         spreadsheet_id: Optional[str] = None, 
                         sheet_name: Optional[str] = None):
    """
    Processa as linhas da planilha, gerando conteúdo e criando documentos.
    """
    logger = logging.getLogger('seo_linkbuilder')
    
    # Inicialização dos Handlers
    try:
        sheets = SheetsHandler()
        gemini = GeminiHandler()
        docs = DocsHandler()
    except Exception as e:
        logger.error(f"Erro ao inicializar handlers: {e}. Encerrando.")
        return

    # Usa o ID e nome da aba fornecidos ou os globais (atualizados pelo menu)
    current_spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
    current_sheet_name = sheet_name or SHEET_NAME

    if not current_spreadsheet_id or not current_sheet_name:
        logger.error("ID da Planilha ou Nome da Aba não foram definidos. Use o menu para selecioná-los.")
        return

    # 1. Obter o mapeamento de colunas ANTES de qualquer leitura de dados
    header_info = sheets._find_header_and_map_columns(current_spreadsheet_id, current_sheet_name)
    if not header_info:
        logger.error(f"Não foi possível obter o mapeamento de colunas para {current_spreadsheet_id}/{current_sheet_name}. Encerrando processamento.")
        return
    _, _, dynamic_column_map = header_info # header_row_index, actual_header_content, dynamic_column_map
    
    # Obtém os nomes reais das colunas necessárias para extrair_titulos_por_ancora
    col_titulo_real = dynamic_column_map.get('titulo', {}).get('name')
    col_palavra_ancora_real = dynamic_column_map.get('palavra_ancora', {}).get('name')

    # 2. Análise de títulos existentes (opcional, mas útil para evitar repetições)
    logger.info("Analisando todos os títulos existentes na planilha...")
    try:
        # Passar filtrar_processados=False aqui para analisar TODOS os títulos existentes, mesmo os já processados
        df_todos_titulos = sheets.ler_planilha( # Ajuste para desempacotar tupla -> REMOVIDO DESEMPACOTAMENTO
            spreadsheet_id=current_spreadsheet_id, 
            sheet_name=current_sheet_name,
            filtrar_processados=False, # Ler todos para análise de títulos
            apenas_dados=True # Indicar que é apenas para leitura de dados brutos
        )

        titulos_existentes = []
        if df_todos_titulos is not None and not df_todos_titulos.empty and col_titulo_real and col_titulo_real in df_todos_titulos.columns:
            titulos_existentes = df_todos_titulos[col_titulo_real].dropna().astype(str).tolist()
        
        # Identificar palavras frequentes nos títulos existentes
        palavras_frequentes_a_evitar = identificar_palavras_frequentes_em_titulos(
            titulos_existentes, 
            limiar_percentual=0.5, # Ex: se "apostas" aparece em >50% dos títulos
            min_titulos_para_analise=10
        )
        if palavras_frequentes_a_evitar:
            logger.info(f"Novos títulos tentarão EVITAR (normalizadas): {palavras_frequentes_a_evitar}")
        
        # Identificar padrões por âncora
        padroes_por_ancora_a_evitar = {}
        if df_todos_titulos is not None and not df_todos_titulos.empty and col_palavra_ancora_real and col_palavra_ancora_real in df_todos_titulos.columns and col_titulo_real:
            logger.info("Analisando títulos por palavra-âncora para padrões repetitivos...")
            titulos_agrupados = extrair_titulos_por_ancora(df_todos_titulos, col_titulo_real, col_palavra_ancora_real)
            padroes_por_ancora_a_evitar = identificar_padroes_por_ancora(titulos_agrupados)
            if padroes_por_ancora_a_evitar:
                logger.info(f"Identificados padrões para {len(padroes_por_ancora_a_evitar)} palavras-âncora.")

    except Exception as e:
        logger.error(f"Erro durante a análise de títulos existentes: {e}")
        palavras_frequentes_a_evitar = []
        padroes_por_ancora_a_evitar = {}
    
    instrucao_base_evitar = ""
    if palavras_frequentes_a_evitar:
        instrucao_base_evitar += f" EVITE usar excessivamente as seguintes palavras e seus derivados no título: {', '.join(palavras_frequentes_a_evitar)}."
    
    # 3. Ler a planilha para processamento efetivo, aplicando filtros conforme necessário
    logger.info(f"Lendo dados da planilha '{current_sheet_name}' ({current_spreadsheet_id}) para processamento efetivo...")

    df_para_processar = None

    if id_linha_especifica:
        logger.info(f"Tentando localizar linha com ID específico: {id_linha_especifica} para processar {limite_linhas if limite_linhas is not None and limite_linhas > 0 else 'todas disponíveis a partir dela'} linha(s).")
        df_completo = sheets.ler_planilha(
            spreadsheet_id=current_spreadsheet_id, 
            sheet_name=current_sheet_name,
            filtrar_processados=False, # Ler tudo para encontrar o ID e fatiar
            apenas_dados=True
        )
        if df_completo is not None and not df_completo.empty:
            col_id_nome_interno = dynamic_column_map.get('id', {}).get('name')
            if col_id_nome_interno and col_id_nome_interno in df_completo.columns:
                df_completo[col_id_nome_interno] = df_completo[col_id_nome_interno].astype(str)
                
                indices_encontrados = df_completo.index[df_completo[col_id_nome_interno] == str(id_linha_especifica)].tolist()

                if indices_encontrados:
                    indice_inicio = indices_encontrados[0] 
                    df_para_processar = df_completo.loc[indice_inicio:].head(limite_linhas if limite_linhas is not None and limite_linhas > 0 else None).copy()
                    
                    logger.info(f"Linha com ID '{id_linha_especifica}' encontrada no índice {indice_inicio}. Serão consideradas {len(df_para_processar)} linha(s) para processamento a partir dela.")
                    
                    if df_para_processar.empty:
                        logger.warning(f"Apesar do ID '{id_linha_especifica}' ter sido encontrado, nenhuma linha ficou selecionada para processamento.")
                        return
                else:
                    logger.warning(f"Nenhuma linha encontrada com o ID '{id_linha_especifica}'. Verifique o ID e a planilha.")
                    return
            else:
                logger.error(f"Coluna de ID ('{col_id_nome_interno or 'id'}') não encontrada no mapeamento ou DataFrame ao buscar por ID. Não é possível prosseguir.")
                return
        else:
            logger.warning("Planilha vazia ou erro ao ler para buscar ID específico.")
            return
        
        if not reprocessar_concluidos and df_para_processar is not None and not df_para_processar.empty:
            col_url_documento_nome_interno = dynamic_column_map.get('url_documento', {}).get('name')
            if col_url_documento_nome_interno and col_url_documento_nome_interno in df_para_processar.columns:
                urls_existentes_mask = pd.notna(df_para_processar[col_url_documento_nome_interno]) & \
                                     (df_para_processar[col_url_documento_nome_interno].astype(str).str.strip() != '')
                linhas_com_url_antes_filtro = urls_existentes_mask.sum()

                if linhas_com_url_antes_filtro > 0:
                    logger.info(f"Das {len(df_para_processar)} linhas selecionadas a partir do ID '{id_linha_especifica}', {linhas_com_url_antes_filtro} já possuem URL e o reprocessamento está DESATIVADO.")
                    df_para_processar = df_para_processar[~urls_existentes_mask]
                    logger.info(f"Após filtro de reprocessamento, {len(df_para_processar)} linhas restam para processamento.")
                
                if df_para_processar.empty and linhas_com_url_antes_filtro > 0:
                    logger.warning(f"Todas as {linhas_com_url_antes_filtro} linhas selecionadas a partir do ID '{id_linha_especifica}' já estavam processadas e o reprocessamento está DESATIVADO. Nada a fazer.")
                    return
            else:
                logger.warning(f"Coluna URL ('{col_url_documento_nome_interno}') não encontrada no mapeamento ao tentar aplicar filtro de reprocessamento para ID específico.")

    else: # Lógica original para linha_inicial_desejada e limite_linhas
        _filtrar_processados_na_leitura_inicial = not reprocessar_concluidos
        if linha_inicial_desejada is not None:
            _filtrar_processados_na_leitura_inicial = False
        
        df_lido_da_planilha = sheets.ler_planilha(
            limite_linhas=limite_linhas, 
            linha_inicial=linha_inicial_desejada,
            spreadsheet_id=current_spreadsheet_id, 
            sheet_name=current_sheet_name,
            filtrar_processados=_filtrar_processados_na_leitura_inicial
        )
        
        if df_lido_da_planilha is None or df_lido_da_planilha.empty:
            logger.warning("Nenhuma linha disponível para processamento após leitura inicial da planilha (sem ID específico).")
            if linha_inicial_desejada is not None and not _filtrar_processados_na_leitura_inicial:
                limite_log = limite_linhas if limite_linhas is not None and limite_linhas > 0 else 'N/A (todas após linha inicial)'
                logger.info(f"Isso significa que não há linhas a partir da linha {linha_inicial_desejada} ou o limite {limite_log} resultou em zero linhas.")
            elif _filtrar_processados_na_leitura_inicial: 
                logger.info("Isso pode ter ocorrido porque todas as linhas elegíveis (dentro do limite, se houver) já estavam processadas e o reprocessamento de concluídos está DESATIVADO.")
            # Casos onde limite_linhas == 0 (ou None) significa "todos"
            elif reprocessar_concluidos and (limite_linhas == 0 or limite_linhas is None) and linha_inicial_desejada is None:
                 logger.info("Modo 'reprocessar concluídos' ATIVO, mas parece que a planilha está vazia ou não há linhas após o cabeçalho.")
            elif not reprocessar_concluidos and (limite_linhas == 0 or limite_linhas is None) and linha_inicial_desejada is None:
                 logger.info("Nenhuma linha pendente encontrada. Para reprocessar linhas já concluídas, reinicie e escolha a opção correspondente.")
            return

        df_para_processar = df_lido_da_planilha.copy()

        if linha_inicial_desejada is not None and not reprocessar_concluidos:
            col_url_documento_nome_interno = dynamic_column_map.get('url_documento', {}).get('name')
            if col_url_documento_nome_interno and col_url_documento_nome_interno in df_para_processar.columns:
                linhas_antes_filtro_manual = len(df_para_processar)
                df_para_processar = df_para_processar[
                    df_para_processar[col_url_documento_nome_interno].isna() |
                    (df_para_processar[col_url_documento_nome_interno] == '')
                ]
                linhas_filtradas_manualmente = linhas_antes_filtro_manual - len(df_para_processar)
                if linhas_filtradas_manualmente > 0:
                    logger.info(f"{linhas_filtradas_manualmente} linha(s) (das {linhas_antes_filtro_manual} lida(s) a partir da linha {linha_inicial_desejada}) foram removidas por já terem URL, pois o reprocessamento está desativado.")
            else:
                logger.warning(f"Não foi possível aplicar o filtro de reprocessamento manual: coluna URL '{col_url_documento_nome_interno}' não encontrada no mapeamento ou DataFrame.")

    # Garantir que df_para_processar não seja None antes de verificar se está vazio
    if df_para_processar is None or df_para_processar.empty:
        logger.warning("Nenhuma linha para processar após todas as filtragens (ID específico ou outros critérios). Verifique as opções.")
        return
            
    total_linhas_para_processar = len(df_para_processar)
    logger.info(f"Total de {total_linhas_para_processar} linhas a serem processadas.")
    if total_linhas_para_processar == 0:
        logger.warning("Nenhuma linha para processar após todas as filtragens. Verifique as opções de linha inicial, limite e reprocessamento.")
        return
        
    custo_total_estimado_usd = 0
    custo_total_estimado_brl = 0
    documentos_gerados_sucesso = 0
    ids_processados_com_sucesso = []
    ids_com_erro = []

    # Loop principal para processar cada linha do DataFrame
    # Adicionado log antes do loop
    logger.info(f"Preparando para iniciar o loop de processamento sobre {total_linhas_para_processar} linha(s) selecionada(s).")

    for i, (original_index, row) in enumerate(df_para_processar.iterrows()):
        # 'original_index' é o índice do DataFrame df_para_processar
        # 'row' é uma Series do Pandas contendo os dados da linha
        
        # Adicionado log no início da iteração
        # Tenta obter o ID da coluna 'id' do mapeamento dinâmico para log.
        col_id_nome_log = dynamic_column_map.get('id', {}).get('name', 'ID_FALLBACK')
        id_item_log = row.get(col_id_nome_log, f"ID_NAO_ENCONTRADO_EM_COL_{col_id_nome_log}")
        sheet_row_num_original = row.get('sheet_row_num', "sheet_row_num_NAO_ENCONTRADO") # sheet_row_num é adicionado por ler_planilha

        logger.info(f"Loop de processamento: Iteração {i+1}/{total_linhas_para_processar}. Processando linha original da planilha nº {sheet_row_num_original} (ID: {id_item_log}).")

        try:
            dados = sheets.extrair_dados_linha(row, dynamic_column_map)
            if not dados:
                logger.error(f"Falha ao extrair dados para a linha {sheet_row_num_original} (ID: {id_item_log}). Pulando esta linha.")
                ids_com_erro.append(str(id_item_log))
                continue
            
            logger.debug(f"Dados extraídos para linha {sheet_row_num_original} (ID: {dados.get('id', 'N/A')}): {dados}")

            # Se estiver em modo de teste, processa apenas a primeira linha elegível
            if modo_teste and documentos_gerados_sucesso >= 1:
                logger.info(f"[MODO TESTE] Limite de 1 linha processada em modo teste atingido. Encerrando processamento de novas linhas.")
                break 
            
            # Obter a palavra-âncora específica desta linha para refinar as instruções de "evitar padrões"
            palavra_ancora_linha = dados.get('palavra_ancora', '')
            instrucao_adicional_evitar = instrucao_base_evitar # Começa com a instrução base
            
            if palavra_ancora_linha and padroes_por_ancora_a_evitar.get(palavra_ancora_linha.lower()):
                padroes_especificos = padroes_por_ancora_a_evitar[palavra_ancora_linha.lower()]
                instrucao_adicional_evitar += f" Para a âncora '{palavra_ancora_linha}', EVITE especificamente os seguintes padrões de título já usados: {', '.join(padroes_especificos)}."
                logger.info(f"Instrução adicional para evitar padrões para âncora '{palavra_ancora_linha}' adicionada.")

            # Adicionado log antes de chamar Gemini
            logger.info(f"Preparando para chamar API Gemini para ID: {dados.get('id')}, Palavra-âncora: '{dados.get('palavra_ancora', 'N/A')}'")
            
            conteudo_gerado, metricas_gemini, info_link_interno = gemini.gerar_conteudo(
                dados=dados, # CORRIGIDO de dados_linha para dados
                instrucao_adicional=instrucao_adicional_evitar.strip(),
                titulos_existentes=titulos_existentes
            )

            logger.info(f"Conteúdo bruto gerado pela API Gemini para ID {dados.get('id', 'N/A')}: {str(conteudo_gerado)[:200]}...")
            logger.debug(f"Métricas Gemini: {metricas_gemini}")
            logger.debug(f"Info Link Interno: {info_link_interno}")

            if not conteudo_gerado:
                logger.error(f"API Gemini retornou conteúdo vazio para ID {dados.get('id', 'N/A')}. Pulando esta linha.")
                ids_com_erro.append(str(dados.get('id', 'N/A')))
                if metricas_gemini and metricas_gemini.get('block_reason'):
                    logger.error(f"  Motivo do bloqueio: {metricas_gemini.get('block_reason_message')}")
                sheets.atualizar_status(sheet_row_num_original, f"Erro Gemini: Conteúdo vazio ou bloqueado - {metricas_gemini.get('block_reason', 'N/D')}")
                continue

            # O título já foi processado e formatado como H1 pela gemini.gerar_conteudo
            # e está na primeira linha de 'conteudo_gerado'.
            # Extraímos ele daqui para uso em docs e sheets.
            linhas_conteudo = conteudo_gerado.strip().split('\n')
            titulo_para_doc_e_sheet = "Sem título"
            if linhas_conteudo:
                titulo_bruto_h1 = linhas_conteudo[0].strip()
                # Remove o marcador H1 (ex: "# ") do início, se presente
                titulo_para_doc_e_sheet = re.sub(r"^#+\s*", "", titulo_bruto_h1).strip()
            
            logger.info(f"Título extraído da primeira linha do conteúdo_gerado: '{titulo_para_doc_e_sheet}' para ID {dados.get('id', 'N/A')}")
            
            # Contar tokens e estimar custo para o item processado
            # (Esta lógica de custo já existe mais abaixo, mas é bom ter a contagem de tokens aqui)
            tokens_entrada = metricas_gemini.get('input_token_count', 0)
            tokens_saida = metricas_gemini.get('output_token_count', contar_tokens(conteudo_gerado))
            custo_item_usd = estimar_custo_gemini(tokens_entrada, tokens_saida) # CORRIGIDO: removido ", _"
            custo_item_brl = custo_item_usd * USD_TO_BRL_RATE
            custo_total_estimado_usd += custo_item_usd
            custo_total_estimado_brl += custo_item_brl

            logger.info(f"Estimativa de custo para este item (ID: {dados.get('id', 'N/A')}): USD {custo_item_usd:.4f} / BRL {custo_item_brl:.2f}")

            if modo_teste:
                logger.info(f"[MODO TESTE] ID: {dados.get('id', 'N/A')}, Linha Planilha: {sheet_row_num_original}")
                logger.info(f"[MODO TESTE] Título: {titulo_para_doc_e_sheet}")
                logger.info(f"[MODO TESTE] Conteúdo Gerado (início): {conteudo_gerado[:150]}...")
                logger.info(f"[MODO TESTE] Link Interno Sugerido: {info_link_interno}")
                logger.info(f"[MODO TESTE] Custo Estimado Item: USD {custo_item_usd:.4f} / BRL {custo_item_brl:.2f}")
                documentos_gerados_sucesso += 1
                ids_processados_com_sucesso.append(str(dados.get('id', 'N/A')))
                # Simular atualização de status em modo teste, sem chamada real à planilha
                logger.info(f"[MODO TESTE] Status seria atualizado para: 'Teste Concluído - {datetime.now().strftime('%Y-%m-%d %H:%M')}'")
                logger.info(f"[MODO TESTE] URL do Documento (simulada): teste_doc_url_{dados.get('id', 'N/A')}")
                logger.info("[MODO TESTE] Nenhuma alteração real será feita na planilha ou Google Docs.")
                # Delay simulado em modo teste também, se configurado
                if DELAY_ENTRE_CHAMADAS_GEMINI > 0:
                    logger.info(f"[MODO TESTE] Aguardando {DELAY_ENTRE_CHAMADAS_GEMINI}s (delay simulado)...")
                    time.sleep(DELAY_ENTRE_CHAMADAS_GEMINI)
                continue # Pula para a próxima iteração em modo de teste APÓS a primeira execução bem-sucedida

            # Criação do Documento no Google Docs
            id_original_doc = dados.get('id', 'Sem-ID') # Renomeado para evitar conflito com id_item_log
            site_doc = dados.get('site', 'Sem-site')
            palavra_ancora_doc = dados.get('palavra_ancora', 'Tópico') # Renomeado
            
            nome_arquivo_gdoc = gerar_nome_arquivo(id_original_doc, site_doc, palavra_ancora_doc) # Sufixo padrão é _conteudo
            logger.info(f"Preparando para criar/atualizar Google Doc com nome: {nome_arquivo_gdoc} para ID {id_original_doc}")

            document_id, document_url = docs.criar_documento(
                titulo=titulo_para_doc_e_sheet,  # Usar o título extraído aqui
                conteudo=conteudo_gerado, # CORRIGIDO de corpo para conteudo
                nome_arquivo=nome_arquivo_gdoc, # CORRIGIDO de nome_arquivo_sem_ext para nome_arquivo
                info_link=info_link_interno
            )

            if document_url:
                logger.info(f"Documento criado/atualizado com sucesso para ID {id_original_doc} (Linha {sheet_row_num_original}): {document_url}")
                sheets.atualizar_url_documento(
                    sheet_row_num_original, 
                    document_url,
                    spreadsheet_id=current_spreadsheet_id, # ADICIONADO
                    sheet_name=current_sheet_name # ADICIONADO
                )
                sheets.atualizar_titulo_documento(
                    sheet_row_num_original, 
                    titulo_para_doc_e_sheet, # Usar o título extraído aqui
                    spreadsheet_id=current_spreadsheet_id, # ADICIONADO
                    sheet_name=current_sheet_name # ADICIONADO
                )
                logger.info(f"Custo e tokens para ID {id_original_doc} (Linha {sheet_row_num_original}) seriam atualizados aqui se a função existisse: Entrada={tokens_entrada}, Saída={tokens_saida}, USD={custo_item_usd:.4f}, BRL={custo_item_brl:.2f}")
                status_final_sucesso = f"Concluído - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                logger.info(f"Status para ID {id_original_doc} (Linha {sheet_row_num_original}) seria atualizado para '{status_final_sucesso}' aqui se a função existisse.")
                documentos_gerados_sucesso += 1
                ids_processados_com_sucesso.append(str(id_original_doc))
            else:
                logger.error(f"Falha ao criar/atualizar documento no Google Docs para ID {id_original_doc} (Linha {sheet_row_num_original}). URL não retornada.")
                ids_com_erro.append(str(id_original_doc))
                sheets.atualizar_status(sheet_row_num_original, "Erro Docs: Falha ao criar/obter URL")
                # Não continuar se o doc falhou, pois não há URL para salvar.

        except Exception as e:
            id_item_excecao = dados.get('id', id_item_log if 'id_item_log' in locals() else f"Desconhecido_Iter_{i}")
            logger.error(f"Erro inesperado ao processar linha {sheet_row_num_original} (ID: {id_item_excecao}): {e}")

    logger.info(f"Processamento concluído. Documentos gerados com sucesso: {documentos_gerados_sucesso}, IDs processados: {ids_processados_com_sucesso}, IDs com erro: {ids_com_erro}")
    return documentos_gerados_sucesso, ids_processados_com_sucesso, ids_com_erro

def print_menu(spreadsheet_id: Optional[str], sheet_name: Optional[str], drive_folder_id: Optional[str]):
    """Imprime o menu principal do aplicativo."""
    print("\n╔═════════════════════════════════════════════════════════════════════════════╗")
    print("║                         GERADOR DE CONTEÚDO SEO                         ║")
    print("╠═════════════════════════════════════════════════════════════════════════════╣")
    # Mostrar informações da planilha e pasta selecionadas
    planilha_status = f'{spreadsheet_id} ({sheet_name if sheet_name else "Nenhuma aba"})' if spreadsheet_id else "Nenhuma planilha selecionada"
    print(f"║ Planilha Ativa: {planilha_status:<56}║")
    pasta_status = drive_folder_id if drive_folder_id else "Nenhuma pasta selecionada"
    print(f"║ Pasta do Drive: {pasta_status:<56}║")
    print("╠═════════════════════════════════════════════════════════════════════════════╣")
    print("║ OPÇÕES PRINCIPAIS:                                                          ║")
    print("║   1. Processar Linhas da Planilha (Gerar Conteúdo)                          ║")
    print("║   2. Verificar Títulos Duplicados na Planilha Atual                         ║")
    print("║   3. Verificar Similaridade de Conteúdos na Planilha Atual                  ║")
    print("║   4. Corrigir Termos Proibidos nos Documentos da Planilha Atual             ║")
    print("║   5. Estimar Custo por Categoria na Planilha Atual                          ║")
    print("║                                                                             ║")
    print("║ CONFIGURAÇÕES:                                                              ║")
    print("║   6. Selecionar Planilha/Aba do Google Sheets                               ║")
    print("║   7. Selecionar Pasta do Google Drive para Salvar Documentos                ║")
    print("║                                                                             ║")
    print("║   0. Sair                                                                     ║")
    print("╚═════════════════════════════════════════════════════════════════════════════╝")

def main(modo_teste: bool = False):
    configurar_logging() # Configura o logging primeiro
    logger = logging.getLogger('seo_linkbuilder') # Obtém a instância do logger
    logger.info(f"Iniciando o SEO-LinkBuilder... Modo Teste: {modo_teste}")
    global SPREADSHEET_ID, SHEET_NAME, DRIVE_FOLDER_ID # Declarar globais

    # Carregar últimas seleções ao iniciar
    ultima_selecao = carregar_ultima_selecao()
    spreadsheet_id_selecionado = ultima_selecao.get("spreadsheet_id")
    sheet_name_selecionado = ultima_selecao.get("sheet_name")
    DRIVE_FOLDER_ID = ultima_selecao.get("drive_folder_id", DRIVE_FOLDER_ID) # Usa o salvo ou o default do config

    if spreadsheet_id_selecionado and sheet_name_selecionado:
        logger.info(f"Carregada última seleção: Planilha '{spreadsheet_id_selecionado}', Aba '{sheet_name_selecionado}'")
        # Atualiza as globais SPREADSHEET_ID e SHEET_NAME para que sheets_handler as use implicitamente se não forem passadas
        SPREADSHEET_ID = spreadsheet_id_selecionado
        SHEET_NAME = sheet_name_selecionado
    if DRIVE_FOLDER_ID:
        logger.info(f"Pasta do Drive para salvar documentos: {DRIVE_FOLDER_ID}")
    
    try:
        # Inicializa o SheetsHandler principal uma vez aqui
        # Ele será atualizado se o usuário selecionar uma nova planilha/aba no menu
        sheets_handler = SheetsHandler() # REMOVIDO ARGUMENTOS
    except Exception as e:
        logger.error(f"Erro ao inicializar SheetsHandler no início: {e}. Verifique as configurações e credenciais.")
        return

    while True:
        print_menu(spreadsheet_id_selecionado, sheet_name_selecionado, DRIVE_FOLDER_ID)
        escolha = input("Escolha uma opção: ").strip()

        if escolha == '1':
            if not spreadsheet_id_selecionado or not sheet_name_selecionado:
                logger.warning("Nenhuma planilha/aba selecionada. Use a opção '6' (Selecionar Planilha/Aba) primeiro.")
                continue
            
            # Início da lógica restaurada para a ESCOLHA 1
            print("\nOpções de processamento para Gerar Conteúdo:")
            print("T - Processar todos os itens pendentes")
            print("Q - Processar uma quantidade específica de itens pendentes")
            print("L - Processar uma linha específica da planilha PELO SEU ID")
            print("V - Voltar ao menu principal")
            
            sub_escolha = input("Escolha uma sub-opção: ").strip().upper()
            
            limite_linhas_proc = None
            # linha_inicial_proc não é mais usada diretamente aqui, id_linha_proc tem prioridade para 'L'
            id_linha_proc = None 
            reprocessar_proc = False

            if sub_escolha == 'T':
                limite_linhas_proc = 0 # Significa processar todos os pendentes
            elif sub_escolha == 'Q':
                try:
                    limite_linhas_proc = int(input("Quantos itens pendentes você quer processar? "))
                    if limite_linhas_proc <= 0:
                        print("Quantidade inválida. Deve ser maior que zero.")
                        continue # Volta para o menu principal
                except ValueError:
                    print("Entrada inválida para quantidade.")
                    continue # Volta para o menu principal
            elif sub_escolha == 'L':
                id_linha_proc = input("Digite o ID da linha que você quer processar: ").strip()
                if not id_linha_proc:
                    print("ID da linha não pode ser vazio.")
                    continue # Volta para o menu principal
                try:
                    quantidade_a_partir_id = int(input(f"Quantos itens você quer processar a partir da linha com ID '{id_linha_proc}' (inclusive esta linha)? "))
                    if quantidade_a_partir_id <= 0:
                        print("Quantidade inválida. Deve ser maior que zero.")
                        continue
                    limite_linhas_proc = quantidade_a_partir_id
                except ValueError:
                    print("Entrada inválida para quantidade.")
                    continue
            elif sub_escolha == 'V':
                continue # Volta para o menu principal
            else:
                print("Sub-opção inválida.")
                continue # Volta para o menu principal

            if sub_escolha in ['T', 'Q', 'L']:
                reprocessar_escolha = input("Deseja reprocessar linhas que já possuem URL de documento? (S/N, Enter para Não): ").strip().upper()
                if reprocessar_escolha == 'S':
                    reprocessar_proc = True
            
            logger.info(f"Iniciando processamento de planilha. Limite: {limite_linhas_proc if limite_linhas_proc is not None else 'N/A'}, ID Linha Específica: {id_linha_proc if id_linha_proc else 'N/A'}, Reprocessar Concluídos: {reprocessar_proc}")
            processar_planilha(
                limite_linhas=limite_linhas_proc, 
                # linha_inicial_desejada não é mais definida neste menu, id_linha_especifica tem prioridade
                id_linha_especifica=id_linha_proc, 
                reprocessar_concluidos=reprocessar_proc, 
                modo_teste=modo_teste,
                spreadsheet_id=spreadsheet_id_selecionado, # Passa o ID da planilha selecionado
                sheet_name=sheet_name_selecionado       # Passa o nome da aba selecionada
            )
            # Fim da lógica restaurada para a ESCOLHA 1

        elif escolha == '2':
            if not spreadsheet_id_selecionado or not sheet_name_selecionado:
                logger.warning("Nenhuma planilha/aba selecionada. Use a opção '6' (Selecionar Planilha/Aba) primeiro.")
                continue
            logger.info("Chamando verificação de similaridade de conteúdos...")
            try:
                temp_sheets_sim = SheetsHandler()
                temp_gemini_sim = GeminiHandler()
                temp_docs_sim = DocsHandler()
                header_info_sim = temp_sheets_sim._find_header_and_map_columns(spreadsheet_id_selecionado, sheet_name_selecionado)
                if not header_info_sim:
                    logger.error("Não foi possível obter mapeamento de colunas para verificação de similaridade.")
                    continue
                _, _, dynamic_column_map_sim = header_info_sim
                
                limiar_str = input("Digite o limiar de similaridade (ex: 0.4 para 40%, Enter para padrão 0.4): ").strip()
                limiar_similaridade_val = 0.4
                if limiar_str:
                    try:
                        limiar_similaridade_val = float(limiar_str)
                        if not (0.0 < limiar_similaridade_val < 1.0):
                            logger.warning("Limiar inválido. Usando padrão 0.4.")
                            limiar_similaridade_val = 0.4
                    except ValueError:
                        logger.warning("Entrada inválida para limiar. Usando padrão 0.4.")
                
                verificar_similaridade_conteudos(temp_sheets_sim, temp_gemini_sim, temp_docs_sim, dynamic_column_map_sim, limiar_similaridade=limiar_similaridade_val, modo_teste=modo_teste)
            except Exception as e:
                logger.error(f"Erro ao preparar para verificar similaridade: {e}")

        elif escolha == '3':
            if not spreadsheet_id_selecionado or not sheet_name_selecionado:
                logger.warning("Nenhuma planilha/aba selecionada. Use a opção '6' (Selecionar Planilha/Aba) primeiro.")
                continue
            logger.info("Chamando correção de termos proibidos...")
            try:
                temp_sheets_term = SheetsHandler()
                temp_docs_term = DocsHandler() 
                header_info_term = temp_sheets_term._find_header_and_map_columns(spreadsheet_id_selecionado, sheet_name_selecionado)
                if not header_info_term:
                    logger.error("Não foi possível obter mapeamento de colunas para correção de termos.")
                    continue
                _, _, dynamic_column_map_term = header_info_term
                corrigir_termos_proibidos(temp_sheets_term, temp_docs_term, dynamic_column_map_term, modo_teste=modo_teste)
            except Exception as e:
                logger.error(f"Erro ao preparar para corrigir termos proibidos: {e}")

        elif escolha == '4':
            if not spreadsheet_id_selecionado or not sheet_name_selecionado:
                logger.warning("Nenhuma planilha/aba selecionada. Use a opção '6' (Selecionar Planilha/Aba) primeiro.")
                continue
            logger.info("Chamando estimativa de custos por categoria...")
            try:
                temp_sheets_custo = SheetsHandler()
                header_info_custo = temp_sheets_custo._find_header_and_map_columns(spreadsheet_id_selecionado, sheet_name_selecionado)
                if not header_info_custo:
                    logger.error("Não foi possível obter mapeamento de colunas para estimar custos.")
                    continue
                _, _, dynamic_column_map_custo = header_info_custo
                custos_categoria = estimar_custo_por_categoria(temp_sheets_custo, dynamic_column_map_custo)
                if custos_categoria:
                    print("\n--- Estimativa de Custo por Categoria ---")
                    for cat, data in custos_categoria.items():
                        print(f"Categoria: {cat}, Custo Médio: R${data['custo_medio']:.2f}, Itens: {data['contagem']}")
                    print("-----------------------------------------")
                else:
                    print("Não foi possível estimar custos por categoria ou não há dados.")
            except Exception as e:
                logger.error(f"Erro ao estimar custos por categoria: {e}")

        elif escolha == '5':
            resultado_selecao = apresentar_menu_planilha(sheets_handler)
            if resultado_selecao:
                spreadsheet_id_selecionado, sheet_name_selecionado = resultado_selecao
                logger.info(f"Planilha '{spreadsheet_id_selecionado}' e Aba '{sheet_name_selecionado}' selecionadas para operações futuras.")
                sheets_handler.spreadsheet_id = spreadsheet_id_selecionado # Atualiza o handler principal se necessário
                sheets_handler.sheet_name = sheet_name_selecionado
            else:
                logger.warning("Seleção de planilha cancelada ou falhou.")

        elif escolha == '6':
            folder_id_atualizado = apresentar_menu_pasta_drive()
            if folder_id_atualizado:
                DRIVE_FOLDER_ID = folder_id_atualizado
                logger.info(f"Pasta do Google Drive para salvar documentos ATUALIZADA para: {DRIVE_FOLDER_ID}")
                # Salva esta nova pasta como parte da última seleção global
                ultima_sel = carregar_ultima_selecao()
                ultima_sel["drive_folder_id"] = DRIVE_FOLDER_ID
                salvar_ultima_selecao(ultima_sel)
            else:
                logger.warning("Seleção de pasta do Drive cancelada ou não alterada.")

        elif escolha == '0':
            logger.info("Saindo do script. Até mais!")
            return
        else:
            print("Opção inválida. Por favor, escolha uma opção válida.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SEO-LinkBuilder - Gerador de conteúdo para SEO')
    parser.add_argument('--teste', action='store_true',
                        help='Executa apenas para a primeira linha sem atualizar a planilha e simula interações com APIs.') # Descrição mais precisa
    
    args = parser.parse_args()
    
    # A lógica para determinar o número de linhas e a partir de qual linha começar
    # agora está dentro da função main() através de um menu interativo.
    
    main(modo_teste=args.teste)