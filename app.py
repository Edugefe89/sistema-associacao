import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz

st.set_page_config(page_title="Sistema V2", page_icon="🚀") # Mudei o ícone para confirmar update

# --- CONEXÃO ---
def get_client_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=3600)
def carregar_lista_sites():
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("cadastro_varreduras")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        if not df.empty and 'Cliente' in df.columns and 'Concorrente' in df.columns:
            df = df[df['Cliente'] != '']
            lista_formatada = (df['Cliente'] + " - " + df['Concorrente']).tolist()
            return sorted(lista_formatada)
        return ["Erro: Verifique cadastro_varreduras"]
    except:
        return ["Erro Conexão Lista"]

def buscar_memoria_paginas(site, letra):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        chave_busca = f"{site} | {letra}".strip()
        if not df.empty and 'Chave' in df.columns:
            df['Chave_Limpa'] = df['Chave'].astype(str).str.strip()
            resultado = df[df['Chave_Limpa'] == chave_busca]
            if not resultado.empty:
                return int(resultado.iloc[0]['Qtd_Paginas'])
        return None
    except:
        return None

def salvar_nova_pagina(site, letra, qtd):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        chave = f"{site} | {letra}"
        sheet.append_row([chave, site, letra, qtd])
    except:
        st.error("Erro ao salvar página.")

def check_password():
    if st.session_state.get('password_correct', False): return True
    st.header("🔒 Login V2")
    try:
        usuarios = st.secrets["passwords"]
    except:
        st.error("Sem Secrets.")
        return False
    user_input = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
    pass_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user_input != "Selecione..." and pass_input == usuarios[user_input]:
            st.session_state['password_correct'] = True
            st.session_state['usuario_logado'] = user_input
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False

# --- REGISTRO COM DEBUG ---
def registrar_log(operador, site, letra, acao, num_paginas=0):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        
        # --- CÁLCULO FORÇADO PARA INTEIRO ---
        segundos_int = 0
        
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            delta = agora - st.session_state['ultimo_timestamp']
            segundos_int = int(delta.total_seconds()) # Garante que é número inteiro
            
            # --- O ESPIÃO ---
            st.toast(f"🕵️ DEBUG: O Python calculou {segundos_int} segundos.")
        
        if acao in ["INICIO", "RETOMADA"]:
             st.session_state['ultimo_timestamp'] = agora

        if 'id_sessao' not in st.session_state:
            st.session_state.id_sessao = str(uuid.uuid4())

        nova_linha = [
            st.session_state.id_sessao, operador, site, letra, acao, 
            agora.strftime("%d/%m/%Y %H:%M:%S"), str(agora.timestamp()), 
            segundos_int, # <--- ENVIANDO O INTEIRO
            num_paginas
        ]
        sheet.append_row(nova_linha)
        return True
    except Exception as e:
        st.error(f"Erro: {e}")
        return False

# --- APP ---
if not check_password(): st.stop()
usuario = st.session_state['usuario_logado'].title()

with st.sidebar:
    st.write(f"👤 {usuario}")
    if st.button("Sair"):
        st.session_state['password_correct'] = False
        st.rerun()
    st.divider()
    if st.button("🔄 Atualizar Sites"):
        carregar_lista_sites.clear()
        st.rerun()

st.title("🔗 Controle V2 (Inteiro)") # Título Mudou

SITES = carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site", SITES)
with c2: letra = st.selectbox("Letra", LETRAS)

if 'paginas' not in st.session_state: st.session_state.paginas = {}
chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    val = buscar_memoria_paginas(site, letra)
    st.session_state.paginas['val'] = val
    st.session_state['last_sel'] = chave

pg_db = st.session_state.paginas.get('val')
if pg_db: 
    st.info(f"📚 Páginas: {pg_db}")
    qtd_pg = pg_db
else: 
    st.warning("🆕 Novo")
    qtd_pg = st.number_input("Qtd Páginas", 1, step=1)

st.divider()
if 'status' not in st.session_state: st.session_state.status = "PARADO"

b1, b2, b3 = st.columns(3)

if st.session_state.status == "PARADO":
    if b1.button("▶️ INICIAR", type="primary", use_container_width=True):
        if not pg_db:
            salvar_nova_pagina(site, letra, qtd_pg)
            st.session_state.paginas['val'] = qtd_pg
        if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
        if registrar_log(usuario, site, letra, "INICIO", qtd_pg):
            st.session_state.status = "TRABALHANDO"
            st.rerun()

elif st.session_state.status == "TRABALHANDO":
    st.success(f"🔨 Trabalhando")
    if b2.button("⏸ PAUSAR", use_container_width=True):
        if registrar_log(usuario, site, letra, "PAUSA", qtd_pg):
            st.session_state.status = "PAUSADO"
            st.rerun()
    if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "FIM", qtd_pg):
            st.session_state.status = "PARADO"
            if 'id_sessao' in st.session_state: del st.session_state['id_sessao']
            st.balloons()
            time.sleep(2)
            st.rerun()

elif st.session_state.status == "PAUSADO":
    st.warning("⏸ Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", qtd_pg):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
