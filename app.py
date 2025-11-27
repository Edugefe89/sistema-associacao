import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz
import extra_streamlit_components as stx

st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- CONEXÃO ---
def get_client_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
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
        return ["Erro: Verifique cadastro"]
    except:
        return ["Erro Conexão"]

# --- FUNÇÃO NOVA: RESUMO DIÁRIO ---
def calcular_resumo_diario(usuario):
    """Lê os logs do dia para mostrar produtividade"""
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        if df.empty: return "00:00", 0

        # Filtra pelo Usuário
        df = df[df['Operador'] == usuario]
        
        # Filtra pela Data de Hoje
        fuso_br = pytz.timezone('America/Sao_Paulo')
        hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")
        
        # Garante que a coluna Data_Hora seja string para comparar
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "00:00", 0

        # 1. Soma do Tempo (em segundos)
        total_segundos = df['Tempo_Decorrido'].sum()
        # Formata HH:MM
        horas = int(total_segundos // 3600)
        minutos = int((total_segundos % 3600) // 60)
        tempo_formatado = f"{horas:02d}h {minutos:02d}m"

        # 2. Soma das Páginas (Conta itens na lista separada por vírgula)
        # Coluna 9 é a lista de páginas (índice 8 se for 0-based, ou pelo nome)
        # Vamos assumir que a coluna se chama 'Paginas_Feitas_Turno' (última coluna)
        # Se o cabeçalho mudou, pegamos pela última coluna do log
        total_paginas = 0
        
        # Itera para contar quantas páginas tem em cada célula "1, 2, 3"
        for item in df.iloc[:, -1]: # Pega a última coluna
            if str(item).strip() not in ["", "-"]:
                lista = str(item).split(',')
                total_paginas += len(lista)
                
        return tempo_formatado, total_paginas

    except Exception as e:
        return "Erro", 0

# --- FUNÇÕES PÁGINAS ---
def buscar_status_paginas(site, letra):
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
                total = int(resultado.iloc[0]['Qtd_Paginas'])
                feitas_str = str(resultado.iloc[0]['Paginas_Concluidas'])
                lista_feitas = []
                if feitas_str and feitas_str != "":
                    lista_feitas = [int(x) for x in feitas_str.split(',') if x.strip().isdigit()]
                return total, lista_feitas
        return None, []
    except:
        return None, []

def salvar_progresso(site, letra, total_paginas, novas_paginas_feitas):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        _, ja_feitas = buscar_status_paginas(site, letra)
        lista_atualizada = sorted(list(set(ja_feitas + novas_paginas_feitas)))
        texto_para_salvar = ", ".join(map(str, lista_atualizada))
        chave_busca = f"{site} | {letra}".strip()
        cell = sheet.find(chave_busca)
        if cell:
            sheet.update_cell(cell.row, 5, texto_para_salvar)
            sheet.update_cell(cell.row, 4, total_paginas)
        else:
            sheet.append_row([chave_busca, site, letra, total_paginas, texto_para_salvar])
    except: pass

# --- LOGIN & COOKIES ---
def get_manager(): return stx.CookieManager()
cookie_manager = get_manager()

def check_password():
    cookie_usuario = cookie_manager.get(cookie="usuario_associacao")
    if cookie_usuario:
        st.session_state['password_correct'] = True
        st.session_state['usuario_logado'] = cookie_usuario
        return True
    
    if st.session_state.get('password_correct', False): return True
    st.header("🔒 Acesso Restrito")
    try: usuarios = st.secrets["passwords"]
    except: st.error("Erro Config."); return False
    user_input = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
    pass_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user_input != "Selecione..." and pass_input == usuarios[user_input]:
            st.session_state['password_correct'] = True
            st.session_state['usuario_logado'] = user_input
            cookie_manager.set("usuario_associacao", user_input, expires_at=datetime.now() + pd.Timedelta(days=7))
            st.rerun()
        else: st.error("Senha incorreta.")
    return False

def logout():
    cookie_manager.delete("usuario_associacao")
    st.session_state['password_correct'] = False
    st.rerun()

# --- LOGS ---
def registrar_log(operador, site, letra, acao, num_paginas_total, paginas_feitas_agora):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        
        tempo_decorrido = 0
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            delta = agora - st.session_state['ultimo_timestamp']
            tempo_decorrido = int(delta.total_seconds())
        
        if acao in ["INICIO", "RETOMADA"]: st.session_state['ultimo_timestamp'] = agora
        if 'id_sessao' not in st.session_state: st.session_state.id_sessao = str(uuid.uuid4())

        str_paginas_agora = ", ".join(map(str, paginas_feitas_agora)) if paginas_feitas_agora else "-"

        nova_linha = [st.session_state.id_sessao, operador, site, letra, acao, 
                      agora.strftime("%d/%m/%Y %H:%M:%S"), str(agora.timestamp()), 
                      tempo_decorrido, str_paginas_agora]
        sheet.append_row(nova_linha)
        return True
    except: return False

# --- APP PRINCIPAL ---
if not check_password(): st.stop()
usuario = st.session_state['usuario_logado'].title()

# --- BARRA LATERAL COM RESUMO ---
with st.sidebar:
    st.write(f"👤 **{usuario}**")
    
    # Exibe Resumo se não estiver logando agora
    if st.session_state.get('password_correct'):
        st.markdown("---")
        st.markdown("### 📊 Produção Hoje")
        
        # Botão discreto para atualizar estatísticas
        if st.button("Atualizar Métricas"):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            
        # Carrega dados (usa memória se tiver, senão calcula)
        if 'resumo_dia' not in st.session_state:
             st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
        
        tempo_hoje, pags_hoje = st.session_state['resumo_dia']
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Tempo", tempo_hoje)
        col_m2.metric("Páginas", pags_hoje)
        st.markdown("---")

    if st.button("Sair"): logout()
    
    st.markdown("---")
    if st.button("🔄 Atualizar Lista Sites"): carregar_lista_sites.clear(); st.rerun()

st.title("Controle de Progresso")

SITES = carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site", SITES)
with c2: letra = st.selectbox("Letra", LETRAS)

chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    total_db, feitas_db = buscar_status_paginas(site, letra)
    st.session_state.memoria_total = total_db
    st.session_state.memoria_feitas = feitas_db
    st.session_state['last_sel'] = chave

total_pg = st.session_state.get('memoria_total')
feitas_pg = st.session_state.get('memoria_feitas', [])
faltam = []
bloqueado = False

if total_pg is not None:
    todas = list(range(1, total_pg + 1))
    faltam = [p for p in todas if p not in feitas_pg]
    progresso = len(feitas_pg) / total_pg if total_pg > 0 else 0
    st.progress(progresso, text=f"{len(feitas_pg)}/{total_pg} ({int(progresso*100)}%)")
    if not faltam: st.success("Letra Concluída"); bloqueado = True
else:
    st.warning("Letra Nova")
    total_pg = st.number_input("Total Páginas:", 1, step=1)

st.divider()
if 'status' not in st.session_state: st.session_state.status = "PARADO"

paginas_agora = []
if st.session_state.status == "TRABALHANDO" and total_pg and faltam:
    st.markdown("### Seleção de Páginas")
    paginas_agora = st.multiselect("Concluído agora:", options=faltam)

b1, b2, b3 = st.columns(3)

if st.session_state.status == "PARADO":
    if not bloqueado:
        if b1.button("▶️ INICIAR", type="primary", use_container_width=True):
            if total_pg and st.session_state.get('memoria_total') is None:
                salvar_progresso(site, letra, total_pg, [])
                st.session_state.memoria_total = total_pg
            if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
            if registrar_log(usuario, site, letra, "INICIO", total_pg, []):
                st.session_state.status = "TRABALHANDO"
                st.rerun()
    else: st.info("Selecione outra letra.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        if registrar_log(usuario, site, letra, "PAUSA", total_pg, paginas_agora):
            if paginas_agora:
                salvar_progresso(site, letra, total_pg, paginas_agora)
                st.session_state.memoria_feitas += paginas_agora
                # Atualiza métrica lateral na hora
                st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            st.session_state.status = "PAUSADO"
            st.rerun()
    
    completo = False
    if faltam and len(paginas_agora) == len(faltam): completo = True
    
    if completo:
        if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            if registrar_log(usuario, site, letra, "FIM", total_pg, paginas_agora):
                if paginas_agora:
                    salvar_progresso(site, letra, total_pg, paginas_agora)
                    st.session_state.memoria_feitas += paginas_agora
                    st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
                st.session_state.status = "PARADO"
                if 'id_sessao' in st.session_state: del st.session_state['id_sessao']
                time.sleep(1); st.rerun()
    else:
        b3.markdown(f"<div style='text-align:center; color:gray; font-size:12px; padding-top:10px;'>Faltam {len(faltam)} pgs</div>", unsafe_allow_html=True)

elif st.session_state.status == "PAUSADO":
    st.warning("Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", total_pg, []):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
