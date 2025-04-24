# SEO-LinkBuilder - Versão 2.0

Automatização para geração de artigos otimizados para SEO utilizando a API do Google Gemini, Google Sheets, Google Docs e Google Drive, com suporte a múltiplas planilhas e abas.

## Descrição

Este projeto automatiza o fluxo de trabalho para geração de conteúdo SEO a partir de dados em planilhas do Google Sheets. O script:

1.  Permite selecionar a planilha e aba desejada.
2.  Lê os dados da aba selecionada.
3.  Apresenta um menu interativo para selecionar categorias de trabalho (baseado na coluna "Palavra-Âncora") ou uma quantidade específica de itens.
4.  Estima o custo de processamento com base na seleção.
5.  Gera artigos otimizados utilizando a API do Gemini para os itens selecionados.
6.  Cria documentos no Google Docs com o conteúdo gerado, salvando-os em uma pasta específica no Google Drive.
7.  Atualiza a planilha original com os títulos gerados e as URLs dos documentos criados nas colunas corretas.
8.  Opcionalmente, realiza verificações de qualidade (títulos duplicados, similaridade de conteúdo, termos proibidos) após a geração.

## Funcionalidades Principais

- **Seleção de Planilha/Aba**: Menu interativo para escolher qual planilha e aba do Google Sheets usar.
- **Menu de Categorias Interativo**: Selecione categorias específicas (baseadas na palavra-âncora), todos os itens, ou uma quantidade aleatória para processar.
- **Estimativa de Custos**: Visualize o custo estimado por categoria e total antes de executar o processamento.
- **Geração de Artigos com Gemini AI**: Cria conteúdo otimizado para SEO, incluindo links âncora de forma natural.
- **Integração Completa**: Google Sheets, Google Docs e Google Drive em um fluxo automatizado.
- **Controle de Qualidade**: Funções para verificar e corrigir títulos duplicados, conteúdos com alta similaridade e termos proibidos (executadas após a geração principal, se não houver limite de linhas).
- **Detecção e Substituição de Termos Proibidos**: Sistema automático para manter o conteúdo de acordo com as políticas.

## Pré-requisitos

- Python 3.7 ou superior
- Acesso às seguintes APIs do Google Cloud:
  - Google Sheets API
  - Google Docs API
  - Google Drive API
  - Google AI (Gemini API)
- Credenciais OAuth2 para as APIs do Google Cloud (arquivo `credentials.json`)
- Chave de API para o Google Gemini

## Instalação

1.  Clone este repositório:
    ```bash
    git clone https://seu-repositorio/SEO-LinkBuilder.git
    cd SEO-LinkBuilder
    ```

2.  Crie e ative um ambiente virtual Python:
    ```bash
    python -m venv venv
    # No Windows:
    # venv\Scripts\activate.bat  (CMD)
    # .\venv\Scripts\Activate.ps1 (PowerShell)
    # No Linux/Mac:
    # source venv/bin/activate
    ```

3.  Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

4.  Crie um arquivo `.env` na raiz do projeto e configure as variáveis de ambiente. Use o exemplo abaixo como base:
    ```dotenv
    # Credenciais e Configurações - NÃO FAÇA COMMIT DESTE ARQUIVO!
    
    # Google Cloud / Gemini API Key
    GOOGLE_API_KEY="SUA_API_KEY_GEMINI_AQUI"
    GOOGLE_CLOUD_API_KEY="SUA_API_KEY_GOOGLE_CLOUD_AQUI" # Opcional, pode ser a mesma acima
    
    # Google Sheets (Padrão, pode ser alterado no menu)
    SPREADSHEET_ID="ID_DA_SUA_PLANILHA_PADRAO"
    SHEET_NAME="NOME_DA_ABA_PADRAO"
    
    # Google Drive
    DRIVE_FOLDER_ID="ID_DA_PASTA_NO_DRIVE_PARA_SALVAR_DOCS"
    
    # Caminho para o arquivo de credenciais OAuth 2.0
    CREDENTIALS_FILE_PATH="credentials/credentials.json"
    
    # Configurações do Gemini
    GEMINI_MODEL="gemini-1.5-flash" # Ou outro modelo disponível
    GEMINI_MAX_OUTPUT_TOKENS="8192"
    GEMINI_TEMPERATURE="0.3"
    
    # Preços Gemini (USD por 1000 tokens) - Verifique os preços atuais!
    GEMINI_PRECO_ENTRADA="0.00025"
    GEMINI_PRECO_SAIDA="0.0005"
    
    # Formato para nome de arquivo do Google Docs
    NOME_ARQUIVO_PADRAO="{id} - {site} - {ancora}"
    
    # (Opcional) Configurações de formatação para os documentos (padrões definidos no código)
    # TITULO_TAMANHO=17
    # SUBTITULOS_ESTILO="NEGRITO"
    # CONTEUDO_COLUNA_DRIVE="L"
    ```

