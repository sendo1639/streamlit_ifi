import sys
import os
import requests
import pandas as pd
import warnings
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# ==============================================================================
# 1. CONFIGURAÇÃO DE LOGS E AMBIENTE
# ==============================================================================
# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
# Correção: _name_ (com dois underlines)
logger = logging.getLogger(__name__)

# Configuração de Importação
try:
    BASE_DIR = Path(_file_).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()).parent if 'macro' in os.getcwd() else Path(os.getcwd()) / 'backend_etl' / 'scripts'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    import utils
    import transformations as tr
    
except ImportError:
    logger.critical(f"Módulo 'utils.py' não encontrado em: {BASE_DIR}")
    sys.exit(1)

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_macroeconomicos'
TABELA_ID = 'banco_central_sgs'
TIMEOUT_SECONDS = 30
START_YEAR_CHUNKING = 1995
CHUNK_SIZE_YEARS = 5

SERIES_SGS: Dict[str, str] = {
    '433': 'IPCA - Mensal (%)',
    '13522': 'IPCA - Acumulado 12 meses (%)',
    '432': 'Meta Selic (% a.a.)',
    '1178': 'Taxa Selic Efetiva (% a.a.)',
    '24363': 'IBC-Br (Índice de Atividade Econômica)',
    '24364': 'IBC-Br (Com Ajuste Sazonal)',
    '1': 'Taxa de Câmbio - Livre (Dólar Venda)',
    '189': 'IGP-M - Mensal (%)',
    '4380': 'PIB mensal - valores correntes'
}

# ==============================================================================
# 3. FUNÇÕES DE EXTRAÇÃO
# ==============================================================================
def fetch_bcb_chunk(codigo_sgs: str, data_ini: str, data_fim: str) -> pd.DataFrame:
    """
    Realiza requisição de um período específico para a API do SGS.
    """
    url = f"http://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados?formato=json&dataInicial={data_ini}&dataFinal={data_fim}"
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        # Correção: response.json() converte para lista de dicts, que o Pandas aceita nativamente
        return pd.DataFrame(response.json())
    except (requests.exceptions.RequestException, ValueError):
        return pd.DataFrame()

def processar_serie_bcb(codigo_sgs: str, nome_indicador: str) -> pd.DataFrame:
    """
    Orquestra a extração de uma série temporal do BCB.
    Tenta download completo; em caso de falha (limite de API), realiza download fracionado.
    """
    logger.info(f"Processando: {nome_indicador} (SGS {codigo_sgs})")
    
    url_full = f"http://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados?formato=json"
    df = pd.DataFrame()
    
    # Estratégia 1: Download Completo
    try:
        response = requests.get(url_full, timeout=TIMEOUT_SECONDS)
        
        # Códigos 400/406 indicam violação de janela de tempo (séries diárias) ou erro na query
        if response.status_code != 200:
            raise ValueError("API limit exceeded or error. Switching to chunking strategy.")
            
        # Correção Crítica: Usar response.json() em vez de read_json(response.content)
        data_json = response.json()
        df = pd.DataFrame(data_json)
    
    # Estratégia 2: Download Fracionado (Chunking)
    except (ValueError, requests.exceptions.RequestException):
        logger.info(f"   -> Iniciando download fracionado ({START_YEAR_CHUNKING}-hoje)...")
        
        chunks: List[pd.DataFrame] = []
        ano_atual = datetime.now().year
        
        for ano_inicio in range(START_YEAR_CHUNKING, ano_atual + 1, CHUNK_SIZE_YEARS):
            ano_fim = min(ano_inicio + (CHUNK_SIZE_YEARS - 1), ano_atual)
            dt_ini = f"01/01/{ano_inicio}"
            dt_fim = f"31/12/{ano_fim}"
            
            df_chunk = fetch_bcb_chunk(codigo_sgs, dt_ini, dt_fim)
            if not df_chunk.empty:
                chunks.append(df_chunk)
        
        if chunks:
            df = pd.concat(chunks, ignore_index=True)
        else:
            logger.error(f"   -> Falha ao obter dados para {nome_indicador}.")
            return pd.DataFrame()

    if df.empty:
        logger.warning(f"   -> Série retornou vazia: {nome_indicador}")
        return pd.DataFrame()

    # Tratamento e Padronização
    try:
        # Conversão de Tipos
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y', errors='coerce')
        
        if 'valor' in df.columns:
            if df['valor'].dtype == 'object':
                df['valor'] = df['valor'].str.replace(',', '.')
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')

        # Metadados
        df['codigo_sgs'] = codigo_sgs
        df['nome_variavel'] = nome_indicador
        df['fonte'] = 'Banco Central (SGS)'
        df = tr.adicionar_metadados(df, fonte_dado='BCB - SGS')
        
        # Limpeza
        df = df.dropna(subset=['data', 'valor']).drop_duplicates()
        df = tr.normalizar_colunas(df)
        
        
        return df
        
    except Exception as e:
        logger.error(f"Erro no tratamento de dados: {e}")
        return pd.DataFrame()

# ==============================================================================
# 4. EXECUÇÃO PRINCIPAL
# ==============================================================================
def main():
    logger.info("Iniciando pipeline de extração Macroecômica (BCB)...")
    
    dataframes_coletados: List[pd.DataFrame] = []
    
    for codigo, nome in SERIES_SGS.items():
        df_temp = processar_serie_bcb(codigo, nome)
        if not df_temp.empty:
            dataframes_coletados.append(df_temp)
    
    if dataframes_coletados:
        df_final = pd.concat(dataframes_coletados, ignore_index=True)
        
        logger.info(f"Total de registros extraídos: {len(df_final)}")
        logger.info(f"Iniciando carga no BigQuery: {DATASET_ID}.{TABELA_ID}")
        
        sucesso = utils.subir_para_bigquery(
            df=df_final, 
            dataset=DATASET_ID, 
            tabela=TABELA_ID, 
            if_exists='replace'
        )
        
        if sucesso:
            logger.info("Pipeline concluído com sucesso.")
        else:
            logger.error("Falha no upload para o BigQuery.")
    else:
        logger.warning("Nenhum dado foi extraído. Verifique a disponibilidade da API.")

# Correção: _name_ e _main_ com dois underlines
if __name__ == "__main__":
    main()