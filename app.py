import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz

st.set_page_config(page_title="Sistema de Associação", page_icon="🔗")

# --- CONEXÃO ---
def get_client_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300) # Cache menor (5 min) para atualizar progresso rápido
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

# --- FUNÇÕES DE PÁGINAS (NOVA LÓGICA) ---
def buscar_status_paginas(site, letra):
    """Retorna: (Total de Páginas, Lista de Páginas JÁ FEITAS)"""
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
                
                # Lógica para ler "1, 2, 3" e transformar em lista [1, 2, 3]
                feitas_str = str(resultado.iloc[0]['Paginas_Concluidas'])
                lista_feitas = []
                if feitas_str and feitas_str != "":
                    # Remove espaços e quebra por vírgula
                    lista_feitas = [int(x) for x in feitas_str.split(',') if x.strip().isdigit()]
                
                return total, lista_feitas
        return None, []
    except:
        return None, []

def salvar_progresso(site, letra, total_paginas, novas_paginas_feitas):
    """Atualiza a lista de páginas feitas no banco"""
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        
        # Primeiro, buscamos o que já estava feito para somar com o novo
        # (Para não perder o que outro estagiário fez)
        _, ja_feitas = buscar_status_paginas(site, letra)
        
        # Junta as listas e remove duplicadas
        lista_atualizada = sorted(list(set(ja_feitas + novas_paginas_feitas)))
        
        # Transforma em texto para salvar: "1, 2, 3"
        texto_para_salvar = ", ".join(map(str, lista_atualizada))
        
        # Busca a linha certa para editar
        chave_busca = f"{site} | {letra}".strip()
        cell = sheet.find(chave_busca)
        
        if cell:
            # Atualiza coluna E (Coluna 5) -> Paginas_Concluidas
            sheet.update_cell(cell.row, 5, texto_para_salvar)
            # Garante que o total está certo na coluna D (Coluna 4)
            sheet.update_cell(cell.row, 4, total_paginas)
        else:
            # Se não achou (é novo), cria linha nova
            sheet.append_row([chave_busca, site, letra, total_paginas, texto_para_salvar])
            
    except Exception as e:
        st.error(f"Erro ao salvar progresso: {e}")

# --- LOGIN ---
def check_password():
    if st.session_state.get('password_correct', False): return True
    st.header("🔒 Login")
    try: usuarios = st.secrets["passwords"]
    except: st.error("Sem Secrets."); return False
    user_input = st.selectbox("Usuário", ["Selecione..."] + list(usuarios.keys()))
    pass_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if user_input != "Selecione..." and pass_input == usuarios[user_input]:
            st.session_state['password_correct'] = True; st.session_state['usuario_logado'] = user_input; st.rerun()
        else: st.error("Senha incorreta.")
    return False

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

        # Formata a lista de páginas feitas AGORA para salvar no log
        str_paginas_agora = ", ".join(map(str, paginas_feitas_agora)) if paginas_feitas_agora else "-"

        nova_linha = [
            st.session_state.id_sessao, operador, site, letra, acao, 
            agora.strftime("%d/%m/%Y %H:%M:%S"), str(agora.timestamp()), 
            tempo_decorrido, 
            str_paginas_agora # Salva quais páginas foram feitas NESTE turno
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
    if st.button("Sair"): st.session_state['password_correct'] = False; st.rerun()
    st.divider()
    if st.button("🔄 Atualizar Sites"): carregar_lista_sites.clear(); st.rerun()

st.title("🔗 Controle de Progresso")

SITES = carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site", SITES)
with c2: letra = st.selectbox("Letra", LETRAS)

# --- LÓGICA DE CHECKLIST ---
chave = f"{site}_{letra}"

# Se mudou seleção, busca no banco
if st.session_state.get('last_sel') != chave:
    total_db, feitas_db = buscar_status_paginas(site, letra)
    st.session_state.memoria_total = total_db
    st.session_state.memoria_feitas = feitas_db
    st.session_state['last_sel'] = chave

total_pg = st.session_state.get('memoria_total')
feitas_pg = st.session_state.get('memoria_feitas', [])

if total_pg is not None:
    # CÁLCULO DE PROGRESSO
    progresso = len(feitas_pg) / total_pg if total_pg > 0 else 0
    st.progress(progresso, text=f"Progresso da Letra: {len(feitas_pg)} de {total_pg} páginas concluídas ({int(progresso*100)}%)")
    
    # Define quais páginas faltam
    todas_paginas = list(range(1, total_pg + 1))
    faltam = [p for p in todas_paginas if p not in feitas_pg]
    
    if not faltam:
        st.success("🏆 Esta letra foi 100% concluída!")
        bloqueado = True
    else:
        bloqueado = False
        
else:
    st.warning("🆕 Letra Nova")
    total_pg = st.number_input("Total de Páginas:", 1, step=1)
    faltam = [] # Ainda não salvou
    bloqueado = False

st.divider()
if 'status' not in st.session_state: st.session_state.status = "PARADO"

# SELETOR DE PÁGINAS FEITAS AGORA (Só aparece se estiver trabalhando)
paginas_selecionadas_agora = []
if st.session_state.status == "TRABALHANDO" and total_pg is not None:
    st.markdown("### 📝 O que você concluiu agora?")
    # Multiselect com as páginas que FALTAM
    paginas_selecionadas_agora = st.multiselect(
        "Selecione as páginas finalizadas neste turno:",
        options=faltam,
        placeholder="Clique para selecionar as páginas..."
    )

b1, b2, b3 = st.columns(3)

if st.session_state.status == "PARADO":
    if not bloqueado:
        if b1.button("▶️ INICIAR", type="primary", use_container_width=True):
            if total_pg is not None and st.session_state.get('memoria_total') is None:
                # Salva o cadastro inicial (0 páginas feitas)
                salvar_progresso(site, letra, total_pg, [])
                st.session_state.memoria_total = total_pg
                
            if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
            if registrar_log(usuario, site, letra, "INICIO", total_pg, []):
                st.session_state.status = "TRABALHANDO"
                st.rerun()
    else:
        st.info("Selecione outra letra para trabalhar.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        # 1. Salva no Log
        if registrar_log(usuario, site, letra, "PAUSA", total_pg, paginas_selecionadas_agora):
            # 2. Atualiza o Banco de Controle (Checklist)
            if paginas_selecionadas_agora:
                salvar_progresso(site, letra, total_pg, paginas_selecionadas_agora)
                # Atualiza memória local para mostrar barra certa na volta
                st.session_state.memoria_feitas = st.session_state.memoria_feitas + paginas_selecionadas_agora
            
            st.session_state.status = "PAUSADO"
            st.rerun()
            
    if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "FIM", total_pg, paginas_selecionadas_agora):
            if paginas_selecionadas_agora:
                salvar_progresso(site, letra, total_pg, paginas_selecionadas_agora)
            
            st.session_state.status = "PARADO"
            if 'id_sessao' in st.session_state: del st.session_state['id_sessao']
            st.balloons()
            time.sleep(2)
            st.rerun()

elif st.session_state.status == "PAUSADO":
    st.warning("⏸ Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if registrar_log(usuario, site, letra, "RETOMADA", total_pg, []):
            st.session_state.status = "TRABALHANDO"
            st.rerun()
