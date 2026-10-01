import datetime
import hashlib
import io
import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(
    page_title="Caixa Legal", 
    page_icon="💰", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

st.cache_data.clear()

DB_CAIXA_FILE = "caixa_legal.db"
CHAVE_PIX = "929813904244"

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
    c.execute("SELECT * FROM usuarios WHERE username = 'gestor'")
    if not c.fetchone():
        c.execute("INSERT OR REPLACE INTO usuarios VALUES ('gestor', ?, 'Gestor de Acompanhamento', 'Ativo')", (hash_senha("gestor123"),))

    conn.commit()
    conn.close()

init_db()

def gerar_qrcode_pix(chave, valor):
    img = qrcode.make(f"PIXKEY:{chave} - Valor: R$ {valor:.2f}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def gerar_pdf_relatorio_caixa(df_dados, titulo_relatorio, total_geral, somas_formas):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#0f172a'))
    story.append(Paragraph("Relatório Financeiro - " + str(titulo_relatorio), title_style))
    story.append(Paragraph("Emitido em: " + datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), styles['Normal']))
    story.append(Spacer(1, 10))

    # Totais por forma de pagamento no PDF
    resumo_texto = f"**Total Geral:** R$ {total_geral:.2f} | **Dinheiro:** R$ {somas_formas.get('Dinheiro', 0):.2f} | **Pix:** R$ {somas_formas.get('Pix', 0):.2f} | **Crédito:** R$ {somas_formas.get('Cartão de Crédito', 0):.2f} | **Débito:** R$ {somas_formas.get('Cartão de Débito', 0):.2f}"
    story.append(Paragraph(resumo_texto, styles['Normal']))
    story.append(Spacer(1, 10))

    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, leading=10)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.whitesmoke, fontName='Helvetica-Bold')

    colunas = df_dados.columns.tolist()
    headers = [Paragraph(str(c), header_style) for c in colunas]
    data_matrix = [headers]

    for _, r in df_dados.iterrows():
        row_cells = []
        for col in colunas:
            val = str(r[col]) if pd.notna(r[col]) else ""
            row_cells.append(Paragraph(val, cell_style))
        data_matrix.append(row_cells)

    num_cols = len(colunas)
    largura_util = 555
    col_widths = [largura_util / num_cols] * num_cols

    tabela = Table(data_matrix, colWidths=col_widths)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario"] = None
    st.session_state["perfil"] = None

def tela_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.write("")
        st.write("")
        st.title("💰 Caixa Legal")
        st.caption("Controle de Caixa Rápido e Intuitivo")
        
        with st.form("form_login_caixa"):
            usuario = st.text_input("Utilizador").strip()
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no Sistema", use_container_width=True)

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
                            st.error("⚠️ Este utilizador está bloqueado.")
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

col_top1, col_top2, col_top3 = st.columns([3, 1, 1])
col_top1.title("💰 Caixa Legal — Ecrã de Operação")
col_top2.markdown(f"👤 **{st.session_state['usuario']}**\n_{st.session_state['perfil']}_")
if col_top3.button("🚪 Sair", use_container_width=True):
    st.session_state["logado"] = False
    st.session_state["usuario"] = None
    st.session_state["perfil"] = None
    st.rerun()

st.divider()

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

