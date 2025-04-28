# Módulo para interagir com as APIs do Google Docs e Drive
import logging
from typing import Dict, List, Tuple, Optional
import re

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
    
    @staticmethod
    def extrair_id_da_url(url: str) -> str:
        """
        Extrai o ID de um documento ou pasta do Google Drive a partir da URL.
        
        Args:
            url: URL do Google Drive/Docs/Sheets
            
        Returns:
            ID extraído da URL
        """
        # Padrões de regex para diferentes formatos de URL do Google
        padroes = [
            r"https://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)",  # Drive folder URL
            r"https://drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9_-]+)",  # Drive folder with user number
            r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",  # Docs URL
            r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",  # Sheets URL
            r"^([a-zA-Z0-9_-]{25,})"  # Raw ID (já é um ID)
        ]
        
        for padrao in padroes:
            match = re.search(padrao, url)
            if match:
                return match.group(1)
        
        # Se não encontrar nenhum ID válido
        return ""
    
    def criar_documento(self, titulo: str, conteudo: str, nome_arquivo: str, info_link=None, target_folder_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Cria um novo documento no Google Docs e o salva na pasta especificada.
        
        Args:
            titulo: Título do documento
            conteudo: Conteúdo em formato natural para o documento
            nome_arquivo: Nome do arquivo para o documento
            info_link: Informações para adicionar link à palavra âncora (opcional)
            target_folder_id: ID da pasta de destino no Drive (opcional, usa config se None)
        
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
            
            # Define a pasta de destino
            folder_id_destino = target_folder_id if target_folder_id else DRIVE_FOLDER_ID
            
            # Verifica se a pasta existe antes de tentar mover
            pasta_existe = self._verificar_pasta(folder_id_destino)
            
            if not pasta_existe:
                # A pasta não existe, criar uma nova para armazenar os documentos
                self.logger.warning(f"A pasta com ID {folder_id_destino} não existe ou você não tem acesso.")
                folder_id_destino = self._criar_pasta_documentos()
            
            # Move o arquivo para a pasta especificada no Drive
            self._mover_para_pasta(document_id, folder_id_destino)
            
            # Configura as permissões do documento para o usuário atual
            self._configurar_permissoes_documento(document_id)
            
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
        if not folder_id:
             self.logger.warning(f"Nenhum ID de pasta de destino fornecido para mover o documento {document_id}. O documento permanecerá na raiz.")
             return
        try:
            # Tenta verificar se a pasta de destino existe
            try:
                folder = self.service_drive.files().get(
                    fileId=folder_id,
                    fields='id,name,mimeType',
                    supportsAllDrives=True
                ).execute()
                
                self.logger.info(f"Pasta de destino verificada: ID={folder.get('id')}, Nome={folder.get('name')}")
                
                # Verifica se é realmente uma pasta
                if folder.get('mimeType') != 'application/vnd.google-apps.folder':
                    self.logger.error(f"O ID {folder_id} não é de uma pasta! MimeType: {folder.get('mimeType')}")
                    return
                    
            except Exception as e:
                self.logger.error(f"Erro ao verificar a pasta de destino {folder_id}: {e}")
                self.logger.info("Tentando mover o documento mesmo assim...")
            
            # Adiciona a pasta como pai do arquivo
            self.logger.info(f"Tentando mover documento {document_id} para a pasta {folder_id}...")
            
            resultado = self.service_drive.files().update(
                fileId=document_id,
                addParents=folder_id,
                removeParents='root',  # Remove da pasta raiz/anterior
                fields='id, parents',
                supportsAllDrives=True  # Suporte para shared drives
            ).execute()
            
            self.logger.info(f"Documento {document_id} movido com sucesso para a pasta {folder_id}")
            self.logger.info(f"Resultado da operação: {resultado}")
        
        except Exception as e:
            self.logger.warning(f"Erro ao mover documento para a pasta: {e}")
            self.logger.warning(f"Detalhes do erro: Documento ID={document_id}, Pasta ID={folder_id}")
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

    def _verificar_pasta(self, folder_id: str) -> bool:
        """
        Verifica se uma pasta existe e está acessível.
        
        Args:
            folder_id: ID da pasta a verificar
            
        Returns:
            True se a pasta existe e é acessível, False caso contrário
        """
        if not folder_id or folder_id == "root":
            self.logger.info("Usando pasta raiz do Google Drive.")
            return True
            
        try:
            pasta = self.service_drive.files().get(
                fileId=folder_id,
                fields='id,name,mimeType',
                supportsAllDrives=True
            ).execute()
            
            # Verifica se é realmente uma pasta
            if pasta.get('mimeType') != 'application/vnd.google-apps.folder':
                self.logger.warning(f"O ID {folder_id} não é uma pasta! É um: {pasta.get('mimeType')}")
                return False
                
            self.logger.info(f"Pasta de destino verificada: {pasta.get('name')} (ID: {pasta.get('id')})")
            return True
            
        except Exception as e:
            self.logger.warning(f"Erro ao verificar pasta {folder_id}: {e}")
            return False
    
    def _criar_pasta_documentos(self) -> str:
        """
        Cria uma nova pasta para armazenar os documentos.
        
        Returns:
            ID da pasta criada
        """
        try:
            # Cria uma nova pasta com nome datado
            import datetime
            agora = datetime.datetime.now()
            data_atual = agora.strftime("%Y-%m-%d_%H-%M-%S")
            nome_pasta = f"SEO-LinkBuilder_{data_atual}"
            
            file_metadata = {
                'name': nome_pasta,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            pasta = self.service_drive.files().create(
                body=file_metadata,
                fields='id,name,webViewLink'
            ).execute()
            
            pasta_id = pasta.get('id')
            self.logger.info(f"Nova pasta criada para armazenar documentos: {nome_pasta} (ID: {pasta_id})")
            self.logger.info(f"Link da pasta: {pasta.get('webViewLink', 'N/A')}")
            
            # Atualizar o DRIVE_FOLDER_ID para uso futuro
            # Nota: Isso apenas atualiza a variável em memória, não o arquivo de configuração
            global DRIVE_FOLDER_ID
            DRIVE_FOLDER_ID = pasta_id
            
            return pasta_id
            
        except Exception as e:
            self.logger.error(f"Erro ao criar pasta para documentos: {e}")
            # Em caso de erro, retorna 'root' (pasta raiz do Drive)
            self.logger.warning("Usando pasta raiz do Drive como alternativa")
            return "root"

    def _configurar_permissoes_documento(self, document_id: str) -> None:
        """
        Configura as permissões do documento para garantir que o proprietário tenha acesso total.
        
        Args:
            document_id: ID do documento a configurar
        """
        try:
            # Verifica quem é o proprietário atual do documento
            file_info = self.service_drive.files().get(
                fileId=document_id,
                fields='owners,permissions',
                supportsAllDrives=True
            ).execute()
            
            self.logger.info("Configurando permissões do documento...")
            
            # Define permissão para qualquer pessoa com o link poder visualizar
            permission = {
                'type': 'anyone',
                'role': 'reader',
                'allowFileDiscovery': False
            }
            
            result = self.service_drive.permissions().create(
                fileId=document_id,
                body=permission,
                fields='id',
                sendNotificationEmail=False
            ).execute()
            
            self.logger.info(f"Permissão configurada para acesso via link: {result.get('id')}")
            
            # Também podemos configurar permissões específicas para o domínio, se necessário
            # Exemplo para permissão de domínio:
            # domain_permission = {
            #     'type': 'domain',
            #     'role': 'reader',
            #     'domain': 'estrelabet.com',
            #     'allowFileDiscovery': True
            # }
            # self.service_drive.permissions().create(
            #     fileId=document_id,
            #     body=domain_permission,
            #     fields='id'
            # ).execute()
            
        except Exception as e:
            self.logger.warning(f"Erro ao configurar permissões do documento {document_id}: {e}")
            # Não interrompe o fluxo principal 