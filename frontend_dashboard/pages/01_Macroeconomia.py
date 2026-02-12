import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import sys
import os
import io


# 1. Importe a sua função de estilo
from interface_utils import configurar_interface_ifi

# 2. Chame a função logo após o set_page_config
st.set_page_config(page_title="Seu Título", layout="wide")
configurar_interface_ifi()



# --- Importação Robusta ---
try:
    from query_engine import carregar_dados_macro, converter_para_csv
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from query_engine import carregar_dados_macro, converter_para_csv

# --- FUNÇÕES AUXILIARES ---

def converter_para_excel(df):
    """Converte DataFrame para buffer Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Macroeconomia')
    return output.getvalue()

def calcular_acumulado_12m(df_filtrado):
    """Calcula acumulado móvel de 12 meses."""
    df = df_filtrado.copy().sort_values('data')
    df['acumulado_12m'] = df['valor'].rolling(window=12).sum()
    return df

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Macroeconomia | IFI", page_icon="📈", layout="wide")

st.title("📈 Monitor Macroeconômico")
st.markdown("Acompanhamento dos principais indicadores de atividade, inflação, câmbio e política monetária.")

# --- CARREGAMENTO ---
with st.spinner('Carregando dados macroeconômicos...'):
    df_raw = carregar_dados_macro()

if df_raw.empty:
    st.error("Erro ao carregar dados.")
    st.stop()

# --- SIDEBAR: FILTRO TEMPORAL ---
st.sidebar.header("⚙️ Configuração")
st.sidebar.subheader("📅 Recorte Temporal")

anos_disponiveis = sorted(df_raw['data'].dt.year.unique())
min_ano, max_ano = min(anos_disponiveis), max(anos_disponiveis)
inicio_padrao = max(2019, min_ano)

anos_selecionados = st.sidebar.slider(
    "Selecione o intervalo:",
    min_value=min_ano,
    max_value=max_ano,
    value=(inicio_padrao, max_ano)
)

# Filtra Base para as abas fixas
start_date = pd.Timestamp(f"{anos_selecionados[0]}-01-01")
end_date = pd.Timestamp(f"{anos_selecionados[1]}-12-31")
df_macro = df_raw[(df_raw['data'] >= start_date) & (df_raw['data'] <= end_date)]

st.sidebar.markdown("---")
st.sidebar.markdown("#### Observações")
st.sidebar.info(
    """
    **Fonte dos Dados:**
    Banco Central do Brasil (SGS).
    """
)

# ==============================================================================
# ESTRUTURA DE 5 ABAS TEMÁTICAS
# ==============================================================================
tab_inflacao, tab_juros, tab_atividade, tab_cambio, tab_explorar = st.tabs([
    "🏷️ Inflação", 
    "💰 Juros (Selic)", 
    "🏭 Atividade", 
    "💵 Câmbio", 
    "🔎 Explorar e Baixar"
])

# --- ABA 1: INFLAÇÃO ---
with tab_inflacao:
    st.markdown("### Dinâmica de Preços")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("**IPCA (Índice Oficial)**")
        df_ipca = df_macro[df_macro['nome_variavel'].str.contains("IPCA", case=False, na=False)].copy()
        if not df_ipca.empty:
            var_ipca = next((v for v in df_ipca['nome_variavel'].unique() if 'mês' in v.lower() or 'mensal' in v.lower()), df_ipca['nome_variavel'].unique()[0])
            df_chart = df_ipca[df_ipca['nome_variavel'] == var_ipca].sort_values('data')
            df_chart = calcular_acumulado_12m(df_chart)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_chart['data'], y=df_chart['valor'], name="Mensal (%)", marker_color='#A9CCE3'))
            fig.add_trace(go.Scatter(x=df_chart['data'], y=df_chart['acumulado_12m'], name="Acumulado 12m", line=dict(color='#E74C3C', width=3), yaxis='y2'))
            fig.update_layout(template="plotly_white", height=400, yaxis2=dict(overlaying='y', side='right'), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.caption("**IGP-M (Índice Geral)**")
        df_igpm = df_macro[df_macro['nome_variavel'].str.contains("IGP-M|IGPM", case=False, na=False)].copy()
        if not df_igpm.empty:
            df_chart_igpm = df_igpm.sort_values('data')
            df_chart_igpm = calcular_acumulado_12m(df_chart_igpm)
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_chart_igpm['data'], y=df_chart_igpm['valor'], name="Mensal (%)", marker_color='#AED6F1'))
            fig2.add_trace(go.Scatter(x=df_chart_igpm['data'], y=df_chart_igpm['acumulado_12m'], name="Acumulado 12m", line=dict(color='#2874A6', width=3), yaxis='y2'))
            fig2.update_layout(template="plotly_white", height=400, yaxis2=dict(overlaying='y', side='right'), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig2, use_container_width=True)

# --- ABA 2: JUROS ---
with tab_juros:
    st.markdown("### Política Monetária")
    df_selic = df_macro[df_macro['nome_variavel'].str.contains("Selic", case=False, na=False)].copy()
    if not df_selic.empty:
        fig_selic = px.line(df_selic, x="data", y="valor", color="nome_variavel", title="Taxa Selic (% a.a.)", template="plotly_white")
        fig_selic.update_traces(line_shape='hv', line_width=3) 
        st.plotly_chart(fig_selic, use_container_width=True)

# --- ABA 3: ATIVIDADE ---
with tab_atividade:
    st.markdown("### Nível de Atividade Econômica")
    col_ibc, col_pib = st.columns(2)
    with col_ibc:
        df_ibc = df_macro[df_macro['nome_variavel'].str.contains("IBC", case=False, na=False)]
        if not df_ibc.empty:
            st.plotly_chart(px.line(df_ibc, x="data", y="valor", title="IBC-Br - Com Ajuste Sazonal", template="plotly_white"), use_container_width=True)
    with col_pib:
        df_pib = df_macro[df_macro['nome_variavel'].str.contains("PIB", case=False, na=False)]
        df_pib = df_pib[~df_pib['nome_variavel'].str.contains("IBC", case=False)]
        if not df_pib.empty:
            st.plotly_chart(px.bar(df_pib, x="data", y="valor", color="nome_variavel", title="PIB - Mensal Valores Correntes", template="plotly_white"), use_container_width=True)

# --- ABA 4: CÂMBIO ---
with tab_cambio:
    st.markdown("### Taxa de Câmbio")
    df_cambio = df_macro[df_macro['nome_variavel'].str.contains("Dólar|Câmbio", case=False, na=False)]
    if not df_cambio.empty:
        st.plotly_chart(px.line(df_cambio, x="data", y="valor", color="nome_variavel", title="Câmbio (R$/US$)", template="plotly_white"), use_container_width=True)

# --- ABA 5: EXPLORAR ---
with tab_explorar:
    st.markdown("### 🔎 Explorador e Baixar")
    
    lista_vars = sorted(df_raw['nome_variavel'].unique())
    
    sel_vars = st.multiselect(
        "Selecione os Indicadores para Comparar e Baixar:", 
        options=lista_vars, 
        default=[lista_vars[0]] if lista_vars else None,
        key="macro_explorer_multi"
    )
    
    if sel_vars:
        # Filtra por variáveis SELECIONADAS e pela DATA da sidebar
        df_custom = df_raw[
            (df_raw['nome_variavel'].isin(sel_vars)) & 
            (df_raw['data'] >= start_date) & 
            (df_raw['data'] <= end_date)
        ]
        
        if not df_custom.empty:
            fig_custom = px.line(df_custom, x="data", y="valor", color="nome_variavel", markers=True, template="plotly_white")
            fig_custom.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_custom, use_container_width=True)
            
            st.divider()
            col_d1, col_d2, col_d3 = st.columns([2,1,1])
            with col_d1: st.info("Escolha o formato para download:")
            with col_d1: st.info("É possivel copiar os dados abaixo ao: 1. clicar na primera célula 2. pressionar ctrl+shift e seta para direita 3. mantendo o ctrl+shift, apertar a seta para baixo. Após isso, copie e cole onde quiser.")
            with col_d2: st.download_button("📥 Baixar CSV", converter_para_csv(df_custom), "macro_ifi.csv", "text/csv", use_container_width=True)
            with col_d3: st.download_button("📊 Baixar Excel", converter_para_excel(df_custom), "macro_ifi.xlsx", use_container_width=True)
            
            st.dataframe(df_custom, use_container_width=True, hide_index=True)
        else:
            st.warning("Não há dados para os indicadores selecionados no período escolhido.")