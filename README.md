# SEO-LinkBuilder

Automatização para geração de artigos otimizados para SEO utilizando a API do Google Gemini, Google Sheets, Google Docs e Google Drive.

## Descrição

Este projeto automatiza o fluxo de trabalho para geração de conteúdo SEO a partir de dados em uma planilha do Google Sheets. O script lê os dados da planilha, gera artigos otimizados utilizando a API do Gemini, cria documentos no Google Docs com o conteúdo gerado, e atualiza a planilha com as URLs dos documentos criados.

## Funcionalidades

- **Menu de categorias interativo**: Selecione categorias específicas de jogos para processar ou escolha "TODOS OS JOGOS" para processar tudo
- **Estimativa de custos**: Visualize o custo estimado por categoria antes de executar o processamento
- **Geração de artigos com Gemini AI**: Cria conteúdo otimizado para SEO com links âncora
- **Integração completa**: Google Sheets, Google Docs e Google Drive em um fluxo automatizado
- **Controle de qualidade**: Verifica e corrige títulos duplicados e conteúdos com alta similaridade
- **Filtro por quantidade**: Opção para processar um número específico de itens aleatoriamente
- **Detecção e substituição de termos proibidos**: Sistema automático para manter o conteúdo de acordo com as políticas

## Pré-requisitos

- Python 3.7 ou superior
- Acesso às seguintes APIs do Google Cloud:
  - Google Sheets API
  - Google Docs API
  - Google Drive API
  - Google AI (Gemini API)
- Credenciais OAuth2 para as APIs do Google Cloud
- Chave de API para o Google Gemini

## Instalação

1. Clone este repositório para sua máquina local:
```bash
git clone https://seu-repositorio/SEO-LinkBuilder.git
cd SEO-LinkBuilder
```

2. Crie e ative um ambiente virtual Python:
```bash
python -m venv venv
# No Windows:
venv\Scripts\activate.bat  # CMD
.\venv\Scripts\Activate.ps1  # PowerShell

# No Linux/Mac:
source venv/bin/activate
```

3. Instale as dependências necessárias:
```bash
pip install -r requirements.txt
```

4. Configure as variáveis de ambiente no arquivo `.env` na raiz do projeto:
```
# Google Cloud / Gemini API Key
GOOGLE_API_KEY="SUA_API_KEY_AQUI"
GOOGLE_CLOUD_API_KEY="SUA_API_KEY_CLOUD_AQUI"

# Google Sheets
SPREADSHEET_ID="ID_DA_SUA_PLANILHA"
SHEET_NAME="NOME_DA_ABA_DA_PLANILHA"

# Google Drive
DRIVE_FOLDER_ID="ID_DA_PASTA_NO_DRIVE"

# Caminho para o arquivo de credenciais
CREDENTIALS_FILE_PATH="credentials/credentials.json"

# Configurações do Gemini
GEMINI_MODEL="gemini-1.5-flash"
GEMINI_MAX_OUTPUT_TOKENS="1024"
GEMINI_TEMPERATURE="0.4"

# Preços Gemini (USD por 1000 tokens)
GEMINI_PRECO_ENTRADA="0.00025"
GEMINI_PRECO_SAIDA="0.0005"

# Formato para nome de arquivo
NOME_ARQUIVO_PADRAO="{id} - {site} - {ancora}"
```

5. Coloque seu arquivo de credenciais OAuth (`credentials.json`) na pasta `credentials/`.

## Uso

Execute o script principal com os seguintes parâmetros:

```bash
# Modo teste (processa apenas a primeira linha e não atualiza a planilha)
python main.py --teste

# Processar 10 linhas (padrão)
python main.py

# Processar um número específico de linhas
python main.py --limite 5

# Processar todas as linhas da planilha
python main.py --todos
```

### Menu Interativo

Ao executar o script, um menu interativo será apresentado, mostrando:

1. Uma visão geral de todas as categorias disponíveis
2. O número de itens em cada categoria
3. O custo estimado por categoria e o custo total
4. A opção "TODOS OS JOGOS" para processar todos os itens
5. A opção de selecionar uma categoria específica
6. A opção de escolher uma quantidade personalizada de itens

Exemplo do menu:
```
============================================================
               MENU DE SELEÇÃO DE CATEGORIAS
============================================================

Total de itens: 150 | Custo estimado total: R$0.51

Categorias disponíveis:

Código | Categoria              | Quantidade | Custo estimado (R$)
------------------------------------------------------------
0      | TODOS OS JOGOS          |    150     | R$0.51
------------------------------------------------------------
  1    | outros               |     26     | R$0.09
  2    | site de apostas      |     21     | R$0.07
  3    | aposta online        |     20     | R$0.07
  4    | casa de apostas      |     19     | R$0.07
  5    | demo                 |     14     | R$0.05
  ...
------------------------------------------------------------
T      | TODOS OS ITENS          |    150     | R$0.51
Q      | QUANTIDADE ESPECÍFICA   | -          | -
------------------------------------------------------------
```

## Estrutura do Projeto

```
SEO-LinkBuilder/
├── venv/                   # Ambiente virtual
├── src/                    # Código fonte do projeto
│   ├── __init__.py
│   ├── auth_handler.py     # Módulo para autenticação Google API
│   ├── sheets_handler.py   # Módulo para interagir com Google Sheets
│   ├── gemini_handler.py   # Módulo para interagir com Gemini API
│   ├── docs_handler.py     # Módulo para interagir com Google Docs/Drive API
│   ├── config.py           # Módulo para carregar configurações
│   └── utils.py            # Funções utilitárias
├── credentials/            # Diretório para armazenar credentials.json
│   └── credentials.json    # Arquivo de credenciais do Google Cloud (não incluído no repositório)
├── data/                   # Dados de entrada/configuração
│   └── prompt.txt          # O prompt base para o Gemini
├── logs/                   # Logs de execução (criado automaticamente)
├── main.py                 # Ponto de entrada principal do script
├── requirements.txt        # Lista de dependências Python
├── .env                    # Arquivo para variáveis de ambiente (não incluído no repositório)
└── .gitignore              # Arquivo para especificar o que o Git deve ignorar
```

## Formato da Planilha

A planilha do Google Sheets deve conter as seguintes colunas:

- Coluna B: ID da campanha/linha
- Coluna C: Data (formato YYYY/MM)
- Coluna D: Site/domínio
- Coluna F: Quantidade de palavras
- Coluna H: Valor
- Coluna I: Palavra-âncora para o link interno
- Coluna J: URL da âncora (para onde o link deve apontar)
- Coluna K: Título sugerido para o artigo
- Coluna L: URL do documento gerado (será preenchida pelo script)

## Personalização

- Edite o arquivo `data/prompt.txt` para personalizar as instruções enviadas para o Gemini AI.
- Ajuste as configurações no arquivo `src/config.py` para modificar os parâmetros do Gemini, formato dos arquivos, etc.

## Solução de Problemas

Se encontrar problemas com a autenticação:

1. Verifique se o arquivo `credentials.json` está na pasta correta
2. Certifique-se de que as APIs necessárias estão ativadas no Google Cloud Console
3. Se o token expirar, delete o arquivo `credentials/token.json` e execute novamente para reautenticar

## Custos

- O uso das APIs do Google Sheets, Docs e Drive é gratuito para a maioria dos casos de uso pessoal.
- A API do Gemini tem custos baseados no número de tokens processados. Consulte o site do Google para informações atualizadas sobre preços.
- O script inclui uma calculadora de custos que estima o valor gasto a cada execução e por categoria.

## Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests. 