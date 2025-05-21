# Módulo para funções utilitárias (logging, formatação, etc.)
import logging
import os
import re
import sys
from datetime import datetime
import tiktoken
from collections import Counter
import unicodedata # Para normalização de acentos
import pandas as pd

# Configura o logger para este módulo
logger = logging.getLogger(__name__)

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
    
    # Remove handlers existentes para evitar duplicação
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    # Configuração base (sem handlers inicialmente)
    logging.basicConfig(
        level=nivel,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Cria os handlers com encoding UTF-8
    file_handler = logging.FileHandler(log_arquivo, encoding='utf-8')
    stream_handler = logging.StreamHandler(sys.stdout)
    # Tenta definir encoding para stdout, pode falhar dependendo do terminal
    try:
        stream_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
    except Exception:
        # Se falhar, usa o stdout padrão (pode ter problemas de encoding no console)
        pass 

    # Define o formatador
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    
    # Adiciona os handlers ao logger raiz
    logging.root.addHandler(file_handler)
    logging.root.addHandler(stream_handler)
    
    # Retorna o logger principal
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

def limpar_markdown_links(texto):
    """Remove links em markdown ([texto](url)) e HTML (<a href=...>) do texto, mantendo apenas o texto visível."""
    # Remove [texto](url)
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    # Remove <a href="...">texto</a>
    texto = re.sub(r'<a [^>]*href=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</a>', r'\2', texto, flags=re.IGNORECASE)
    return texto

def converter_markdown_para_docs(texto, info_link=None):
    """
    Converte texto com estrutura natural para o formato usado pela API do Google Docs.
    Identifica título, subtítulos, parágrafos e listas.
    """
    requests = []
    # Limpa links markdown e HTML antes de processar
    texto = limpar_markdown_links(texto)
    # Divide o texto em linhas
    linhas = [linha.strip() for linha in texto.split('\n') if linha.strip()]
    if not linhas:
        return requests
    titulo_principal = linhas[0]
    # Insere o título principal
    requests.append({
        'insertText': {
            'location': {'index': 1},
            'text': titulo_principal + '\n\n'
        }
    })
    # Formata como Heading 1
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'startIndex': 1,
                'endIndex': 1 + len(titulo_principal)
            },
            'paragraphStyle': {
                'namedStyleType': 'HEADING_1'
            },
            'fields': 'namedStyleType'
        }
    })
    # Aplica estilo ao título (tamanho 13pt, negrito)
    requests.append({
        'updateTextStyle': {
            'range': {
                'startIndex': 1,
                'endIndex': 1 + len(titulo_principal)
            },
            'textStyle': {
                'fontSize': {
                    'magnitude': 13,
                    'unit': 'PT'
                },
                'bold': True
            },
            'fields': 'fontSize,bold'
        }
    })
    posicao_atual = 1 + len(titulo_principal) + 2
    mapa_paragrafos = {}
    indice_paragrafo = 0
    mapa_paragrafos[0] = {
        'texto': titulo_principal,
        'inicio': 1,
        'fim': 1 + len(titulo_principal)
    }
    i = 1
    while i < len(linhas):
        linha = linhas[i]
        indice_paragrafo += 1
        # Detecta se é item de lista
        eh_lista = bool(re.match(r'^(\*|-|\d+\.)\s+', linha))
        eh_subtitulo = not eh_lista and len(linha) < 60 and not linha[-1] in '.!?:;,' and (i == 1 or i == len(linhas)-1 or len(linhas[i-1]) > 50 or len(linhas[i+1]) > 50)
        inicio_paragrafo = posicao_atual
        fim_paragrafo = posicao_atual + len(linha)
        mapa_paragrafos[indice_paragrafo] = {
            'texto': linha,
            'inicio': inicio_paragrafo,
            'fim': fim_paragrafo,
            'tipo': 'subtitulo' if eh_subtitulo else ('lista' if eh_lista else 'paragrafo')
        }
        if eh_subtitulo:
            requests.append({
                'insertText': {
                    'location': {'index': posicao_atual},
                    'text': linha + '\n\n'
                }
            })
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': posicao_atual,
                        'endIndex': posicao_atual + len(linha)
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'HEADING_2'
                    },
                    'fields': 'namedStyleType'
                }
            })
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': posicao_atual,
                        'endIndex': posicao_atual + len(linha)
                    },
                    'textStyle': {
                        'fontSize': {
                            'magnitude': 11,
                            'unit': 'PT'
                        },
                        'bold': True
                    },
                    'fields': 'fontSize,bold'
                }
            })
            posicao_atual += len(linha) + 2
        elif eh_lista:
            # Remove marcador de lista
            texto_item = re.sub(r'^(\*|-|\d+\.)\s+', '', linha)
            requests.append({
                'insertText': {
                    'location': {'index': posicao_atual},
                    'text': texto_item + '\n'
                }
            })
            # Marca como item de lista
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': posicao_atual,
                        'endIndex': posicao_atual + len(texto_item)
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'NORMAL_TEXT'
                    },
                    'fields': 'namedStyleType'
                }
            })
            posicao_atual += len(texto_item) + 1
        else:
            requests.append({
                'insertText': {
                    'location': {'index': posicao_atual},
                    'text': linha + '\n\n'
                }
            })
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': posicao_atual,
                        'endIndex': posicao_atual + len(linha)
                    },
                    'textStyle': {
                        'fontSize': {
                            'magnitude': 11,
                            'unit': 'PT'
                        },
                        'bold': False
                    },
                    'fields': 'fontSize,bold'
                }
            })
            posicao_atual += len(linha) + 2
        i += 1
    
    # Se temos informações de link, adiciona o link
    if info_link and 'palavra' in info_link and 'url' in info_link:
        palavra = info_link['palavra']
        url = info_link['url']
        paragrafo_alvo = info_link.get('paragrafo', -1)
        
        # Se sabemos em qual parágrafo a palavra está
        if paragrafo_alvo > 0 and paragrafo_alvo in mapa_paragrafos:
            paragrafo = mapa_paragrafos[paragrafo_alvo]
            texto_paragrafo = paragrafo['texto'].lower()
            posicao_na_linha = texto_paragrafo.find(palavra.lower())
            
            if posicao_na_linha >= 0:
                # Calcula a posição exata no documento
                posicao_inicio = paragrafo['inicio'] + posicao_na_linha
                posicao_fim = posicao_inicio + len(palavra)
                
                # Adiciona o comando para criar o link
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': posicao_inicio,
                            'endIndex': posicao_fim
                        },
                        'textStyle': {
                            'link': {
                                'url': url
                            }
                        },
                        'fields': 'link'
                    }
                })
                
                # Adiciona um estilo extra para destacar o link
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': posicao_inicio,
                            'endIndex': posicao_fim
                        },
                        'textStyle': {
                            'foregroundColor': {
                                'color': {
                                    'rgbColor': {
                                        'blue': 0.8,
                                        'red': 0.0,
                                        'green': 0.0
                                    }
                                }
                            },
                            'underline': True
                        },
                        'fields': 'foregroundColor,underline'
                    }
                })
                
                logger.info(
                    f"Link aplicado à palavra '{palavra}' no parágrafo {paragrafo_alvo} posição {posicao_inicio}-{posicao_fim}"
                )
                return requests
        
        # Se não sabemos o parágrafo exato ou não encontramos a palavra no parágrafo, procuramos em todos os parágrafos
        for num_paragrafo, paragrafo in mapa_paragrafos.items():
            # Pular parágrafos de título ou subtítulo
            if paragrafo.get('tipo') == 'subtitulo':
                continue
                
            texto_paragrafo = paragrafo['texto'].lower()
            posicao_na_linha = texto_paragrafo.find(palavra.lower())
            
            if posicao_na_linha >= 0:
                # Calcula a posição exata no documento
                posicao_inicio = paragrafo['inicio'] + posicao_na_linha
                posicao_fim = posicao_inicio + len(palavra)
                
                # Adiciona o comando para criar o link
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': posicao_inicio,
                            'endIndex': posicao_fim
                        },
                        'textStyle': {
                            'link': {
                                'url': url
                            }
                        },
                        'fields': 'link'
                    }
                })
                
                # Adiciona um estilo extra para destacar o link
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': posicao_inicio,
                            'endIndex': posicao_fim
                        },
                        'textStyle': {
                            'foregroundColor': {
                                'color': {
                                    'rgbColor': {
                                        'blue': 0.8,
                                        'red': 0.0,
                                        'green': 0.0
                                    }
                                }
                            },
                            'underline': True
                        },
                        'fields': 'foregroundColor,underline'
                    }
                })
                
                logger.info(
                    f"Link aplicado à palavra '{palavra}' no parágrafo {num_paragrafo} posição {posicao_inicio}-{posicao_fim}"
                )
                break
    
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
        logger.warning(f"Erro ao contar tokens com tiktoken: {e}")
        palavras = texto.split()
        # Aproximação: ~0.75 tokens por palavra para inglês, ~0.6 para português
        return int(len(palavras) * 0.6)

