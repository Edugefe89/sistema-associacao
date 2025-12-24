import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import pytz
import extra_streamlit_components as stx # <--- ESTE IMPORT É OBRIGATÓRIO AQUI

# --- CÓDIGO DE EMERGÊNCIA
if "sair" in st.query_params:
    st.title("🛑 Reset de Emergência")
    
    # CORREÇÃO: Usamos stx.CookieManager() direto, em vez da função get_manager()
    try:
        cm_temp = stx.CookieManager()
        cm_temp.delete("usuario_associacao")
        cm_temp.delete("timer_inicio")
    except: pass
    
    # Limpa a sessão
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
    st.warning("Cookies limpos. Clique no botão abaixo para voltar.")
    
    # Este botão força a limpeza da URL e recarrega LIMPO
    if st.button("♻️ VOLTAR PARA O LOGIN (CLIQUE AQUI)"):
        st.query_params.clear()
        st.rerun()
        
    st.stop()
# ==============================================================================
# 1. FUNÇÕES DE CONEXÃO E CACHE
# ==============================================================================

@st.cache_resource
def get_client_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"⚠️ Erro de Conexão: {e}")
        return None

def get_manager():
    return stx.CookieManager()

def forcar_atualizacao_mapa():
    """Lê o banco de acompanhamento e salva na memória"""
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("acompanhamento_paginas")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        st.session_state['dados_mapa_cache'] = df
    except:
        st.session_state['dados_mapa_cache'] = pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_lista_sites_v2():
    try:
        client = get_client_google()
        if client is None: return [], {} 
        
        sheet = client.open("Sistema_Associacao").worksheet("cadastro_varreduras")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        lista_sites = []
        regras_exclusao = {}

        if not df.empty and 'Cliente' in df.columns:
            for index, row in df.iterrows():
                if row['Cliente'] != '':
                    nome_completo = f"{row['Cliente']} - {row['Concorrente']}"
                    lista_sites.append(nome_completo)
                    
                    letras_proibidas = []
                    if 'Delete_Letras' in df.columns:
                        texto_delete = str(row['Delete_Letras']).upper().strip()
                        if texto_delete:
                            letras_proibidas = [l.strip() for l in texto_delete.split(',') if l.strip()]
                    
                    regras_exclusao[nome_completo] = letras_proibidas

            return sorted(lista_sites), regras_exclusao
        return [], {}
    except Exception as e: 
        st.error(f"Erro ao carregar sites: {e}")
        return [], {}
        
def buscar_status_paginas(site, letra):
    try:
        client = get_client_google()
        if client is None: return None, [], 100

        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        chave = f"{site} | {letra}".strip()
        if not df.empty and 'Chave' in df.columns:
            res = df[df['Chave'].astype(str).str.strip() == chave]
            if not res.empty:
                total = int(res.iloc[0]['Qtd_Paginas'])
                feitas_str = str(res.iloc[0]['Paginas_Concluidas']).replace("'", "")
                feitas = [int(x) for x in feitas_str.split(',') if x.strip().isdigit()] if feitas_str else []
                try: qtd_ultima = int(res.iloc[0]['Qtd_Ultima_Pag'])
                except: qtd_ultima = 100
                return total, feitas, qtd_ultima
        return None, [], 100
    except Exception as e: 
        return None, [], 100

@st.cache_data(ttl=600) 
def carregar_dados_resumo_geral():
    try:
        client = get_client_google()
        if client is None: return None
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        return pd.DataFrame(sheet.get_all_records())
    except: return None

def exibir_resumo_geral(site_atual, regras_exclusao):
    df = carregar_dados_resumo_geral()
    if df is None or df.empty: return
    try:
        cadastradas = {}
        if 'Site' in df.columns:
            df_site = df[df['Site'] == site_atual]
            for _, row in df_site.iterrows():
                total = int(row['Qtd_Paginas'])
                feitas_str = str(row['Paginas_Concluidas']).replace("'", "").strip()
                if feitas_str and any(c.isdigit() for c in feitas_str):
                    qtd_feitas = len([x for x in feitas_str.split(',') if x.strip()])
                else: qtd_feitas = 0
                cadastradas[str(row['Letra']).strip()] = (total, qtd_feitas)

        bloqueadas = regras_exclusao.get(site_atual, [])
        dados_tabela = []
        for letra in list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            if letra in bloqueadas: status = "🚫 Inexistente"
            elif letra in cadastradas:
                total, feitas = cadastradas[letra]
                if feitas >= total: status = "✅ Concluída"
                else: status = f"📊 {feitas}/{total} Feitas"
            else: status = "🟡 A Cadastrar"
            dados_tabela.append({"Letra": letra, "Progresso": status})

        st.markdown("### 🔠 Visão Geral (A-Z)")
        st.dataframe(pd.DataFrame(dados_tabela), use_container_width=True, hide_index=True, height=300)
    except Exception as e: st.error(f"Erro visual: {e}")

