"""
Página: Estatais — Dados Trimestrais 2025
Fonte: SEST/MGI via LAI — extração trimestral (planilha SIEST)
Período: 2025 em diante (1º a 4º trimestre)

Abas: Panorama Geral, Desempenho (DRE), Balanço, Relações com Tesouro,
Sustentabilidade (Não Dependentes), Análise TCU, Explorar e Baixar.
Pendente: DVA.
"""

import io
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from interface_utils import configurar_interface_ifi

st.set_page_config(
    page_title="Estatais 2025 | IFI",
    page_icon="🏛️",
    layout="wide"
)
configurar_interface_ifi()

try:
    from query_engine import carregar_dados_estatais_2025, converter_para_csv
except ImportError:
    import sys, os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from query_engine import carregar_dados_estatais_2025, converter_para_csv

# ==============================================================================
# CONSTANTES
# ==============================================================================
CORES = {
    "azul_ifi":  "#003366",
    "laranja":   "#E67E22",
    "verde":     "#27AE60",
    "vermelho":  "#C0392B",
    "cinza":     "#7F8C8D",
    "roxo":      "#8E44AD",
}

RUBRICAS = {
    # DRE
    "lle":                290000000,
    "larf":               250000000,
    "resultado_fin":      250100000,
    "receita_fin":        250101000,
    "receita_liquida":    230000000,
    "resultado_bruto":    240000000,
    "subvencao_tesouro":  260100000,
    "bas":                240101160,
    # Fluxo de Caixa
    "dividendos_uniao":   330022010,
    "jcp_uniao":          330025010,
    "afac_uniao":         330031000,
    "aporte_capital":     330034000,
    "subvencao_custeio":  330040000,
    "fco":                319900000,
    "caixa_inicio":       350000000,
    "caixa_final":        390000000,
    "variacao_caixa":     340000000,
    # Balanço
    "pl":                 130000000,
    "ativo_total":        110000000,
    "passivo_total":      120000000,
    "ativo_circulante":   110100000,
    "passivo_circulante": 120100000,
    "estoques":           110113000,
    "disponibilidades":   110101000,
}

# Instituições financeiras não têm AC/PC no mesmo padrão — excluídas
# da análise de liquidez (estrutura de balanço diferente por norma)
INST_FINANCEIRAS = {
    "BASA", "BNB", "GRUPO BB", "GRUPO BNDES", "GRUPO CAIXA",
    "FINEP", "ABGF",
}

# ==============================================================================
# HELPERS
# ==============================================================================
def converter_para_excel(df: pd.DataFrame, sheet: str = "Dados") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet)
    return buf.getvalue()

def botoes_download(df: pd.DataFrame, prefixo: str, sheet: str = "Dados"):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.caption("Baixar dados exibidos:")
    with col2:
        st.download_button("📥 CSV",
            converter_para_csv(df), f"{prefixo}.csv", "text/csv",
            use_container_width=True)
    with col3:
        st.download_button("📊 Excel",
            converter_para_excel(df, sheet), f"{prefixo}.xlsx",
            use_container_width=True)

def pegar_por_rubrica(df: pd.DataFrame, codigo: int) -> pd.DataFrame:
    """
    Retorna valores de uma rubrica por empresa/trimestre.
    'valor' = acumulado no ano. 'valor_trimestre' = trimestre isolado.
    """
    return (
        df[df["rubrica"] == codigo]
        .groupby(["exercicio", "trimestre", "sigla_empresa",
                  "dependencia", "setor", "periodo_label"])
        [["valor", "valor_trimestre"]]
        .sum(min_count=1)
        .reset_index()
    )

def fmt1(v):
    try:
        return f"{float(v):,.1f}"
    except Exception:
        return str(v)

def rotulo_periodo(row):
    return f"{int(row['exercicio'])}-T{int(row['trimestre'])}"

# ==============================================================================
# CARREGAMENTO
# ==============================================================================
st.title("🏛️ Monitor de Empresas Estatais — Dados Trimestrais 2025")
st.markdown("Demonstrações financeiras trimestrais — SEST/MGI via LAI")

with st.spinner("Carregando dados trimestrais..."):
    df_raw = carregar_dados_estatais_2025()

if df_raw is None or df_raw.empty:
    st.error("Não foi possível carregar os dados. Verifique se o `etl_estatais_2025.py` já foi executado.")
    st.stop()

df_raw["rubrica"] = pd.to_numeric(df_raw["rubrica"], errors="coerce")

# periodo_label aplicado UMA VEZ de forma vetorizada — evita df.apply(axis=1)
# em cada aba (gargalo de performance identificado: 20 chamadas por interação)
df_raw["periodo_label"] = (
    df_raw["exercicio"].astype("Int64").astype(str)
    + "-T" + df_raw["trimestre"].astype("Int64").astype(str)
)

# ==============================================================================
# SIDEBAR
# ==============================================================================
st.sidebar.header("🔍 Filtros")

trimestres_disp = sorted(df_raw["trimestre"].dropna().unique())
trim_sel = st.sidebar.multiselect(
    "Trimestre:", trimestres_disp, default=trimestres_disp,
    format_func=lambda x: f"{int(x)}º Trimestre"
)

dep_opcoes = sorted(df_raw["dependencia"].dropna().unique())
dep_sel = st.sidebar.multiselect("Dependência:", dep_opcoes, default=dep_opcoes)

setores_disp = sorted(df_raw["setor"].dropna().unique())
setor_sel = st.sidebar.multiselect("Setor:", setores_disp, default=setores_disp)

df_base = df_raw[
    df_raw["trimestre"].isin(trim_sel) &
    df_raw["dependencia"].isin(dep_sel) &
    df_raw["setor"].isin(setor_sel)
].copy()

st.sidebar.divider()
st.sidebar.caption(
    f"**{df_base['sigla_empresa'].nunique()} empresas** · "
    f"**{len(trim_sel)} trimestre(s)**"
)
st.sidebar.info("**Fonte:** SEST/MGI via LAI (extração SIEST)\n\n"
                "**Unidade original:** R$ mil → convertida para R$ no ETL.")

df_dre = df_base[df_base["nome_tipo_plano_contas"] == "DRE"]
df_bal = df_base[df_base["nome_tipo_plano_contas"] == "Balanço"]
df_fc  = df_base[df_base["nome_tipo_plano_contas"] == "Fluxo de Caixa"]
df_dva = df_base[df_base["nome_tipo_plano_contas"] == "DVA"]

# ==============================================================================
# ABAS
# ==============================================================================
tab_pan, tab_dre_aba, tab_bal_aba, tab_trs, tab_sust, tab_tcu, tab_exp = st.tabs([
    "📊 Panorama Geral",
    "📈 Desempenho (DRE)",
    "⚖️ Balanço",
    "🤝 Relações com Tesouro",
    "📉 Sustentabilidade",
    "🔍 Análise TCU",
    "🔎 Explorar e Baixar",
])