def substituir_links_markdown(texto, palavra_ancora, url_ancora):
    """
    Aplica o hyperlink na palavra-âncora apenas no segundo parágrafo do corpo do texto (ignorando o título).
    Se não encontrar no segundo, tenta no terceiro. Nunca aplica no título.
    """
    logger = logging.getLogger('seo_linkbuilder.utils')
    paragrafos = [p for p in texto.split('\n') if p.strip()]
    palavra_ancora = palavra_ancora.strip()
    # Ignora o título (primeiro parágrafo)
    corpo = paragrafos[1:] if len(paragrafos) > 1 else []
    # Tenta aplicar no segundo parágrafo do corpo (parágrafo 2 do texto)
    if len(corpo) >= 1 and palavra_ancora in corpo[0]:
        i = 1  # Parágrafo 2 do texto
        paragrafo = corpo[0]
        match = re.search(r'\b' + re.escape(palavra_ancora) + r'\b', paragrafo)
        if match:
            inicio_contexto = max(0, match.start() - 50)
            fim_contexto = min(len(paragrafo), match.end() + 50)
            contexto = paragrafo[inicio_contexto:fim_contexto]
            logger.info(f"Contexto da palavra-âncora: '...{contexto}...'")
        info_link = {
            'palavra': palavra_ancora,
            'url': url_ancora,
            'paragrafo': i+1,  # +1 porque ignoramos o título
            'contexto_natural': True
        }
        return texto, info_link
    # Se não encontrar no segundo, tenta no terceiro parágrafo do corpo
    if len(corpo) >= 2 and palavra_ancora in corpo[1]:
        i = 2  # Parágrafo 3 do texto
        paragrafo = corpo[1]
        match = re.search(r'\b' + re.escape(palavra_ancora) + r'\b', paragrafo)
        if match:
            inicio_contexto = max(0, match.start() - 50)
            fim_contexto = min(len(paragrafo), match.end() + 50)
            contexto = paragrafo[inicio_contexto:fim_contexto]
            logger.info(f"Contexto da palavra-âncora: '...{contexto}...'")
        info_link = {
            'palavra': palavra_ancora,
            'url': url_ancora,
            'paragrafo': i+1,
            'contexto_natural': True
        }
        return texto, info_link
    # Se não encontrar, segue o fluxo normal (busca em outros parágrafos, mas nunca no título)
    for idx, paragrafo in enumerate(corpo):
        if palavra_ancora in paragrafo:
            info_link = {
                'palavra': palavra_ancora,
                'url': url_ancora,
                'paragrafo': idx+2,  # +2 porque ignoramos o título
                'contexto_natural': True
            }
            return texto, info_link
    # Se não encontrar, retorna texto sem info_link
    logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no corpo do texto para aplicar hyperlink.")
    return texto, None

