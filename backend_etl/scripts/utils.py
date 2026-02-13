import pandas as pd
from google.oauth2 import service_account
from google.cloud import bigquery
import os
import streamlit as st
from pathlib import Path

# --- CONFIGURAÇÕES GLOBAIS ---
# O ID do seu projeto no BigQuery [cite: 50]
PROJECT_ID = '294242506105' 

def encontrar_arquivo_projeto(nome_arquivo):
    """Procura o arquivo de credenciais subindo nas pastas (útil para o Spyder)."""
    caminho_atual = Path(os.getcwd()).resolve()
    for diretorio in [caminho_atual] + list(caminho_atual.parents):
        arquivo_teste = diretorio / nome_arquivo
        if arquivo_teste.exists():
            return str(arquivo_teste)
    return None

def get_credentials():
    """
    Gerenciador de Credenciais Híbrido:
    1. Tenta Streamlit Secrets (Nuvem/Deploy)
    2. Tenta Variável de Ambiente (GitHub Actions)
    3. Tenta Arquivo Local (Spyder/PC)
    """
    # 1. TENTA STREAMLIT SECRETS (Para o Passo 2: Deploy)
    if "gcp_service_account" in st.secrets:
        # Transforma o dicionário do Secrets em credenciais oficiais
        creds_dict = dict(st.secrets["gcp_service_account"])
        return service_account.Credentials.from_service_account_info(creds_dict)

    # 2. TENTA VARIÁVEL DE AMBIENTE (Padrão GitHub Actions)
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.exists(env_path):
        return service_account.Credentials.from_service_account_file(env_path)

    # 3. FALLBACK LOCAL (Uso no PC) [cite: 76, 77]
    caminho_local = encontrar_arquivo_projeto('service_account.json')
    if caminho_local:
        return service_account.Credentials.from_service_account_file(caminho_local)

    raise FileNotFoundError("❌ Nenhuma fonte de credenciais do BigQuery foi encontrada.")

def get_bq_client():
    """Retorna o cliente nativo do BigQuery."""
    credentials = get_credentials()
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)

def subir_para_bigquery(df, dataset, tabela, if_exists='replace'):
    """Função genérica para upload de dados (Backend/ETL). [cite: 78, 79]"""
    try:
        credentials = get_credentials()
        destination = f"{dataset}.{tabela}"
        
        # O to_gbq é excelente para cargas rápidas
        df.to_gbq(
            destination_table=destination,
            project_id=PROJECT_ID,
            credentials=credentials,
            if_exists=if_exists
        )
        return True
    except Exception as e:
        # Usamos st.error para que o erro apareça no dashboard se algo falhar
        st.error(f"Erro ao subir para BigQuery: {e}")
        return False