"""
ETL: Boletim Focus (Expectativas de Mercado) — BCB
=====================================================
Fontes (todas via python-bcb / OData Expectativas):
    ExpectativasMercadoAnuais            -> focus_expectativas_anuais(_staging)
    ExpectativaMercadoMensais            -> focus_expectativas_mensais(_staging)
    ExpectativasMercadoInflacao12Meses   -> focus_inflacao_12meses(_staging)

Decisões de arquitetura (22/07/2026):
  - Coleta SEM filtro de indicador — puxa o endpoint inteiro. O volume é
    trivial pro BigQuery (~48k linhas só de IPCA/Anuais) e deixa a base
    pronta pra qualquer indicador que quisermos mostrar no futuro.
  - Guarda AMBOS os valores de baseCalculo (0 = "Hoje"/30 dias,
    1 = "5 dias úteis") — mais flexibilidade analítica, custo baixo.
  - Padrão staging + final, igual ANBIMA: staging recebe a coleta bruta
    (para auditoria), final recebe deduplicado pela chave natural.

Validado ao vivo em 22/07/2026:
  - Nomenclatura correta: "ExpectativaMercadoMensais" (singular
    "Expectativa"), diferente de "ExpectativasMercadoAnuais" (plural).
  - baseCalculo e Suavizada conferidos número a número contra dois
    boletins PDF oficiais (19/jun e 17/jul/2026).
  - .collect() pagina sozinho sem truncar (48.052 linhas para IPCA,
    volta até 2000, sem necessidade de .limit()).

Como usar:
    python etl_focus.py
    ou no Spyder: %run etl_focus.py
"""

import sys
import logging
from pathlib import Path

import pandas as pd
from bcb import Expectativas

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

api = Expectativas(timeout=300)


# ==============================================================================
# COLETA — um endpoint inteiro por vez, sem filtro de indicador
# ==============================================================================
def coletar_endpoint(nome_endpoint: str, tentativas: int = 3) -> pd.DataFrame:
    """
    Coleta um endpoint inteiro, sem filtro. Com retry e timeout crescente
    para endpoints mais densos (ex: Mensais, que tem granularidade mensal
    de DataReferencia e por isso gera bem mais linhas que o Anuais).
    """
    timeouts = [120, 300, 600]
    for tentativa in range(1, tentativas + 1):
        timeout_atual = timeouts[min(tentativa - 1, len(timeouts) - 1)]
        logger.info(f"Coletando {nome_endpoint} (tentativa {tentativa}/{tentativas}, "
                    f"timeout={timeout_atual}s)...")
        try:
            ep = api.get_endpoint(nome_endpoint)
            df = ep.query().collect(timeout=timeout_atual)
            logger.info(f"  ✅ {len(df):,} linha(s) | "
                        f"{df['Indicador'].nunique()} indicador(es) distinto(s)")
            return df
        except Exception as e:
            logger.warning(f"  ⚠️  Tentativa {tentativa} falhou: {e}")
            if tentativa == tentativas:
                logger.error(f"  ❌ Todas as tentativas falharam para {nome_endpoint}.")
                return pd.DataFrame()
    return pd.DataFrame()


# ==============================================================================
# VALIDAÇÃO
# ==============================================================================
def validar(df: pd.DataFrame, nome: str, colunas_esperadas: list) -> bool:
    if df.empty:
        logger.warning(f"  ⚠️  {nome}: DataFrame vazio — pulando carga.")
        return False

    faltantes = [c for c in colunas_esperadas if c not in df.columns]
    if faltantes:
        logger.error(f"  ❌ {nome}: colunas esperadas ausentes: {faltantes}")
        return False

    # Checa se baseCalculo tem os dois valores esperados (0 e 1)
    if 'baseCalculo' in df.columns:
        valores_base = sorted(df['baseCalculo'].dropna().unique())
        if valores_base != [0, 1]:
            logger.warning(
                f"  ⚠️  {nome}: baseCalculo tem valores {valores_base} "
                f"(esperado [0, 1]) — verificar se a coleta veio completa."
            )

    logger.info(f"  ✅ {nome}: validação OK — {len(df):,} linhas")
    return True


# ==============================================================================
# CARGA — staging (bruto) + final (deduplicado pela chave natural)
# ==============================================================================
def carregar(df: pd.DataFrame, tabela_final: str, chave_natural: list):
    tabela_staging = f"{tabela_final}_staging"

    logger.info(f"  Subindo staging: {tabela_staging}...")
    utils.subir_para_bigquery(
        df, DATASET_ID, tabela_staging, if_exists='replace'
    )

    df_dedup = df.drop_duplicates(subset=chave_natural)
    n_dup = len(df) - len(df_dedup)
    if n_dup > 0:
        logger.info(f"  {n_dup:,} linha(s) duplicada(s) removida(s) na chave natural")

    logger.info(f"  Subindo final: {tabela_final}...")
    utils.subir_para_bigquery(
        df_dedup, DATASET_ID, tabela_final, if_exists='replace'
    )
    logger.info(f"  ✅ {tabela_final}: {len(df_dedup):,} linha(s) carregada(s)")


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================
def executar():
    logger.info("=" * 60)
    logger.info("ETL Focus — Expectativas de Mercado (BCB)")
    logger.info("=" * 60)

    # --- Anuais ---
    logger.info("\n--- ExpectativasMercadoAnuais ---")
    df_anuais = coletar_endpoint("ExpectativasMercadoAnuais")
    colunas_anuais = [
        'Indicador', 'IndicadorDetalhe', 'Data', 'DataReferencia',
        'Media', 'Mediana', 'DesvioPadrao', 'Minimo', 'Maximo',
        'numeroRespondentes', 'baseCalculo'
    ]
    if validar(df_anuais, "Anuais", colunas_anuais):
        carregar(
            df_anuais, "focus_expectativas_anuais",
            chave_natural=['Indicador', 'IndicadorDetalhe', 'Data',
                           'DataReferencia', 'baseCalculo']
        )

    # --- Mensais ---
    logger.info("\n--- ExpectativaMercadoMensais ---")
    df_mensais = coletar_endpoint("ExpectativaMercadoMensais")
    colunas_mensais = [
        'Indicador', 'Data', 'DataReferencia', 'Media', 'Mediana',
        'DesvioPadrao', 'Minimo', 'Maximo', 'numeroRespondentes', 'baseCalculo'
    ]
    if validar(df_mensais, "Mensais", colunas_mensais):
        carregar(
            df_mensais, "focus_expectativas_mensais",
            chave_natural=['Indicador', 'Data', 'DataReferencia', 'baseCalculo']
        )

    # --- Inflação 12 Meses ---
    logger.info("\n--- ExpectativasMercadoInflacao12Meses ---")
    df_infl12 = coletar_endpoint("ExpectativasMercadoInflacao12Meses")
    colunas_infl12 = [
        'Indicador', 'Data', 'Suavizada', 'Media', 'Mediana',
        'DesvioPadrao', 'Minimo', 'Maximo', 'numeroRespondentes', 'baseCalculo'
    ]
    if validar(df_infl12, "Inflação 12 Meses", colunas_infl12):
        carregar(
            df_infl12, "focus_inflacao_12meses",
            chave_natural=['Indicador', 'Data', 'Suavizada', 'baseCalculo']
        )

    logger.info("\n" + "=" * 60)
    logger.info("✅ ETL Focus concluído.")
    logger.info("=" * 60)


if __name__ == "__main__":
    executar()