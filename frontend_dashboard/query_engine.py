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

@st.cache_data(ttl=3600)
def carregar_dados_ettj():
    """
    Busca a série histórica da curva de juros ETTJ (ANBIMA).
    Colunas: data | vertice_du | nome_variavel | valor
    """
    sql = f"""
        SELECT data, vertice_du, nome_variavel, valor
        FROM `{PROJECT_ID}.dados_macroeconomicos.anbima_ettj`
        ORDER BY data DESC, vertice_du ASC
    """
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_estatais():
    """
    Busca a base completa de estatais do BigQuery.
    Retorna todos os planos de contas (Balanço, DRE, DVA, Fluxo de Caixa)
    para todos os anos e empresas disponíveis.
    """
    sql = f"""
        SELECT
            exercicio,
            codigo_siest,
            sigla_empresa,
            nome_empresa,
            dependencia,
            setor,
            nome_tipo_plano_contas,
            rubrica,
            rubrica_nome,
            valor
        FROM `{PROJECT_ID}.dados_fiscais.sest_estatais`
        ORDER BY exercicio, sigla_empresa, nome_tipo_plano_contas, rubrica
    """
    return executar_query(sql)


@st.cache_data(ttl=3600)
def carregar_dados_siga_brasil():
    """
    Carrega dados do SIGA Brasil — Estatais Dependentes (Pellegrini v2).
    Tabela: dados_fiscais.siga_brasil_dependentes
 
    Colunas novas em relação à v1:
      despesa_pessoal_mi           — GND Pessoal isolado (R$ Mi)
      num_funcionarios             — quantitativo dez/ano (arquivo pessoal SEST)
      desp_pessoal_por_func_mes_rs — Pellegrini: Pessoal / (Func × 13)
    """
    sql = f"""
        SELECT
            exercicio,
            sigla_empresa,
            despesas_totais_mi,
            recursos_tesouro_mi,
            grau_dependencia_pct,
            comp_pessoal_correntes_pct,
            comp_investimentos_pct,
            despesa_pessoal_mi,
            num_funcionarios,
            desp_pessoal_por_func_mes_rs
        FROM `{PROJECT_ID}.dados_fiscais.siga_brasil_dependentes`
        ORDER BY exercicio, sigla_empresa
    """
    return executar_query(sql)


@st.cache_data(ttl=3600)
def carregar_dados_estatais_2025():
    """
    Carrega dados contábeis trimestrais das estatais (2025+).
    Tabela: dados_fiscais.estatais_2025
    Schema: exercicio, trimestre, periodicidade, universo_cod, universo_desc,
            sigla_empresa, nome_empresa, dependencia, setor, area_atuacao,
            nome_tipo_plano_contas, rubrica, rubrica_nome,
            valor (acumulado no ano), valor_trimestre (isolado do trimestre)

    IMPORTANTE: 'valor' é o acumulado no ano-calendário (1T, 1T+2T, ...),
    como reportado pelo SIEST. 'valor_trimestre' é o valor isolado daquele
    trimestre (calculado no ETL por diferença entre acumulados). Contas de
    Balanço (estoque) têm valor == valor_trimestre, pois são saldos pontuais.
    'valor_trimestre' pode ser NULL quando há um trimestre faltante na série
    (não inferimos esse caso para evitar dado incorreto).
    """
    sql = f"""
        SELECT
            exercicio, trimestre, periodicidade,
            universo_cod, universo_desc,
            sigla_empresa, nome_empresa,
            dependencia, setor, area_atuacao,
            nome_tipo_plano_contas, rubrica, rubrica_nome,
            valor, valor_trimestre
        FROM `{PROJECT_ID}.dados_fiscais.estatais_2025`
        ORDER BY exercicio, trimestre, sigla_empresa
    """
    df = executar_query(sql)
    if df is not None and not df.empty:
        # Rubrica como int para compatibilizar com filtros (vem como string do BQ)
        df['rubrica'] = pd.to_numeric(df['rubrica'], errors='coerce').astype('Int64')
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
    UNION ALL
    SELECT 'ETTJ' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia
    FROM `{PROJECT_ID}.dados_macroeconomicos.anbima_ettj`
    """
    return executar_query(sql)

def converter_para_csv(df):
    """Auxiliar para exportação de dados no dashboard."""
    return df.to_csv(index=False).encode('utf-8')