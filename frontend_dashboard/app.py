import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os
import time
from datetime import datetime, timedelta

# --- Configuração de Caminhos e Módulos ---
# Garante que o Python encontre o query_engine e interface_utils [cite: 76]
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from interface_utils import configurar_interface_ifi
from query_engine import (
    carregar_dados_macro, 
    carregar_dados_fiscais, 
    carregar_dados_sociais, 
    get_status_atualizacao
)

# --- CONFIGURAÇÃO DA PÁGINA  ---
st.set_page_config(
    page_title="Home | IFI", # Nome que aparece na aba do navegador
    page_icon="📊",
    layout="wide"
)

# Aplica a identidade visual institucional 
configurar_interface_ifi()

# --- INICIALIZAÇÃO DE ESTADO ---
if 'fiscal_index' not in st.session_state:
    st.session_state.fiscal_index = 0

# --- ESTILIZAÇÃO CSS COMPLEMENTAR ---
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 26px; font-weight: 700; }
    div[data-testid="stMarkdownContainer"] p { font-size: 0.95rem; }
    .stProgress > div > div > div > div { background-color: #003366; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
def criar_sparkline(df, coluna_data, coluna_valor, cor_linha):
    if df.empty: return None
    df_spark = df.sort_values(coluna_data).tail(12)
    fig = px.line(df_spark, x=coluna_data, y=coluna_valor)
    fig.update_traces(line_color=cor_linha, line_width=2.5)
    fig.update_layout(
        showlegend=False, height=60, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode=False
    )
    return fig

# --- CABEÇALHO ---
st.markdown("### Panorama Econômico e Social")
st.caption("Resumo dos principais indicadores. Utilize o menu lateral para explorações detalhadas.")
st.divider()

# --- CARREGAMENTO DE DADOS (BigQuery) [cite: 48, 49] ---
with st.spinner("Sincronizando com o BigQuery..."):
    df_macro = carregar_dados_macro()
    df_fiscal = carregar_dados_fiscais(tipo="reais")
    df_social = carregar_dados_sociais()

# ==============================================================================
# 1. TERMÔMETRO MACROECONÔMICO
# ==============================================================================
st.subheader("Indicadores de Conjuntura")
c1, c2, c3 = st.columns(3)

with c1:
    with st.container(border=True):
        opcoes_preco = {
            "IPCA (Inflação Mensal)": {"busca": "IPCA - Mensal", "cor": "#E74C3C"},
            "IGP-M (Índice Geral)": {"busca": "IGP-M", "cor": "#8E44AD"}
        }
        escolha = st.selectbox("Preços:", list(opcoes_preco.keys()))
        cfg = opcoes_preco[escolha]
        df_f = df_macro[df_macro['nome_variavel'].str.contains(cfg['busca'], case=False)].sort_values('data')
        
        if not df_f.empty:
            ultimo = df_f.iloc[-1]
            st.metric(escolha, f"{ultimo['valor']:.2f}%")
            st.caption(f"Ref: {ultimo['data'].strftime('%b/%Y')}")
            st.plotly_chart(criar_sparkline(df_f, 'data', 'valor', cfg['cor']), use_container_width=True)

with c2:
    with st.container(border=True):
        df_s = df_macro[df_macro['nome_variavel'].str.contains("Selic", case=False)].sort_values('data')
        if not df_s.empty:
            ultimo = df_s.iloc[-1]
            st.metric("Taxa Selic Meta", f"{ultimo['valor']:.2f}%")
            st.caption(f"Ref: {ultimo['data'].strftime('%d/%m/%Y')}")
            st.plotly_chart(criar_sparkline(df_s, 'data', 'valor', '#2E86C1'), use_container_width=True)

with c3:
    with st.container(border=True):
        opcoes_real = {
            "Atividade (PIB)": {"busca": "PIB", "cor": "#27AE60", "pref": "R$ ", "suf": " Tri"},
            "Câmbio (Dólar)": {"busca": "Dólar", "cor": "#117A65", "pref": "R$ ", "suf": ""}
        }
        escolha = st.selectbox("Atividade e Mercado:", list(opcoes_real.keys()))
        cfg = opcoes_real[escolha]
        df_f = df_macro[df_macro['nome_variavel'].str.contains(cfg['busca'], case=False)].sort_values('data')
        
        if not df_f.empty:
            ultimo = df_f.iloc[-1]
            st.metric(escolha, f"{cfg['pref']}{ultimo['valor']:,.2f}{cfg['suf']}")
            st.caption(f"Ref: {ultimo['data'].strftime('%d/%m/%Y')}")
            st.plotly_chart(criar_sparkline(df_f, 'data', 'valor', cfg['cor']), use_container_width=True)

# ==============================================================================
# 2. DESTAQUES FISCAIS E SOCIAIS [cite: 51]
# ==============================================================================
st.divider()
col_f, col_s = st.columns(2)

with col_f:
    st.subheader("Resultado do Tesouro (RTN)")
    with st.container(border=True):
        lista_fiscal = [
            ("Resultado Primário", "5. RESULTADO PRIMÁRIO", "#884EA0"),
            ("Receita Total", "1. RECEITA TOTAL", "#27AE60"),
            ("Despesa Total", "4. DESPESA TOTAL", "#C0392B")
        ]
        idx = st.session_state.fiscal_index % len(lista_fiscal)
        nome, busca, cor = lista_fiscal[idx]
        
        df_f = df_fiscal[df_fiscal['rubrica'].str.contains(busca, case=False)].sort_values('data')
        if not df_f.empty:
            ultimo = df_f.iloc[-1]
            st.metric(nome, f"R$ {ultimo['valor']/1000:,.1f} Bi")
            st.caption(f" Ref: {ultimo['data'].strftime('%b/%Y')}")
            st.plotly_chart(criar_sparkline(df_f, 'data', 'valor', cor), use_container_width=True)
        st.progress((idx + 1) / len(lista_fiscal))

with col_s:
    st.subheader("Assistência Social")
    with st.container(border=True):
        opcoes_soc = {
            "Famílias Beneficiárias": {"busca": "qtd_familias_beneficiarias_bolsa_familia_s", "cor": "#F39C12", "div": 1e6, "suf": " Mi"},
            "Valor Repassado": {"busca": "valor_repassado_bolsa_familia_s", "cor": "#D35400", "div": 1e9, "suf": " Bi (R$)"}
        }
        escolha = st.selectbox("Métrica Bolsa Família:", list(opcoes_soc.keys()))
        cfg = opcoes_soc[escolha]
        df_s = df_social[df_social['nome_variavel'].str.contains(cfg['busca'], case=False)].sort_values('data')
        
        if not df_s.empty:
            ultimo = df_s.iloc[-1]
            st.metric(escolha, f"{(ultimo['valor']/cfg['div']):.2f}{cfg['suf']}")
            st.caption(f"Ref: {ultimo['data'].strftime('%b/%Y')}")
            st.plotly_chart(criar_sparkline(df_s, 'data', 'valor', cfg['cor']), use_container_width=True)

# --- RODAPÉ COM SINAL DE VIDA (SIDEBAR) ---
status = get_status_atualizacao()
if not status.empty:
    data_carga = status['ultima_carga'].max() - timedelta(hours=3) # Ajuste fuso Brasília
    st.sidebar.markdown(f"""
        <div style="position: fixed; bottom: 20px; font-size: 11px; color: #6c757d;">
            Última coleta de dados:<br><b>{data_carga.strftime('%d/%m/%Y às %H:%M:%S')}</b>
        </div>
    """, unsafe_allow_html=True)

# --- MOTOR DO CARROSSEL ---
time.sleep(8) # Aumentado para 8s para facilitar a leitura
st.session_state.fiscal_index = (st.session_state.fiscal_index + 1) % len(lista_fiscal)
st.rerun()  