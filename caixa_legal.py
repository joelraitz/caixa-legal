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

def gerar_pdf_relatorio_caixa(df_dados, titulo_relatorio):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#0f172a'))
    story.append(Paragraph("Relatório Financeiro - " + str(titulo_relatorio), title_style))
    story.append(Paragraph("Emitido em: " + datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), styles['Normal']))
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

# Barra Superior Simples
col_top1, col_top2, col_top3 = st.columns([3, 1, 1])
col_top1.title("💰 Caixa Legal — Ecrã de Operação")
col_top2.write(f"👤 **{st.session_state['usuario']}**
