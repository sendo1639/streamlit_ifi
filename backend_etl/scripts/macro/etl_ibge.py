"""
ETL: Indicadores IBGE (SIDRA)
===============================
Coleta tabelas do SIDRA e grava tudo numa tabela longa:
    dados_macroeconomicos.ibge_sidra

APIs usadas (direto via requests, sem sidrapy):
  - Metadados/períodos: servicodados.ibge.gov.br/api/v3/agregados/{t}/...
  - Valores:            apisidra.ibge.gov.br/values/t/{t}/n1/all/v/.../p/.../c.../all
O sidrapy é só um invólucro dessa mesma URL e não trata o limite da API
(50.000 valores por consulta — a 7060 sozinha tem ~146 mil), então a
coleta é fatiada por intervalos de período aqui mesmo.

Tabelas (códigos validados contra os metadados do IBGE em 24/09/2026 —
PIM, PMS e PMC já na base 2022=100): ver TABELAS abaixo. Para incluir
outra, basta acrescentar uma entrada — conferir antes o código em
https://servicodados.ibge.gov.br/api/v3/agregados/{t}/metadados

Convenção de data: `data` = 1º dia do ÚLTIMO mês coberto pelo período.
  - Mensal 202607            → 2026-07-01
  - Trimestre móvel 202607   → 2026-07-01 (mai-jun-jul/2026)
  - Trimestral 202602        → 2026-06-01 (2º trimestre de 2026)
O código original do SIDRA fica em `periodo_codigo` e o rótulo em `periodo`.

Carga: recarga completa a cada execução (replace). Se uma tabela falhar,
as linhas dela da versão anterior do BigQuery são mantidas.

Como usar:
    python etl_ibge.py
"""

import sys
import time
import logging
from pathlib import Path
from datetime import date

import pandas as pd
import requests
from google.api_core.exceptions import NotFound

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
    import transformations as tr
except ImportError as e:
    logger.critical(f"Módulo não encontrado: {e}")
    sys.exit(1)

DATASET_ID = 'dados_macroeconomicos'
TABELA_ID = 'ibge_sidra'

URL_METADADOS = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/metadados"
URL_PERIODOS = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/periodos"
URL_VALORES = "https://apisidra.ibge.gov.br/values"
LIMITE_VALORES = 45_000   # limite da API é 50.000 por consulta — margem de segurança
TIMEOUT = 180
MAX_RETRIES = 3

# Atraso máximo aceitável da última observação, por periodicidade (dias)
ATRASO_MAXIMO = {'mensal': 120, 'trimestral móvel': 150, 'trimestral': 240}

# pesquisa | tabela | descrição curta | variáveis | classificação (id) ou None
TABELAS = [
    # --- Inflação ---
    ('IPCA',    1737, 'IPCA - índice geral (histórico desde 1979)', [2266, 63, 69, 2265], None),
    ('IPCA',    7060, 'IPCA - grupos, subgrupos, itens e subitens (desde 2020)', [63, 69, 2265, 66], 315),
    ('IPCA-15', 3065, 'IPCA-15 - índice geral', [1117, 355, 356, 1120], None),
    ('INPC',    1736, 'INPC - índice geral', [2289, 44, 68, 2292], None),
    # --- Mercado de trabalho (PNAD Contínua mensal, trimestre móvel) ---
    ('PNAD',    6381, 'Taxa de desocupação', [4099], None),
    ('PNAD',    6441, 'Taxa composta de subutilização', [4118], None),
    ('PNAD',    8513, 'Taxa de informalidade', [12466], None),
    ('PNAD',    5944, 'Taxa de participação na força de trabalho', [4096], None),
    ('PNAD',    6318, 'População por condição na força de trabalho', [1641], 629),
    ('PNAD',    6390, 'Rendimento médio habitual (real e nominal)', [5933, 5929], None),
    ('PNAD',    6392, 'Massa de rendimento habitual (real e nominal)', [6293, 6288], None),
    # --- Atividade mensal ---
    ('PIM',     8888, 'Produção física industrial por seções e atividades', [12606, 12607, 11601, 11602, 11603, 11604], 544),
    ('PMS',     5906, 'Volume e receita de serviços', [7167, 7168, 11623, 11624, 11625, 11626], 11046),
    ('PMC',     8880, 'Comércio varejista (restrito)', [7169, 7170, 11708, 11709, 11710, 11711], 11046),
    ('PMC',     8881, 'Comércio varejista ampliado', [7169, 7170, 11708, 11709, 11710, 11711], 11046),
    # --- PIB trimestral (Contas Nacionais) ---
    ('PIB',     1620, 'Índice de volume encadeado (1995=100)', [583], 11255),
    ('PIB',     1621, 'Índice de volume encadeado com ajuste sazonal (1995=100)', [584], 11255),
    ('PIB',     5932, 'Taxas de variação do volume', [6561, 6562, 6563, 6564], 11255),
    ('PIB',     1846, 'Valores a preços correntes (R$ milhões)', [585], 11255),
]

