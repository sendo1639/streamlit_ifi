"""
P�gina: Monitor de Empresas Estatais (SEST/MGI)
Fonte: Demonstrações financeiras históricas obtidas
Período: 2008–2024 (dados anuais)

Metodologia DVA/DRE: Pellegrini (2019) — Ipea
"""

import io
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from interface_utils import configurar_interface_ifi

st.set_page_config(
    page_title="Estatais | IFI",
    page_icon="🏛️",
    layout="wide"
)
configurar_interface_ifi()

try:
    from query_engine import carregar_dados_estatais, carregar_dados_siga_brasil, converter_para_csv
except ImportError:
    import sys, os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from query_engine import carregar_dados_estatais, carregar_dados_siga_brasil, converter_para_csv

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

# Códigos de rubrica — fonte única de verdade para seleção de indicadores
# Evita problemas de variação de texto entre empresas/anos
RUBRICAS = {
    # DRE
    "resultado_liquido":           500000,
    # Balanço
    "ativo_total":                 199999,
    "patrimonio_liquido":          250000,
    "passivo_total":               299999,
    # DVA (apenas rubricas PAI — evita dupla contagem com subcontas)
    "dva_va_distribuir":           610000,
    "dva_pessoal":                 630000,
    "dva_impostos":                640000,
    "dva_capital_terceiros":       650000,
    "dva_capital_proprio":         660000,
    "dva_lucros_retidos":          670000,
    # Fluxo de Caixa
    "fc_dividendos_uniao":         400411,
    "fc_jcp_uniao":                400421,
    "fc_afac_uniao":               400600,
    "fc_aporte_capital_uniao":     400700,
    "fc_subvencao":                400800,
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
    Retorna valores de uma rubrica específica por empresa e ano.
    Usa código numérico — robusto contra variações de texto.
    """
    return (
        df[df["rubrica"] == codigo]
        .groupby(["exercicio", "sigla_empresa", "dependencia", "setor"])["valor"]
        .sum().reset_index()
    )

def fmt1(v):
    """Formata número com 1 casa decimal e separador de milhar."""
    try:
        return f"{float(v):,.1f}"
    except Exception:
        return str(v)

# ==============================================================================
# CARREGAMENTO
# ==============================================================================
st.title("🏛️ Monitor de Empresas Estatais Federais")
st.markdown("Demonstrações financeiras consolidadas — SEST/MGI · 2008–2024 · Dados anuais")

with st.spinner("Carregando dados das estatais..."):
    df_raw = carregar_dados_estatais()

if df_raw is None or df_raw.empty:
    st.error("Não foi possível carregar os dados. Verifique se o ETL já foi executado.")
    st.stop()

# Garante rubrica numérica
df_raw["rubrica"] = pd.to_numeric(df_raw["rubrica"], errors="coerce")

# ==============================================================================
# SIDEBAR — FILTROS GLOBAIS
# ==============================================================================
st.sidebar.header("🔍 Filtros")

dep_opcoes = ["Todas", "Dependente", "Não dependente"]
escolha_dep = st.sidebar.radio("Dependência:", dep_opcoes)

setores_disp = sorted(df_raw["setor"].unique())
escolha_setores = st.sidebar.multiselect("Setor:", setores_disp, default=setores_disp)

ano_min = int(df_raw["exercicio"].min())
ano_max = int(df_raw["exercicio"].max())
periodo = st.sidebar.slider("Período:", ano_min, ano_max, (ano_min, ano_max))

# Para filtro de dependência, usa a classificação MAIS RECENTE da empresa
# (evita problema de empresas que mudaram de categoria ao longo dos anos)
dep_atual = (
    df_raw.sort_values("exercicio", ascending=False)
          .drop_duplicates("sigla_empresa")[["sigla_empresa", "dependencia"]]
          .set_index("sigla_empresa")["dependencia"]
)

df_base = df_raw.copy()
if escolha_dep != "Todas":
    empresas_dep = dep_atual[dep_atual == escolha_dep].index
    df_base = df_base[df_base["sigla_empresa"].isin(empresas_dep)]
if escolha_setores:
    df_base = df_base[df_base["setor"].isin(escolha_setores)]
df_base = df_base[df_base["exercicio"].between(periodo[0], periodo[1])]

empresas_disp = sorted(df_base["sigla_empresa"].unique())
escolha_empresas = st.sidebar.multiselect(
    "Empresas (vazio = todas):", empresas_disp,
    help="Deixe vazio para incluir todas."
)
if escolha_empresas:
    df_base = df_base[df_base["sigla_empresa"].isin(escolha_empresas)]

st.sidebar.divider()
st.sidebar.caption(
    f"**{df_base['sigla_empresa'].nunique()} empresas** · "
    f"**{periodo[0]}–{periodo[1]}**"
)
st.sidebar.info(
    "**Fonte:** SEST/MGI\n\n"
)

# Subsets por plano
df_bal = df_base[df_base["nome_tipo_plano_contas"] == "Balanço"]
df_dre = df_base[df_base["nome_tipo_plano_contas"] == "DRE"]
df_dva = df_base[df_base["nome_tipo_plano_contas"] == "DVA"]
df_fc  = df_base[df_base["nome_tipo_plano_contas"] == "Fluxo de Caixa"]

# ==============================================================================
# ABAS
# ==============================================================================
tab_pan, tab_dre, tab_bal, tab_trs, tab_dva_tab, tab_exp = st.tabs([
    "📊 Panorama Geral",
    "📈 Desempenho (DRE)",
    "⚖️ Balanço",
    "🤝 Relações com Tesouro",
    "💰 DVA",
    "🔎 Explorar e Baixar",
])

# ==============================================================================
# ABA 1 — PANORAMA GERAL
# ==============================================================================
with tab_pan:
    st.markdown("### Visão Geral")

    c1, c2, c3, c4 = st.columns(4)
    n_emp  = df_base["sigla_empresa"].nunique()
    n_dep  = len(dep_atual[dep_atual == "Dependente"])
    n_ndep = len(dep_atual[dep_atual == "Não dependente"])
    c1.metric("Empresas no filtro", n_emp)
    c2.metric("Dependentes (total)", n_dep)
    c3.metric("Não dependentes (total)", n_ndep)
    c4.metric("Anos cobertos", df_base["exercicio"].nunique())

    st.divider()

    col_a, col_b = st.columns(2)

    df_rl  = pegar_por_rubrica(df_dre, RUBRICAS["resultado_liquido"])
    df_pl  = pegar_por_rubrica(df_bal, RUBRICAS["patrimonio_liquido"])

    with col_a:
        if not df_rl.empty:
            df_agg = (df_rl.groupby(["exercicio", "dependencia"])["valor"]
                          .sum().reset_index()
                          .assign(valor_mi=lambda x: x["valor"]/1e6))
            fig = px.bar(df_agg, x="exercicio", y="valor_mi",
                color="dependencia", barmode="group",
                title="Resultado Líquido Agregado (R$ Milhões)",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano","dependencia":""},
                color_discrete_map={
                    "Dependente":    CORES["vermelho"],
                    "Não dependente": CORES["azul_ifi"]},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig.update_layout(height=370, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        if not df_pl.empty:
            df_pl_agg = (df_pl.groupby("exercicio")["valor"]
                              .sum().reset_index()
                              .assign(valor_mi=lambda x: x["valor"]/1e6))
            fig2 = px.line(df_pl_agg, x="exercicio", y="valor_mi",
                title="Patrimônio Líquido Agregado (R$ Milhões)",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano"},
                template="plotly_white", markers=True)
            fig2.update_traces(
                line_color=CORES["azul_ifi"], line_width=2.5,
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig2.update_layout(height=370)
            st.plotly_chart(fig2, use_container_width=True)

    # Empresas com PL negativo
    st.divider()
    st.markdown("##### Empresas com Patrimônio Líquido Negativo")
    if not df_pl.empty:
        pl_neg = df_pl[df_pl["valor"] < 0]
        if not pl_neg.empty:
            df_cnt = (pl_neg.groupby("exercicio")["sigla_empresa"]
                            .count().reset_index()
                            .rename(columns={"sigla_empresa":"qtd"}))
            col1, col2 = st.columns([2,1])
            with col1:
                fig3 = px.bar(df_cnt, x="exercicio", y="qtd",
                    title="Nº de Empresas com PL Negativo",
                    labels={"qtd":"Empresas","exercicio":"Ano"},
                    template="plotly_white",
                    color_discrete_sequence=[CORES["vermelho"]])
                fig3.update_layout(height=300)
                st.plotly_chart(fig3, use_container_width=True)
            with col2:
                ano_ref = pl_neg["exercicio"].max()
                st.caption(f"**Com PL negativo em {ano_ref}:**")
                for _, r in pl_neg[pl_neg["exercicio"]==ano_ref].iterrows():
                    st.markdown(f"- **{r['sigla_empresa']}** (R$ {r['valor']/1e6:,.1f} Mi)")

    # Tabela cadastral
    st.divider()
    st.markdown("##### Empresas no filtro atual")

    # Info básica por empresa (último ano disponível)
    resumo = (
        df_base.sort_values("exercicio", ascending=False)
               .drop_duplicates("sigla_empresa")
               [["sigla_empresa","nome_empresa","dependencia","setor"]]
               .sort_values("sigla_empresa")
               .reset_index(drop=True)
    )
    resumo.columns = ["Sigla","Nome","Dependência","Setor"]
    st.dataframe(resumo, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA 2 — DESEMPENHO (DRE)
# ==============================================================================
with tab_dre:
    st.markdown("### Demonstração do Resultado e Grau de Dependência")

    # --- Grau de Dependência (Pellegrini) ---
    with st.spinner("Carregando dados SIGA Brasil..."):
        df_siga = carregar_dados_siga_brasil()

    if not df_siga.empty:
        st.markdown("#### Grau de Dependência do Governo Federal")

        anos_siga = sorted(df_siga["exercicio"].dropna().unique(), reverse=True)
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            ano_pell = st.selectbox("Ano de referência:", anos_siga, key="pell_ano")

        df_pell = (df_siga[df_siga["exercicio"] == ano_pell]
                   .sort_values("grau_dependencia_pct", ascending=False).copy())

        if not df_pell.empty:
            # Média ponderada de despesa por funcionário (denominador = total func × 13)
            tot_pess_r = (df_pell["despesa_pessoal_mi"].fillna(0) * 1e6).sum()
            tot_func   = df_pell["num_funcionarios"].sum(skipna=True)

            # Total
            total_row = pd.DataFrame([{
                "sigla_empresa":             "TOTAL",
                "despesas_totais_mi":         df_pell["despesas_totais_mi"].sum().round(1),
                "recursos_tesouro_mi":        df_pell["recursos_tesouro_mi"].sum().round(1),
                "grau_dependencia_pct":       round(
                    df_pell["recursos_tesouro_mi"].sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_pessoal_correntes_pct": round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_pessoal_correntes_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_investimentos_pct":     round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_investimentos_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "desp_pessoal_por_func_mes_rs": round(
                    tot_pess_r / (tot_func * 13), 2)
                    if pd.notna(tot_func) and tot_func > 0 else None,
            }])
            colunas_tab = [
                "sigla_empresa", "despesas_totais_mi", "recursos_tesouro_mi",
                "grau_dependencia_pct", "comp_pessoal_correntes_pct",
                "comp_investimentos_pct", "desp_pessoal_por_func_mes_rs",
            ]
            df_tab = pd.concat(
                [df_pell[[c for c in colunas_tab if c in df_pell.columns]],
                 total_row[[c for c in colunas_tab if c in total_row.columns]]],
                ignore_index=True
            )
            df_tab.columns = [
                "Denominação", "Despesas (R$ Mi)", "Rec. Tesouro (R$ Mi)",
                "Grau Depend. (%)", "Pessoal e Correntes (%)",
                "Invest. e Inversões (%)", "Desp. Pessoal/Func./Mês (R$)",
            ]
            for c in ["Despesas (R$ Mi)", "Rec. Tesouro (R$ Mi)"]:
                df_tab[c] = df_tab[c].map(fmt1)
            for c in ["Grau Depend. (%)", "Pessoal e Correntes (%)",
                      "Invest. e Inversões (%)"]:
                df_tab[c] = df_tab[c].map(
                    lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            df_tab["Desp. Pessoal/Func./Mês (R$)"] = df_tab[
                "Desp. Pessoal/Func./Mês (R$)"].map(
                lambda x: f"R$ {float(x):,.0f}" if pd.notna(x) and x != "—"
                else "—")

            def highlight_total(row):
                if row["Denominação"] == "TOTAL":
                    return ["font-weight:bold;background-color:#f0f2f6"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_tab.style.apply(highlight_total, axis=1),
                use_container_width=True, hide_index=True,
                height=min(650, (len(df_tab)+1)*38)
            )
            with col_s2:
                st.caption(" ")
                st.download_button("📥 CSV",
                    df_pell.to_csv(index=False).encode("utf-8"),
                    f"grau_dependencia_{ano_pell}.csv",
                    use_container_width=True)

        st.divider()

        # Evolução grau de dependência
        st.markdown("#### Evolução do Grau de Dependência (%)")
        emps_siga = sorted(df_siga["sigla_empresa"].unique())
        emp_ev = st.multiselect("Empresas:", emps_siga,
                                default=emps_siga[:5], key="pell_emp")
        if emp_ev:
            df_ev = df_siga[df_siga["sigla_empresa"].isin(emp_ev)]
            fig_ev = px.line(df_ev, x="exercicio", y="grau_dependencia_pct",
                color="sigla_empresa", markers=True,
                title="Grau de Dependência do Governo Federal (%)",
                labels={"grau_dependencia_pct":"% Grau de Dependência",
                        "exercicio":"Ano","sigla_empresa":"Empresa"},
                template="plotly_white")
            fig_ev.update_traces(
                hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>")
            fig_ev.add_hline(y=100, line_dash="dot", line_color="gray",
                annotation_text="100%", annotation_position="right")
            fig_ev.update_layout(height=420, yaxis=dict(range=[0,105],ticksuffix="%"),
                hovermode="x unified", legend=dict(orientation="h",y=1.1))
            st.plotly_chart(fig_ev, use_container_width=True)
        st.divider()

        # --- Bloco C: Despesa de Pessoal por Funcionário por Mês ---
        st.markdown("#### Despesa de Pessoal por Funcionário por Mês")
        st.caption(
            "GND Pessoal ÷ (Nº funcionários × 13). "
            "Divisor 13 = 12 meses + 13º salário, para base mensal real. "
            "Fonte: Quantitativo de Pessoal das Estatais (SEST/MGI, dez/ano)."
        )

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            df_func_ano = (
                df_siga[df_siga["exercicio"] == ano_pell]
                .dropna(subset=["desp_pessoal_por_func_mes_rs"])
                .sort_values("desp_pessoal_por_func_mes_rs", ascending=True)
            )
            if not df_func_ano.empty:
                fig_func = px.bar(
                    df_func_ano,
                    x="desp_pessoal_por_func_mes_rs", y="sigla_empresa",
                    orientation="h",
                    title=f"Ranking — {ano_pell} (R$ / func. / mês)",
                    labels={"desp_pessoal_por_func_mes_rs": "R$",
                            "sigla_empresa": ""},
                    color="desp_pessoal_por_func_mes_rs",
                    color_continuous_scale=["#AED6F1", "#1A5276"],
                    template="plotly_white"
                )
                fig_func.update_traces(
                    hovertemplate="%{y}: R$ %{x:,.0f}<extra></extra>")
                fig_func.update_layout(
                    height=max(380, len(df_func_ano) * 30),
                    coloraxis_showscale=False,
                    xaxis_tickprefix="R$ ", xaxis_tickformat=",."
                )
                st.plotly_chart(fig_func, use_container_width=True)
            else:
                st.info("Dados de funcionários não disponíveis para este ano.")

        with col_c2:
            emps_com_func = [
                e for e in sorted(df_siga["sigla_empresa"].unique())
                if df_siga[df_siga["sigla_empresa"] == e]
                   ["desp_pessoal_por_func_mes_rs"].notna().any()
            ]
            if emps_com_func:
                emp_func = st.selectbox(
                    "Empresa — evolução histórica:",
                    emps_com_func, key="func_empresa"
                )
                df_func_emp = (
                    df_siga[df_siga["sigla_empresa"] == emp_func]
                    .dropna(subset=["desp_pessoal_por_func_mes_rs"])
                    .sort_values("exercicio")
                )
                fig_func_ev = px.line(
                    df_func_emp,
                    x="exercicio", y="desp_pessoal_por_func_mes_rs",
                    markers=True,
                    title=f"{emp_func} — Desp. Pessoal / Func. / Mês (R$)",
                    labels={"desp_pessoal_por_func_mes_rs": "R$",
                            "exercicio": "Ano"},
                    template="plotly_white"
                )
                fig_func_ev.update_traces(
                    line_color=CORES["azul_ifi"],
                    hovertemplate="%{x}: R$ %{y:,.0f}<extra></extra>"
                )
                fig_func_ev.update_layout(
                    height=380,
                    yaxis_tickprefix="R$ ", yaxis_tickformat=",."
                )
                st.plotly_chart(fig_func_ev, use_container_width=True)

    else:
        st.info("⏳ Execute `etl_siga_brasil.py` para popular o Grau de Dependência.")

    st.divider()

    # --- Resultado Líquido (DRE) ---
    st.markdown("#### Resultado Líquido (DRE)")
    df_rl = pegar_por_rubrica(df_dre, RUBRICAS["resultado_liquido"])

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        if not df_rl.empty:
            ano_rl = st.selectbox("Ano:", sorted(df_rl["exercicio"].unique(), reverse=True),
                                  key="dre_ano")
            df_rl_ano = (df_rl[df_rl["exercicio"]==ano_rl]
                         .assign(valor_mi=lambda x: x["valor"]/1e6)
                         .sort_values("valor_mi"))
            fig = px.bar(df_rl_ano, x="valor_mi", y="sigla_empresa",
                orientation="h",
                color="valor_mi",
                color_continuous_scale=["#C0392B","#ECF0F1","#27AE60"],
                color_continuous_midpoint=0,
                title=f"Resultado Líquido — {ano_rl} (R$ Mi)",
                labels={"valor_mi":"R$ Mi","sigla_empresa":""},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>")
            fig.update_layout(height=max(420,len(df_rl_ano)*24),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    with col_d2:
        if not df_rl.empty:
            emp_rl = st.selectbox("Empresa:", sorted(df_rl["sigla_empresa"].unique()),
                                  key="dre_emp")
            df_rl_e = (df_rl[df_rl["sigla_empresa"]==emp_rl]
                       .assign(valor_mi=lambda x: x["valor"]/1e6)
                       .sort_values("exercicio"))
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_rl_e["exercicio"], y=df_rl_e["valor_mi"],
                marker_color=["#27AE60" if v>=0 else "#C0392B"
                              for v in df_rl_e["valor_mi"]],
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>"
            ))
            fig2.update_layout(
                title=f"{emp_rl} — Resultado Líquido (R$ Mi)",
                xaxis_title="Ano", yaxis_title="R$ Mi",
                template="plotly_white", height=380)
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    botoes_download(df_rl.assign(valor_mi=lambda x: x["valor"]/1e6),
                    "estatais_dre_resultado", "Resultado")

# ==============================================================================
# ABA 3 — BALANÇO
# ==============================================================================
with tab_bal:
    st.markdown("### Balanço Patrimonial")

    df_pl  = pegar_por_rubrica(df_bal, RUBRICAS["patrimonio_liquido"])
    df_at  = pegar_por_rubrica(df_bal, RUBRICAS["ativo_total"])

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        if not df_pl.empty:
            ano_bal = st.selectbox("Ano:", sorted(df_pl["exercicio"].unique(), reverse=True),
                                   key="bal_ano")
            df_pl_ano = (df_pl[df_pl["exercicio"]==ano_bal]
                         .assign(valor_mi=lambda x: x["valor"]/1e6)
                         .sort_values("valor_mi"))
            fig = px.bar(df_pl_ano, x="valor_mi", y="sigla_empresa",
                orientation="h",
                color="valor_mi",
                color_continuous_scale=["#C0392B","#ECF0F1","#2874A6"],
                color_continuous_midpoint=0,
                title=f"Patrimônio Líquido — {ano_bal} (R$ Mi)",
                labels={"valor_mi":"R$ Mi","sigla_empresa":""},
                template="plotly_white")
            fig.update_traces(hovertemplate="%{y}: R$ %{x:,.1f} Mi<extra></extra>")
            fig.update_layout(height=max(420,len(df_pl_ano)*24),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    with col_b2:
        if not df_pl.empty:
            emp_bal = st.selectbox("Empresa:", sorted(df_pl["sigla_empresa"].unique()),
                                   key="bal_emp")
            df_pl_e = (df_pl[df_pl["sigla_empresa"]==emp_bal]
                       .assign(valor_mi=lambda x: x["valor"]/1e6)
                       .sort_values("exercicio"))
            fig2 = px.area(df_pl_e, x="exercicio", y="valor_mi",
                title=f"{emp_bal} — Patrimônio Líquido (R$ Mi)",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano"},
                template="plotly_white")
            fig2.update_traces(
                line_color=CORES["azul_ifi"],
                fillcolor="rgba(0,51,102,0.15)",
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

    # ROE
    st.divider()
    st.markdown("##### ROE — Retorno sobre Patrimônio Líquido")
    st.caption("Resultado Líquido ÷ Patrimônio Líquido × 100")

    df_rl = pegar_por_rubrica(df_dre, RUBRICAS["resultado_liquido"])

    if not df_pl.empty and not df_rl.empty:
        df_roe = pd.merge(
            df_rl.rename(columns={"valor":"resultado"}),
            df_pl.rename(columns={"valor":"pl"}),
            on=["exercicio","sigla_empresa"]
        )
        df_roe = df_roe[df_roe["pl"] != 0].copy()
        df_roe["roe"]          = (df_roe["resultado"] / df_roe["pl"] * 100).round(1)
        df_roe["ambos_neg"]    = (df_roe["resultado"] < 0) & (df_roe["pl"] < 0)
        df_roe["resultado_mi"] = df_roe["resultado"] / 1e6
        df_roe["pl_mi"]        = df_roe["pl"] / 1e6

        ano_roe = st.selectbox("Ano:", sorted(df_roe["exercicio"].unique(), reverse=True),
                               key="roe_ano")
        df_roe_ano = df_roe[df_roe["exercicio"]==ano_roe].sort_values("roe")

        # Alerta para casos ambos negativos
        ambos_neg = df_roe_ano[df_roe_ano["ambos_neg"]]
        if not ambos_neg.empty:
            empresas_str = ", ".join(ambos_neg["sigla_empresa"].tolist())
            st.warning(
                f"⚠️ **ROE não interpretável:** {empresas_str} apresentam "
                "resultado líquido E patrimônio líquido negativos em {ano_roe}."
            )

        # Gráfico ROE — empresas com ambos negativos em cor distinta
        df_roe_ano["cor"] = df_roe_ano.apply(
            lambda r: CORES["cinza"] if r["ambos_neg"] else
                      (CORES["verde"] if r["roe"] >= 0 else CORES["vermelho"]),
            axis=1
        )
        fig3 = go.Figure()
        for _, r in df_roe_ano.iterrows():
            fig3.add_trace(go.Bar(
                x=[r["roe"]], y=[r["sigla_empresa"]],
                orientation="h",
                marker_color=r["cor"],
                name=r["sigla_empresa"],
                showlegend=False,
                hovertemplate=(
                    f"<b>{r['sigla_empresa']}</b><br>"
                    f"ROE: {r['roe']:.1f}%<br>"
                    f"Resultado: R$ {r['resultado_mi']:,.1f} Mi<br>"
                    f"PL: R$ {r['pl_mi']:,.1f} Mi"
                    + (" ⚠️ Ambos negativos" if r["ambos_neg"] else "")
                    + "<extra></extra>"
                )
            ))
        fig3.update_layout(
            title=f"ROE por Empresa — {ano_roe} (%)",
            xaxis_title="ROE (%)", yaxis_title="",
            template="plotly_white",
            height=max(420,len(df_roe_ano)*24)
        )
        fig3.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig3, use_container_width=True)
        st.caption("🔘 Cinza = ROE não interpretável (resultado e PL ambos negativos)")

        # Métricas alternativas para empresas com ambos negativos
        if not ambos_neg.empty:
            st.markdown("##### Métricas alternativas para empresas com PL negativo")

            # Dívida Bruta / Ativo Total
            df_passivo = pegar_por_rubrica(df_bal, RUBRICAS["passivo_total"])
            df_at2     = pegar_por_rubrica(df_bal, RUBRICAS["ativo_total"])

            empresas_neg = ambos_neg["sigla_empresa"].tolist()
            col_m1, col_m2 = st.columns(2)

            with col_m1:
                st.caption("**Passivo Total / Ativo Total (Alavancagem)**")
                df_alav = pd.merge(
                    df_passivo[df_passivo["sigla_empresa"].isin(empresas_neg)]
                              .rename(columns={"valor":"passivo"}),
                    df_at2[df_at2["sigla_empresa"].isin(empresas_neg)]
                           .rename(columns={"valor":"ativo"}),
                    on=["exercicio","sigla_empresa"]
                )
                df_alav = df_alav[df_alav["ativo"] != 0].copy()
                df_alav["alavancagem"] = (df_alav["passivo"] / df_alav["ativo"] * 100).round(1)
                if not df_alav.empty:
                    fig_alav = px.line(df_alav, x="exercicio", y="alavancagem",
                        color="sigla_empresa", markers=True,
                        labels={"alavancagem":"Passivo/Ativo (%)","exercicio":"Ano"},
                        template="plotly_white")
                    fig_alav.update_traces(
                        hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>")
                    fig_alav.add_hline(y=100, line_dash="dot", line_color="red",
                        annotation_text="100% (passivo > ativo)",
                        annotation_position="right")
                    fig_alav.update_layout(height=320,
                        legend=dict(orientation="h",y=1.1))
                    st.plotly_chart(fig_alav, use_container_width=True)

# ==============================================================================
# ABA 4 — RELAÇÕES COM TESOURO
# ==============================================================================
# ==============================================================================
# TRECHO ATUALIZADO: ABA "RELAÇÕES COM TESOURO"
# Substitui o bloco "with tab_trs:" no 04_Estatais.py
# ==============================================================================

# --- ABA 4 — RELAÇÕES COM TESOURO ---
with tab_trs:
    st.markdown("### Relações Financeiras com o Tesouro Nacional")


    # ----- Códigos por família (dependentes + não dependentes) -----
    CODIGOS = {
        "Aportes de Capital":       [400700, 316000],
        "AFAC Recebido":            [400600, 315000],
        "Subvenção para Custeio":   [400800],            # só dependentes
        "Dividendos pagos à União": [400411, 311110],
        "JCP pago à União":         [400421, 311210],
    }

    def buscar_multiplos_codigos(df_fc, codigos):
        """Busca em múltiplos códigos de rubrica e consolida."""
        df = df_fc[df_fc["rubrica"].isin(codigos)]
        if df.empty:
            return pd.DataFrame()
        return (
            df.groupby(["exercicio", "sigla_empresa", "dependencia", "setor"])["valor"]
              .sum().reset_index()
        )

    # Coleta dados por categoria
    dados = {
        nome: buscar_multiplos_codigos(df_fc, cods)
        for nome, cods in CODIGOS.items()
    }

    # Normaliza sinais — dividendos/JCP vêm negativos no FC
    # Convertemos para positivo na exibição (entrada para a União)
    for nome in ["Dividendos pagos à União", "JCP pago à União"]:
        if not dados[nome].empty:
            dados[nome]["valor"] = dados[nome]["valor"].abs()

    def agg_anual(df, nome):
        if df.empty:
            return pd.DataFrame()
        return (df.groupby("exercicio")["valor"].sum().reset_index()
                  .assign(tipo=nome, valor_mi=lambda x: x["valor"] / 1e6))

    df_trs = pd.concat(
        [agg_anual(dados[nome], nome) for nome in CODIGOS.keys()],
        ignore_index=True
    ).dropna()

    if not df_trs.empty:
        fig = px.bar(df_trs, x="exercicio", y="valor_mi", color="tipo",
            title="Fluxo Financeiro Entre União e Estatais (R$ Milhões)",
            labels={"valor_mi":"R$ Mi","exercicio":"Ano","tipo":""},
            barmode="group", template="plotly_white",
            color_discrete_map={
                "Aportes de Capital":       CORES["vermelho"],
                "AFAC Recebido":            "#E74C3C",
                "Subvenção para Custeio":   CORES["laranja"],
                "Dividendos pagos à União": CORES["verde"],
                "JCP pago à União":         "#1E8449",
            })
        fig.update_traces(
            hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
        fig.update_layout(height=420, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    # ----- Saldo líquido -----
    st.divider()
    st.markdown("##### Saldo Líquido: União → Estatais")
    st.caption("Positivo = Tesouro transferiu mais. Negativo = Estatais devolveram mais.")

    anos_todos = sorted(set(
        e for nome in CODIGOS.keys() if not dados[nome].empty
        for e in dados[nome]["exercicio"].unique()
    ))

    if anos_todos:
        def tot(df):
            return df.groupby("exercicio")["valor"].sum() if not df.empty else pd.Series(dtype=float)

        df_saldo = pd.DataFrame(index=anos_todos)
        df_saldo["entrada"] = (
            tot(dados["Aportes de Capital"])
              .add(tot(dados["AFAC Recebido"]), fill_value=0)
              .add(tot(dados["Subvenção para Custeio"]), fill_value=0)
        )
        df_saldo["saida"] = (
            tot(dados["Dividendos pagos à União"])
              .add(tot(dados["JCP pago à União"]), fill_value=0)
        )
        df_saldo = df_saldo.fillna(0)
        df_saldo["saldo"] = (df_saldo["entrada"] - df_saldo["saida"]) / 1e6
        df_saldo = df_saldo.reset_index().rename(columns={"index": "exercicio"})

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_saldo["exercicio"], y=df_saldo["saldo"],
            marker_color=[CORES["vermelho"] if v > 0 else CORES["verde"]
                          for v in df_saldo["saldo"]],
            hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>",
            showlegend=False
        ))
        fig2.update_layout(
            title="Saldo Líquido das Transferências (R$ Milhões)",
            xaxis_title="Ano", yaxis_title="R$ Mi",
            template="plotly_white", height=340,
            shapes=[dict(type="line",
                x0=df_saldo["exercicio"].min(), x1=df_saldo["exercicio"].max(),
                y0=0, y1=0, line=dict(color="black", width=1, dash="dash"))]
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ----- Detalhamento por empresa com ordenação dinâmica -----
    st.divider()
    st.markdown("##### Detalhamento por Empresa")

    det_list = []
    for nome, df_t in dados.items():
        if not df_t.empty:
            d = df_t.copy()
            d["tipo"]     = nome
            d["valor_mi"] = d["valor"] / 1e6
            det_list.append(d)

    if det_list:
        df_det = pd.concat(det_list)

        col_t1, col_t2 = st.columns([1, 2])
        with col_t1:
            ano_det = st.selectbox("Ano:",
                sorted(df_det["exercicio"].unique(), reverse=True),
                key="trs_ano")
        with col_t2:
            # Permite filtrar tipos para habilitar ordenação decrescente
            tipos_disp = sorted(df_det["tipo"].unique())
            tipos_sel = st.multiselect(
                "Tipos de fluxo:",
                options=tipos_disp,
                default=tipos_disp,
                key="trs_tipos"
            )

        if not tipos_sel:
            st.warning("Selecione ao menos um tipo de fluxo.")
        else:
            df_det_ano = df_det[
                (df_det["exercicio"] == ano_det) &
                (df_det["tipo"].isin(tipos_sel))
            ].copy()

            # ----- LÓGICA DE ORDENAÇÃO -----
            if len(tipos_sel) == 1:
                # Um único tipo: ordena empresas pelo valor (decrescente)
                ordem_empresas = (
                    df_det_ano.sort_values("valor_mi", ascending=True)
                              ["sigla_empresa"].tolist()
                )
                df_det_ano["sigla_empresa"] = pd.Categorical(
                    df_det_ano["sigla_empresa"],
                    categories=ordem_empresas, ordered=True
                )
                titulo = f"{tipos_sel[0]} por Empresa — {ano_det} (R$ Mi)"
            else:
                # Múltiplos tipos: ordena pelo total de cada empresa
                totais = (
                    df_det_ano.groupby("sigla_empresa")["valor_mi"]
                              .apply(lambda s: s.abs().sum())
                              .sort_values(ascending=True)
                )
                df_det_ano["sigla_empresa"] = pd.Categorical(
                    df_det_ano["sigla_empresa"],
                    categories=totais.index.tolist(), ordered=True
                )
                titulo = f"Fluxo por Empresa — {ano_det} (R$ Mi)"

            df_det_ano = df_det_ano.sort_values("sigla_empresa")

            fig3 = px.bar(df_det_ano, x="valor_mi", y="sigla_empresa",
                color="tipo", orientation="h", barmode="group",
                title=titulo,
                labels={"valor_mi":"R$ Mi","sigla_empresa":"","tipo":""},
                template="plotly_white",
                color_discrete_map={
                    "Aportes de Capital":       CORES["vermelho"],
                    "AFAC Recebido":            "#E74C3C",
                    "Subvenção para Custeio":   CORES["laranja"],
                    "Dividendos pagos à União": CORES["verde"],
                    "JCP pago à União":         "#1E8449",
                })
            fig3.update_traces(
                hovertemplate="%{fullData.name}: R$ %{x:,.1f} Mi<extra></extra>")
            fig3.update_layout(
                height=max(420, df_det_ano["sigla_empresa"].nunique() * 30),
                legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig3, use_container_width=True)

            st.divider()
            botoes_download(df_det_ano, "estatais_relacoes_tesouro", "Tesouro")

# ==============================================================================
# ABA 5 — DVA
# ==============================================================================
with tab_dva_tab:
    st.markdown("### Demonstração do Valor Adicionado")
    st.caption(
        "Valores por **rubrica pai** — evita dupla contagem com subcontas. "
        "Ex.: rubrica 630000 (PESSOAL) inclui todos os salários; "
        "subcontas 630100, 630200... não são somadas separadamente."
    )

    # Usa APENAS rubricas pai (sem subcontas)
    CAT_DVA = {
        "Pessoal":            RUBRICAS["dva_pessoal"],
        "Impostos e Taxas":   RUBRICAS["dva_impostos"],
        "Cap. de Terceiros":  RUBRICAS["dva_capital_terceiros"],
        "Cap. Próprio":       RUBRICAS["dva_capital_proprio"],
        "Lucros Retidos":     RUBRICAS["dva_lucros_retidos"],
    }
    CORES_DVA = {
        "Pessoal":           CORES["azul_ifi"],
        "Impostos e Taxas":  CORES["laranja"],
        "Cap. de Terceiros": CORES["verde"],
        "Cap. Próprio":      CORES["roxo"],
        "Lucros Retidos":    CORES["cinza"],
    }

    dados_dva = []
    for cat, cod in CAT_DVA.items():
        d = pegar_por_rubrica(df_dva, cod)
        if not d.empty:
            d["categoria"] = cat
            d["valor_mi"]  = d["valor"] / 1e6
            dados_dva.append(d)

    if dados_dva:
        df_dva_plot = pd.concat(dados_dva)

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            ano_dva = st.selectbox("Ano:",
                sorted(df_dva_plot["exercicio"].unique(), reverse=True),
                key="dva_ano")
            df_pizza = (df_dva_plot[
                (df_dva_plot["exercicio"]==ano_dva) &
                (df_dva_plot["valor_mi"] > 0)]
                .groupby("categoria")["valor_mi"].sum().reset_index())

            fig = px.pie(df_pizza, values="valor_mi", names="categoria",
                title=f"Distribuição do Valor Adicionado — {ano_dva}",
                color="categoria",
                color_discrete_map=CORES_DVA,
                template="plotly_white")
            fig.update_traces(
                textposition="inside", textinfo="percent+label",
                hovertemplate="%{label}: R$ %{value:,.1f} Mi<extra></extra>")
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_v2:
            df_stack = (df_dva_plot[df_dva_plot["valor_mi"]>0]
                        .groupby(["exercicio","categoria"])["valor_mi"]
                        .sum().reset_index())
            fig2 = px.bar(df_stack, x="exercicio", y="valor_mi",
                color="categoria", barmode="stack",
                title="Evolução da Distribuição do VA (R$ Milhões)",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano","categoria":""},
                color_discrete_map=CORES_DVA,
                template="plotly_white")
            fig2.update_traces(
                hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
            fig2.update_layout(height=400,
                legend=dict(orientation="h",y=1.1))
            st.plotly_chart(fig2, use_container_width=True)

        # Dividendos à União (DVA)
        st.divider()
        st.markdown("##### Dividendos e JCP pagos à União (DVA)")
        df_div_u = pegar_por_rubrica(df_dva, 660100)  # Dividendos e JCP destinados à União
        if not df_div_u.empty:
            df_du_agg = (df_div_u.groupby("exercicio")["valor"].sum().reset_index()
                                  .assign(valor_mi=lambda x: x["valor"]/1e6))
            fig3 = px.bar(df_du_agg, x="exercicio", y="valor_mi",
                title="Dividendos e JCP pagos à União (R$ Milhões)",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano"},
                template="plotly_white",
                color_discrete_sequence=[CORES["verde"]])
            fig3.update_traces(
                hovertemplate="%{x}: R$ %{y:,.1f} Mi<extra></extra>")
            fig3.update_layout(height=320)
            st.plotly_chart(fig3, use_container_width=True)

        st.divider()
        botoes_download(df_dva_plot, "estatais_dva","DVA")
    else:
        st.info("Sem dados DVA para o filtro atual.")

# ==============================================================================
# ABA 6 — EXPLORAR E BAIXAR
# ==============================================================================
with tab_exp:
    st.markdown("### Explorar e Baixar")
    st.caption(
        "Baixe o plano de contas completo para o conjunto de empresas "
        "e período selecionados na barra lateral."
    )

    plano_sel = st.selectbox("Plano de Contas:",
        sorted(df_base["nome_tipo_plano_contas"].unique()), key="exp_plano")

    df_exp = df_base[df_base["nome_tipo_plano_contas"] == plano_sel].copy()

    if not df_exp.empty:
        st.info(
            f"**{len(df_exp):,}** linhas · "
            f"**{df_exp['sigla_empresa'].nunique()}** empresas · "
            f"**{df_exp['exercicio'].nunique()}** anos"
        )

        # Gráfico de rubrica selecionável (opcional)
        rubricas_disp = sorted(df_exp["rubrica_nome"].unique())
        rubrica_graf = st.selectbox("Rubrica para visualizar:",
                                    rubricas_disp, key="exp_rub")
        df_graf = (df_exp[df_exp["rubrica_nome"]==rubrica_graf]
                   .assign(valor_mi=lambda x: x["valor"]/1e6))
        if not df_graf.empty:
            fig = px.line(df_graf, x="exercicio", y="valor_mi",
                color="sigla_empresa", markers=True,
                title=f"{rubrica_graf}",
                labels={"valor_mi":"R$ Mi","exercicio":"Ano",
                        "sigla_empresa":"Empresa"},
                template="plotly_white")
            fig.update_traces(
                hovertemplate="%{fullData.name}: R$ %{y:,.1f} Mi<extra></extra>")
            fig.update_layout(height=440, hovermode="x unified",
                legend=dict(orientation="h",y=1.1))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        # Download do plano completo (sem precisar selecionar rubrica)
        botoes_download(df_exp, f"estatais_{plano_sel.lower().replace(' ','_')}",
                        plano_sel)

        df_tab = df_exp[["exercicio","sigla_empresa","dependencia","setor",
                          "nome_tipo_plano_contas","rubrica","rubrica_nome","valor"]].copy()
        df_tab["valor"] = df_tab["valor"].map(fmt1)
        st.dataframe(df_tab, use_container_width=True, hide_index=True,
                     height=400)
    else:
        st.info("Sem dados para o filtro atual.")