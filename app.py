import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz
import extra_streamlit_components as stx

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- 1. GERENCIADOR DE COOKIES ---
# (Sem cache para não bugar)
def get_manager():
    return stx.CookieManager()

# --- 2. CONEXÃO GOOGLE SHEETS ---
def get_client_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de Conexão Google: {e}")
        return None

# --- 3. FUNÇÕES DE DADOS (COM CACHE) ---
@st.cache_data(ttl=300)
def carregar_lista_sites():
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("cadastro_varreduras")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        if not df.empty and 'Cliente' in df.columns:
            df = df[df['Cliente'] != '']
            lista = (df['Cliente'] + " - " + df['Concorrente']).tolist()
            return sorted(lista)
        return []
    except: return []

def buscar_status_paginas(site, letra):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        chave = f"{site} | {letra}".strip()
        if not df.empty and 'Chave' in df.columns:
            res = df[df['Chave'].astype(str).str.strip() == chave]
            if not res.empty:
                total = int(res.iloc[0]['Qtd_Paginas'])
                feitas_str = str(res.iloc[0]['Paginas_Concluidas'])
                feitas = [int(x) for x in feitas_str.split(',') if x.strip().isdigit()] if feitas_str else []
                return total, feitas
        return None, []
    except: return None, []

def salvar_progresso(site, letra, total, novas):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        _, ja_feitas = buscar_status_paginas(site, letra)
        lista_final = sorted(list(set(ja_feitas + novas)))
        txt_salvar = ", ".join(map(str, lista_final))
        chave = f"{site} | {letra}".strip()
        cell = sheet.find(chave)
        if cell:
            sheet.update_cell(cell.row, 5, txt_salvar)
            sheet.update_cell(cell.row, 4, total)
        else:
            sheet.append_row([chave, site, letra, total, txt_salvar])
    except: pass

def registrar_log(operador, site, letra, acao, total, novas):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        fuso = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso)
        
        tempo = 0
        if acao != "INICIO" and 'ultimo_timestamp' in st.session_state:
            tempo = int((agora - st.session_state['ultimo_timestamp']).total_seconds())
        
        if acao in ["INICIO", "RETOMADA"]: st.session_state['ultimo_timestamp'] = agora
        if 'id_sessao' not in st.session_state: st.session_state.id_sessao = str(uuid.uuid4())
        
        str_novas = ", ".join(map(str, novas)) if novas else "-"
        sheet.append_row([st.session_state.id_sessao, operador, site, letra, acao, 
                          agora.strftime("%d/%m/%Y %H:%M:%S"), str(agora.timestamp()), tempo, str_novas])
        return True
    except: return False

