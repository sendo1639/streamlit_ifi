import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os
import io
from datetime import datetime
from datetime import timedelta
from query_engine import get_status_atualizacao

# 1. estilo
from interface_utils import configurar_interface_ifi

# 2. Chame a função logo após o set_page_config
st.set_page_config(page_title="Seu Título", layout="wide")
configurar_interface_ifi()

# --- Configuração de Importação (Robusta) ---
try:
    from query_engine import carregar_dados_sociais, converter_para_csv
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from query_engine import carregar_dados_sociais, converter_para_csv

# --- FUNÇÕES AUXILIARES ---
def converter_para_excel(df):
    """Converte DataFrame para buffer Excel (XLSX)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados_Sociais')
    return output.getvalue()

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E TEXTOS
# ==============================================================================
st.set_page_config(
    page_title="Monitor Social | IFI",
    page_icon="imão",
    layout="wide"
)

st.title("Social")
st.markdown("""
Acompanhe a evolução dos principais programas de transferência de renda e cadastro social.
""")

# ==============================================================================
# 2. CARREGAMENTO DE DADOS (CACHEADO)
# ==============================================================================
with st.spinner('Conectando ao BigQuery e carregando dados...'):
    df_raw = carregar_dados_sociais()

if df_raw.empty:
    st.error("❌ Não foi possível carregar os dados. Verifique a conexão ou se a tabela está vazia.")
    st.stop()

# ==============================================================================
# 3. BARRA LATERAL (FILTROS ESTÁVEIS)
# ==============================================================================

# --- 3.1 Filtro Temporal ---
st.sidebar.subheader("📅 Recorte Temporal")
anos_disponiveis = sorted(df_raw['data'].dt.year.unique())
min_ano, max_ano = min(anos_disponiveis), max(anos_disponiveis)

anos_selecionados = st.sidebar.slider(
    "Selecione o intervalo de anos:",
    min_value=min_ano,
    max_value=max_ano,
    value=(min_ano, max_ano)
)

st.sidebar.divider()

# --- 3.2 Filtro Nível 1: Indicador/Programa ---
# CORREÇÃO: Usamos df_raw (base completa) para gerar a lista. 
# Assim, as opções não somem quando mudamos a data.
lista_programas = sorted(df_raw['nome_indicador'].unique())

programa_selecionado = st.sidebar.selectbox(
    "1. Selecione o Programa:",
    options=lista_programas,
    index=0
)

# --- 3.3 Filtro Nível 2: Variáveis ---
# Filtramos apenas pelo programa selecionado (mas ainda considerando todo o histórico)
df_programa_full = df_raw[df_raw['nome_indicador'] == programa_selecionado]
lista_variaveis = sorted(df_programa_full['nome_variavel'].unique())

if not lista_variaveis:
    st.warning("Não há variáveis disponíveis para este programa.")
    st.stop()

default_var = next((v for v in lista_variaveis if 'Beneficiários' in v or 'Geral' in v), lista_variaveis[0])

# Layout do Multiselect
container_multiselect = st.sidebar.container()
selecionar_tudo = st.sidebar.checkbox("Selecionar todas as variáveis", value=False)

with container_multiselect:
    if selecionar_tudo:
        variaveis_selecionadas = lista_variaveis
        st.multiselect(
            "2. Selecione as Variáveis:",
            options=lista_variaveis,
            default=lista_variaveis,
            disabled=True
        )
    else:
        variaveis_selecionadas = st.multiselect(
            "2. Selecione as Variáveis:",
            options=lista_variaveis,
            default=[default_var]
        )

if not variaveis_selecionadas:
    st.warning("⚠️ Por favor, selecione pelo menos uma variável.")
    st.stop()

# --- 3.4 Aplicação dos Filtros (DATA + VARIÁVEIS) ---
# Agora sim aplicamos o filtro de data, APÓS o usuário já ter feito suas escolhas.

start_date = pd.Timestamp(f"{anos_selecionados[0]}-01-01")
end_date = pd.Timestamp(f"{anos_selecionados[1]}-12-31")

# Filtra Data E Variáveis E Programa
df_visualizacao = df_raw[
    (df_raw['nome_indicador'] == programa_selecionado) &
    (df_raw['nome_variavel'].isin(variaveis_selecionadas)) &
    (df_raw['data'] >= start_date) & 
    (df_raw['data'] <= end_date)
]

# Observações 
st.sidebar.markdown("---") 
st.sidebar.markdown("#### Observações")
st.sidebar.info(
    """
    **Fonte dos Dados:**
    [SAGICAD - VIS DATA 3](https://aplicacoes.cidadania.gov.br/vis/data3/data-explorer.php)
    
    Dados obtidos através de uma API (MDS/SAGI). Os dados do VIS DATA foram usados como referência.
    """
)   

# ==============================================================================
# 4. VISUALIZAÇÃO GRÁFICA
# ==============================================================================
st.divider()

if not df_visualizacao.empty:
    fig = px.line(
        df_visualizacao,
        x="data",
        y="valor",
        color="nome_variavel",
        markers=True,
        title=f"{programa_selecionado}",
        template="plotly_white",
        labels={"data": "Mês de Referência", "valor": "Valor", "nome_variavel": "Variável"}
    )

    fig.update_layout(
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#eee'),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    # Mensagem amigável em vez de resetar a tela
    st.info(f"ℹ️ Não há dados para **{programa_selecionado}** no período de **{anos_selecionados[0]} a {anos_selecionados[1]}**.")
    st.caption("Tente ampliar o recorte temporal na barra lateral.")

# ==============================================================================
# 5. TABELA DE DADOS E EXPORTAÇÃO
# ==============================================================================
st.divider()
st.subheader("Baixar Dados")

# Só mostra botões se tiver dados
if not df_visualizacao.empty:
    csv_data = converter_para_csv(df_visualizacao)
    xlsx_data = converter_para_excel(df_visualizacao)

    col1, col2, col3 = st.columns([5, 1, 1])

    with col1:
        st.info("Escolha o formato para download:")
        st.info("É possivel copiar os dados abaixo ao: 1. clicar na primera célula 2. pressionar ctrl+shift e seta para direita 3. mantendo o ctrl+shift, apertar a seta para baixo. Após isso, copie e cole onde quiser.")

    with col2:
        st.download_button(
            label="📥 Baixar CSV",
            data=csv_data,
            file_name=f"ifi_social_{programa_selecionado.replace(' ', '_').lower()}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col3:
        st.download_button(
            label="📊 Baixar Excel",
            data=xlsx_data,
            file_name=f"ifi_social_{programa_selecionado.replace(' ', '_').lower()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # Tabela
    df_tabela = df_visualizacao.copy()
    df_tabela['data'] = df_tabela['data'].dt.strftime('%d/%m/%Y')

    st.dataframe(
        df_tabela[['data', 'nome_variavel', 'valor', 'origem_dado']],
        use_container_width=True,
        hide_index=True
    )

df_status = get_status_atualizacao()

if not df_status.empty:
    # Captura a data da última carga no BigQuery [cite: 51]
    data_carga = df_status['ultima_carga'].max()
    data_ajustada = data_carga + timedelta(hours=-3)
    data_formatada = data_ajustada.strftime('%d/%m/%Y às %H:%M:%S')
    
    # CSS para fixar o texto no final da sidebar [cite: 37, 38]
    st.sidebar.markdown(
        f"""
        <style>
            .sidebar-footer {{
                position: fixed;
                bottom: 15px;
                left: 15px;
                font-size: 12px;
                color: #6c757d; 
                font-family: 'sans-serif';
            }}
        </style>
        <div class="sidebar-footer">
            Última coleta de dados: <br>
            <b>{data_formatada}</b>
        </div>
        """, 
        unsafe_allow_html=True
)