5.  Coloque seu arquivo de credenciais OAuth (`credentials.json`) na pasta `credentials/`. Este arquivo é obtido no Google Cloud Console ao criar credenciais do tipo "OAuth 2.0 Client ID" para "Desktop app".

## Uso

Execute o script principal a partir do terminal, com o ambiente virtual ativado:

```bash
# Execução padrão (processa 10 linhas após seleção)
python main.py

# Modo teste (processa apenas a PRIMEIRA linha selecionada, mas ATUALIZA a planilha para essa linha)
python main.py --teste

# Processar um número específico de linhas após seleção
python main.py --limite 5

# Processar todas as linhas selecionadas (sem limite)
python main.py --todos
```

### Menus Interativos

Ao executar, o script apresentará os seguintes menus:

1.  **Seleção de Planilha/Aba**: Permite usar a configuração padrão do `.env` ou inserir manualmente o ID da planilha e o nome da aba desejada.
2.  **Seleção de Categorias/Quantidade**: Mostra um resumo dos itens encontrados na aba selecionada, agrupados por categorias (baseadas na palavra-âncora). Permite escolher processar:
    *   Todos os itens.
    *   Itens de uma categoria específica.
    *   Uma quantidade específica de itens aleatórios.
3.  **Confirmação de Custo**: Exibe o custo total estimado para a seleção feita e pede confirmação para prosseguir.

## Estrutura do Projeto

```
SEO-LinkBuilder/
├── venv/                   # Ambiente virtual Python (ignorado pelo Git)
├── src/                    # Código fonte principal
│   ├── __init__.py
│   ├── auth_handler.py     # Gerencia a autenticação OAuth2 com as APIs do Google.
│   │   └── obter_credenciais(): Obtém ou renova as credenciais do usuário.
│   │   └── criar_servico_sheets(): Cria o objeto de serviço para a API do Sheets.
│   │   └── criar_servico_docs(): Cria o objeto de serviço para a API do Docs.
│   │   └── criar_servico_drive(): Cria o objeto de serviço para a API do Drive.
│   ├── sheets_handler.py   # Interage com a API do Google Sheets.
│   │   └── SheetsHandler(): Classe principal.
│   │       ├── ler_planilha(): Lê dados da planilha, filtra por ID válido e adiciona índice original.
│   │       ├── atualizar_url_documento(): Atualiza a célula da URL do Doc na linha correta.
│   │       ├── atualizar_titulo_documento(): Atualiza a célula do Título/Tema na linha correta.
│   │       ├── obter_abas_disponiveis(): Lista as abas de uma planilha.
│   │       └── extrair_dados_linha(): Extrai dados de uma linha do DataFrame.
│   ├── gemini_handler.py   # Interage com a API do Google Gemini.
│   │   └── GeminiHandler(): Classe principal.
│   │       ├── gerar_conteudo(): Constrói o prompt e chama a API Gemini para gerar o artigo.
│   │       ├── carregar_prompt_template(): Carrega o modelo de prompt do arquivo.
│   │       └── verificar_conteudo_proibido(): Verifica e substitui termos proibidos.
│   ├── docs_handler.py     # Interage com as APIs do Google Docs e Drive.
│   │   └── DocsHandler(): Classe principal.
│   │       ├── criar_documento(): Cria um novo Google Doc na pasta especificada.
│   │       ├── atualizar_documento(): Substitui o conteúdo de um Doc existente.
│   │       ├── obter_conteudo_documento(): Lê o texto de um Google Doc.
│   │       └── formatar_documento(): Aplica formatação básica (títulos, parágrafos, links).
│   ├── config.py           # Carrega configurações do arquivo .env e define constantes.
│   │   └── COLUNAS: Dicionário mapeando nomes lógicos de colunas para seus índices numéricos.
│   │   └── MESES: Dicionário de meses (usado no menu antigo, pode ser removido).
│   │   └── gerar_nome_arquivo(): Cria o nome do arquivo para o Google Doc.
│   │   └── estimar_custo_gemini(): Calcula o custo estimado da API Gemini.
│   └── utils.py            # Funções utilitárias diversas.
│       └── configurar_logging(): Configura o sistema de logs (console e arquivo UTF-8).
│       └── converter_markdown_para_docs(): Converte texto para o formato da API do Docs.
│       └── contar_tokens(): Estima a contagem de tokens para a API Gemini.
│       └── substituir_links_markdown(): Encontra a palavra-âncora no texto gerado.
├── credentials/            # Diretório para armazenar credentials.json e token.json
│   └── credentials.json    # Arquivo de credenciais OAuth 2.0 (NÃO INCLUIR NO GIT)
│   └── token.json          # Token de acesso gerado automaticamente (NÃO INCLUIR NO GIT)
├── data/                   # Arquivos de dados/templates
│   └── prompt.txt          # O prompt base usado para gerar conteúdo com o Gemini.
├── logs/                   # Logs de execução (criado automaticamente, ignorado pelo Git)
├── main.py                 # Ponto de entrada principal do script. Orquestra o fluxo.
│   └── main(): Função principal que executa os menus e o loop de processamento.
│   └── apresentar_menu_planilha(): Exibe o menu para seleção de planilha/aba.
│   └── estimar_custo_por_categoria(): Calcula custos por grupo de palavra-âncora.
│   └── apresentar_menu_categorias(): Exibe o menu de seleção de categorias/quantidade.
│   └── filtrar_dataframe_por_categorias(): Filtra o DataFrame com base na seleção do menu.
│   └── verificar_titulos_duplicados(): Função de controle de qualidade.
│   └── verificar_similaridade_conteudos(): Função de controle de qualidade.
│   └── corrigir_termos_proibidos(): Função de controle de qualidade.
├── requirements.txt        # Lista de dependências Python.
├── .env                    # Arquivo para variáveis de ambiente (NÃO INCLUIR NO GIT).
└── README.md               # Este arquivo.
└── .gitignore              # Arquivo para especificar o que o Git deve ignorar.
```

