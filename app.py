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
    """Retorna: (Total Paginas, Lista Feitas, Qtd Produtos Ultima Pagina)"""
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
                
                # Tenta pegar a qtd da última página (Coluna F / index 5 se existir)
                # Se não tiver preenchido (letras antigas), assume 100 por padrão
                try:
                    qtd_ultima = int(res.iloc[0]['Qtd_Ultima_Pag'])
                except:
                    qtd_ultima = 100 
                
                return total, feitas, qtd_ultima
        return None, [], 100
    except: return None, [], 100

def salvar_progresso(site, letra, total_paginas, novas_paginas_feitas, qtd_ultima_pag=100):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        
        # Busca dados atuais para não perder histórico
        _, ja_feitas, _ = buscar_status_paginas(site, letra)
        
        lista_completa = sorted(list(set(ja_feitas + novas_paginas_feitas)))
        # Faxina: remove páginas maiores que o total
        lista_limpa = [p for p in lista_completa if p <= int(total_paginas)]
        texto_para_salvar = ", ".join(map(str, lista_limpa))
        
        chave_busca = f"{site} | {letra}".strip()
        cell = sheet.find(chave_busca)
        
        if cell:
            # Atualiza: Col 5 (Lista), Col 4 (Total)
            sheet.update_cell(cell.row, 5, texto_para_salvar)
            sheet.update_cell(cell.row, 4, total_paginas)
            # Se quiser atualizar a qtd da última página também (caso tenha mudado)
            sheet.update_cell(cell.row, 6, qtd_ultima_pag)
        else:
            # Cria nova linha: Chave, Site, Letra, Total, Lista, Qtd_Ultima
            sheet.append_row([chave_busca, site, letra, total_paginas, texto_para_salvar, qtd_ultima_pag])
    except: pass

def registrar_log(operador, site, letra, acao, total, novas, qtd_ultima_pag):
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
        
        # --- CÁLCULO PRECISO DE PRODUTOS ---
        qtd_produtos = 0
        if novas:
            for p in novas:
                # Se for a última página, soma o valor "quebrado"
                if p == int(total):
                    qtd_produtos += int(qtd_ultima_pag)
                else:
                    # Se for qualquer outra página, soma 100
                    qtd_produtos += 100
        
        # Salva na coluna K (Qtd_Total)
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
            total,
            qtd_produtos
        ]
        sheet.append_row(nova_linha)
        return True
    except: return False

