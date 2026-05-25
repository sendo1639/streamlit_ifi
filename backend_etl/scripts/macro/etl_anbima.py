"""
ETL: Estrutura a Termo das Taxas de Juros (ETTJ) — ANBIMA
===========================================================
Coleta diária dos vértices da curva de juros (ETTJ IPCA, ETTJ PRÉ
e Inflação Implícita) do endpoint de download da ANBIMA.

LIMITAÇÃO CONHECIDA: A ANBIMA disponibiliza apenas os últimos 5 dias
úteis no site público. Por isso, este script deve rodar DIARIAMENTE
para construir o histórico de forma incremental no BigQuery.

Execução:
  python etl_anbima.py            → coleta dias úteis novos (padrão)
  python etl_anbima.py --force    → força re-coleta dos últimos 5 dias
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
    logger.critical(f"Módulo não encontrado: {e}. Verifique BASE_DIR: {BASE_DIR}")
    sys.exit(1)

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_macroeconomicos'
TABELA_ID  = 'anbima_ettj'

# URL da página principal — necessário para obter cookies de sessão
URL_PAGINA = "https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm"

# URL do endpoint de download (POST)
URL_DOWNLOAD = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"

TIMEOUT   = 30
PAUSA_REQ = 1.2   # segundos entre requisições
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Marcador que identifica o início da seção de interesse no CSV
MARCADOR_SECAO_ETTJ = "ETTJ"

# ==============================================================================
# 3. EXTRAÇÃO
# ==============================================================================
def iniciar_sessao() -> requests.Session:
    """
    Cria uma sessão HTTP e faz GET na página principal da ANBIMA
    para obter os cookies de sessão necessários antes do POST.
    """
    sessao = requests.Session()
    try:
        logger.info("Iniciando sessão com a ANBIMA...")
        sessao.get(URL_PAGINA, headers=HEADERS_PAGINA, timeout=TIMEOUT)
        logger.info("  Sessão estabelecida.")
    except requests.exceptions.RequestException as e:
        logger.warning(f"  Não foi possível carregar a página principal: {e}")
    return sessao


def buscar_ettj_dia(data_ref: date, sessao: requests.Session) -> pd.DataFrame:
    """
    Faz o POST para um único dia útil e retorna o DataFrame no formato longo.
    Retorna DataFrame vazio se a data não tiver dados.
    """
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
                URL_DOWNLOAD,
                data=payload,
                headers=HEADERS_POST,
                timeout=TIMEOUT
            )
            resp.raise_for_status()

            # Detecta resposta HTML (sem dados) vs CSV (com dados)
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
    """
    O CSV da ANBIMA contém múltiplas seções (Beta/Lambda, ETTJ, Prefixados,
    Erros). Esta função localiza e extrai apenas a seção ETTJ.

    Estrutura do arquivo:
        [linha 1]  22/05/2026;Beta 1;Beta 2;...
        [linha 2]  PREFIXADOS;...
        [linha 3]  IPCA;...
        [linha 4]  (vazia)
        [linha 5]  ETTJ Inflação Implicita (IPCA)   <-- marcador
        [linha 6]  Vertices;ETTJ IPCA;ETTJ PREF;Inflação Implícita
        [linha 7+] 126;9,0397;13,9729;4,5242
        ...
        [linha N]  (vazia)                           <-- fim da seção
        [linha N+1] PREFIXADOS (CIRCULAR 3.361)
        ...
    """
    linhas = conteudo_csv.splitlines()

    # 1. Encontra a linha do marcador
    idx_inicio = None
    for i, linha in enumerate(linhas):
        if MARCADOR_SECAO_ETTJ in linha and "Vertices" not in linha:
            idx_inicio = i + 1  # A próxima linha é o cabeçalho da tabela
            break

    if idx_inicio is None:
        logger.debug(f"  Seção ETTJ não encontrada para {data_ref}.")
        return pd.DataFrame()

    # 2. Coleta as linhas da seção até a próxima linha vazia
    linhas_secao = []
    for linha in linhas[idx_inicio:]:
        if linha.strip() == "":
            break
        linhas_secao.append(linha)

    if len(linhas_secao) < 2:  # Precisa de pelo menos cabeçalho + 1 dado
        return pd.DataFrame()

    # 3. Lê a seção como CSV
    texto_secao = "\n".join(linhas_secao)
    try:
        df = pd.read_csv(
            StringIO(texto_secao),
            sep=";",
            thousands=".",
            decimal=",",
            encoding="latin-1",
        )
    except Exception as e:
        logger.warning(f"  Erro ao parsear seção ETTJ de {data_ref}: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    return _transformar_para_formato_longo(df, data_ref)


def _transformar_para_formato_longo(df_wide: pd.DataFrame, data_ref: date) -> pd.DataFrame:
    """
    Converte a tabela ETTJ de formato wide para long.

    Entrada:
        Vertices | ETTJ IPCA | ETTJ PREF | Inflação Implícita
        126      | 9.0397    | 13.9729   | 4.5242

    Saída:
        data       | vertice_du | nome_variavel              | valor
        2026-05-22 | 126        | ettj_ipca_pct_aa_252       | 9.0397
    """
    df = tr.normalizar_colunas(df_wide.copy())

    col_vertice = df.columns[0]
    cols_valor  = [c for c in df.columns if c != col_vertice]

    # Garante que vértice é inteiro
    df[col_vertice] = pd.to_numeric(df[col_vertice], errors='coerce')
    df = df.dropna(subset=[col_vertice])
    df[col_vertice] = df[col_vertice].astype(int)

    # Converte colunas de valor para numérico
    for col in cols_valor:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Wide → Long
    df_long = df.melt(
        id_vars=[col_vertice],
        value_vars=cols_valor,
        var_name='nome_variavel',
        value_name='valor'
    )
    df_long = df_long.rename(columns={col_vertice: 'vertice_du'})
    df_long = df_long.dropna(subset=['valor'])

    # Mapeamento de nomes para versão legível
    mapa = {
        "ettj_ipca": "ettj_ipca_pct_aa_252",
        "ettj_pref": "ettj_pre_pct_aa_252",
        "inflacao":  "inflacao_implicita_pct_aa_252",
    }
    def mapear(nome: str) -> str:
        for chave, nome_limpo in mapa.items():
            if chave in nome.lower():
                return nome_limpo
        return nome

    df_long['nome_variavel'] = df_long['nome_variavel'].apply(mapear)
    df_long['data']          = pd.Timestamp(data_ref)
    df_long = tr.adicionar_metadados(df_long, fonte_dado='ANBIMA - ETTJ')

    return df_long[['data', 'vertice_du', 'nome_variavel', 'valor', 'fonte', 'data_carga']]


# ==============================================================================
# 4. CONTROLE DE DATAS
# ==============================================================================
def ultimos_dias_uteis(n: int) -> list:
    """Retorna os últimos N dias úteis até ontem."""
    ontem = date.today() - timedelta(days=1)
    idx = pd.bdate_range(end=ontem, periods=n, freq='B')
    return [d.date() for d in idx]


def buscar_ultima_data_bq() -> date | None:
    """Consulta o BigQuery para saber a data mais recente já armazenada."""
    try:
        client = utils.get_bq_client()
        sql = f"""
            SELECT MAX(data) AS ultima_data
            FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`
        """
        resultado = client.query(sql).to_dataframe()
        ultima = resultado['ultima_data'].iloc[0]
        return pd.Timestamp(ultima).date() if not pd.isna(ultima) else None
    except Exception:
        return None


def calcular_datas_pendentes() -> tuple:
    """
    Descobre quais dias úteis ainda não estão no BigQuery,
    dentro da janela disponível da ANBIMA (5 dias úteis).
    """
    disponiveis = ultimos_dias_uteis(JANELA_DISPONIVEL_DIAS_UTEIS)
    ultima_no_bq = buscar_ultima_data_bq()

    if ultima_no_bq is None:
        logger.info("Tabela não encontrada. Coletando toda a janela disponível (5 dias úteis).")
        return disponiveis, 'replace'

    pendentes = [d for d in disponiveis if d > ultima_no_bq]

    if not pendentes:
        logger.info(f"BigQuery já atualizado até {ultima_no_bq}. Nada a fazer.")
    else:
        logger.info(f"Última data no BigQuery : {ultima_no_bq}")
        logger.info(f"Dias pendentes          : {len(pendentes)} ({pendentes[0]} → {pendentes[-1]})")

    return pendentes, 'append'


# ==============================================================================
# 5. CARGA
# ==============================================================================
# ==============================================================================
# Substituir a função executar_carga() no etl_anbima.py pelo trecho abaixo.
# Usa MERGE (upsert) no BigQuery em vez de APPEND puro.
# Garante que:
#   - Não há duplicatas (mesma data+vértice+variável nunca aparece duas vezes)
#   - Buracos causados por falhas são preenchidos automaticamente na próxima execução
#   - Reprocessamentos com --force são seguros sem precisar deletar antes
# ==============================================================================

def executar_carga(datas: list, if_exists: str) -> bool:
    """
    Coleta os dados das datas fornecidas e faz UPSERT no BigQuery.
    
    Usa MERGE para garantir idempotência:
    - Se a combinação (data + vertice_du + nome_variavel) já existe → atualiza o valor
    - Se não existe → insere como novo registro
    
    Isso protege contra duplicatas e permite reprocessar datas sem risco.
    """
    if not datas:
        return True

    coletados = []
    sessao = iniciar_sessao()

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
    logger.info(f"Total coletado: {len(df_final)} linhas")

    return _upsert_bigquery(df_final)


def _upsert_bigquery(df: pd.DataFrame) -> bool:
    """
    Faz MERGE (upsert) no BigQuery usando uma tabela temporária como staging.

    Fluxo:
      1. Sobe os dados novos para uma tabela temporária (_ettj_staging)
      2. Executa MERGE da staging na tabela final
      3. Deleta a tabela temporária

    Chave de unicidade: (data, vertice_du, nome_variavel)
    """
    TABELA_STAGING = f"{TABELA_ID}_staging"
    full_final   = f"`{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`"
    full_staging = f"`{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_STAGING}`"

    try:
        client = utils.get_bq_client()

        # PASSO 1: Sobe para staging (sempre replace — é temporária)
        logger.info("  Subindo dados para tabela staging...")
        ok = utils.subir_para_bigquery(df, DATASET_ID, TABELA_STAGING, if_exists='replace')
        if not ok:
            return False

        # PASSO 2: MERGE — insere novos, atualiza existentes
        logger.info("  Executando MERGE na tabela final...")
        sql_merge = f"""
            MERGE {full_final} AS destino
            USING {full_staging} AS origem
                ON  destino.data          = origem.data
                AND destino.vertice_du    = origem.vertice_du
                AND destino.nome_variavel = origem.nome_variavel

            -- Se já existe: atualiza valor e data_carga
            WHEN MATCHED THEN
                UPDATE SET
                    destino.valor      = origem.valor,
                    destino.data_carga = origem.data_carga

            -- Se não existe: insere
            WHEN NOT MATCHED THEN
                INSERT (data, vertice_du, nome_variavel, valor, fonte, data_carga)
                VALUES (origem.data, origem.vertice_du, origem.nome_variavel,
                        origem.valor, origem.fonte, origem.data_carga)
        """
        client.query(sql_merge).result()
        logger.info("  ✅ MERGE concluído.")

        # PASSO 3: Limpa a staging
        client.query(f"DROP TABLE IF EXISTS {full_staging}").result()
        logger.info("  Tabela staging removida.")

        return True

    except Exception as e:
        logger.error(f"  ❌ Erro no upsert: {e}")
        return False


# ==============================================================================
# 6. PONTO DE ENTRADA
# ==============================================================================
def _deletar_datas_bq(datas: list):
    """Remove registros das datas especificadas (usado no --force)."""
    if not datas:
        return
    try:
        client = utils.get_bq_client()
        lista  = ", ".join([f"DATE '{d}'" for d in datas])
        client.query(
            f"DELETE FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}` WHERE data IN ({lista})"
        ).result()
        logger.info(f"  Registros removidos para {len(datas)} datas.")
    except Exception as e:
        logger.warning(f"  Não foi possível deletar registros anteriores: {e}")


def main():
    parser = argparse.ArgumentParser(description="ETL ANBIMA — ETTJ (coleta diária incremental)")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-coleta os 5 dias disponíveis (corrige falhas pontuais)."
    )
    args = parser.parse_args()

    logger.info("=" * 55)
    logger.info("ETL ANBIMA — Curva de Juros ETTJ (incremental)")
    logger.info("=" * 55)

    if args.force:
        logger.info("Modo: FORCE — re-coletando os 5 dias úteis disponíveis.")
        datas     = ultimos_dias_uteis(JANELA_DISPONIVEL_DIAS_UTEIS)
        if_exists = 'append'
        _deletar_datas_bq(datas)
    else:
        datas, if_exists = calcular_datas_pendentes()

    sucesso = executar_carga(datas, if_exists)

    logger.info("✅ Concluído com sucesso." if sucesso else "❌ Falha na carga.")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()