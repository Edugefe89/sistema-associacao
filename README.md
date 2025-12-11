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
