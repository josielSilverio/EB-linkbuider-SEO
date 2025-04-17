# Módulo para funções utilitárias (logging, formatação, etc.)
import logging
import os
import re
import sys
from datetime import datetime
import tiktoken

# Configuração de logging
def configurar_logging(nivel=logging.INFO):
    """
    Configura o sistema de logging para o console e um arquivo
    """
    # Cria o diretório de logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Nome do arquivo de log com data atual
    data_atual = datetime.now().strftime('%Y-%m-%d')
    log_arquivo = f'logs/seo_linkbuilder_{data_atual}.log'
    
    # Configuração do logging
    logging.basicConfig(
        level=nivel,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_arquivo),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('seo_linkbuilder')

# Funções para manipulação de texto
def extrair_titulos_markdown(texto):
    """
    Extrai todos os títulos (H1, H2, H3, etc.) de um texto em Markdown.
    Retorna uma lista de tuplas (nivel, texto_titulo)
    """
    padrao = r'^(#{1,6})\s+(.*?)$'
    titulos = []
    
    for linha in texto.split('\n'):
        match = re.match(padrao, linha)
        if match:
            nivel = len(match.group(1))  # Número de # define o nível
            titulo = match.group(2).strip()
            titulos.append((nivel, titulo))
    
    return titulos

def converter_markdown_para_docs(texto, info_link=None):
    """
    Converte texto com estrutura natural para o formato usado pela API do Google Docs.
    Identifica título, subtítulos e parágrafos com base no contexto e posição no texto.
    
    Args:
        texto: O texto a ser convertido
        info_link: Informações sobre o link a ser criado (opcional)
        
    Returns:
        Lista de requests para a API do Docs
    """
    requests = []
    # Divide o texto em linhas
    linhas = texto.split('\n')
    
    # Primeira linha não vazia é o título principal
    titulo_principal = None
    linha_atual = 0
    
    # Encontra o título principal (primeira linha não vazia)
    while linha_atual < len(linhas) and not titulo_principal:
        if linhas[linha_atual].strip():
            titulo_principal = linhas[linha_atual].strip()
            # Insere o título principal
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': titulo_principal + '\n'
                }
            })
            # Formata como Heading 1
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': 1 + len(titulo_principal) + 1
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'HEADING_1'
                    },
                    'fields': 'namedStyleType'
                }
            })
        linha_atual += 1
    
    # Variáveis para rastrear a posição atual no documento
    posicao_atual = 1 + len(titulo_principal) + 1 if titulo_principal else 1
    
    # Rastreia a posição atual no texto original 
    posicao_texto_original = 0
    
    # Processa o restante do texto
    paragrafo_atual = ""
    modo_paragrafo = True
    
    for i in range(linha_atual, len(linhas)):
        linha = linhas[i].strip()
        
        # Atualiza a posição no texto original
        posicao_texto_original += len(linhas[i]) + 1  # +1 para o \n
        
        # Linha vazia significa quebra de parágrafo
        if not linha:
            if paragrafo_atual:
                # Adiciona o parágrafo ao documento
                requests.append({
                    'insertText': {
                        'location': {'index': 1},
                        'text': paragrafo_atual + '\n\n'
                    }
                })
                
                # Atualiza a posição atual
                posicao_atual += len(paragrafo_atual) + 2  # +2 para \n\n
                
                paragrafo_atual = ""
            modo_paragrafo = True
            continue
        
        # Verifica se é um subtítulo (geralmente são linhas curtas)
        # A heurística é: linha curta (< 60 chars) e que não termina com pontuação
        # E que não está no meio de um parágrafo
        eh_subtitulo = False
        if modo_paragrafo and len(linha) < 60 and not linha[-1] in '.!?:;,':
            eh_subtitulo = True
        
        if eh_subtitulo:
            # Se tem texto acumulado, insere como parágrafo
            if paragrafo_atual:
                requests.append({
                    'insertText': {
                        'location': {'index': 1},
                        'text': paragrafo_atual + '\n\n'
                    }
                })
                posicao_atual += len(paragrafo_atual) + 2
                paragrafo_atual = ""
            
            # Insere o subtítulo
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': linha + '\n'
                }
            })
            
            # Formata como Heading 2
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': 1 + len(linha) + 1
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'HEADING_2'
                    },
                    'fields': 'namedStyleType'
                }
            })
            
            # Atualiza a posição atual
            posicao_atual += len(linha) + 1
            
            modo_paragrafo = True
        else:
            # Texto normal, adiciona ao parágrafo atual
            if paragrafo_atual:
                paragrafo_atual += " " + linha
            else:
                paragrafo_atual = linha
            modo_paragrafo = False
    
    # Adiciona qualquer texto restante
    if paragrafo_atual:
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': paragrafo_atual + '\n'
            }
        })
        posicao_atual += len(paragrafo_atual) + 1
    
    # Se temos informações de link, adiciona o link
    if info_link:
        # Encontra a posição do link no documento
        # Precisamos recalcular as posições no documento final
        texto_completo = texto
        
        # Calcula a posição relativa ao início do documento
        posicao_inicio = info_link['posicao_inicio'] 
        posicao_fim = info_link['posicao_fim']
        
        # Posições aproximadas no documento final
        doc_inicio = posicao_inicio + 1  # +1 para o índice base do Google Docs
        doc_fim = posicao_fim + 1
        
        # Adiciona o comando para criar o link
        requests.append({
            'updateTextStyle': {
                'range': {
                    'startIndex': doc_inicio,
                    'endIndex': doc_fim
                },
                'textStyle': {
                    'link': {
                        'url': info_link['url']
                    }
                },
                'fields': 'link'
            }
        })
    
    return requests

# Contador de tokens
def contar_tokens(texto, modelo="gpt-3.5-turbo"):
    """
    Conta os tokens em um texto com base no modelo especificado.
    Útil para estimar custos antes de enviar para a API.
    """
    try:
        # Tenta usar o contador de tokens do tiktoken
        codificador = tiktoken.encoding_for_model(modelo)
        return len(codificador.encode(texto))
    except Exception as e:
        # Fallback: estimativa aproximada baseada em palavras
        logging.warning(f"Erro ao contar tokens com tiktoken: {e}")
        palavras = texto.split()
        # Aproximação: ~0.75 tokens por palavra para inglês, ~0.6 para português
        return int(len(palavras) * 0.6)

def substituir_links_markdown(texto, palavra_ancora, url_ancora):
    """
    Substitui ocorrências da palavra âncora para criar links no Google Docs.
    Agora trabalha com texto em formato natural, em vez de markdown.
    """
    # Padrão regex para encontrar a palavra âncora como palavra completa (ignorando case)
    padrao = r'(^|[^\w])(' + re.escape(palavra_ancora) + r')([^\w]|$)'
    
    # Verificamos se a palavra âncora foi encontrada
    match = re.search(padrao, texto, flags=re.IGNORECASE)
    
    if not match:
        # Se não encontrou, retorna o texto original
        return texto
    
    # Posição onde a palavra foi encontrada
    posicao_inicio = match.start(2)
    posicao_fim = match.end(2)
    
    # Guardamos a informação da posição da palavra âncora para criar o link posteriormente
    # Esta informação será usada pela função converter_markdown_para_docs
    info_link = {
        'palavra': match.group(2),
        'url': url_ancora,
        'posicao_inicio': posicao_inicio,
        'posicao_fim': posicao_fim
    }
    
    # Retornamos o texto original e a informação do link
    return texto, info_link 