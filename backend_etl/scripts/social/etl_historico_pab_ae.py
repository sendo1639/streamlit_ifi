"""
ETL: Histórico Auxílio Brasil — versão estática (sem rede)
=============================================================
O Auxílio Brasil foi extinto (virou Bolsa Família) — os dados
históricos são fixos e não mudam mais. Lê de um arquivo estático já
congelado no repositório (gerado via congelar_historico_pab.py),
em vez de buscar da fonte externa — que estava sendo bloqueada no
GitHub Actions (provavelmente por IP de datacenter).

Continua rodando DEPOIS do etl_social.py no pipeline, porque aquele
script usa if_exists='replace' e apaga a tabela inteira toda vez —
esse histórico precisa ser reanexado (append) a cada execução.

Como usar:
    python etl_historico_pab_ae.py
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

import utils

DATASET_ID = 'dados_sociais'
TABELA_ID = 'base_consolidada_pbf_cadun'
CAMINHO_ARQUIVO = Path(BASE_DIR) / 'data' / 'historico_auxilio_brasil_congelado.csv'

if __name__ == "__main__":
    print("Carregando histórico congelado do Auxílio Brasil (arquivo local)...")

    if not CAMINHO_ARQUIVO.exists():
        print(f"❌ Arquivo não encontrado: {CAMINHO_ARQUIVO}")
        sys.exit(1)

    df_final = pd.read_csv(CAMINHO_ARQUIVO)
    df_final['data'] = pd.to_datetime(df_final['data'])
    if 'data_carga' in df_final.columns:
        df_final['data_carga'] = pd.to_datetime(df_final['data_carga'])

    print(f"✅ {len(df_final)} linha(s) carregadas do arquivo.")
    print(f"Enviando para o BigQuery ({DATASET_ID}.{TABELA_ID}, append)...")

    utils.subir_para_bigquery(df=df_final, dataset=DATASET_ID, tabela=TABELA_ID, if_exists='append')