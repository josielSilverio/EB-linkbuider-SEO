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
    
    def criar_documento(self, titulo: str, conteudo: str, nome_arquivo: str) -> Tuple[str, str]:
        """
        Cria um novo documento no Google Docs e o salva na pasta especificada.
        
        Args:
            titulo: Título do documento
            conteudo: Conteúdo (markdown) a ser inserido no documento
            nome_arquivo: Nome do arquivo para o documento
        
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
            
            # Extrai os títulos do markdown (para formatação)
            titulos = extrair_titulos_markdown(conteudo)
            
            # Converte o markdown para requests da API do Docs
            requests = converter_markdown_para_docs(conteudo)
            
            # Aplica as atualizações ao documento
            if requests:
                self.service_docs.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": requests}
                ).execute()
                self.logger.info(f"Conteúdo inserido no documento {document_id}")
            
            # Formata o título principal (H1) para tamanho 17
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