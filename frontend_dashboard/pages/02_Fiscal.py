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
    from query_engine import carregar_dados_fiscais, converter_para_csv
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from query_engine import carregar_dados_fiscais, converter_para_csv

# --- FUNÇÕES AUXILIARES ---

def encontrar_rubricas_top5(lista_disponivel):
    """Retorna os nomes exatos das 5 principais contas."""
    keywords = [
        "1. RECEITA TOTAL",
        "2. TRANSF", 
        "3. RECEITA LÍQUIDA",
        "4. DESPESA TOTAL",
        "5. RESULTADO PRIMÁRIO"
    ]
    encontradas = []
    for key in keywords:
        match = next((r for r in lista_disponivel if key in r), None)
        if match: encontradas.append(match)
    return encontradas

def encontrar_match_pib(rubrica_real, lista_pib):
    """Encontra o par correspondente na lista do PIB."""
    try:
        return lista_pib[lista_pib.index(rubrica_real)]
    except ValueError:
        texto_busca = rubrica_real[:15]
        return next((r for r in lista_pib if texto_busca in r), None)

def converter_para_excel(df):
    """Converte DataFrame para buffer Excel (XLSX)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados_Fiscais')
    return output.getvalue()

def criar_grafico_dual(df_r, df_p, titulo):
    """Gera um gráfico isolado com Eixo Duplo (R$ e PIB)."""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_r['data'], y=df_r['valor'],
        name="R$ Bi", line=dict(color='#1f77b4', width=2.5), yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_p['data'], y=df_p['valor'],
        name="% PIB", mode='lines+markers',
        line=dict(color='#ff7f0e', width=2, dash='dot'), marker=dict(size=6), yaxis='y2'
    ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14)),
        template="plotly_white",
        height=350, 
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", y=1.1, x=0.5, xanchor='center'),
        yaxis=dict(showgrid=False),
        yaxis2=dict(overlaying='y', side='right', showgrid=True, gridcolor='#eee')
    )
    return fig

def criar_grafico_simples(df, titulo, cor_linha='#1f77b4'):
    """Gera um gráfico de linha simples."""
    fig = px.line(df, x="data", y="valor", title=titulo, template="plotly_white")
    fig.update_traces(line_color=cor_linha, line_width=2.5)
    fig.update_layout(
        title=dict(font=dict(size=14)),
        height=350,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_title=None, yaxis_title=None,
        yaxis=dict(showgrid=True, gridcolor='#eee')
    )
    return fig

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Fiscal | IFI", page_icon="🏛️", layout="wide")

st.title("🏛️ Monitor Fiscal (RTN)")
st.markdown("Acompanhe as finanças públicas federais.")

# --- CARREGAMENTO ---
with st.spinner('Carregando dados fiscais...'):
    df_reais_raw = carregar_dados_fiscais(tipo="reais")
    df_pib_raw = carregar_dados_fiscais(tipo="pib")

if df_reais_raw.empty or df_pib_raw.empty:
    st.error("Erro ao carregar dados.")
    st.stop()

# ==============================================================================
# 1. SIDEBAR: CONFIGURAÇÕES GLOBAIS
# ==============================================================================

# Filtro Temporal
st.sidebar.subheader("📅 Recorte Temporal")
anos_disponiveis = sorted(df_reais_raw['data'].dt.year.unique())
min_ano, max_ano = min(anos_disponiveis), max(anos_disponiveis)

anos_selecionados = st.sidebar.slider(
    "Selecione o intervalo de anos:",
    min_value=min_ano,
    max_value=max_ano,
    value=(min_ano, max_ano)
)

# Aplicação do Filtro Global
start_date = pd.Timestamp(f"{anos_selecionados[0]}-01-01")
end_date = pd.Timestamp(f"{anos_selecionados[1]}-12-31")

df_reais_full = df_reais_raw[(df_reais_raw['data'] >= start_date) & (df_reais_raw['data'] <= end_date)]
df_pib_full = df_pib_raw[(df_pib_raw['data'] >= start_date) & (df_pib_raw['data'] <= end_date)]

# Preparação das Listas (Necessário antes de renderizar os widgets de seleção)
lista_reais = sorted(df_reais_full['rubrica'].unique())
lista_pib = sorted(df_pib_full['rubrica'].unique())

st.sidebar.divider()

# Modo de Visualização
modo_visualizacao = st.sidebar.radio(
    "1. Modo de Visualização:",
    options=["Valores Reais (R$ Bilhões) - Mensal ", "% do PIB - Anual", "Comparativo"]
)

st.sidebar.divider()

# Escopo da Análise
escopo_analise = st.sidebar.radio(
    "2. Escopo:", 
    ["Contas Principais (Em Painel)", "Seleção Manual (Outras Contas)"],
    help="Painel exibe 5 gráficos separados. Manual permite comparar rubricas específicas."
)

# ==============================================================================
# 2. SIDEBAR: SELEÇÃO MANUAL 
# ==============================================================================
# Variáveis para armazenar a seleção manual (inicializadas como None)
rubrica_r_manual = None
rubrica_p_sel_manual = None
sel_manual = None

if escopo_analise == "Seleção Manual (Outras Contas)":
    st.sidebar.markdown("---")
    
    if modo_visualizacao == "Comparativo":
        ix_padrao = next((i for i, r in enumerate(lista_reais) if 'Resultado Primário' in r), 0)
        rubrica_r_manual = st.sidebar.selectbox("Selecione a Rubrica:", lista_reais, index=ix_padrao)
        
        rubrica_p = encontrar_match_pib(rubrica_r_manual, lista_pib)
        # Se achou match, pega o index, senão 0
        idx_p = lista_pib.index(rubrica_p) if rubrica_p in lista_pib else 0
        rubrica_p_sel_manual = st.sidebar.selectbox("Correspondente % PIB:", lista_pib, index=idx_p)
        
    else:
        lista_base = lista_reais if "Reais" in modo_visualizacao else lista_pib
        # Multiselect
        sel_manual = st.sidebar.multiselect("Rubricas:", lista_base, default=[lista_base[0]])

# ==============================================================================
# 3. SIDEBAR: OBSERVAÇÕES (Renderiza por último na barra)
# ==============================================================================
st.sidebar.markdown("---") 
st.sidebar.markdown("### ℹ️ Observações")
st.sidebar.info(
    """
    **Correção Monetária:**
    Os dados em "Valores Reais" referem-se aos valores nominais trazidos a valor presente (último mês observado) corrigidos pelo IPCA.
    
    **Fonte dos Dados:**
    [Tesouro Nacional Transparente](https://www.tesourotransparente.gov.br/)
    """
)

# ==============================================================================
# 4. ÁREA PRINCIPAL: GRÁFICOS E TABELAS
# ==============================================================================
df_exportacao = pd.DataFrame() 
st.divider()

# --- CENÁRIO A: PAINEL DE AGREGADOS ---
if escopo_analise == "Contas Principais (Em Painel)":
    
    st.subheader(f"📊 Painel das Principais Contas - {modo_visualizacao}")
    
    top5_reais = encontrar_rubricas_top5(lista_reais)
    top5_pib = encontrar_rubricas_top5(lista_pib)
    
    # Prepara exportação
    if "Reais" in modo_visualizacao:
        df_exportacao = df_reais_full[df_reais_full['rubrica'].isin(top5_reais)]
    elif "PIB" in modo_visualizacao:
        df_exportacao = df_pib_full[df_pib_full['rubrica'].isin(top5_pib)]
    else: 
        df_exportacao = df_reais_full[df_reais_full['rubrica'].isin(top5_reais)]

    cols = st.columns(2)
    
    for i, rubrica_r in enumerate(top5_reais):
        with cols[i % 2]: 
            dfr = df_reais_full[df_reais_full['rubrica'] == rubrica_r].sort_values('data')
            
            if modo_visualizacao == "Comparativo":
                rubrica_p = encontrar_match_pib(rubrica_r, lista_pib)
                if rubrica_p:
                    dfp = df_pib_full[df_pib_full['rubrica'] == rubrica_p].sort_values('data')
                    fig = criar_grafico_dual(dfr, dfp, rubrica_r.replace("1/", "")) 
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"Dados PIB não encontrados: {rubrica_r}")
            
            elif modo_visualizacao == "Valores Reais (R$ Bilhões) - Mensal ":
                fig = criar_grafico_simples(dfr, rubrica_r, '#1f77b4') 
                st.plotly_chart(fig, use_container_width=True)
                
            elif modo_visualizacao == "% do PIB - Anual":
                rubrica_p = encontrar_match_pib(rubrica_r, lista_pib)
                if rubrica_p:
                    dfp = df_pib_full[df_pib_full['rubrica'] == rubrica_p].sort_values('data')
                    fig = criar_grafico_simples(dfp, rubrica_p, '#ff7f0e')
                    st.plotly_chart(fig, use_container_width=True)

# --- CENÁRIO B: SELEÇÃO MANUAL ---
else:
    # Aqui usamos as variáveis capturadas lá em cima na sidebar
    
    if modo_visualizacao == "Comparativo":
        # Usa rubrica_r_manual e rubrica_p_sel_manual
        dfr = df_reais_full[df_reais_full['rubrica'] == rubrica_r_manual].sort_values('data')
        dfp = df_pib_full[df_pib_full['rubrica'] == rubrica_p_sel_manual].sort_values('data')
        
        fig = criar_grafico_dual(dfr, dfp, f"Comparativo: {rubrica_r_manual}")
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        df_exportacao = dfr 
        
    else:
        # Usa sel_manual
        if not sel_manual:
            st.warning("Selecione uma rubrica na barra lateral.")
            st.stop()
            
        lista_base = lista_reais if "Reais" in modo_visualizacao else lista_pib
        df_base = df_reais_full if "Reais" in modo_visualizacao else df_pib_full
        
        df_viz = df_base[df_base['rubrica'].isin(sel_manual)]
        
        fig = px.line(df_viz, x="data", y="valor", color="rubrica", title=f"Evolução Fiscal ({modo_visualizacao})", markers=True)
        fig.update_layout(height=500, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        
        df_exportacao = df_viz

# --- EXPORTAÇÃO ---
st.divider()
st.subheader("Baixar dados")

csv_data = converter_para_csv(df_exportacao)
xlsx_data = converter_para_excel(df_exportacao)

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.info("Escolha o formato para download:")
    st.info("É possivel copiar os dados abaixo ao: 1. clicar na primera célula 2. pressionar ctrl+shift e seta para direita 3. mantendo o ctrl+shift, apertar a seta para baixo. Após isso, copie e cole onde quiser.")

with col2:
    st.download_button(
        label="📥 Baixar CSV",
        data=csv_data,
        file_name="fiscal_dados.csv",
        mime="text/csv",
        use_container_width=True
    )

with col3:
    st.download_button(
        label="📊 Baixar Excel",
        data=xlsx_data,
        file_name="fiscal_dados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

st.dataframe(df_exportacao, use_container_width=True, hide_index=True)