def calcular_resumo_diario(usuario):
    """Calcula usando a soma direta das colunas do Log"""
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return "0h 0m", 0, 0
        
        df = df[df['Operador'] == usuario]
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "0h 0m", 0, 0
        
        # 1. Soma Tempo (PAUSA/FIM)
        df_produtivo = df[df['Acao'].isin(['PAUSA', 'FIM'])]
        seg = df_produtivo['Tempo_Decorrido'].sum() if 'Tempo_Decorrido' in df_produtivo.columns else 0
        h, m = int(seg // 3600), int((seg % 3600) // 60)
        tempo_str = f"{h}h {m}m"
        
        # 2. Soma Páginas
        paginas = 0
        if 'Paginas_Turno' in df.columns:
            for item in df['Paginas_Turno']:
                texto = str(item).strip()
                if texto and texto not in ["", "-"]:
                    lista = [x for x in texto.split(',') if x.strip()]
                    paginas += len(lista)
        
        # 3. Soma Produtos (Coluna K - Qtd_Total)
        total_produtos = 0
        if 'Qtd_Total' in df.columns:
            # Converte para numérico e soma
            total_produtos = pd.to_numeric(df['Qtd_Total'], errors='coerce').fillna(0).sum()
        
        return tempo_str, paginas, int(total_produtos)
    except Exception as e: 
        print(e)
        return "...", 0, 0

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
                    cookie_manager.set("usuario_associacao", user_input, expires_at=datetime.now() + pd.Timedelta(days=1))
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Dados incorretos.")
    st.stop()

if cookie_usuario:
    st.session_state['usuario_logado'] = cookie_usuario

usuario = st.session_state['usuario_logado'].title()

# --- 5. BARRA LATERAL ---
with st.sidebar:
    st.write(f"👤 **{usuario}**")
    
    if st.button("Sair / Logout"):
        with st.spinner("Desconectando..."):
            try: cookie_manager.delete("usuario_associacao"); cookie_manager.set("usuario_associacao", "", expires_at=datetime.now())
            except: pass
            for key in list(st.session_state.keys()): del st.session_state[key]
            time.sleep(3); st.rerun()

    st.divider()
    st.markdown("### 📊 Produção Hoje")
    
    if 'resumo_dia' not in st.session_state:
        with st.spinner("Calculando..."):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
    
    t, p, prod = st.session_state['resumo_dia']
    
    st.metric("⏱ Tempo", t)
    c_pag, c_prod = st.columns(2)
    c_pag.metric("📄 Pags", p)
    c_prod.metric("📦 Prods", prod)
    
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

chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    with st.spinner(f"Verificando histórico..."):
        # Agora retorna 3 valores (Total, Feitas, Qtd_Ultima)
        tot, feitas, qtd_ult = buscar_status_paginas(site, letra)
        st.session_state.mem_tot = tot
        st.session_state.mem_feit = feitas
        st.session_state.mem_ult = qtd_ult
        st.session_state['last_sel'] = chave

tot_pg = st.session_state.get('mem_tot')
feitas_pg = st.session_state.get('mem_feit', [])
qtd_ultima = st.session_state.get('mem_ult', 100) # Padrão 100 se não vier nada

faltam = []
bloq = False

if tot_pg:
    # Se já existe, mostra as infos
    faltam = [p for p in range(1, tot_pg+1) if p not in feitas_pg]
    prog = len(feitas_pg)/tot_pg if tot_pg > 0 else 0
    st.progress(prog, f"{len(feitas_pg)}/{tot_pg} ({int(prog*100)}%)")
    
    # Mostra a quantidade da última página apenas como info
    st.caption(f"ℹ️ Última página ({tot_pg}) tem **{qtd_ultima}** produtos.")
    
    if not faltam: st.success("Letra Concluída!"); bloq = True
else:
    # SE FOR NOVO CADASTRO
    st.warning("🆕 Letra Nova - Configuração Inicial")
    col_a, col_b = st.columns(2)
    with col_a:
        tot_pg = st.number_input("Total de Páginas:", 1, step=1)
    with col_b:
        # Pergunta a quantidade da última página
        qtd_ultima_input = st.number_input(f"Qtd Produtos na Pág {tot_pg} (Última):", min_value=1, max_value=100, value=100)
    
    # Atualiza a variável temporária para usar no salvamento
    qtd_ultima = qtd_ultima_input

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
                # Salva o cadastro inicial (Total + Qtd Ultima)
                if st.session_state.get('mem_tot') is None:
                    salvar_progresso(site, letra, tot_pg, [], qtd_ultima)
                    st.session_state.mem_tot = tot_pg
                    st.session_state.mem_ult = qtd_ultima
                
                if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
                
                if registrar_log(usuario, site, letra, "INICIO", tot_pg, [], qtd_ultima):
                    st.session_state.status = "TRABALHANDO"
                    st.rerun()
    else: st.info("Finalizado.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        with st.spinner("Salvando pausa..."):
            if registrar_log(usuario, site, letra, "PAUSA", tot_pg, sel_agora, qtd_ultima):
                if sel_agora:
                    salvar_progresso(site, letra, tot_pg, sel_agora, qtd_ultima)
                    st.session_state.mem_feit += sel_agora
                    st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
                st.session_state.status = "PAUSADO"
                st.rerun()
    
    comp = False
    if faltam and len(sel_agora) == len(faltam): comp = True
    
    if comp:
        if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            with st.spinner("Finalizando..."):
                if registrar_log(usuario, site, letra, "FIM", tot_pg, sel_agora, qtd_ultima):
                    salvar_progresso(site, letra, tot_pg, sel_agora, qtd_ultima)
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
            if registrar_log(usuario, site, letra, "RETOMADA", tot_pg, [], qtd_ultima):
                st.session_state.status = "TRABALHANDO"
                st.rerun()