# ==========================================
# PAINEL DO ADMINISTRADOR / GESTOR
# ==========================================
if perfil_atual in ["Gerente / Admin", "Gestor de Acompanhamento"]:
    st.subheader("📊 Painel de Controlo e Acompanhamento Geral")
    
    conn = get_connection()
    df_mov = pd.read_sql_query("SELECT * FROM movimentacoes_caixa", conn)
    conn.close()

    # Calcular somas detalhadas por forma de pagamento (Apenas Vendas)
    df_vendas = df_mov[df_mov['tipo'] == 'Venda'] if not df_mov.empty else pd.DataFrame()
    total_geral = df_vendas['valor'].sum() if not df_vendas.empty else 0.0
    
    soma_dinheiro = df_vendas[df_vendas['forma_pagamento'] == 'Dinheiro']['valor'].sum() if not df_vendas.empty else 0.0
    soma_pix = df_vendas[df_vendas['forma_pagamento'] == 'Pix']['valor'].sum() if not df_vendas.empty else 0.0
    soma_credito = df_vendas[df_vendas['forma_pagamento'] == 'Cartão de Crédito']['valor'].sum() if not df_vendas.empty else 0.0
    soma_debito = df_vendas[df_vendas['forma_pagamento'] == 'Cartão de Débito']['valor'].sum() if not df_vendas.empty else 0.0

    somas_dict = {
        'Dinheiro': soma_dinheiro,
        'Pix': soma_pix,
        'Cartão de Crédito': soma_credito,
        'Cartão de Débito': soma_debito
    }

    # Métricas Visuais de Totais
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💰 Total Geral", f"R$ {total_geral:.2f}")
    c2.metric("💵 Dinheiro", f"R$ {soma_dinheiro:.2f}")
    c3.metric("📲 Pix", f"R$ {soma_pix:.2f}")
    c4.metric("💳 Crédito", f"R$ {soma_credito:.2f}")
    c5.metric("💳 Débito", f"R$ {soma_debito:.2f}")

    st.divider()
    st.markdown("### 📋 Extrato Geral e Relatório PDF com Totais")
    
    col_adm1, col_adm2 = st.columns(2)
    with col_adm1:
        st.write("#### 📈 Últimas Movimentações")
        conn = get_connection()
        df_all = pd.read_sql_query("SELECT * FROM movimentacoes_caixa ORDER BY id DESC LIMIT 10", conn)
        conn.close()
        st.dataframe(df_all, use_container_width=True)

    with col_adm2:
        st.write("#### 📄 Exportar Relatório com Totais em PDF")
        conn = get_connection()
        df_pdf_data = pd.read_sql_query("SELECT m.turno_id as 'Turno', m.operador as 'Operador', m.tipo as 'Tipo', m.forma_pagamento as 'Forma Pag.', m.valor as 'Valor (R$)', m.data_hora as 'Data/Hora' FROM movimentacoes_caixa m ORDER BY m.id DESC", conn)
        conn.close()
        
        if not df_pdf_data.empty:
            pdf_bytes = gerar_pdf_relatorio_caixa(df_pdf_data, "Extrato Geral Consolidado", total_geral, somas_dict)
            st.download_button("📥 Descarregar Relatório PDF", data=pdf_bytes, file_name="relatorio_caixa_totalizado.pdf", mime="application/pdf", use_container_width=True)

    if perfil_atual == "Gerente / Admin":
        st.divider()
        st.markdown("### 👥 Gestão de Utilizadores (Bloquear / Criar)")
        with st.form("form_adm_user"):
            c_u1, c_u2, c_u3 = st.columns(3)
            novo_u = c_u1.text_input("Novo Utilizador").strip()
            nova_s = c_u2.text_input("Senha", type="password")
            novo_p = c_u3.selectbox("Perfil", ["Operador de Caixa", "Gestor de Acompanhamento", "Gerente / Admin"])
            if st.form_submit_button("Criar Utilizador", use_container_width=True):
                if novo_u and nova_s:
                    try:
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, 'Ativo')", (novo_u, hash_senha(nova_s), novo_p))
                        conn.commit()
                        conn.close()
                        st.success("Utilizador criado com sucesso!")
                        st.rerun()
                    except:
                        st.error("Utilizador já existe.")

