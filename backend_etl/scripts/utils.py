import pandas as pd
from google.oauth2 import service_account
from google.cloud import bigquery
import os
from pathlib import Path

# --- CONFIGURAÇÕES GLOBAIS ---
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
    Retorna as credenciais. 
    Prioriza a variável de ambiente (GitHub/Nuvem) e faz fallback para o arquivo local.
    """
    # 1. Tenta pegar o caminho da variável de ambiente (Padrão GitHub Actions)
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    if env_path and os.path.exists(env_path):
        return service_account.Credentials.from_service_account_file(env_path)
    
    # 2. Fallback para o seu método original (Uso local no PC)
    caminho_local = encontrar_arquivo_projeto('service_account.json')
    if caminho_local:
        return service_account.Credentials.from_service_account_file(caminho_local)
    
    raise FileNotFoundError("❌ Chave do BigQuery não encontrada (Ambiente ou Arquivo).")

def get_bq_client():
    credentials = get_credentials()
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)

def subir_para_bigquery(df, dataset, tabela, if_exists='replace'):
    try:
        credentials = get_credentials()
        destination = f"{dataset}.{tabela}"
        print(f"Subindo {len(df)} linhas para {destination}...")
        
        df.to_gbq(
            destination_table=destination,
            project_id=PROJECT_ID,
            credentials=credentials,
            if_exists=if_exists
        )
        print(f"✅ Sucesso! Tabela {tabela} atualizada.")
        return True
    except Exception as e:
        print(f"Erro ao subir para BigQuery: {e}")
        return False