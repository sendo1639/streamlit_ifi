import sys
import os
import io
import warnings
import logging
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

import pandas as pd
import requests
from google.cloud import bigquery

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuração de Path (Backend ETL) ---
try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()).parent if 'social' in os.getcwd() else Path(os.getcwd()) / 'backend_etl'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

# --- Importação Segura do Utils ---
try:
    from utils import PROJECT_ID, get_bq_client
except ImportError:
    logger.critical(f"Erro: 'utils.py' não encontrado em {BASE_DIR}.")
    sys.exit(1)
    
try:
    import transformations as tr
except ImportError: 
    logger.critical(f"Erro: 'utils.py' não encontrado em {BASE_DIR}.")
    sys.exit(1)

warnings.filterwarnings("ignore")

# --- Constantes ---
DATASET_ID = 'dados_fiscais'
URL_RTN = "http://sisweb.tesouro.gov.br/apex/cosis/thot/link/rtn/serie-historica?conteudo=cdn"
TIMEOUT = 120

def parse_fiscal_date(value: Any) -> Optional[str]:
    """
    Converte cabeçalhos (que podem vir como string ou datetime) para string YYYY-MM-DD.
    """
    if pd.isna(value) or value == '':
        return None

    # Se o Pandas já leu como Timestamp (comum em Excel), apenas formata
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime('%Y-%m-%d')
    
    val_str = str(value).strip().lower()

    # Caso 1: Dado Anual (ex: "2023" ou 2023.0)
    # Remove .0 se vier como float
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
        
    if val_str.isdigit() and len(val_str) == 4:
        return f"{val_str}-12-31"

    # Caso 2: Dado Mensal (ex: "jan/23")
    mapa_meses = {
        'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
        'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
    }
    
    try:
        # Verifica se tem separador "/"
        if '/' not in val_str:
            return None
            
        parte_mes, parte_ano = val_str.split('/')
        
        # Normalização do ano (2 digitos -> 4 digitos)
        if len(parte_ano) == 2:
            ano_int = int(parte_ano)
            parte_ano = f"19{parte_ano}" if ano_int > 80 else f"20{parte_ano}"
        
        if parte_mes in mapa_meses:
            return f"{parte_ano}-{mapa_meses[parte_mes]}-01"
            
    except Exception:
        return None
        
    return None

def transform_wide_to_long(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """
    Normaliza tabelas do Tesouro (Wide -> Long), limpa rubricas e datas.
    """
    logger.info(f"Processando tabela: {table_name}")
    
    # 1. Limpeza estrutural
    df = df.dropna(axis=1, how='all')
    col_rubrica = df.columns[0] # Assume que a 1ª coluna é a discriminação
    
    # Remove linhas onde a rubrica é vazia
    df = df[df[col_rubrica].notna()]
    
    # 2. Unpivot (Transforma colunas de data em linhas)
    df_long = pd.melt(
        df, 
        id_vars=[col_rubrica], 
        var_name='periodo_raw', 
        value_name='valor'
    )
    
    # 3. Tratamento de Nomes
    df_long = df_long.rename(columns={col_rubrica: 'rubrica'})
    df_long['rubrica'] = df_long['rubrica'].astype(str).str.strip()
    df_long = tr.adicionar_metadados(df_long, fonte_dado='RTN')
    
    # 4. Tratamento de Datas
    # Aplica o parser para string YYYY-MM-DD
    df_long['data_referencia'] = df_long['periodo_raw'].apply(parse_fiscal_date)
    
    # Remove registros onde a data não é válida (isso remove colunas de 'Total', 'Obs', etc)
    df_long = df_long.dropna(subset=['data_referencia'])

    # 5. Tratamento de Tipos para o BigQuery (CRÍTICO: O erro pyarrow ocorre aqui)
    # Convertemos para datetime64[ns]
    df_long['data_referencia'] = pd.to_datetime(df_long['data_referencia'])
    
    # 6. Tratamento de Valores
    df_long['valor'] = pd.to_numeric(df_long['valor'], errors='coerce')
    
    return df_long[['rubrica', 'data_referencia', 'valor', 'data_carga', 'fonte', 'frequencia']]

def fetch_rtn_data() -> io.BytesIO:
    """Baixa o arquivo Excel do Tesouro Nacional."""
    logger.info(f"Iniciando download: {URL_RTN}")
    response = requests.get(URL_RTN, verify=False, timeout=TIMEOUT)
    response.raise_for_status()
    return io.BytesIO(response.content)

def upload_to_bigquery(client: bigquery.Client, df: pd.DataFrame, table_id: str):
    """Configura e executa o job de carga no BigQuery."""
    full_table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_id}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("rubrica", "STRING"),
            bigquery.SchemaField("data_referencia", "DATE"),
            bigquery.SchemaField("valor", "FLOAT"),
        ]
    )
    
    try:
        logger.info(f"Enviando {len(df)} linhas para {full_table_id}...")
        job = client.load_table_from_dataframe(df, full_table_id, job_config=job_config)
        job.result()
        logger.info("✅ Carga concluída com sucesso.")
    except Exception as e:
        logger.error(f"❌ Falha no upload para {full_table_id}: {e}")

def main():
    logger.info("--- ETL TESOURO NACIONAL (RTN) ---")
    
    try:
        client = get_bq_client()
    except Exception as e:
        logger.critical(f"Falha na autenticação: {e}")
        return

    try:
        excel_file = fetch_rtn_data()
    except Exception as e:
        logger.critical(f"Falha no download: {e}")
        return

    tasks = [
        ("1.2-A", "rtn_valores_reais_ipca"),
        ("2.2-A", "rtn_percentual_pib")
    ]

    for sheet_name, table_name in tasks:
        try:
            # header=4 é padrão histórico, mas pode mudar.
            # Se a tabela vier vazia, verifique se o header mudou no Excel.
            df_raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=4)
            
            df_clean = transform_wide_to_long(df_raw, table_name)
            
            if not df_clean.empty:
                upload_to_bigquery(client, df_clean, table_name)
            else:
                logger.warning(f"⚠️ Aba {sheet_name} resultou vazia. Verifique o cabeçalho.")
                logger.warning(f"Colunas encontradas: {df_raw.columns[:5].tolist()}")
                
        except Exception as e:
            logger.error(f"Erro ao processar aba {sheet_name}: {e}")

    logger.info("--- FIM DO PROCESSO ---")

if __name__ == "__main__":
    main()