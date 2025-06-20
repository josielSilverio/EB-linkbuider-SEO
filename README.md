## O que há de novo na versão 3.1?

*   **Processamento em Duas Etapas**: Agora você pode escolher gerar apenas títulos, apenas conteúdos, ou ambos em uma única execução.
*   **Sistema de Aprendizado**: Implementação de um banco de dados SQLite para armazenar e aprender com os títulos gerados.
*   **Feedback de Títulos**: Sistema de avaliação de títulos gerados para melhorar a qualidade das próximas gerações.
*   **Controle de Rate Limit**: Implementação de sistema de retry com backoff exponencial para lidar com limites de API.
*   **Verificação de Linhas Processadas**: O script agora verifica e para automaticamente quando todas as linhas necessárias foram processadas.
*   **Melhor Gerenciamento de Memória**: Otimizações para lidar com grandes volumes de dados.

## O que há de novo na versão 3.0?

*   **Interface Interativa Completa**: Seleção de Planilha/Aba e Pasta do Drive via menus no terminal, eliminando a necessidade de configurar IDs no `.env`.
*   **Menu de Categorias Aprimorado**: Selecione por palavra-âncora, todos os itens ou quantidade aleatória, com estimativa de custo clara antes de prosseguir.
*   **Geração de Conteúdo Otimizada**:
    *   Inclusão de descrições de jogos e instruções de estilo específicas por jogo/categoria no prompt do Gemini para maior relevância e unicidade.
    *   Verificação e correção automática do tamanho do título gerado (9-15 palavras).
*   **Integração Gemini Robusta**: Uso do modelo `gemini-1.5-flash` (ou configurável), com tratamento de erros e estimativa de custos aprimorada.
*   **Controle de Qualidade Pós-Geração (Opcional)**:
    *   Verificação e alerta para títulos duplicados entre os documentos gerados na mesma execução.
    *   Detecção de similaridade de conteúdo entre documentos (usando TF-IDF básico) para identificar possíveis repetições.
    *   Verificação e substituição automática de termos proibidos/sensíveis no conteúdo gerado.
*   **Melhor Gerenciamento de Custos**: Estimativas mais claras no menu e baseadas nos preços configuráveis no `.env`.
*   **Logging Detalhado**: Logs em arquivo (`logs/`) com codificação UTF-8 para facilitar diagnóstico de erros, incluindo informações sobre qual linha/célula está sendo atualizada.
*   **Tratamento de Erros Aprimorado**: Mensagens de erro mais claras e tratamento específico para problemas comuns de autenticação, API e acesso a arquivos.
*   **Estrutura de Código Refatorada**: Melhor organização em módulos (`src/`) para facilitar a manutenção e futuras expansões.
*   **README Atualizado (Versão 2.4)**: Documentação mais completa e clara, refletindo as últimas funcionalidades e refinamentos no processo de geração de conteúdo. 

## Descrição

Este projeto automatiza o fluxo de trabalho para geração de conteúdo SEO a partir de dados em planilhas do Google Sheets. O script:

1.  Permite selecionar a planilha e aba desejada.
2.  Lê os dados da aba selecionada.
3.  Apresenta um menu interativo para selecionar categorias de trabalho (baseado na coluna "Palavra-Âncora"), processar uma linha específica por ID (perguntando a quantidade de itens subsequentes), ou uma quantidade específica de itens.
4.  Estima o custo de processamento com base na seleção.
5.  Gera artigos otimizados utilizando a API do Gemini para os itens selecionados, com foco em naturalidade, "brasilidade", coerência e originalidade, seguindo as diretrizes do `prompt.txt`.
6.  Cria documentos no Google Docs com o conteúdo gerado, salvando-os em uma pasta específica no Google Drive.
7.  Atualiza a planilha original com os títulos gerados (apenas o título na coluna "tema") e as URLs dos documentos criados nas colunas corretas.
8.  Realiza verificações de qualidade (títulos duplicados, similaridade de conteúdo, termos proibidos) após a geração.

## Funcionalidades Principais