# ==============================================================================
# ABA — PANORAMA GERAL
# ==============================================================================
with tab_pan:
    st.markdown("### Visão Geral — Dados Trimestrais 2025")

    c1, c2, c3, c4 = st.columns(4)
    dep_contagem = df_base.drop_duplicates("sigla_empresa")["dependencia"].value_counts()
    c1.metric("Empresas no filtro", df_base["sigla_empresa"].nunique())
    c2.metric("Dependentes", int(dep_contagem.get("Dependente", 0)))
    c3.metric("Não dependentes", int(dep_contagem.get("Não dependente", 0)))
    c4.metric("Trimestres cobertos", df_base["trimestre"].nunique())

    st.divider()

    df_rl_pan = pegar_por_rubrica(df_dre, RUBRICAS["lle"])
    df_pl_pan = pegar_por_rubrica(df_bal, RUBRICAS["pl"])

    with st.expander("🔧 Diagnóstico", expanded=False):
        st.caption(
            f"LLE (rubrica {RUBRICAS['lle']}): {len(df_rl_pan)} linha(s) · "
            f"{df_rl_pan['sigla_empresa'].nunique() if not df_rl_pan.empty else 0} empresa(s)\n\n"
            f"PL (rubrica {RUBRICAS['pl']}): {len(df_pl_pan)} linha(s) · "
            f"{df_pl_pan['sigla_empresa'].nunique() if not df_pl_pan.empty else 0} empresa(s)\n\n"
            f"Balanço total: {len(df_bal)} linha(s) · "
            f"{df_bal['rubrica'].nunique() if not df_bal.empty else 0} rubricas"
        )

    col_a, col_b = st.columns(2)

    with col_a:
        if not df_rl_pan.empty:
            df_agg = (
                df_rl_pan.groupby(["exercicio","trimestre","periodo_label","dependencia"])
                ["valor"].sum().reset_index()
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values(["exercicio","trimestre"])
            )
            fig = px.bar(df_agg, x="periodo_label", y="valor_mi",
                color="dependencia", barmode="group",
                title="Resultado Líquido Agregado — Acumulado no Ano (R$ Mi)",
                labels={"valor_mi":"R$ Mi","periodo_label":"Período","dependencia":""},
                color_discrete_map={"Dependente":CORES["vermelho"],
                                    "Não dependente":CORES["azul_ifi"]},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig.update_layout(height=370, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados de Resultado Líquido para o filtro atual.")

    with col_b:
        if not df_pl_pan.empty:
            df_pl_agg = (
                df_pl_pan.groupby(["exercicio","trimestre","periodo_label"])
                ["valor"].sum().reset_index()
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values(["exercicio","trimestre"])
            )
            fig2 = px.line(df_pl_agg, x="periodo_label", y="valor_mi",
                title="Patrimônio Líquido Agregado (R$ Mi)",
                labels={"valor_mi":"R$ Mi","periodo_label":"Período"},
                template="plotly_white", markers=True)
            fig2.update_traces(line_color=CORES["azul_ifi"], line_width=2.5,
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig2.update_layout(height=370)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados de Patrimônio Líquido para o filtro atual.")

    st.caption("ℹ️ Resultado Líquido: acumulado no ano. Patrimônio Líquido: saldo pontual do trimestre.")

    st.divider()
    st.markdown("##### Empresas com Patrimônio Líquido Negativo")
    if not df_pl_pan.empty:
        ultimo = df_pl_pan.sort_values(["exercicio","trimestre"]).iloc[-1]
        pl_neg = df_pl_pan[
            (df_pl_pan["exercicio"] == ultimo["exercicio"]) &
            (df_pl_pan["trimestre"] == ultimo["trimestre"]) &
            (df_pl_pan["valor"] < 0)
        ]
        if not pl_neg.empty:
            st.caption(f"**Com PL negativo em {ultimo['periodo_label']}:**")
            for _, r in pl_neg.sort_values("valor").iterrows():
                st.markdown(f"- **{r['sigla_empresa']}** (R$ {r['valor']/1e6:,.1f} Mi)")
        else:
            st.caption(f"Nenhuma empresa com PL negativo em {ultimo['periodo_label']}.")

    st.divider()
    st.markdown("##### Empresas no filtro atual")
    resumo = (
        df_base.sort_values(["exercicio","trimestre"], ascending=False)
               .drop_duplicates("sigla_empresa")
               [["sigla_empresa","nome_empresa","dependencia","setor"]]
               .sort_values("sigla_empresa").reset_index(drop=True)
    )
    resumo.columns = ["Sigla","Nome","Dependência","Setor"]
    st.dataframe(resumo, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA — DESEMPENHO (DRE)
# ==============================================================================
with tab_dre_aba:
    st.markdown("### Demonstração do Resultado — Resultado Líquido")
    st.info(
        "A tabela do Grau de Dependência (metodologia Pellegrini) usa execução "
        "orçamentária anual (SIGA Brasil) — sem equivalente trimestral. "
        "Consulte na página 2008–2024.", icon="📌"
    )

    df_rl_dre = pegar_por_rubrica(df_dre, RUBRICAS["lle"])

    col_d1, col_d2 = st.columns(2)

    with col_d1:
        if not df_rl_dre.empty:
            periodos_dre = sorted(df_rl_dre["periodo_label"].unique(),
                key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
            periodo_dre = st.selectbox("Período:", periodos_dre, key="dre25_periodo")
            df_rl_per = (
                df_rl_dre[df_rl_dre["periodo_label"]==periodo_dre]
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values("valor_mi")
            )
            fig = px.bar(df_rl_per, x="valor_mi", y="sigla_empresa", orientation="h",
                color="valor_mi",
                color_continuous_scale=["#C0392B","#ECF0F1","#27AE60"],
                color_continuous_midpoint=0,
                title=f"Resultado Líquido — {periodo_dre} (R$ Mi, acumulado)",
                labels={"valor_mi":"R$ Mi","sigla_empresa":""},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>")
            fig.update_layout(height=max(420, len(df_rl_per)*24), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    with col_d2:
        if not df_rl_dre.empty:
            emp_dre = st.selectbox("Empresa:", sorted(df_rl_dre["sigla_empresa"].unique()),
                                   key="dre25_emp")
            df_rl_e = (
                df_rl_dre[df_rl_dre["sigla_empresa"]==emp_dre]
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values(["exercicio","trimestre"])
            )
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_rl_e["periodo_label"], y=df_rl_e["valor_mi"],
                marker_color=["#27AE60" if v>=0 else "#C0392B" for v in df_rl_e["valor_mi"]],
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>"
            ))
            fig2.update_layout(
                title=f"{emp_dre} — Resultado Líquido (R$ Mi, acumulado)",
                xaxis_title="Período", yaxis_title="R$ Mi",
                template="plotly_white", height=380)
            st.plotly_chart(fig2, use_container_width=True)

    st.caption("ℹ️ 4º trimestre = resultado do ano completo.")
    st.divider()
    df_rl_dl = df_rl_dre.assign(valor_mi=lambda x: x["valor"]/1e6) if not df_rl_dre.empty else df_rl_dre
    botoes_download(df_rl_dl, "estatais2025_dre_resultado", "Resultado")

# ==============================================================================
# ABA — BALANÇO
# ==============================================================================
with tab_bal_aba:
    st.markdown("### Balanço Patrimonial")

    df_pl_bal = pegar_por_rubrica(df_bal, RUBRICAS["pl"])
    df_rl_dre_bal = pegar_por_rubrica(df_dre, RUBRICAS["lle"])

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        if not df_pl_bal.empty:
            periodos_bal = sorted(df_pl_bal["periodo_label"].unique(),
                key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
            periodo_bal = st.selectbox("Período:", periodos_bal, key="bal25_periodo")
            df_pl_per = (
                df_pl_bal[df_pl_bal["periodo_label"]==periodo_bal]
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values("valor_mi")
            )
            fig = px.bar(df_pl_per, x="valor_mi", y="sigla_empresa", orientation="h",
                color="valor_mi",
                color_continuous_scale=["#C0392B","#ECF0F1","#2874A6"],
                color_continuous_midpoint=0,
                title=f"Patrimônio Líquido — {periodo_bal} (R$ Mi)",
                labels={"valor_mi":"R$ Mi","sigla_empresa":""},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>")
            fig.update_layout(height=max(420, len(df_pl_per)*24), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    with col_b2:
        if not df_pl_bal.empty:
            emp_bal = st.selectbox("Empresa:", sorted(df_pl_bal["sigla_empresa"].unique()),
                                   key="bal25_emp")
            df_pl_e = (
                df_pl_bal[df_pl_bal["sigla_empresa"]==emp_bal]
                .assign(valor_mi=lambda x: x["valor"]/1e6)
                .sort_values(["exercicio","trimestre"])
            )
            fig2 = px.area(df_pl_e, x="periodo_label", y="valor_mi",
                title=f"{emp_bal} — Patrimônio Líquido (R$ Mi)",
                labels={"valor_mi":"R$ Mi","periodo_label":"Período"},
                template="plotly_white")
            fig2.update_traces(line_color=CORES["azul_ifi"],
                fillcolor="rgba(0,51,102,0.15)",
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

    st.caption("ℹ️ Patrimônio Líquido é saldo pontual — não acumula entre trimestres.")

    st.divider()
    st.markdown("##### ROE — Retorno sobre Patrimônio Líquido")
    st.caption("Resultado Líquido (acumulado) ÷ Patrimônio Líquido (saldo pontual) × 100")

    if not df_pl_bal.empty and not df_rl_dre_bal.empty:
        df_roe = pd.merge(
            df_rl_dre_bal[["exercicio","trimestre","sigla_empresa","valor","periodo_label"]]
                          .rename(columns={"valor":"resultado"}),
            df_pl_bal[["exercicio","trimestre","sigla_empresa","valor"]]
                      .rename(columns={"valor":"pl"}),
            on=["exercicio","trimestre","sigla_empresa"]
        )
        df_roe = df_roe[df_roe["pl"] != 0].copy()
        df_roe["roe"] = (df_roe["resultado"] / df_roe["pl"] * 100).round(1)
        df_roe["ambos_neg"] = (df_roe["resultado"] < 0) & (df_roe["pl"] < 0)
        df_roe["resultado_mi"] = df_roe["resultado"] / 1e6
        df_roe["pl_mi"] = df_roe["pl"] / 1e6

        periodos_roe = sorted(df_roe["periodo_label"].unique(),
            key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
        periodo_roe = st.selectbox("Período:", periodos_roe, key="roe25_periodo")
        df_roe_per = df_roe[df_roe["periodo_label"]==periodo_roe].sort_values("roe")

        ambos_neg = df_roe_per[df_roe_per["ambos_neg"]]
        if not ambos_neg.empty:
            st.warning(
                f"⚠️ ROE não interpretável: {', '.join(ambos_neg['sigla_empresa'].tolist())} "
                f"têm resultado e PL ambos negativos em {periodo_roe}."
            )

        df_roe_per["cor"] = df_roe_per.apply(
            lambda r: CORES["cinza"] if r["ambos_neg"] else
                      (CORES["verde"] if r["roe"]>=0 else CORES["vermelho"]), axis=1)
        fig3 = go.Figure()
        for _, r in df_roe_per.iterrows():
            fig3.add_trace(go.Bar(
                x=[r["roe"]], y=[r["sigla_empresa"]], orientation="h",
                marker_color=r["cor"], name=r["sigla_empresa"], showlegend=False,
                hovertemplate=(
                    f"<b>{r['sigla_empresa']}</b><br>ROE: {r['roe']:.1f}%<br>"
                    f"Resultado: R$ {r['resultado_mi']:,.1f} Mi<br>"
                    f"PL: R$ {r['pl_mi']:,.1f} Mi"
                    + (" ⚠️ Ambos negativos" if r["ambos_neg"] else "")
                    + "<extra></extra>"
                )
            ))
        fig3.update_layout(title=f"ROE por Empresa — {periodo_roe} (%)",
            xaxis_title="ROE (%)", yaxis_title="", template="plotly_white",
            height=max(420, len(df_roe_per)*24))
        fig3.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig3, use_container_width=True)
        st.caption("🔘 Cinza = ROE não interpretável (resultado e PL ambos negativos)")

        if not ambos_neg.empty:
            st.markdown("##### Métricas alternativas — empresas com PL negativo")
            empresas_neg = ambos_neg["sigla_empresa"].tolist()
            df_pass_b = pegar_por_rubrica(df_bal, RUBRICAS["passivo_total"])
            df_at_b   = pegar_por_rubrica(df_bal, RUBRICAS["ativo_total"])
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.caption("**Passivo Total / Ativo Total (Alavancagem)**")
                df_alav = pd.merge(
                    df_pass_b[df_pass_b["sigla_empresa"].isin(empresas_neg)]
                              [["exercicio","trimestre","sigla_empresa","valor","periodo_label"]]
                              .rename(columns={"valor":"passivo"}),
                    df_at_b[df_at_b["sigla_empresa"].isin(empresas_neg)]
                            [["exercicio","trimestre","sigla_empresa","valor"]]
                            .rename(columns={"valor":"ativo"}),
                    on=["exercicio","trimestre","sigla_empresa"]
                )
                df_alav = df_alav[df_alav["ativo"]!=0].copy()
                df_alav["alavancagem"] = (df_alav["passivo"]/df_alav["ativo"]*100).round(1)
                df_alav = df_alav.sort_values(["exercicio","trimestre"])
                if not df_alav.empty:
                    fig_alav = px.line(df_alav, x="periodo_label", y="alavancagem",
                        color="sigla_empresa", markers=True,
                        labels={"alavancagem":"Passivo/Ativo (%)","periodo_label":"Período"},
                        template="plotly_white")
                    fig_alav.add_hline(y=100, line_dash="dot", line_color="red",
                        annotation_text="100%", annotation_position="right")
                    fig_alav.update_layout(height=320, legend=dict(orientation="h", y=1.1))
                    st.plotly_chart(fig_alav, use_container_width=True)
            with col_m2:
                st.caption("**FCO — Trimestre Isolado**")
                df_fco_neg = pegar_por_rubrica(
                    df_fc[df_fc["sigla_empresa"].isin(empresas_neg)], RUBRICAS["fco"])
                if not df_fco_neg.empty:
                    df_fco_neg = df_fco_neg.dropna(subset=["valor_trimestre"]).copy()
                    df_fco_neg["valor_mi"] = df_fco_neg["valor_trimestre"]/1e6
                    df_fco_neg = df_fco_neg.sort_values(["exercicio","trimestre"])
                    fig_fco = px.bar(df_fco_neg, x="periodo_label", y="valor_mi",
                        color="sigla_empresa", barmode="group",
                        labels={"valor_mi":"R$ Mi","periodo_label":"Período"},
                        title="FCO Trimestral (R$ Mi)", template="plotly_white")
                    fig_fco.update_layout(height=320, legend=dict(orientation="h", y=1.1))
                    st.plotly_chart(fig_fco, use_container_width=True)
                else:
                    st.info("Dados de FCO não disponíveis.")

    st.divider()
    botoes_download(
        df_pl_bal.assign(valor_mi=lambda x: x["valor"]/1e6) if not df_pl_bal.empty else df_pl_bal,
        "estatais2025_balanco_pl", "PL")

# ==============================================================================
# ABA — RELAÇÕES COM TESOURO
# ==============================================================================
with tab_trs:
    st.markdown("### Relações Financeiras com o Tesouro Nacional")

    with st.expander("ℹ️ Contas utilizadas"):
        st.markdown("""
Plano de contas único (9 dígitos) — um código por categoria, válido para todas as empresas.

| Categoria | Código |
|---|---|
| Aporte de Capital da União | 330034000 |
| AFAC Recebido | 330031000 |
| Subvenção para Custeio | 330040000 |
| Dividendos pagos à União | 330022010 |
| JCP pago à União | 330025010 |

Dividendos e JCP vêm negativos no FC (saída de caixa da empresa) — convertidos para positivo na exibição.
Valores acumulados no ano.
        """)

    CODIGOS_TRS = {
        "Aportes de Capital":       RUBRICAS["aporte_capital"],
        "AFAC Recebido":            RUBRICAS["afac_uniao"],
        "Subvenção para Custeio":   RUBRICAS["subvencao_custeio"],
        "Dividendos pagos à União": RUBRICAS["dividendos_uniao"],
        "JCP pago à União":         RUBRICAS["jcp_uniao"],
    }
    CORES_TRS = {
        "Aportes de Capital":       CORES["vermelho"],
        "AFAC Recebido":            "#E74C3C",
        "Subvenção para Custeio":   CORES["laranja"],
        "Dividendos pagos à União": CORES["verde"],
        "JCP pago à União":         "#1E8449",
    }

    dados_trs = {nome: pegar_por_rubrica(df_fc, cod) for nome, cod in CODIGOS_TRS.items()}

    for nome in ["Dividendos pagos à União", "JCP pago à União"]:
        if not dados_trs[nome].empty:
            dados_trs[nome]["valor"] = dados_trs[nome]["valor"].abs()

    lista_trs = []
    for nome, df_t in dados_trs.items():
        if not df_t.empty:
            d = df_t.groupby(["exercicio","trimestre","periodo_label"])["valor"].sum().reset_index()
            d["tipo"] = nome
            d["valor_mi"] = d["valor"]/1e6
            lista_trs.append(d.sort_values(["exercicio","trimestre"]))
    df_trs_agg = pd.concat(lista_trs, ignore_index=True).dropna() if lista_trs else pd.DataFrame()

    if not df_trs_agg.empty:
        fig = px.bar(df_trs_agg, x="periodo_label", y="valor_mi", color="tipo",
            title="Fluxo Financeiro Entre União e Estatais (R$ Mi, acumulado no ano)",
            labels={"valor_mi":"R$ Mi","periodo_label":"Período","tipo":""},
            barmode="group", template="plotly_white", color_discrete_map=CORES_TRS)
        fig.update_traces(hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
        fig.update_layout(height=420, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("##### Saldo Líquido: União → Estatais")
    st.caption("Positivo = Tesouro transferiu mais. Negativo = Estatais devolveram mais.")

    periodos_saldo = sorted(set(
        (r["exercicio"], r["trimestre"])
        for nome in CODIGOS_TRS if not dados_trs[nome].empty
        for _, r in dados_trs[nome][["exercicio","trimestre"]].drop_duplicates().iterrows()
    ))
    if periodos_saldo:
        def tot_trs(df):
            return df.groupby(["exercicio","trimestre"])["valor"].sum() if not df.empty else pd.Series(dtype=float)
        idx = pd.MultiIndex.from_tuples(periodos_saldo, names=["exercicio","trimestre"])
        df_saldo = pd.DataFrame(index=idx)
        df_saldo["entrada"] = (
            tot_trs(dados_trs["Aportes de Capital"])
            .add(tot_trs(dados_trs["AFAC Recebido"]), fill_value=0)
            .add(tot_trs(dados_trs["Subvenção para Custeio"]), fill_value=0)
        )
        df_saldo["saida"] = (
            tot_trs(dados_trs["Dividendos pagos à União"])
            .add(tot_trs(dados_trs["JCP pago à União"]), fill_value=0)
        )
        df_saldo = df_saldo.fillna(0).reset_index()
        df_saldo["saldo"] = (df_saldo["entrada"] - df_saldo["saida"])/1e6
        df_saldo["periodo_label"] = (
            df_saldo["exercicio"].astype(str) + "-T" + df_saldo["trimestre"].astype(str))
        df_saldo = df_saldo.sort_values(["exercicio","trimestre"])

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_saldo["periodo_label"], y=df_saldo["saldo"],
            marker_color=[CORES["vermelho"] if v>0 else CORES["verde"] for v in df_saldo["saldo"]],
            hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>", showlegend=False))
        fig2.update_layout(title="Saldo Líquido das Transferências (R$ Mi)",
            xaxis_title="Período", yaxis_title="R$ Mi",
            template="plotly_white", height=340)
        fig2.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("##### Detalhamento por Empresa")
    det_list = []
    for nome, df_t in dados_trs.items():
        if not df_t.empty:
            d = df_t.copy()
            d["tipo"] = nome
            d["valor_mi"] = d["valor"]/1e6
            det_list.append(d)
    if det_list:
        df_det = pd.concat(det_list)
        col_t1, col_t2 = st.columns([1,2])
        with col_t1:
            periodos_det = sorted(df_det["periodo_label"].unique(),
                key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
            periodo_det = st.selectbox("Período:", periodos_det, key="trs25_periodo")
        with col_t2:
            tipos_disp = sorted(df_det["tipo"].unique())
            tipos_sel = st.multiselect("Tipos de fluxo:", tipos_disp,
                default=tipos_disp, key="trs25_tipos")

        if not tipos_sel:
            st.warning("Selecione ao menos um tipo de fluxo.")
        else:
            df_det_per = df_det[
                (df_det["periodo_label"]==periodo_det) &
                (df_det["tipo"].isin(tipos_sel))
            ].copy()
            if len(tipos_sel) == 1:
                ordem = df_det_per.sort_values("valor_mi", ascending=True)["sigla_empresa"].tolist()
                titulo = f"{tipos_sel[0]} por Empresa — {periodo_det} (R$ Mi)"
            else:
                ordem = (df_det_per.groupby("sigla_empresa")["valor_mi"]
                         .apply(lambda s: s.abs().sum()).sort_values(ascending=True).index.tolist())
                titulo = f"Fluxo por Empresa — {periodo_det} (R$ Mi)"
            df_det_per["sigla_empresa"] = pd.Categorical(
                df_det_per["sigla_empresa"], categories=ordem, ordered=True)
            df_det_per = df_det_per.sort_values("sigla_empresa")

            fig3 = px.bar(df_det_per, x="valor_mi", y="sigla_empresa",
                color="tipo", orientation="h", barmode="group", title=titulo,
                labels={"valor_mi":"R$ Mi","sigla_empresa":"","tipo":""},
                template="plotly_white", color_discrete_map=CORES_TRS)
            fig3.update_traces(
                hovertemplate="%{fullData.name}: R$ %{x:,.1f} Mi<extra></extra>")
            fig3.update_layout(
                height=max(420, df_det_per["sigla_empresa"].nunique()*30),
                legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig3, use_container_width=True)
            st.divider()
            botoes_download(df_det_per, "estatais2025_relacoes_tesouro", "Tesouro")

# ==============================================================================
# ABA — SUSTENTABILIDADE (NÃO DEPENDENTES)
# ==============================================================================
with tab_sust:
    st.markdown("### Sustentabilidade Econômico-Financeira — Empresas Não Dependentes")
    st.caption(
        "Empresas não dependentes deveriam se auto-sustentar operacionalmente. "
        "Quando o resultado líquido positivo é sustentado por receita financeira — "
        "e não pela atividade-fim — a fronteira com a dependência se estreita, "
        "gerando risco fiscal não orçado para o Tesouro Nacional."
    )

    # Filtra não dependentes
    df_dre_nd = df_dre[df_dre["dependencia"] == "Não dependente"].copy()
    df_bal_nd = df_bal[df_bal["dependencia"] == "Não dependente"].copy()
    df_fc_nd  = df_fc[df_fc["dependencia"]  == "Não dependente"].copy()

    if df_dre_nd.empty:
        st.info("Nenhuma empresa não dependente no filtro atual.")
        st.stop()

    # Seletor de período
    periodos_nd = sorted(df_dre_nd["periodo_label"].unique(),
        key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
    periodo_nd = st.selectbox("Período de referência:", periodos_nd, key="sust_periodo")

    # Cálculo dos indicadores para o período selecionado
    def pegar_nd(df, cod):
        r = df[(df["rubrica"]==cod) & (df["periodo_label"]==periodo_nd)]
        return r.groupby("sigla_empresa")["valor"].sum()

    s_larf = pegar_nd(df_dre_nd, RUBRICAS["larf"])
    s_lle  = pegar_nd(df_dre_nd, RUBRICAS["lle"])
    s_rl   = pegar_nd(df_dre_nd, RUBRICAS["receita_liquida"])
    s_rf   = pegar_nd(df_dre_nd, RUBRICAS["receita_fin"])
    s_fco  = pegar_nd(df_fc_nd,  RUBRICAS["fco"])

    df_ind = pd.DataFrame({
        "LARF": s_larf, "LLE": s_lle, "RL": s_rl, "RF": s_rf, "FCO": s_fco
    })

    # Exclui linhas sem Receita Líquida (instituições financeiras usam outro padrão)
    df_ind = df_ind[df_ind["RL"].notna() & (df_ind["RL"] != 0)].copy()
    df_ind["Margem_Op"]  = (df_ind["LARF"] / df_ind["RL"] * 100).round(1)
    df_ind["Margem_Liq"] = (df_ind["LLE"]  / df_ind["RL"] * 100).round(1)
    df_ind["RF_RL_pct"]  = (df_ind["RF"]   / df_ind["RL"] * 100).round(1)
    df_ind["FCO_LLE"]    = (df_ind["FCO"]  / df_ind["LLE"]).round(2)

    # -----------------------------------------------------------------------
    # PAINEL DE RISCO (tabela semáforo)
    # -----------------------------------------------------------------------
    st.markdown("#### Painel de Risco")

    def sem_op(v):
        if pd.isna(v): return "—"
        return "🔴" if v < 0 else ("🟡" if v < 5 else "🟢")

    def sem_rf(v):
        if pd.isna(v): return "—"
        return "🔴" if v > 30 else ("🟡" if v > 15 else "🟢")

    def sem_fco(v):
        if pd.isna(v): return "—"
        return "🔴" if v < 0 else ("🟡" if v < 0.5 else "🟢")

    df_painel = df_ind.sort_values("Margem_Op").copy()
    df_display = pd.DataFrame({
        "Empresa":               df_painel.index,
        "Margem Op. (%)":        df_painel["Margem_Op"].map(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"),
        "Margem Líq. (%)":       df_painel["Margem_Liq"].map(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"),
        "RF / Rec. Líq. (%)":   df_painel["RF_RL_pct"].map(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"),
        "FCO / LLE":             df_painel["FCO_LLE"].map(
            lambda x: f"{x:.2f}" if pd.notna(x) else "—"),
        "⚡ Op.":  df_painel["Margem_Op"].apply(sem_op),
        "💰 RF":   df_painel["RF_RL_pct"].apply(sem_rf),
        "💵 FCO":  df_painel["FCO_LLE"].apply(sem_fco),
    })

    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.caption(
        "⚡ Margem Operacional: 🔴 < 0% · 🟡 0–5% · 🟢 > 5%  "
        "— 💰 RF/Rec. Líq.: 🔴 > 30% · 🟡 15–30% · 🟢 < 15%  "
        "— 💵 FCO/LLE: 🔴 < 0 · 🟡 0–0,5 · 🟢 > 0,5"
    )

    st.divider()

    # -----------------------------------------------------------------------
    # GRÁFICO 1 — Margem Operacional vs Margem Líquida
    # -----------------------------------------------------------------------
    st.markdown("#### Margem Operacional vs. Margem Líquida")
    st.caption(
        "Quando a Margem Líquida supera expressivamente a Margem Operacional, "
        "o resultado contábil está sendo sustentado por receita financeira — "
        "não pela atividade-fim da empresa."
    )

    df_marg = df_painel[["Margem_Op","Margem_Liq"]].dropna()
    df_marg_long = pd.melt(
        df_marg.reset_index(),
        id_vars=["sigla_empresa"],
        value_vars=["Margem_Op","Margem_Liq"],
        var_name="Tipo", value_name="Margem"
    )
    df_marg_long["Tipo"] = df_marg_long["Tipo"].map({
        "Margem_Op":  "Margem Operacional (LARF/RL)",
        "Margem_Liq": "Margem Líquida (LLE/RL)"
    })
    # Ordena por Margem Operacional
    ordem_marg = df_marg.sort_values("Margem_Op")["Margem_Op"].index.tolist()

    fig_marg = px.bar(
        df_marg_long,
        x="Margem", y="sigla_empresa",
        color="Tipo", barmode="overlay",
        orientation="h",
        title=f"Margem Operacional vs. Líquida — {periodo_nd} (%)",
        labels={"Margem":"%","sigla_empresa":"","Tipo":""},
        color_discrete_map={
            "Margem Operacional (LARF/RL)": CORES["azul_ifi"],
            "Margem Líquida (LLE/RL)":      "rgba(39,174,96,0.45)",
        },
        template="plotly_white",
        category_orders={"sigla_empresa": ordem_marg}
    )
    fig_marg.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
    fig_marg.update_traces(hovertemplate="%{fullData.name}<br>%{y}: %{x:.1f}%<extra></extra>")
    fig_marg.update_layout(
        height=max(400, len(df_marg)*36),
        legend=dict(orientation="h", y=1.08),
        hovermode="y unified", xaxis_ticksuffix="%"
    )
    st.plotly_chart(fig_marg, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # GRÁFICO 2 — RF / Receita Líquida — evolução trimestral
    # -----------------------------------------------------------------------
    st.markdown("#### Receita Financeira / Receita Líquida — Evolução")
    st.caption(
        "Quanto da receita total vem de rendimentos financeiros sobre aportes "
        "do Tesouro, e não da atividade operacional."
    )

    # Empresas com RF/RL > 15% no período selecionado — mais relevantes
    empresas_rf_alerta = df_painel[df_painel["RF_RL_pct"] > 15].index.tolist()
    emps_rf_sel = st.multiselect(
        "Empresas:", sorted(df_dre_nd["sigla_empresa"].unique()),
        default=empresas_rf_alerta[:6] if empresas_rf_alerta else [],
        key="sust_rf_emp"
    )

    if emps_rf_sel:
        def serie_ratio(cod_num, cod_den, label, df_src):
            s_num = (df_src[df_src["rubrica"]==cod_num]
                     .groupby(["exercicio","trimestre","sigla_empresa","periodo_label"])["valor"]
                     .sum().reset_index().rename(columns={"valor":"num"}))
            s_den = (df_src[df_src["rubrica"]==cod_den]
                     .groupby(["exercicio","trimestre","sigla_empresa","periodo_label"])["valor"]
                     .sum().reset_index().rename(columns={"valor":"den"}))
            df_r = pd.merge(s_num, s_den, on=["exercicio","trimestre","sigla_empresa","periodo_label"])
            df_r = df_r[df_r["den"]!=0].copy()
            df_r["ratio"] = (df_r["num"]/df_r["den"]*100).round(1)
            df_r["label"] = label
            return df_r.sort_values(["exercicio","trimestre"])

        df_evol_rf = serie_ratio(
            RUBRICAS["receita_fin"], RUBRICAS["receita_liquida"],
            "RF / Rec. Líq. (%)", df_dre_nd
        )
        df_evol_rf = df_evol_rf[df_evol_rf["sigla_empresa"].isin(emps_rf_sel)]

        if not df_evol_rf.empty:
            fig_evol = px.line(df_evol_rf, x="periodo_label", y="ratio",
                color="sigla_empresa", markers=True,
                title="Receita Financeira / Receita Líquida (%)",
                labels={"ratio":"%","periodo_label":"Período","sigla_empresa":""},
                template="plotly_white")
            fig_evol.add_hline(y=30, line_dash="dot", line_color="red",
                annotation_text="Limiar de atenção (30%)",
                annotation_position="bottom right")
            fig_evol.update_traces(
                hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>")
            fig_evol.update_layout(
                height=400, yaxis_ticksuffix="%",
                legend=dict(orientation="h", y=1.1),
                hovermode="x unified"
            )
            st.plotly_chart(fig_evol, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # GRÁFICO 3 — FCO / LLE
    # -----------------------------------------------------------------------
    st.markdown("#### FCO / LLE — Conversão do Lucro em Caixa")
    st.caption(
        "Razão entre o Fluxo de Caixa Operacional e o Lucro Líquido. "
        "Valor negativo indica que a empresa consome caixa mesmo registrando "
        "lucro contábil — sinal de resultado não sustentável no médio prazo."
    )

    df_fco_nd_r = pegar_por_rubrica(df_fc_nd, RUBRICAS["fco"])
    df_lle_nd_r = pegar_por_rubrica(df_dre_nd, RUBRICAS["lle"])

    if not df_fco_nd_r.empty and not df_lle_nd_r.empty:
        # FCO acumulado no período (usar valor, não valor_trimestre)
        df_fco_ratio = pd.merge(
            df_fco_nd_r[["exercicio","trimestre","sigla_empresa","valor","periodo_label"]]
                        .rename(columns={"valor":"fco"}),
            df_lle_nd_r[["exercicio","trimestre","sigla_empresa","valor"]]
                        .rename(columns={"valor":"lle"}),
            on=["exercicio","trimestre","sigla_empresa"]
        )
        df_fco_ratio = df_fco_ratio[df_fco_ratio["lle"]!=0].copy()
        df_fco_ratio["fco_lle"] = (df_fco_ratio["fco"]/df_fco_ratio["lle"]).round(2)
        df_fco_ratio = df_fco_ratio.sort_values(["exercicio","trimestre"])

        emps_fco = st.multiselect(
            "Empresas:", sorted(df_fco_ratio["sigla_empresa"].unique()),
            default=sorted(df_fco_ratio["sigla_empresa"].unique())[:6],
            key="sust_fco_emp"
        )
        if emps_fco:
            df_fco_sel = df_fco_ratio[df_fco_ratio["sigla_empresa"].isin(emps_fco)]
            fig_fco = px.line(df_fco_sel, x="periodo_label", y="fco_lle",
                color="sigla_empresa", markers=True,
                title="FCO / LLE — evolução trimestral",
                labels={"fco_lle":"FCO/LLE","periodo_label":"Período","sigla_empresa":""},
                template="plotly_white")
            fig_fco.add_hline(y=0, line_dash="dash", line_color="red", line_width=1.5,
                annotation_text="FCO negativo", annotation_position="right")
            fig_fco.add_hline(y=1, line_dash="dot", line_color="gray",
                annotation_text="FCO = LLE", annotation_position="right")
            fig_fco.update_traces(
                hovertemplate="%{fullData.name}: %{y:.2f}<extra></extra>")
            fig_fco.update_layout(
                height=400, legend=dict(orientation="h", y=1.1),
                hovermode="x unified"
            )
            st.plotly_chart(fig_fco, use_container_width=True)

    st.caption(
        "ℹ️ Instituições financeiras (BASA, BNB, GRUPO BB, GRUPO BNDES, GRUPO CAIXA, "
        "FINEP, ABGF) não aparecem na tabela de Margens por utilizarem estrutura "
        "contábil diferente (sem Receita Líquida no mesmo padrão). "
        "Estão presentes no gráfico de FCO/LLE quando disponível."
    )

    st.divider()
    botoes_download(df_ind.reset_index(), "estatais2025_sustentabilidade", "Sustentabilidade")
    st.divider()
    st.markdown("### Bloco B — Empresas Dependentes: Custo Fiscal e Trajetória")
    st.caption(
        "Para as dependentes, o custo fiscal já existe e é orçado. "
        "A questão relevante é outra: **qual é o tamanho do buraco operacional, "
        "o patrimônio ainda resiste e as transferências geram capacidade real?** "
        "Empresas com resultado negativo E patrimônio líquido negativo representam "
        "o risco mais grave — o custo fiscal acumulado já superou o capital original."
    )

    df_dre_dep = df_dre[df_dre["dependencia"] == "Dependente"].copy()
    df_bal_dep = df_bal[df_bal["dependencia"] == "Dependente"].copy()
    df_fc_dep  = df_fc[df_fc["dependencia"]  == "Dependente"].copy()

    if df_dre_dep.empty:
        st.info("Nenhuma empresa dependente no filtro atual.")
    else:
        periodos_dep = sorted(df_dre_dep["periodo_label"].unique(),
            key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
        periodo_dep = st.selectbox(
            "Período de referência:", periodos_dep, key="sust_dep_periodo")

        def pegar_dep(df_src, cod):
            r = df_src[(df_src["rubrica"]==cod) &
                       (df_src["periodo_label"]==periodo_dep)]
            return r.groupby("sigla_empresa")["valor"].sum()

        s_larf_d = pegar_dep(df_dre_dep, RUBRICAS["larf"])
        s_lle_d  = pegar_dep(df_dre_dep, RUBRICAS["lle"])
        s_subv_d = pegar_dep(df_dre_dep, RUBRICAS["subvencao_tesouro"])
        s_fco_d  = pegar_dep(df_fc_dep,  RUBRICAS["fco"])
        s_pl_d   = pegar_dep(df_bal_dep, RUBRICAS["pl"])

        df_dep = pd.DataFrame({
            "LARF": s_larf_d, "LLE": s_lle_d,
            "Subv": s_subv_d, "FCO": s_fco_d, "PL": s_pl_d
        }).dropna(how="all")

        df_dep["LARF_mi"] = (df_dep["LARF"] / 1e6).round(1)
        df_dep["LLE_mi"]  = (df_dep["LLE"]  / 1e6).round(1)
        df_dep["Subv_mi"] = (df_dep["Subv"] / 1e6).round(1)
        df_dep["FCO_mi"]  = (df_dep["FCO"]  / 1e6).round(1)
        df_dep["PL_mi"]   = (df_dep["PL"]   / 1e6).round(1)

        # Painel de Situação
        st.markdown("#### Painel de Situação")

        def sem_lle_d(v):
            if pd.isna(v): return "—"
            return "🔴" if v < 0 else "🟢"

        def sem_pl_d(v):
            if pd.isna(v): return "—"
            return "🔴" if v < 0 else "🟢"

        def sem_fco_d(v):
            if pd.isna(v): return "—"
            return "🔴" if v < 0 else ("🟡" if v < 50 else "🟢")

        df_painel_dep = df_dep.sort_values("LLE_mi").copy()

        df_display_dep = pd.DataFrame({
            "Empresa":           df_painel_dep.index,
            "Res. Op. (R$ Mi)":  df_painel_dep["LARF_mi"].map(
                lambda x: f"{x:,.1f}" if pd.notna(x) else "—"),
            "Res. Líq. (R$ Mi)": df_painel_dep["LLE_mi"].map(
                lambda x: f"{x:,.1f}" if pd.notna(x) else "—"),
            "Subvenção (R$ Mi)": df_painel_dep["Subv_mi"].map(
                lambda x: f"{x:,.1f}" if pd.notna(x) else "—"),
            "FCO (R$ Mi)":       df_painel_dep["FCO_mi"].map(
                lambda x: f"{x:,.1f}" if pd.notna(x) else "—"),
            "PL (R$ Mi)":        df_painel_dep["PL_mi"].map(
                lambda x: f"{x:,.1f}" if pd.notna(x) else "—"),
            "💰 Res.": df_painel_dep["LLE_mi"].apply(sem_lle_d),
            "🏦 PL":   df_painel_dep["PL_mi"].apply(sem_pl_d),
            "💵 FCO":  df_painel_dep["FCO_mi"].apply(sem_fco_d),
        })

        st.dataframe(df_display_dep, use_container_width=True, hide_index=True)
        st.caption(
            "💰 Resultado Líquido: 🔴 negativo · 🟢 positivo  "
            "— 🏦 PL: 🔴 negativo (patrimônio destruído) · 🟢 positivo  "
            "— 💵 FCO: 🔴 negativo · 🟡 < R$50 Mi · 🟢 positivo"
        )

        st.divider()

        # Gráfico 1 — Resultado Operacional vs Líquido
        st.markdown("#### Resultado Operacional vs. Líquido (R$ Mi)")
        st.caption(
            "A diferença entre as duas barras representa o repasse do Tesouro "
            "que sustenta o resultado contábil. Onde a barra vermelha intensa "
            "(operacional) é muito maior que a transparente (líquido), a subvenção "
            "não está cobrindo o deficit."
        )

        df_g1 = df_painel_dep[["LARF_mi","LLE_mi"]].dropna(how="all").copy()
        df_g1_long = pd.melt(
            df_g1.reset_index(),
            id_vars=["sigla_empresa"],
            value_vars=["LARF_mi","LLE_mi"],
            var_name="Tipo", value_name="Valor"
        )
        df_g1_long["Tipo"] = df_g1_long["Tipo"].map({
            "LARF_mi": "Resultado Operacional (LARF)",
            "LLE_mi":  "Resultado Líquido (LLE)"
        })
        ordem_g1 = df_g1.sort_values("LARF_mi").index.tolist()

        fig_g1 = px.bar(
            df_g1_long, x="Valor", y="sigla_empresa",
            color="Tipo", barmode="overlay", orientation="h",
            title=f"Resultado Operacional vs. Líquido — {periodo_dep} (R$ Mi)",
            labels={"Valor":"R$ Mi","sigla_empresa":"","Tipo":""},
            color_discrete_map={
                "Resultado Operacional (LARF)": CORES["vermelho"],
                "Resultado Líquido (LLE)":      "rgba(231,76,60,0.35)",
            },
            template="plotly_white",
            category_orders={"sigla_empresa": ordem_g1}
        )
        fig_g1.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
        fig_g1.update_traces(
            hovertemplate="%{fullData.name}<br>%{y}: R$ %{x:,.1f} Mi<extra></extra>")
        fig_g1.update_layout(
            height=max(400, len(df_g1)*36),
            legend=dict(orientation="h", y=1.08),
            hovermode="y unified"
        )
        st.plotly_chart(fig_g1, use_container_width=True)

        st.divider()

        # Gráfico 2 — PL e FCO
        st.markdown("#### Patrimônio Líquido e FCO (R$ Mi)")
        st.caption(
            "PL negativo: o custo fiscal acumulado já superou o capital original. "
            "FCO negativo: as transferências recebidas não geram caixa operacional real."
        )

        col_b1, col_b2 = st.columns(2)

        with col_b1:
            df_pl_g = df_painel_dep[["PL_mi"]].dropna().sort_values("PL_mi")
            fig_pl = go.Figure()
            fig_pl.add_trace(go.Bar(
                x=df_pl_g["PL_mi"], y=df_pl_g.index,
                orientation="h",
                marker_color=[CORES["vermelho"] if v < 0 else CORES["azul_ifi"]
                              for v in df_pl_g["PL_mi"]],
                hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>",
                showlegend=False
            ))
            fig_pl.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
            fig_pl.update_layout(
                title=f"Patrimônio Líquido — {periodo_dep}",
                xaxis_title="R$ Mi", yaxis_title="",
                template="plotly_white",
                height=max(380, len(df_pl_g)*30)
            )
            st.plotly_chart(fig_pl, use_container_width=True)

        with col_b2:
            df_fco_g = df_painel_dep[["FCO_mi"]].dropna().sort_values("FCO_mi")
            fig_fco_d = go.Figure()
            fig_fco_d.add_trace(go.Bar(
                x=df_fco_g["FCO_mi"], y=df_fco_g.index,
                orientation="h",
                marker_color=[CORES["vermelho"] if v < 0 else CORES["verde"]
                              for v in df_fco_g["FCO_mi"]],
                hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>",
                showlegend=False
            ))
            fig_fco_d.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
            fig_fco_d.update_layout(
                title=f"FCO Acumulado — {periodo_dep}",
                xaxis_title="R$ Mi", yaxis_title="",
                template="plotly_white",
                height=max(380, len(df_fco_g)*30)
            )
            st.plotly_chart(fig_fco_d, use_container_width=True)

        st.divider()
        botoes_download(
            df_dep.reset_index(),
            "estatais2025_sustentabilidade_dependentes",
            "Dependentes"
        )


# ==============================================================================
# ABA — ANÁLISE TCU
# ==============================================================================
with tab_tcu:
    st.markdown("### 🔍 Análise TCU — Acórdão 1196/2026 (dados trimestrais)")

    st.info(
        "Replicação dos indicadores do **Acórdão TCU 1196/2026** "
        "(TC 014.984/2025-3, rel. Min. Benjamin Zymler, sessão 13/05/2026).",
        icon="📋"
    )

    # BLOCO 1 — LARF vs LLE
    st.markdown("#### 1. LARF vs LLE — Sustentabilidade Operacional")
    st.caption(
        "**LARF** = Lucro Antes do Resultado Financeiro. "
        "**LLE** = Lucro Líquido do Exercício. "
        "LLE > 0 com LARF < 0 indica lucro sustentado por receita financeira."
    )

    df_larf = pegar_por_rubrica(df_dre, RUBRICAS["larf"])
    df_lle  = pegar_por_rubrica(df_dre, RUBRICAS["lle"])

    if not df_larf.empty and not df_lle.empty:
        periodos_larf = sorted(df_larf["periodo_label"].unique(),
            key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)

        col_t1, col_t2 = st.columns([2,2])
        with col_t1:
            periodo_larf = st.selectbox("Período:", periodos_larf, key="tcu25_larf_periodo")
        with col_t2:
            empresas_larf = sorted(set(df_larf["sigla_empresa"]) | set(df_lle["sigla_empresa"]))
            emp_def = [e for e in ["EMGEPRON","INFRAERO","ECT","CMB","ENBPAR"] if e in empresas_larf]
            emp_larf = st.multiselect("Empresas:", empresas_larf,
                default=emp_def or empresas_larf[:5], key="tcu25_larf_emp")

        if emp_larf:
            df_l = df_larf[(df_larf["periodo_label"]==periodo_larf) &
                           (df_larf["sigla_empresa"].isin(emp_larf))].rename(columns={"valor":"larf"})
            df_ll = df_lle[(df_lle["periodo_label"]==periodo_larf) &
                           (df_lle["sigla_empresa"].isin(emp_larf))].rename(columns={"valor":"lle"})
            df_comp = pd.merge(df_l[["sigla_empresa","larf"]],
                               df_ll[["sigla_empresa","lle"]],
                               on="sigla_empresa", how="outer").fillna(0)
            df_comp["larf_mi"] = df_comp["larf"]/1e6
            df_comp["lle_mi"]  = df_comp["lle"]/1e6
            df_comp["pct_rf"] = df_comp.apply(
                lambda r: ((r["lle_mi"]-r["larf_mi"])/r["lle_mi"]*100)
                          if r["lle_mi"]!=0 else None, axis=1)
            df_comp = df_comp.sort_values("lle_mi", ascending=True)

            col_g1, col_g2 = st.columns([3,2])
            with col_g1:
                fig_larf = go.Figure()
                fig_larf.add_trace(go.Bar(
                    name="LARF (Operacional)", x=df_comp["larf_mi"], y=df_comp["sigla_empresa"],
                    orientation="h",
                    marker_color=[CORES["verde"] if v>=0 else CORES["vermelho"] for v in df_comp["larf_mi"]],
                    hovertemplate="%{y} LARF: R$ %{x:,.1f} Mi<extra></extra>"))
                fig_larf.add_trace(go.Bar(
                    name="LLE", x=df_comp["lle_mi"], y=df_comp["sigla_empresa"],
                    orientation="h",
                    marker_color=["rgba(39,174,96,0.35)" if v>=0 else "rgba(192,57,43,0.35)"
                                  for v in df_comp["lle_mi"]],
                    hovertemplate="%{y} LLE: R$ %{x:,.1f} Mi<extra></extra>"))
                fig_larf.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
                fig_larf.update_layout(
                    title=f"LARF vs LLE — {periodo_larf} (R$ Mi)",
                    barmode="overlay", xaxis_title="R$ Mi", yaxis_title="",
                    template="plotly_white", height=max(380, len(df_comp)*36),
                    legend=dict(orientation="h", y=1.1), hovermode="y unified")
                st.plotly_chart(fig_larf, use_container_width=True)

            with col_g2:
                st.caption("**% do LLE via Resultado Financeiro**")
                df_tab1 = df_comp[["sigla_empresa","larf_mi","lle_mi","pct_rf"]].copy()
                df_tab1 = df_tab1.sort_values("pct_rf", ascending=False, na_position="last")
                df_tab1.columns = ["Empresa","LARF (R$ Mi)","LLE (R$ Mi)","% RF no LLE"]
                df_tab1["LARF (R$ Mi)"] = df_tab1["LARF (R$ Mi)"].map(fmt1)
                df_tab1["LLE (R$ Mi)"]  = df_tab1["LLE (R$ Mi)"].map(fmt1)
                df_tab1["% RF no LLE"]  = df_tab1["% RF no LLE"].map(
                    lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
                st.dataframe(df_tab1, use_container_width=True, hide_index=True,
                             height=min(450, (len(df_tab1)+1)*38))

            criticos = df_comp[(df_comp["larf_mi"]<0) & (df_comp["lle_mi"]>0)]["sigla_empresa"].tolist()
            if criticos:
                st.warning(f"⚠️ Dependência de receita financeira: {', '.join(criticos)} "
                           f"— LLE positivo, LARF negativo em {periodo_larf}.")

        st.divider()

    # BLOCO 2 — RF / Receita Líquida
    st.markdown("#### 2. Receita Financeira / Receita Líquida (%)")

    df_rf2  = pegar_por_rubrica(df_dre, RUBRICAS["receita_fin"])
    df_rliq = pegar_por_rubrica(df_dre, RUBRICAS["receita_liquida"])

    if not df_rf2.empty and not df_rliq.empty:
        periodos_rf = sorted(df_rf2["periodo_label"].unique(),
            key=lambda x: (int(x.split("-T")[0]), int(x.split("-T")[1])), reverse=True)
        periodo_rf = st.selectbox("Período:", periodos_rf, key="tcu25_rf_periodo")

        df_rf_p  = df_rf2[df_rf2["periodo_label"]==periodo_rf].rename(columns={"valor":"rec_fin"})
        df_rl_p  = df_rliq[df_rliq["periodo_label"]==periodo_rf].rename(columns={"valor":"receita_liq"})
        df_ratio = pd.merge(df_rf_p[["sigla_empresa","rec_fin"]],
                            df_rl_p[["sigla_empresa","receita_liq"]],
                            on="sigla_empresa", how="inner")
        df_ratio = df_ratio[df_ratio["receita_liq"]>0].copy()
        df_ratio["pct"] = (df_ratio["rec_fin"]/df_ratio["receita_liq"]*100).round(1)
        df_ratio = df_ratio.sort_values("pct", ascending=True)

        if not df_ratio.empty:
            col_g1, col_g2 = st.columns([3,2])
            with col_g1:
                fig_rf = go.Figure()
                fig_rf.add_trace(go.Bar(
                    x=df_ratio["pct"], y=df_ratio["sigla_empresa"], orientation="h",
                    marker_color=[CORES["vermelho"] if v>30 else
                                  CORES["laranja"] if v>15 else CORES["verde"]
                                  for v in df_ratio["pct"]],
                    hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
                fig_rf.add_vline(x=36, line_dash="dot", line_color="red",
                    annotation_text="Média 3T2025 (TCU: 36%)", annotation_position="top right")
                fig_rf.update_layout(
                    title=f"Rec. Financeira / Rec. Líquida — {periodo_rf} (%)",
                    xaxis_title="% da Receita Líquida", xaxis_ticksuffix="%",
                    template="plotly_white", height=max(400, len(df_ratio)*22))
                st.plotly_chart(fig_rf, use_container_width=True)

            with col_g2:
                st.caption(f"**Quadro 3 — estilo TCU ({periodo_rf})**")
                df_tab2 = (df_ratio[["sigla_empresa","rec_fin","receita_liq","pct"]]
                           .assign(rfm=lambda x: x["rec_fin"]/1e6, rlm=lambda x: x["receita_liq"]/1e6)
                           .sort_values("pct", ascending=False)
                           [["sigla_empresa","rfm","rlm","pct"]])
                total = pd.DataFrame([{"sigla_empresa":"TOTAL",
                    "rfm": df_tab2["rfm"].sum(),
                    "rlm": df_tab2["rlm"].sum(),
                    "pct": round(df_tab2["rfm"].sum()/df_tab2["rlm"].sum()*100,1)
                          if df_tab2["rlm"].sum()>0 else None}])
                df_tab2 = pd.concat([df_tab2, total], ignore_index=True)
                df_tab2.columns = ["Empresa","Rec. Fin. (R$ Mi)","Rec. Líq. (R$ Mi)","%"]
                df_tab2["Rec. Fin. (R$ Mi)"] = df_tab2["Rec. Fin. (R$ Mi)"].map(fmt1)
                df_tab2["Rec. Líq. (R$ Mi)"] = df_tab2["Rec. Líq. (R$ Mi)"].map(fmt1)
                df_tab2["%"] = df_tab2["%"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
                def hl_total(row):
                    return ["font-weight:bold;background-color:#f0f2f6"]*len(row) \
                           if row["Empresa"]=="TOTAL" else [""]*len(row)
                st.dataframe(df_tab2.style.apply(hl_total, axis=1),
                    use_container_width=True, hide_index=True,
                    height=min(450, (len(df_tab2)+1)*38))

        st.markdown("##### Evolução trimestral")
        emps_evol = sorted(df_rf2["sigla_empresa"].unique())
        emp_evol_def = [e for e in ["EMGEPRON","ENBPAR","INFRAERO"] if e in emps_evol]
        emp_evol = st.multiselect("Empresas:", emps_evol,
            default=emp_evol_def or emps_evol[:3], key="tcu25_rf_evol_emp")
        if emp_evol:
            df_evol = pd.merge(
                df_rf2[df_rf2["sigla_empresa"].isin(emp_evol)]
                      [["periodo_label","sigla_empresa","valor","exercicio","trimestre"]]
                      .rename(columns={"valor":"rec_fin"}),
                df_rliq[["periodo_label","sigla_empresa","valor"]].rename(columns={"valor":"receita_liq"}),
                on=["periodo_label","sigla_empresa"], how="inner")
            df_evol = df_evol[df_evol["receita_liq"]>0].copy()
            df_evol["pct"] = (df_evol["rec_fin"]/df_evol["receita_liq"]*100).round(1)
            df_evol = df_evol.sort_values(["exercicio","trimestre"])
            fig_evol = px.line(df_evol, x="periodo_label", y="pct",
                color="sigla_empresa", markers=True,
                title="Evolução Trimestral — RF / Receita Líquida (%)",
                labels={"pct":"%","periodo_label":"Período","sigla_empresa":""},
                template="plotly_white")
            fig_evol.update_traces(hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>")
            fig_evol.update_layout(height=380, legend=dict(orientation="h", y=1.1),
                                   hovermode="x unified")
            st.plotly_chart(fig_evol, use_container_width=True)

    st.divider()

    # BLOCO 3 — FCO e Saldo de Caixa
    st.markdown("#### 3. Fluxo de Caixa Operacional e Saldo de Caixa")
    st.info(
        "FCO e saldo de caixa vêm **diretos** das demonstrações trimestrais "
        "(rubricas 319900000 e 390000000). Este bloco replica os gráficos "
        "individuais do Apêndice II do TCU (ex.: ECT, INFRAERO) — não o "
        "Gráfico 4 agregado (OI + LLE + Dividendos), ainda pendente.",
        icon="📌"
    )

    df_fco_25   = pegar_por_rubrica(df_fc, RUBRICAS["fco"])
    df_caixa_25 = pegar_por_rubrica(df_fc, RUBRICAS["caixa_final"])

    if not df_fco_25.empty and not df_caixa_25.empty:
        emps_fco = sorted(
            set(df_fco_25["sigla_empresa"]) & set(df_caixa_25["sigla_empresa"]))
        emp_fco_def = [e for e in ["ECT","EMGEPRON","INFRAERO","CMB","CODERN"] if e in emps_fco]
        emp_fco = st.multiselect("Empresas:", emps_fco,
            default=emp_fco_def or emps_fco[:4], key="tcu25_fco_emp")

        if emp_fco:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                df_fco_f = (
                    df_fco_25[df_fco_25["sigla_empresa"].isin(emp_fco)]
                    .assign(valor_mi=lambda x: x["valor_trimestre"]/1e6)
                    .sort_values(["exercicio","trimestre"])
                )
                n_nulos = df_fco_f["valor_mi"].isna().sum()
                fig_fco = px.line(df_fco_f.dropna(subset=["valor_mi"]),
                    x="periodo_label", y="valor_mi", color="sigla_empresa", markers=True,
                    title="FCO — Trimestre Isolado (R$ Mi)",
                    labels={"valor_mi":"R$ Mi","periodo_label":"Período","sigla_empresa":""},
                    template="plotly_white")
                fig_fco.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
                fig_fco.update_traces(hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
                fig_fco.update_layout(height=380, legend=dict(orientation="h", y=1.1),
                                      hovermode="x unified")
                st.plotly_chart(fig_fco, use_container_width=True)
                if n_nulos > 0:
                    st.caption(f"ℹ️ {n_nulos} ponto(s) omitido(s) — trimestre anterior ausente.")

            with col_f2:
                df_cx_f = (
                    df_caixa_25[df_caixa_25["sigla_empresa"].isin(emp_fco)]
                    .assign(valor_mi=lambda x: x["valor"]/1e6)
                    .sort_values(["exercicio","trimestre"])
                )
                fig_cx = px.line(df_cx_f, x="periodo_label", y="valor_mi",
                    color="sigla_empresa", markers=True,
                    title="Saldo de Caixa Final (R$ Mi)",
                    labels={"valor_mi":"R$ Mi","periodo_label":"Período","sigla_empresa":""},
                    template="plotly_white")
                fig_cx.update_traces(hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
                fig_cx.update_layout(height=380, legend=dict(orientation="h", y=1.1),
                                     hovermode="x unified")
                st.plotly_chart(fig_cx, use_container_width=True)
    else:
        st.info("Dados de FCO/Caixa não disponíveis para os filtros atuais.")

    st.divider()
    with st.expander("ℹ️ Nota metodológica"):
        st.markdown("""
**Referência:** Acórdão TCU nº 1196/2026 – Plenário (TC 014.984/2025-3).

**Acumulado vs. Trimestre Isolado:** DRE e Fluxo de Caixa são acumulados no ano.
`valor` = acumulado (usado nos Blocos 1 e 2). `valor_trimestre` = isolado (usado no FCO do Bloco 3).
Balanço = saldo pontual, sem acumulação.

**Pendente:** Gráfico 4 (OI + LLE + Dividendos aggregado), BAS, DVA.

**Fonte:** SEST/MGI via LAI (extração SIEST, 02/06/2026).
        """)

    botoes_download(df_base, "estatais_2025_analise_tcu", "TCU_2025")

# ==============================================================================
# ABA — EXPLORAR E BAIXAR
# ==============================================================================
with tab_exp:
    st.markdown("### Explorar e Baixar")
    st.caption("Baixe o plano de contas completo para o filtro atual da barra lateral.")

    plano_sel = st.selectbox("Plano de Contas:",
        sorted(df_base["nome_tipo_plano_contas"].unique()), key="exp25_plano")
    df_exp = df_base[df_base["nome_tipo_plano_contas"]==plano_sel].copy()

    if not df_exp.empty:
        st.info(f"**{len(df_exp):,}** linhas · **{df_exp['sigla_empresa'].nunique()}** empresas · "
                f"**{df_exp['trimestre'].nunique()}** trimestre(s)")

        rubrica_graf = st.selectbox("Rubrica para visualizar:",
            sorted(df_exp["rubrica_nome"].dropna().unique()), key="exp25_rub")
        df_graf = (
            df_exp[df_exp["rubrica_nome"]==rubrica_graf]
            .assign(valor_mi=lambda x: x["valor"]/1e6)
            .sort_values(["exercicio","trimestre"])
        )
        if not df_graf.empty:
            fig = px.line(df_graf, x="periodo_label", y="valor_mi",
                color="sigla_empresa", markers=True, title=rubrica_graf,
                labels={"valor_mi":"R$ Mi","periodo_label":"Período","sigla_empresa":"Empresa"},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
            fig.update_layout(height=440, hovermode="x unified",
                legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("⚠️ DRE/FC/DVA: acumulado no ano. Balanço: saldo pontual.")

        st.divider()
        botoes_download(df_exp, f"estatais2025_{plano_sel.lower().replace(' ','_')}", plano_sel)

        df_tab_exp = df_exp[["exercicio","trimestre","sigla_empresa","dependencia","setor",
                             "nome_tipo_plano_contas","rubrica","rubrica_nome",
                             "valor","valor_trimestre"]].copy()
        df_tab_exp["valor"] = df_tab_exp["valor"].map(fmt1)
        df_tab_exp["valor_trimestre"] = df_tab_exp["valor_trimestre"].map(
            lambda x: fmt1(x) if pd.notna(x) else "—")
        st.dataframe(df_tab_exp, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("Sem dados para o filtro atual.")