import sys
import os
import pandas as pd
import streamlit as st
from pathlib import Path
import streamlit as st
from datetime import datetime

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


def get_status_atualizacao():
    """
    Busca as datas de carga mais recentes usando os nomes exatos do BigQuery.
    """
    client = get_bq_client()
    
    # Query ajustada conforme a imagem do seu banco de dados
    sql = """
    SELECT 'Macro' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `dados_macroeconomicos.banco_central_sgs`
    
    UNION ALL
    
    -- Usamos a tabela de valores reais como referência para o domínio Fiscal
    SELECT 'Fiscal' as dominio, MAX(data_carga) as ultima_carga, MAX(data_referencia) as referencia 
    FROM `dados_fiscais.rtn_valores_reais_ipca`
    
    UNION ALL
    
    -- Nome ajustado conforme aparece na sua aba do BigQuery
    SELECT 'Social' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `dados_sociais.base_consolidada_pbf_cadun`
    """
    
    try:
        return client.query(sql).to_dataframe()
    except Exception as e:
        print(f"⚠️ Erro ao acessar tabelas: {e}")
        return pd.DataFrame()