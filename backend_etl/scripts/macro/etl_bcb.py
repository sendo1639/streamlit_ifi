import sys
import os
import time
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
logger = logging.getLogger(__name__)

# Configuração de Importação
try:
    BASE_DIR = Path(__file__).resolve().parent.parent
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
MAX_RETRIES = 3
# Início do download fracionado (usado sempre nas séries diárias — a API limita
# a 10 anos por consulta — e como plano B nas demais):
#  - séries DIÁRIAS começam em 1995 de propósito: antes do Plano Real, dólar e
#    Selic estão em moedas/regimes antigos (ex.: dólar = 2.828,00 em 1984);
#  - as demais começam em 1980, antes da série mais antiga. Em 25/09/2026, no
#    GitHub Actions, o download completo do PIB mensal (4380) falhou, o
#    fracionado começou em 1995 e 1990–1994 se perderam.
# Blocos anteriores ao início da série voltam vazios (404), sem custo relevante.
START_YEAR_CHUNKING = 1980
START_YEAR_CHUNKING_DIARIAS = 1995
SERIES_DIARIAS = {'1', '432', '1178'}
CHUNK_SIZE_YEARS = 5
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"

# Códigos conferidos contra o nome oficial no SGS (serviço FachadaWSSGS) em
# 24/09/2026. Aberturas e núcleos do IPCA também conferidos contra os valores
# em 12 meses citados no RAF nº 113 (jun/2026) — bateram todos.
SERIES_SGS: Dict[str, str] = {
    # --- Inflação ---
    '433': 'IPCA - Mensal (%)',
    '13522': 'IPCA - Acumulado 12 meses (%)',
    '13521': 'Meta para a inflação (%)',
    '189': 'IGP-M - Mensal (%)',
    # Aberturas do IPCA (var. % mensal)
    '11428': 'IPCA - Itens livres (%)',
    '4449': 'IPCA - Administrados (%)',
    '27864': 'IPCA - Alimentação no domicílio (%)',
    '27863': 'IPCA - Industriais (%)',
    '10844': 'IPCA - Serviços (%)',
    '10841': 'IPCA - Bens não duráveis (%)',
    '10842': 'IPCA - Bens semiduráveis (%)',
    '10843': 'IPCA - Bens duráveis (%)',
    # Núcleos do IPCA (var. % mensal)
    '11427': 'IPCA - Núcleo EX0 (%)',
    '16121': 'IPCA - Núcleo EX1 (%)',
    '27838': 'IPCA - Núcleo EX2 (%)',
    '27839': 'IPCA - Núcleo EX3 (%)',
    '4466': 'IPCA - Núcleo MS - médias aparadas com suavização (%)',
    '11426': 'IPCA - Núcleo MA - médias aparadas sem suavização (%)',
    '16122': 'IPCA - Núcleo DP - dupla ponderação (%)',
    '28750': 'IPCA - Núcleo P55 - percentil 55 (%)',
    '28751': 'IPCA - Núcleo EX-FE - ex-alimentação e energia (%)',
    # --- Juros ---
    '432': 'Meta Selic (% a.a.)',
    '1178': 'Taxa Selic Efetiva (% a.a.)',
    '4390': 'Selic acumulada no mês (% a.m.)',
    # --- Crédito ---
    '20714': 'Taxa média de juros do crédito - Total (% a.a.)',
    '20715': 'Taxa média de juros do crédito - Pessoas jurídicas (% a.a.)',
    '20716': 'Taxa média de juros do crédito - Pessoas físicas (% a.a.)',
    '25351': 'Indicador de Custo do Crédito - ICC (% a.a.)',
    '20783': 'Spread médio do crédito - Total (p.p.)',
    # --- Atividade e câmbio ---
    '24363': 'IBC-Br (Índice de Atividade Econômica)',
    '24364': 'IBC-Br (Com Ajuste Sazonal)',
    '1': 'Taxa de Câmbio - Livre (Dólar Venda)',
    '4380': 'PIB mensal - valores correntes'
}

# ==============================================================================
# 3. FUNÇÕES DE EXTRAÇÃO
# ==============================================================================
def fetch_bcb_chunk(codigo_sgs: str, data_ini: str, data_fim: str) -> Optional[pd.DataFrame]:
    """
    Realiza requisição de um período específico para a API do SGS, com retry.
    Retorna None se todas as tentativas falharem — diferente de um DataFrame
    vazio, que é resposta válida (período anterior ao início da série).
    """
    url = f"{URL_SGS.format(codigo=codigo_sgs)}&dataInicial={data_ini}&dataFinal={data_fim}"
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=TIMEOUT_SECONDS)
            # 404 = série sem observações no período (ex: antes do início da série)
            if response.status_code == 404:
                return pd.DataFrame()
            response.raise_for_status()
            return pd.DataFrame(response.json())
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"   -> {data_ini}-{data_fim}: tentativa {tentativa}/{MAX_RETRIES} falhou ({e})")
            if tentativa < MAX_RETRIES:
                time.sleep(5 * tentativa)
    return None

