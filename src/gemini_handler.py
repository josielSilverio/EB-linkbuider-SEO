# Módulo para interagir com a API do Gemini
import os
import logging
import google.generativeai as genai
import re
import random
from typing import Dict, Tuple, Optional

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
        "gates of olympus": "Foque na rica temática mitológica grega. Descreva como o jogo incorpora Zeus e outros elementos da mitologia em sua mecânica. Mencione os multiplicadores e o sistema de rodadas bônus.",
        "fortune rabbit": "Enfatize a temática asiática e os elementos culturais de sorte. Descreva os símbolos especiais e como eles se conectam com as tradições de fortuna. Mencione as mecânicas de bônus.",
        "sweet bonanza": "Destaque o visual colorido e a temática de doces. Explique o sistema único de pagamentos em cluster em vez de linhas tradicionais. Mencione as rodadas bônus e multiplicadores.",
        
        # Jogos de mesa
        "blackjack": "Aborde o equilíbrio entre sorte e estratégia. Explique a mecânica básica e por que o jogo atrai tanto jogadores iniciantes quanto experientes. Mencione a importância das decisões estratégicas.",
        "poker": "Destaque o elemento de habilidade e psicologia. Explique como o jogo se diferencia de outros jogos de cassino pelo componente estratégico. Mencione as variantes mais populares.",
        "roleta": "Explique a elegância e simplicidade do jogo. Descreva os diferentes tipos de apostas possíveis e como a roleta mantém seu charme através dos séculos. Mencione as diferenças entre as versões."
    }
    
    # Detecta palavras-chave no nome do jogo
    for palavra_chave, instrucao in instrucoes_especiais.items():
        if palavra_chave.lower() in palavra_ancora.lower():
            return instrucao
    
    # Instruções padrão baseadas em categorias de jogos
    if any(termo in palavra_ancora.lower() for termo in ["fortune", "lucky", "tiger", "gold", "gems", "dragon"]):
        return "Destaque a temática de fortuna e riqueza do jogo. Explique os símbolos especiais e como eles se conectam com o tema principal. Descreva as mecânicas de bônus e o visual distintivo."
    
    if any(termo in palavra_ancora.lower() for termo in ["book", "dead", "egypt", "vikings", "aztec"]):
        return "Enfatize o tema histórico ou mitológico. Explique como o jogo incorpora elementos culturais autênticos em sua mecânica. Descreva os símbolos e recursos especiais que o tornam único."
    
    if any(termo in palavra_ancora.lower() for termo in ["fruit", "candy", "sweet", "fish"]):
        return "Destaque o visual colorido e temático. Explique como o jogo se diferencia com seus símbolos e mecânicas especiais. Descreva a experiência visual e as funcionalidades exclusivas."
    
    # Instrução genérica para garantir originalidade
    return "Destaque o que torna este jogo único entre seus concorrentes. Explique as mecânicas principais, recursos especiais e elementos visuais distintivos. Mantenha o foco nas características específicas deste jogo."


