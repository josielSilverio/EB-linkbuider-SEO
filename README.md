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

## Manual dos Scripts: Entendendo os Arquivos

Aqui está um guia rápido sobre os principais arquivos de script (`.py`) neste projeto, para que servem e o que você pode querer ajustar:

### 📄 `main.py` - O Maestro da Orquestra

*   **Para que serve?** É o ponto de entrada principal. Ele coordena todo o processo: chama os menus, lê a planilha através do `sheets_handler`, filtra os dados com base na sua escolha, chama o `gemini_handler` para gerar o texto, usa o `docs_handler` para criar os documentos e, finalmente, atualiza a planilha.
*   **Funções Principais:**
    *   `main()`: A função principal que executa todo o fluxo.
    *   `apresentar_menu_planilha()`: Mostra o menu para você escolher a planilha e a aba.
    *   `estimar_custo_por_categoria()`: Calcula o custo estimado para cada grupo de palavras-chave.
    *   `apresentar_menu_categorias()`: Mostra o menu para escolher quais categorias ou quantidade processar.
    *   `filtrar_dataframe_por_categorias()`: Seleciona as linhas da planilha com base na sua escolha no menu.
    *   `verificar_titulos_duplicados()`, `verificar_similaridade_conteudos()`, `corrigir_termos_proibidos()`: Funções de controle de qualidade executadas no final (se não usar `--limite`).
*   **O que você pode alterar (e por quê):**
    *   **Textos dos Menus:** Você pode editar os textos (`print` e `input`) dentro das funções `apresentar_menu_*` para mudar como os menus aparecem para você.
    *   **Confirmação de Custo:** Alterar o texto da pergunta `input()` que pede confirmação antes de processar.
    *   **Lógica de Processamento:** Modificar o loop `for i, (idx, linha) in enumerate(df_filtrado.iterrows()):` se precisar processar as linhas de forma diferente (mas cuidado para manter a lógica de atualização correta!).
    *   **Controle de Qualidade:** Comentar (`#`) as chamadas para `verificar_titulos_duplicados`, `verificar_similaridade_conteudos` ou `corrigir_termos_proibidos` no final da função `main` se não quiser executar essas verificações (por exemplo, para acelerar o processo).

### ⚙️ `src/config.py` - O Painel de Controle

*   **Para que serve?** Este arquivo carrega as configurações do seu arquivo `.env` e define constantes importantes usadas em todo o projeto, como os nomes das colunas da planilha ou o formato do nome do arquivo.
*   **Elementos Principais:**
    *   Carregamento das variáveis do `.env` (como `SPREADSHEET_ID`, `SHEET_NAME`, `DRIVE_FOLDER_ID`, chaves de API, configurações do Gemini).
    *   `COLUNAS`: **Muito importante!** Mapeia nomes como `'id'`, `'palavra_ancora'`, `'titulo'` para os *números* das colunas na sua planilha (A=0, B=1, C=2, ...).
    *   `NOME_ARQUIVO_PADRAO`: Define como o nome dos arquivos do Google Docs será montado.
    *   `GEMINI_PRECO_ENTRADA`, `GEMINI_PRECO_SAIDA`: Preços usados para estimar o custo.
    *   `gerar_nome_arquivo()`: Função que cria o nome do arquivo com base no padrão.
    *   `estimar_custo_gemini()`: Função que calcula o custo estimado de uma chamada Gemini.
*   **O que você pode alterar (e por quê):**
    *   **Mapeamento de Colunas (`COLUNAS`):** **Se a estrutura da sua planilha mudar**, você *PRECISA* atualizar os números (índices) neste dicionário para que o script leia e escreva nas colunas corretas.
    *   **Padrão de Nome de Arquivo (`NOME_ARQUIVO_PADRAO`):** Altere a string de formato (ex: `"{id} - {ancora}"`) se quiser que os nomes dos documentos gerados sejam diferentes.
    *   **Preços do Gemini:** Atualize os valores `GEMINI_PRECO_*` se o Google alterar os preços, para manter as estimativas de custo precisas (é carregado do `.env`, então altere lá).
    *   **Lógica de `gerar_nome_arquivo()`:** Se precisar de uma lógica mais complexa para nomes de arquivo do que o padrão permite, você pode modificar esta função.
    *   **Configurações Padrão:** Os valores padrão (ex: `"gemini-1.5-pro"` se a variável não estiver no `.env`) podem ser alterados aqui, mas é melhor definir tudo no `.env`.

