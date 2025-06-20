# Módulo para interagir com a API do Gemini
import os
import logging
import google.generativeai as genai
import re
import random
import time
from typing import Dict, Tuple, Optional, List
from unidecode import unidecode
from google.api_core import retry
from google.api_core.exceptions import ResourceExhausted
from Levenshtein import ratio
import sqlite3

from src.config import (
    GOOGLE_API_KEY, 
    GEMINI_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_TEMPERATURE,
    estimar_custo_gemini,
    GEMINI_PRECO_ENTRADA as GEMINI_INPUT_COST_PER_1K,
    GEMINI_PRECO_SAIDA as GEMINI_OUTPUT_COST_PER_1K
)
from src.utils import contar_tokens, substituir_links_markdown, normalizar_texto
from .db_handler import DBHandler

def qualquer_palavra_em_outra(palavras1, palavras2):
    """
    Verifica se qualquer palavra de palavras1 está em qualquer palavra de palavras2
    """
    for p1 in palavras1:
        for p2 in palavras2:
            if len(p1) > 3 and p1 in p2:  # Ignora palavras muito curtas
                return True
    return False

def verificar_conteudo_proibido(texto: str) -> str:
    """
    Verifica e substitui termos sensíveis no conteúdo gerado.
    
    Args:
        texto: O texto a ser verificado
        
    Returns:
        Texto com termos sensíveis substituídos por alternativas adequadas
    """
    # Mapeamento de termos sensíveis para alternativas
    termos_proibidos = {
        # Termos de ganho financeiro
        r'\bganhar dinheiro\b': 'ter uma experiência divertida',
        r'\blucrar\b': 'divertir-se',
        r'\blucrativo\b': 'empolgante',
        r'\blucros\b': 'momentos divertidos',
        r'\bganhos\b': 'resultados positivos',
        r'\bganhar\b': 'aproveitar',
        r'\brico\b': 'mais experiente',
        r'\briqueza\b': 'satisfação',
        r'\benriquecer\b': 'melhorar sua experiência',
        r'\bfique rico\b': 'divirta-se mais',
        r'\brentabilidade\b': 'diversão',
        r'\brentável\b': 'interessante',
        r'\bretorno\b': 'satisfação',
        
        # Garantias de sucesso
        r'\bgarantido\b': 'possível',
        r'\bgarantia\b': 'possibilidade',
        r'\bcerteza\b': 'chance',
        r'\binfalível\b': 'interessante',
        
        # Termos relacionados a dinheiro
        r'\bdinheiro fácil\b': 'diversão responsável',
        r'\bgrana\b': 'experiência',
        r'\bdinheiro real\b': 'jogo interativo',
        
        # Termos de apostas (novos)
        r'\bapostar tudo\b': 'jogar com responsabilidade',
        r'\bapostar alto\b': 'jogar com moderação',
        r'\bapostas altas\b': 'jogadas estratégicas',
        r'\bvício\b': 'hobby',
        r'\bviciado\b': 'entusiasta',
        
        # Termos discriminatórios (novos)
        r'\braciais\b': 'racionais',
        r'\bpreconceito\b': 'diferenças',
        r'\bdiscriminação\b': 'distinção',
        
        # Termos políticos (novos)
        r'\bpolítica\b': 'gestão',
        r'\bpolítico\b': 'administrador',
        r'\bpartido\b': 'grupo',
        r'\beleição\b': 'escolha',
        r'\bvotar\b': 'escolher',
        
        # Termos de violência (novos)
        r'\bviolência\b': 'desafio',
        r'\bbriga\b': 'competição',
        r'\bcrime\b': 'incidente',
        r'\btragédia\b': 'acontecimento',
        
        # Termos infantis (novos)
        r'\bcriança\b': 'pessoa',
        r'\binfantil\b': 'iniciante',
        r'\bmenor de idade\b': 'inexperiente',
        
        # Termos de investimento (novos)
        r'\binvestir\b': 'participar',
        r'\binvestimento\b': 'participação',
        r'\binvestidor\b': 'participante',
        r'\baplicar\b': 'utilizar',
        r'\baplicação\b': 'utilização'
    }
    
    texto_modificado = texto
    termos_substituidos = []
    
    for padrao, substituto in termos_proibidos.items():
        # Encontra todas as ocorrências do padrão
        ocorrencias = re.findall(padrao, texto_modificado, re.IGNORECASE)
        
        if ocorrencias:
            # Registra os termos encontrados
            termos_substituidos.extend(ocorrencias)
            # Substitui o termo (mantendo case-sensitivity quando possível)
            texto_modificado = re.sub(padrao, substituto, texto_modificado, flags=re.IGNORECASE)
    
    # Retorna o texto modificado e a lista de termos substituídos
    return texto_modificado, termos_substituidos

    

def extrair_instrucao_especial_jogo(palavra_ancora: str) -> str:
    """Gera instruções personalizadas de estilo para cada tema, garantindo conteúdo único e eficaz"""
    
    instrucoes_especiais = {
        # Temas de Entretenimento e Cultura Pop
        "filme": "Explore conexões com a cultura pop, críticas, curiosidades de bastidores e impacto cultural. Relacione com outros filmes do mesmo gênero ou diretor.",
        "série": "Analise elementos narrativos, desenvolvimento de personagens, teorias de fãs e comparações com outras séries populares.",
        "música": "Discuta influências musicais, história da música, análise de letras, impacto cultural e conexões com outros artistas.",
        "game": "Aborde mecânicas de jogo, desenvolvimento, comunidade de jogadores, competições e evolução dos videogames.",
        
        # Temas de Cassino (mantidos e adaptados)
        "aviator": "Destaque a mecânica única de timing e a experiência visual do jogo. Foque em como o jogo combina estratégia pessoal com decisões rápidas.",
        "blackjack": "Aborde o equilíbrio entre sorte e estratégia. Explique a mecânica básica e por que o jogo atrai tanto jogadores iniciantes quanto experientes.",
        "roleta": "Explique a elegância e simplicidade do jogo. Descreva os diferentes tipos de apostas possíveis e como a roleta mantém seu charme através dos séculos.",
        
        # Temas de Esporte e E-sports
        "futebol": "Analise táticas, estatísticas, histórico de partidas, rivalidades clássicas e momentos memoráveis do esporte.",
        "basquete": "Explore estratégias de jogo, evolução do esporte, recordes históricos e impacto cultural.",
        "e-sports": "Discuta cenário competitivo, times profissionais, estratégias de jogo e crescimento do setor.",
        
        # Temas de Tecnologia e Inovação
        "tecnologia": "Aborde inovações recentes, impacto na sociedade, tendências futuras e análise de produtos/serviços.",
        "smartphone": "Compare modelos, analise recursos, discuta tendências de mercado e impacto na comunicação moderna.",
        "inteligência artificial": "Explore aplicações práticas, avanços recentes, implicações éticas e futuro da tecnologia.",
        
        # Temas de Arte e Cultura
        "arte": "Discuta movimentos artísticos, técnicas, artistas influentes e impacto cultural.",
        "literatura": "Analise obras literárias, autores, gêneros e influência na cultura contemporânea.",
        "teatro": "Explore produções teatrais, história do teatro, técnicas de atuação e impacto cultural.",
        
        # Temas de Gastronomia
        "culinária": "Aborde receitas, técnicas de preparo, história dos pratos e influências culturais.",
        "restaurante": "Analise experiências gastronômicas, tendências culinárias e críticas gastronômicas.",
        
        # Temas de Viagem e Turismo
        "viagem": "Explore destinos, dicas de planejamento, experiências culturais e recomendações práticas.",
        "turismo": "Discuta pontos turísticos, cultura local, dicas de viagem e experiências únicas."
    }
    
    # Detecta palavras-chave no nome do jogo/tema
    palavra_ancora_lower = palavra_ancora.lower()
    for palavra_chave, instrucao in instrucoes_especiais.items():
        if palavra_chave.lower() in palavra_ancora_lower:
            return instrucao
    
    # Instruções baseadas em categorias gerais
    if any(termo in palavra_ancora_lower for termo in ["fortune", "lucky", "tiger", "gold", "gems", "dragon"]):
        return "Destaque a temática de fortuna e sorte. Explore aspectos culturais, simbolismo e elementos visuais."
    
    if any(termo in palavra_ancora_lower for termo in ["book", "dead", "egypt", "vikings", "aztec"]):
        return "Enfatize o tema histórico ou mitológico. Explore conexões com a cultura, história e lendas relacionadas."
    
    if any(termo in palavra_ancora_lower for termo in ["esporte", "sport", "campeonato", "copa"]):
        return "Analise aspectos esportivos, estatísticas, histórico de competições e momentos memoráveis."
    
    if any(termo in palavra_ancora_lower for termo in ["tech", "digital", "app", "software"]):
        return "Explore aspectos tecnológicos, inovações, tendências e impacto na sociedade moderna."
    
    # Instrução genérica para garantir originalidade
    return "Para este tema, destaque o que o torna verdadeiramente único. Explore aspectos culturais, históricos ou sociais relevantes. Considere tendências atuais e conexões com outros temas populares. O objetivo é encontrar uma perspectiva nova e interessante para o título e o artigo."


