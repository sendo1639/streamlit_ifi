"""
Renovação de tabelas no BigQuery Sandbox — evita expiração de 60 dias
========================================================================
Usa a mesma autenticação híbrida já definida em utils.get_bq_client()
(Streamlit Secrets -> variável de ambiente do GitHub Actions -> JSON
local) — funciona nos dois ambientes sem código extra.

Motivo desta peça existir separada de qualquer ETL: a expiração conta
a partir da CRIAÇÃO da tabela e nenhuma carga a reinicia — nem
if_exists='append', nem if_exists='replace' do pandas-gbq, nem
WRITE_TRUNCATE (os dois últimos sobrescrevem os dados mas preservam o
objeto). Confirmado em 24/09/2026 pelos metadados: banco_central_sgs e
rtn_* eram regravadas todo dia e mesmo assim expira = criada + 60 dias.
Só recriar a tabela (DROP + CREATE) reinicia o relógio.

Mecanismo: varre TODAS as tabelas de TODOS os datasets do projeto
(até 24/09/2026 só varria dados_macroeconomicos — as tabelas de
estatais em dados_fiscais expiraram por isso). Para
qualquer uma com <= LIMIAR_DIAS de expiração restante, copia para uma
tabela temporária, confirma a contagem de linhas, apaga a original,
recria com o mesmo nome (nova expiração de 60 dias), confirma de novo,
e só então limpa a temporária. Nunca apaga sem confirmar a cópia antes.

Como usar:
    python renovar_tabelas_bigquery.py
    (Spyder): %run renovar_tabelas_bigquery.py
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()) / 'backend_etl' / 'scripts'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    import utils
except ImportError as e:
    logger.critical(f"Módulo não encontrado: {e}")
    sys.exit(1)

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
LIMIAR_DIAS = 5  # renova quando restarem <= 5 dias dos 60 (decidido em 22/07/2026)
SUFIXO_TEMP = '_renovacao_tmp'


def renovar_tabela(client, dataset_id: str, tabela_id: str) -> bool:
    """Renova uma tabela, resetando sua expiração de 60 dias."""
    tabela_original = f"{utils.PROJECT_ID}.{dataset_id}.{tabela_id}"
    tabela_temp     = f"{utils.PROJECT_ID}.{dataset_id}.{tabela_id}{SUFIXO_TEMP}"

    logger.info(f"  Renovando: {tabela_original}")

    try:
        n_original = list(client.query(
            f"SELECT COUNT(*) as n FROM `{tabela_original}`"
        ).result())[0].n
    except Exception as e:
        logger.error(f"    ❌ Não foi possível ler a tabela original: {e}")
        return False

    if n_original == 0:
        logger.warning(f"    ⚠️  Tabela vazia — abortando por segurança.")
        return False

    try:
        client.query(f"""
            CREATE OR REPLACE TABLE `{tabela_temp}` AS
            SELECT * FROM `{tabela_original}`
        """).result()
        n_temp = list(client.query(
            f"SELECT COUNT(*) as n FROM `{tabela_temp}`"
        ).result())[0].n
    except Exception as e:
        logger.error(f"    ❌ Falha ao copiar/verificar tabela temporária: {e}")
        return False

    if n_temp != n_original:
        logger.error(
            f"    ❌ ABORTANDO: contagem não bate "
            f"(original={n_original:,}, temp={n_temp:,}). Original preservada."
        )
        return False

    try:
        client.delete_table(tabela_original)
        client.query(f"""
            CREATE TABLE `{tabela_original}` AS
            SELECT * FROM `{tabela_temp}`
        """).result()
        n_final = list(client.query(
            f"SELECT COUNT(*) as n FROM `{tabela_original}`"
        ).result())[0].n
    except Exception as e:
        logger.critical(
            f"    ❌ CRÍTICO: falha ao recriar '{tabela_id}'. "
            f"Dados seguros em '{tabela_temp}' — NÃO apagar manualmente. Erro: {e}"
        )
        return False

    if n_final != n_original:
        logger.critical(
            f"    ❌ CRÍTICO: tabela final tem {n_final:,} linhas, "
            f"esperado {n_original:,}. NÃO apague '{tabela_temp}'."
        )
        return False

    client.delete_table(tabela_temp)
    logger.info(f"    ✅ Renovada — {n_final:,} linha(s), expiração resetada.")
    return True


def executar() -> bool:
    logger.info("=" * 60)
    logger.info("RENOVAÇÃO DE TABELAS — proteção contra expiração (Sandbox)")
    logger.info("=" * 60)

    client = utils.get_bq_client()
    agora = datetime.now(timezone.utc)
    falhas = []

    datasets = [d.dataset_id for d in client.list_datasets()]
    logger.info(f"Datasets encontrados: {datasets}")

    for dataset_id in datasets:
        logger.info(f"\nDataset: {dataset_id}")
        try:
            tabelas = list(client.list_tables(f"{utils.PROJECT_ID}.{dataset_id}"))
        except Exception as e:
            logger.error(f"  ❌ Não foi possível listar tabelas: {e}")
            falhas.append(dataset_id)
            continue

        for item in tabelas:
            if item.table_id.endswith(SUFIXO_TEMP):
                logger.critical(
                    f"  {item.table_id}: temporária de uma renovação que falhou — "
                    f"conferir a original manualmente antes de apagar."
                )
                falhas.append(item.table_id)
                continue

            tabela_ref = client.get_table(item.reference)
            if tabela_ref.expires is None:
                logger.info(f"  {item.table_id}: sem expiração — ignorando.")
                continue

            dias_restantes = (tabela_ref.expires - agora).days
            if dias_restantes <= LIMIAR_DIAS:
                logger.warning(
                    f"  {item.table_id}: expira em {dias_restantes} dia(s) "
                    f"— renovando..."
                )
                if not renovar_tabela(client, dataset_id, item.table_id):
                    falhas.append(item.table_id)
            else:
                logger.info(
                    f"  {item.table_id}: expira em {dias_restantes} dia(s) — OK."
                )

    logger.info("\n" + "=" * 60)
    if falhas:
        logger.error(f"❌ Varredura concluída com falhas: {falhas}")
    else:
        logger.info("✅ Varredura concluída.")
    logger.info("=" * 60)
    return not falhas


if __name__ == "__main__":
    sys.exit(0 if executar() else 1)