### 🔑 `src/auth_handler.py` - O Porteiro das APIs

*   **Para que serve?** Cuida da parte chata de fazer login na sua conta Google de forma segura (OAuth2) para permitir que o script acesse Sheets, Docs e Drive em seu nome. Ele gerencia o token de acesso.
*   **Funções Principais:**
    *   `obter_credenciais()`: Lida com o fluxo de login, pedindo sua autorização no navegador na primeira vez ou quando o token expira, e salva/lê o `token.json`.
    *   `criar_servico_sheets()`, `criar_servico_docs()`, `criar_servico_drive()`: Usam as credenciais obtidas para criar os objetos que permitem interagir com cada API.
*   **O que você pode alterar (e por quê):**
    *   **Escopos (`SCOPES`):** A lista `SCOPES` define quais permissões o script pede (ler/escrever planilhas, documentos, drive). Você *poderia* alterar isso se precisasse de mais ou menos permissões, mas geralmente as atuais são as necessárias.
    *   **Nome do Arquivo de Token:** Você pode mudar o nome `'credentials/token.json'` se quiser salvar o token em outro lugar, mas normalmente não há motivo.
    *   **Caminho das Credenciais:** O caminho para `credentials.json` é lido do `config.py` (que lê do `.env`). Altere no `.env` se necessário.

### 📊 `src/sheets_handler.py` - O Arquivista da Planilha

*   **Para que serve?** É responsável por toda a comunicação com o Google Sheets: ler os dados da aba que você escolheu e escrever de volta a URL do documento e o título gerado na linha correta.
*   **Funções Principais:**
    *   `SheetsHandler()`: A classe que inicializa o serviço.
    *   `ler_planilha()`: Lê os dados da planilha, remove cabeçalho, filtra linhas com ID inválido e, crucialmente, adiciona a coluna `linha_original` para saber a posição real de cada linha.
    *   `atualizar_url_documento()`: Escreve a URL na coluna correta (J por padrão) da linha original.
    *   `atualizar_titulo_documento()`: Escreve o título na coluna correta (I por padrão) da linha original.
    *   `obter_abas_disponiveis()`: Usada pelo menu para listar as abas.
*   **O que você pode alterar (e por quê):**
    *   **Range de Leitura (`ler_planilha`):** A linha `range=f"{nome_aba}!A:O"` define que ele lê as colunas de A até O. Se precisar de mais ou menos colunas, ajuste aqui (mas lembre-se de atualizar o `COLUNAS` no `config.py` se a posição das colunas usadas mudar).
    *   **Validação de ID (`is_valid_id` dentro de `ler_planilha`):** Se seus IDs tiverem um formato específico ou se houver outros textos na coluna de ID que você quer ignorar, pode ajustar a lógica desta sub-função.
    *   **Colunas de Atualização (`atualizar_*`):** As letras das colunas onde o Título (`'I'`) e a URL (`'J'`) são escritos estão definidas diretamente nestas funções. Se precisar mudar essas colunas de destino na sua planilha, altere essas letras aqui.

### ✨ `src/gemini_handler.py` - O Escritor Criativo (IA)

*   **Para que serve?** Este módulo conversa com a API do Google Gemini. Ele pega os dados da planilha, monta uma instrução (prompt) e pede ao Gemini para gerar o texto do artigo.
*   **Funções Principais:**
    *   `GeminiHandler()`: A classe que inicializa a API Gemini com suas configurações.
    *   `gerar_conteudo()`: A função principal que recebe os dados, chama `_construir_prompt` e envia para o Gemini.
    *   `carregar_prompt_template()`: Lê o arquivo `data/prompt.txt`.
    *   `_construir_prompt()`: Substitui os placeholders (como `{palavra_ancora}`) no template do prompt com os dados da linha atual.
    *   `verificar_conteudo_proibido()`: Procura por termos inadequados no texto gerado e os substitui.