# ==========================================
# PAINEL DO OPERADOR DE CAIXA (Ecrã Único PDV)
# ==========================================
else:
    if turno_ativo is None:
        st.warning("⚠️ O seu caixa está **FECHADO**. Insira o fundo inicial de troco para abrir o caixa.")
        with st.form("form_abrir_caixa_simples"):
            fundo_inicial = st.number_input("Valor do Fundo de Troco Inicial (R$)", min_value=0.0, value=100.0, step=10.0)
            if st.form_submit_button("🚀 Abrir Caixa Agora", type="primary", use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO turnos_caixa (operador, data_abertura, valor_inicial, status) VALUES (?, ?, ?, 'Aberto')",
                    (usuario_atual, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fundo_inicial)
                )
                conn.commit()
                conn.close()
                st.success("Caixa aberto com sucesso!")
                st.rerun()
    else:
        turno_id = turno_ativo[0]
        fundo_inicial = turno_ativo[1]
        
        conn = get_connection()
        df_m_turno = pd.read_sql_query("SELECT id, tipo, forma_pagamento, valor, descricao, data_hora FROM movimentacoes_caixa WHERE turno_id = ?", conn, params=(turno_id,))
        conn.close()

        vendas_dinheiro = df_m_turno[(df_m_turno['tipo'] == 'Venda') & (df_m_turno['forma_pagamento'] == 'Dinheiro')]['valor'].sum() if not df_m_turno.empty else 0.0
        total_sangria = df_m_turno[df_m_turno['tipo'] == 'Sangria']['valor'].sum() if not df_m_turno.empty else 0.0
        total_reforco = df_m_turno[df_m_turno['tipo'] == 'Reforço']['valor'].sum() if not df_m_turno.empty else 0.0
        caixa_gaveta = fundo_inicial + vendas_dinheiro + total_reforco - total_sangria

        st.info(f"🟢 **CAIXA ABERTO** (Turno #{turno_id:03d}) | 💵 **Em Dinheiro na Gaveta:** R$ {caixa_gaveta:.2f}")

        st.markdown("### 🛒 Registar Venda ou Operação Rápida")
        with st.form("form_pdv_rapido", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            tipo_mov = col_f1.selectbox("Tipo de Operação", ["Venda", "Sangria (Retirada)", "Reforço (Entrada de Troco)"])
            
            forma_pag = "Dinheiro"
            if tipo_mov == "Venda":
                forma_pag = col_f2.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito"])
            
            valor = st.number_input("Valor (R$)", min_value=0.01, value=10.0, step=1.0)
            
            if tipo_mov == "Venda" and forma_pag == "Pix":
                st.info(f"📲 **Chave Pix para leitura:** `{CHAVE_PIX}`")
                st.image(gerar_qrcode_pix(CHAVE_PIX, valor), width=180)

            if tipo_mov == "Venda" and forma_pag == "Dinheiro":
                recebido = st.number_input("Dinheiro entregue pelo cliente (R$)", min_value=0.0, value=float(valor), step=1.0)
                troco = recebido - valor
                if troco >= 0:
                    st.success(f"🧮 **Troco a devolver: R$ {troco:.2f}**")
                else:
                    st.error("⚠️ O valor entregue é menor que a venda.")

            descricao = st.text_input("Identificação / Descrição (Opcional)").strip()

            if st.form_submit_button("✅ Confirmar Lançamento", type="primary", use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO movimentacoes_caixa (turno_id, tipo, forma_pagamento, valor, descricao, data_hora, operador) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (turno_id, tipo_mov, forma_pag, valor, descricao, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), usuario_atual)
                )
                conn.commit()
                conn.close()
                st.success("Registo efetuado com sucesso!")
                st.rerun()

        st.divider()
        st.markdown("### 📋 Últimos Movimentos e Cancelamentos")
        if not df_m_turno.empty:
            st.dataframe(df_m_turno, use_container_width=True)
            
            with st.form("form_cancela_simples"):
                id_cancela = st.selectbox("Selecione o ID para Cancelar", df_m_turno['id'].tolist())
                st.write("🔒 **Autorização de Superior para Cancelamento**")
                
                conn = get_connection()
                sup_list = pd.read_sql_query("SELECT username FROM usuarios WHERE perfil IN ('Gerente / Admin', 'Gestor de Acompanhamento') AND status = 'Ativo'", conn)['username'].tolist()
                conn.close()

                sup_escolhido = st.selectbox("Selecionar Superior", sup_list)
                senha_sup = st.text_input("Senha do Superior", type="password")

                if st.form_submit_button("❌ Cancelar Movimento", use_container_width=True):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT senha FROM usuarios WHERE username = ?", (sup_escolhido,))
                    res_s = c.fetchone()
                    if res_s and res_s[0] == hash_senha(senha_sup):
                        c.execute("DELETE FROM movimentacoes_caixa WHERE id = ?", (id_cancela,))
                        conn.commit()
                        conn.close()
                        st.success("Movimento cancelado com sucesso!")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("Senha do superior incorreta.")
        else:
            st.info("Nenhum movimento neste turno.")

        st.divider()
        st.markdown("### 🔒 Fechamento de Caixa")
        with st.form("form_fechar_caixa_simples"):
            contagem_fisica = st.number_input("Dinheiro contado fisicamente na gaveta (R$)", min_value=0.0, value=float(caixa_gaveta), step=1.0)
            obs_f = st.text_input("Observação do Fechamento").strip()
            
            if st.form_submit_button("🔒 Fechar Caixa Definitivamente", use_container_width=True):
                dif = contagem_fisica - caixa_gaveta
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "UPDATE turnos_caixa SET valor_fechamento = ?, diferenca = ?, status = 'Fechado', observacao = ? WHERE id = ?",
                    (contagem_fisica, dif, f"Fechado. Dif: R$ {dif:.2f}. {obs_f}", turno_id)
                )
                conn.commit()
                conn.close()
                st.success(f"Caixa fechado! Diferença: R$ {dif:.2f}")
                st.rerun()