## Formato Esperado da Planilha

Para que o script funcione corretamente, a planilha selecionada deve ter colunas com os seguintes dados (a ordem exata das colunas é definida em `src/config.py` -> `COLUNAS`):

- **ID**: Identificador único da linha/campanha (Coluna A por padrão).
- **Site**: Nome do site relacionado (Coluna B por padrão).
- **Palavra-Âncora**: A palavra ou frase que será usada como âncora para o link interno (Coluna G por padrão). Usada também para agrupar no menu de categorias.
- **URL da Âncora**: O link de destino para a palavra-âncora (Coluna H por padrão).
- **Título/Tema**: O tema ou título base para a geração do artigo (Coluna I por padrão). Esta coluna **será sobrescrita** com o título gerado pelo Gemini.
- **URL do Documento**: Coluna onde a URL do Google Doc gerado será inserida (Coluna J por padrão). Esta coluna **será sobrescrita**.

*Observação: Outras colunas podem existir, mas não são diretamente utilizadas pelo fluxo principal de geração e atualização.* 

## Personalização

- Edite o arquivo `data/prompt.txt` para modificar as instruções e o estilo do conteúdo gerado pelo Gemini.
- Ajuste as configurações no arquivo `.env` para mudar IDs padrão, chaves de API, modelo Gemini, etc.
- Modifique o dicionário `COLUNAS` em `src/config.py` se a estrutura da sua planilha for diferente.

## Solução de Problemas

- **Erro de Autenticação/Token**: Se encontrar erros como `RefreshError` ou relacionados a permissões:
    1.  Verifique se o arquivo `credentials/credentials.json` está correto e se foi gerado para "Desktop app".
    2.  Certifique-se de que as APIs (Sheets, Docs, Drive) estão ativadas no Google Cloud Console para o projeto associado às credenciais.
    3.  **Delete o arquivo `credentials/token.json`** (ele será recriado na próxima execução) e autorize o aplicativo novamente no navegador quando solicitado.
- **Erro `Unable to parse range`**: Geralmente indica que o nome da aba (`SHEET_NAME`) fornecido no `.env` ou no menu não corresponde exatamente a uma aba existente na planilha selecionada (`SPREADSHEET_ID`). Verifique maiúsculas/minúsculas e espaços.
- **Erros de Codificação (`UnicodeEncodeError`/`UnicodeDecodeError`)**: Certifique-se de que o arquivo `.env` está salvo com codificação **UTF-8**. As correções recentes no código devem lidar com a leitura e escrita em UTF-8, mas a fonte original (`.env`) precisa estar correta.
- **Planilha não Atualiza**: Verifique os logs (`logs/seo_linkbuilder_*.log`). Os logs detalhados agora mostram exatamente qual célula o script tentou atualizar. Confirme se o `indice_original_linha` nos logs corresponde à linha que você esperava atualizar na planilha.

## Custos

- O uso das APIs do Google Sheets, Docs e Drive geralmente se enquadra nos limites gratuitos para uso normal.
- A API do Gemini **tem custos** baseados no número de tokens de entrada (prompt) e saída (texto gerado). Consulte a documentação oficial do Google AI para os preços atualizados do modelo configurado (`GEMINI_MODEL` no `.env`).
- O script exibe uma estimativa de custo antes de iniciar o processamento em lote.

## Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir *issues* e *pull requests*. 