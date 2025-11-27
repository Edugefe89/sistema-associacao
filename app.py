import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- FUNÇÕES AUXILIARES ---

def check_password():
    if st.session_state.get('password_correct', False):
        return True

    st.header("🔒 Login de Acesso")
    usuarios_cadastrados = st.secrets["passwords"]
    lista_usuarios = ["Selecione seu usuário"] + list(usuarios_cadastrados.keys())
    
    user_input = st.selectbox("Usuário", lista_usuarios)
    pass_input = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if user_input != "Selecione seu usuário":
            if pass_input == usuarios_cadastrados[user_input]:
                st.session_state['password_correct'] = True
                st.session_state['usuario_logado'] = user_input
                st.rerun()
            else:
                st.error("😕 Senha incorreta.")
        else:
            st.warning("Selecione um usuário.")
    return False

def conectar_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("Sistema_Associacao").worksheet("Logs")
    return sheet

def registrar_log(operador, site, letra, acao, num_paginas=0):
    try:
        sheet = conectar_google_sheets()
        
        # Fuso Horário
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        
        # --- CÁLCULO DO TEMPO DECORRIDO ---
        tempo_decorrido = "00:00:00" # Padrão para o INICIO
        
        # Se não for INICIO, tenta calcular a diferença do último registro
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            anterior = st.session_state['ultimo_timestamp']
            delta = agora - anterior
            # Remove os milissegundos para ficar bonito (HH:MM:SS)
            tempo_decorrido = str(delta).split('.')[0]
        
        # Atualiza o timestamp na memória para a próxima vez
        st.session_state['ultimo_timestamp'] = agora
        # ----------------------------------

        if 'id_sessao' not in st.session_state:
            st.session_state.id_sessao = str(uuid.uuid4())

        nova_linha = [
            st.session_state.id_sessao,
            operador,
            site,
            letra,
            acao,
            agora.strftime("%d/%m/%Y %H:%M:%S"),
            str(agora.timestamp()),
            tempo_decorrido, # Nova Coluna de Tempo
            num_paginas
        ]
        
        sheet.append_row(nova_linha)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

# --- APP ---

if not check_password():
    st.stop()

usuario = st.session_state['usuario_logado'].title()

with st.sidebar:
    st.write(f"👤 Logado: **{usuario}**")
    if st.button("Sair"):
        st.session_state['password_correct'] = False
        st.rerun()

st.title("🔗 Controle de Associação")

SITES = ["Site A", "Site B", "Site C", "Site D"] 
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

col1, col2 = st.columns(2)
with col1:
    site = st.selectbox("Site / Projeto", SITES)
with col2:
    letra = st.selectbox("Letra / Lote", LETRAS)

num_paginas = st.number_input("Número de Páginas (Opcional)", min_value=0, step=1)

st.divider()

if 'status' not in st.session_state:
    st.session_state.status = "PARADO"

col_btn1, col_btn2, col_btn3 = st.columns(3)

# 1. INICIAR
if st.session_state.status == "PARADO":
    if col_btn1.button("▶️ INICIAR", type="primary", use_container_width=True):
        # Limpa o timestamp antigo para garantir que comece do zero
        if 'ultimo_timestamp' in st.session_state:
            del st.session_state['ultimo_timestamp']
            
        if registrar_log(usuario, site, letra, "INICIO", num_paginas):
            st.session_state.status = "TRABALHANDO"
            st.rerun()

# 2. PAUSAR
if st.session_state.status == "TRABALHANDO":
    st.success(f"🟢 Trabalhando... (Relógio rodando)")
    
    if col_btn2.button("⏸ PAUSAR", use_container_width=True):
        if registrar_log(usuario, site, letra, "PAUSA", num_paginas):
            st.session_state.status = "PAUSADO"
            st.rerun()
    
    if col_btn3.button("✅ FINALIZAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "FIM", num_paginas):
            st.session_state.status = "PARADO"
            if 'id_sessao' in st.session_state:
                del st.session_state['id_sessao']
            st.balloons()
            time.sleep(2)
            st.rerun()

# 3. RETOMAR
if st.session_state.status == "PAUSADO":
    st.warning("⏸ Tarefa Pausada (Relógio rodando no descanso)")
    if col_btn1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", num_paginas):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
