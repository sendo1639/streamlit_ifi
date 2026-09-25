"""
ETL: Boletim Focus (Expectativas de Mercado) — BCB
=====================================================
Fontes (API Olinda "Expectativas", chamada direto via requests):
    ExpectativasMercadoAnuais            -> focus_expectativas_anuais
    ExpectativaMercadoMensais            -> focus_expectativas_mensais
    ExpectativasMercadoInflacao12Meses   -> focus_inflacao_12meses

Decisões de arquitetura (22/07/2026, mantidas):
  - Coleta SEM filtro de indicador — o endpoint inteiro.
  - Guarda AMBOS os valores de baseCalculo (0 = "Hoje"/30 dias,
    1 = "5 dias úteis").
  - Nomenclatura: "ExpectativaMercadoMensais" (singular) ≠
    "ExpectativasMercadoAnuais" (plural).
  - Valores conferidos contra os boletins PDF de 19/jun e 17/jul/2026.

Carga incremental (24/09/2026):
  - Modo padrão: lê a última `Data` de cada tabela final, recoleta da API
    tudo a partir de (última Data − JANELA_SOBREPOSICAO_DIAS) e reescreve
    só esse trecho:
        final = final[Data < corte]  UNION ALL  staging
    via CREATE OR REPLACE TABLE (DDL, permitido no Sandbox — sem DML).
    A staging passa a guardar só a coleta da execução (auditoria).
  - Modo --completo: recoleta o histórico inteiro, ano a ano, e substitui
    a tabela final. Para primeira carga ou reconstrução.
  - O python-bcb saiu: a API direta é ~1s por endpoint no incremental e
    elimina a dependência (a 0.4.0 já quebrou o PTAX).
  - O servidor do BCB NÃO decodifica '+' como espaço — a URL do $filter é
    montada à mão com %20.

Como usar:
    python etl_focus.py              (incremental — o que roda no pipeline)
    python etl_focus.py --completo   (recarga total)
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    import os
    BASE_DIR = Path(os.getcwd()) / 'backend_etl' / 'scripts'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    import utils
except ImportError as e:
    logger.critical(f"Módulo não encontrado: {e}")
    sys.exit(1)

DATASET_ID = 'dados_macroeconomicos'
URL_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
TIMEOUT = 300
MAX_RETRIES = 3
JANELA_SOBREPOSICAO_DIAS = 14   # recoleta as 2 últimas semanas a cada execução
ANO_INICIO_COMPLETO = 1999      # primeira Data do Focus Anuais: 30/04/1999

COLUNAS_NUMERICAS = ['Media', 'Mediana', 'DesvioPadrao', 'Minimo', 'Maximo',
                     'numeroRespondentes']

ENDPOINTS = [
    {
        'endpoint': 'ExpectativasMercadoAnuais',
        'tabela': 'focus_expectativas_anuais',
        'colunas': ['Indicador', 'IndicadorDetalhe', 'Data', 'DataReferencia',
                    'Media', 'Mediana', 'DesvioPadrao', 'Minimo', 'Maximo',
                    'numeroRespondentes', 'baseCalculo'],
        'chave': ['Indicador', 'IndicadorDetalhe', 'Data', 'DataReferencia', 'baseCalculo'],
    },
    {
        'endpoint': 'ExpectativaMercadoMensais',
        'tabela': 'focus_expectativas_mensais',
        'colunas': ['Indicador', 'Data', 'DataReferencia', 'Media', 'Mediana',
                    'DesvioPadrao', 'Minimo', 'Maximo', 'numeroRespondentes',
                    'baseCalculo'],
        'chave': ['Indicador', 'Data', 'DataReferencia', 'baseCalculo'],
    },
    {
        'endpoint': 'ExpectativasMercadoInflacao12Meses',
        'tabela': 'focus_inflacao_12meses',
        'colunas': ['Indicador', 'Data', 'Suavizada', 'Media', 'Mediana',
                    'DesvioPadrao', 'Minimo', 'Maximo', 'numeroRespondentes',
                    'baseCalculo'],
        'chave': ['Indicador', 'Data', 'Suavizada', 'baseCalculo'],
    },
]


# ==============================================================================
# COLETA
# ==============================================================================
def buscar(endpoint: str, filtro: str) -> pd.DataFrame:
    """Uma chamada OData com $filter. Levanta exceção se todas as tentativas falharem."""
    filtro_url = filtro.replace(' ', '%20').replace("'", '%27')
    url = f"{URL_BASE}{endpoint}?$filter={filtro_url}&$format=json"
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return pd.DataFrame(resp.json()['value'])
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            logger.warning(f"  Tentativa {tentativa}/{MAX_RETRIES} falhou ({filtro}): {e}")
            if tentativa == MAX_RETRIES:
                raise
            time.sleep(10 * tentativa)


def coletar_desde(endpoint: str, corte: date) -> pd.DataFrame:
    return buscar(endpoint, f"Data ge '{corte:%Y-%m-%d}'")


def coletar_completo(endpoint: str) -> pd.DataFrame:
    """Histórico inteiro, um ano por chamada. Qualquer ano falhando aborta."""
    partes = []
    for ano in range(ANO_INICIO_COMPLETO, date.today().year + 1):
        df_ano = buscar(endpoint, f"Data ge '{ano}-01-01' and Data lt '{ano + 1}-01-01'")
        logger.info(f"  {ano}: {len(df_ano):,} linha(s)")
        partes.append(df_ano)
    return pd.concat(partes, ignore_index=True)


# ==============================================================================
# TRATAMENTO E VALIDAÇÃO
# ==============================================================================
def padronizar(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Fixa colunas e tipos para bater com o schema já existente no BigQuery."""
    df = df[cfg['colunas']].copy()
    df['Data'] = pd.to_datetime(df['Data'])
    for col in COLUNAS_NUMERICAS:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('float64')
    df['baseCalculo'] = df['baseCalculo'].astype('int64')
    for col in ['Indicador', 'IndicadorDetalhe', 'DataReferencia', 'Suavizada']:
        if col in df.columns:
            df[col] = df[col].astype('string')
    return df.drop_duplicates(subset=cfg['chave'])


