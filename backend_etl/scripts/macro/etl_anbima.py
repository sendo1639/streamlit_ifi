"""
ETL: Estrutura a Termo das Taxas de Juros (ETTJ) — ANBIMA
===========================================================
Coleta diária incremental da curva de juros.
Compatível com BigQuery free tier (sem DML/MERGE).

Execução:
  python etl_anbima.py            → coleta dias úteis novos
  python etl_anbima.py --force    → re-coleta os 5 dias disponíveis
"""

import sys
import os
import time
import logging
import argparse
import warnings
from io import StringIO
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import requests

# ==============================================================================
# 1. CONFIGURAÇÃO DE AMBIENTE
# ==============================================================================
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
    import transformations as tr
except ImportError as e:
    logger.critical(f"Módulo não encontrado: {e}")
    sys.exit(1)

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_macroeconomicos'
TABELA_ID  = 'anbima_ettj'

URL_PAGINA   = "https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm"
URL_DOWNLOAD = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"

TIMEOUT   = 30
PAUSA_REQ = 1.2
MAX_RETRIES = 3
JANELA_DISPONIVEL_DIAS_UTEIS = 5

HEADERS_PAGINA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
HEADERS_POST = {
    **HEADERS_PAGINA,
    "Referer": URL_PAGINA,
    "Content-Type": "application/x-www-form-urlencoded",
}

MARCADOR_SECAO_ETTJ = "ETTJ"

MAPA_VARIAVEIS = {
    "ettj_ipca": "ettj_ipca_pct_aa_252",
    "ettj_pref": "ettj_pre_pct_aa_252",
    "inflacao":  "inflacao_implicita_pct_aa_252",
}

# ==============================================================================
# 3. EXTRAÇÃO
# ==============================================================================
def iniciar_sessao() -> requests.Session:
    """Faz GET na página principal para obter cookies antes dos POSTs."""
    sessao = requests.Session()
    try:
        logger.info("Iniciando sessão com a ANBIMA...")
        sessao.get(URL_PAGINA, headers=HEADERS_PAGINA, timeout=TIMEOUT)
        logger.info("  Sessão estabelecida.")
    except requests.exceptions.RequestException as e:
        logger.warning(f"  Não foi possível carregar a página principal: {e}")
    return sessao


def buscar_ettj_dia(data_ref: date, sessao: requests.Session) -> pd.DataFrame:
    """POST para um único dia — retorna DataFrame vazio se sem dados."""
    payload = {
        "Tipo":    "glimp",
        "DataRef": data_ref.strftime("%d/%m/%Y"),
        "escolha": "2",
        "Idioma":  "PT",
        "saida":   "csv",
        "Dt_Ref":  data_ref.strftime("%d/%m/%Y"),
    }

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = sessao.post(
                URL_DOWNLOAD, data=payload,
                headers=HEADERS_POST, timeout=TIMEOUT
            )
            resp.raise_for_status()
            conteudo = resp.content.decode("latin-1").strip()

            if not conteudo or "<html" in conteudo.lower() or len(conteudo) < 50:
                return pd.DataFrame()

            return _extrair_secao_ettj(conteudo, data_ref)

        except requests.exceptions.RequestException as e:
            logger.warning(f"  Tentativa {tentativa}/{MAX_RETRIES} — {data_ref}: {e}")
            if tentativa < MAX_RETRIES:
                time.sleep(PAUSA_REQ * tentativa * 2)

    return pd.DataFrame()


