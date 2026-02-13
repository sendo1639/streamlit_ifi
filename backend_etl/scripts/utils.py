import pandas as pd
from google.oauth2 import service_account
from google.cloud import bigquery
import os
import sys
import logging
from pathlib import Path

# --- CONFIGURAÇÕES GLOBAIS ---
# ID oficial do projeto IFI no Google Cloud [cite: 50]
PROJECT_ID = '294242506105' 

# Configuração de Logging Profissional 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def encontrar_arquivo_projeto(nome_arquivo):
    """
    Localizador de Credenciais: Sobe níveis de diretório para encontrar o arquivo.
    Permite que scripts rodem de qualquer pasta (Backend ou Frontend)[cite: 76].
    """
    caminho_atual = Path(os.getcwd()).resolve()
    for diretorio in [caminho_atual] + list(caminho_atual.parents):
        arquivo_teste = diretorio / nome_arquivo
        if arquivo_teste.exists():
            return str(arquivo_teste)
    return None

def get_credentials():
    """
    Autentica no Google Cloud de forma híbrida[cite: 77].
    Prioridade: 1. Streamlit Secrets (Nuvem) | 2. Env Var (GitHub) | 3. JSON (Local)
    """
    # 1. TENTA STREAMLIT SECRETS (Ambiente de Produção/Dashboard)
    # Importação 'preguiçosa' para não quebrar o ETL no GitHub Actions
    if 'streamlit' in sys.modules or os.getenv('STREAMLIT_SERVER_PORT'):
        try:
            import streamlit as st
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                return service_account.Credentials.from_service_account_info(creds_dict)
        except Exception:
            pass

    # 2. TENTA VARIÁVEL DE AMBIENTE (Ambiente de Automação/GitHub Actions)
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.exists(env_path):
        return service_account.Credentials.from_service_account_file(env_path)

    # 3. FALLBACK PARA ARQUIVO LOCAL (Ambiente de Desenvolvimento/Spyder)
    # Busca o service_account.json na raiz do projeto [cite: 43, 76]
    caminho_local = encontrar_arquivo_projeto('service_account.json')
    if caminho_local:
        return service_account.Credentials.from_service_account_file(caminho_local)

    raise FileNotFoundError("❌ Nenhuma fonte de credenciais do BigQuery foi encontrada (Secrets, Env ou JSON).")

def get_bq_client():
    """
    Retorna o cliente nativo do BigQuery para controle fino de Schema[cite: 79, 80].
    """
    credentials = get_credentials()
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)

def subir_para_bigquery(df, dataset, tabela, if_exists='replace'):
    """
    Função genérica para cargas simples usando Pandas to_gbq[cite: 78].
    """
    try:
        credentials = get_credentials()
        destination = f"{dataset}.{tabela}"
        
        logger.info(f"🚀 Iniciando upload de {len(df)} linhas para {destination}...")
        
        df.to_gbq(
            destination_table=destination,
            project_id=PROJECT_ID,
            credentials=credentials,
            if_exists=if_exists
        )
        logger.info(f"✅ Sucesso! Tabela {tabela} atualizada.")
        return True

    except Exception as e:
        erro_msg = f"❌ Erro ao subir dados para o BigQuery: {e}"
        logger.error(erro_msg)
        
        # Só tenta mostrar erro no Streamlit se estivermos rodando o dashboard
        if 'streamlit' in sys.modules:
            import streamlit as st
            st.error(erro_msg)
        return False