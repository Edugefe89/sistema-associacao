import streamlit as st
import time
import utils # Importa as funções

st.set_page_config(page_title="Controle", page_icon="🔗")

# Segurança: Se tentar entrar direto pelo link sem logar, chuta de volta
if 'usuario_logado' not in st.session_state:
    st.switch_page("app.py")

# Carrega a barra lateral padrão (com logout e métricas)
utils.sidebar_padrao()

st.title("🔗 Painel de Execução")
usuario = st.session_state['usuario_logado']

# --- INTERFACE ---
SITES = utils.carregar_lista_sites()
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

c1, c2 = st.columns(2)
with c1: site = st.selectbox("Site", SITES)
with c2: letra = st.selectbox("Letra", LETRAS)

# Memória de Páginas
chave = f"{site}_{letra}"
if st.session_state.get('last_sel') != chave:
    tot, feitas = utils.buscar_status_paginas(site, letra)
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
    if not faltam: st.success("Concluído!"); bloq = True
else:
    st.warning("Novo")
    tot_pg = st.number_input("Total Páginas", 1, step=1)

st.divider()
if 'status' not in st.session_state: st.session_state.status = "PARADO"

sel_agora = []
if st.session_state.status == "TRABALHANDO" and tot_pg and faltam:
    st.markdown("### Feito agora:")
    sel_agora = st.multiselect("Páginas:", options=faltam)

b1, b2, b3 = st.columns(3)

if st.session_state.status == "PARADO":
    if not bloq:
        if b1.button("▶️ INICIAR", type="primary", use_container_width=True):
            if tot_pg and st.session_state.get('mem_tot') is None:
                utils.salvar_progresso(site, letra, tot_pg, [])
                st.session_state.mem_tot = tot_pg
            if 'ultimo_timestamp' in st.session_state: del st.session_state['ultimo_timestamp']
            if utils.registrar_log(usuario, site, letra, "INICIO", tot_pg, []):
                st.session_state.status = "TRABALHANDO"; st.rerun()
    else: st.info("Finalizado.")

elif st.session_state.status == "TRABALHANDO":
    if b2.button("⏸ PAUSAR", use_container_width=True):
        if utils.registrar_log(usuario, site, letra, "PAUSA", tot_pg, sel_agora):
            if sel_agora:
                utils.salvar_progresso(site, letra, tot_pg, sel_agora)
                st.session_state.mem_feit += sel_agora
                st.session_state['resumo_dia'] = utils.calcular_resumo_diario(usuario)
            st.session_state.status = "PAUSADO"; st.rerun()
    
    comp = False
    if faltam and len(sel_agora) == len(faltam): comp = True
    
    if comp:
        if b3.button("✅ FINALIZAR", type="primary", use_container_width=True):
            if utils.registrar_log(usuario, site, letra, "FIM", tot_pg, sel_agora):
                utils.salvar_progresso(site, letra, tot_pg, sel_agora)
                st.session_state.mem_feit += sel_agora
                st.session_state.status = "PARADO"
                st.balloons(); time.sleep(1); st.rerun()

elif st.session_state.status == "PAUSADO":
    st.warning("Pausado")
    if b1.button("▶️ RETOMAR", type="primary", use_container_width=True):
        if utils.registrar_log(usuario, site, letra, "RETOMADA", tot_pg, []):
            st.session_state.status = "TRABALHANDO"; st.rerun()
