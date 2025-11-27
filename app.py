import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz

st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- CONEXÃO E CACHE ---

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
        return ["Erro: Verifique a aba cadastro_varreduras"]
    except:
        return ["Erro de Conexão"]

def buscar_memoria_paginas(site, letra):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        # Ajuste para garantir que leia como string e trate espaços
        chave_busca = f"{site} | {letra}".strip()
        
        if not df.empty and 'Chave' in df.columns:
            # Cria coluna temporária limpa para comparar
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
        st.error("Erro ao salvar memória de páginas.")

# --- LOGIN ---
def check_password():
    if st.session_state.get('password_correct', False):
        return True
    
    st.header("🔒 Login")
    try:
        usuarios = st.secrets["passwords"]
    except:
        st.error("Configure os Secrets.")
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

# --- REGISTRO DE LOGS (ATUALIZADO PARA SEGUNDOS) ---
def registrar_log(operador, site, letra, acao, num_paginas=0):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        
        # MUDANÇA AQUI: Padrão agora é 0 (número) e não texto
        tempo_decorrido_segundos = 0
        
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            delta = agora - st.session_state['ultimo_timestamp']
            # Pega o total de segundos inteiro
            tempo_decorrido_segundos = int(delta.total_seconds())
        
        if acao in ["INICIO", "RETOMADA"]:
             st.session_state['ultimo_timestamp'] = agora

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
            tempo_decorrido_segundos, # Agora salva apenas o número (ex: 3600)
            num_paginas
        ]
        sheet.append_row(nova_linha)
        return True
    except Exception as e:
        st.error(f"Erro: {e}")
        return False

# --- APP PRINCIPAL ---
if not check_password():
    st.stop()

usuario = st.session_state['usuario_logado'].title()

with st.sidebar:
    st.write(f"👤 **{usuario}**")
    if st.button("Sair"):
        st.session_state['password_correct'] = False
        st.rerun()
    st.divider()
    if st.button("🔄 Atualizar Sites"):
        carregar_lista_sites.clear()
        st.rerun()

st.title("🔗 Controle de Associação")

SITES_DINAMICOS = carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

col1, col2 = st.columns(2)
with col1:
    site_selecionado = st.selectbox("Site / Projeto", SITES_DINAMICOS)
with col2:
    letra_selecionada = st.selectbox("Letra / Lote", LETRAS)

st.divider()

# --- LÓGICA DE PÁGINAS ---
if 'paginas_memoria' not in st.session_state:
    st.session_state.paginas_memoria = {}

chave_atual = f"{site_selecionado}_{letra_selecionada}"

if st.session_state.get('ultima_selecao') != chave_atual:
    with st.spinner("Verificando histórico..."):
        paginas_encontradas = buscar_memoria_paginas(site_selecionado, letra_selecionada)
        st.session_state.paginas_memoria['valor'] = paginas_encontradas
        st.session_state['ultima_selecao'] = chave_atual

paginas_db = st.session_state.paginas_memoria.get('valor')

if paginas_db is not None:
    st.info(f"📚 Letra já cadastrada com **{paginas_db} páginas**.")
    num_paginas_final = paginas_db
else:
    st.warning("🆕 Letra nova! Informe as páginas.")
    num_paginas_final = st.number_input("Quantidade de Páginas:", min_value=1, step=1)

# --- BOTÕES ---
st.divider()

if 'status' not in st.session_state:
    st.session_state.status = "PARADO"

c1, c2, c3 = st.columns(3)

if st.session_state.status == "PARADO":
    if c1.button("▶️ INICIAR", type="primary", use_container_width=True):
        if paginas_db is None:
            salvar_nova_pagina(site_selecionado, letra_selecionada, num_paginas_final)
            st.session_state.paginas_memoria['valor'] = num_paginas_final
            
        if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
        
        if registrar_log(usuario, site_selecionado, letra_selecionada, "INICIO", num_paginas_final):
            st.session_state.status = "TRABALHANDO"
            st.rerun()

elif st.session_state.status == "TRABALHANDO":
    st.success(f"🔨 Trabalhando em **{site_selecionado} - Letra {letra_selecionada}**")
    if c2.button("⏸ PAUSAR", use_container_width=True):
        if registrar_log(usuario, site_selecionado, letra_selecionada, "PAUSA", num_paginas_final):
            st.session_state.status = "PAUSADO"
            st.rerun()
    if c3.button("✅ FINALIZAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site_selecionado, letra_selecionada, "FIM", num_paginas_final):
            st.session_state.status = "PARADO"
            if 'id_sessao' in st.session_state: del st.session_state['id_sessao']
            st.balloons()
            time.sleep(2)
            st.rerun()

elif st.session_state.status == "PAUSADO":
    st.warning("⏸ Pausado")
    if c1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site_selecionado, letra_selecionada, "RETOMADA", num_paginas_final):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