*   **O que você pode alterar (e por quê):**
    *   **Edição do Prompt:** A maneira mais comum de alterar a saída do Gemini é **editando o arquivo `data/prompt.txt`**. Mude as instruções, o tom, o estilo, etc., diretamente lá.
    *   **Construção do Prompt (`_construir_prompt`):** Se você adicionar novas colunas na planilha com informações que quer passar para o Gemini, precisará adicionar novos placeholders no `prompt.txt` e atualizar esta função para incluir esses novos dados no prompt final.
    *   **Configurações de Geração (no `.env`):** Altere `GEMINI_MODEL`, `GEMINI_MAX_OUTPUT_TOKENS` e `GEMINI_TEMPERATURE` no seu arquivo `.env` para usar outro modelo, controlar o tamanho máximo da resposta ou ajustar a criatividade/aleatoriedade do texto.
    *   **Configurações de Segurança (`safety_settings`):** Você pode ajustar os níveis de bloqueio para diferentes categorias de conteúdo potencialmente prejudicial, mas cuidado para não ser restritivo demais.
    *   **Termos Proibidos (`TERMOS_PROIBIDOS`):** Adicione ou remova palavras da lista `TERMOS_PROIBIDOS` dentro da função `verificar_conteudo_proibido` para controlar quais termos são automaticamente filtrados/substituídos.

### 📑 `src/docs_handler.py` - O Editor e Organizador de Documentos

*   **Para que serve?** Ele cria os novos arquivos no Google Docs, insere o texto gerado pelo Gemini, aplica alguma formatação básica (títulos, negrito, links) e salva o documento na pasta correta do Google Drive.
*   **Funções Principais:**
    *   `DocsHandler()`: A classe que inicializa os serviços do Docs e Drive.
    *   `criar_documento()`: Cria um novo Google Doc em branco na pasta definida no `.env` (`DRIVE_FOLDER_ID`).
    *   `atualizar_documento()`: Usado pelas funções de controle de qualidade para substituir o conteúdo de um documento existente.
    *   `formatar_documento()`: Chama a função `converter_markdown_para_docs` (do `utils.py`) para preparar os comandos de formatação e os aplica ao documento.
    *   `obter_conteudo_documento()`: Usado pelas funções de controle de qualidade para ler o texto de um documento existente.
*   **O que você pode alterar (e por quê):**
    *   **Pasta do Drive (no `.env`):** Altere o `DRIVE_FOLDER_ID` no arquivo `.env` para salvar os documentos em uma pasta diferente.
    *   **Formatação de Documento:** A maior parte da lógica de formatação está na função `converter_markdown_para_docs` em `src/utils.py`. Se quiser mudar tamanhos de fonte, negrito, estilos de título, cores de link, etc., você precisará modificar as estruturas de `requests` criadas naquela função.

### 🛠️ `src/utils.py` - A Caixa de Ferramentas

*   **Para que serve?** Contém funções auxiliares usadas por outros módulos. Coisas como configurar os logs, processar texto, contar tokens, etc.
*   **Funções Principais:**
    *   `configurar_logging()`: Define como as mensagens de log são exibidas (no console e no arquivo `.log`) e garante o uso de UTF-8.
    *   `converter_markdown_para_docs()`: Pega o texto simples gerado pelo Gemini e o transforma nos comandos que a API do Google Docs entende para criar títulos, parágrafos e aplicar o link âncora.
    *   `contar_tokens()`: Estima quantos tokens um texto usará na API Gemini (útil para prever custos).
    *   `substituir_links_markdown()`: Encontra a `palavra_ancora` no texto gerado para que a função de formatação saiba onde inserir o link.
*   **O que você pode alterar (e por quê):**
    *   **Formato do Log (`configurar_logging`):** Altere a string `format=` se quiser que as mensagens de log tenham uma aparência diferente.
    *   **Lógica de Conversão (`converter_markdown_para_docs`):** Se o Gemini começar a gerar texto com marcações diferentes (além de simples parágrafos e talvez títulos implícitos) ou se você quiser formatar listas, etc., teria que aprimorar a lógica aqui para identificar e converter essas estruturas.
    *   **Lógica de Encontrar Link (`substituir_links_markdown`):** Se a forma como o Gemini insere a palavra-âncora mudar ou se você tiver requisitos mais complexos para onde o link deve ir, pode ajustar a lógica de busca nesta função. 

    eee