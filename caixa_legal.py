import datetime
import hashlib
import io
import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(
    page_title="Caixa Legal", 
    page_icon="💰", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.cache_data.clear()

DB_CAIXA_FILE = "caixa_legal.db"

def hash_senha(senha):
    return hashlib.sha256(str.encode(senha)).hexdigest()

def get_connection():
    conn = sqlite3.connect(DB_CAIXA_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, senha TEXT NOT NULL, perfil TEXT NOT NULL, status TEXT DEFAULT 'Ativo')")
    c.execute("CREATE TABLE IF NOT EXISTS turnos_caixa (id INTEGER PRIMARY KEY AUTOINCREMENT, operador TEXT, data_abertura TEXT, valor_inicial REAL, valor_fechamento REAL, diferenca REAL, status TEXT DEFAULT 'Aberto', observacao TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS movimentacoes_caixa (id INTEGER PRIMARY KEY AUTOINCREMENT, turno_id INTEGER, tipo TEXT, forma_pagamento TEXT, valor REAL, descricao TEXT, data_hora TEXT, operador TEXT)")

    c.execute("SELECT * FROM usuarios WHERE username = 'caixa'")
    if not c.fetchone():
        c.execute("INSERT OR REPLACE INTO usuarios VALUES ('caixa', ?, 'Operador de Caixa', 'Ativo')", (hash_senha("1234"),))
    c.execute("SELECT * FROM usuarios WHERE username = 'gerente'")
    if not c.fetchone():
        c.execute("INSERT OR REPLACE INTO usuarios VALUES ('gerente', ?, 'Gerente / Admin', 'Ativo')", (hash_senha("admin123"),))

    conn.commit()
    conn.close()

init_db()

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario"] = None
    st.session_state["perfil"] = None

if "modo_login" not in st.session_state:
    st.session_state["modo_login"] = "login"

def tela_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.write("")
        st.write("")
        st.title("💰 Caixa Legal")
        st.caption("Controle de Caixa, Turnos e Movimentos Financeiros")
        
        with st.form("form_login_caixa"):
            usuario = st.text_input("Utilizador").strip()
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no Caixa", use_container_width=True)

            if btn_login:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT perfil, status, senha FROM usuarios WHERE username = ?", (usuario,))
                res = c.fetchone()
                conn.close()

                if res:
                    perfil, status, senha_bd = res
                    if senha_bd == hash_senha(senha):
                        if status == "Bloqueado":
                            st.error("⚠️ Este utilizador está bloqueado. Contacte o Administrador.")
                        else:
                            st.session_state["logado"] = True
                            st.session_state["usuario"] = usuario
                            st.session_state["perfil"] = perfil
                            st.rerun()
                    else:
                        st.error("Utilizador ou senha incorretos.")
                else:
                    st.error("Utilizador não encontrado.")

if not st.session_state["logado"]:
    tela_login()
    st.stop()

with st.sidebar:
    st.write("### 👤 " + str(st.session_state['usuario']))
    st.caption("Perfil: " + str(st.session_state['perfil']))
    st.divider()
    if st.button("🔄 Atualizar Sessão", use_container_width=True):
        st.rerun()
    if st.button("🚪 Encerrar Caixa / Sair", use_container_width=True):
        st.session_state["logado"] = False
        st.session_state["usuario"] = None
        st.session_state["perfil"] = None
        st.rerun()

st.title("💰 Caixa Legal — Gestão Financeira Inspirada no Saipos")
perfil_atual = st.session_state["perfil"]
usuario_atual = st.session_state["usuario"]

def get_turno_aberto(usuario):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, valor_inicial, data_abertura FROM turnos_caixa WHERE operador = ? AND status = 'Aberto'", (usuario,))
    res = c.fetchone()
    conn.close()
    return res

turno_ativo = get_turno_aberto(usuario_atual)

if perfil_atual == "Gerente / Admin":
    abas = st.tabs([
        "📊 Dashboard Interativo de Vendas", 
        "🔓 Abrir / Gerir Turnos", 
        "💸 Movimentos (Vendas/Sangrias)", 
        "👥 Gestão de Utilizadores", 
        "📈 Relatórios e Fechos"
    ])
    aba_dash, aba_turnos, aba_mov, aba_usr, aba_rel = abas
else:
    abas = st.tabs(["🔓 Abertura de Caixa", "💸 Lançamentos (Vendas / Sangria / Reforço)", "🔒 Fecho de Caixa & Relatório"])
    aba_abertura_op, aba_mov_op, aba_fecho_op = abas

if perfil_atual == "Gerente / Admin":
    with aba_dash:
        st.subheader("📊 Dashboard Interativo — Progresso e Desempenho de Vendas do Dia")
        
        conn = get_connection()
        df_mov = pd.read_sql_query("SELECT * FROM movimentacoes_caixa", conn)
        df_turnos = pd.read_sql_query("SELECT * FROM turnos_caixa", conn)
        conn.close()

        if not df_mov.empty:
            df_mov['data_hora'] = pd.to_datetime(df_mov['data_hora'])
            hoje = datetime.datetime.now().date()
            df_hoje = df_mov[df_mov['data_hora'].dt.date == hoje]
        else:
            df_hoje = pd.DataFrame()

        # Métricas Principais do Dia
        faturamento_hoje = df_hoje[df_hoje['tipo'] == 'Venda']['valor'].sum() if not df_hoje.empty else 0.0
        total_vendas_qtd = len(df_hoje[df_hoje['tipo'] == 'Venda']) if not df_hoje.empty else 0
        ticket_medio = faturamento_hoje / total_vendas_qtd if total_vendas_qtd > 0 else 0.0

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("💰 Faturamento Hoje", f"R$ {faturamento_hoje:.2f}")
        col_m2.metric("🧾 Nº de Vendas Hoje", total_vendas_qtd)
        col_m3.metric("📈 Ticket Médio", f"R$ {ticket_medio:.2f}")
        
        meta_dia = 1000.00  # Meta configurável de exemplo
        progresso_meta = min(faturamento_hoje / meta_dia, 1.0) if meta_dia > 0 else 0
        col_m4.metric("🎯 Progresso da Meta (R$ 1.000)", f"{progresso_meta * 100:.1f}%")
        st.progress(progresso_meta)

        st.divider()

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            if not df_hoje.empty and not df_hoje[df_hoje['tipo'] == 'Venda'].empty:
                fig_pag = px.pie(
                    df_hoje[df_hoje['tipo'] == 'Venda'], 
                    names='forma_pagamento', 
                    values='valor', 
                    title="Vendas de Hoje por Forma de Pagamento", 
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.RdBu
                )
                fig_pag.update_layout(margin=dict(t=30, b=10, l=10, r=10))
                st.plotly_chart(fig_pag, use_container_width=True)
            else:
                st.info("Sem registos de vendas para o dia de hoje.")

        with col_g2:
            if not df_hoje.empty and not df_hoje[df_hoje['tipo'] == 'Venda'].empty:
                df_temp = df_hoje[df_hoje['tipo'] == 'Venda'].copy()
                df_temp['hora'] = df_temp['data_hora'].dt.strftime('%H:00')
                df_hora = df_temp.groupby('hora')['valor'].sum().reset_index()
                
                fig_hora = px.bar(
                    df_hora, 
                    x='hora', 
                    y='valor', 
                    title="Evolução de Vendas por Hora (Hoje)",
                    labels={'hora': 'Hora do Dia', 'valor': 'Faturamento (R$)'},
                    text_auto='.2f'
                )
                fig_hora.update_layout(margin=dict(t=30, b=10, l=10, r=10))
                st.plotly_chart(fig_hora, use_container_width=True)
            else:
                st.info("Sem dados temporais suficientes para o gráfico por hora.")

    with aba_turnos:
        st.subheader("🔓 Gestão e Acompanhamento de Turnos de Caixa")
        conn = get_connection()
        df_t = pd.read_sql_query("SELECT * FROM turnos_caixa ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_t, use_container_width=True)

    with aba_mov:
        st.subheader("💸 Registo de Movimentos Financeiros (Estilo PDV Saipos)")
        if turno_ativo is None:
            st.warning("⚠️ Não tem nenhum turno aberto no momento. Abra um caixa para poder movimentar.")
        else:
            turno_id = turno_ativo[0]
            st.info(f"Turno Ativo ID: {turno_id:03d} | Aberto em: {turno_ativo[2]} | Fundo Inicial: R$ {turno_ativo[1]:.2f}")

            with st.form("form_mov_saipos", clear_on_submit=True):
                tipo_mov = st.selectbox("Tipo de Movimento", ["Venda", "Sangria (Retirada de Dinheiro)", "Reforço (Entrada de Troco/Dinheiro)", "Despesa / Pagamento à Vista"])
                
                forma_pag = "Dinheiro"
                if tipo_mov == "Venda":
                    forma_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Delivery / Online"])
                
                valor = st.number_input("Valor (R$)", min_value=0.01, value=10.0, step=1.0)
                descricao = st.text_input("Descrição / Observação (Ex: Venda Mesa 04, Pagamento Fornecedor)").strip()

                if st.form_submit_button("💾 Registar Movimento no Caixa", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO movimentacoes_caixa (turno_id, tipo, forma_pagamento, valor, descricao, data_hora, operador) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (turno_id, tipo_mov, forma_pag, valor, descricao, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), usuario_atual)
                    )
                    conn.commit()
                    conn.close()
                    st.success("✅ Movimento registado com sucesso!")
                    st.rerun()

    with aba_usr:
        st.subheader("👥 Gestão Completa de Utilizadores (Criar, Alterar Senha, Bloquear/Liberar)")
        
        tab_u1, tab_u2 = st.tabs(["➕ Criar Novo Utilizador", "⚙️ Gerir, Senhas e Estado (Bloquear/Liberar)"])
        
        with tab_u1:
            with st.form("form_novo_usuario", clear_on_submit=True):
                novo_user = st.text_input("Nome de Utilizador (Login)").strip()
                nova_senha = st.text_input("Senha Inicial", type="password")
                novo_perfil = st.selectbox("Perfil de Acesso", ["Operador de Caixa", "Gerente / Admin"])
                
                if st.form_submit_button("💾 Cadastrar Utilizador", type="primary"):
                    if novo_user and nova_senha:
                        try:
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute(
                                "INSERT INTO usuarios (username, senha, perfil, status) VALUES (?, ?, ?, 'Ativo')",
                                (novo_user, hash_senha(nova_senha), novo_perfil)
                            )
                            conn.commit()
                            conn.close()
                            st.success(f"✅ Utilizador '{novo_user}' criado com sucesso!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Erro: Este nome de utilizador já existe no sistema.")
                    else:
                        st.warning("Por favor, preencha o utilizador e a senha.")

        with tab_u2:
            conn = get_connection()
            df_usuarios = pd.read_sql_query("SELECT username, perfil, status FROM usuarios", conn)
            conn.close()

            if not df_usuarios.empty:
                st.dataframe(df_usuarios, use_container_width=True)
                
                st.divider()
                st.subheader("🛠️ Modificar Utilizador Selecionado")
                
                user_selecionado = st.selectbox("Escolha o Utilizador", df_usuarios['username'].tolist())
                
                # Obter status atual
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT status, perfil FROM usuarios WHERE username = ?", (user_selecionado,))
                st_atual, perf_atual_usr = c.fetchone()
                conn.close()

                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    nova_senha_edit = st.text_input("Nova Senha (deixar em branco para não alterar)", type="password")
                with col_e2:
                    novo_status_edit = st.selectbox("Estado da Conta", ["Ativo", "Bloqueado"], index=0 if st_atual == "Ativo" else 1)

                if st.button("💾 Atualizar Dados do Utilizador", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    if nova_senha_edit.strip():
                        c.execute("UPDATE usuarios SET senha = ?, status = ? WHERE username = ?", (hash_senha(nova_senha_edit), novo_status_edit, user_selecionado))
                    else:
                        c.execute("UPDATE usuarios SET status = ? WHERE username = ?", (novo_status_edit, user_selecionado))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Utilizador '{user_selecionado}' atualizado com sucesso!")
                    st.rerun()
            else:
                st.info("Nenhum utilizador registado.")

    with aba_rel:
        st.subheader("📈 Relatórios de Fecho e Auditoria de Caixa")
        conn = get_connection()
        df_r = pd.read_sql_query("SELECT m.id, m.turno_id as 'Turno', m.operador as 'Operador', m.tipo as 'Tipo', m.forma_pagamento as 'Forma Pag.', m.valor as 'Valor (R$)', m.descricao as 'Descrição', m.data_hora as 'Data/Hora' FROM movimentacoes_caixa m ORDER BY m.id DESC", conn)
        conn.close()
        st.dataframe(df_r, use_container_width=True)

else:
    # PERFIL OPERADOR DE CAIXA
    with aba_abertura_op:
        st.subheader("🔓 Abertura de Caixa (Início de Turno)")
        if turno_ativo is not None:
            st.success(f"✅ Caixa Aberto! Turno ID: {turno_ativo[0]:03d} | Fundo Inicial: R$ {turno_ativo[1]:.2f}")
            st.info("Utilize a aba ao lado para fazer lançamentos de vendas, sangrias ou reforços.")
        else:
            with st.form("form_abertura"):
                valor_fundo = st.number_input("Valor do Fundo de Troco Inicial (R$)", min_value=0.0, value=100.0, step=10.0)
                obs_abertura = st.text_input("Observações da Abertura").strip()

                if st.form_submit_button("🚀 Abrir Caixa Agora", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO turnos_caixa (operador, data_abertura, valor_inicial, status, observacao) VALUES (?, ?, ?, 'Aberto', ?)",
                        (usuario_atual, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), valor_fundo, obs_abertura)
                    )
                    conn.commit()
                    conn.close()
                    st.success("✅ Caixa aberto com sucesso!")
                    st.rerun()

    with aba_mov_op:
        st.subheader("💸 Lançamentos do Turno (Vendas, Sangrias e Reforços)")
        if turno_ativo is None:
            st.warning("⚠️ O seu caixa está fechado. Abra o caixa primeiro na aba anterior.")
        else:
            turno_id = turno_ativo[0]
            fundo_inicial = turno_ativo[1]
            
            conn = get_connection()
            df_m_turno = pd.read_sql_query("SELECT tipo, forma_pagamento, valor, descricao, data_hora FROM movimentacoes_caixa WHERE turno_id = ?", conn, params=(turno_id,))
            conn.close()

            vendas_dinheiro = df_m_turno[(df_m_turno['tipo'] == 'Venda') & (df_m_turno['forma_pagamento'] == 'Dinheiro')]['valor'].sum() if not df_m_turno.empty else 0.0
            total_sangria = df_m_turno[df_m_turno['tipo'] == 'Sangria']['valor'].sum() if not df_m_turno.empty else 0.0
            total_reforco = df_m_turno[df_m_turno['tipo'] == 'Reforço']['valor'].sum() if not df_m_turno.empty else 0.0
            
            caixa_teorico_dinheiro = fundo_inicial + vendas_dinheiro + total_reforco - total_sangria

            st.metric("Caixa Teórico em Dinheiro (Gaveta)", f"R$ {caixa_teorico_dinheiro:.2f}")

            with st.form("form_mov_operador", clear_on_submit=True):
                tipo_mov = st.selectbox("Tipo de Operação", ["Venda", "Sangria (Retirada de Dinheiro)", "Reforço (Adicionar Troco)"])
                
                forma_pag = "Dinheiro"
                if tipo_mov == "Venda":
                    forma_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Delivery / Online"])
                
                valor = st.number_input("Valor (R$)", min_value=0.01, value=20.0, step=1.0)
                descricao = st.text_input("Descrição / Identificação").strip()

                if st.form_submit_button("Confirmar Lançamento", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO movimentacoes_caixa (turno_id, tipo, forma_pagamento, valor, descricao, data_hora, operador) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (turno_id, tipo_mov, forma_pag, valor, descricao, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), usuario_atual)
                    )
                    conn.commit()
                    conn.close()
                    st.success("✅ Registo efetuado com sucesso!")
                    st.rerun()

            st.divider()
            st.subheader("📋 Extrato do Turno Atual")
            if not df_m_turno.empty:
                st.dataframe(df_m_turno, use_container_width=True)
            else:
                st.info("Nenhum movimento registado neste turno ainda.")

    with aba_fecho_op:
        st.subheader("🔒 Fechamento de Caixa (Conferência de Gaveta)")
        if turno_ativo is None:
            st.info("Nenhum caixa aberto neste momento.")
        else:
            turno_id = turno_ativo[0]
            fundo_inicial = turno_ativo[1]

            conn = get_connection()
            df_m_turno = pd.read_sql_query("SELECT tipo, forma_pagamento, valor FROM movimentacoes_caixa WHERE turno_id = ?", conn, params=(turno_id,))
            conn.close()

            vendas_dinheiro = df_m_turno[(df_m_turno['tipo'] == 'Venda') & (df_m_turno['forma_pagamento'] == 'Dinheiro')]['valor'].sum() if not df_m_turno.empty else 0.0
            total_sangria = df_m_turno[df_m_turno['tipo'] == 'Sangria']['valor'].sum() if not df_m_turno.empty else 0.0
            total_reforco = df_m_turno[df_m_turno['tipo'] == 'Reforço']['valor'].sum() if not df_m_turno.empty else 0.0
            
            valor_teorico_gaveta = fundo_inicial + vendas_dinheiro + total_reforco - total_sangria

            st.write(f"**Fundo Inicial:** R$ {fundo_inicial:.2f}")
            st.write(f"**Vendas em Dinheiro:** R$ {vendas_dinheiro:.2f}")
            st.write(f"**Reforços:** R$ {total_reforco:.2f}")
            st.write(f"**Sangrias (Retiradas):** R$ {total_sangria:.2f}")
            st.markdown(f"### **Total Teórico em Dinheiro na Gaveta: R$ {valor_teorico_gaveta:.2f}**")

            with st.form("form_fecho"):
                valor_informado = st.number_input("Contagem Física (Quanto tem realmente na gaveta em dinheiro?)", min_value=0.0, value=float(valor_teorico_gaveta), step=1.0)
                obs_fecho = st.text_input("Observações do Fechamento (Ex: Quebra de caixa de R$ 5,00)").strip()

                if st.form_submit_button("🔒 Fechar Caixa Definitivamente", type="primary"):
                    diferenca = valor_informado - valor_teorico_gaveta
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        "UPDATE turnos_caixa SET valor_fechamento = ?, diferenca = ?, status = 'Fechado', observacao = ? WHERE id = ?",
                        (valor_informado, diferenca, f"Fechado. {obs_fecho} (Dif: R$ {diferenca:.2f})", turno_id)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Caixa fechado com sucesso! Diferença apurada: R$ {diferenca:.2f}")
                    st.rerun()
