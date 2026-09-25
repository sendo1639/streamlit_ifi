"""Aba ANBIMA — Estrutura a Termo das Taxas de Juros (ETTJ). Migrada da página antiga."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from query_engine import carregar_dados_ettj
from macro import visual as v

NOMES_LEGIVEIS = {
    "ettj_ipca_pct_aa_252": "ETTJ IPCA",
    "ettj_pre_pct_aa_252": "ETTJ PRÉ",
    "inflacao_implicita_pct_aa_252": "Inflação Implícita",
}
CORES_CURVAS = {"ETTJ IPCA": "#003366", "ETTJ PRÉ": "#E67E22", "Inflação Implícita": "#27AE60"}
VERTICES_REF = [252, 504, 1260, 2520]


def render():
    st.markdown("##### Estrutura a Termo das Taxas de Juros")
    with st.spinner("Carregando a curva de juros..."):
        df = carregar_dados_ettj()

    if df.empty:
        st.warning("⏳ Dados da ETTJ indisponíveis. Verificar se o ETL etl_anbima.py rodou.")
        return

    df["curva"] = df["nome_variavel"].map(NOMES_LEGIVEIS).fillna(df["nome_variavel"])
    datas = sorted(df["data"].dt.date.unique(), reverse=True)

    col_controles, col_grafico = st.columns([1, 3])

    with col_controles:
        curvas_disp = sorted(df["curva"].unique())
        curvas = st.multiselect("Curvas:", curvas_disp, default=curvas_disp, key="ettj_curvas")
        modo = st.radio("Modo:", ["Dia específico", "Comparar datas"], key="ettj_modo")
        if modo == "Dia específico":
            datas_plot = [st.selectbox("Data de referência:", datas,
                                       format_func=lambda d: d.strftime("%d/%m/%Y"), key="ettj_data")]
        else:
            datas_plot = st.multiselect("Datas (até 5):", datas, default=datas[:3],
                                        format_func=lambda d: d.strftime("%d/%m/%Y"),
                                        max_selections=5, key="ettj_datas")
        st.info(f"📅 **Histórico disponível**\n\n**{len(datas)}** dias úteis\n\n"
                f"De {min(datas):%d/%m/%Y} até {max(datas):%d/%m/%Y}")

    with col_grafico:
        if not curvas or not datas_plot:
            st.warning("Selecione ao menos uma curva e uma data.")
            return

        df_plot = df[df["data"].dt.date.isin(datas_plot) & df["curva"].isin(curvas)] \
            .sort_values(["data", "curva", "vertice_du"])
        if df_plot.empty:
            st.info("Não há dados para a combinação selecionada.")
            return

        titulo = (f"Curva zero cupom — {datas_plot[0]:%d/%m/%Y}" if modo == "Dia específico"
                  else "Comparativo de curvas de juros")
        fig = v.figura_base(titulo, "% a.a.", altura=460)
        fig.update_layout(xaxis=dict(title="Dias úteis (vértice)", tickformat=","),
                          yaxis=dict(ticksuffix="%"))

        datas_ord = sorted(datas_plot)
        for i, data_ref in enumerate(datas_ord):
            ultima = i == len(datas_ord) - 1
            for curva in curvas:
                c = df_plot[(df_plot["data"].dt.date == data_ref) & (df_plot["curva"] == curva)]
                if c.empty:
                    continue
                nome = curva if modo == "Dia específico" else f"{curva} ({data_ref:%d/%m/%Y})"
                fig.add_trace(go.Scatter(
                    x=c["vertice_du"], y=c["valor"], name=nome, mode="lines",
                    line=dict(color=CORES_CURVAS.get(curva, "#666"), width=2.5 if ultima else 1.8,
                              dash=None if ultima or modo == "Dia específico" else "dot",
                              shape="spline", smoothing=0.8),
                    opacity=1 if ultima else 0.4 + 0.6 * i / max(len(datas_ord) - 1, 1),
                    hovertemplate="%{y:.4f}% a.a. (%{x} du)",
                ))

        dados = df_plot[["data", "curva", "vertice_du", "valor"]].rename(
            columns={"vertice_du": "vertice_du (dias úteis)", "valor": "taxa (% a.a.)"})
        v.mostrar_grafico(fig, dados, "ANBIMA", chave="ettj")

        if modo == "Dia específico":
            st.markdown("##### Vértices de referência")
            for col, vert in zip(st.columns(len(VERTICES_REF)), VERTICES_REF):
                with col, st.container(border=True):
                    st.caption(f"**{vert} du** (~{vert // 252} ano{'s' if vert >= 504 else ''})")
                    for curva in curvas:
                        taxa = df_plot[(df_plot["curva"] == curva) & (df_plot["vertice_du"] == vert)]["valor"]
                        if not taxa.empty:
                            st.metric(curva, v.num(taxa.iloc[0], 2, '%'))