# Lista de stopwords em português (expandida e normalizada)
PORTUGUESE_STOPWORDS = set([
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "nao", "uma", # "não" normalizado
    "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", "ao", "ele",
    "das", "tem", "a", "seu", "sua", "ou", "ser", "quando", "muito", "ha", "nos", "ja", # "à", "há", "já" normalizados
    "esta", "eu", "tambem", "so", "pelo", "pela", "ate", "isso", "ela", "entre", "era", # "está", "também", "só", "até" normalizados
    "depois", "sem", "mesmo", "aos", "ter", "seus", "quem", "nas", "me", "esse", "eles",
    "estao", "voce", "tinha", "foram", "essa", "num", "nem", "suas", "meu", "as", "minha", # "estão", "você", "às" normalizados
    "numa", "pelos", "elas", "havia", "seja", "qual", "sera", "nos", "tenho", "lhe", "deles", # "será" normalizado
    "essas", "esses", "pelas", "este", "fosse", "dele", "tu", "te", "voces", "vos", "lhes", # "vocês" normalizado
    "meus", "minhas", "teu", "tua", "teus", "tuas", "nosso", "nossa", "nossos", "nossas",
    "dela", "delas", "esta", "estes", "estas", "aquele", "aquela", "aqueles", "aquelas",
    "isto", "aquilo", "estou", "estamos", "estavam", "estive", "esteve", "estivemos",
    "estiveram", "estivesse", "estivessemos", "estivessem", "estiver", "estivermos",
    "estiverem", "hei", "ha", "havemos", "hao", "houve", "houvemos", "houveram", "houvera", # "hão" normalizado
    "houveramos", "haja", "hajamos", "hajam", "houvesse", "houvessemos", "houvessem",
    "houver", "houvermos", "houverem", "houverei", "houvera", "houveremos", "houverao", # "houverá", "houverão" normalizados
    "houveria", "houveriamos", "houveriam", "sou", "somos", "sao", "era", "eramos", "eram", # "são", "éramos" normalizados
    "fui", "foi", "fomos", "foram", "fora", "foramos", "seja", "sejamos", "sejam", "fosse", # "fôramos" normalizado
    "fossemos", "fossem", "for", "formos", "forem", "serei", "sera", "seremos", "serao", # "será", "serão" normalizados
    "seria", "seriamos", "seriam", "tenho", "tem", "temos", "tem", "tinha", "tinhamos", # "têm", "tínhamos" normalizados
    "tinham", "tive", "teve", "tivemos", "tiveram", "tivera", "tiveramos", "tenha", # "tivéramos" normalizado
    "tenhamos", "tenham", "tivesse", "tivessemos", "tivessem", "tiver", "tivermos",
    "tiverem", "terei", "tera", "teremos", "terao", "teria", "teriamos", "teriam", # "terá", "terão" normalizados
    # Adicionando algumas palavras curtas que podem ser comuns em títulos mas não são stopwords clássicas
    "sobre", "onde", "como", "porque", "pra", "pro", "pras", "pros", "quer", "ver", "vai", "sao", "guia", "dicas"
])

def normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    if not isinstance(texto, str):
        return ""
    # Normalização para decompor acentos
    nfkd_form = unicodedata.normalize('NFKD', texto.lower())
    # Mantém apenas caracteres ASCII (remove acentos)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def identificar_palavras_frequentes_em_titulos(
    titulos: list[str],
    limiar_percentual: float = 0.3,
    min_titulos_para_analise: int = 5,
    min_palavra_len: int = 4
) -> list[str]:
    """
    Identifica palavras e frases comuns (excluindo stopwords) que aparecem em uma alta porcentagem de títulos.
    Args:
        titulos: Lista de strings, onde cada string é um título.
        limiar_percentual: Percentual de títulos em que uma palavra deve aparecer para ser considerada frequente.
        min_titulos_para_analise: Número mínimo de títulos válidos para realizar a análise.
        min_palavra_len: Comprimento mínimo da palavra (normalizada) para ser considerada.
    Returns:
        Lista de palavras e frases frequentes (normalizadas) a serem evitadas.
    """
    titulos_validos_normalizados = [
        normalizar_texto(str(t)) for t in titulos 
        if t and isinstance(t, str) and normalizar_texto(str(t)).strip() and normalizar_texto(str(t)).strip() != "sem titulo"
    ]

    if not titulos_validos_normalizados or len(titulos_validos_normalizados) < min_titulos_para_analise:
        logger.info(
            f"Número de títulos válidos ({len(titulos_validos_normalizados)}) é menor que "
            f"o mínimo para análise ({min_titulos_para_analise}). Nenhuma palavra será marcada como frequente."
        )
        return []

    # Contador para palavras individuais
    contador_palavras_em_titulos = Counter()
    # Contador para frases comuns (2-3 palavras)
    contador_frases_em_titulos = Counter()
    total_titulos_analisados = len(titulos_validos_normalizados)

    for titulo_norm in titulos_validos_normalizados:
        # Análise de palavras individuais
        palavras = re.findall(r'\b\w+\b', titulo_norm)
        palavras_unicas_no_titulo = set()
        for palavra_norm in palavras:
            if palavra_norm not in PORTUGUESE_STOPWORDS and len(palavra_norm) >= min_palavra_len:
                palavras_unicas_no_titulo.add(palavra_norm)
        
        for palavra_unica_norm in palavras_unicas_no_titulo:
            contador_palavras_em_titulos[palavra_unica_norm] += 1
        
        # Análise de frases comuns (2-3 palavras)
        palavras_com_stop = [w for w in re.findall(r'\b\w+\b', titulo_norm)]
        if len(palavras_com_stop) >= 2:
            # Bigramas (sequências de 2 palavras)
            for i in range(len(palavras_com_stop) - 1):
                bigrama = f"{palavras_com_stop[i]} {palavras_com_stop[i+1]}"
                contador_frases_em_titulos[bigrama] += 1
            
            # Trigramas (sequências de 3 palavras)
            if len(palavras_com_stop) >= 3:
                for i in range(len(palavras_com_stop) - 2):
                    trigrama = f"{palavras_com_stop[i]} {palavras_com_stop[i+1]} {palavras_com_stop[i+2]}"
                    contador_frases_em_titulos[trigrama] += 1
            
    palavras_frequentes = []
    frases_frequentes = []
    
    if not contador_palavras_em_titulos and not contador_frases_em_titulos:
        logger.info("Nenhuma palavra ou frase candidata encontrada após filtragem.")
        return []

    logger.debug(f"Contagem de palavras nos títulos (top 10): {contador_palavras_em_titulos.most_common(10)}")
    logger.debug(f"Contagem de frases nos títulos (top 10): {contador_frases_em_titulos.most_common(10)}")

    # Palavras individuais frequentes
    for palavra_norm, contagem in contador_palavras_em_titulos.items():
        percentual_ocorrencia = contagem / total_titulos_analisados
        if percentual_ocorrencia > limiar_percentual and len(palavra_norm) >= min_palavra_len:
            palavras_frequentes.append(palavra_norm)
    
    # Frases frequentes (excluindo as que são stopwords completas)
    for frase_norm, contagem in contador_frases_em_titulos.items():
        percentual_ocorrencia = contagem / total_titulos_analisados
        frase_palavras = frase_norm.split()
        
        # Verifica se a frase não é composta apenas de stopwords
        if not all(p in PORTUGUESE_STOPWORDS for p in frase_palavras):
            # Se contiver pelo menos uma palavra não-stopword com comprimento mínimo
            if any(len(p) >= min_palavra_len and p not in PORTUGUESE_STOPWORDS for p in frase_palavras):
                if percentual_ocorrencia > limiar_percentual:
                    frases_frequentes.append(frase_norm)
            
    resultado_final = palavras_frequentes + frases_frequentes
            
    if resultado_final:
        logger.info(
            f"Padrões frequentes identificados (ocorrem em > {limiar_percentual*100:.0f}% de {total_titulos_analisados} títulos):"
        )
        if palavras_frequentes:
            logger.info(f"Palavras: {palavras_frequentes}")
        if frases_frequentes:
            logger.info(f"Frases: {frases_frequentes}")
    else:
        logger.info(
            f"Nenhuma palavra ou frase excedeu o limiar de frequência de {limiar_percentual*100:.0f}% nos {total_titulos_analisados} títulos analisados."
        )
        
    return resultado_final