def processar_serie_bcb(codigo_sgs: str, nome_indicador: str) -> pd.DataFrame:
    """
    Orquestra a extração de uma série temporal do BCB.
    Tenta download completo; se a API recusar (séries diárias têm limite de
    10 anos por consulta), faz download fracionado. Se qualquer fração
    falhar, a série inteira é descartada — nunca retorna série com buraco.
    """
    logger.info(f"Processando: {nome_indicador} (SGS {codigo_sgs})")

    df = pd.DataFrame()

    # Estratégia 1: Download Completo
    try:
        response = requests.get(URL_SGS.format(codigo=codigo_sgs), timeout=TIMEOUT_SECONDS)

        # Códigos 400/406 indicam violação de janela de tempo (séries diárias) ou erro na query
        if response.status_code != 200:
            raise ValueError("API limit exceeded or error. Switching to chunking strategy.")

        df = pd.DataFrame(response.json())

    # Estratégia 2: Download Fracionado (Chunking)
    except (ValueError, requests.exceptions.RequestException):
        inicio = START_YEAR_CHUNKING_DIARIAS if codigo_sgs in SERIES_DIARIAS else START_YEAR_CHUNKING
        logger.info(f"   -> Iniciando download fracionado ({inicio}-hoje)...")

        chunks: List[pd.DataFrame] = []
        ano_atual = datetime.now().year

        for ano_inicio in range(inicio, ano_atual + 1, CHUNK_SIZE_YEARS):
            ano_fim = min(ano_inicio + (CHUNK_SIZE_YEARS - 1), ano_atual)
            dt_ini = f"01/01/{ano_inicio}"
            dt_fim = f"31/12/{ano_fim}"

            df_chunk = fetch_bcb_chunk(codigo_sgs, dt_ini, dt_fim)
            if df_chunk is None:
                logger.error(f"   -> Falha no bloco {ano_inicio}-{ano_fim} de {nome_indicador}.")
                return pd.DataFrame()
            chunks.append(df_chunk)

        df = pd.concat(chunks, ignore_index=True)

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
        # A Meta Selic (432) vem projetada até a próxima reunião do Copom — corta no dia de hoje
        df = df[df['data'] <= pd.Timestamp.today().normalize()]
        df = tr.normalizar_colunas(df)

        logger.info(f"   -> {len(df):,} obs. | {df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y}")
        return df
        
    except Exception as e:
        logger.error(f"Erro no tratamento de dados: {e}")
        return pd.DataFrame()

# ==============================================================================
# 4. EXECUÇÃO PRINCIPAL
# ==============================================================================
def carregar_series_atuais(codigos: List[str]) -> pd.DataFrame:
    """Lê do BigQuery as séries que falharam hoje, para não apagá-las no replace."""
    lista = ", ".join(f"'{c}'" for c in codigos)
    sql = f"""
        SELECT * FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`
        WHERE codigo_sgs IN ({lista})
    """
    return utils.get_bq_client().query(sql).to_dataframe()

def main() -> bool:
    logger.info("Iniciando pipeline de extração Macroecômica (BCB)...")

    dataframes_coletados: List[pd.DataFrame] = []
    falhas: List[str] = []

    for codigo, nome in SERIES_SGS.items():
        df_temp = processar_serie_bcb(codigo, nome)
        if df_temp.empty:
            falhas.append(codigo)
        else:
            dataframes_coletados.append(df_temp)

    # Série que falhou hoje mantém a versão de ontem (o replace apagaria)
    if falhas:
        logger.warning(f"Séries com falha na coleta: {falhas} — mantendo a versão atual do BigQuery.")
        try:
            df_antigas = carregar_series_atuais(falhas)
        except Exception as e:
            logger.error(f"Não foi possível ler as séries antigas ({e}) — abortando carga para não perder dados.")
            return False
        faltando = set(falhas) - set(df_antigas['codigo_sgs'].unique())
        if faltando:
            logger.warning(f"Séries sem versão anterior no BigQuery: {sorted(faltando)}")
        dataframes_coletados.append(df_antigas)

    if not dataframes_coletados:
        logger.error("Nenhum dado foi extraído. Verifique a disponibilidade da API.")
        return False

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
        logger.info("Pipeline concluído com sucesso." if not falhas else
                    "Pipeline concluído — com séries mantidas da versão anterior.")
    else:
        logger.error("Falha no upload para o BigQuery.")
    return sucesso and not falhas

if __name__ == "__main__":
    sys.exit(0 if main() else 1)