"""Aba Calendário — agenda de divulgações do IBGE e do BCB."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from query_engine import carregar_calendario
from macro import visual as v

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

PERIODOS = {
    "Próximos 30 dias": (0, 30),
    "Próximos 90 dias": (0, 90),
    "Últimos 30 dias": (-30, 0),
    "Tudo": (None, None),
}


def _rotulo_data(d: pd.Timestamp) -> str:
    hoje = pd.Timestamp(date.today())
    extra = " · hoje" if d == hoje else " · amanhã" if d == hoje + timedelta(days=1) else ""
    return f"{d:%d/%m/%Y} ({DIAS_SEMANA[d.weekday()]}){extra}"


def tabela_agenda(df: pd.DataFrame, chave: str):
    """Tabela de eventos já filtrada — usada aqui e no Panorama."""
    exibir = pd.DataFrame({
        "Data": df['data'].map(_rotulo_data),
        "Hora": df['hora'].fillna("–"),
        "Fonte": df['fonte'],
        "Divulgação": df['evento'],
        "Referência": df['referencia'].fillna(""),
        "Tema": df['tema'],
    })
    st.dataframe(exibir, hide_index=True, width="stretch", key=f"agenda_{chave}")


def render():
    agenda = carregar_calendario()
    if agenda.empty:
        st.warning("Calendário indisponível — verificar o ETL etl_calendario.py.")
        return

    c1, c2, c3 = st.columns([1.2, 1, 2])
    with c1:
        periodo = st.radio("Período", list(PERIODOS), horizontal=False, key="cal_periodo")
    with c2:
        fontes = st.multiselect("Fonte", sorted(agenda['fonte'].unique()),
                                default=sorted(agenda['fonte'].unique()), key="cal_fontes")
    with c3:
        temas = st.multiselect("Tema", sorted(agenda['tema'].unique()),
                               default=sorted(agenda['tema'].unique()), key="cal_temas")

    hoje = pd.Timestamp(date.today())
    ini, fim = PERIODOS[periodo]
    filtro = agenda['fonte'].isin(fontes) & agenda['tema'].isin(temas)
    if ini is not None:
        filtro &= agenda['data'].between(hoje + timedelta(days=ini), hoje + timedelta(days=fim))
    selecionados = agenda[filtro]
    if periodo == "Últimos 30 dias":
        selecionados = selecionados.sort_values(['data', 'hora'], ascending=False)

    st.caption(f"{len(selecionados)} divulgação(ões) · horários de Brasília · "
               "Copom: decisão divulgada após o fechamento do mercado no 2º dia da reunião.")
    if selecionados.empty:
        st.info("Nenhuma divulgação para os filtros escolhidos.")
    else:
        tabela_agenda(selecionados, chave="aba")

    st.caption("Fontes: IBGE (API de calendário) e Banco Central (calendários oficiais em formato iCalendar). "
               "O IBGE publica sua agenda com cerca de 4 meses de antecedência.")
