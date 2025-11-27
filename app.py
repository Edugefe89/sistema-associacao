import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_google_sheets():
    # Define o escopo
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Pega as credenciais dos "Segredos" do Streamlit (nuvem)
    # O Python vai transformar o TOML do Streamlit em um dicionário para o Google
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Abre a planilha
    sheet = client.open("Sistema_Associacao").worksheet("Logs")
    return sheet

# --- FUNÇÃO DE REGISTRO ---
def registrar_log(operador, site, letra, acao):
    try:
        sheet = conectar_google_sheets()
        agora = datetime.now()
        
        # Se não tiver ID na sessão, cria um novo
        if 'id_sessao' not in st.session_state:
            st.session_state.id_sessao = str(uuid.uuid4())

        # Dados para salvar (Ordem exata das colunas que criamos)
        nova_linha = [
            st.session_state.id_sessao,
            operador,
            site,
            letra,
            acao, # INICIO, PAUSA, FIM...
            agora.strftime("%d/%m/%Y %H:%M:%S"),
            str(agora.timestamp())
        ]
        
        sheet.append_row(nova_linha)
        return True
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return False

# --- INTERFACE ---
st.title("🔗 Controle de Associação")

# Configurações iniciais
EQUIPE = ["Selecione...", "Estagiário 1", "Estagiário 2", "Estagiário 3", "Estagiário 4", "Estagiário 5", "Estagiário 6", "Estagiário 7", "Estagiário 8"]
SITES = ["Site A", "Site B", "Site C", "Site D"] # Mude para os nomes reais
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# Sidebar
st.sidebar.header("Login")
usuario = st.sidebar.selectbox("Quem é você?", EQUIPE)

if usuario != "Selecione...":
    st.write(f"Olá, **{usuario}**.")
    
    col1, col2 = st.columns(2)
    with col1:
        site = st.selectbox("Site", SITES)
    with col2:
        letra = st.selectbox("Letra", LETRAS)
        
    st.divider()

    # Estado da Sessão (Memória do App)
    if 'status' not in st.session_state:
        st.session_state.status = "PARADO" # PARADO, TRABALHANDO, PAUSADO

    col_btn1, col_btn2, col_btn3 = st.columns(3)

    # LÓGICA DOS BOTÕES
    
    # 1. Botão INICIAR (Só aparece se estiver Parado)
    if st.session_state.status == "PARADO":
        if col_btn1.button("▶️ INICIAR", type="primary", use_container_width=True):
            if registrar_log(usuario, site, letra, "INICIO"):
                st.session_state.status = "TRABALHANDO"
                st.rerun()

    # 2. Botão PAUSAR (Só aparece se estiver Trabalhando)
    if st.session_state.status == "TRABALHANDO":
        st.success(f"🟢 Trabalhando em: {site} - Letra {letra}")
        if col_btn2.button("⏸ PAUSAR", use_container_width=True):
            if registrar_log(usuario, site, letra, "PAUSA"):
                st.session_state.status = "PAUSADO"
                st.rerun()
        
        # Botão FINALIZAR
        if col_btn3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            if registrar_log(usuario, site, letra, "FIM"):
                st.session_state.status = "PARADO"
                # Reseta o ID da sessão para a próxima ser nova
                if 'id_sessao' in st.session_state:
                    del st.session_state['id_sessao']
                st.balloons()
                time.sleep(2)
                st.rerun()

    # 3. Botão RETOMAR (Só aparece se estiver Pausado)
    if st.session_state.status == "PAUSADO":
        st.warning("⏸ Tarefa Pausada. Deseja retomar?")
        if col_btn1.button("▶️ RETOMAR", type="primary", use_container_width=True):
            if registrar_log(usuario, site, letra, "RETOMADA"):
                st.session_state.status = "TRABALHANDO"
                st.rerun()

else:
    st.info("👈 Selecione seu nome na barra lateral.")