COLUNAS_FINAIS = ['data', 'periodo_codigo', 'periodo', 'periodicidade', 'pesquisa',
                  'tabela', 'tabela_descricao', 'variavel_codigo', 'variavel', 'unidade',
                  'categoria_codigo', 'categoria', 'valor', 'fonte', 'data_carga']


# ==============================================================================
# ACESSO À API
# ==============================================================================
def get_json(url: str):
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"  Tentativa {tentativa}/{MAX_RETRIES} falhou ({url[-80:]}): {e}")
            if tentativa == MAX_RETRIES:
                raise
            time.sleep(5 * tentativa)


def fatias_de_periodos(periodos: list, n_por_periodo: int) -> list:
    """Agrupa a lista ordenada de períodos em intervalos 'ini-fim' dentro do limite da API."""
    tamanho = max(1, LIMITE_VALORES // n_por_periodo)
    return [f"{grupo[0]}-{grupo[-1]}"
            for grupo in (periodos[i:i + tamanho] for i in range(0, len(periodos), tamanho))]


def coletar_tabela(tabela: int, variaveis: list, classificacao) -> tuple:
    """Retorna (DataFrame bruto, periodicidade) de uma tabela, fatiando por período."""
    meta = get_json(URL_METADADOS.format(t=tabela))
    periodicidade = meta['periodicidade']['frequencia']
    periodos = sorted(p['id'] for p in get_json(URL_PERIODOS.format(t=tabela)))

    n_categorias = 1
    trecho_class = ""
    if classificacao is not None:
        classe = next(c for c in meta['classificacoes'] if c['id'] == classificacao)
        n_categorias = len(classe['categorias'])
        trecho_class = f"/c{classificacao}/all"

    vars_url = ",".join(str(v) for v in variaveis)
    partes = []
    for fatia in fatias_de_periodos(periodos, len(variaveis) * n_categorias):
        url = f"{URL_VALORES}/t/{tabela}/n1/all/v/{vars_url}/p/{fatia}{trecho_class}"
        dados = get_json(url)
        cabecalho, linhas = dados[0], dados[1:]
        if 'Variável' not in cabecalho.get('D2N', ''):
            raise ValueError(f"Ordem de dimensões inesperada no cabeçalho: {cabecalho}")
        partes.append(pd.DataFrame(linhas))

    return pd.concat(partes, ignore_index=True), periodicidade


# ==============================================================================
# TRATAMENTO
# ==============================================================================
def periodo_para_data(codigo: str, periodicidade: str) -> pd.Timestamp:
    ano, sufixo = int(codigo[:4]), int(codigo[4:])
    mes = sufixo * 3 if periodicidade == 'trimestral' else sufixo
    return pd.Timestamp(year=ano, month=mes, day=1)


def padronizar(df: pd.DataFrame, pesquisa: str, tabela: int, descricao: str,
               periodicidade: str) -> pd.DataFrame:
    out = pd.DataFrame({
        'periodo_codigo': df['D3C'],
        'periodo': df['D3N'],
        'periodicidade': periodicidade,
        'pesquisa': pesquisa,
        'tabela': tabela,
        'tabela_descricao': descricao,
        'variavel_codigo': df['D2C'].astype(int),
        'variavel': df['D2N'],
        'unidade': df['MN'],
        'categoria_codigo': df['D4C'].astype('Int64') if 'D4C' in df else pd.array([pd.NA] * len(df), dtype='Int64'),
        'categoria': df['D4N'] if 'D4N' in df else None,
        # Valores especiais do SIDRA ('...', '-', 'X', '..') viram NaN e saem
        'valor': pd.to_numeric(df['V'], errors='coerce'),
    })
    out['data'] = out['periodo_codigo'].map(lambda c: periodo_para_data(c, periodicidade))
    out = out.dropna(subset=['valor'])
    out = tr.adicionar_metadados(out, fonte_dado=f'IBGE - SIDRA {tabela}')
    return out[COLUNAS_FINAIS]


def validar(df: pd.DataFrame, variaveis: list, periodicidade: str) -> list:
    """Retorna lista de problemas (vazia = ok)."""
    problemas = []
    if df.empty:
        return ["nenhuma linha com valor"]
    faltando = set(variaveis) - set(df['variavel_codigo'].unique())
    if faltando:
        problemas.append(f"variáveis sem dado: {sorted(faltando)}")
    atraso = (pd.Timestamp(date.today()) - df['data'].max()).days
    if atraso > ATRASO_MAXIMO.get(periodicidade, 240):
        problemas.append(f"última observação tem {atraso} dias ({df['data'].max():%Y-%m})")
    chave = ['periodo_codigo', 'variavel_codigo', 'categoria_codigo']
    if df.duplicated(subset=chave).any():
        problemas.append("linhas duplicadas na chave (período, variável, categoria)")
    return problemas


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================
def carregar_tabelas_atuais(tabelas: list) -> pd.DataFrame:
    """Lê do BigQuery as tabelas SIDRA que falharam hoje, para não apagá-las no replace."""
    lista = ", ".join(str(t) for t in tabelas)
    sql = f"SELECT * FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}` WHERE tabela IN ({lista})"
    return utils.get_bq_client().query(sql).to_dataframe()


def executar() -> bool:
    logger.info("=" * 60)
    logger.info("ETL IBGE — SIDRA")
    logger.info("=" * 60)

    coletados, falhas = [], []
    for pesquisa, tabela, descricao, variaveis, classificacao in TABELAS:
        logger.info(f"{pesquisa} {tabela} — {descricao}")
        try:
            bruto, periodicidade = coletar_tabela(tabela, variaveis, classificacao)
            df = padronizar(bruto, pesquisa, tabela, descricao, periodicidade)
            problemas = validar(df, variaveis, periodicidade)
        except Exception as e:
            problemas = [f"erro na coleta: {e}"]

        if problemas:
            logger.error(f"  ❌ {tabela}: {'; '.join(problemas)}")
            falhas.append(tabela)
            continue
        logger.info(f"  ✅ {len(df):,} linha(s) | {periodicidade} | "
                    f"{df['data'].min():%Y-%m} → {df['data'].max():%Y-%m}")
        coletados.append(df)

    if falhas:
        logger.warning(f"Tabelas com falha: {falhas} — mantendo a versão atual do BigQuery.")
        try:
            coletados.append(carregar_tabelas_atuais(falhas))
        except NotFound:
            logger.warning(f"{TABELA_ID} ainda não existe (primeira carga) — seguindo sem as tabelas com falha.")
        except Exception as e:
            logger.error(f"Não foi possível ler a versão anterior ({e}) — abortando para não perder dados.")
            return False

    if not coletados:
        logger.error("❌ Nada coletado.")
        return False

    df_final = pd.concat(coletados, ignore_index=True)
    logger.info(f"Total: {len(df_final):,} linha(s) → {DATASET_ID}.{TABELA_ID}")
    sucesso = utils.subir_para_bigquery(df_final, DATASET_ID, TABELA_ID, if_exists='replace')

    logger.info("=" * 60)
    logger.info("✅ ETL IBGE concluído." if sucesso and not falhas else "❌ ETL IBGE terminou com falhas.")
    logger.info("=" * 60)
    return sucesso and not falhas


if __name__ == "__main__":
    sys.exit(0 if executar() else 1)