def limpar_nome_arquivo(nome_arquivo: str) -> str:
    """
    Limpa uma string para ser usada como nome de arquivo, removendo caracteres inválidos
    e substituindo espaços. Utiliza a função normalizar_texto para remover acentos.
    """
    if not isinstance(nome_arquivo, str):
        logger.warning(f"Tentativa de limpar nome de arquivo não string: {type(nome_arquivo)}. Retornando fallback.")
        return "documento_sem_nome_valido"
    
    nome_normalizado = normalizar_texto(nome_arquivo) # Remove acentos e converte para minúsculas
    
    # Remove caracteres que não são alfanuméricos, espaço, ponto, hífen ou underscore
    nome_limpo = re.sub(r'[^a-z0-9\s._-]', '', nome_normalizado)
    
    # Substitui um ou mais espaços, hífens ou underscores por um único hífen
    nome_limpo = re.sub(r'[\s_-]+', '-', nome_limpo)
    
    # Remove hífens do início e do fim
    nome_limpo = nome_limpo.strip('-')
    
    # Garante que não seja apenas um ponto ou vazio
    if not nome_limpo or nome_limpo == '.':
        logger.warning(f"Nome de arquivo ficou vazio ou inválido após limpeza de '{nome_arquivo}'. Retornando fallback.")
        # Tenta usar uma parte do original se possível, ou um nome genérico
        fallback_match = re.search(r'[a-z0-9]+', normalizar_texto(nome_arquivo))
        if fallback_match:
            return fallback_match.group(0)[:50] # Pega a primeira sequência alfanumérica
        return "documento_gerado"
        
    # Limitar o comprimento (opcional, mas bom para alguns sistemas de arquivos)
    # max_len = 100
    # if len(nome_limpo) > max_len:
    #     nome_limpo = nome_limpo[:max_len].rsplit('-', 1)[0] # Tenta cortar em um hífen para não quebrar palavras
        
    return nome_limpo 

