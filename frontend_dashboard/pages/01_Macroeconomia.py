import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import sys
import os
import io
from datetime import datetime
from datetime import timedelta
from query_engine import get_status_atualizacao
from query_engine import carregar_dados_macro, converter_para_csv, carregar_dados_ettj

# 1. estilo
from interface_utils import configurar_interface_ifi

# 2. Chame a função logo após o set_page_config
st.set_page_config(page_title="Seu Título", layout="wide")
configurar_interface_ifi()



# --- Importação ---
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

st.title("Macroeconomia")
st.markdown("Acompanhamento dos principais indicadores de atividade, inflação, câmbio e política monetária.")

# --- CARREGAMENTO ---
with st.spinner('Carregando dados macroeconômicos...'):
    df_raw = carregar_dados_macro()

if df_raw.empty:
    st.error("Erro ao carregar dados.")
    st.stop()

# --- SIDEBAR: FILTRO TEMPORAL ---
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
tab_inflacao, tab_juros, tab_atividade, tab_cambio, tab_ettj, tab_explorar = st.tabs([
    "🏷️ Inflação", 
    "💰 Juros (Selic)", 
    "🏭 Atividade", 
    "💵 Câmbio",
    "📐 Curva de Juros (ETTJ)",
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

# --- ABA 5: CURVA DE JUROS (ETTJ) ---
with tab_ettj:
    st.markdown("### Estrutura a Termo das Taxas de Juros — ANBIMA")
    st.caption("Curva de juros estimada pela ANBIMA. Fonte: coleta diária incremental.")
 
    # --- Carregamento ---
    with st.spinner("Carregando dados da curva de juros..."):
        df_ettj_raw = carregar_dados_ettj()
 
    if df_ettj_raw.empty:
        st.warning(
            "⏳ Dados ainda não disponíveis. O histórico é construído diariamente. "
            "Verifique se o ETL já rodou ao menos uma vez."
        )
        st.stop()
 
    # --- Mapeamento para nomes legíveis ---
    NOMES_LEGIVEIS = {
        "ettj_ipca_pct_aa_252":          "ETTJ IPCA",
        "ettj_pre_pct_aa_252":           "ETTJ PRÉ",
        "inflacao_implicita_pct_aa_252": "Inflação Implícita",
    }
    CORES_CURVAS = {
        "ETTJ IPCA":          "#003366",
        "ETTJ PRÉ":           "#E67E22",
        "Inflação Implícita": "#27AE60",
    }
 
    df_ettj_raw["curva"] = df_ettj_raw["nome_variavel"].map(NOMES_LEGIVEIS).fillna(df_ettj_raw["nome_variavel"])
 
    # --- Layout: dois painéis lado a lado ---
    col_controles, col_grafico = st.columns([1, 3])
 
    with col_controles:
        st.markdown("#### ⚙️ Configurações")
 
        # Seleção de curvas (multi)
        curvas_disponiveis = sorted(df_ettj_raw["curva"].unique())
        curvas_selecionadas = st.multiselect(
            "Curvas:",
            options=curvas_disponiveis,
            default=curvas_disponiveis,
            key="ettj_curvas"
        )
 
        st.divider()
 
        # Modo de visualização
        modo = st.radio(
            "Modo:",
            options=["Dia específico", "Comparar datas"],
            key="ettj_modo"
        )
 
        datas_disponiveis = sorted(df_ettj_raw["data"].dt.date.unique(), reverse=True)
 
        if modo == "Dia específico":
            data_sel = st.selectbox(
                "Data de referência:",
                options=datas_disponiveis,
                format_func=lambda d: d.strftime("%d/%m/%Y"),
                key="ettj_data_unica"
            )
            datas_plot = [data_sel]
 
        else:  # Comparar datas
            st.caption("Selecione até 5 datas para comparar:")
            datas_plot = st.multiselect(
                "Datas:",
                options=datas_disponiveis,
                default=datas_disponiveis[:3] if len(datas_disponiveis) >= 3 else datas_disponiveis,
                format_func=lambda d: d.strftime("%d/%m/%Y"),
                max_selections=5,
                key="ettj_datas_multi"
            )
 
        st.divider()
 
        # Info sobre o histórico disponível
        n_dias = len(datas_disponiveis)
        data_mais_antiga = min(datas_disponiveis).strftime("%d/%m/%Y") if datas_disponiveis else "—"
        data_mais_recente = max(datas_disponiveis).strftime("%d/%m/%Y") if datas_disponiveis else "—"
 
        st.info(
            f"📅 **Histórico disponível**\n\n"
            f"**{n_dias}** dias úteis\n\n"
            f"De {data_mais_antiga}\n\n"
            f"até {data_mais_recente}"
        )
 
    with col_grafico:
 
        if not curvas_selecionadas:
            st.warning("Selecione ao menos uma curva.")
 
        elif not datas_plot:
            st.warning("Selecione ao menos uma data.")
 
        else:
            # --- Filtragem ---
            df_plot = df_ettj_raw[
                (df_ettj_raw["data"].dt.date.isin(datas_plot)) &
                (df_ettj_raw["curva"].isin(curvas_selecionadas))
            ].sort_values(["data", "curva", "vertice_du"])
 
            if df_plot.empty:
                st.info("Não há dados para a combinação selecionada.")
            else:
                # --- Construção do gráfico ---
                fig = go.Figure()
 
                if modo == "Dia específico":
                    # Uma linha por curva, estilo ANBIMA
                    for curva in curvas_selecionadas:
                        df_c = df_plot[df_plot["curva"] == curva]
                        if df_c.empty:
                            continue
                        fig.add_trace(go.Scatter(
                            x=df_c["vertice_du"],
                            y=df_c["valor"],
                            name=curva,
                            mode="lines",
                            line=dict(
                                color=CORES_CURVAS.get(curva, "#666"),
                                width=2.5,
                                shape="spline",
                                smoothing=0.8,
                            ),
                            hovertemplate=(
                                f"<b>{curva}</b><br>"
                                "Vértice: %{x} du<br>"
                                "Taxa: %{y:.4f}% a.a.<extra></extra>"
                            )
                        ))
 
                    data_fmt = pd.Timestamp(datas_plot[0]).strftime("%d/%m/%Y")
                    titulo = f"Curva Zero Cupom — {data_fmt}"
 
                else:
                    # Comparativo: uma linha por (data × curva)
                    # Usa opacidade para diferenciar datas
                    n_datas = len(datas_plot)
                    for i, data_ref in enumerate(sorted(datas_plot)):
                        opacidade = 0.4 + 0.6 * (i / max(n_datas - 1, 1))
                        for curva in curvas_selecionadas:
                            df_c = df_plot[
                                (df_plot["data"].dt.date == data_ref) &
                                (df_plot["curva"] == curva)
                            ]
                            if df_c.empty:
                                continue
                            cor_base = CORES_CURVAS.get(curva, "#666")
                            data_fmt = data_ref.strftime("%d/%m/%Y")
                            fig.add_trace(go.Scatter(
                                x=df_c["vertice_du"],
                                y=df_c["valor"],
                                name=f"{curva} ({data_fmt})",
                                mode="lines",
                                line=dict(
                                    color=cor_base,
                                    width=1.8 + i * 0.3,
                                    dash="solid" if i == n_datas - 1 else "dot",
                                    shape="spline",
                                    smoothing=0.8,
                                ),
                                opacity=opacidade,
                                hovertemplate=(
                                    f"<b>{curva} — {data_fmt}</b><br>"
                                    "Vértice: %{x} du<br>"
                                    "Taxa: %{y:.4f}% a.a.<extra></extra>"
                                )
                            ))
 
                    titulo = "Comparativo de Curvas de Juros"
 
                # --- Layout do gráfico ---
                fig.update_layout(
                    title=dict(text=titulo, font=dict(size=15, color="#003366")),
                    template="plotly_white",
                    height=460,
                    xaxis=dict(
                        title="Dias Úteis (Vértice)",
                        showgrid=True,
                        gridcolor="#f0f0f0",
                        tickformat=",",
                    ),
                    yaxis=dict(
                        title="Taxa % a.a.",
                        showgrid=True,
                        gridcolor="#f0f0f0",
                        ticksuffix="%",
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="left",
                        x=0,
                    ),
                    hovermode="x unified",
                    margin=dict(l=10, r=10, t=60, b=10),
                )
 
                st.plotly_chart(fig, use_container_width=True)
 
                # --- Métricas rápidas (apenas modo dia específico) ---
                if modo == "Dia específico" and len(curvas_selecionadas) > 0:
                    st.markdown("##### Vértices de referência")
                    vertices_ref = [252, 504, 1260, 2520]
                    cols_met = st.columns(len(vertices_ref))
 
                    for i, vert in enumerate(vertices_ref):
                        with cols_met[i]:
                            with st.container(border=True):
                                st.caption(f"**{vert} du**")
                                for curva in curvas_selecionadas:
                                    df_vert = df_plot[
                                        (df_plot["curva"] == curva) &
                                        (df_plot["vertice_du"] == vert)
                                    ]
                                    if not df_vert.empty:
                                        taxa = df_vert["valor"].iloc[0]
                                        st.metric(
                                            label=curva,
                                            value=f"{taxa:.2f}%",
                                            label_visibility="visible"
                                        )
 
                # --- Download dos dados filtrados ---
                st.divider()
                col_d1, col_d2 = st.columns([4, 1])
                with col_d1:
                    st.caption("Baixar os dados exibidos no gráfico:")
                with col_d2:
                    st.download_button(
                        "📥 CSV",
                        data=df_plot.drop(columns=["curva"]).to_csv(index=False).encode("utf-8"),
                        file_name="ettj_anbima.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

# --- ABA 6: EXPLORAR ---
with tab_explorar:
    st.markdown("### Explorar e Baixar")
    
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