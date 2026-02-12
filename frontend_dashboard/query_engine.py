import sys
import os
import pandas as pd
import streamlit as st
from pathlib import Path

# ==============================================================================
# 1. CONFIGURAÇÃO DE CAMINHOS (CORRIGIDA)
# ==============================================================================

# Identifica o caminho onde este arquivo (query_engine.py) está
CURRENT_FILE = Path(__file__).resolve()
# Sobe um nível para chegar em 'frontend_dashboard'
FRONTEND_DIR = CURRENT_FILE.parent
# Sobe mais um nível para chegar na raiz 'monitor_economia_ifi'
PROJECT_ROOT = FRONTEND_DIR.parent

# --- A CORREÇÃO ESTÁ AQUI ---
# Aponta exatamente para onde o utils.py está: backend_etl/scripts
SCRIPTS_DIR = PROJECT_ROOT / 'backend_etl' / 'scripts'

# Verificação de segurança: O arquivo existe mesmo?
utils_file_path = SCRIPTS_DIR / "utils.py"
if not utils_file_path.exists():
    st.error(f"❌ ERRO GRAVE DE CAMINHO:")
    st.error(f"O arquivo 'utils.py' não foi encontrado no caminho esperado.")
    st.write(f"Esperado: `{utils_file_path}`")
    st.stop()

# Adiciona a pasta 'scripts' no topo da lista de busca do Python
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# ==============================================================================
# 2. IMPORTAÇÃO DO UTILS
# ==============================================================================
try:
    # Agora o Python sabe olhar dentro de 'backend_etl/scripts'
    from utils import get_bq_client, PROJECT_ID
except ImportError as e:
    st.error("❌ Falha ao importar 'utils.py'.")
    st.code(f"Tentando importar de: {SCRIPTS_DIR}\nErro: {e}")
    st.stop()

# ==============================================================================
# 3. FUNÇÕES DE CARGA DE DADOS (COM CACHE)
# ==============================================================================

# --- DADOS SOCIAIS ---
@st.cache_data(ttl=3600)  # Cache dura 1 hora
def carregar_dados_sociais():
    try:
        client = get_bq_client()
        query = f"""
            SELECT *
            FROM `{PROJECT_ID}.dados_sociais.base_consolidada_pbf_cadun`
            ORDER BY data DESC
        """
        df = client.query(query).to_dataframe()
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados sociais: {e}")
        return pd.DataFrame()

# --- DADOS MACROECONÔMICOS ---
@st.cache_data(ttl=3600)
def carregar_dados_macro():
    try:
        client = get_bq_client()
        query = f"""
            SELECT *
            FROM `{PROJECT_ID}.dados_macroeconomicos.banco_central_sgs`
            ORDER BY data DESC
        """
        df = client.query(query).to_dataframe()
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados macro: {e}")
        return pd.DataFrame()

# --- DADOS FISCAIS (RTN) ---
@st.cache_data(ttl=3600)
def carregar_dados_fiscais(tipo="reais"):
    try:
        client = get_bq_client()
        tabela = "rtn_valores_reais_ipca" if tipo == "reais" else "rtn_percentual_pib"
        query = f"""
            SELECT *
            FROM `{PROJECT_ID}.dados_fiscais.{tabela}`
            ORDER BY data_referencia DESC
        """
        df = client.query(query).to_dataframe()
        if 'data_referencia' in df.columns:
            df = df.rename(columns={'data_referencia': 'data'})
            df['data'] = pd.to_datetime(df['data'])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados fiscais ({tipo}): {e}")
        return pd.DataFrame()

# ==============================================================================
# 4. UTILITÁRIOS
# ==============================================================================
def converter_para_csv(df):
    return df.to_csv(index=False).encode('utf-8')