def verificar_e_corrigir_titulo(titulo: str, palavra_ancora: str, is_document_title: bool = False) -> Tuple[bool, str]:
    """
    Verifica e corrige o comprimento do título, garantindo que tenha entre 9-15 palavras,
    não ultrapasse 100 caracteres e não termine com reticências.
    Também remove o prefixo "Título:" e rejeita frases de continuação.
    
    Args:
        titulo: O título a ser verificado
        palavra_ancora: A palavra-âncora (opcional)
        is_document_title: Se True, aceita títulos menores para documentos já existentes
        
    Returns:
        Tupla (sucesso, titulo_corrigido)
        - sucesso: Boolean indicando se o título é válido 
        - titulo_corrigido: Título corrigido e formatado corretamente
    """
    logger = logging.getLogger('seo_linkbuilder.gemini')
    
    if not titulo:
        logger.warning("Título vazio recebido para verificação.")
        return False, "Sem título"
    
    # Remove espaços extras e quebras de linha
    titulo_processado = re.sub(r'\\s+', ' ', titulo).strip()

    # NOVA LIMPEZA: Remover todos os asteriscos de marcação markdown do título
    titulo_original = titulo_processado
    titulo_processado = re.sub(r"\*\*|\*", "", titulo_processado).strip()
    if titulo_processado != titulo_original:
        logger.info(f"Marcações Markdown (asteriscos) removidos do título: '{titulo_original}' -> '{titulo_processado}'")

    # Remover prefixos como "Título:", "**Título:**", "Tema:", etc.
    padrao_prefixo = r"^\s*(\*\*|\*|)(t[íi]tulo|tema|palavra-chave|palavra chave|conteudo|texto|conclusão)\s*[:：]?\s*"
    titulo_limpo_de_prefixo = re.sub(padrao_prefixo, "", titulo_processado, flags=re.IGNORECASE).strip()
    
    # Remove também quaisquer asteriscos ou # que possam ter sobrado no início
    titulo_limpo_de_prefixo = re.sub(r"^\s*(\*\*|\*|#)+\s*", "", titulo_limpo_de_prefixo).strip()

    if titulo_limpo_de_prefixo != titulo_processado:
        logger.info(f"Prefixo de título/tema/palavra-chave/marcador removido. Título antes: '{titulo_processado}'. Depois: '{titulo_limpo_de_prefixo}'")
        titulo_processado = titulo_limpo_de_prefixo
        if not titulo_processado:
            logger.warning("Título ficou vazio após remover prefixo e será rejeitado.")
            return False, "Sem título após limpeza"

    # NOVA LIMPEZA: Remover asteriscos/cerquilhas do final do título processado
    titulo_processado_antes_final_clean = titulo_processado
    titulo_processado = re.sub(r"\s*(\*\*|\*|#)+$", "", titulo_processado).strip()
    if titulo_processado != titulo_processado_antes_final_clean:
        logger.info(f"Caracteres de formatação removidos do final do título. Antes: '{titulo_processado_antes_final_clean}'. Depois: '{titulo_processado}'")
        if not titulo_processado:
            logger.warning("Título ficou vazio após remover formatação final e será rejeitado.")
            return False, "Sem título após limpeza final"

    # Lista de frases de continuação a serem rejeitadas no início do título
    frases_de_continuacao_proibidas = [
        "em resumo,", "concluindo,", "para concluir,",
        "em primeiro lugar,", "em segundo lugar,", "em terceiro lugar,", "em quarto lugar,", "em quinto lugar,",
        "além disso,", "portanto,", "no entanto,", "contudo,", "assim sendo,", "dessa forma,",
        "por conseguinte,", "em suma,", "finalmente,"
    ]
    titulo_lower_para_verificacao = titulo_processado.lower()
    for frase_proibida in frases_de_continuacao_proibidas:
        if titulo_lower_para_verificacao.startswith(frase_proibida):
            logger.warning(f"Título rejeitado por começar com frase de continuação proibida ('{frase_proibida}'): '{titulo_processado}'")
            return False, titulo_processado

    # Nova verificação: Rejeitar títulos que terminam de forma incompleta
    terminacoes_incompletas_proibidas = [
        " de", " a", " o", " com", " em", " por", " para", " que", 
        " é", " são", " foi", " era", " ser", " estar",
        " e", " ou", " mas", " nem", " pois",
        " se", " como", " quando", " onde",
        " sobre", " entre", " até", " sem", " sob",
        " um", " uma", " uns", " umas", "; é"
    ]
    
    # Também verifica se termina com ponto e vírgula simples
    if titulo_processado.endswith(";"):
        logger.warning(f"Título rejeitado por terminar com ponto e vírgula, sugerindo incompletude: '{titulo_processado}'")
        return False, titulo_processado

    titulo_lower_para_final = titulo_processado.lower()
    for term_proibido in terminacoes_incompletas_proibidas:
        if titulo_lower_para_final.endswith(term_proibido.strip()):
            if term_proibido == "; é" and titulo_lower_para_final.endswith("; é"):
                logger.warning(f"Título rejeitado por terminar com padrão proibido indicando incompletude ('{term_proibido}'): '{titulo_processado}'")
                return False, titulo_processado
            elif term_proibido != "; é" and titulo_lower_para_final.endswith(term_proibido):
                partes = titulo_processado.rsplit(None, 1)
                if len(partes) > 1 and partes[-1].lower() == term_proibido.strip():
                    logger.warning(f"Título rejeitado por terminar com palavra/frase que sugere incompletude ('{term_proibido.strip()}'): '{titulo_processado}'")
                    return False, titulo_processado
    
    # Verificar se a string é realmente o conteúdo completo em vez de um título
    if len(titulo_processado) > 250:
        palavras_titulo = titulo_processado.split()[:10]
        titulo_processado = " ".join(palavras_titulo)
        logger.warning(f"Texto muito longo detectado como título. Considerado como: {titulo_processado}")
        if not titulo_processado.endswith("..."):
            titulo_processado += "..."

    # 1. Verificar e remover reticências do final
    if titulo_processado.endswith("..."):
        titulo_processado = titulo_processado[:-3].strip()
        logger.info(f"Reticências removidas do final do título: '{titulo_processado}'")
        if not titulo_processado:
            logger.warning("Título ficou vazio após remover reticências.")
            return False, "Sem título após remover reticências"

    # Conta palavras
    palavras = titulo_processado.split()
    num_palavras = len(palavras)
    
    # Limita o comprimento em caracteres
    MAX_CARACTERES = 100
    if len(titulo_processado) > MAX_CARACTERES:
        logger.warning(f"Título excede {MAX_CARACTERES} caracteres: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        titulo_processado = titulo_processado[:MAX_CARACTERES].rsplit(' ', 1)[0]
        logger.info(f"Título reduzido para: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        palavras = titulo_processado.split()
        num_palavras = len(palavras)

    # Verifica se está dentro dos limites de palavras (9-15)
    if not (9 <= num_palavras <= 15) and not is_document_title:
        logger.warning(f"Título com número de palavras fora do intervalo (9-15): '{titulo_processado}' ({num_palavras} palavras).")
        if is_document_title:
            logger.info(f"Aceitando título existente com {num_palavras} palavras pois is_document_title=True")
            return True, titulo_processado
        return False, titulo_processado
        
    # Se todas as verificações passaram
    logger.info(f"Título validado e corrigido: '{titulo_processado}'")
    return True, titulo_processado


class GeminiHandler:
    def __init__(self, credentials_path: str = None):
        # Inicializa o logger
        self.logger = logging.getLogger('seo_linkbuilder.gemini')
        
        # Verifica se a chave da API está definida
        if not GOOGLE_API_KEY:
            erro_msg = "API key para o Gemini não encontrada. Verifique o arquivo .env"
            self.logger.error(erro_msg)
            raise ValueError(erro_msg)
        
        # Configura a API do Gemini
        try:
            genai.configure(api_key=GOOGLE_API_KEY)
            # Configuração da geração
            generation_config = {
                "temperature": GEMINI_TEMPERATURE,
                "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
            }
            self.temperatura_atual = GEMINI_TEMPERATURE
            # Adiciona configuração de safety settings (pode ser vazia)
            self.safety_settings = []
            
            self.model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=generation_config
            )
            self.logger.info(f"API do Gemini inicializada com sucesso. Modelo: {GEMINI_MODEL}")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar a API do Gemini: {e}")
            raise
        
        self.max_retries = 5
        self.base_delay = 2  # 60 segundos base delay
        self.max_delay = 5  # 5 minutos máximo delay
        self.db = DBHandler()
    
    def carregar_prompt_template(self, tipo: str = 'conteudo') -> str:
        """
        Carrega o template do prompt do arquivo correto conforme o tipo ('titulos' ou 'conteudo').
        """
        if tipo == 'titulos':
            path = "data/prompt_titulos.txt"
        else:
            path = "data/prompt_conteudo.txt"
        try:
            with open(path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
            self.logger.info(f"Template de prompt '{tipo}' carregado com sucesso")
            return prompt_template
        except Exception as e:
            self.logger.error(f"Erro ao carregar template de prompt '{tipo}': {e}")
            raise
    
    def _verificar_diversidade_titulos(self, prompt: str, dados: Dict[str, str]) -> str:
        """
        Verifica e garante a diversidade de títulos no prompt.
        
        Args:
            prompt: O prompt base
            dados: Dicionário com dados do prompt
            
        Returns:
            Prompt modificado com instruções de diversidade
        """
        # Categorias temáticas para diversificação
        categorias_tematicas = {
            "Entretenimento": ["filme", "série", "música", "game", "livro", "quadrinho"],
            "Cultura": ["arte", "literatura", "teatro", "dança", "cinema", "fotografia"],
            "Tecnologia": ["tech", "app", "software", "gadget", "smartphone", "computador"],
            "Esportes": ["futebol", "basquete", "vôlei", "tênis", "corrida", "natação"],
            "Gastronomia": ["comida", "culinária", "restaurante", "receita", "chef", "bebida"],
            "Viagem": ["turismo", "viagem", "destino", "hotel", "passeio", "aventura"],
            "Ciência": ["descoberta", "pesquisa", "inovação", "estudo", "experimento"],
            "História": ["época", "período", "civilização", "personagem", "evento"],
            "Lifestyle": ["moda", "beleza", "saúde", "bem-estar", "decoração"],
            "Cassino": ["slot", "roleta", "poker", "blackjack", "bingo", "apostas"]
        }
        
        # Identifica a categoria principal baseada na palavra-âncora
        palavra_ancora = dados.get('palavra_ancora', '').lower()
        categoria_principal = None
        for categoria, palavras_chave in categorias_tematicas.items():
            if any(palavra in palavra_ancora for palavra in palavras_chave):
                categoria_principal = categoria
                break
        
        # Se não encontrou categoria específica, usa uma aleatória
        if not categoria_principal:
            categoria_principal = random.choice(list(categorias_tematicas.keys()))
        
        # Gera instruções de diversificação baseadas na categoria
        instrucoes_diversidade = f"""
INSTRUÇÕES DE DIVERSIFICAÇÃO TEMÁTICA:

1. FOCO PRINCIPAL: {categoria_principal}
   - Explore diferentes aspectos dentro desta categoria
   - Evite repetir os mesmos ângulos ou abordagens
   
2. CONEXÕES CRIATIVAS:
   - Relacione o tema principal com outras categorias de forma natural
   - Crie conexões interessantes mas relevantes
   - Mantenha o equilíbrio entre o tema principal e as conexões
   
3. VARIAÇÃO DE ESTRUTURAS:
   - Alterne entre diferentes formatos de título
   - Use diferentes elementos de engajamento (perguntas, números, comparações)
   - Evite padrões repetitivos
   
4. ELEMENTOS DE ENGAJAMENTO:
   - Curiosidade: Desperte interesse sem clickbait
   - Valor: Ofereça benefício claro ao leitor
   - Originalidade: Traga ângulos únicos e frescos
   
5. EQUILÍBRIO DE TONS:
   - Informativo: Dados, fatos, análises
   - Entretenimento: Diversão, curiosidades
   - Prático: Dicas, guias, soluções
   
6. EVITAR:
   - Repetição de palavras-chave
   - Estruturas similares consecutivas
   - Temas muito distantes do foco principal
   - Clickbait ou sensacionalismo
"""
        
        return prompt + instrucoes_diversidade

    
    
    def _construir_prompt(self, dados: Dict[str, str], prompt_template: str) -> str:
        """
        Constrói o prompt para o Gemini usando o template e os dados da linha
        """
        try:
            # Sempre use o site como tema, nunca use um valor padrão
            site = dados.get('site', '')
            palavra_ancora = dados.get('palavra_ancora', '').lower()
            url_ancora = dados.get('url_ancora', '')
            
            # IMPORTANTE: Registra a palavra-âncora específica para este artigo
            self.logger.info(f"Construindo prompt para palavra-âncora específica: '{palavra_ancora}'")
            
            # Cria um tema baseado no site e na palavra-âncora
            if 'apostas' not in site.lower():
                tema = f"apostas em {site}" 
            else:
                tema = site
                
            # CORREÇÃO: Não use categorização automática para títulos
            # Isso evita que o sistema misture palavras-âncora diferentes
            
            # Instrução específica para garantir uso exclusivo da palavra-âncora
            instrucao_ancora_especifica = (
                "\n\nATENÇÃO SOBRE A PALAVRA-ÂNCORA:\n"
                f"1. A palavra-âncora para este artigo é: '{palavra_ancora}'\n"
                "2. NÃO mencione outras palavras-âncora ou jogos não relacionados\n"
                f"3. O conteúdo deve ser sobre '{palavra_ancora}' e temas relacionados\n"
                f"4. O título pode ou não mencionar '{palavra_ancora}', use se encaixar naturalmente\n"
                f"5. NUNCA substitua '{palavra_ancora}' por outro jogo ou tema similar\n"
            )
            
            # Preenche o template com os dados específicos desta linha
            prompt = prompt_template.replace("{{site}}", site)
            prompt = prompt.replace("{{palavra_ancora}}", palavra_ancora)
            prompt = prompt.replace("{palavra_ancora}", palavra_ancora)  # Adiciona suporte ao formato sem chaves duplas
            prompt = prompt.replace("{{url_ancora}}", url_ancora)
            
            # Se houver um título predefinido, use-o
            if 'titulo' in dados and dados['titulo'] and str(dados['titulo']).strip() != "Sem titulo":
                titulo_base = dados['titulo']
                self.logger.info(f"Usando título base fornecido: '{titulo_base}'")
                prompt = prompt.replace("{{titulo}}", titulo_base)
            else:
                # Caso contrário, deixe o modelo gerar um título específico para esta palavra-âncora
                prompt = prompt.replace("{{titulo}}", f"Artigo sobre {palavra_ancora}")
                
            # Adiciona a instrução específica para garantir exclusividade da palavra-âncora
            prompt += instrucao_ancora_especifica
            
            # Adiciona informação do link para personalização
            link_info = (
                f"\n\nEXTREMAMENTE IMPORTANTE: A palavra-âncora '{palavra_ancora}' DEVE aparecer de forma NATURAL no segundo OU terceiro parágrafo. "
                f"Não force o texto, use-a em uma frase que faça sentido e flua naturalmente.\n"
                f"Exemplos incorretos (forçados): 'Considerando {palavra_ancora}, podemos afirmar...', 'No que diz respeito à {palavra_ancora}...'\n"
                f"Exemplos corretos (naturais): 'Os jogadores que buscam {palavra_ancora} devem...', 'A experiência de {palavra_ancora} oferece muitas vantagens...'\n"
                f"\nIMPORTANTE: NUNCA coloque a palavra-âncora no primeiro parágrafo ou depois do terceiro parágrafo!"
            )
            
            # Adiciona alerta sobre termos proibidos
            termos_proibidos_alerta = (
                "\n\nIMPORTANTE: Nunca use termos como 'ganhar', 'lucrar', 'ganhos', 'dinheiro fácil' ou "
                "qualquer linguagem que sugira garantia de resultados financeiros. Mantenha o foco em diversão, "
                "entretenimento, estratégia e experiência."
            )
            
            prompt += link_info + termos_proibidos_alerta
            
            return prompt
            
        except Exception as e:
            self.logger.error(f"Erro ao construir prompt: {e}")
            raise

    def _calcular_similaridade_titulos(self, titulo1: str, titulo2: str) -> float:
        """
        Calcula a similaridade entre dois títulos usando uma combinação de métricas.
        Retorna um valor entre 0 (completamente diferentes) e 1 (muito similares).
        """
        # Normaliza os títulos
        titulo1_norm = normalizar_texto(titulo1.lower())
        titulo2_norm = normalizar_texto(titulo2.lower())
        
        # Calcula similaridade de palavras (Levenshtein)
        similaridade_palavras = self._calcular_similaridade_palavras(titulo1_norm, titulo2_norm)
        
        # Calcula similaridade de estrutura
        estrutura_similar = self._verificar_estrutura_similar(titulo1_norm, titulo2_norm)
        
        # Calcula similaridade de temas
        temas_similares = self._verificar_temas_similares(titulo1_norm, titulo2_norm)
        
        # Pesos para cada tipo de similaridade
        peso_palavras = 0.4
        peso_estrutura = 0.3
        peso_temas = 0.3
        
        # Calcula similaridade final ponderada
        similaridade_final = (
            similaridade_palavras * peso_palavras +
            float(estrutura_similar) * peso_estrutura +
            float(temas_similares) * peso_temas
        )
        
        return similaridade_final

    def _verificar_temas_similares(self, titulo1: str, titulo2: str) -> bool:
        """
        Verifica se dois títulos compartilham temas similares.
        """
        # Palavras-chave por categoria temática
        temas = {
            'cinema': {'filme', 'série', 'netflix', 'cinema', 'hollywood', 'diretor', 'ator'},
            'música': {'música', 'cantor', 'banda', 'show', 'festival', 'spotify'},
            'games': {'game', 'jogo', 'console', 'playstation', 'xbox', 'nintendo'},
            'tech': {'tecnologia', 'app', 'smartphone', 'gadget', 'internet', 'digital'},
            'lifestyle': {'vida', 'rotina', 'hábito', 'dica', 'produtividade'},
            'cultura': {'arte', 'cultura', 'história', 'museu', 'teatro'},
        }
        
        # Identifica temas presentes em cada título
        temas_titulo1 = set()
        temas_titulo2 = set()
        
        for tema, palavras in temas.items():
            if any(palavra in titulo1 for palavra in palavras):
                temas_titulo1.add(tema)
            if any(palavra in titulo2 for palavra in palavras):
                temas_titulo2.add(tema)
        
        # Calcula interseção de temas
        temas_comuns = temas_titulo1.intersection(temas_titulo2)
        
        # Retorna True se compartilham mais de um tema
        return len(temas_comuns) > 1

    def verificar_titulo_gerado(self, titulo: str, palavra_ancora: str, palavras_a_evitar: list, titulos_existentes: list = None) -> bool:
        """
        Verifica se um título gerado é válido segundo critérios estabelecidos.
        
        Args:
            titulo: O título a ser verificado
            palavra_ancora: A palavra-âncora que deve estar presente no título
            palavras_a_evitar: Lista de palavras que não devem aparecer no título
            titulos_existentes: Lista opcional de títulos já existentes para verificar duplicidade
            
        Returns:
            Boolean indicando se o título é válido
        """
        logger = logging.getLogger('seo_linkbuilder.gemini')
        
        # Verifica se o título está vazio
        if not titulo or len(titulo.strip()) == 0:
            logger.warning(f"Título vazio rejeitado")
            return False
            
        # Normaliza o título e a palavra-âncora para comparação
        titulo_norm = normalizar_texto(titulo.lower())
        palavra_ancora_norm = normalizar_texto(palavra_ancora.lower())
        
        # Verifica se a palavra-âncora está presente
        if palavra_ancora_norm not in titulo_norm:
            logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no título: '{titulo}'. O título será rejeitado.")
            return False
            
        # Verifica palavras a evitar
        for palavra in palavras_a_evitar:
            if normalizar_texto(palavra.lower()) in titulo_norm:
                logger.warning(f"Palavra proibida '{palavra}' encontrada no título: '{titulo}'. O título será rejeitado.")
                return False
                
        # Verifica similaridade com títulos existentes
        if titulos_existentes:
            for titulo_existente in titulos_existentes:
                similaridade = self._calcular_similaridade_titulos(titulo, titulo_existente)
                if similaridade > 0.6:  # Limite de similaridade
                    logger.warning(f"Título muito similar a um existente (similaridade: {similaridade:.2f}). Rejeitado.")
                    return False
        
        return True

    def verificar_conteudo_gerado(self, conteudo: str, palavra_ancora: str) -> Tuple[bool, str]:
        """
        Verifica se o conteúdo gerado é válido e atende aos critérios estabelecidos.
        
        Args:
            conteudo: O conteúdo a ser verificado
            palavra_ancora: A palavra-âncora que deve estar presente no conteúdo
            
        Returns:
            Tupla (sucesso, mensagem)
            - sucesso: Boolean indicando se o conteúdo é válido
            - mensagem: Mensagem de erro ou sucesso
        """
        if not conteudo:
            return False, "Conteúdo vazio"
        
        # 1. Verifica presença da palavra-âncora
        if palavra_ancora.lower() not in conteudo.lower():
            return False, f"Palavra-âncora '{palavra_ancora}' não encontrada no conteúdo"
        
        # 2. Verifica número de parágrafos
        paragrafos = [p for p in conteudo.split('\n\n') if p.strip()]
        if len(paragrafos) < 8:
            return False, f"Conteúdo tem apenas {len(paragrafos)} parágrafos (mínimo 8)"
        
        # 3. Verifica número de palavras
        palavras = conteudo.split()
        if len(palavras) < 400:
            return False, f"Conteúdo tem apenas {len(palavras)} palavras (mínimo 400)"
        
        # 4. Verifica presença de subtítulos
        if not re.search(r'##\s+.+', conteudo):
            return False, "Conteúdo não contém subtítulos (H2)"
        
        # 5. Verifica presença de listas
        if not re.search(r'[-*]\s+.+', conteudo):
            return False, "Conteúdo não contém listas com marcadores"
        
        # 6. Verifica posição da palavra-âncora
        paragrafos_iniciais = '\n\n'.join(paragrafos[:3])
        if palavra_ancora.lower() not in paragrafos_iniciais.lower():
            return False, f"Palavra-âncora '{palavra_ancora}' não encontrada nos 3 primeiros parágrafos"
        
        # 7. Verifica comprimento dos parágrafos
        paragrafos_longo = [p for p in paragrafos if len(p.split()) > 6]
        if len(paragrafos_longo) > len(paragrafos) * 0.3:  # Mais de 30% dos parágrafos são longos
            return False, "Muitos parágrafos longos detectados"
        
        return True, "Conteúdo válido"

    def gerar_conteudo(self, dados: Dict[str, str], instrucao_adicional: str = None, titulos_existentes: list = None) -> Tuple[str, Dict[str, float], Optional[Dict]]:
        """
        Gera conteúdo usando a API do Gemini.
        
        Args:
            dados: Dicionário com os dados da linha da planilha
            instrucao_adicional: Texto opcional a ser adicionado ao prompt para personalizar a geração
            titulos_existentes: Lista de títulos já existentes para evitar repetição.
        
        Returns:
            Tupla (conteudo_gerado, metricas, info_link)
            onde metricas é um dict com 'tokens_entrada', 'tokens_saida', 'custo_estimado'
        """
        try:
            # Carrega o template do prompt
            prompt_template = self.carregar_prompt_template()
            self.logger.info("Template de prompt carregado")
            
            # Constrói o prompt
            prompt = self._construir_prompt(dados, prompt_template)
            
            # Adiciona instrução adicional ao prompt, se fornecida
            palavras_a_evitar = []
            if instrucao_adicional:
                prompt += instrucao_adicional
                self.logger.info(f"Instrução adicional adicionada ao prompt: {instrucao_adicional}")
                
                # Extrai palavras a evitar do instrucao_adicional para validação posterior
                if "EVITE RIGOROSAMENTE o uso das seguintes PALAVRAS" in instrucao_adicional:
                    match = re.search(r"PALAVRAS.*?: (.*?)\.", instrucao_adicional)
                    if match:
                        palavras_texto = match.group(1)
                        palavras_a_evitar.extend([p.strip().strip("'") for p in palavras_texto.split(",")])
                
                if "NUNCA use os seguintes PADRÕES ou SEQUÊNCIAS DE PALAVRAS" in instrucao_adicional:
                    match = re.search(r"SEQUÊNCIAS DE PALAVRAS: (.*?)\.", instrucao_adicional)
                    if match:
                        frases_texto = match.group(1)
                        palavras_a_evitar.extend([p.strip().strip("'") for p in frases_texto.split(",")])
            
            # Armazena temperatura original e ajusta para mais aleatoriedade
            temperatura_original = self.temperatura_atual
            nova_temperatura = min(0.9, temperatura_original + 0.1 * (hash(dados.get('site', '')) % 5))
            self.temperatura_atual = nova_temperatura
            
            # Conta tokens de entrada para estimativa de custo
            tokens_entrada = contar_tokens(prompt)
            self.logger.info(f"Prompt construído com {tokens_entrada} tokens estimados")
            
            # Log das entidades importantes no prompt
            palavra_ancora = dados.get('palavra_ancora', '')
            self.logger.info(f"Palavra-âncora que DEVE ser inserida naturalmente: '{palavra_ancora}'")
            self.logger.info(f"Título: '{dados.get('titulo', 'Será gerado automaticamente')}'")
            if titulos_existentes:
                self.logger.info(f"Títulos existentes fornecidos para verificação: {len(titulos_existentes)} títulos.")
            
            # Cria configuração de geração com a nova temperatura
            generation_config = {
                "temperature": self.temperatura_atual,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
            }
            
            # Variáveis para métricas
            tokens_saida = 0
            custo_estimado = 0
            tentativas = 0
            max_tentativas = 3
            conteudo_gerado = ""
            
            # Loop de tentativas para gerar conteúdo válido
            while tentativas < max_tentativas:
                tentativas += 1
                self.logger.info(f"Tentativa {tentativas} de geração de conteúdo")
                
                # Faz a requisição à API do Gemini (removido safety_settings)
                resposta = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                # Extrai o conteúdo da resposta
                conteudo_gerado = resposta.text
                
                # Conta tokens de saída para estimativa de custo
                tokens_saida = contar_tokens(conteudo_gerado)
                
                # Calcula custo estimado
                custo_estimado = (tokens_entrada * GEMINI_INPUT_COST_PER_1K / 1000) + (tokens_saida * GEMINI_OUTPUT_COST_PER_1K / 1000)
                
                # Verifica se o título está adequado
                linhas = conteudo_gerado.strip().split('\n')
                titulo_gerado = linhas[0].strip() if linhas else "Sem título"
                
                # Aplica verificação e correção de comprimento e palavra-âncora no título
                # A palavra_ancora é crucial aqui
                sucesso, titulo_corrigido = verificar_e_corrigir_titulo(titulo_gerado, palavra_ancora)
                
                # Se o título foi corrigido, substitui no conteúdo
                # Se for None, significa que é inválido e precisa regenerar.
                if sucesso:
                    self.logger.info(f"Título gerado é aceitável: '{titulo_corrigido}'")
                    break # Sai do loop de tentativas
                else:
                    self.logger.warning(f"Título '{titulo_gerado}' invalidado por verificar_e_corrigir_titulo. Tentando novamente.")

                # Título contém padrões proibidos ou é inválido, tenta novamente com temperatura mais alta
                self.temperatura_atual = min(0.95, self.temperatura_atual + 0.1)
                generation_config["temperature"] = self.temperatura_atual
                self.logger.info(f"Aumentando temperatura para {self.temperatura_atual} e tentando novamente")
                # INSTRUÇÃO AGRESSIVA para evitar repetição
                instrucao_adicional = "\n\nATENÇÃO: Os títulos anteriores foram rejeitados por serem repetidos ou pouco criativos. GERE UM TÍTULO TOTALMENTE DIFERENTE DE TUDO QUE JÁ FOI USADO PARA ESTA PALAVRA-ÂNCORA. NÃO USE NÚMEROS, NÃO USE PADRÕES JÁ VISTOS, INOVE!"
                prompt += instrucao_adicional
            
            # Restaura a temperatura original para próximas chamadas
            self.temperatura_atual = temperatura_original
            
            # 'conteudo_gerado' é o texto completo da última tentativa da API (ou da primeira bem-sucedida)
            # 'titulo_corrigido' é o título dessa mesma tentativa, após passar por verificar_e_corrigir_titulo no loop

            # Extrai o corpo do conteúdo gerado, removendo o título original (que poderia estar em qualquer formato)
            linhas_conteudo_original = conteudo_gerado.strip().split('\n')
            corpo_do_texto = ""
            if linhas_conteudo_original:
                primeira_linha_original = linhas_conteudo_original[0].strip()
                # Remove marcadores H1/H2/H3 etc. da primeira linha original para evitar duplicação ao reconstruir o corpo
                primeira_linha_sem_h = re.sub(r"^#+\s*", "", primeira_linha_original).strip()
                
                # Compara o título corrigido (sem marcadores) com a primeira linha original (sem marcadores)
                # Se forem iguais, o corpo começa da segunda linha. Senão, a primeira linha já é parte do corpo.
                if normalizar_texto(titulo_corrigido.lower()) == normalizar_texto(primeira_linha_sem_h.lower()):
                    corpo_do_texto = "\n".join(linhas_conteudo_original[1:]).strip()
                    self.logger.info("Título original encontrado na primeira linha e removido para reconstrução do corpo.")
                else:
                    # Se o título corrigido não bate com a primeira linha, considera a primeira linha já é parte do corpo
                    # Isso pode acontecer se o título foi extraído de um H2 ou H3, ou se era um parágrafo.
                    corpo_do_texto = "\n".join(linhas_conteudo_original).strip()
                    self.logger.info("Primeira linha original não corresponde ao título corrigido, mantida como parte do corpo.")
            else:
                self.logger.warning("Conteúdo gerado pela API estava vazio, resultando em corpo vazio.")

            # Reconstrói o conteúdo com o título H1 formatado e o corpo
            conteudo_com_titulo_formatado = f"# {titulo_corrigido}\n\n{corpo_do_texto}"
            self.logger.info(f"Conteúdo formatado com título H1: '# {titulo_corrigido}'")
            
            # Insere a palavra-âncora no texto formatado
            # A variável 'palavra_ancora' já está definida no escopo de gerar_conteudo (vinda de 'dados')
            conteudo_processado, info_link = substituir_links_markdown(
                conteudo_com_titulo_formatado, 
                palavra_ancora, 
                dados.get('url_ancora', '')
            )
            
            # Monta métricas para logging e custos
            # tokens_entrada e custo_estimado são da última tentativa bem sucedida ou da última tentativa falha.
            metricas = {
                'input_token_count': tokens_entrada, 
                'output_token_count': contar_tokens(conteudo_gerado), # Baseado no output bruto da API
                'cost_usd': custo_estimado,
                'tentativas': tentativas,
                'block_reason': resposta.prompt_feedback.block_reason if resposta.prompt_feedback else None,
                'block_reason_message': resposta.prompt_feedback.block_reason_message if resposta.prompt_feedback else None
            }
            
            # Logs sobre o processamento
            self.logger.info(f"Conteúdo gerado com {metricas['output_token_count']} tokens de saída (baseado na resposta da API)")
            self.logger.info(f"Custo estimado: ${metricas['cost_usd']:.6f} USD")
            
            if info_link:
                self.logger.info(f"Palavra-âncora '{palavra_ancora}' inserida no parágrafo {info_link['paragrafo']}")
            else:
                self.logger.warning(f"Não foi possível inserir a palavra-âncora '{palavra_ancora}' no texto")
            
            return conteudo_processado, metricas, info_link
        
        except Exception as e:
            self.logger.error(f"Erro ao gerar conteúdo com o Gemini: {e}")
            self.logger.exception("Detalhes do erro:")
            raise

    def gerar_titulos(self, dados: Dict[str, str], quantidade: int = 1) -> List[str]:
        """
        Gera apenas títulos para o conteúdo, sem gerar o corpo do texto.
        Args:
            dados: Dicionário com os dados necessários (palavra_ancora, etc)
            quantidade: Quantidade de títulos a serem gerados
        Returns:
            Lista de títulos gerados
        """
        self.logger.info(f"Gerando {quantidade} título(s) para palavra-âncora: {dados.get('palavra_ancora')}")

        # Carrega o template de prompt para títulos
        prompt_template = self.carregar_prompt_template('titulos')
        palavra_ancora = dados.get('palavra_ancora', '')

        # Constrói o prompt específico para geração de títulos
        prompt = self._construir_prompt(dados, prompt_template)

        # Adiciona instrução para gerar múltiplos títulos se necessário, forçando diversidade
        if quantidade > 1:
            prompt += f"""
\n\nGere {quantidade} títulos únicos e criativos para o tema '{palavra_ancora}'. Cada título deve:
- Usar uma estrutura diferente (ex: pergunta provocativa, frase de efeito, metáfora, afirmação ousada, etc.)
- NÃO repetir padrões comuns como 'Erros Críticos', 'Dicas Essenciais', 'Guia Completo', etc.
- Ser original, instigante e fugir do óbvio.
- A palavra-âncora '{palavra_ancora}' pode ser usada se encaixar naturalmente, mas não é obrigatória.

Exemplos de estruturas:
1. Pergunta provocativa: "Que verdade sobre entretenimento online iniciantes descobrem tarde demais?"
2. Frase de efeito: "Convertendo Simples Palpites em Decisões Calculadas"
3. Metáfora: "Entendendo o Jogo: Menos Sorte, Mais Estratégia"
4. Afirmação ousada: "Quase Tudo Que Você Sabe Sobre Jogos Online Pode Estar Errado."
"""

        # Aumenta levemente a temperatura para títulos
        temp_titulos = min(1.0, GEMINI_TEMPERATURE + 0.15)
        generation_config = {
            "temperature": temp_titulos,
            "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
        }

        # Gera os títulos
        response = self._make_api_call(self.model.generate_content, prompt, generation_config=generation_config)

        if not response or not response.text:
            self.logger.error("Falha ao gerar títulos: resposta vazia da API")
            return []

        # Processa a resposta para extrair os títulos
        titulos = []
        titulos_existentes = set()
        for linha in response.text.split('\n'):
            titulo = linha.strip()
            if titulo and not titulo.startswith(('#', '*', '-', '1.', '2.', '3.')):
                # Verifica se o título é válido
                sucesso, titulo_corrigido = verificar_e_corrigir_titulo(
                    titulo, 
                    palavra_ancora,
                    is_document_title=False
                )
                # Rejeita títulos muito similares aos já aceitos
                if sucesso:
                    titulo_norm = normalizar_texto(titulo_corrigido.lower())
                    if any(self._calcular_similaridade_titulos(titulo_norm, normalizar_texto(t.lower())) > 0.7 for t in titulos_existentes):
                        self.logger.warning(f"Título rejeitado por ser muito similar a outro já aceito: '{titulo_corrigido}'")
                        continue
                    titulos.append(titulo_corrigido)
                    titulos_existentes.add(titulo_corrigido)
                else:
                    self.logger.info(f"Título rejeitado por não passar validação: '{titulo}'")

        self.logger.info(f"Títulos gerados com sucesso: {len(titulos)}")
        return titulos

    def gerar_conteudo_por_titulo(self, dados: Dict[str, str], titulo: str) -> Tuple[str, Dict[str, float], Optional[Dict]]:
        """
        Gera conteúdo baseado em um título específico.
        
        Args:
            dados: Dicionário com os dados para geração
            titulo: Título específico para o conteúdo
            
        Returns:
            Tupla (conteudo, metricas, info_link)
        """
        self.logger.info(f"Gerando conteúdo para título: {titulo}")
        # Carrega o template de prompt para conteúdo
        prompt_template = self.carregar_prompt_template('conteudo')
        # Adiciona o título ao prompt
        prompt = self._construir_prompt(dados, prompt_template)
        prompt += f"\n\nUse o seguinte título como base para o conteúdo:\n{titulo}"
        # Conta tokens de entrada para estimativa de custo
        tokens_entrada = contar_tokens(prompt)
        # Gera o conteúdo
        response = self._make_api_call(self.model.generate_content, prompt)
        if not response or not response.text:
            self.logger.error("Falha ao gerar conteúdo: resposta vazia da API")
            return "", {}, None
        # Processa o conteúdo gerado
        conteudo = response.text.strip()
        tokens_saida = contar_tokens(conteudo)
        custo_estimado = (tokens_entrada * GEMINI_INPUT_COST_PER_1K / 1000) + (tokens_saida * GEMINI_OUTPUT_COST_PER_1K / 1000)
        # Calcula métricas completas
        metricas = {
            'input_token_count': tokens_entrada,
            'output_token_count': tokens_saida,
            'cost_usd': custo_estimado,
            'num_palavras': len(conteudo.split()),
            'num_caracteres': len(conteudo),
        }
        # Processa links
        conteudo_processado, info_link = substituir_links_markdown(
            conteudo,
            dados.get('palavra_ancora', ''),
            dados.get('url_ancora', '')
        )
        self.logger.info("Conteúdo gerado com sucesso")
        return conteudo_processado, metricas, info_link

    def calcular_metricas_conteudo(self, dados: Dict[str, str], titulo: str) -> Optional[Dict[str, float]]:
        """
        Calcula as métricas estimadas para um conteúdo sem gerá-lo.
        
        Args:
            dados: Dicionário com os dados para geração
            titulo: Título específico para o conteúdo
            
        Returns:
            Dicionário com as métricas estimadas ou None em caso de erro
        """
        logger = logging.getLogger('seo_linkbuilder.gemini')
        
        try:
            # Carrega o template do prompt
            prompt_template = self.carregar_prompt_template('conteudo')
            
            # Constrói o prompt
            prompt = self._construir_prompt(dados, prompt_template)
            
            # Calcula tokens de entrada
            input_tokens = contar_tokens(prompt)
            
            # Estima tokens de saída (baseado em experiências anteriores)
            estimated_output_tokens = 2000  # Estimativa média para um artigo
            
            # Calcula custo estimado
            input_cost = (input_tokens / 1000) * GEMINI_INPUT_COST_PER_1K
            output_cost = (estimated_output_tokens / 1000) * GEMINI_OUTPUT_COST_PER_1K
            total_cost = input_cost + output_cost
            
            # Estima número de palavras e caracteres
            estimated_words = estimated_output_tokens // 1.3  # Média de 1.3 tokens por palavra
            estimated_chars = estimated_words * 5  # Média de 5 caracteres por palavra
            
            return {
                'input_token_count': input_tokens,
                'output_token_count': estimated_output_tokens,
                'cost_usd': total_cost,
                'num_palavras': int(estimated_words),
                'num_caracteres': int(estimated_chars)
            }
            
        except Exception as e:
            logger.error(f"Erro ao calcular métricas do conteúdo: {e}")
            return None

    def _normalizar_flex(self, texto):
        return unidecode(texto.lower().strip())

    def _exponential_backoff(self, attempt: int) -> float:
        """Calcula o tempo de espera com backoff exponencial e jitter."""
        delay = min(self.base_delay * (2 ** attempt) + random.uniform(0, 1), 120)
        return delay

    def _make_api_call(self, func, *args, **kwargs):
        """Faz chamada à API com retry e backoff exponencial, tentando indefinidamente em caso de erro de cota."""
        attempt = 0
        while True:  # Tenta até conseguir
            try:
                return func(*args, **kwargs)
            except ResourceExhausted as e:
                attempt += 1
                # Extrai o tempo de espera sugerido pela API, se disponível, mas nunca ultrapassa 120 segundos
                wait_time = self._exponential_backoff(attempt)
                if hasattr(e, 'retry_delay') and e.retry_delay:
                    wait_time = min(120, e.retry_delay.seconds)
                self.logger.warning(f"Rate limit atingido (erro 429). Tentativa {attempt}. Aguardando {wait_time:.1f} segundos antes de tentar novamente...")
                time.sleep(wait_time)
            except Exception as e:
                raise

    def _calcular_similaridade_palavras(self, palavras1: str, palavras2: str) -> float:
        """
        Calcula a similaridade entre duas sequências de palavras usando o algoritmo de Levenshtein.
        """
        return ratio(palavras1.lower(), palavras2.lower())

    def _verificar_estrutura_similar(self, titulo1: str, titulo2: str) -> bool:
        """
        Verifica se dois títulos têm estrutura similar.
        """
        # Remove palavras comuns e muito curtas
        palavras_comuns = {'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'e', 'ou', 'mas', 'por', 'para', 'com', 'sem', 'em', 'no', 'na', 'nos', 'nas', 'de', 'do', 'da', 'dos', 'das'}
        
        # Extrai palavras significativas
        palavras1 = [p for p in titulo1.split() if len(p) > 3 and p not in palavras_comuns]
        palavras2 = [p for p in titulo2.split() if len(p) > 3 and p not in palavras_comuns]
        
        # Verifica se têm o mesmo número de palavras significativas
        if len(palavras1) != len(palavras2):
            return False
        
        # Verifica se as palavras estão na mesma ordem
        similaridade = sum(1 for p1, p2 in zip(palavras1, palavras2) if self._calcular_similaridade_palavras(p1, p2) > 0.8)
        return similaridade / len(palavras1) > 0.7

    def _extrair_tema_principal(self, titulo: str) -> str:
        """Extrai o tema principal de um título."""
        temas = {
            "Cinema": ["filme", "cinema", "diretor", "ator", "atriz", "oscar"],
            "Séries": ["série", "netflix", "temporada", "episódio", "hbo", "disney+"],
            "Games": ["game", "jogo", "playstation", "xbox", "nintendo", "steam"],
            "Tecnologia": ["tech", "smartphone", "app", "gadget", "android", "iphone"],
            "Música": ["música", "cantor", "banda", "álbum", "spotify", "show"],
            "Esportes": ["futebol", "basquete", "esporte", "atleta", "campeonato"],
            "Lifestyle": ["moda", "estilo", "tendência", "dicas", "lifestyle"],
            "Cultura Pop": ["pop", "viral", "meme", "influencer", "youtube"]
        }
        
        titulo_lower = titulo.lower()
        for tema, palavras_chave in temas.items():
            if any(palavra in titulo_lower for palavra in palavras_chave):
                return tema
        return "Geral"

    def _extrair_estrutura(self, titulo: str) -> str:
        """Extrai o padrão de estrutura de um título."""
        import re
        
        # Remove números específicos
        estrutura = re.sub(r'\d+', '#', titulo)
        # Remove palavras específicas mantendo estrutura
        estrutura = re.sub(r'\b\w+\b', 'PALAVRA', estrutura)
        return estrutura

    async def gerar_titulo(self, palavra_ancora: str, prompt: str) -> str:
        """Gera um título usando o modelo e aprende com sucessos anteriores."""
        tema_principal = self._extrair_tema_principal(palavra_ancora)
        
        # Busca padrões bem-sucedidos
        padroes_sucesso = self.db.get_successful_patterns(tema_principal)
        titulos_similares = self.db.get_similar_successful_titles(palavra_ancora, tema_principal)
        
        # Adiciona exemplos bem-sucedidos ao prompt
        if titulos_similares:
            prompt += "\n\nExemplos de títulos bem-sucedidos:\n"
            for titulo in titulos_similares:
                prompt += f"- {titulo['title']}\n"
        
        # Gera o título
        titulo = await super().gerar_titulo(palavra_ancora, prompt)
        
        # Armazena o novo título
        estrutura = self._extrair_estrutura(titulo)
        temas_secundarios = [tema for tema in self._extrair_temas_secundarios(titulo)]
        
        title_id = self.db.add_title(
            title=titulo,
            anchor_word=palavra_ancora,
            main_theme=tema_principal,
            structure_type=estrutura,
            themes=temas_secundarios
        )
        
        return titulo

    def _extrair_temas_secundarios(self, titulo: str) -> List[str]:
        """Extrai temas secundários de um título."""
        temas = []
        titulo_lower = titulo.lower()
        
        # Mapeia palavras-chave para temas
        mapeamento_temas = {
            "Entretenimento": ["diversão", "lazer", "hobby", "passatempo"],
            "Tecnologia": ["digital", "online", "virtual", "internet"],
            "Cultura": ["arte", "cultura", "história", "tradição"],
            "Lifestyle": ["vida", "estilo", "dia a dia", "rotina"],
            "Social": ["amigos", "família", "relacionamento", "pessoas"]
        }
        
        for tema, palavras in mapeamento_temas.items():
            if any(palavra in titulo_lower for palavra in palavras):
                temas.append(tema)
        
        return temas

    def atualizar_desempenho_titulo(self, titulo: str, performance_score: float, feedback_score: float = None):
        """Atualiza o desempenho de um título e aprende com seu sucesso."""
        try:
            # Encontra o ID do título no banco
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM titles WHERE title = ?", (titulo,))
                result = cursor.fetchone()
                
                if result:
                    title_id = result[0]
                    # Atualiza as métricas
                    self.db.update_title_performance(title_id, performance_score, feedback_score)
                    
                    # Se o título foi bem-sucedido, atualiza o contador de estruturas
                    if performance_score > 0.7 or (feedback_score and feedback_score > 0.7):
                        estrutura = self._extrair_estrutura(titulo)
                        tema = self._extrair_tema_principal(titulo)
                        self.db.update_structure_success(estrutura, tema)
                        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar desempenho: {e}")