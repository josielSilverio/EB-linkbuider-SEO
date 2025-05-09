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
    estimar_custo_gemini
)
from src.utils import contar_tokens, substituir_links_markdown

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


def verificar_e_corrigir_titulo(titulo: str) -> str:
    """
    Verifica e corrige o comprimento do título, garantindo que tenha entre 9-15 palavras.
    
    Args:
        titulo: O título a ser verificado
        
    Returns:
        Título corrigido ou original se estiver dentro dos limites
    """
    if not titulo:
        return titulo
    
    # Remove espaços extras e quebras de linha
    titulo = re.sub(r'\s+', ' ', titulo).strip()
    
    # Conta palavras
    palavras = titulo.split()
    num_palavras = len(palavras)
    
    # Verifica se está dentro dos limites
    if 9 <= num_palavras <= 15:
        return titulo
    
    # Correção para títulos muito curtos
    if num_palavras < 9:
        # Identifica o tema principal
        jogo = ""
        temas = ["olympus", "zeus", "fortuna", "aviator", "blackjack", "roleta", "poker", "slot"]
        for tema in temas:
            if tema.lower() in titulo.lower():
                jogo = tema
                break
        
        # Adiciona qualificadores para expandir o título
        qualificadores = [
            "com mecânicas inovadoras e design impressionante",
            "com recursos exclusivos e jogabilidade envolvente",
            "uma nova abordagem para jogos de cassino online",
            "combinando estratégia e chance de maneira equilibrada",
            "revolucionando a experiência de jogos digitais modernos"
        ]
        
        # Escolhe um qualificador que não repita palavras já presentes
        random.shuffle(qualificadores)
        for qualificador in qualificadores:
            if not any(q.lower() in titulo.lower() for q in qualificador.split()):
                novo_titulo = f"{titulo}: {qualificador}"
                if len(novo_titulo.split()) >= 9:
                    return novo_titulo
        
        # Se nenhum qualificador funcionou, adiciona um genérico
        return f"{titulo}: uma abordagem inovadora para jogos de cassino digitais"
    
    # Correção para títulos muito longos
    else:  # num_palavras > 15
        # Tenta remover palavras menos importantes mantendo a estrutura
        artigos_e_conjuncoes = ["e", "o", "a", "os", "as", "um", "uma", "uns", "umas", "com", "para", "que", "de", "do", "da"]
        adjetivos_comuns = ["incrível", "impressionante", "fantástico", "maravilhoso", "excelente", "surpreendente"]
        
        # Primeiro tenta remover adjetivos não essenciais
        nova_lista = []
        removidos = 0
        palavras_para_remover = num_palavras - 15
        
        for palavra in palavras:
            if removidos < palavras_para_remover and palavra.lower() in adjetivos_comuns:
                removidos += 1
                continue
            nova_lista.append(palavra)
        
        # Se ainda está longo, tenta remover artigos e conjunções do meio (não do início)
        if len(nova_lista) > 15:
            temp_lista = [nova_lista[0]]  # Mantém a primeira palavra
            removidos = 0
            palavras_para_remover = len(nova_lista) - 15
            
            for palavra in nova_lista[1:]:
                if removidos < palavras_para_remover and palavra.lower() in artigos_e_conjuncoes:
                    removidos += 1
                    continue
                temp_lista.append(palavra)
            
            nova_lista = temp_lista
        
        # Se ainda está longo, remove palavras do final (preservando a estrutura principal)
        if len(nova_lista) > 15:
            nova_lista = nova_lista[:15]
        
        return " ".join(nova_lista)


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
        
        # Palavras de início comuns que queremos evitar
        inicios_comuns = [
            "segredos", "o poder", "a magia", "o guia", "como", "descubra", 
            "explorando", "o mundo", "7 dicas", "tudo sobre", "a arte de",
            "o mito", "a lenda", "desvendando", "jornada"
        ]
        
        # Padrões estruturais comuns a evitar
        padroes_comuns = [
            "[substantivo]: uma [jornada/experiência]",
            "o [substantivo] de [jogo]",
            "[jogo]: [substantivo] e [substantivo]"
        ]
        
        # Regra obrigatória de comprimento do título
        regra_comprimento = (
            "REGRA OBRIGATÓRIA DE COMPRIMENTO DO TÍTULO:\n"
            "- O título DEVE ter entre 9 e 15 palavras, nem mais nem menos.\n"
            "- Conte as palavras antes de finalizar o título e ajuste se necessário.\n"
            "- Esta é uma regra INVIOLÁVEL - títulos muito curtos ou muito longos serão rejeitados.\n"
        )
        
        # Se é um jogo de mitologia ou deuses, adicione instruções específicas
        palavra_ancora = dados.get('palavra_ancora', '').lower()
        if any(termo in palavra_ancora for termo in ['olympus', 'zeus', 'thor', 'viking', 'egypt', 'maya', 'aztec']):
            instrucao_especifica = (
                "REGRA ESPECIAL PARA ESTE TÍTULO:\n"
                "- NÃO comece com o nome de deuses, mitologias ou locais míticos\n"
                "- Evite COMPLETAMENTE começar com as palavras 'Segredos', 'Poder', 'Jornada', 'Mito', 'Guia'\n"
                "- Crie um título que não se pareça com NENHUM outro já usado para jogos similares\n"
                "- Obrigatoriamente use uma abordagem que não envolva a palavra 'experiência' ou 'jornada'\n"
                + regra_comprimento
            )
            prompt += "\n" + instrucao_especifica
        
        # Para outros tipos de jogos, adicione instruções gerais
        else:
            instrucao_geral = (
                "REGRA ESPECIAL PARA ESTE TÍTULO:\n"
                "- Use uma estrutura completamente diferente dos exemplos mostrados\n"
                "- Evite começar com qualquer palavra comum em títulos de artigos\n"
                "- Crie um título que poderia se destacar em uma revista premium\n"
                + regra_comprimento
            )
            prompt += "\n" + instrucao_geral
        
        return prompt

    
    
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

    def gerar_conteudo(self, dados: Dict[str, str], instrucao_adicional: str = None) -> Tuple[str, Dict[str, float], Optional[Dict]]:
        """
        Gera conteúdo usando a API do Gemini.
        
        Args:
            dados: Dicionário com os dados da linha da planilha
            instrucao_adicional: Texto opcional a ser adicionado ao prompt para personalizar a geração
        
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
            if instrucao_adicional:
                prompt += instrucao_adicional
                self.logger.info(f"Instrução adicional adicionada ao prompt: {instrucao_adicional}")
            
            # Conta tokens de entrada para estimativa de custo
            tokens_entrada = contar_tokens(prompt)
            self.logger.info(f"Prompt construído com {tokens_entrada} tokens estimados")
            
            # Log das entidades importantes no prompt
            site = dados.get('site', 'Não fornecido')
            self.logger.info(f"Site: '{site}'")
            
            # Não logar 'tema' como 'Sem tema', usar o site como tema
            tema = f"apostas em {site}" if 'apostas' not in site.lower() else site
            self.logger.info(f"Tema: '{tema}'")
            
            palavra_ancora = dados.get('palavra_ancora', '')
            url_ancora = dados.get('url_ancora', '')
            
            self.logger.info(f"Palavra-âncora que DEVE ser inserida naturalmente: '{palavra_ancora}'")
            self.logger.info(f"URL-âncora para a palavra: '{url_ancora}'")
            self.logger.info(f"Título: '{dados.get('titulo', 'Será gerado automaticamente')}'")
            
            # Armazena temperatura original
            temperatura_original = self.temperatura_atual
            # Aumenta a temperatura para cada execução para garantir mais aleatoriedade
            nova_temperatura = min(0.9, temperatura_original + 0.1 * (hash(dados.get('site', '')) % 5))
            self.temperatura_atual = nova_temperatura
            
            # Cria configuração de geração com a nova temperatura
            generation_config = {
                "temperature": nova_temperatura,
                "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
            }
            
            # Usa a nova configuração para este request específico
            self.logger.info(f"Usando temperatura: {nova_temperatura} para gerar conteúdo único")
            
            # Gera o conteúdo chamando a API do Gemini com a configuração específica
            self.logger.info("Chamando a API Gemini para gerar conteúdo...")
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Restaura a temperatura original
            self.temperatura_atual = temperatura_original
            
            # Extrai o texto gerado e limpa formatações indesejadas
            conteudo_gerado = response.text.strip()
            
            # Verifica se a palavra-âncora está presente ANTES de ajustar o tamanho
            palavra_presente = palavra_ancora.lower() in conteudo_gerado.lower()
            
            if not palavra_presente:
                self.logger.warning(f"ALERTA: Palavra-âncora '{palavra_ancora}' não detectada no texto gerado. Tentando novamente...")
                
                # Adiciona uma instrução ainda mais específica
                prompt_ajustado = prompt + (
                    f"\n\nATENÇÃO CRÍTICA: Você FALHOU em incluir a palavra-âncora '{palavra_ancora}' no texto. "
                    f"É ABSOLUTAMENTE OBRIGATÓRIO incluir EXATAMENTE a palavra '{palavra_ancora}' no segundo ou terceiro parágrafo. "
                    f"Não parafraseie, não use sinônimos, use EXATAMENTE a palavra '{palavra_ancora}' e de forma natural no texto."
                )
                
                # Aumenta a temperatura para maior variação
                nova_temperatura = min(0.95, nova_temperatura + 0.15)
                
                # Cria nova configuração
                generation_config = {
                    "temperature": nova_temperatura,
                    "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
                }
                
                # Tenta gerar novamente com foco na palavra-âncora
                try:
                    self.logger.info(f"Gerando novo conteúdo com ênfase na inclusão da palavra-âncora '{palavra_ancora}'...")
                    response = self.model.generate_content(
                        prompt_ajustado,
                        generation_config=generation_config
                    )
                    conteudo_gerado = response.text.strip()
                    
                    # Verifica se a palavra-âncora está presente agora
                    palavra_presente = palavra_ancora.lower() in conteudo_gerado.lower()
                    if palavra_presente:
                        self.logger.info(f"✓ Sucesso! Palavra-âncora '{palavra_ancora}' incluída na nova geração.")
                    else:
                        self.logger.error(f"❌ FALHA: Mesmo após segunda tentativa, a palavra-âncora '{palavra_ancora}' não foi incluída.")
                except Exception as e:
                    self.logger.error(f"Erro ao tentar gerar conteúdo com a palavra-âncora: {e}")
            
            # Enquanto o número de palavras for menor que 470 ou maior que 550, tenta gerar novamente
            num_tentativas = 0
            max_tentativas = 3
            
            while num_tentativas < max_tentativas:
                # Verifica o tamanho do texto em palavras
                num_palavras = len(conteudo_gerado.split())
                
                if 470 <= num_palavras <= 550:
                    break
                    
                if num_palavras < 470:
                    self.logger.warning(f"Texto gerado tem apenas {num_palavras} palavras. Tentando gerar um texto mais longo (tentativa {num_tentativas+1}/{max_tentativas})")
                    # Ajusta o prompt para pedir texto mais longo
                    prompt_ajustado = prompt + (
                        f"\n\nIMPORTANTE: O texto DEVE ter entre 470 e 550 palavras. Forneça conteúdo mais detalhado em cada tópico. "
                        f"E LEMBRE-SE: A palavra-âncora '{palavra_ancora}' DEVE aparecer no segundo ou terceiro parágrafo de forma natural."
                    )
                elif num_palavras > 550:
                    self.logger.warning(f"Texto gerado tem {num_palavras} palavras, acima do limite. Tentando gerar um texto mais conciso (tentativa {num_tentativas+1}/{max_tentativas})")
                    # Ajusta o prompt para pedir texto mais curto
                    prompt_ajustado = prompt + (
                        f"\n\nIMPORTANTE: O texto DEVE ter no máximo 550 palavras. Seja mais conciso em cada tópico. "
                        f"E LEMBRE-SE: A palavra-âncora '{palavra_ancora}' DEVE aparecer no segundo ou terceiro parágrafo de forma natural."
                    )
                
                # Aumenta a temperatura para maior variação
                nova_temperatura = min(0.9, nova_temperatura + 0.1)
                
                # Cria nova configuração com temperatura aumentada
                generation_config = {
                    "temperature": nova_temperatura,
                    "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
                }
                
                # Tenta gerar novamente
                try:
                    response = self.model.generate_content(
                        prompt_ajustado,
                        generation_config=generation_config
                    )
                    novo_conteudo = response.text.strip()
                    
                    # Verifica se a palavra-âncora está presente no novo texto
                    palavra_presente_novo = palavra_ancora.lower() in novo_conteudo.lower()
                    if not palavra_presente_novo and palavra_presente:
                        # O novo texto não tem a palavra-âncora, mas o anterior tinha
                        self.logger.warning(f"O novo texto não contém a palavra-âncora '{palavra_ancora}', mantendo texto anterior.")
                        break
                    
                    # Verifica se o novo conteúdo está dentro do intervalo desejado
                    novo_num_palavras = len(novo_conteudo.split())
                    mais_proximo_do_ideal = abs(novo_num_palavras - 500) < abs(num_palavras - 500)
                    
                    if palavra_presente_novo and (mais_proximo_do_ideal or not palavra_presente):
                        conteudo_gerado = novo_conteudo
                        palavra_presente = True
                        self.logger.info(f"Gerado novo conteúdo com {novo_num_palavras} palavras e contendo a palavra-âncora.")
                    elif mais_proximo_do_ideal and not palavra_presente_novo and not palavra_presente:
                        conteudo_gerado = novo_conteudo
                        self.logger.warning(f"Gerado novo conteúdo com {novo_num_palavras} palavras, mas ainda sem a palavra-âncora.")
                    else:
                        self.logger.warning("O novo conteúdo não era melhor que o anterior.")
                except Exception as e:
                    self.logger.error(f"Erro ao tentar gerar conteúdo ajustado: {e}")
                    
                num_tentativas += 1
            
            # Restaura a temperatura original
            self.temperatura_atual = temperatura_original
            
            # Verifica a estrutura básica do texto gerado
            linhas = conteudo_gerado.split('\n')
            self.logger.info(f"Resposta final contém {len(linhas)} linhas")
            if len(linhas) > 0:
                self.logger.info(f"Primeira linha: '{linhas[0][:50]}...'")
                if len(linhas) > 2:
                    self.logger.info(f"Terceira linha: '{linhas[2][:50]}...'")
            
            # Conta tokens de saída para estimativa de custo
            tokens_saida = contar_tokens(conteudo_gerado)
            self.logger.info(f"Resposta gerada com {tokens_saida} tokens e {len(conteudo_gerado)} caracteres")
            
            # Verifica o tamanho final do texto em palavras
            num_palavras = len(conteudo_gerado.split())
            self.logger.info(f"Número de palavras no texto gerado: {num_palavras}")
            if num_palavras < 470 or num_palavras > 550:
                self.logger.warning(f"ALERTA: Texto gerado tem menos de 470 ou mais de 550 palavras ({num_palavras})")
            
            # Calcula custo estimado
            custo_estimado = estimar_custo_gemini(tokens_entrada, tokens_saida)
            self.logger.info(f"Custo estimado: ${custo_estimado:.6f} USD")
            
            # Verifica se há termos proibidos no conteúdo gerado
            conteudo_filtrado, termos_substituidos = verificar_conteudo_proibido(conteudo_gerado)
            if termos_substituidos:
                self.logger.warning(f"Foram substituídos {len(termos_substituidos)} termos proibidos no conteúdo: {', '.join(termos_substituidos)}")
                conteudo_gerado = conteudo_filtrado
                
            # Adiciona o link na palavra âncora
            info_link = None
            if palavra_ancora and url_ancora:
                self.logger.info(f"Iniciando processo para criar link da palavra-âncora '{palavra_ancora}' para URL '{url_ancora}'...")
                conteudo_gerado, info_link = substituir_links_markdown(conteudo_gerado, palavra_ancora, url_ancora)
                if info_link:
                    self.logger.info(f"✓ Link criado com sucesso para a palavra-âncora '{palavra_ancora}' no parágrafo {info_link.get('paragrafo', '?')}!")
                    if 'paragrafo' in info_link and info_link['paragrafo'] > 3:
                        self.logger.warning(f"⚠️ Palavra-âncora inserida no parágrafo {info_link['paragrafo']}, não nos parágrafos 2 ou 3 como solicitado.")
                else:
                    self.logger.error(f"❌ FALHA: Palavra-âncora '{palavra_ancora}' não foi encontrada no texto gerado.")
            else:
                self.logger.warning("Palavra-âncora ou URL não encontrados. Conteúdo gerado sem link.")
            
            # Retorna o conteúdo gerado e as métricas
            metricas = {
                'tokens_entrada': tokens_entrada,
                'tokens_saida': tokens_saida,
                'custo_estimado': custo_estimado
            }
            
            return conteudo_gerado, metricas, info_link
        
        except Exception as e:
            self.logger.error(f"Erro ao gerar conteúdo: {e}")
            raise