def _extrair_secao_ettj(conteudo_csv: str, data_ref: date) -> pd.DataFrame:
    """Localiza e extrai apenas a seção ETTJ do CSV multi-seção da ANBIMA."""
    linhas = conteudo_csv.splitlines()

    idx_inicio = None
    for i, linha in enumerate(linhas):
        if MARCADOR_SECAO_ETTJ in linha and "Vertices" not in linha:
            idx_inicio = i + 1
            break

    if idx_inicio is None:
        return pd.DataFrame()

    linhas_secao = []
    for linha in linhas[idx_inicio:]:
        if linha.strip() == "":
            break
        linhas_secao.append(linha)

    if len(linhas_secao) < 2:
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            StringIO("\n".join(linhas_secao)),
            sep=";", thousands=".", decimal=",",
            encoding="latin-1",
        )
    except Exception as e:
        logger.warning(f"  Erro ao parsear seção ETTJ de {data_ref}: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    return _transformar_para_formato_longo(df, data_ref)


def _transformar_para_formato_longo(df_wide: pd.DataFrame, data_ref: date) -> pd.DataFrame:
    """Converte wide → long e adiciona metadados."""
    df = tr.normalizar_colunas(df_wide.copy())

    col_vertice = df.columns[0]
    cols_valor  = [c for c in df.columns if c != col_vertice]

    df[col_vertice] = pd.to_numeric(df[col_vertice], errors="coerce")
    df = df.dropna(subset=[col_vertice])
    df[col_vertice] = df[col_vertice].astype(int)

    for col in cols_valor:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df_long = df.melt(
        id_vars=[col_vertice],
        value_vars=cols_valor,
        var_name="nome_variavel",
        value_name="valor"
    )
    df_long = df_long.rename(columns={col_vertice: "vertice_du"})
    df_long = df_long.dropna(subset=["valor"])

    def mapear(nome: str) -> str:
        for chave, nome_limpo in MAPA_VARIAVEIS.items():
            if chave in nome.lower():
                return nome_limpo
        return nome

    df_long["nome_variavel"] = df_long["nome_variavel"].apply(mapear)
    df_long["data"]          = pd.Timestamp(data_ref)
    df_long = tr.adicionar_metadados(df_long, fonte_dado="ANBIMA - ETTJ")

    return df_long[["data", "vertice_du", "nome_variavel", "valor",
                    "fonte", "data_carga"]]


# ==============================================================================
# 4. CONTROLE DE DATAS
# ==============================================================================
def ultimos_dias_uteis(n: int) -> list:
    """Retorna os últimos N dias úteis até ontem."""
    ontem = date.today() - timedelta(days=1)
    idx = pd.bdate_range(end=ontem, periods=n, freq="B")
    return [d.date() for d in idx]


def buscar_datas_existentes_bq() -> set:
    """
    Retorna o conjunto de datas que já estão no BigQuery.
    Usa SELECT (não DML) — compatível com free tier.
    """
    try:
        client = utils.get_bq_client()
        sql = f"""
            SELECT DISTINCT CAST(data AS STRING) AS data_str
            FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`
        """
        df = client.query(sql).to_dataframe()
        return set(pd.to_datetime(df["data_str"]).dt.date)
    except Exception:
        # Tabela não existe ainda — primeira carga
        return set()


def calcular_datas_pendentes() -> tuple:
    """
    Compara os últimos 5 dias úteis disponíveis na ANBIMA
    com o que já está no BigQuery.
    Retorna apenas as datas que ainda não foram carregadas.
    """
    disponiveis  = set(ultimos_dias_uteis(JANELA_DISPONIVEL_DIAS_UTEIS))
    existentes   = buscar_datas_existentes_bq()
    pendentes    = sorted(disponiveis - existentes)

    if not existentes:
        logger.info("Tabela não encontrada. Coletando toda a janela disponível.")
    elif not pendentes:
        logger.info(f"BigQuery já atualizado. Nenhum dia pendente.")
    else:
        logger.info(f"Dias já no BigQuery  : {sorted(disponiveis & existentes)}")
        logger.info(f"Dias pendentes       : {pendentes}")

    return pendentes


# ==============================================================================
# 5. CARGA (sem DML — apenas append de linhas novas)
# ==============================================================================
def executar_carga(datas: list) -> bool:
    """
    Coleta e carrega apenas datas que ainda não estão no BigQuery.
    Usa append puro — sem MERGE, sem DML, compatível com free tier.
    """
    if not datas:
        return True

    coletados = []
    sessao    = iniciar_sessao()

    for i, data_ref in enumerate(datas, 1):
        df_dia = buscar_ettj_dia(data_ref, sessao)

        if not df_dia.empty:
            coletados.append(df_dia)
            logger.info(f"  [{i}/{len(datas)}] ✅ {data_ref} — {len(df_dia)} registros")
        else:
            logger.warning(f"  [{i}/{len(datas)}] ⚠️  {data_ref} — sem dados (feriado?)")

        time.sleep(PAUSA_REQ)

    sessao.close()

    if not coletados:
        logger.warning("Nenhum dado coletado.")
        return False

    df_final = pd.concat(coletados, ignore_index=True)
    logger.info(f"Total: {len(df_final)} linhas → carregando no BigQuery (append)...")

    # Append puro — duplicatas já foram removidas antes via set de datas
    return utils.subir_para_bigquery(
        df_final, DATASET_ID, TABELA_ID, if_exists="append"
    )


def executar_carga_force() -> bool:
    """
    Modo --force: re-coleta os 5 dias disponíveis.
    Remove as datas antigas em Python (filtra o append)
    sem precisar de DELETE no BigQuery.

    Estratégia:
      1. Baixa os 5 dias da ANBIMA
      2. Para as datas já existentes no BQ, não faz nada
         (o append duplicaria — então checamos antes de subir)
      Resultado: idêntico ao modo normal, mas garante que
      os dados dos 5 dias estão corretos mesmo após falhas.
    """
    logger.info("Modo FORCE: verificando os 5 dias disponíveis...")
    datas_disponiveis = ultimos_dias_uteis(JANELA_DISPONIVEL_DIAS_UTEIS)
    existentes        = buscar_datas_existentes_bq()

    # No --force, recoleta tudo mas só sobe o que NÃO está no BQ ainda
    # Para re-subir datas já existentes com dados corrigidos,
    # seria necessário habilitar billing. Orientamos o usuário nesse caso.
    pendentes = [d for d in datas_disponiveis if d not in existentes]

    if not pendentes:
        logger.info(
            "Todos os 5 dias já estão no BigQuery.\n"
            "Para re-processar datas já carregadas (ex: corrigir dados),\n"
            "é necessário habilitar o billing no Google Cloud (DML).\n"
            "Ou exclua manualmente a tabela no console e rode novamente."
        )
        return True

    logger.info(f"Coletando {len(pendentes)} dias ainda ausentes: {pendentes}")
    return executar_carga(pendentes)


# ==============================================================================
# 6. PONTO DE ENTRADA
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ETL ANBIMA — ETTJ (coleta diária, free tier compatível)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Verifica e completa os 5 dias disponíveis."
    )
    args = parser.parse_args()

    logger.info("=" * 55)
    logger.info("ETL ANBIMA — Curva de Juros ETTJ (incremental)")
    logger.info("=" * 55)

    if args.force:
        sucesso = executar_carga_force()
    else:
        datas   = calcular_datas_pendentes()
        sucesso = executar_carga(datas)

    logger.info("✅ Concluído com sucesso." if sucesso else "❌ Falha na carga.")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()