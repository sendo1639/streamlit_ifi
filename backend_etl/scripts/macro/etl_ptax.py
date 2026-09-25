"""
ETL: PTAX (Câmbio Institucional) — BCB
=========================================
Fonte: API Olinda do BCB, função CotacaoMoedaPeriodo, chamada direto via
requests (sem python-bcb). Moedas: USD, EUR (decidido em 22/07/2026).

Diagnóstico do "bug do PTAX" (24/09/2026):
  - A API em si funciona: devolve o histórico inteiro (2000 → hoje, ~65 mil
    linhas por moeda, todos os boletins) numa chamada só.
  - O problema era o python-bcb 0.4.0: ele converte datas ISO
    ('2026-07-13' ou date()) para '7/13/2026', formato que a API aceita
    sem erro mas responde com lista VAZIA. Por isso a dependência saiu.
  - Formato exigido pela API: 'MM-DD-AAAA', entre aspas simples, na URL.
    O servidor NÃO decodifica '+' como espaço — a URL é montada à mão.

Boletins: a tabela final guarda só o boletim de "Fechamento" (igualdade
exata). Até 30/06/2011 a API também devolve "Fechamento Interbancário",
que o filtro antigo (.str.contains) deixava passar — 2 linhas por dia.
Em 23/04/2025 o BCB publicou o Fechamento duas vezes (valores idênticos),
por isso a deduplicação é por (moeda, data), mantendo o último horário.

Carga: recarga completa a cada execução (volume pequeno, ~13 mil linhas
na final) — idempotente, sem risco de duplicar ou deixar buraco.

Como usar:
    python etl_ptax.py
    ou no Spyder: %run etl_ptax.py
"""

import sys
import time
import logging
from pathlib import Path
from datetime import date

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
TABELA_FINAL = 'ptax_cotacoes'
TABELA_STAGING = 'ptax_cotacoes_staging'
MOEDAS = ['USD', 'EUR']
DATA_INICIO_HISTORICO = date(2000, 1, 1)
TIMEOUT = 180
MAX_RETRIES = 3

URL_PERIODO = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
    "dataFinalCotacao=@dataFinalCotacao)"
)


# ==============================================================================
# COLETA
# ==============================================================================
def buscar_periodo(moeda: str, ini: date, fim: date) -> pd.DataFrame:
    """Uma chamada à API para [ini, fim]. Levanta exceção se todas as tentativas falharem."""
    url = (
        f"{URL_PERIODO}?@moeda='{moeda}'"
        f"&@dataInicial='{ini:%m-%d-%Y}'"
        f"&@dataFinalCotacao='{fim:%m-%d-%Y}'"
        f"&$format=json"
    )
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return pd.DataFrame(resp.json()['value'])
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            logger.warning(f"  {moeda} {ini}..{fim}: tentativa {tentativa}/{MAX_RETRIES} falhou — {e}")
            if tentativa == MAX_RETRIES:
                raise
            time.sleep(5 * tentativa)


def coletar_moeda(moeda: str) -> pd.DataFrame:
    """Histórico inteiro numa chamada; se falhar, cai para coleta ano a ano."""
    hoje = date.today()
    logger.info(f"Coletando {moeda} ({DATA_INICIO_HISTORICO} → {hoje})...")

    try:
        df = buscar_periodo(moeda, DATA_INICIO_HISTORICO, hoje)
        logger.info(f"  ✅ Coleta única: {len(df):,} linha(s)")
        return df
    except Exception:
        logger.warning("  ⚠️  Coleta única falhou — tentando ano a ano...")

    partes = []
    for ano in range(DATA_INICIO_HISTORICO.year, hoje.year + 1):
        fim = date(ano, 12, 31) if ano < hoje.year else hoje
        try:
            partes.append(buscar_periodo(moeda, date(ano, 1, 1), fim))
        except Exception:
            # Um ano faltando corromperia a recarga completa — aborta a moeda
            logger.error(f"  ❌ {moeda} {ano}: falhou em todas as tentativas — abortando {moeda}.")
            return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    logger.info(f"  ✅ Coleta ano a ano: {len(df):,} linha(s)")
    return df


# ==============================================================================
# TRATAMENTO E VALIDAÇÃO
# ==============================================================================
def filtrar_fechamento(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Só boletim de Fechamento, uma linha por (moeda, data)."""
    df = df_bruto[df_bruto['tipoBoletim'].str.strip() == 'Fechamento'].copy()
    df['data'] = df['dataHoraCotacao'].dt.normalize()

    df = df.sort_values('dataHoraCotacao')
    n_antes = len(df)
    df = df.drop_duplicates(subset=['moeda', 'data'], keep='last')
    if n_antes > len(df):
        logger.info(f"{n_antes - len(df):,} fechamento(s) repetido(s) no mesmo dia removido(s)")

    colunas = ['data', 'moeda', 'cotacaoCompra', 'cotacaoVenda',
               'paridadeCompra', 'paridadeVenda', 'dataHoraCotacao', 'tipoBoletim']
    return df[colunas].sort_values(['moeda', 'data']).reset_index(drop=True)


def validar(df_final: pd.DataFrame) -> bool:
    ok = True
    for moeda in MOEDAS:
        d = df_final[df_final['moeda'] == moeda]
        if d.empty:
            logger.error(f"  ❌ {moeda}: nenhuma linha na tabela final.")
            ok = False
            continue
        anos = d['data'].dt.year.nunique()
        esperado = date.today().year - DATA_INICIO_HISTORICO.year + 1
        atraso = (pd.Timestamp(date.today()) - d['data'].max()).days
        logger.info(f"  {moeda}: {len(d):,} dias | {d['data'].min():%Y-%m-%d} → "
                    f"{d['data'].max():%Y-%m-%d} | {anos}/{esperado} anos")
        if anos < esperado:
            logger.error(f"  ❌ {moeda}: faltam anos na série.")
            ok = False
        if atraso > 7:
            logger.error(f"  ❌ {moeda}: última cotação tem {atraso} dias.")
            ok = False
    return ok


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================
def executar() -> bool:
    logger.info("=" * 60)
    logger.info("ETL PTAX — Câmbio Institucional (BCB)")
    logger.info("=" * 60)

    partes = []
    for moeda in MOEDAS:
        df_moeda = coletar_moeda(moeda)
        if df_moeda.empty:
            logger.error("❌ Coleta incompleta — nada foi gravado no BigQuery.")
            return False
        df_moeda['moeda'] = moeda
        partes.append(df_moeda)

    df_bruto = pd.concat(partes, ignore_index=True)
    df_bruto['dataHoraCotacao'] = pd.to_datetime(df_bruto['dataHoraCotacao'])
    logger.info(f"Total bruto (todas as moedas e boletins): {len(df_bruto):,} linha(s)")

    df_final = filtrar_fechamento(df_bruto)
    if not validar(df_final):
        logger.error("❌ Validação falhou — nada foi gravado no BigQuery.")
        return False

    logger.info("Subindo staging (bruto, todos os boletins)...")
    if not utils.subir_para_bigquery(df_bruto, DATASET_ID, TABELA_STAGING, if_exists='replace'):
        return False

    logger.info(f"Subindo final (só Fechamento): {len(df_final):,} linha(s)...")
    if not utils.subir_para_bigquery(df_final, DATASET_ID, TABELA_FINAL, if_exists='replace'):
        return False

    logger.info("=" * 60)
    logger.info(f"✅ ETL PTAX concluído — {len(df_final):,} linha(s) na tabela final")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    sys.exit(0 if executar() else 1)