- **Seleção de Planilha/Aba**: Menu interativo para escolher qual planilha e aba do Google Sheets usar.
- **Menu de Categorias Interativo**: Selecione categorias específicas (baseadas na palavra-âncora), todos os itens, uma quantidade aleatória, ou uma linha específica por ID para processar (com opção de definir quantos itens a partir dali).
- **Estimativa de Custos**: Visualize o custo estimado por categoria e total antes de executar o processamento.
- **Geração de Artigos com Gemini AI**: Cria conteúdo otimizado para SEO, incluindo links âncora de forma natural. O processo é guiado por um `prompt.txt` customizável para garantir alta qualidade, tom jornalístico brasileiro e originalidade.
- **Integração Completa**: Google Sheets, Google Docs e Google Drive em um fluxo automatizado.
- **Controle de Qualidade Avançado**:
  - **Verificação de Títulos Duplicados**: Sistema automático para identificar e corrigir títulos duplicados, gerando novos conteúdos únicos.
  - **Análise de Similaridade**: Detecta conteúdos muito similares usando análise de similaridade de cosseno e TF-IDF, reescrevendo automaticamente quando necessário.
  - **Detecção e Substituição de Termos Proibidos**: Sistema automático para manter o conteúdo de acordo com as políticas, substituindo termos sensíveis por alternativas adequadas.
  - **Validação de Títulos**: Verifica e corrige títulos para garantir que tenham entre 9-15 palavras, não ultrapassem 100 caracteres, e contenham a palavra-âncora.
- **Instruções Específicas por Jogo**: Sistema inteligente que gera instruções personalizadas baseadas no tipo de jogo ou categoria, garantindo conteúdo relevante e único.
- **Persistência de Seleção**: Salva a última seleção de planilha/aba para facilitar o uso subsequente.
- **Tratamento de Erros Robusto**: Sistema de retry com backoff exponencial para lidar com falhas de API.
- **Logging Detalhado**: Sistema de logs abrangente para rastrear todo o processo de geração e identificar problemas.

## Pré-requisitos

### Ambiente de Desenvolvimento (IDE e Python)

