"""
Página de Macroeconomia — organizada por FONTE de dado (IBGE, BCB, ANBIMA).

Esta página só monta a estrutura; cada aba vive num módulo de
frontend_dashboard/macro/. Consultas em query_engine.py, séries em
macro/catalogo.py, padrão visual em macro/visual.py.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from interface_utils import configurar_interface_ifi
from query_engine import get_status_macro
from macro import panorama, calendario, anbima, bcb, ibge
from macro import visual as v

st.set_page_config(page_title="Macroeconomia | IFI", page_icon="📈", layout="wide")
configurar_interface_ifi()

st.title("Macroeconomia")
st.caption("Conjuntura econômica a partir das fontes oficiais — IBGE, Banco Central e ANBIMA. "
           "Dados atualizados diariamente.")

# Abas preguiçosas: só a aba aberta executa (e consulta o BigQuery)
abas = v.abas(["📊 Panorama", "🇧🇷 IBGE", "🏦 Banco Central", "📐 ANBIMA", "🗓️ Calendário",
               "🔎 Explorar e baixar"], chave="abas_macro")
secoes = [panorama.render, ibge.render, bcb.render, anbima.render, calendario.render,
          lambda: v.em_construcao("Explorar e baixar: todas as séries do monitor")]

for aba, secao in zip(abas, secoes):
    with aba:
        if v.aberta(aba):
            secao()

# --- Sidebar: quando cada fonte foi atualizada ---
status = get_status_macro()
if not status.empty:
    with st.sidebar.expander("🔄 Atualização dos dados", expanded=False):
        for _, linha in status.iterrows():
            st.caption(f"**{linha['fonte']}**: {linha['atualizada_em']:%d/%m/%Y %H:%M}")
