"""
Recuperação de emergência — verificar e salvar anbima_ettj_staging
========================================================================
A anbima_ettj já expirou (404 confirmado). Este script:
  1. Salva IMEDIATAMENTE um backup local do que existir na staging,
     independente do conteúdo — prioridade máxima, antes de qualquer
     outra análise, já que ela mesma expira em poucos dias.
  2. Depois do backup garantido, gera um diagnóstico do que ela
     realmente contém (datas cobertas, nº de linhas) para avaliarmos
     o tamanho real da perda.

Como usar:
    %run "CAMINHO\\recuperar_anbima_staging.py"
"""

import logging
from datetime import date
import pandas as pd

import sys, os
from pathlib import Path

try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()) / 'backend_etl' / 'scripts'
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import utils

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

DATASET_ID = 'dados_macroeconomicos'
TABELA = 'anbima_ettj_staging'
PASTA_SAIDA = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data\backup"

client = utils.get_bq_client()

# ─── PASSO 1 — Backup local IMEDIATO, sem análise prévia ────────────────────
logger.info(f"Baixando TODO o conteúdo de {TABELA} (prioridade: preservar antes de tudo)...")

try:
    df = client.query(f"""
        SELECT * FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA}`
    """).to_dataframe()

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = os.path.join(PASTA_SAIDA, f"EMERGENCIA_backup_{TABELA}_{date.today():%Y%m%d}.xlsx")
    df.to_excel(caminho, index=False)

    logger.info(f"✅ Backup salvo em: {caminho}")
    logger.info(f"✅ {len(df):,} linha(s) preservadas — independente do que vier a seguir.")

except Exception as e:
    logger.critical(f"❌ FALHA AO BAIXAR/SALVAR: {e}")
    logger.critical("   Isso é crítico — pode significar que a staging já expirou também.")
    sys.exit(1)

# ─── PASSO 2 — Diagnóstico: o que realmente está aqui? ──────────────────────
print("\n" + "=" * 74)
print("DIAGNÓSTICO — conteúdo real da anbima_ettj_staging")
print("=" * 74)

if df.empty:
    print("\n⚠️  Tabela vazia. Não há nada a recuperar daqui.")
else:
    print(f"\nTotal de linhas: {len(df):,}")
    print(f"Colunas: {list(df.columns)}")

    if 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
        datas_unicas = sorted(df['data'].dt.date.unique())
        print(f"\nDatas distintas cobertas: {len(datas_unicas)}")
        print(f"Data mais antiga: {datas_unicas[0]}")
        print(f"Data mais recente: {datas_unicas[-1]}")
        print(f"\nTodas as datas presentes:")
        for d in datas_unicas:
            print(f"  {d}")
    else:
        print("\n⚠️  Coluna 'data' não encontrada — inspecionar estrutura manualmente:")
        print(df.head(10).to_string())

print("\n" + "=" * 74)
print("👉 Compare a lista de datas acima com o período que a anbima_ettj")
print("   principal deveria ter (~25/mai a ~22/jul). Qualquer dia útil")
print("   ausente aqui é uma perda que só seria recuperável, em tese,")
print("   pelo etl_anbima_historico.py (fonte B3, metodologia diferente).")
print("=" * 74)