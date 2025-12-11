# 🔗 Sistema de Controle de Associação (SaaS Interno)

Este é um sistema web desenvolvido em **Python (Streamlit)** para gerenciar a produtividade da equipe de associação de produtos. Ele funciona como uma interface de controle de ponto e tarefas, utilizando o **Google Sheets** como banco de dados em tempo real.

## 🚀 Funcionalidades

* **Autenticação Segura:** Login com senha e persistência de sessão via Cookies (expiração automática).
* **Logout Blindado:** Sistema de cookies e parâmetros de URL para garantir desconexão real.
* **Gestão de Tarefas:** Cadastro dinâmico de novas letras/lotes com contagem personalizada de produtos na última página.
* **Checklist Inteligente:** Formulário de bloqueio que impede cliques duplos e envio de dados duplicados.
* **Blacklist de Letras:** Filtra letras indesejadas baseada na configuração do cliente (ex: pular letras G, H).
* **Dashboard em Tempo Real:**
    * Métricas de produtividade (Tempo, Páginas, Produtos).
    * Tabela Geral (A-Z) com status de cada letra.
    * Mapa visual da letra atual.
* **Banco de Dados:** Integração total com Google Sheets para logs e persistência.

## 🛠️ Tecnologias Utilizadas

* **Frontend:** [Streamlit](https://streamlit.io/)
* **Manipulação de Dados:** Pandas
* **Conexão Google:** gspread, oauth2client
* **Componentes Extras:** extra-streamlit-components (Cookie Manager)

## 📋 Pré-requisitos e Instalação

### 1. Dependências
Crie um arquivo `requirements.txt` com o seguinte conteúdo:
```text
streamlit
pandas
gspread
oauth2client
extra-streamlit-components
pytz
2. Configuração do Google Sheets
O sistema exige uma planilha com 3 abas específicas. A estrutura das colunas deve ser respeitada:

Aba 1: cadastro_varreduras

Usada para listar os clientes e regras de exclusão.

Colunas: Cliente | Concorrente | Delete_Letras (Ex: "G, H")

Aba 2: Controle_Paginas

Armazena o estado atual de cada letra (memória do sistema).

Colunas: Chave | Site | Letra | Qtd_Paginas | Paginas_Concluidas | Qtd_Ultima_Pag | Responsavel

Aba 3: Logs

Histórico de todas as ações para cálculo de métricas.

Colunas: ID_Sessao | Operador | Site | Letra | Acao | Data_Hora | Timestamp | Tempo_Decorrido | Paginas_Turno | Total_Paginas | Qtd_Total

3. Configuração de Segredos (.streamlit/secrets.toml)
Crie a pasta .streamlit e o arquivo secrets.toml com suas credenciais:

Ini, TOML

[passwords]
"joao" = "senha123"
"maria" = "senha456"

[gcp_service_account]
type = "service_account"
project_id = "seu-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----..."
client_email = "..."
client_id = "..."
auth_uri = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
token_uri = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
auth_provider_x509_cert_url = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
client_x509_cert_url = "..."
⚙️ Como Rodar
No terminal, execute:

Bash

streamlit run app.py
🛡️ Regras de Negócio Implementadas
Tranca de Seleção: O usuário não consegue iniciar sem selecionar um cliente válido (trava no "Selecione...").

Anti-Duplicidade: O sistema verifica a última ação no Log. Se o usuário tentar "Pausar" duas vezes seguidas, o segundo clique é ignorado.

Formulário de Trabalho: Durante a execução, os cliques no checklist não recarregam a página. O envio só ocorre ao clicar em "Pausar" ou "Finalizar".

Cálculo de Produtos:

Páginas normais = 100 produtos.

Última página = Valor cadastrado pelo usuário (ex: 45).

Sanitização de Dados: O sistema força a conversão de tempo (vírgula para ponto) e adiciona apóstrofos (') nas listas de páginas para evitar que o Google Sheets formate como data.

👤 Autor
Desenvolvido para uso interno da equipe de Associação.
