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
        r'\bdinheiro real\b': 'jogo interativo'
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
    """Gera instruções personalizadas de estilo para cada jogo, garantindo conteúdo único e eficaz"""
    
    instrucoes_especiais = {
        # Crash games
        "aviator": "Destaque a mecânica única de timing e a experiência visual do jogo. Foque em como o jogo combina estratégia pessoal com decisões rápidas. Mencione a curva de voo e o aspecto visual distinto.",
        "spaceman": "Enfatize o tema espacial e o visual único. Descreva a experiência imersiva e como o jogo se destaca dos outros crash games com sua temática intergaláctica.",
        "crash": "Destaque o elemento de estratégia e timing. Explique como o jogo oferece uma experiência diferente dos slots tradicionais, com foco na tomada de decisões e controle.",
        
        # Slots populares
        "gates of olympus": "Foque na rica temática mitológica grega. Descreva como o jogo incorpora Zeus e outros elementos da mitologia em sua mecânica. Mencione os multiplicadores e o sistema de rodadas bônus. Explore ângulos como: a popularidade de temas míticos em slots, ou como a volatilidade do jogo se alinha com a natureza dos deuses.",
        "fortune rabbit": "Enfatize a temática asiática e os elementos culturais de sorte. Descreva os símbolos especiais e como eles se conectam com as tradições de fortuna. Mencione as mecânicas de bônus. Sugira títulos que explorem a simbologia da sorte ou o design visual do jogo.",
        "sweet bonanza": "Destaque o visual colorido e a temática de doces. Explique o sistema único de pagamentos em cluster em vez de linhas tradicionais. Mencione as rodadas bônus e multiplicadores. Incentive títulos que brinquem com a experiência sensorial ou a inovação da mecânica de cluster.",
        "lucky dragons": "Explore a mística dos dragões asiáticos neste slot. Além das mecânicas de bônus e visuais, sugira ângulos como: o simbolismo dos dragões na cultura dos jogos de sorte, comparativos com outros slots de temática similar, ou a experiência do jogador em busca da sorte do dragão.",
        
        # Jogos de mesa
        "blackjack": "Aborde o equilíbrio entre sorte e estratégia. Explique a mecânica básica e por que o jogo atrai tanto jogadores iniciantes quanto experientes. Mencione a importância das decisões estratégicas. Sugira análises sobre a psicologia do jogador de blackjack ou a evolução das estratégias.",
        "poker": "Destaque o elemento de habilidade e psicologia. Explique como o jogo se diferencia de outros jogos de cassino pelo componente estratégico. Mencione as variantes mais populares. Encoraje discussões sobre o poker como esporte mental ou a importância do bluff.",
        "roleta": "Explique a elegância e simplicidade do jogo. Descreva os diferentes tipos de apostas possíveis e como a roleta mantém seu charme através dos séculos. Mencione as diferenças entre as versões online e físicas, como dealers ao vivo e variedades exclusivas da web. Incentive ângulos como: a matemática por trás da roleta, ou o glamour associado ao jogo.",
        "bacbo": "Este jogo combina elementos do Bacará com dados. Explique essa fusão única e como ela atrai jogadores. Considere ângulos como: Bacbo é uma simplificação bem-vinda do Bacará? Como a adição de dados muda a dinâmica do jogo? A experiência é mais rápida ou tensa? Explore a popularidade crescente de jogos de cassino ao vivo com mecânicas inovadoras.",
        
        # Termos genéricos de apostas - NOVAS ADIÇÕES
        "casa de apostas": "Foque nos aspectos de confiança, segurança, variedade de mercados (esportes, cassino), qualidade do atendimento e experiência do usuário na plataforma. Ângulos possíveis: O que procurar em uma casa de apostas de excelência? Como a tecnologia está transformando as casas de apostas? Comparativos de funcionalidades.",
        "aposta online": "Aborde a conveniência, acessibilidade e a vasta gama de opções disponíveis nas apostas online. Pode incluir dicas para iniciantes, como entender odds, diferentes tipos de apostas (simples, múltiplas, sistemas) e a importância do jogo responsável no ambiente digital.",
        "aposta esportiva": "Explore a paixão pelos esportes combinada com a análise e estratégia. Destaque a importância de conhecer o esporte, os times/atletas, e como analisar estatísticas. Pode focar em mercados específicos (futebol, basquete, tênis, eSports) e estratégias como handicap, over/under, etc.",
        "site de apostas": "Similar a 'casa de apostas', mas com ênfase na interface digital. Explore a usabilidade da plataforma, design responsivo (mobile), facilidade de navegação, métodos de pagamento seguros e a integração de ferramentas de jogo responsável. O que faz um site de apostas ser intuitivo e seguro?",
        "bet": "Use este termo mais genérico para discutir o conceito de 'bet' (aposta) de forma mais ampla. Pode incluir a psicologia por trás das apostas, a evolução histórica, a importância da gestão de banca, e como o 'bet' se manifesta em diferentes culturas e contextos de entretenimento.",
        "roleta online": "Diferencie da roleta tradicional, destacando as vantagens do ambiente online: variedades do jogo (europeia, americana, francesa, multi-wheel), mesas com dealers ao vivo para uma experiência imersiva, bônus específicos para roleta online e a conveniência de jogar a qualquer hora e lugar.",
        "bet online": "Combine os conceitos de 'bet' e 'online'. Enfatize a transformação digital no setor de apostas, a facilidade de acesso, a diversidade de modalidades (esportes, cassino, crash games, etc.) disponíveis online e a importância de escolher plataformas regulamentadas e seguras para uma experiência de bet online positiva."
    }
    
    # Detecta palavras-chave no nome do jogo
    for palavra_chave, instrucao in instrucoes_especiais.items():
        if palavra_chave.lower() in palavra_ancora.lower():
            return instrucao
    
    # Instruções padrão baseadas em categorias de jogos
    if any(termo in palavra_ancora.lower() for termo in ["fortune", "lucky", "tiger", "gold", "gems", "dragon"]):
        return "Destaque a temática de fortuna e riqueza do jogo. Além de explicar símbolos e bônus, explore ângulos como: a psicologia da busca pela sorte nesses jogos, o design visual que evoca riqueza, ou um comparativo com outros jogos de temática similar."
    
    if any(termo in palavra_ancora.lower() for termo in ["book", "dead", "egypt", "vikings", "aztec"]):
        return "Enfatize o tema histórico ou mitológico. Além de explicar mecânicas, explore o apelo dessas narrativas nos jogos, como o jogo se compara a lendas reais, ou a experiência de 'aventura' que ele proporciona."
    
    if any(termo in palavra_ancora.lower() for termo in ["fruit", "candy", "sweet", "fish"]):
        return "Destaque o visual colorido e temático. Além das mecânicas, explore como o design influencia o humor do jogador, a nostalgia (no caso de frutas), ou a simplicidade divertida que esses temas oferecem."
    
    # Instrução genérica para garantir originalidade
    return "Para este jogo, destaque o que o torna verdadeiramente único. Vá além da simples descrição de mecânicas e visuais. Explore ângulos como: Qual é a experiência central que ele oferece ao jogador? Como ele se posiciona em relação a outros jogos do mesmo gênero? Existe algum aspecto cultural ou tendência que ele reflete? O objetivo é encontrar uma perspectiva nova e interessante para o título e o artigo."