def extrair_titulos_por_ancora(df, coluna_titulo, coluna_ancora):
    """
    Agrupa títulos por palavra-âncora para detectar padrões repetitivos.
    
    Args:
        df: DataFrame com os dados
        coluna_titulo: Índice da coluna de títulos
        coluna_ancora: Índice da coluna de palavras-âncora
        
    Returns:
        Dicionário com palavras-âncora como chaves e listas de títulos como valores
    """
    logger = logging.getLogger('seo_linkbuilder.utils')
    
    if df.empty:
        logger.warning("DataFrame vazio em extrair_titulos_por_ancora.")
        return {}
    
    # Verifica se as colunas de título e âncora existem no DataFrame
    if coluna_titulo not in df.columns:
        logger.error(f"Coluna de título '{coluna_titulo}' não encontrada no DataFrame.")
        return {}
    if coluna_ancora not in df.columns:
        logger.error(f"Coluna de âncora '{coluna_ancora}' não encontrada no DataFrame.")
        return {}

    titulos_por_ancora = {}
    
    for idx, row in df.iterrows():
        if pd.isna(row[coluna_ancora]) or pd.isna(row[coluna_titulo]):
            continue
        
        ancora = str(row[coluna_ancora]).lower().strip()
        titulo = str(row[coluna_titulo]).strip()
        
        if not ancora or not titulo:
            continue
            
        if ancora not in titulos_por_ancora:
            titulos_por_ancora[ancora] = []
            
        titulos_por_ancora[ancora].append(titulo)
    
    # Log para depuração
    logger.info(f"Extração de títulos por âncora: {len(titulos_por_ancora)} âncoras encontradas")
    for ancora, titulos in titulos_por_ancora.items():
        if len(titulos) > 3:  # Mostra apenas âncoras com mais de 3 títulos para não sobrecarregar o log
            logger.info(f"Âncora '{ancora}' tem {len(titulos)} títulos")
    
    return titulos_por_ancora