# ==============================================================================
# 2. FUNÇÕES DE LOG E SALVAMENTO
# ==============================================================================

def salvar_progresso(site, letra, total_paginas, novas_paginas_feitas, usuario_nome, qtd_ultima_pag=100):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Controle_Paginas")
        _, ja_feitas, _ = buscar_status_paginas(site, letra)
        lista_completa = sorted(list(set(ja_feitas + novas_paginas_feitas)))
        lista_limpa = [p for p in lista_completa if p <= int(total_paginas)]
        texto_para_salvar = "'" + ", ".join(map(str, lista_limpa))
        chave_busca = f"{site} | {letra}".strip()
        cell = sheet.find(chave_busca)
        
        if cell:
            sheet.update_cell(cell.row, 5, texto_para_salvar)
            sheet.update_cell(cell.row, 4, total_paginas)
            sheet.update_cell(cell.row, 6, qtd_ultima_pag)
            sheet.update_cell(cell.row, 7, usuario_nome)
        else:
            sheet.append_row([chave_busca, site, letra, total_paginas, texto_para_salvar, qtd_ultima_pag, usuario_nome])
    except: pass

def registrar_log(operador, site, letra, acao, total, novas, qtd_ultima_pag):
    try:
        # 1. BLINDAGEM DE DADOS (Converte tudo para evitar erro de matemática)
        try:
            total_safe = int(float(str(total))) if total else 0
            qtd_ultima_safe = int(float(str(qtd_ultima_pag))) if qtd_ultima_pag else 100
        except:
            total_safe = 0
            qtd_ultima_safe = 100

        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        
        # 2. VERIFICAÇÃO DE DUPLICIDADE (Com proteção extra)
        try:
            todos_logs = sheet.get_all_records()
            df_log = pd.DataFrame(todos_logs)
            
            if not df_log.empty and 'Operador' in df_log.columns and 'Acao' in df_log.columns:
                # Filtra apenas logs desse usuário para evitar erro com dados de outros
                logs_usuario = df_log[df_log['Operador'].astype(str) == str(operador)]
                
                if not logs_usuario.empty:
                    ultima_acao = logs_usuario.iloc[-1]['Acao']
                    # Se a última ação for igual a atual, retorna True para não travar,
                    # MAS permite que o fluxo do botão continue
                    if str(acao) == str(ultima_acao) and acao != "PAUSA": 
                        return True 
        except Exception as e_pandas:
            print(f"Erro na verificação de duplicidade (ignorando): {e_pandas}")
            # Se der erro ao verificar duplicidade, segue o baile e registra o log igual.

        fuso = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso)
        
        tempo = 0
        
        # 3. CÁLCULO DE TEMPO
        if acao in ["INICIO", "RETOMADA"]:
            st.session_state['ultimo_timestamp'] = agora
            tempo = 0
            
        elif acao in ["PAUSA", "FIM"]:
            if 'ultimo_timestamp' in st.session_state and st.session_state['ultimo_timestamp']:
                try:
                    delta = agora - st.session_state['ultimo_timestamp']
                    tempo = int(delta.total_seconds())
                except: tempo = 0
            else:
                tempo = 0

        if 'id_sessao' not in st.session_state: st.session_state.id_sessao = str(uuid.uuid4())
        
        # Formata lista de novas páginas
        str_novas = ", ".join(map(str, novas)) if novas else "-"
        
        # Cálculo de produtos seguro
        qtd_produtos = 0
        if novas:
            for p in novas:
                try:
                    p_int = int(float(str(p)))
                    if p_int == total_safe: qtd_produtos += qtd_ultima_safe
                    else: qtd_produtos += 100
                except: pass
        
        nova_linha = [
            st.session_state.id_sessao, str(operador), str(site), str(letra), str(acao), 
            agora.strftime("%d/%m/%Y %H:%M:%S"), str(agora.timestamp()), 
            tempo, str_novas, total_safe, qtd_produtos
        ]
        
        sheet.append_row(nova_linha)
        return True

    except Exception as e: 
        # AGORA VAI APARECER O ERRO NA TELA DA CAMILLY
        st.error(f"⚠️ Erro Crítico no Log: {e}")
        # Mesmo com erro, retornamos True para ela conseguir trabalhar
        return True