def verificar_e_corrigir_titulo(titulo: str, palavra_ancora: str, is_document_title: bool = False) -> Tuple[bool, str]:
    """
    Verifica e corrige o comprimento do título, garantindo que tenha entre 9-15 palavras,
    não ultrapasse 100 caracteres, contenha a palavra-âncora e não termine com reticências.
    Também remove o prefixo "Título:" e rejeita frases de continuação.
    
    Args:
        titulo: O título a ser verificado
        palavra_ancora: A palavra-âncora que deve estar presente no título
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

    # Remover prefixos como "Título:", "**Título:**", "Tema:", etc. de forma flexível.
    # Esta regex remove espaços, markdown opcional (**, *), a palavra "título" ou "tema" (com ou sem acento),
    # e um dois-pontos opcional, tudo no início da string, case-insensitive.
    # A palavra "palavra-chave" ou "palavra chave" também foi adicionada aos prefixos a remover.
    padrao_prefixo = r"^\s*(\*\*|\*|)(t[íi]tulo|tema|palavra-chave|palavra chave|conteudo|texto|conclusão)\s*[:：]?\s*"
    titulo_limpo_de_prefixo = re.sub(padrao_prefixo, "", titulo_processado, flags=re.IGNORECASE).strip()
    
    # Remove também quaisquer asteriscos ou # que possam ter sobrado no início após a remoção do prefixo
    # ou que foram gerados incorretamente pelo modelo.
    titulo_limpo_de_prefixo = re.sub(r"^\s*(\*\*|\*|#)+\s*", "", titulo_limpo_de_prefixo).strip()

    if titulo_limpo_de_prefixo != titulo_processado:
        logger.info(f"Prefixo de título/tema/palavra-chave/marcador removido. Título antes: '{titulo_processado}'. Depois: '{titulo_limpo_de_prefixo}'")
        titulo_processado = titulo_limpo_de_prefixo
        if not titulo_processado: # Se o título ficou vazio após remover o prefixo
            logger.warning("Título ficou vazio após remover prefixo e será rejeitado.")
            return False, "Sem título após limpeza"

    # NOVA LIMPEZA: Remover asteriscos/cerquilhas do final do título processado
    titulo_processado_antes_final_clean = titulo_processado
    titulo_processado = re.sub(r"\s*(\*\*|\*|#)+$", "", titulo_processado).strip() # Regex para o final
    if titulo_processado != titulo_processado_antes_final_clean:
        logger.info(f"Caracteres de formatação removidos do final do título. Antes: '{titulo_processado_antes_final_clean}'. Depois: '{titulo_processado}'")
        if not titulo_processado: # Se ficou vazio após remover do final
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
        # Adicionar mais conforme necessário, sempre com espaço antes para pegar a palavra inteira no final.
        # "; é" é um caso específico.
    ]
    # Também verifica se termina com ponto e vírgula simples, o que pode indicar continuação
    if titulo_processado.endswith(";"):
        logger.warning(f"Título rejeitado por terminar com ponto e vírgula, sugerindo incompletude: '{titulo_processado}'")
        return False, titulo_processado

    titulo_lower_para_final = titulo_processado.lower()
    for term_proibido in terminacoes_incompletas_proibidas:
        if titulo_lower_para_final.endswith(term_proibido.strip()): # .strip() para o caso de "; é" 
            # Para casos como "; é", o .strip() assegura que estamos verificando o final correto.
            # Para os outros com espaço antes, o endswith continuará funcionando bem após o strip() no term_proibido
            if term_proibido == "; é" and titulo_lower_para_final.endswith("; é"):
                 logger.warning(f"Título rejeitado por terminar com padrão proibido indicando incompletude ('{term_proibido}'): '{titulo_processado}'")
                 return False, titulo_processado
            elif term_proibido != "; é" and titulo_lower_para_final.endswith(term_proibido): # Garante que não é um falso positivo com "; é"
                 # Verifica se a palavra antes da terminação não a torna válida (ex: "Guia Completo de A a Z")
                 # Esta é uma heurística e pode precisar de refinamento.
                 partes = titulo_processado.rsplit(None, 1) # Divide na última palavra
                 if len(partes) > 1 and partes[-1].lower() == term_proibido.strip():
                    logger.warning(f"Título rejeitado por terminar com palavra/frase que sugere incompletude ('{term_proibido.strip()}'): '{titulo_processado}'")
                    return False, titulo_processado
    
    # Verificar se a string é realmente o conteúdo completo em vez de um título
    if len(titulo_processado) > 250:  # Se é muito longo, provavelmente não é um título
        palavras_titulo = titulo_processado.split()[:10]
        titulo_processado = " ".join(palavras_titulo)
        logger.warning(f"Texto muito longo detectado como título. Considerado como: {titulo_processado}")
        # Adiciona reticências aqui porque é um truncamento de um texto maior, não um título finalizado com "..."
        if not titulo_processado.endswith("..."):
             titulo_processado += "..."


    # 1. Verificar e remover reticências do final
    if titulo_processado.endswith("..."):
        titulo_processado = titulo_processado[:-3].strip()
        logger.info(f"Reticências removidas do final do título: '{titulo_processado}'")
        if not titulo_processado: # Se o título ficou vazio após remover "..."
            logger.warning("Título ficou vazio após remover reticências.")
            return False, "Sem título após remover reticências"

    # 2. Verificar presença da palavra-âncora (case-insensitive)
    if palavra_ancora and palavra_ancora.strip() and palavra_ancora.lower() not in titulo_processado.lower():
        if not is_document_title:  # Só rejeitamos se for um novo título, não se estivermos corrigindo um existente
            logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no título: '{titulo_processado}'. O título será rejeitado.")
            return False, titulo_processado # Rejeita o título se a palavra-âncora não estiver presente
        else:
            logger.info(f"Palavra-âncora '{palavra_ancora}' não encontrada no título existente: '{titulo_processado}', mas não rejeitando por ser documento existente.")

    # Conta palavras
    palavras = titulo_processado.split()
    num_palavras = len(palavras)
    
    # Limita o comprimento em caracteres
    MAX_CARACTERES = 100
    if len(titulo_processado) > MAX_CARACTERES:
        logger.warning(f"Título excede {MAX_CARACTERES} caracteres: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        # Reduz o título para caber no limite de caracteres, tenta não cortar palavras-chave
        if palavra_ancora and palavra_ancora.strip() and palavra_ancora.lower() in titulo_processado.lower():
            # Tenta preservar a palavra_ancora ao truncar
            idx_ancora = titulo_processado.lower().find(palavra_ancora.lower())
            fim_ancora = idx_ancora + len(palavra_ancora)
            
            if fim_ancora > MAX_CARACTERES - 20 and len(titulo_processado) > MAX_CARACTERES : # Se a âncora está no final e estoura
                 # Trunca antes da âncora e tenta re-adicionar, se possível
                parte_antes = titulo_processado[:idx_ancora].rsplit(' ',1)[0] if idx_ancora >0 else ""
                novo_titulo_tentativa = f"{parte_antes} {palavra_ancora}"
                if len(novo_titulo_tentativa) <= MAX_CARACTERES :
                    titulo_processado = novo_titulo_tentativa.strip()
                else: # Se mesmo assim não cabe, usa o método padrão de truncamento
                    titulo_processado = titulo_processado[:MAX_CARACTERES].rsplit(' ', 1)[0]

            elif len(titulo_processado) > MAX_CARACTERES : # Ancora no inicio ou meio
                 titulo_processado = titulo_processado[:MAX_CARACTERES].rsplit(' ', 1)[0]
        else: # Se âncora não está ou não foi fornecida, trunca normalmente
            titulo_processado = titulo_processado[:MAX_CARACTERES].rsplit(' ', 1)[0]

        logger.info(f"Título reduzido para: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        palavras = titulo_processado.split() # Recalcula palavras
        num_palavras = len(palavras)

    # Verifica se está dentro dos limites de palavras (9-15)
    if not (9 <= num_palavras <= 15) and not is_document_title:
        logger.warning(f"Título com número de palavras fora do intervalo (9-15): '{titulo_processado}' ({num_palavras} palavras).")
        # Para títulos de documentos existentes, somos mais tolerantes
        if is_document_title:
            logger.info(f"Aceitando título existente com {num_palavras} palavras pois is_document_title=True")
            return True, titulo_processado
        # Títulos fora da contagem de palavras após ajustes são rejeitados para nova geração.
        # A lógica de expansão/redução anterior era muito propensa a criar títulos de baixa qualidade.
        # É melhor o Gemini tentar novamente com as restrições do prompt.
        return False, titulo_processado 
        
    # Se todas as verificações passaram
    logger.info(f"Título validado e corrigido: '{titulo_processado}'")
    return True, titulo_processado


class GeminiHandler:
    def __init__(self):
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
        Adiciona verificação específica para garantir que os títulos não sigam padrões repetitivos.
        
        Args:
            prompt: O prompt original
            dados: Dicionário com os dados para o prompt
        
        Returns:
            Prompt modificado com instruções adicionais anti-padrões
        """
        # Verifica se temos um titulo já definido
        if 'titulo' in dados and dados['titulo'] and dados['titulo'].strip():
            return prompt  # Se já tem título, não precisa modificar
        
        # Palavras e frases de início comuns que queremos evitar - CRÍTICO PARA DIVERSIDADE
        padroes_proibidos = [
            # Artigos definidos + substantivos comuns
            "a evolu", "a analis", "a histor", "a experienc", "a jornada", "a transformac", 
            "a fascinant", "a importanc", "a influenc", "o impacto", "o guia", "o manual",
            "o segredo", "o papel", "o poder", "o jeito", "o metodo", "a arte", "a magia",
            "a tecnica", "o jogo", "a estrateg", "a mecanic", "as vantagens", "as possibilidades",
            
            # Adjetivos iniciais comuns
            "fascinante", "incrivel", "surpreendente", "impressionante", "inacreditavel",
            "fundamental", "essencial", "crucial", "importante", "significativo", "inovador",
            "revolucionario", "tradicional", "classico", "moderno", "contemporaneo", "completo",
            "detalhado", "abrangente", "definitivo", "unico", "exclusivo", "especial",
            
            # Construções comuns
            "como dominar", "como jogar", "como aproveitar", "como utilizar", "como entender",
            "dicas para", "truques para", "segredos para", "estrategias para", "metodos para",
            "guia completo", "guia definitivo", "guia pratico", "guia essencial", "manual de",
            "tudo sobre", "tudo que", "tudo o que", "o que voce", "o que todo", "por que escolher",
            
            # Estruturas de listas
            "top", "melhores", "principais", "essenciais", "fundamentais", "cruciais", "basicas",
            
            # Padrões específicos identificados como repetitivos
            "uma analise", "uma abordagem", "uma visao", "uma perspectiva", "uma exploracao",
            "entendendo", "compreendendo", "descobrindo", "explorando", "desvendando", "revelando",
            "dominando", "aprendendo", "conhecendo", "desenvolvendo", "aprimorando", "maximizando"
        ]
        
        # Rotação obrigatória de estruturas (12 tipos diferentes)
        estruturas_rotativas = [
            # 1. PERGUNTA PROVOCATIVA
            "Por que {PALAVRA_ANCORA} continua fascinando jogadores mesmo após anos de lançamento?",
            "O que torna {PALAVRA_ANCORA} tão singular no universo dos jogos de cassino online?",
            "Onde encontrar as informações mais precisas sobre estratégias em {PALAVRA_ANCORA}?",
            "Qual o segredo por trás do design imersivo que caracteriza {PALAVRA_ANCORA}?",
            
            # 2. DADOS NUMÉRICOS
            "5 fatores que contribuem para a popularidade crescente de {PALAVRA_ANCORA} entre brasileiros",
            "7 conceitos essenciais para compreender a matemática por trás de {PALAVRA_ANCORA}",
            "3 razões pelas quais {PALAVRA_ANCORA} atrai tanto jogadores iniciantes quanto veteranos",
            "10 curiosidades pouco conhecidas que explicam o fenômeno {PALAVRA_ANCORA} na atualidade",
            
            # 3. CONTRASTE/OPOSIÇÃO
            "Entre sorte e estratégia: {PALAVRA_ANCORA} analisado sob perspectivas complementares",
            "Mito versus realidade: o que jogadores precisam saber sobre {PALAVRA_ANCORA}",
            "Tradição e inovação: como {PALAVRA_ANCORA} equilibra elementos clássicos e modernos",
            "Simplicidade aparente, complexidade real: desvendando as camadas de {PALAVRA_ANCORA}",
            
            # 4. NARRATIVA HISTÓRICA
            "Das mesas europeias para o mundo digital: traçando a evolução de {PALAVRA_ANCORA}",
            "Do nicho à popularidade global: a trajetória surpreendente de {PALAVRA_ANCORA}",
            "Origens e transformações: como {PALAVRA_ANCORA} se adaptou às novas gerações",
            "Momentos decisivos que definiram o desenvolvimento e posicionamento de {PALAVRA_ANCORA}",
            
            # 5. ANÁLISE TÉCNICA
            "Mecânicas fundamentais que fazem de {PALAVRA_ANCORA} um exemplo de design equilibrado",
            "Elementos estruturais que explicam o engajamento duradouro com {PALAVRA_ANCORA}",
            "Padrões algorítmicos presentes em {PALAVRA_ANCORA} e seus efeitos na experiência",
            "Dissecando as camadas técnicas que compõem a jogabilidade única de {PALAVRA_ANCORA}",
            
            # 6. FRASE INACABADA
            "Quando {PALAVRA_ANCORA} transcende as expectativas tradicionais de seu gênero...",
            "Enquanto especialistas debatem estratégias para {PALAVRA_ANCORA}, jogadores descobrem...",
            "Mesmo entre tantas opções no mercado, {PALAVRA_ANCORA} continua relevante porque...",
            "Para além do entretenimento básico, {PALAVRA_ANCORA} representa um fenômeno cultural...",
            
            # 7. CITAÇÃO/FRASE DE EFEITO
            "Simplesmente revolucionário: por que {PALAVRA_ANCORA} redefine padrões na indústria",
            "Impossível ignorar: como {PALAVRA_ANCORA} conquistou seu espaço no hall da fama",
            "Mais que um jogo, uma experiência: dissecando o fenômeno {PALAVRA_ANCORA}",
            "Além das expectativas: o impacto cultural de {PALAVRA_ANCORA} em diferentes mercados",
            
            # 8. IMPERATIVO
            "Descubra por que {PALAVRA_ANCORA} permanece relevante mesmo com tantas alternativas",
            "Entenda os mecanismos psicológicos que fazem de {PALAVRA_ANCORA} tão atraente",
            "Conheça as nuances estratégicas que podem transformar sua experiência com {PALAVRA_ANCORA}",
            "Explore as dimensões culturais e sociais que cercam o universo de {PALAVRA_ANCORA}",
            
            # 9. PARADOXO
            "Simples na aparência, complexo na execução: {PALAVRA_ANCORA} sob análise profunda",
            "Acessível para iniciantes, desafiador para veteranos: o equilíbrio em {PALAVRA_ANCORA}",
            "Aleatório mas previsível: compreendendo a matemática que governa {PALAVRA_ANCORA}",
            "Tradicional e inovador simultaneamente: o caso fascinante de {PALAVRA_ANCORA}",
            
            # 10. MOVIMENTO/CICLO
            "Do nicho ao mainstream: como {PALAVRA_ANCORA} transformou-se em fenômeno cultural",
            "Da criação ao reconhecimento global: jornada histórica de {PALAVRA_ANCORA}",
            "Entre altos e baixos: a resiliente trajetória de {PALAVRA_ANCORA} no mercado",
            "Do desenvolvimento à consolidação: marcos importantes na história de {PALAVRA_ANCORA}",
            
            # 11. IMPACTO
            "Como {PALAVRA_ANCORA} influenciou toda uma geração de jogos similares",
            "Por que {PALAVRA_ANCORA} continua impactando o comportamento dos jogadores",
            "De que forma {PALAVRA_ANCORA} redefiniu expectativas na indústria do entretenimento",
            "Em que medida {PALAVRA_ANCORA} contribuiu para a evolução dos jogos online",
            
            # 12. PSICOLOGIA
            "Gatilhos psicológicos que explicam o fascínio duradouro por {PALAVRA_ANCORA}",
            "Mecanismos cognitivos ativados durante sessões de {PALAVRA_ANCORA}",
            "Aspectos emocionais envolvidos na experiência imersiva de {PALAVRA_ANCORA}",
            "Processos mentais que tornam {PALAVRA_ANCORA} tão envolvente para diferentes perfis"
        ]
        
        # Seleciona aleatoriamente um modelo de cada categoria para sugerir ao Gemini
        estruturas_selecionadas = []
        for i in range(0, len(estruturas_rotativas), 4):
            grupo = estruturas_rotativas[i:i+4]
            estruturas_selecionadas.append(random.choice(grupo))
        
        # Embaralha as estruturas selecionadas para maior diversidade
        random.shuffle(estruturas_selecionadas)
        
        # Instruções específicas sobre diversidade de títulos
        instrucoes_diversidade = (
            "\n\nINSTRUÇÕES CRÍTICAS PARA GARANTIR TÍTULOS ÚNICOS E DIVERSIFICADOS:\n"
            f"1. É ABSOLUTAMENTE PROIBIDO começar o título com qualquer dos seguintes padrões (ou suas variações): {', '.join(padroes_proibidos[:20])}...\n"
            "2. PROIBIDO usar ARTIGOS DEFINIDOS no início do título (A, O, As, Os).\n"
            "3. PROIBIDO usar QUALQUER ADJETIVO no início do título.\n"
            "4. PROIBIDO iniciar com 'Uma análise', 'Um guia', ou estruturas similares.\n"
            "5. OBRIGATÓRIO: Use uma abordagem criativa e única, evitando QUALQUER estrutura já comum em blogs.\n\n"
            "Para ajudar, aqui estão algumas ESTRUTURAS APROVADAS que você pode ADAPTAR (mas não copiar exatamente):\n"
        )
        
        # Adiciona 5 estruturas aleatórias das selecionadas como exemplos
        exemplos_estruturas = random.sample(estruturas_selecionadas, min(5, len(estruturas_selecionadas)))
        for i, exemplo in enumerate(exemplos_estruturas, 1):
            if '{PALAVRA_ANCORA}' in exemplo:
                # Substitui o placeholder pela palavra real
                palavra_ancora = dados.get('palavra_ancora', 'este jogo')
                exemplo = exemplo.replace('{PALAVRA_ANCORA}', palavra_ancora)
            instrucoes_diversidade += f"- Exemplo {i}: \"{exemplo}\"\n"
        
        # Adiciona aviso final sobre a importância da diversidade
        instrucoes_diversidade += (
            "\nAVISO FINAL: Qualquer título que começar com estruturas comuns como \"A Evolução\", \"A Análise\", "
            "ou \"A Experiência\" será REJEITADO e o artigo terá que ser refeito. Use criatividade para evitar padrões!"
        )
        
        # Adiciona as instruções ao prompt original
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
                "\n\nATENÇÃO CRÍTICA SOBRE A PALAVRA-ÂNCORA:\n"
                "1. A palavra-âncora para este artigo é EXCLUSIVAMENTE: '{palavra_ancora}'\n"
                "2. NÃO mencione outras palavras-âncora ou jogos não relacionados a '{palavra_ancora}'\n"
                "3. Todo o conteúdo deve ser sobre '{palavra_ancora}' e APENAS '{palavra_ancora}'\n"
                "4. O título DEVE mencionar especificamente '{palavra_ancora}' e não outros jogos\n"
                "5. NUNCA substitua '{palavra_ancora}' por outro jogo ou tema similar\n"
            )
            
            # Preenche o template com os dados específicos desta linha
            prompt = prompt_template.replace("{{site}}", site)
            prompt = prompt.replace("{{palavra_ancora}}", palavra_ancora)
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
            
            # Adiciona informação do site e do link para personalização + alerta de termos proibidos
            prompt += f"\n{link_info}{termos_proibidos_alerta}"
            
            return prompt
        except KeyError as e:
            self.logger.error(f"Erro ao construir prompt - chave ausente: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Erro ao construir prompt: {e}")
            raise

    def verificar_titulo_gerado(self, titulo: str, palavra_ancora: str, palavras_a_evitar: list, titulos_existentes: list = None) -> bool:
        """
        Verifica se o título gerado é válido e único.
        """
        if not titulo:
            self.logger.warning("Título vazio recebido em verificar_titulo_gerado.")
            return False
        
        titulo_norm = normalizar_texto(titulo.lower())
        palavra_ancora_norm = normalizar_texto(palavra_ancora.lower())

        # 1. Verificar presença da palavra-âncora (flexível)
        if palavra_ancora and palavra_ancora.strip():
            ancora_norm = self._normalizar_flex(palavra_ancora)
            titulo_norm_flex = self._normalizar_flex(titulo)
            # Aceita plural/singular simples
            formas_aceitas = [ancora_norm]
            if ancora_norm.endswith('s'):
                formas_aceitas.append(ancora_norm.rstrip('s'))
            else:
                formas_aceitas.append(ancora_norm + 's')
            if not any(f in titulo_norm_flex for f in formas_aceitas):
                self.logger.warning(f"Palavra-âncora '{palavra_ancora}' (normalizada) não encontrada no título '{titulo}'. O título será rejeitado.")
                return False

        # 2. Verificar se termina com reticências
        if titulo.strip().endswith("..."):
            self.logger.warning(f"Título '{titulo}' termina com reticências.")
            return False

        # 3. Verifica similaridade com títulos existentes
        if titulos_existentes:
            for titulo_existente in titulos_existentes:
                titulo_existente_norm = normalizar_texto(titulo_existente.lower())
                
                # Extrai palavras significativas (ignora palavras comuns e muito curtas)
                palavras_comuns = {'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'e', 'ou', 'mas', 'por', 'para', 'com', 'sem', 'em', 'no', 'na', 'nos', 'nas', 'de', 'do', 'da', 'dos', 'das'}
                palavras_titulo = {p for p in titulo_norm.split() if len(p) > 3 and p not in palavras_comuns}
                palavras_existente = {p for p in titulo_existente_norm.split() if len(p) > 3 and p not in palavras_comuns}

                if not palavras_titulo or not palavras_existente:
                    continue

                # Calcula similaridade usando Jaccard Index
                palavras_comuns = palavras_titulo.intersection(palavras_existente)
                similaridade_jaccard = len(palavras_comuns) / len(palavras_titulo.union(palavras_existente))
                
                # Verifica padrões numéricos no início
                match_titulo = re.match(r"^(\d+)\s+(\w+\s+\w+)", titulo_norm)
                match_existente = re.match(r"^(\d+)\s+(\w+\s+\w+)", titulo_existente_norm)
                
                if match_titulo and match_existente:
                    numero_titulo = match_titulo.group(1)
                    palavras_titulo = match_titulo.group(2)
                    numero_existente = match_existente.group(1)
                    palavras_existente = match_existente.group(2)
                    
                    # Rejeita se tiver mesmo número e palavras similares
                    if numero_titulo == numero_existente and self._calcular_similaridade_palavras(palavras_titulo, palavras_existente) > 0.7:
                        self.logger.warning(f"Título rejeitado por padrão numérico similar: '{titulo}' vs '{titulo_existente}'")
                        return False
                
                # Verifica similaridade geral
                if similaridade_jaccard > 0.4:  # Reduzido o limiar de similaridade
                    self.logger.warning(f"Título rejeitado por alta similaridade ({similaridade_jaccard:.2f}) com título existente: '{titulo}' vs '{titulo_existente}'")
                    return False
                
                # Verifica similaridade de estrutura
                if self._verificar_estrutura_similar(titulo_norm, titulo_existente_norm):
                    self.logger.warning(f"Título rejeitado por estrutura similar: '{titulo}' vs '{titulo_existente}'")
                    return False

        # 4. Verifica padrões proibidos no início
        padroes_proibidos_inicio = [
            "a evolu", "a analis", "a histor", "a experienc", "a jornada", "a transformac", 
            "a fascinant", "a importanc", "a influenc", "o impacto", "o guia", "o manual",
            "o segredo", "o papel", "o poder", "o jeito", "o metodo", "a arte", "a magia",
            "a tecnica", "o jogo", "a estrateg", "a mecanic", "as vantagens", "as possibilidades",
            "a abordagem", "a visao", "a perspectiva", "a exploracao", "a descoberta",
            "o fenomeno", "a ciencia", "o estudo", "a investigacao", "a analise",
            "o caminho", "a rota", "a trajetoria", "a aventura", "a missao",
            "a explicacao", "a compreensao", "o entendimento", "a percepcao",
            "a revolucao", "a inovacao", "a transformacao", "a mudanca", "a alteracao",
            "o desenvolvimento", "a evolucao", "o crescimento", "a expansao", "o avanco",
            "a exploracao", "a investigacao", "a pesquisa", "o estudo", "a observacao",
            "a essencia", "a natureza", "o cerne", "o nucleo", "a base", "o fundamento",
            "os segredos", "os misterios", "as curiosidades", "os detalhes", "os aspectos",
            "uma analise", "uma abordagem", "uma visao", "uma perspectiva", "uma exploracao",
            "um guia", "um manual", "um panorama", "um olhar", "uma investigacao"
        ]
        
        for padrao in padroes_proibidos_inicio:
            if titulo_norm.startswith(padrao):
                self.logger.warning(f"Título rejeitado por iniciar com padrão proibido '{padrao}': '{titulo}'")
                return False

        # 5. Verifica estruturas problemáticas
        estruturas_problematicas = [
            "dicas para", "truques para", "segredos para", "estrategias para", "metodos para",
            "guia completo", "guia definitivo", "guia pratico", "guia essencial", "manual de",
            "tudo sobre", "tudo que", "tudo o que", "o que voce", "o que todo", "por que escolher",
            "como dominar", "como jogar", "como aproveitar", "como utilizar", "como entender"
        ]
        
        for estrutura in estruturas_problematicas:
            if estrutura in titulo_norm:
                self.logger.warning(f"Título rejeitado por conter estrutura problemática '{estrutura}': '{titulo}'")
                return False

        # 6. Verifica palavras a evitar
        if palavras_a_evitar:
            for palavra in palavras_a_evitar:
                palavra_norm = normalizar_texto(palavra.lower())
                if f" {palavra_norm} " in f" {titulo_norm} ":
                    self.logger.warning(f"Título rejeitado por conter palavra a evitar '{palavra}': '{titulo}'")
                    return False

        # 7. Verifica comprimento
        palavras = [p for p in titulo.split() if p.strip()]
        if len(palavras) < 9 or len(palavras) > 15:
            self.logger.warning(f"Título rejeitado por ter {len(palavras)} palavras (deve ter entre 9-15): '{titulo}'")
            return False

        # 8. Verifica comprimento em caracteres
        if len(titulo) > 100:
            self.logger.warning(f"Título rejeitado por ter {len(titulo)} caracteres (máximo 100): '{titulo}'")
            return False

        return True

    def _calcular_similaridade_palavras(self, palavras1: str, palavras2: str) -> float:
        """
        Calcula a similaridade entre duas sequências de palavras usando o algoritmo de Levenshtein.
        """
        from Levenshtein import ratio
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

    def verificar_conteudo_gerado(self, conteudo: str, palavra_ancora: str) -> Tuple[bool, str]:
        """
        Verifica se o conteúdo gerado atende aos requisitos.
        
        Args:
            conteudo: O conteúdo gerado
            palavra_ancora: A palavra-âncora que deve estar presente
            
        Returns:
            Tupla (sucesso, mensagem_erro)
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
Exemplos de estruturas:
1. Pergunta provocativa: "Que verdade sobre {palavra_ancora} iniciantes descobrem tarde demais (e custa caro)?"
2. Frase de efeito: "{palavra_ancora}: Convertendo Simples Palpites em Decisões Calculadas"
3. Metáfora: "Entendendo {palavra_ancora}: Menos [Comparação A Menos Atrativa] e Mais [Comparação B Mais Estratégica/Interessante]."
4. Afirmação ousada: "Quase Tudo Que Você Sabe Sobre {palavra_ancora} Pode Estar Errado."
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
                    if any(self._calcular_similaridade_palavras(titulo_norm, normalizar_texto(t.lower())) > 0.7 for t in titulos_existentes):
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
        Gera conteúdo para um título específico.
        Args:
            dados: Dicionário com os dados necessários
            titulo: Título pré-gerado para o conteúdo
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