def validar(df: pd.DataFrame, cfg: dict) -> bool:
    faltantes = [c for c in cfg['colunas'] if c not in df.columns]
    if faltantes:
        logger.error(f"  ❌ Colunas ausentes na resposta da API: {faltantes}")
        return False
    if df.empty:
        logger.error("  ❌ API devolveu 0 linhas.")
        return False
    bases = sorted(df['baseCalculo'].dropna().unique())
    if bases != [0, 1]:
        logger.warning(f"  ⚠️  baseCalculo = {bases} (esperado [0, 1]).")
    return True


# ==============================================================================
# BIGQUERY
# ==============================================================================
def ultima_data(client, tabela: str):
    try:
        df = client.query(
            f"SELECT MAX(Data) AS d, COUNT(*) AS n FROM `{utils.PROJECT_ID}.{DATASET_ID}.{tabela}`"
        ).to_dataframe()
        return pd.Timestamp(df['d'][0]).date(), int(df['n'][0])
    except Exception:
        return None, 0


def mesclar_incremental(client, cfg: dict, corte: date, n_antes: int) -> bool:
    """final = final[Data < corte] ∪ staging, numa única instrução DDL."""
    final = f"{utils.PROJECT_ID}.{DATASET_ID}.{cfg['tabela']}"
    staging = f"{final}_staging"
    cols = ', '.join(cfg['colunas'])
    client.query(f"""
        CREATE OR REPLACE TABLE `{final}` AS
        SELECT {cols} FROM `{final}` WHERE Data < DATETIME '{corte:%Y-%m-%d}'
        UNION ALL
        SELECT {cols} FROM `{staging}`
    """).result()

    n_depois = list(client.query(f"SELECT COUNT(*) AS n FROM `{final}`").result())[0].n
    logger.info(f"  {cfg['tabela']}: {n_antes:,} → {n_depois:,} linha(s) (+{n_depois - n_antes:,})")
    if n_depois < n_antes:
        logger.error("  ❌ A tabela final encolheu após a mescla — verificar.")
        return False
    return True


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================
def processar(client, cfg: dict, completo: bool) -> bool:
    logger.info(f"\n--- {cfg['endpoint']} → {cfg['tabela']} ---")
    ultima, n_antes = (None, 0) if completo else ultima_data(client, cfg['tabela'])

    try:
        if ultima is None:
            if not completo:
                logger.warning("  Tabela final não encontrada — fazendo carga completa.")
            df = coletar_completo(cfg['endpoint'])
        else:
            corte = ultima - timedelta(days=JANELA_SOBREPOSICAO_DIAS)
            logger.info(f"  Última Data no BigQuery: {ultima} | recoletando desde {corte}")
            df = coletar_desde(cfg['endpoint'], corte)
    except Exception as e:
        logger.error(f"  ❌ Coleta falhou: {e}")
        return False

    if not validar(df, cfg):
        return False
    df = padronizar(df, cfg)
    logger.info(f"  Coletadas {len(df):,} linha(s) | Data {df['Data'].min():%Y-%m-%d} → {df['Data'].max():%Y-%m-%d}")

    if ultima is not None and df['Data'].max().date() < ultima:
        logger.error("  ❌ A API devolveu dados mais antigos que os do BigQuery — abortando.")
        return False

    if not utils.subir_para_bigquery(df, DATASET_ID, f"{cfg['tabela']}_staging", if_exists='replace'):
        return False

    if ultima is None:
        return utils.subir_para_bigquery(df, DATASET_ID, cfg['tabela'], if_exists='replace')
    return mesclar_incremental(client, cfg, corte, n_antes)


def executar(completo: bool = False) -> bool:
    logger.info("=" * 60)
    logger.info(f"ETL Focus — Expectativas de Mercado (BCB) | modo "
                f"{'COMPLETO' if completo else 'incremental'}")
    logger.info("=" * 60)

    client = utils.get_bq_client()
    resultados = [processar(client, cfg, completo) for cfg in ENDPOINTS]

    ok = all(resultados)
    logger.info("\n" + "=" * 60)
    logger.info("✅ ETL Focus concluído." if ok else "❌ ETL Focus terminou com falhas.")
    logger.info("=" * 60)
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL Focus — Expectativas de Mercado")
    parser.add_argument("--completo", action="store_true",
                        help="Recoleta o histórico inteiro e substitui as tabelas finais.")
    args = parser.parse_args()
    sys.exit(0 if executar(completo=args.completo) else 1)
