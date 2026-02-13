import sys
import os
import pandas as pd
import streamlit as st
from pathlib import Path

# ==============================================================================
# 1. CONFIGURAÇÃO DE AMBIENTE E CAMINHOS
# ==============================================================================
# Identificação dinâmica de diretórios para garantir que o Deploy funcione
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / 'backend_etl' / 'scripts'

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    # Centraliza a conexão através do utils.py
    from utils import get_bq_client, PROJECT_ID
except ImportError:
    st.error(f"❌ Erro Crítico: 'utils.py' não localizado em {SCRIPTS_DIR}")
    st.stop()

# ==============================================================================
# 2. MOTOR DE EXECUÇÃO (Função Genérica)
# ==============================================================================
def executar_query(sql: str) -> pd.DataFrame:
    """
    Executa uma consulta no BigQuery e retorna um DataFrame.
    """
    try:
        client = get_bq_client()
        query_job = client.query(sql)
        return query_job.to_dataframe()
    except Exception as e:
        st.error(f"⚠️ Erro na consulta ao BigQuery: {e}")
        return pd.DataFrame()

# ==============================================================================
# 3. CARREGAMENTO DE DADOS (Com Cache de 1 Hora)
# ==============================================================================

@st.cache_data(ttl=3600)
def carregar_dados_sociais():
    """Busca dados consolidados do PBF/CadÚnico."""
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_sociais.base_consolidada_pbf_cadun` ORDER BY data DESC"
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_macro():
    """Busca indicadores do Banco Central (SGS)."""
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_macroeconomicos.banco_central_sgs` ORDER BY data DESC"
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_fiscais(tipo="reais"):
    """Busca séries do Tesouro Nacional (RTN)."""
    tabela = "rtn_valores_reais_ipca" if tipo == "reais" else "rtn_percentual_pib"
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_fiscais.{tabela}` ORDER BY data_referencia DESC"
    
    df = executar_query(sql)
    if not df.empty and 'data_referencia' in df.columns:
        df = df.rename(columns={'data_referencia': 'data'})
        df['data'] = pd.to_datetime(df['data'])
    return df

# ==============================================================================
# 4. MONITORAMENTO E STATUS (Sinal de Vida)
# ==============================================================================

def get_status_atualizacao():
    """
    Monitora a saúde do pipeline consultando os metadados das tabelas.
    """
    # Usamos o ID do projeto para evitar erros de localização 404
    sql = f"""
    SELECT 'Macro' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `{PROJECT_ID}.dados_macroeconomicos.banco_central_sgs`
    UNION ALL
    SELECT 'Fiscal' as dominio, MAX(data_carga) as ultima_carga, MAX(data_referencia) as referencia 
    FROM `{PROJECT_ID}.dados_fiscais.rtn_valores_reais_ipca`
    UNION ALL
    SELECT 'Social' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `{PROJECT_ID}.dados_sociais.base_consolidada_pbf_cadun`
    """
    return executar_query(sql)

def converter_para_csv(df):
    """Auxiliar para exportação de dados no dashboard."""
    return df.to_csv(index=False).encode('utf-8')