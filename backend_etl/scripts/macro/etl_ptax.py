"""
ETL: PTAX (Câmbio Institucional) — BCB
=========================================
Fonte: CotacaoMoedaPeriodo (python-bcb / PTAX), filtrada para o
boletim de Fechamento apenas — decisão tomada em 22/07/2026.

Moedas coletadas: USD, EUR (decidido em 22/07/2026).

Validado ao vivo:
  - CotacaoMoedaPeriodo(moeda, dataInicial, dataFinalCotacao) funciona
    para qualquer moeda (testado USD e EUR, valores batendo exato).
  - tipoBoletim vem como "Fechamento" (via essa função) — nome
    inconsistente com "Fechamento PTAX" que aparece em CotacaoMoedaDia,
    por isso o filtro usa .str.contains(), não igualdade exata.
  - NÃO testamos ainda se a função aceita um intervalo de datas muito
    longo numa chamada só — por isso este script tenta o histórico
    inteiro primeiro e cai para coleta por ano se algo parecer errado.

Como usar:
    python etl_ptax.py
    ou no Spyder: %run etl_ptax.py
"""

import sys
import logging
from pathlib import Path
from datetime import date

import pandas as pd
from bcb import PTAX

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
MOEDAS = ['USD', 'EUR']
DATA_INICIO_HISTORICO = '2000-01-01'  # PTAX existe desde muito antes; ajustável

ptax = PTAX()
ep_moeda_periodo = ptax.get_endpoint('CotacaoMoedaPeriodo')


def coletar_moeda_completa(moeda: str) -> pd.DataFrame:
    """Tenta a série inteira de uma vez; cai para coleta por ano se necessário."""
    hoje = date.today().isoformat()
    logger.info(f"Coletando {moeda} — tentando histórico completo de uma vez...")

    try:
        df = ep_moeda_periodo.get(
            moeda=moeda, dataInicial=DATA_INICIO_HISTORICO, dataFinalCotacao=hoje
        )
        # Sinal de suspeita: poucos anos de cobertura pra um pedido de 25+ anos
        if not df.empty:
            df['dataHoraCotacao'] = pd.to_datetime(df['dataHoraCotacao'])
            anos_cobertos = df['dataHoraCotacao'].dt.year.nunique()
            if anos_cobertos >= 15:
                logger.info(f"  ✅ Coleta única funcionou — {len(df):,} linha(s), "
                            f"{anos_cobertos} ano(s) distintos")
                return df
            else:
                logger.warning(
                    f"  ⚠️  Só {anos_cobertos} ano(s) cobertos — "
                    f"suspeito de limite na chamada. Tentando por ano..."
                )
        else:
            logger.warning("  ⚠️  Retorno vazio — tentando por ano...")
    except Exception as e:
        logger.warning(f"  ⚠️  Falhou ({e}) — tentando coleta por ano...")

    # --- Fallback: coleta ano a ano ---
    partes = []
    ano_inicio = int(DATA_INICIO_HISTORICO[:4])
    ano_fim = date.today().year

    for ano in range(ano_inicio, ano_fim + 1):
        ini = f"{ano}-01-01"
        fim = f"{ano}-12-31" if ano < ano_fim else date.today().isoformat()
        try:
            df_ano = ep_moeda_periodo.get(
                moeda=moeda, dataInicial=ini, dataFinalCotacao=fim
            )
            if not df_ano.empty:
                partes.append(df_ano)
                logger.info(f"  {ano}: {len(df_ano):,} linha(s)")
        except Exception as e:
            logger.warning(f"  {ano}: erro — {e}")

    df_final = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    logger.info(f"  Total via fallback por ano: {len(df_final):,} linha(s)")
    return df_final


def executar():
    logger.info("=" * 60)
    logger.info("ETL PTAX — Câmbio Institucional (BCB)")
    logger.info("=" * 60)

    partes_moedas = []
    for moeda in MOEDAS:
        df_moeda = coletar_moeda_completa(moeda)
        if not df_moeda.empty:
            df_moeda['moeda'] = moeda
            partes_moedas.append(df_moeda)

    if not partes_moedas:
        logger.error("❌ Nenhuma moeda coletada — abortando carga.")
        return

    df_bruto = pd.concat(partes_moedas, ignore_index=True)
    logger.info(f"\nTotal bruto (todas moedas, todos boletins): {len(df_bruto):,} linha(s)")

    # --- Staging: tudo que veio, sem filtro ---
    logger.info("Subindo staging (bruto, todos os boletins)...")
    utils.subir_para_bigquery(
        df_bruto, DATASET_ID, 'ptax_cotacoes_staging', if_exists='replace'
    )

    # --- Final: só Fechamento, deduplicado ---
    df_bruto['tipoBoletim'] = df_bruto['tipoBoletim'].astype(str)
    df_fechamento = df_bruto[
        df_bruto['tipoBoletim'].str.contains('Fechamento', case=False, na=False)
    ].copy()

    df_final = df_fechamento.drop_duplicates(subset=['moeda', 'dataHoraCotacao'])
    n_dup = len(df_fechamento) - len(df_final)
    if n_dup > 0:
        logger.info(f"{n_dup:,} duplicata(s) removida(s) na chave natural")

    logger.info(f"Subindo final (só Fechamento): {len(df_final):,} linha(s)...")
    utils.subir_para_bigquery(
        df_final, DATASET_ID, 'ptax_cotacoes', if_exists='replace'
    )

    logger.info("\n" + "=" * 60)
    logger.info(f"✅ ETL PTAX concluído — {len(df_final):,} linha(s) na tabela final")
    logger.info("=" * 60)


if __name__ == "__main__":
    executar()