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

# --- 3. FUNÇÕES DE DADOS ---
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

def salvar_progresso(site, letra, total_paginas, novas_paginas_feitas):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        
        _, ja_feitas = buscar_status_paginas(site, letra)
        
        lista_completa = sorted(list(set(ja_feitas + novas_paginas_feitas)))
        
        # FAXINA DE DADOS (Remove páginas maiores que o total, ex: 2003)
        lista_limpa = [p for p in lista_completa if p <= int(total_paginas)]
        
        texto_para_salvar = ", ".join(map(str, lista_limpa))
        
        chave_busca = f"{site} | {letra}".strip()
        cell = sheet.find(chave_busca)
        
        if cell:
            sheet.update_cell(cell.row, 5, texto_para_salvar)
            sheet.update_cell(cell.row, 4, total_paginas)
        else:
            sheet.append_row([chave_busca, site, letra, total_paginas, texto_para_salvar])
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
        
        nova_linha = [
            st.session_state.id_sessao, 
            operador, 
            site, 
            letra, 
            acao, 
            agora.strftime("%d/%m/%Y %H:%M:%S"), 
            str(agora.timestamp()), 
            tempo, 
            str_novas,
            total
        ]
        sheet.append_row(nova_linha)
        return True
    except: return False

def calcular_resumo_diario(usuario):
    """Calcula tempo PRODUTIVO e páginas feitas hoje"""
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return "0h 0m", 0
        
        # 1. Filtra Usuário
        df = df[df['Operador'] == usuario]
        
        # 2. Filtra Hoje
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        # Garante que é string para não dar erro
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "0h 0m", 0
        
        # --- CORREÇÃO DO TEMPO (SÓ PRODUTIVO) ---
        # Só soma o tempo se a ação foi PAUSA ou FIM. 
        # (Ignora RETOMADA, pois é o tempo de descanso)
        df_produtivo = df[df['Acao'].isin(['PAUSA', 'FIM'])]
        seg = df_produtivo['Tempo_Decorrido'].sum() if 'Tempo_Decorrido' in df_produtivo.columns else 0
        
        h, m = int(seg // 3600), int((seg % 3600) // 60)
        s = int(seg % 60) # Opcional: se quiser mostrar segundos também
        
        # Se quiser mostrar segundos, mude o return final. 
        # Por enquanto mantive Horas e Minutos.
        tempo_str = f"{h}h {m}m"
        
        # --- CORREÇÃO DAS PÁGINAS (COLUNA CERTA) ---
        paginas = 0
        
        # Procura explicitamente pela coluna 'Paginas_Turno'
        if 'Paginas_Turno' in df.columns:
            for item in df['Paginas_Turno']:
                texto = str(item).strip()
                # Ignora traços e vazios
                if texto and texto not in ["", "-"]:
                    # Quebra a lista "1, 2, 3" e conta
                    lista = [x for x in texto.split(',') if x.strip()]
                    paginas += len(lista)
        
        return tempo_str, paginas

    except Exception as e:
        print(f"Erro resumo: {e}")
        return "...", 0

# --- 4. LÓGICA DE LOGIN ---
cookie_manager = get_manager()
cookie_usuario = cookie_manager.get(cookie="usuario_associacao")

if not cookie_usuario and not st.session_state.get('password_correct', False):
    st.title("🔒 Acesso Restrito")
    try: usuarios = st.secrets["passwords"]
    except: st.error("Configure os Secrets."); st.stop()

    col1, col2 = st.columns([2,1])
    with col1:
        user_input = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
        pass_input = st.text_input("Senha", type="password")

        if st.button("Entrar", type="primary"):
            with st.spinner("Autenticando..."):
                if user_input != "Selecione..." and pass_input == usuarios[user_input]:
                    st.session_state['password_correct'] = True
                    st.session_state['usuario_logado'] = user_input
                    cookie_manager.set("usuario_associacao", user_input, expires_at=datetime.now() + pd.Timedelta(days=7))
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Dados incorretos.")
    st.stop()

if cookie_usuario:
    st.session_state['usuario_logado'] = cookie_usuario

usuario = st.session_state['usuario_logado'].title()

# --- 5. BARRA LATERAL (AJUSTADA PARA NÃO CORTAR TEXTO) ---
with st.sidebar:
    st.write(f"👤 **{usuario}**")
    
    if st.button("Sair / Logout"):
        with st.spinner("Saindo..."):
            try: cookie_manager.delete("usuario_associacao")
            except: pass
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            time.sleep(1)
            st.rerun()

    st.divider()
    st.markdown("### 📊 Produção Hoje")
    
    if 'resumo_dia' not in st.session_state:
        with st.spinner("Calculando..."):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
    
    t, p = st.session_state['resumo_dia']
    
    # MUDANÇA AQUI: Layout vertical para não cortar
    st.metric("⏱ Tempo Trabalhado", t)
    st.metric("📄 Páginas Entregues", p)
    
    if st.button("Atualizar Métricas"):
        with st.spinner("Recalculando..."):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            st.rerun()
    
    st.divider()
    if st.button("🔄 Atualizar Lista Sites"):
        with st.spinner("Baixando sites..."):
            carregar_lista_sites.clear()
            st.rerun()

# --- 6. SISTEMA PRINCIPAL ---
st.title("🔗 Controle de Progresso")

with st.spinner("Carregando sistema..."):
    SITES = carregar_lista_sites()
    LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site / Projeto", SITES)
with c2: letra = st.selectbox("Letra / Lote", LETRAS)

# Bloqueio visual durante consulta
chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    with st.spinner(f"Verificando histórico..."):
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
            with st.spinner("Iniciando..."):
                if tot_pg and st.session_state.get('mem_tot') is None:
                    salvar_progresso(site, letra, tot_pg, [])
                    st.session_state.mem_tot = tot_pg
                if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
                if registrar_log(usuario, site, letra, "INICIO", tot_pg, []):
                    st.session_state.status = "TRABALHANDO"
                    st.rerun()
    else: st.info("Finalizado.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        with st.spinner("Salvando pausa..."):
            if registrar_log(usuario, site, letra, "PAUSA", tot_pg, sel_agora):
                if sel_agora:
                    salvar_progresso(site, letra, tot_pg, sel_agora)
                    st.session_state.mem_feit += sel_agora
                    st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
                st.session_state.status = "PAUSADO"
                st.rerun()
    
    comp = False
    if faltam and len(sel_agora) == len(faltam): comp = True
    
    if comp:
        if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            with st.spinner("Finalizando..."):
                if registrar_log(usuario, site, letra, "FIM", tot_pg, sel_agora):
                    salvar_progresso(site, letra, tot_pg, sel_agora)
                    st.session_state.mem_feit += sel_agora
                    st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
                    st.session_state.status = "PARADO"
                    st.balloons(); time.sleep(2); st.rerun()
    else:
        b3.markdown(f"<div style='text-align:center; color:gray; font-size:12px; padding-top:10px;'>Faltam {len(faltam)} pgs</div>", unsafe_allow_html=True)

elif st.session_state.status == "PAUSADO":
    st.warning("Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        with st.spinner("Retomando..."):
            if registrar_log(usuario, site, letra, "RETOMADA", tot_pg, []):
                st.session_state.status = "TRABALHANDO"
                st.rerun()


