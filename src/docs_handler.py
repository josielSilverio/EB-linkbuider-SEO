# Módulo para interagir com as APIs do Google Docs e Drive
import logging
from typing import Dict, List, Tuple, Optional

from src.config import DRIVE_FOLDER_ID, TITULO_TAMANHO
from src.auth_handler import obter_credenciais, criar_servico_docs, criar_servico_drive
from src.utils import extrair_titulos_markdown, converter_markdown_para_docs

class DocsHandler:
    def __init__(self):
        # Inicializa o logger
        self.logger = logging.getLogger('seo_linkbuilder.docs')
        
        # Obtém credenciais e inicializa os serviços
        try:
            self.credenciais = obter_credenciais()
            self.service_docs = criar_servico_docs(self.credenciais)
            self.service_drive = criar_servico_drive(self.credenciais)
            self.logger.info("Serviços do Google Docs e Drive inicializados com sucesso")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar os serviços: {e}")
            raise
    
    def criar_documento(self, titulo: str, conteudo: str, nome_arquivo: str, info_link=None) -> Tuple[str, str]:
        """
        Cria um novo documento no Google Docs e o salva na pasta especificada.
        
        Args:
            titulo: Título do documento
            conteudo: Conteúdo em formato natural para o documento
            nome_arquivo: Nome do arquivo para o documento
            info_link: Informações para adicionar link à palavra âncora (opcional)
        
        Returns:
            Tupla (document_id, document_url)
        """
        try:
            # Cria um documento em branco com o título especificado
            documento = self.service_docs.documents().create(
                body={"title": nome_arquivo}
            ).execute()
            
            document_id = documento.get('documentId')
            self.logger.info(f"Documento criado com ID: {document_id}")
            
            # Verifica o tamanho do conteúdo
            self.logger.info(f"Tamanho do conteúdo: {len(conteudo)} caracteres")
            
            # Verificação da estrutura do texto
            linhas = conteudo.split('\n')
            self.logger.info(f"Número de linhas no texto: {len(linhas)}")
            if len(linhas) > 0:
                self.logger.info(f"Primeira linha (título): {linhas[0][:50]}...")
            
            # Depuração de info_link
            if info_link:
                self.logger.info(f"Informações de link: palavra='{info_link.get('palavra', '')}', URL={info_link.get('url', '')}")
            else:
                self.logger.warning("Nenhuma informação de link fornecida")

            # Converte o texto para requests da API do Docs, incluindo informações do link
            requests = converter_markdown_para_docs(conteudo, info_link)
            self.logger.info(f"Gerados {len(requests)} requests para a API do Docs")
            
            # Aplica as atualizações ao documento
            if requests:
                self.service_docs.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": requests}
                ).execute()
                self.logger.info(f"Conteúdo inserido no documento {document_id}")
            else:
                self.logger.warning("Nenhum request gerado para atualizar o documento")
            
            # Formata o título principal (H1) para tamanho configurado
            self._formatar_titulo(document_id, TITULO_TAMANHO)
            
            # Move o arquivo para a pasta especificada no Drive
            self._mover_para_pasta(document_id, DRIVE_FOLDER_ID)
            
            # Obtém a URL do documento
            document_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return document_id, document_url
        
        except Exception as e:
            self.logger.error(f"Erro ao criar documento: {e}")
            raise
    
    def _formatar_titulo(self, document_id: str, tamanho: int = 17) -> None:
        """
        Formata o título principal (H1) do documento com o tamanho especificado.
        
        Args:
            document_id: ID do documento no Google Docs
            tamanho: Tamanho da fonte para o título
        """
        try:
            # Obtém o documento para encontrar o título
            documento = self.service_docs.documents().get(documentId=document_id).execute()
            
            # Procura pelo primeiro título (H1)
            for elemento in documento.get('body', {}).get('content', []):
                if 'paragraph' in elemento:
                    paragrafo = elemento.get('paragraph', {})
                    estilo = paragrafo.get('paragraphStyle', {}).get('namedStyleType', '')
                    
                    # Se encontrou um H1, aplica o tamanho da fonte
                    if estilo == 'HEADING_1':
                        start_index = elemento.get('startIndex')
                        end_index = elemento.get('endIndex')
                        
                        # Aplica o tamanho da fonte
                        self.service_docs.documents().batchUpdate(
                            documentId=document_id,
                            body={
                                "requests": [
                                    {
                                        "updateTextStyle": {
                                            "range": {
                                                "startIndex": start_index,
                                                "endIndex": end_index
                                            },
                                            "textStyle": {
                                                "fontSize": {
                                                    "magnitude": tamanho,
                                                    "unit": "PT"
                                                },
                                                "bold": True
                                            },
                                            "fields": "fontSize,bold"
                                        }
                                    }
                                ]
                            }
                        ).execute()
                        
                        self.logger.info(f"Título formatado com tamanho {tamanho}pt")
                        break
        
        except Exception as e:
            self.logger.warning(f"Erro ao formatar título: {e}")
    
    def _mover_para_pasta(self, document_id: str, folder_id: str) -> None:
        """
        Move o documento para a pasta especificada no Google Drive.
        
        Args:
            document_id: ID do documento a ser movido
            folder_id: ID da pasta de destino
        """
        try:
            # Adiciona a pasta como pai do arquivo
            self.service_drive.files().update(
                fileId=document_id,
                addParents=folder_id,
                removeParents='root',  # Remove da pasta raiz/anterior
                fields='id, parents'
            ).execute()
            
            self.logger.info(f"Documento {document_id} movido para a pasta {folder_id}")
        
        except Exception as e:
            self.logger.warning(f"Erro ao mover documento para a pasta: {e}")
            # Isso não deve interromper o fluxo principal, apenas logamos o erro 
    
    def obter_conteudo_documento(self, document_id: str) -> str:
        """
        Recupera o conteúdo de um documento do Google Docs.
        
        Args:
            document_id: ID do documento do Google Docs a ser recuperado
            
        Returns:
            Conteúdo do documento como texto
        """
        try:
            # Obtém o documento
            documento = self.service_docs.documents().get(documentId=document_id).execute()
            
            # Extrai o conteúdo do documento
            conteudo = ''
            if 'body' in documento and 'content' in documento['body']:
                for elemento in documento['body']['content']:
                    if 'paragraph' in elemento:
                        for item in elemento['paragraph']['elements']:
                            if 'textRun' in item and 'content' in item['textRun']:
                                conteudo += item['textRun']['content']
            
            self.logger.info(f"Conteúdo do documento {document_id} recuperado com sucesso ({len(conteudo)} caracteres)")
            return conteudo
        
        except Exception as e:
            self.logger.error(f"Erro ao recuperar conteúdo do documento {document_id}: {e}")
            raise
    
    def atualizar_documento(self, document_id: str, titulo: str, conteudo: str, nome_arquivo: str, info_link: dict = None) -> tuple:
        """
        Atualiza um documento existente no Google Docs com novo título e conteúdo.
        
        Args:
            document_id: ID do documento existente
            titulo: Novo título para o documento
            conteudo: Novo conteúdo do documento
            nome_arquivo: Nome para identificar o documento
            info_link: Informações sobre o link inserido no conteúdo
            
        Returns:
            Tupla (document_id, document_url)
        """
        try:
            # Primeiro, renomeia o documento
            self.service_drive.files().update(
                fileId=document_id,
                body={'name': nome_arquivo}
            ).execute()
            
            # Prepara o conteúdo (titulo + corpo)
            conteudo_completo = f"{titulo}\n\n{conteudo}"
            
            # Limpa o documento existente
            self.service_docs.documents().batchUpdate(
                documentId=document_id,
                body={
                    'requests': [
                        {
                            'deleteContentRange': {
                                'range': {
                                    'startIndex': 1,
                                    'endIndex': self._obter_tamanho_documento(document_id)
                                }
                            }
                        }
                    ]
                }
            ).execute()
            
            # Insere o novo conteúdo
            self.service_docs.documents().batchUpdate(
                documentId=document_id,
                body={
                    'requests': [
                        {
                            'insertText': {
                                'location': {
                                    'index': 1
                                },
                                'text': conteudo_completo
                            }
                        }
                    ]
                }
            ).execute()
            
            # Formata o título (primeira linha) como H1
            self.service_docs.documents().batchUpdate(
                documentId=document_id,
                body={
                    'requests': [
                        {
                            'updateParagraphStyle': {
                                'range': {
                                    'startIndex': 1,
                                    'endIndex': len(titulo) + 1
                                },
                                'paragraphStyle': {
                                    'namedStyleType': 'HEADING_1'
                                },
                                'fields': 'namedStyleType'
                            }
                        }
                    ]
                }
            ).execute()
            
            # Se houver informações de link, formata o link
            if info_link and 'inicio' in info_link and 'fim' in info_link:
                # Ajusta os índices para o documento atualizado (adiciona o tamanho do título + 2 quebras de linha)
                offset = len(titulo) + 2
                inicio_link = info_link['inicio'] + offset
                fim_link = info_link['fim'] + offset
                
                # Adiciona o link
                self.service_docs.documents().batchUpdate(
                    documentId=document_id,
                    body={
                        'requests': [
                            {
                                'updateTextStyle': {
                                    'range': {
                                        'startIndex': inicio_link,
                                        'endIndex': fim_link
                                    },
                                    'textStyle': {
                                        'link': {
                                            'url': info_link['url']
                                        }
                                    },
                                    'fields': 'link'
                                }
                            }
                        ]
                    }
                ).execute()
            
            # Obtém a URL do documento
            document_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            self.logger.info(f"Documento {document_id} atualizado com sucesso")
            return document_id, document_url
        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar documento {document_id}: {e}")
            raise
            
    def _obter_tamanho_documento(self, document_id: str) -> int:
        """
        Obtém o tamanho total (número de caracteres) de um documento.
        
        Args:
            document_id: ID do documento
            
        Returns:
            Número de caracteres no documento
        """
        documento = self.service_docs.documents().get(documentId=document_id).execute()
        return documento.get('body', {}).get('content', [])[-1].get('endIndex', 0) 