def identificar_padroes_por_ancora(titulos_por_ancora):
    """
    Identifica padrões repetitivos em títulos para cada palavra-âncora.
    
    Args:
        titulos_por_ancora: Dicionário com palavras-âncora como chaves e listas de títulos como valores
        
    Returns:
        Dicionário com palavras-âncora como chaves e listas de padrões a evitar como valores
    """
    logger = logging.getLogger('seo_linkbuilder.utils')
    import re
    from collections import Counter
    
    padroes_por_ancora = {}
    
    for ancora, titulos in titulos_por_ancora.items():
        if len(titulos) < 3:  # Ignora âncoras com poucos títulos
            continue
            
        # Normaliza os títulos
        titulos_norm = [normalizar_texto(titulo.lower()) for titulo in titulos]
        
        # Detecta padrões de início comuns (2-3 primeiras palavras)
        inicios = []
        for titulo in titulos_norm:
            palavras = titulo.split()
            if len(palavras) >= 3:
                inicios.append(' '.join(palavras[:3]))
            elif len(palavras) >= 2:
                inicios.append(' '.join(palavras[:2]))
                
        # Conta frequência dos inícios
        contador_inicios = Counter(inicios)
        
        # Identifica inícios repetidos (mais de uma vez)
        padroes_repetidos = [inicio for inicio, count in contador_inicios.items() if count > 1]
        
        # Detecta frases completas repetidas (como "a evolução da experiência")
        frases_comuns = []
        for i in range(len(titulos_norm)):
            for j in range(i+1, len(titulos_norm)):
                # Encontra subsequências comuns de 3+ palavras
                palavras_titulo1 = titulos_norm[i].split()
                palavras_titulo2 = titulos_norm[j].split()
                
                for k in range(len(palavras_titulo1) - 2):
                    for l in range(len(palavras_titulo2) - 2):
                        if (k < len(palavras_titulo1) - 2 and 
                            l < len(palavras_titulo2) - 2 and
                            palavras_titulo1[k] == palavras_titulo2[l] and 
                            palavras_titulo1[k+1] == palavras_titulo2[l+1] and
                            palavras_titulo1[k+2] == palavras_titulo2[l+2]):
                            frase = ' '.join(palavras_titulo1[k:k+3])
                            if frase not in frases_comuns and len(frase.split()) >= 3:
                                frases_comuns.append(frase)
        
        # Junta todos os padrões detectados
        padroes = padroes_repetidos + frases_comuns
        
        # Remove duplicatas e mantém apenas padrões mais significativos
        padroes = list(set(padroes))
        
        # Adiciona ao dicionário se tiver padrões detectados
        if padroes:
            padroes_por_ancora[ancora] = padroes
            logger.info(f"Padrões repetitivos identificados para âncora '{ancora}': {padroes}")
    
    return padroes_por_ancora 