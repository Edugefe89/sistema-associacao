import streamlit as st
import pandas as pd
from datetime import datetime
import utils # Importa o arquivo de funções

st.set_page_config(page_title="Login - Associação", page_icon="🔒")

# Tenta pegar o gerenciador de cookies
try:
    cookie_manager = utils.get_cookie_manager()
except:
    st.error("Erro ao carregar cookies. Verifique o arquivo utils.py")
    st.stop()

# Verifica se já tem cookie
cookie_user = cookie_manager.get("usuario_associacao")
if cookie_user:
    st.session_state['usuario_logado'] = cookie_user
    st.switch_page("pages/01_Execucao.py") # Joga direto pro sistema

st.title("🔒 Acesso Restrito")

try: usuarios = st.secrets["passwords"]
except: st.error("Configure os Secrets."); st.stop()

col1, col2 = st.columns([2,1])
with col1:
    user = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar", type="primary"):
        if user != "Selecione..." and senha == usuarios[user]:
            # Salva Cookie (7 dias)
            cookie_manager.set("usuario_associacao", user, expires_at=datetime.now() + pd.Timedelta(days=7))
            st.session_state['usuario_logado'] = user
            st.rerun()
        else:
            st.error("Dados incorretos.")
