import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os
import time

# 1. Importe a sua função de estilo
from interface_utils import configurar_interface_ifi

# 2. Chame a função logo após o set_page_config
st.set_page_config(page_title="Seu Título", layout="wide")
configurar_interface_ifi()

# --- Importação do Motor de Dados ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from query_engine import carregar_dados_macro, carregar_dados_fiscais, carregar_dados_sociais
except ImportError:
    st.error("Erro ao importar o motor de dados (query_engine).")
    st.stop()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Panorama | IFI",
    page_icon="📊",
    layout="wide"
)

# --- INICIALIZAÇÃO DO ESTADO DO CARROSSEL (APENAS FISCAL) ---
if 'fiscal_index' not in st.session_state:
    st.session_state.fiscal_index = 0

# CSS Customizado
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    div[data-testid="stMarkdownContainer"] p { font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÃO AUXILIAR: SPARKLINE ---
def criar_sparkline(df, coluna_data, coluna_valor, cor_linha):
    if df.empty: return None
    df_spark = df.sort_values(coluna_data).tail(12)
    fig = px.line(df_spark, x=coluna_data, y=coluna_valor)
    fig.update_traces(line_color=cor_linha, line_width=2)
    fig.update_layout(
        showlegend=False, height=50, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode=False
    )
    return fig

# --- TÍTULO ---
st.title("IFI")
st.markdown("### Resumo dos indicadores. Navegue entre as páginas para explorar os dados e baixá-los.")
st.divider()

# --- CARREGAMENTO DE DADOS ---
df_macro = carregar_dados_macro()
df_fiscal = carregar_dados_fiscais(tipo="reais")
df_social = carregar_dados_sociais()

# ==============================================================================
# 1. TERMÔMETRO MACRO
# ==============================================================================
st.subheader("Acompanhamento Macro")
col1, col2, col3 = st.columns(3)

# --- KPI 1: PREÇOS (INTERATIVO) ---
with col1:
    container = st.container(border=True)
    opcoes_preco = {
        "IPCA (Inflação Mensal)": {"busca": "IPCA - Mensal", "cor": "#E74C3C"},
        "IGP-M (Índice Geral)": {"busca": "IGP-M", "cor": "#8E44AD"}
    }
    escolha_preco = container.selectbox("Indicador de Preço:", list(opcoes_preco.keys()), key="sel_macro_preco")
    
    val, fig, data_obs = "N/A", None, ""
    try:
        cfg = opcoes_preco[escolha_preco]
        df_f = df_macro[df_macro['nome_variavel'].str.contains(cfg['busca'], case=False, na=False)].sort_values('data')
        if not df_f.empty:
            ultimo_dado = df_f.iloc[-1]
            val = f"{ultimo_dado['valor']:.2f}%"
            data_obs = ultimo_dado['data'].strftime('%d/%m/%Y')
            fig = criar_sparkline(df_f, 'data', 'valor', cfg['cor'])
    except: pass
    
    container.metric(escolha_preco, val)
    if data_obs: container.caption(f" Última observação: {data_obs}")
    if fig: container.plotly_chart(fig, use_container_width=True)

# --- KPI 2: JUROS (FIXO) ---
with col2:
    container = st.container(border=True)
    val, fig, data_obs = "N/A", None, ""
    try:
        df_s = df_macro[df_macro['nome_variavel'].str.contains("Selic", case=False, na=False)].sort_values('data')
        if not df_s.empty:
            ultimo_dado = df_s.iloc[-1]
            val = f"{ultimo_dado['valor']:.2f}%"
            data_obs = ultimo_dado['data'].strftime('%d/%m/%Y')
            fig = criar_sparkline(df_s, 'data', 'valor', '#2E86C1')
    except: pass
    
    container.metric("Taxa Selic Meta", val)
    if data_obs: container.caption(f" Última observação: {data_obs}")
    if fig: container.plotly_chart(fig, use_container_width=True)

# --- KPI 3: ECONOMIA REAL (INTERATIVO) ---
with col3:
    container = st.container(border=True)
    opcoes_real = {
        "Atividade (PIB) - Mensal": {"busca": "PIB", "cor": "#27AE60", "divisor": 1, "prefixo": "R$ ", "sufixo": " Tri"},
        "Câmbio (Dólar)": {"busca": "Dólar", "cor": "#117A65", "divisor": 1, "prefixo": "R$ ", "sufixo": ""}
    }
    escolha_real = container.selectbox("Indicador de Atividade:", list(opcoes_real.keys()), key="sel_macro_real")
    
    val, fig, data_obs = "N/A", None, ""
    try:
        cfg = opcoes_real[escolha_real]
        df_f = df_macro[df_macro['nome_variavel'].str.contains(cfg['busca'], case=False, na=False)].sort_values('data')
        if not df_f.empty:
            ultimo_dado = df_f.iloc[-1]
            valor_final = ultimo_dado['valor'] / cfg['divisor']
            val = f"{cfg['prefixo']}{valor_final:,.2f}{cfg['sufixo']}"
            data_obs = ultimo_dado['data'].strftime('%d/%m/%Y')
            fig = criar_sparkline(df_f, 'data', 'valor', cfg['cor'])
    except: pass
    
    container.metric(escolha_real, val)
    if data_obs: container.caption(f"Última observação: {data_obs}")
    if fig: container.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# 2. FISCAL (CARROSSEL) E SOCIAL
# ==============================================================================
st.divider()
col_fisc, col_soc = st.columns(2)

# --- KPI 4: FISCAL (CARROSSEL AUTOMÁTICO) ---
with col_fisc:
    st.subheader("Destaque Fiscal")
    container = st.container(border=True)
    
    lista_fiscal = [
        ("Resultado Primário", "5. RESULTADO PRIMÁRIO", "#884EA0"),
        ("Receita Total", "1. RECEITA TOTAL", "#27AE60"),
        ("Despesa Total", "4. DESPESA TOTAL", "#C0392B"),
        ("Receita Líquida", "3. RECEITA LÍQUIDA", "#2E86C1")
    ]
    
    idx = st.session_state.fiscal_index % len(lista_fiscal)
    nome_f, busca_f, cor_f = lista_fiscal[idx]
    
    val_fisc, fig_fisc, data_obs_f = "N/A", None, ""
    try:
        df_f = df_fiscal[df_fiscal['rubrica'].str.contains(busca_f, case=False, na=False)].sort_values('data')
        if not df_f.empty:
            ultimo_dado = df_f.iloc[-1]
            val_fisc = f"R$ {ultimo_dado['valor']/1000:,.1f} Bi"
            data_obs_f = ultimo_dado['data'].strftime('%d/%m/%Y')
            fig_fisc = criar_sparkline(df_f, 'data', 'valor', cor_f)
    except: pass
    
    container.metric(nome_f, val_fisc)
    if data_obs_f: container.caption(f" Última observação: {data_obs_f}")
    if fig_fisc: container.plotly_chart(fig_fisc, use_container_width=True)
    container.progress((idx + 1) / len(lista_fiscal))

# --- KPI 5: SOCIAL (INTERATIVO) ---
with col_soc:
    st.subheader("Destaque Social: Bolsa Família")
    container = st.container(border=True)
    
    opcoes_social = {
        "Quantidade de Famílias": {"busca": "qtd_familias_beneficiarias_bolsa_familia_s", "cor": "#F39C12", "divisor": 1_000_000, "sufixo": " Mi"},
        "Valor Repassado": {"busca": "valor_repassado_bolsa_familia_s", "cor": "#D35400", "divisor": 1_000_000_000, "prefixo": "R$", "sufixo": " Bi"}
    }
    
    escolha_soc = container.selectbox("Métrica Social:", list(opcoes_social.keys()), key="sel_social_kpi")
    
    val_soc, fig_soc, data_obs_s = "N/A", None, ""
    try:
        cfg = opcoes_social[escolha_soc]
        df_bf = df_social[df_social['nome_indicador'].str.contains("Bolsa Família", case=False, na=False)]
        df_s = df_bf[df_bf['nome_variavel'].str.contains(cfg['busca'], case=False)].sort_values('data')
        
        if not df_s.empty:
            ultimo_dado = df_s.iloc[-1]
            val_num = ultimo_dado['valor'] / cfg['divisor']
            val_soc = f"{val_num:.2f}{cfg['sufixo']}"
            data_obs_s = ultimo_dado['data'].strftime('%d/%m/%Y')
            fig_soc = criar_sparkline(df_s, 'data', 'valor', cfg['cor'])
    except: pass
    
    container.metric(escolha_soc, val_soc)
    if data_obs_s: container.caption(f" Última observação: {data_obs_s}")
    if fig_soc: container.plotly_chart(fig_soc, use_container_width=True)
    
    st.sidebar.markdown("") 
    st.sidebar.markdown("#### Nota:")
    st.sidebar.info(
        """
        Recarrege a página caso estaja com problema na apresentação dos dados.
        """
        )


# ==============================================================================
# MOTOR DO CARROSSEL
# ==============================================================================
time.sleep(5)
st.session_state.fiscal_index = (st.session_state.fiscal_index + 1) % len(lista_fiscal)
st.rerun()