import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz
import extra_streamlit_components as stx

# --- GERENCIADOR DE COOKIES (SEM CACHE) ---
# Importante: Não use @st.cache_resource aqui para evitar erro de Widget
def get_cookie_manager():
    return stx.CookieManager()

# --- CONEXÃO COM GOOGLE SHEETS ---
def get_client_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de Conexão Google: {e}")
        return None

# --- FUNÇÕES DE BANCO DE DADOS ---
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
            # Converte para string e remove espaços para garantir o match
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
        # Calcula segundos inteiros
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
        # Garante que Data_Hora é string antes de comparar
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "00:00", 0
        
        # Soma do Tempo
        seg = df['Tempo_Decorrido'].sum() if 'Tempo_Decorrido' in df.columns else 0
        h, m = int(seg // 3600), int((seg % 3600) // 60)
        
        # Conta Páginas (Conta quantos números tem separados por vírgula na última coluna)
        paginas = 0
        col_pags = df.columns[-1] 
        for item in df[col_pags]:
            if str(item).strip() not in ["", "-"]:
                paginas += len(str(item).split(','))
                
        return f"{h:02d}h {m:02d}m", paginas
    except: return "Erro", 0

# --- BARRA LATERAL PADRÃO (COM CORREÇÃO DE LOGOUT) ---
def sidebar_padrao():
    if 'usuario_logado' not in st.session_state:
        return

    usuario = st.session_state['usuario_logado'].title()
    with st.sidebar:
        st.write(f"👤 **{usuario}**")
        
        # Logout com Try/Except para evitar KeyError se o cookie já sumiu
        if st.button("Sair / Logout"):
            try:
                cookie_manager = get_cookie_manager()
                cookie_manager.delete("usuario_associacao")
            except KeyError:
                pass # Se der erro porque a chave não existe, apenas segue o baile
            except Exception as e:
                print(f"Erro ao deletar cookie: {e}")

            # Limpa toda a memória da sessão
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            st.rerun()

        st.divider()
        st.markdown("### 📊 Hoje")
        
        if 'resumo_dia' not in st.session_state:
             st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
        
        t, p = st.session_state['resumo_dia']
        c1, c2 = st.columns(2)
        c1.metric("Tempo", t)
        c2.metric("Pags", p)
        
        if st.button("Atualizar Métricas"):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            st.rerun()