*   **Python**: Certifique-se de ter o Python 3.7 ou superior instalado.
    *   **Windows**: Baixe o instalador no [site oficial do Python](https://www.python.org/downloads/windows/). 
    **Importante:** Durante a instalação, marque a opção "Add Python X.Y to PATH" para que o Python seja reconhecido no terminal.
*   **IDE (Ambiente de Desenvolvimento Integrado)**: Embora você possa usar qualquer editor de texto ou IDE, recomendamos fortemente um com integração IA para facilitar o desenvolvimento:
    *   **Recomendado:** [**Cursor**](https://www.cursor.com/) - Um editor de código moderno baseado no VSCode, mas com funcionalidades de IA profundamente integradas que podem aumentar sua produtividade. Baixe a versão para Windows no site e siga o instalador.
    *   **Alternativa:** [**Windsurf Editor**](https://windsurf.com/editor) - Outra opção de IDE com foco em IA, que pode ser uma alternativa interessante. Verifique o site para download e instalação no Windows.

### Dependências do Sistema

*   **SQLite3**: O projeto agora utiliza SQLite para armazenamento de dados. Na maioria dos sistemas, o SQLite já vem instalado com o Python.
*   **Google Chrome**: Recomendado para autenticação OAuth2 com o Google.

### APIs e Credenciais do Google

*   Acesso às seguintes APIs do Google Cloud (habilite-as no seu projeto do Google Cloud Console):
    *   Google Sheets API
    *   Google Docs API
    *   Google Drive API
*   Chave de API para o Google AI (Gemini API) - Obtenha em [Google AI Studio](https://aistudio.google.com/app/apikey) ou no Google Cloud Console.
*   Credenciais OAuth2 para as APIs do Google Cloud:
    *   Crie credenciais do tipo "OAuth 2.0 Client ID" no Google Cloud Console.
    *   Selecione o tipo de aplicação "Desktop app".
    *   Baixe o arquivo JSON resultante e salve-o como `credentials.json` dentro de uma pasta chamada `credentials` na raiz do projeto (`SEO-LinkBuilder/credentials/credentials.json`).

## Instalação

1.  Clone este repositório:
    ```bash
    git clone https://github.com/caiorcastro/EB-LinkBuider.git
    cd EB-LinkBuider 
    ```
    *Observação: Se você já clonou o repositório anteriormente, use `git pull` dentro da pasta para obter as atualizações mais recentes.*

2.  Crie e ative um ambiente virtual Python (obrigatório):
    ```bash
    # Certifique-se de que o Python está no PATH (ver pré-requisitos)
    python -m venv venv
    ```
    *   **No Windows (CMD):**
        ```cmd
        venv\Scripts\activate.bat
        ```
    *   **No Windows (PowerShell):**
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```
        *(Se encontrar um erro de execução de script no PowerShell, pode ser necessário ajustar a política de execução com: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*
    *   **No Linux/Mac:**
        ```bash
        source venv/bin/activate
        ```
    *Seu terminal deve indicar que o ambiente virtual está ativo (ex: `(venv) C:\...`)*

3.  Instale as dependências Python dentro do ambiente virtual ativo:
    ```bash
    # Atualiza o pip para a versão mais recente
    python -m pip install --upgrade pip
    
    # Instala as dependências do projeto
    pip install -r requirements.txt
    ```

4.  Crie um arquivo `.env` na raiz do projeto (na mesma pasta que o `main_duas_etapas.py`). Use o exemplo abaixo como base, **substituindo os valores de exemplo pelas suas chaves reais**:
    ```dotenv
    # Credenciais e Configurações - NÃO FAÇA COMMIT DESTE ARQUIVO!
    
    # Google Cloud / Gemini API Key
    GOOGLE_API_KEY="SUA_API_KEY_GEMINI_AQUI"
    
    # Caminho para o arquivo de credenciais OAuth 2.0 (obrigatório)
    CREDENTIALS_FILE_PATH="credentials/credentials.json"
    
    # Configurações do Gemini
    GEMINI_MODEL="gemini-1.5-flash"
    GEMINI_MAX_OUTPUT_TOKENS="8192"
    GEMINI_TEMPERATURE="0.4"
    
    # Preços Gemini (USD por 1 Milhão de tokens)
    GEMINI_PRECO_ENTRADA_MILHAO_TOKENS="0.35"
    GEMINI_PRECO_SAIDA_MILHAO_TOKENS="1.05"
    
    # Configurações de Delay e Retry
    DELAY_ENTRE_CHAMADAS_GEMINI=2  # Segundos entre chamadas à API
    MAX_RETRIES=3                  # Número máximo de tentativas em caso de erro
    ```

5.  Coloque seu arquivo de credenciais OAuth (`credentials.json`) baixado do Google Cloud Console dentro da pasta `credentials/`.

6.  Inicialize o banco de dados SQLite (primeira execução apenas):
    ```bash
    python check_db.py
    ```

## Uso

Execute o script principal a partir do terminal, **com o ambiente virtual (`venv`) ativado**:

```bash
# Execução com menu interativo
python main_duas_etapas.py

# Verificar estatísticas do banco de dados de títulos
python check_learning_db.py
```

### Menus Interativos

O script agora apresenta um menu inicial com três opções:

1.  **Gerar apenas títulos**: Use esta opção primeiro para gerar e avaliar títulos.
2.  **Gerar apenas conteúdos**: Use após ter títulos aprovados para gerar os artigos.
3.  **Gerar títulos e conteúdos**: Processo completo em uma única execução.

Em seguida, você pode escolher:

1.  **Gerar tudo**: Processa todas as linhas que não têm título/conteúdo.
2.  **Gerar número específico**: Define quantos itens processar.
3.  **Cancelar**: Volta ao menu anterior.

### Verificações de Qualidade

Após a geração do conteúdo, o script realiza automaticamente as seguintes verificações de qualidade:

1. **Verificação de Títulos Duplicados**:
   - Identifica títulos idênticos ou muito similares
   - Gera novos conteúdos únicos para substituir duplicatas
   - Atualiza a planilha com os novos títulos e URLs

2. **Análise de Similaridade de Conteúdo**:
   - Usa TF-IDF e similaridade de cosseno para detectar conteúdos muito similares
   - Reescreve automaticamente conteúdos que ultrapassam o limiar de similaridade
   - Mantém a originalidade e diversidade do conteúdo

3. **Verificação de Termos Proibidos**:
   - Identifica e substitui termos sensíveis por alternativas adequadas
   - Mantém o conteúdo em conformidade com as políticas
   - Registra as substituições realizadas nos logs

### Logs e Monitoramento

- Os logs são salvos em `logs/seo_linkbuilder_AAAA-MM-DD.log`
- Incluem informações detalhadas sobre:
  - Processo de geração de conteúdo
  - Verificações de qualidade realizadas
  - Substituições de termos proibidos
  - Erros e exceções encontradas
  - Atualizações na planilha

## Estrutura do Projeto

```
EB-LinkBuider/           # Nome alterado para corresponder ao repo
├── venv/                   # Ambiente virtual Python (ignorado pelo Git)
├── src/                    # Código fonte principal
│   ├── __init__.py
│   ├── auth_handler.py     # Gerencia a autenticação OAuth2 com as APIs do Google.
│   ├── sheets_handler.py   # Interage com a API do Google Sheets.
│   ├── gemini_handler.py   # Interage com a API do Google Gemini AI.
│   ├── docs_handler.py     # Interage com as APIs do Google Docs e Drive.
│   ├── config.py           # Carrega configurações do .env e define constantes (colunas, etc.).
│   └── utils.py            # Funções utilitárias diversas (logging, conversão, contagem tokens).
├── credentials/            # Diretório para armazenar credentials.json e token.json
│   ├── credentials.json    # Seu arquivo de credenciais OAuth 2.0 (NÃO INCLUIR NO GIT)
│   └── token.json          # Token de acesso gerado automaticamente (NÃO INCLUIR NO GIT)
├── data/                   # Arquivos de dados/templates
│   └── prompt.txt          # O prompt base usado para gerar conteúdo com o Gemini.
├── logs/                   # Logs de execução (criado automaticamente, ignorado pelo Git)
│   └── seo_linkbuilder_AAAA-MM-DD.log # Arquivo de log diário
├── main.py                 # Ponto de entrada principal do script. Orquestra o fluxo.
├── requirements.txt        # Lista de dependências Python (pacotes necessários).
├── .env                    # Arquivo para variáveis de ambiente (NÃO INCLUIR NO GIT).
├── README.md               # Este arquivo.
└── .gitignore              # Arquivo para especificar o que o Git deve ignorar.
```
*(A estrutura detalhada das funções dentro de cada arquivo `.py` foi movida para o final deste README na seção "Guia Detalhado dos Scripts")*

## Formato Esperado da Planilha

Para que o script funcione corretamente, a planilha e a aba selecionadas devem ter colunas com os seguintes dados. A ordem exata das colunas **é importante** e é definida no arquivo `src/config.py` através do dicionário `COLUNAS`:

- **ID** (Coluna A por padrão): Identificador único da linha/campanha. O script ignora linhas onde esta coluna está vazia ou não parece ser um ID válido.
- **Site** (Coluna B por padrão): Nome do site relacionado. Usado para gerar o nome do arquivo do Google Doc.
- **Palavra-Âncora** (Coluna G por padrão): A palavra ou frase que será usada como âncora para o link interno no texto gerado. Usada também para agrupar no menu de categorias.
- **URL da Âncora** (Coluna H por padrão): O link de destino para a palavra-âncora.
- **Título/Tema** (Coluna I por padrão): O tema ou título base para a geração do artigo. Esta coluna **será sobrescrita** com o título gerado pelo Gemini.
- **URL do Documento** (Coluna J por padrão): Coluna onde a URL do Google Doc gerado será inserida pelo script. Esta coluna **será sobrescrita**.

*Observação: Outras colunas podem existir na planilha, mas não são diretamente utilizadas pelo fluxo principal de geração e atualização.*

## Personalização

- **Prompt do Gemini**: Edite o arquivo `data/prompt.txt` para modificar as instruções, o tom (foco no jornalismo brasileiro), o estilo e a estrutura do conteúdo que o Gemini irá gerar. Este é o principal arquivo para refinar a "voz" da IA e garantir a "brasilidade" e qualidade do texto. Experimente diferentes abordagens para otimizar os resultados.
- **Configurações (`.env`)**: Ajuste as configurações no arquivo `.env` para suas chaves de API, o modelo Gemini desejado (`GEMINI_MODEL`), a temperatura (`GEMINI_TEMPERATURE`), os preços de token (para estimativas de custo mais precisas), etc.
- **Mapeamento de Colunas (`src/config.py`)**: Se a estrutura da sua planilha for diferente (ex: a Palavra-Âncora está na coluna F em vez de G), modifique o dicionário `COLUNAS` no arquivo `src/config.py`. Lembre-se que a contagem de colunas começa em 0 (A=0, B=1, C=2, ...).
- **Nome do Arquivo do Google Doc (`src/config.py`)**: O formato do nome do arquivo é definido na função `gerar_nome_arquivo` dentro de `src/config.py`. O formato atual é `"[ID] - [Site] - [Ancora] - [4 Primeiras Palavras do Título]"`. Você pode alterar essa função para usar outras colunas ou um formato diferente.
- **Termos Proibidos (`src/gemini_handler.py`)**: A função `verificar_conteudo_proibido` contém um dicionário `termos_proibidos` que mapeia palavras/frases a serem substituídas. Você pode adicionar, remover ou modificar esses termos e suas substituições conforme necessário.

## Solução de Problemas Comuns

- **Erro de Autenticação/Token (`RefreshError`, `invalid_grant`, etc.)**:
    1.  **Verifique `credentials.json`**: Confirme se o arquivo `credentials/credentials.json` está correto, se foi gerado para "Desktop app" no Google Cloud Console e se corresponde ao projeto onde as APIs (Sheets, Docs, Drive) estão ativadas.
    2.  **Ative as APIs**: Certifique-se de que as APIs Google Sheets, Google Docs e Google Drive estão **ativadas** no Google Cloud Console para o projeto associado às suas credenciais.
    3.  **Delete `token.json`**: A causa mais comum. Vá até a pasta `credentials/` e **delete o arquivo `token.json`** (ele guarda a autorização anterior). Na próxima execução do script (`python main.py`), ele pedirá para você autorizar o acesso novamente através do navegador. Siga os passos na tela.
    4. **Tela de Consentimento OAuth**: Verifique se a tela de consentimento OAuth no Google Cloud Console está configurada corretamente, especialmente se estiver em modo de "Teste" e seu email não estiver listado como usuário de teste. Considere publicá-la se necessário (para uso interno pode não ser preciso).
- **Erro `Unable to parse range` ou `Requested entity was not found` (Sheets)**:
    *   Geralmente indica que o nome da aba (`SHEET_NAME`) selecionado no menu não corresponde **exatamente** a uma aba existente na planilha (`SPREADSHEET_ID`) fornecida. Verifique maiúsculas/minúsculas, espaços extras e se a planilha/aba realmente existe e está acessível pela conta autorizada.
    *   Pode ocorrer também se o ID da Planilha estiver incorreto ou se a conta autorizada não tiver permissão para acessá-la.
- **Erro `File not found` ao tentar salvar o Google Doc (Drive)**:
    *   Verifique se o ID da Pasta do Google Drive (`DRIVE_FOLDER_ID`) fornecido no menu está correto.
    *   Confirme se a conta que autorizou o script tem permissão de **escrita** (Editor) na pasta de destino no Google Drive.
- **Erros de Codificação (`UnicodeEncodeError`/`UnicodeDecodeError`)**:
    *   Certifique-se de que o arquivo `.env` está salvo com codificação **UTF-8**. Use um editor como VS Code ou Notepad++ para verificar e salvar com a codificação correta.
    *   Verifique também a codificação do arquivo `prompt.txt` (deve ser UTF-8).
- **Planilha Não Atualiza ou Atualiza Linha Errada**:
    *   Verifique os logs (`logs/seo_linkbuilder_*.log`). Eles detalham qual `indice_original_linha` o script está tentando atualizar e em qual célula (ex: `I15`, `J23`).
    *   Confirme se o mapeamento das colunas de Título e URL do Documento no `src/config.py` (padrão `I` e `J`) corresponde à sua planilha.
    *   Verifique se não há filtros aplicados na visualização da planilha que possam esconder a linha atualizada.
- **Conteúdo Gerado Pelo Gemini é Bloqueado (`FinishReason.SAFETY`)**:
    *   A API do Gemini tem filtros de segurança. Se o seu prompt ou o conteúdo gerado acionar esses filtros, a resposta pode ser bloqueada.
    *   Revise seu `prompt.txt` para evitar linguagem que possa ser interpretada como prejudicial, antiética, perigosa, etc.
    *   Tente simplificar o prompt ou o Título/Tema fornecido na planilha.
    *   Verifique as configurações de segurança (`safety_settings`) na chamada da API em `src/gemini_handler.py`, mas ajuste com cautela. Relaxar demais os filtros pode gerar conteúdo inadequado.

## Custos Estimados

- O uso das APIs do Google Sheets, Docs e Drive geralmente se enquadra nos limites da camada gratuita para uso normal, mas verifique os limites atuais na documentação do Google Cloud.
- A **API do Gemini (Google AI) TEM CUSTOS** associados ao processamento de texto. Os custos são baseados no **número de tokens** de entrada (seu prompt + dados da planilha) e de saída (o artigo gerado).
- Os preços variam conforme o modelo (`GEMINI_MODEL`) escolhido no `.env`. Verifique a [página de preços oficial do Google AI](https://ai.google.dev/pricing) para os valores mais recentes.
- O script exibe uma **estimativa de custo** antes de iniciar o processamento em lote, com base nos preços definidos no seu `.env`. **Esta é apenas uma estimativa**, e o custo real pode variar ligeiramente.

## Guia Detalhado dos Scripts (`.py`)

Aqui está um detalhamento do propósito e das funções principais de cada arquivo Python no diretório `src/`, além do `main.py`:

*(Esta seção é mais técnica e útil se você quiser modificar o comportamento do script)*

### 📄 `main.py` - O Maestro da Orquestra

*   **Propósito:** Ponto de entrada principal. Orquestra todo o fluxo: menus (incluindo seleção por ID e quantidade), leitura da planilha, filtragem, loop de processamento (chamando Gemini e Docs), atualização da planilha e controle de qualidade opcional.
*   **Funções Principais:**
    *   `main()`: Orquestra todo o fluxo principal.
    *   `apresentar_menu_planilha()`: Pede ID/URL da planilha, valida, lista abas e obtém a seleção do usuário.
    *   `apresentar_menu_pasta_drive()`: Pede ID/URL da pasta do Drive e valida.
    *   `estimar_custo_por_categoria()`: Calcula o custo estimado agrupado por palavra-âncora.
    *   `apresentar_menu_categorias()`: Mostra resumo, calcula custo total, e permite selecionar categorias/quantidade.
    *   `filtrar_dataframe_por_categorias()`: Filtra o DataFrame da planilha com base na seleção do menu.
    *   `processar_linha()`: (Dentro do loop principal) Chama os handlers para gerar conteúdo, criar/atualizar Doc e atualizar a planilha para uma única linha.
    *   `verificar_titulos_duplicados()`, `verificar_similaridade_conteudos()`, `corrigir_termos_proibidos()`: Funções de controle de qualidade pós-geração (executadas se `--todos` for usado ou sem limite).

### ⚙️ `src/config.py` - O Painel de Controle

*   **Propósito:** Carrega configurações do arquivo `.env`, define constantes importantes (como o mapeamento de colunas) e fornece funções relacionadas à configuração.
*   **Elementos/Funções Principais:**
    *   Carrega variáveis do `.env` (Chaves de API, Configs Gemini, Caminho das Credenciais, Preços).
    *   `COLUNAS`: **Dicionário crucial** que mapeia nomes lógicos (ex: `'ID'`, `'Palavra-Âncora'`) para os índices numéricos das colunas na planilha (A=0, B=1, ...). **Ajuste aqui se sua planilha for diferente.**
    *   `gerar_nome_arquivo()`: Define o formato do nome do arquivo do Google Doc. **Altere aqui para mudar o padrão de nomenclatura.**
    *   `estimar_custo_gemini()`: Calcula o custo estimado de uma chamada à API Gemini com base nos tokens e nos preços do `.env`.

### 🔑 `src/auth_handler.py` - O Porteiro das APIs Google

*   **Propósito:** Gerencia a autenticação OAuth2 com as APIs do Google (Sheets, Docs, Drive). Lida com o fluxo de obtenção e atualização de credenciais do usuário.
*   **Funções Principais:**
    *   `obter_credenciais()`: Obtém ou renova as credenciais OAuth2. Lida com o fluxo de autorização no navegador na primeira vez ou quando o token expira. Salva/lê o `token.json`. Usa `CREDENTIALS_FILE_PATH` do `config.py`.
    *   `criar_servico_sheets()`, `criar_servico_docs()`, `criar_servico_drive()`: Usam as credenciais obtidas para criar os objetos de serviço que permitem interagir com cada API do Google.

### 📊 `src/sheets_handler.py` - O Arquivista da Planilha

*   **Propósito:** Encapsula toda a interação com a API do Google Sheets. Lê dados, atualiza células específicas (URL do Doc, Título gerado).
*   **Classe Principal:** `SheetsHandler`
*   **Métodos Principais:**
    *   `ler_planilha()`: Lê os dados da aba especificada, converte para DataFrame (Pandas), filtra linhas inválidas (sem ID), e **adiciona a coluna `linha_original`** para rastrear a posição real na planilha.
    *   `atualizar_url_documento()`: Atualiza a célula na coluna definida em `COLUNAS['URL_DOC']` (padrão J) na linha original correta com a URL do Google Doc.
    *   `atualizar_titulo_documento()`: Atualiza a célula na coluna `COLUNAS['TITULO_TEMA']` (padrão I) na linha original com o título gerado pelo Gemini.
    *   `obter_abas_disponiveis()`: Lista os nomes de todas as abas na planilha fornecida.
    *   `extrair_dados_linha()`: Extrai os dados relevantes de uma linha específica do DataFrame usando o mapeamento `COLUNAS`.

### ✨ `src/gemini_handler.py` - O Escritor Criativo (IA)

*   **Propósito:** Interage com a API do Google Gemini para gerar o conteúdo dos artigos. Constrói o prompt (baseado no `data/prompt.txt`), faz a chamada à API, processa a resposta e realiza verificações.
*   **Classe Principal:** `GeminiHandler`
*   **Métodos Principais:**
    *   `carregar_prompt_template()`: Carrega o conteúdo do arquivo `data/prompt.txt`.
    *   `_construir_prompt()`: Substitui os placeholders (ex: `{palavra_ancora}`, `{url_ancora}`) no template do prompt com os dados específicos da linha atual da planilha. Inclui lógicas para adicionar descrições de jogos e instruções especiais.
    *   `gerar_conteudo()`: Orquestra a geração: constrói o prompt, chama a API do Gemini (`genai.GenerativeModel.generate_content`), estima o custo, extrai o texto da resposta e verifica termos proibidos.
    *   `verificar_conteudo_proibido()`: Verifica o texto gerado contra uma lista de termos e os substitui por alternativas mais seguras.
    *   `verificar_e_corrigir_titulo()`: Garante que o título gerado tenha um comprimento adequado (9-15 palavras).

### 📑 `src/docs_handler.py` - O Editor e Organizador de Documentos

*   **Propósito:** Gerencia a criação e atualização de arquivos no Google Docs e a interação com o Google Drive (para salvar na pasta correta).
*   **Classe Principal:** `DocsHandler`
*   **Métodos Principais:**
    *   `criar_documento()`: Cria um novo Google Doc com o nome gerado (`gerar_nome_arquivo`) dentro da pasta especificada (`folder_id`) no Google Drive. Retorna o ID e a URL do novo documento.
    *   `atualizar_documento()`: Substitui o conteúdo de um Google Doc existente pelo novo texto gerado (usado pelas funções de controle de qualidade).
    *   `formatar_documento()`: Aplica formatação básica ao conteúdo do documento. Chama `utils.converter_markdown_para_docs` para gerar os requests de formatação (título, parágrafos, inserção de link âncora) e os envia para a API do Docs.
    *   `obter_conteudo_documento()`: Lê e retorna o texto puro de um Google Doc existente (usado pelas funções de controle de qualidade).

### 🛠️ `src/utils.py` - A Caixa de Ferramentas

*   **Propósito:** Contém funções utilitárias genéricas usadas por vários outros módulos.
*   **Funções Principais:**
    *   `configurar_logging()`: Configura o sistema de logging para registrar mensagens no console e em um arquivo (`logs/seo_linkbuilder_*.log`) com codificação UTF-8.
    *   `converter_markdown_para_docs()`: Converte o texto (com possível Markdown simples) gerado pelo Gemini em uma lista de `requests` que a API do Google Docs entende para formatar o documento (parágrafos, título, negrito, links). **A lógica de formatação principal reside aqui.**
    *   `contar_tokens()`: Estima a contagem de tokens de um texto usando a API do Gemini (método `count_tokens`), necessário para a estimativa de custos.
    *   `substituir_links_markdown()`: Encontra a `palavra_ancora` no texto gerado e a marca de forma especial para que `converter_markdown_para_docs` saiba onde inserir o link HTML correto.

## Novas Funcionalidades e Melhorias

### Sistema de Verificação de Qualidade
- **Verificação de Títulos Duplicados**: Identifica automaticamente títulos duplicados e gera novos conteúdos únicos para substituí-los.
- **Análise de Similaridade**: Usa TF-IDF e similaridade de cosseno para detectar conteúdos muito similares, reescrevendo automaticamente quando necessário.
- **Validação de Títulos**: Sistema robusto que verifica e corrige títulos para garantir qualidade e adequação.

### Instruções Específicas por Jogo
O sistema agora inclui um conjunto abrangente de instruções específicas para diferentes tipos de jogos:
- Crash Games (Aviator, Spaceman)
- Slots Populares (Gates of Olympus, Fortune Rabbit, Sweet Bonanza)
- Jogos de Mesa (Blackjack, Poker, Roleta, Bacbo)
- Termos Genéricos de Apostas (Casa de Apostas, Aposta Online, etc.)

### Melhorias na Geração de Conteúdo
- **Temperatura Adaptativa**: Ajusta automaticamente a temperatura do modelo para gerar conteúdo mais diverso quando necessário.
- **Validação de Conteúdo**: Verifica e corrige problemas comuns como títulos incompletos, formatação incorreta e termos proibidos.
- **Persistência de Seleção**: Salva a última seleção de planilha/aba para facilitar o uso subsequente.

### Tratamento de Erros e Logging
- **Sistema de Retry**: Implementa backoff exponencial para lidar com falhas de API.
- **Logging Detalhado**: Sistema abrangente de logs para rastrear todo o processo de geração.
- **Validação de Dados**: Verificações robustas em cada etapa do processo.

# Configuração do Ambiente Virtual

Antes de executar o projeto, recomenda-se criar um ambiente virtual para isolar as dependências do Python. Siga os passos abaixo:

## 1. Crie o ambiente virtual

No terminal, navegue até a pasta do projeto e execute:

### Windows
```powershell
python -m venv venv
```

### Linux/Mac
```bash
python3 -m venv venv
```

## 2. Ative o ambiente virtual

### Windows
```powershell
.\venv\Scripts\activate
```

### Linux/Mac
```bash
source venv/bin/activate
```

Você saberá que o ambiente está ativado quando aparecer `(venv)` no início da linha do terminal.

## 3. Instale as dependências

Com o ambiente virtual ativado, execute:

```sh
pip install -r requirements.txt
```

Se necessário, atualize o pip:
```sh
pip install --upgrade pip
```

---

# (Seção original do README continua abaixo)