def verificar_e_corrigir_titulo(titulo: str, palavra_ancora: str) -> Optional[str]:
    """
    Verifica e corrige o comprimento do título, garantindo que tenha entre 9-15 palavras,
    não ultrapasse 100 caracteres, contenha a palavra-âncora e não termine com reticências.
    
    Args:
        titulo: O título a ser verificado
        palavra_ancora: A palavra-âncora que deve estar presente no título
        
    Returns:
        Título corrigido e válido, ou None se não puder ser validado/corrigido.
    """
    logger = logging.getLogger('seo_linkbuilder.gemini')
    
    if not titulo:
        logger.warning("Título vazio recebido para verificação.")
        return None
    
    # Remove espaços extras e quebras de linha
    titulo_processado = re.sub(r'\s+', ' ', titulo).strip()
    
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
            return None

    # 2. Verificar presença da palavra-âncora (case-insensitive)
    if palavra_ancora.lower() not in titulo_processado.lower():
        logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no título: '{titulo_processado}'. O título será rejeitado.")
        return None # Rejeita o título se a palavra-âncora não estiver presente

    # Conta palavras
    palavras = titulo_processado.split()
    num_palavras = len(palavras)
    
    # Limita o comprimento em caracteres
    MAX_CARACTERES = 100
    if len(titulo_processado) > MAX_CARACTERES:
        logger.warning(f"Título excede {MAX_CARACTERES} caracteres: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        # Reduz o título para caber no limite de caracteres, tenta não cortar palavras-chave
        if palavra_ancora.lower() in titulo_processado.lower():
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
        else: # Se âncora não está (não deveria acontecer devido à checagem anterior), trunca normalmente
            titulo_processado = titulo_processado[:MAX_CARACTERES].rsplit(' ', 1)[0]

        logger.info(f"Título reduzido para: '{titulo_processado}' ({len(titulo_processado)} caracteres)")
        palavras = titulo_processado.split() # Recalcula palavras
        num_palavras = len(palavras)

    # Verifica se está dentro dos limites de palavras (9-15)
    if not (9 <= num_palavras <= 15):
        logger.warning(f"Título com número de palavras fora do intervalo (9-15): '{titulo_processado}' ({num_palavras} palavras).")
        # Títulos fora da contagem de palavras após ajustes são rejeitados para nova geração.
        # A lógica de expansão/redução anterior era muito propensa a criar títulos de baixa qualidade.
        # É melhor o Gemini tentar novamente com as restrições do prompt.
        return None 
        
    # Se todas as verificações passaram
    logger.info(f"Título validado e corrigido: '{titulo_processado}'")
    return titulo_processado


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
    
    def carregar_prompt_template(self) -> str:
        """
        Carrega o template do prompt do arquivo prompt.txt
        """
        try:
            with open("data/prompt.txt", "r", encoding="utf-8") as f:
                prompt_template = f.read()
            self.logger.info("Template de prompt carregado com sucesso")
            return prompt_template
        except Exception as e:
            self.logger.error(f"Erro ao carregar template do prompt: {e}")
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
        Verifica se o título gerado contém palavras ou padrões proibidos, a palavra-âncora e não termina com reticências.
        
        Args:
            titulo: O título gerado
            palavra_ancora: A palavra-âncora que deve estar presente
            palavras_a_evitar: Lista de palavras e frases a evitar
            titulos_existentes: Lista de títulos já existentes para verificar similaridade
            
        Returns:
            True se o título é aceitável, False caso contrário
        """
        if not titulo:
            self.logger.warning("Título vazio recebido em verificar_titulo_gerado.")
            return False
        
        titulo_norm = normalizar_texto(titulo.lower())
        palavra_ancora_norm = normalizar_texto(palavra_ancora.lower())

        # 1. Verificar presença da palavra-âncora
        if palavra_ancora_norm not in titulo_norm:
            self.logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no título '{titulo}' durante a verificação.")
            return False

        # 2. Verificar se termina com reticências
        if titulo.strip().endswith("..."):
            self.logger.warning(f"Título '{titulo}' termina com reticências.")
            return False

        # 3. Verifica se o título é muito similar a algum título existente
        if titulos_existentes:
            for titulo_existente in titulos_existentes:
                titulo_existente_norm = normalizar_texto(titulo_existente.lower())
                palavras_titulo = set(titulo_norm.split())
                palavras_existente = set(titulo_existente_norm.split())
                
                # Ignora palavras muito curtas na comparação de similaridade
                palavras_titulo_filtradas = {p for p in palavras_titulo if len(p) > 2}
                palavras_existente_filtradas = {p for p in palavras_existente if len(p) > 2}

                if not palavras_titulo_filtradas or not palavras_existente_filtradas: # Evita divisão por zero se um dos títulos for só palavras curtas
                    continue

                palavras_comuns = palavras_titulo_filtradas.intersection(palavras_existente_filtradas)
                
                # Similaridade mais rigorosa: Jaccard Index > 0.5 (ou 50% de sobreposição de palavras significativas)
                # E verifica se o início do título é idêntico (padrões como "7 alguma coisa")
                similaridade_jaccard = len(palavras_comuns) / len(palavras_titulo_filtradas.union(palavras_existente_filtradas))
                
                # Verificação de padrão numérico inicial (ex: "7 Dicas...", "5 Segredos...")
                match_titulo_num = re.match(r"^(\d+)\s+\w+", titulo_norm)
                match_existente_num = re.match(r"^(\d+)\s+\w+", titulo_existente_norm)

                if match_titulo_num and match_existente_num:
                    # Se ambos começam com um número e a primeira palavra após o número é a mesma
                    if match_titulo_num.group(0) == match_existente_num.group(0):
                        self.logger.warning(f"Título rejeitado por padrão numérico inicial repetido: '{titulo}' vs '{titulo_existente}'")
                        return False
                
                if similaridade_jaccard > 0.5: # Aumentado o limiar de similaridade para 0.5
                    self.logger.warning(f"Título rejeitado por alta similaridade ({similaridade_jaccard:.2f}) com título existente: '{titulo}' vs '{titulo_existente}'")
                    return False
        
        # Lista ampliada de padrões absolutamente proibidos no início do título
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
        
        # Verifica se começa com algum dos padrões proibidos
        for padrao in padroes_proibidos_inicio:
            if titulo_norm.startswith(padrao):
                self.logger.warning(f"Título rejeitado por iniciar com padrão proibido '{padrao}': '{titulo}'")
                return False
        
        # Verifica estruturas comuns e repetitivas no título inteiro
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
        
        # Verifica se contém palavras ou frases específicas a evitar
        if palavras_a_evitar:
            for palavra in palavras_a_evitar:
                palavra_norm = normalizar_texto(palavra.lower())
                # Verifica se é uma palavra inteira ou parte de uma
                if f" {palavra_norm} " in f" {titulo_norm} ":
                    self.logger.warning(f"Título rejeitado por conter palavra a evitar '{palavra}': '{titulo}'")
                    return False
        
        # Verifica se o título tem comprimento adequado (9-15 palavras)
        palavras = [p for p in titulo.split() if p.strip()]
        if len(palavras) < 9 or len(palavras) > 15:
            self.logger.warning(f"Título rejeitado por ter {len(palavras)} palavras (deve ter entre 9-15): '{titulo}'")
            return False
        
        # Verifica o comprimento em caracteres (máximo 100)
        if len(titulo) > 100:
            self.logger.warning(f"Título rejeitado por ter {len(titulo)} caracteres (máximo 100): '{titulo}'")
            return False
        
        # Se passou por todas as verificações, o título é aceitável
        self.logger.info(f"Título '{titulo}' passou na verificação de duplicidade e padrões.")
        return True

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
                titulo_corrigido_ou_none = verificar_e_corrigir_titulo(titulo_gerado, palavra_ancora)
                
                # Se o título foi corrigido, substitui no conteúdo
                # Se for None, significa que é inválido e precisa regenerar.
                if titulo_corrigido_ou_none is None:
                    self.logger.warning(f"Título gerado '{titulo_gerado}' foi rejeitado por verificar_e_corrigir_titulo (ausência de âncora, reticências, ou tamanho).")
                    # Prepara para próxima tentativa
                elif titulo_gerado != titulo_corrigido_ou_none:
                    self.logger.info(f"Título corrigido de '{titulo_gerado}' para '{titulo_corrigido_ou_none}' por verificar_e_corrigir_titulo.")
                    if linhas:
                        linhas[0] = titulo_corrigido_ou_none
                        conteudo_gerado = '\n'.join(linhas)
                
                # Verifica o título (corrigido ou original se não foi corrigido) com verificar_titulo_gerado
                # A função verificar_titulo_gerado também precisa da palavra_ancora
                titulo_para_verificar = titulo_corrigido_ou_none if titulo_corrigido_ou_none else titulo_gerado

                if titulo_corrigido_ou_none and self.verificar_titulo_gerado(titulo_para_verificar, palavra_ancora, palavras_a_evitar, titulos_existentes):
                    self.logger.info(f"Título gerado é aceitável: '{titulo_para_verificar}'")
                    break # Sai do loop de tentativas
                else:
                    if not titulo_corrigido_ou_none:
                        self.logger.warning(f"Título '{titulo_gerado}' invalidado por verificar_titulo_gerado. Tentando novamente.")
                    else:
                        self.logger.warning(f"Título '{titulo_para_verificar}' rejeitado por verificar_titulo_gerado. Tentando novamente.")

                # Título contém padrões proibidos ou é inválido, tenta novamente com temperatura mais alta
                self.temperatura_atual = min(0.95, self.temperatura_atual + 0.1)
                generation_config["temperature"] = self.temperatura_atual
                self.logger.info(f"Aumentando temperatura para {self.temperatura_atual} e tentando novamente")
            
            # Restaura a temperatura original para próximas chamadas
            self.temperatura_atual = temperatura_original
            
            # Monta métricas para logging e custos
            metricas = {
                'tokens_entrada': tokens_entrada,
                'tokens_saida': tokens_saida,
                'custo_estimado': custo_estimado,
                'tentativas': tentativas
            }
            
            # Insere a palavra-âncora no texto (agora com verificação de contexto natural)
            conteudo_processado, info_link = substituir_links_markdown(conteudo_gerado, palavra_ancora, dados.get('url_ancora', ''))
            
            # Logs sobre o processamento
            self.logger.info(f"Conteúdo gerado com {tokens_saida} tokens de saída")
            self.logger.info(f"Custo estimado: ${custo_estimado:.6f} USD")
            
            if info_link:
                self.logger.info(f"Palavra-âncora '{palavra_ancora}' inserida no parágrafo {info_link['paragrafo']}")
            else:
                self.logger.warning(f"Não foi possível inserir a palavra-âncora '{palavra_ancora}' no texto")
            
            return conteudo_processado, metricas, info_link
        
        except Exception as e:
            self.logger.error(f"Erro ao gerar conteúdo com o Gemini: {e}")
            self.logger.exception("Detalhes do erro:")
            raise