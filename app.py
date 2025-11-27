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
    # Pega usuários do Segredos do Streamlit
    try:
        usuarios_cadastrados = st.secrets["passwords"]
    except:
        st.error("Erro: Senhas não configuradas nos Secrets.")
        return False
        
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

# Função base de conexão
def get_client_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- NOVA FUNÇÃO: CARREGAR LISTA DE SITES (COM CACHE) ---
@st.cache_data(ttl=3600) # Guarda na memória por 1 hora (3600 seg)
def carregar_lista_sites():
    try:
        client = get_client_google()
        # Abre a aba de cadastro
        sheet = client.open("Sistema_Associacao").worksheet("cadastro_varreduras")
        # Pega todos os dados
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        # Cria a lista formatada "Cliente - Concorrente"
        if not df.empty and 'Cliente' in df.columns and 'Concorrente' in df.columns:
            # Filtra linhas vazias
            df = df[df['Cliente'] != '']
            lista_formatada = (df['Cliente'] + " - " + df['Concorrente']).tolist()
            return sorted(lista_formatada) # Retorna em ordem alfabética
        else:
            return ["Erro: Colunas Cliente/Concorrente não encontradas"]
            
    except Exception as e:
        return [f"Erro ao carregar lista: {e}"]

# Função de salvar log
def registrar_log(operador, site, letra, acao, num_paginas=0):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        
        tempo_decorrido = "00:00:00"
        
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            anterior = st.session_state['ultimo_timestamp']
            delta = agora - anterior
            tempo_decorrido = str(delta).split('.')[0]
        
        if acao == "INICIO" or acao == "RETOMADA":
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
            tempo_decorrido,
            num_paginas
        ]
        
        sheet.append_row(nova_linha)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

# --- APP PRINCIPAL ---

if not check_password():
    st.stop()

usuario = st.session_state['usuario_logado'].title()

with st.sidebar:
    st.write(f"👤 Logado: **{usuario}**")
    if st.button("Sair"):
        st.session_state['password_correct'] = False
        st.rerun()
    
    st.divider()
    st.markdown("### ⚙️ Admin")
    # Botão para forçar atualização da lista de sites
    if st.button("🔄 Atualizar Lista de Sites"):
        carregar_lista_sites.clear() # Limpa o cache
        st.rerun()

st.title("🔗 Controle de Associação")

# --- CARREGA OS SITES DA PLANILHA ---
with st.spinner("Carregando lista de sites..."):
    SITES_DINAMICOS = carregar_lista_sites()

LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

col1, col2 = st.columns(2)
with col1:
    site = st.selectbox("Site / Projeto", SITES_DINAMICOS)
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
        if 'ultimo_timestamp' in st.session_state:
            del st.session_state['ultimo_timestamp']
            
        if registrar_log(usuario, site, letra, "INICIO", num_paginas):
            st.session_state.status = "TRABALHANDO"
            st.rerun()

# 2. PAUSAR
if st.session_state.status == "TRABALHANDO":
    st.success(f"🟢 Trabalhando em: **{site}**")
    
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
    st.warning("⏸ Tarefa Pausada")
    if col_btn1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", num_paginas):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