def calcular_resumo_diario(usuario):
    try:
        client = get_client_google()
        sheet = client.open("Sistema_Associacao").worksheet("Logs")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return "0h 0m", 0, 0
        
        df = df[df['Operador'] == usuario]
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        df = df[df['Data_Hora'].astype(str).str.startswith(hoje)]
        
        if df.empty: return "0h 0m", 0, 0
        
        seg = 0
        if 'Tempo_Decorrido' in df.columns:
            coluna_limpa = df['Tempo_Decorrido'].astype(str).str.replace(',', '.')
            coluna_numerica = pd.to_numeric(coluna_limpa, errors='coerce').fillna(0)
            mask_produtivo = df['Acao'].isin(['PAUSA', 'FIM'])
            seg = coluna_numerica[mask_produtivo].sum()
            
        h, m = int(seg // 3600), int((seg % 3600) // 60)
        tempo_str = f"{h}h {m}m"
        
        paginas = 0
        if 'Paginas_Turno' in df.columns:
            for item in df['Paginas_Turno']:
                texto = str(item).strip()
                if texto and any(c.isdigit() for c in texto):
                    texto = texto.replace("'", "")
                    lista = [x for x in texto.split(',') if x.strip()]
                    paginas += len(lista)
        
        total_prod = 0
        if 'Qtd_Total' in df.columns:
            col_prod_limpa = df['Qtd_Total'].astype(str).str.replace('.', '', regex=False)
            total_prod = pd.to_numeric(col_prod_limpa, errors='coerce').fillna(0).sum()
            
        return tempo_str, paginas, int(total_prod)
    except Exception as e: 
        return "...", 0, 0

# ==============================================================================
# 3. LÓGICA DE LOGIN
# ==============================================================================

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
                    cookie_manager.set("usuario_associacao", user_input, expires_at=datetime.now() + timedelta(days=1))
                    time.sleep(1)
                    st.rerun()
                else: st.error("Dados incorretos.")
    st.stop()

if cookie_usuario:
    st.session_state['usuario_logado'] = cookie_usuario

usuario = st.session_state['usuario_logado'].title()

# Recuperação de Sessão (Timer)
if 'status' not in st.session_state:
    cookie_timer = cookie_manager.get(cookie="timer_inicio")
    
    if cookie_timer:
        try:
            fuso = pytz.timezone('America/Sao_Paulo')
            timestamp_recuperado = datetime.fromisoformat(cookie_timer)
            agora = datetime.now(fuso)
            horas_passadas = (agora - timestamp_recuperado).total_seconds() / 3600
            
            if horas_passadas < 12:
                st.session_state['status'] = "TRABALHANDO"
                st.session_state['ultimo_timestamp'] = timestamp_recuperado
                st.toast(f"🔄 Sessão recuperada! Iniciada às {timestamp_recuperado.strftime('%H:%M')}")
            else:
                cookie_manager.delete("timer_inicio")
                st.session_state['status'] = "PARADO"
        except:
            st.session_state['status'] = "PARADO"
    else:
        st.session_state['status'] = "PARADO"

# ==============================================================================
# 4. SIDEBAR - MÉTRICAS E MENU
# ==============================================================================
with st.sidebar:
    st.write(f"👤 **{usuario}**")
    if st.button("Sair / Logout"):
        with st.spinner("Desconectando..."):
            try: 
                cookie_manager.delete("usuario_associacao")
                cookie_manager.delete("timer_inicio") 
                cookie_manager.set("usuario_associacao", "", expires_at=datetime.now())
            except: pass
            for k in list(st.session_state.keys()): del st.session_state[k]
            time.sleep(2); st.rerun()

    st.divider()
    st.markdown("### 📊 Produção Hoje")
    if 'resumo_dia' not in st.session_state:
        with st.spinner("Calculando..."):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
    
    t, p, prod = st.session_state['resumo_dia']
    c_pag, c_prod = st.columns(2)
    c_pag.metric("📄 Páginas", p)
    c_prod.metric("📦 Produtos", prod)
    
    if st.button("Atualizar Métricas"):
        with st.spinner("Recalculando..."):
            st.session_state['resumo_dia'] = calcular_resumo_diario(usuario)
            st.rerun()
    st.divider()
    if st.button("🔄 Atualizar Lista Sites"):
        with st.spinner("Baixando sites..."):
            carregar_lista_sites_v2.clear()
            st.rerun()

# ==============================================================================
# 5. SISTEMA PRINCIPAL - HEADER
# ==============================================================================
st.title("🔗 Controle de Progresso")

with st.spinner("Carregando sistema..."):
    SITES_DO_BANCO, REGRAS_EXCLUSAO = carregar_lista_sites_v2()
    SITES = ["Selecione..."] + SITES_DO_BANCO
    LETRAS_PADRAO = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# --- CORREÇÃO DO BLOQUEIO DE SITE ---
# Verifica qual site está selecionado na memória do Streamlit
valor_site_atual = st.session_state.get("Site / Projeto", "Selecione...")

# Regra de Ouro: Só bloqueia SE o status for Trabalhando E o site NÃO for "Selecione..."
if st.session_state.get('status') == "TRABALHANDO" and valor_site_atual != "Selecione...":
    disabled_sel = True
else:
    # Se cair aqui, libera o botão!
    disabled_sel = False
    # E se o sistema achava que estava trabalhando, forçamos para PARADO para corrigir o bug
    if st.session_state.get('status') == "TRABALHANDO":
        st.session_state['status'] = "PARADO"

# ------------------------------------

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site / Projeto", SITES, disabled=disabled_sel)

if site == "Selecione...":
    st.info("⬅️ Selecione um Cliente/Concorrente acima para liberar o sistema.")
    st.stop()

letras_proibidas = REGRAS_EXCLUSAO.get(site, [])
letras_finais = [l for l in LETRAS_PADRAO if l not in letras_proibidas]

with c2: letra = st.selectbox("Letra", letras_finais, disabled=disabled_sel)

chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave and not disabled_sel:
    with st.spinner("Carregando histórico e mapa..."):
        tot, feitas, qtd_ult = buscar_status_paginas(site, letra)
        st.session_state.mem_tot = tot
        st.session_state.mem_feit = feitas
        st.session_state.mem_ult = qtd_ult
        forcar_atualizacao_mapa()
        st.session_state['last_sel'] = chave
        # Reseta seleção do mapa ao trocar de letra
        st.session_state['selecao_mapa_cache'] = []

tot_pg = st.session_state.get('mem_tot')
feitas_pg = st.session_state.get('mem_feit', [])
qtd_ultima = st.session_state.get('mem_ult', 100)

faltam = []
bloq_total = False

if tot_pg:
    todas = list(range(1, tot_pg+1))
    faltam = [p for p in todas if p not in feitas_pg]
    prog = len(feitas_pg)/tot_pg if tot_pg > 0 else 0
    st.progress(prog, f"{len(feitas_pg)}/{tot_pg} ({int(prog*100)}%)")
    st.caption(f"ℹ️ Última página tem **{qtd_ultima}** produtos.")
    if not faltam: st.success("Letra Concluída!"); bloq_total = True
else:
    st.warning("🆕 Configuração Inicial")
    col_a, col_b = st.columns(2)
    with col_a: tot_pg = st.number_input("Total Páginas:", 1, step=1)
    with col_b: qtd_ultima_input = st.number_input(f"Produtos na Pág {tot_pg}:", 1, 100, 100)
    qtd_ultima = qtd_ultima_input

st.divider()

# ==============================================================================
# 6. SIDEBAR - MAPA INTERATIVO (MOVIDO PARA CIMA PARA FUNCIONAR LOGICA)
# ==============================================================================
# A lógica do mapa precisa rodar ANTES do formulário para o 'selecao_mapa_cache' estar atualizado
if tot_pg is not None:
    with st.sidebar:
        st.divider()
        c_mapa_titulo, c_mapa_refresh = st.columns([4,1])
        c_mapa_titulo.markdown(f"### 🗺️ Mapa {letra}")
        if c_mapa_refresh.button("🔄", help="Atualizar mapa da equipe"):
            forcar_atualizacao_mapa()
            st.rerun()

        if 'dados_mapa_cache' not in st.session_state: forcar_atualizacao_mapa()
        df_bd = st.session_state['dados_mapa_cache']
        chave_atual = f"{site} | {letra}"
        
        paginas_em_andamento_bd = set()
        if not df_bd.empty and 'chave' in df_bd.columns and 'pagina' in df_bd.columns:
            filtro = df_bd[(df_bd["chave"] == chave_atual) & (df_bd["status"] == "Em andamento")]
            paginas_em_andamento_bd = set(filtro["pagina"].astype(int).tolist())

        set_feitas = set(feitas_pg)
        dados_mapa = []
        for i in range(1, tot_pg + 1):
            if i in set_feitas: dados_mapa.append({"Pág": i, "Status": "✅", "Selecionar": True, "bloqueado": True})
            elif i in paginas_em_andamento_bd: dados_mapa.append({"Pág": i, "Status": "🟡", "Selecionar": True, "bloqueado": False})
            else: dados_mapa.append({"Pág": i, "Status": "", "Selecionar": False, "bloqueado": False})

        df_mapa = pd.DataFrame(dados_mapa)
        
        # O Editor agora é apenas leitura/input visual
        df_editado = st.data_editor(
            df_mapa,
            column_config={
                "Pág": st.column_config.NumberColumn("Página", disabled=True, format="%d", width="small"),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small"),
                "Selecionar": st.column_config.CheckboxColumn("Trabalhar", default=False, width="small"),
                "bloqueado": None
            },
            disabled=["Pág", "Status", "bloqueado"],
            hide_index=True, use_container_width=True, height=300, key=f"editor_event_{letra}"
        )

        # Lógica de salvar no banco e atualizar sessão
        selecao_final = set(df_editado[(df_editado["Selecionar"] == True) & (df_editado["bloqueado"] == False)]["Pág"].tolist())

        # Se houver mudança visual, processa no banco
        if selecao_final != paginas_em_andamento_bd:
            try:
                client = get_client_google()
                sheet_acompanhamento = client.open("Sistema_Associacao").worksheet("acompanhamento_paginas")
                
                # 1. Adicionar Novas (Batch)
                novas = selecao_final - paginas_em_andamento_bd
                rows_to_add = []
                for p in novas: 
                    rows_to_add.append([chave_atual, letra, int(p), "Em andamento"])
                
                if rows_to_add:
                    sheet_acompanhamento.append_rows(rows_to_add)

                # 2. Remover Antigas (Cuidado com Rate Limit)
                removidas = paginas_em_andamento_bd - selecao_final
                if removidas:
                    dados_atuais = sheet_acompanhamento.get_all_records()
                    linhas_para_deletar = []
                    for idx, row in enumerate(dados_atuais):
                        if row['chave'] == chave_atual and int(row['pagina']) in removidas:
                            linhas_para_deletar.append(idx + 2)
                    
                    # CORREÇÃO CRÍTICA: Deleta de trás para frente e com pausa
                    for l in sorted(linhas_para_deletar, reverse=True):
                        try:
                            sheet_acompanhamento.delete_row(l)
                            time.sleep(0.8) # Pausa para evitar API Error
                        except: pass

                forcar_atualizacao_mapa()
                st.session_state['selecao_mapa_cache'] = list(selecao_final) # Salva para o formulário usar
                st.rerun()
            except Exception as e: st.error(f"Erro ao salvar seleção: {e}")
        else:
             # Se não mudou, apenas garante que a sessão tenha o valor atual
             st.session_state['selecao_mapa_cache'] = list(paginas_em_andamento_bd)

        st.sidebar.divider()
        exibir_resumo_geral(site, REGRAS_EXCLUSAO)

# ==============================================================================
# 7. FORMULÁRIO DE TRABALHO (VERSÃO ANTI-TRAVAMENTO)
# ==============================================================================

if st.session_state.status == "PARADO":
    if not bloq_total:
        c_btn = st.columns(3)
        # Garante que feitas_pg seja uma lista para evitar erro visual
        feitas_safe = feitas_pg if isinstance(feitas_pg, list) else []
        txt_btn = "▶️ RETOMAR" if feitas_safe else "▶️ INICIAR"
        
        # --- BOTÃO RETOMAR/INICIAR ---
        if c_btn[0].button(txt_btn, type="primary", use_container_width=True):
            erro_identificado = None
            try:
                with st.spinner("Sincronizando com o banco..."):
                    # 1. IGNORA A MEMÓRIA E BUSCA DADOS FRESCOS
                    # Isso resolve o bug de "clicar e nada acontecer" se a memória estiver vazia
                    t_fresh, f_fresh, q_fresh = buscar_status_paginas(site, letra)
                    
                    # Se o banco retornou vazio (None), usa valores padrão para não quebrar
                    val_tot = t_fresh if t_fresh else 1
                    val_ult = q_fresh if q_fresh else 100
                    
                    # Atualiza a memória da sessão AGORA
                    st.session_state.mem_tot = val_tot
                    st.session_state.mem_feit = f_fresh
                    st.session_state.mem_ult = val_ult
                    
                    # 2. LOGICA DE INÍCIO (SE NECESSÁRIO)
                    # Se for a primeira vez (lista de feitas vazia), registra no controle
                    if not f_fresh: 
                        salvar_progresso(site, letra, val_tot, [], usuario, val_ult)
                    
                    # 3. REGISTRO DE LOG
                    acao_log = "RETOMADA" if f_fresh else "INICIO"
                    
                    # Tenta registrar o log
                    log_ok = registrar_log(usuario, site, letra, acao_log, val_tot, [], val_ult)
                    
                    if log_ok:
                        # 4. ATUALIZA COOKIE E ESTADO
                        fuso = pytz.timezone('America/Sao_Paulo')
                        agora_iso = datetime.now(fuso).isoformat()
                        
                        # Define o cookie novamente para garantir
                        cookie_manager.set("timer_inicio", agora_iso, expires_at=datetime.now() + timedelta(days=1))
                        
                        forcar_atualizacao_mapa()
                        st.session_state.status = "TRABALHANDO"
                        st.rerun()
                    else:
                        erro_identificado = "Falha ao gravar no Log. Tente novamente."

            except Exception as e:
                erro_identificado = f"Erro técnico: {e}"

            # Se algo deu errado, mostramos o erro VISÍVEL
            if erro_identificado:
                st.error(f"⚠️ {erro_identificado}")
                st.warning("Dica: Tente atualizar a página (F5) e selecionar a letra novamente.")

    else: st.info("Selecione outra letra.")

elif st.session_state.status == "TRABALHANDO":
    
    # Proteção: Se a memória estiver vazia mesmo no status trabalhando, recarrega
    if st.session_state.get('mem_tot') is None:
         with st.spinner("Recuperando dados..."):
             tot, feitas, qtd_ult = buscar_status_paginas(site, letra)
             st.session_state.mem_tot = tot
             st.session_state.mem_feit = feitas
             st.session_state.mem_ult = qtd_ult
             st.rerun()

    with st.form(key="form_trabalho", clear_on_submit=False):
        st.markdown("### 📝 Marque o que você concluiu:")
        
        # Garante inteiros
        try: total_loop = int(st.session_state.mem_tot)
        except: total_loop = 1
            
        todas_reload = list(range(1, total_loop+1))
        
        lista_feitas = st.session_state.mem_feit if isinstance(st.session_state.mem_feit, list) else []
        faltam_reload = [p for p in todas_reload if p not in lista_feitas]
        
        default_mapa = st.session_state.get('selecao_mapa_cache', [])
        default_valido = [x for x in default_mapa if x in faltam_reload]

        sel_agora = st.multiselect("Selecione as páginas:", options=faltam_reload, default=default_valido)
        st.write("") 
        
        c_form1, c_form2 = st.columns(2)
        submit_pause = c_form1.form_submit_button("⏸ PAUSAR (Sair)", use_container_width=True)
        submit_finish = c_form2.form_submit_button("✅ FINALIZAR", type="primary", use_container_width=True)
        
        # Pega valores seguros da sessão
        tot_safe = st.session_state.mem_tot
        ult_safe = st.session_state.mem_ult

        if submit_pause:
            with st.spinner("Salvando..."): 
                registrar_log(usuario, site, letra, "PAUSA", tot_safe, sel_agora, ult_safe)
                
                if sel_agora:
                    salvar_progresso(site, letra, tot_safe, sel_agora, usuario, ult_safe)
                    if isinstance(st.session_state.mem_feit, list):
                        st.session_state.mem_feit += sel_agora
                
                cookie_manager.delete("timer_inicio")
                time.sleep(1) 
                st.session_state['resumo_dia'] = calcular_resumo_diario(usuario) 
                st.session_state.status = "PARADO"
                st.rerun()
        
        if submit_finish:
            if faltam_reload and len(sel_agora) == len(faltam_reload):
                with st.spinner("Finalizando..."):
                    registrar_log(usuario, site, letra, "FIM", tot_safe, sel_agora, ult_safe)
                    salvar_progresso(site, letra, tot_safe, sel_agora, usuario, ult_safe)
                    
                    cookie_manager.delete("timer_inicio")
                    
                    time.sleep(1) 
                    st.session_state['resumo_dia'] = calcular_resumo_diario(usuario) 
                    
                    st.session_state.status = "PARADO"
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning(f"⚠️ Você precisa marcar todas as páginas restantes para finalizar.")