def calcular_resumo_diario(usuario):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return "00:00", 0
        
        df = df[df['Operador'] == usuario]
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "00:00", 0
        
        seg = df['Tempo_Decorrido'].sum() if 'Tempo_Decorrido' in df.columns else 0
        h, m = int(seg // 3600), int((seg % 3600) // 60)
        
        paginas = 0
        col_pags = df.columns[-1] 
        for item in df[col_pags]:
            if str(item).strip() not in ["", "-"]:
                paginas += len(str(item).split(','))
                
        return f"{h:02d}h {m:02d}m", paginas
    except: return "Calculando...", 0

# --- 4. LÓGICA DE LOGIN ---
cookie_manager = get_manager()
cookie_usuario = cookie_manager.get(cookie="usuario_associacao")

# Se não estiver logado via cookie ou via sessão, mostra tela de login
if not cookie_usuario and not st.session_state.get('password_correct', False):
    st.title("🔒 Acesso Restrito")
    try: usuarios = st.secrets["passwords"]
    except: st.error("Configure os Secrets."); st.stop()

    col1, col2 = st.columns([2,1])
    with col1:
        user_input = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
        pass_input = st.text_input("Senha", type="password")

        if st.button("Entrar", type="primary"):
            if user_input != "Selecione..." and pass_input == usuarios[user_input]:
                st.session_state['password_correct'] = True
                st.session_state['usuario_logado'] = user_input
                # Salva Cookie (7 dias)
                cookie_manager.set("usuario_associacao", user_input, expires_at=datetime.now() + pd.Timedelta(days=7))
                st.rerun()
            else:
                st.error("Dados incorretos.")
    st.stop() # Para o código aqui se não estiver logado

# Se chegou aqui, está logado!
if cookie_usuario:
    st.session_state['usuario_logado'] = cookie_usuario

usuario = st.session_state['usuario_logado'].title()

# --- 5. BARRA LATERAL (LOGOUT + RESUMO) ---
with st.sidebar:
    st.write(f"👤 **{usuario}**")
    
    # Botão de Sair (Deleta Cookie e Limpa Sessão)
    if st.button("Sair / Logout"):
        try:
            cookie_manager.delete("usuario_associacao")
        except: pass
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.divider()
    st.markdown("### 📊 Produção Hoje")
    
    if 'resumo_dia' not in st.session_state:
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
    
    t, p = st.session_state['resumo_dia']
    c1, c2 = st.columns(2)
    c1.metric("Tempo", t)
    c2.metric("Páginas", p)
    
    if st.button("Atualizar Métricas"):
        st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
        st.rerun()
    
    st.divider()
    if st.button("🔄 Atualizar Lista Sites"): carregar_lista_sites.clear(); st.rerun()

# --- 6. SISTEMA PRINCIPAL (INTERFACE) ---
st.title("🔗 Controle de Progresso")

SITES = carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site", SITES)
with c2: letra = st.selectbox("Letra", LETRAS)

chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    tot, feitas = buscar_status_paginas(site, letra)
    st.session_state.mem_tot = tot
    st.session_state.mem_feit = feitas
    st.session_state['last_sel'] = chave

tot_pg = st.session_state.get('mem_tot')
feitas_pg = st.session_state.get('mem_feit', [])
faltam = []
bloq = False

if tot_pg:
    faltam = [p for p in range(1, tot_pg+1) if p not in feitas_pg]
    prog = len(feitas_pg)/tot_pg if tot_pg > 0 else 0
    st.progress(prog, f"{len(feitas_pg)}/{tot_pg} ({int(prog*100)}%)")
    if not faltam: st.success("Letra Concluída!"); bloq = True
else:
    st.warning("Letra Nova")
    tot_pg = st.number_input("Total Páginas", 1, step=1)

st.divider()
if 'status' not in st.session_state: st.session_state.status = "PARADO"

sel_agora = []
if st.session_state.status == "TRABALHANDO" and tot_pg and faltam:
    st.markdown("### 📝 Feito agora:")
    sel_agora = st.multiselect("Páginas:", options=faltam)

b1, b2, b3 = st.columns(3)

if st.session_state.status == "PARADO":
    if not bloq:
        if b1.button("▶️ INICIAR", type="primary", use_container_width=True):
            if tot_pg and st.session_state.get('mem_tot') is None:
                salvar_progresso(site, letra, tot_pg, [])
                st.session_state.mem_tot = tot_pg
            if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
            if registrar_log(usuario, site, letra, "INICIO", tot_pg, []):
                st.session_state.status = "TRABALHANDO"; st.rerun()
    else: st.info("Finalizado.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        if registrar_log(usuario, site, letra, "PAUSA", tot_pg, sel_agora):
            if sel_agora:
                salvar_progresso(site, letra, tot_pg, sel_agora)
                st.session_state.mem_feit += sel_agora
                st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            st.session_state.status = "PAUSADO"; st.rerun()
    
    comp = False
    if faltam and len(sel_agora) == len(faltam): comp = True
    
    if comp:
        if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            if registrar_log(usuario, site, letra, "FIM", tot_pg, sel_agora):
                salvar_progresso(site, letra, tot_pg, sel_agora)
                st.session_state.mem_feit += sel_agora
                st.session_state.status = "PARADO"
                st.balloons(); time.sleep(1); st.rerun()
    else:
        b3.markdown(f"<div style='text-align:center; color:gray; font-size:12px; padding-top:10px;'>Faltam {len(faltam)} pgs</div>", unsafe_allow_html=True)

elif st.session_state.status == "PAUSADO":
    st.warning("Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", tot_pg, []):
            st.session_state.status = "TRABALHANDO"; st.rerun()
