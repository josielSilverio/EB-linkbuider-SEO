# Módulo para interagir com a API do Gemini
import os
import logging
import google.generativeai as genai
from typing import Dict, Tuple, Optional

from src.config import (
    GOOGLE_API_KEY, 
    GEMINI_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_TEMPERATURE,
    estimar_custo_gemini
)
from src.utils import contar_tokens, substituir_links_markdown

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
            self.model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config={
                    "temperature": GEMINI_TEMPERATURE,
                    "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
                }
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
    
    def _construir_prompt(self, dados: Dict[str, str], prompt_template: str) -> str:
        """
        Constrói o prompt para o Gemini usando o template e os dados da linha
        """
        try:
            # Preenche o template com os dados
            prompt = prompt_template.format(
                tema=dados.get('tema', ''),
                palavra_ancora=dados.get('palavra_ancora', ''),
                url_ancora=dados.get('url_ancora', ''),
                titulo=dados.get('titulo', '')
            )
            return prompt
        except KeyError as e:
            self.logger.error(f"Erro ao construir prompt - chave ausente: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Erro ao construir prompt: {e}")
            raise
    
    def gerar_conteudo(self, dados: Dict[str, str]) -> Tuple[str, Dict[str, float], Optional[str]]:
        """
        Gera conteúdo usando a API do Gemini.
        
        Args:
            dados: Dicionário com os dados da linha da planilha
        
        Returns:
            Tupla (conteudo_gerado, metricas, info_link)
            onde metricas é um dict com 'tokens_entrada', 'tokens_saida', 'custo_estimado'
        """
        try:
            # Carrega o template do prompt
            prompt_template = self.carregar_prompt_template()
            
            # Constrói o prompt
            prompt = self._construir_prompt(dados, prompt_template)
            
            # Conta tokens de entrada para estimativa de custo
            tokens_entrada = contar_tokens(prompt)
            self.logger.info(f"Prompt construído com {tokens_entrada} tokens estimados")
            
            # Gera o conteúdo chamando a API do Gemini
            response = self.model.generate_content(prompt)
            
            # Extrai o texto gerado e limpa formatações indesejadas
            conteudo_gerado = response.text.strip()
            
            # Conta tokens de saída para estimativa de custo
            tokens_saida = contar_tokens(conteudo_gerado)
            self.logger.info(f"Resposta gerada com {tokens_saida} tokens estimados")
            
            # Calcula custo estimado
            custo_estimado = estimar_custo_gemini(tokens_entrada, tokens_saida)
            self.logger.info(f"Custo estimado: ${custo_estimado:.6f} USD")
            
            # Adiciona o link na palavra âncora
            palavra_ancora = dados.get('palavra_ancora', '')
            url_ancora = dados.get('url_ancora', '')
            
            info_link = None
            if palavra_ancora and url_ancora:
                conteudo_gerado, info_link = substituir_links_markdown(conteudo_gerado, palavra_ancora, url_ancora)
                if info_link:
                    self.logger.info(f"Link adicionado para a palavra-âncora: {palavra_ancora}")
                else:
                    self.logger.warning(f"Palavra-âncora '{palavra_ancora}' não encontrada no texto gerado.")
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