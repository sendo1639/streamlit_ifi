"""
Congela o histórico do Auxílio Brasil em arquivo local — roda uma vez só.
=============================================================================
"""

import sys, os
from pathlib import Path
import pandas as pd

try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()) / 'backend_etl' / 'scripts'
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

sys.path.append(str(Path(BASE_DIR) / 'social'))
from etl_historico_pab_ae import processar_pab_legacy, CONFIG_HISTORICO

CAMINHO_SAIDA = Path(BASE_DIR) / 'data' / 'historico_auxilio_brasil_congelado.csv'

print("Baixando o histórico do Auxílio Brasil pela última vez...")
dfs = [processar_pab_legacy(c) for c in CONFIG_HISTORICO]
df_final = pd.concat([d for d in dfs if not d.empty], ignore_index=True)

if df_final.empty:
    print("❌ Nada foi baixado — não sobrescrevendo o arquivo existente.")
else:
    CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(CAMINHO_SAIDA, index=False, encoding='utf-8')
    print(f"✅ {len(df_final)} linha(s) congeladas em: {CAMINHO_SAIDA}")