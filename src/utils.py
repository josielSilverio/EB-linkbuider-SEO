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

def converter_markdown_para_docs(texto):
    """
    Converte a formatação Markdown básica para o formato usado pela API do Google Docs.
    Retorna um array de pedidos (requests) para a API do Docs.
    """
    requests = []
    paragrafo_atual = ""
    
    # Divide o texto em linhas
    linhas = texto.split('\n')
    
    for i, linha in enumerate(linhas):
        # Verifica se é um título
        titulo_match = re.match(r'^(#{1,6})\s+(.*?)$', linha)
        if titulo_match:
            nivel = len(titulo_match.group(1))
            titulo_texto = titulo_match.group(2).strip()
            
            # Se tem texto acumulado, insere como parágrafo normal
            if paragrafo_atual.strip():
                requests.append({
                    'insertText': {
                        'location': {'index': 1},
                        'text': paragrafo_atual + '\n'
                    }
                })
                paragrafo_atual = ""
            
            # Insere o título
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': titulo_texto + '\n'
                }
            })
            
            # Aplica formatação conforme o nível do título
            estilo = 'HEADING_1'
            if nivel == 2:
                estilo = 'HEADING_2'
            elif nivel >= 3:
                estilo = 'HEADING_3'
            
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': 1 + len(titulo_texto) + 1
                    },
                    'paragraphStyle': {
                        'namedStyleType': estilo
                    },
                    'fields': 'namedStyleType'
                }
            })
        
        # Verifica se é uma linha em branco (quebra de parágrafo)
        elif not linha.strip():
            if paragrafo_atual:
                requests.append({
                    'insertText': {
                        'location': {'index': 1},
                        'text': paragrafo_atual + '\n\n'
                    }
                })
                paragrafo_atual = ""
            else:
                # Se já estava em branco, adiciona outra quebra
                requests.append({
                    'insertText': {
                        'location': {'index': 1},
                        'text': '\n'
                    }
                })
        
        # Conteúdo normal
        else:
            # Processa o texto para verificar formatação inline (negrito, itálico)
            texto_processado = linha
            
            # Adiciona ao parágrafo atual
            if paragrafo_atual:
                paragrafo_atual += " " + texto_processado
            else:
                paragrafo_atual = texto_processado
    
    # Adiciona qualquer texto restante
    if paragrafo_atual:
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': paragrafo_atual + '\n'
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
    Substitui ocorrências da palavra âncora por um link markdown apontando para a URL.
    """
    # Padrão regex para encontrar a palavra âncora como palavra completa (ignorando case)
    padrao = r'(^|[^\w])(' + re.escape(palavra_ancora) + r')([^\w]|$)'
    
    # Função de substituição que preserva o case original e adiciona o link
    def adicionar_link(match):
        antes = match.group(1)  # Texto antes da palavra
        palavra = match.group(2)  # A palavra âncora encontrada com o case original
        depois = match.group(3)  # Texto depois da palavra
        return f"{antes}[{palavra}]({url_ancora}){depois}"
    
    # Substitui apenas a primeira ocorrência
    texto_substituido = re.sub(padrao, adicionar_link, texto, count=1, flags=re.IGNORECASE)
    return texto_substituido 