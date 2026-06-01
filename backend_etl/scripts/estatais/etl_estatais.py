"""
ETL: Empresas Estatais Federais — SEST/MGI
==========================================
Lê a planilha histórica da SEST (obtida via LAI) e carrega no BigQuery.

Execução manual (quando chegar planilha nova):
    python etl_estatais.py --arquivo "caminho/para/planilha.xlsx"
    python etl_estatais.py --arquivo "caminho/para/planilha.xlsx" --force

Flags:
    --arquivo  Caminho para o .xlsx da SEST (obrigatório)
    --force    Pula a validação e força o replace (usar com cautela)
"""

import sys
import os
import argparse
import logging
from pathlib import Path

import pandas as pd

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

# ==============================================================================
# 2. CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_fiscais'
TABELA_ID  = 'sest_estatais'

# Foco da análise: apenas dados anuais de 2008 a 2024
ANO_INICIO = 2008
ANO_FIM    = 2024

# Planos de contas que vamos manter (nomes modernos pós-2008)
PLANOS_VALIDOS = {'Balanço', 'DRE', 'DVA', 'Fluxo de Caixa'}

# Mapeamento de nomes antigos para modernos (pré-2008 não será carregado,
# mas normaliza eventuais inconsistências que apareçam no arquivo)
MAPA_PLANOS = {
    'Ativo e Passivo':       'Balanço',
    'Resultado':             'DRE',
    'Origem Aplicação':      'Fluxo de Caixa',
    'Fluxo Cx':              'Fluxo de Caixa',
    'Informações Adicionais': None,   # Descartado
}

# Mapeamento de siglas inconsistentes → sigla canônica
# Baseado no código SIEST (mesmo código = mesma empresa)
# Mantemos o nome mais recente/oficial em cada caso
MAPA_SIGLAS = {
    # SIEST 2651 — Ceasa mudou de nome
    'CEASA/MG':          'CEASAMINAS',
    # SIEST 4014 — variação de acentuação
    'TELEBRÁS':          'TELEBRAS',
    # SIEST 5000 — padroniza para nome do grupo
    'BB (Grupo)':        'GRUPO BB',
    # SIEST 5110
    'CAIXA (Grupo)':     'GRUPO CAIXA',
    # SIEST 5500
    'BNDES (Grupo)':     'GRUPO BNDES',
    # SIEST 8095 — variação de encoding
    'CONCEICAO':         'CONCEIÇÃO',
    # SIEST 8800 — padroniza para nome do grupo
    'GR. PETROBRAS':     'PETROBRAS (Grupo)',
    # SIEST 10071
    'ENBPar (Grupo)':    'GRUPO ENBPar',
    # SIEST 9725 — SPA foi renomeada para APS; mantemos APS (mais recente)
    'SPA':               'APS',
    # SIEST 7919 — VALEC foi renomeada para INFRA S.A.; mantemos INFRA S.A.
    'VALEC':             'INFRA S.A.',
}

# Colunas que vamos carregar no BigQuery
COLUNAS_FINAIS = [
    'exercicio', 'codigo_siest', 'sigla_empresa', 'nome_empresa',
    'dependencia', 'setor', 'nome_tipo_plano_contas',
    'rubrica', 'rubrica_nome', 'valor',
    'fonte', 'data_carga'
]

# ==============================================================================
# 3. LEITURA E NORMALIZAÇÃO
# ==============================================================================
def ler_planilha(caminho: str) -> pd.DataFrame:
    """Lê o Excel da SEST e retorna o DataFrame bruto."""
    logger.info(f"Lendo planilha: {caminho}")
    try:
        df = pd.read_excel(
            caminho,
            sheet_name='Controle',
            usecols=[
                'exercicio', 'periodicidade', 'codigo_siest',
                'sigla_empresa', 'nome_empresa', 'dependencia', 'setor',
                'nome_tipo_plano_contas', 'rubrica', 'rubrica_nome', 'valor'
            ]
        )
        logger.info(f"  Lidas {len(df):,} linhas brutas.")
        return df
    except Exception as e:
        logger.critical(f"Erro ao ler planilha: {e}")
        sys.exit(1)


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todas as transformações de limpeza e normalização.
    Retorna o DataFrame pronto para o BigQuery.
    """
    logger.info("Iniciando normalização...")
    n_original = len(df)

    # --- PASSO 1: Filtro de periodicidade e período ---
    df = df[df['periodicidade'] == 'Anual'].copy()
    df = df[df['exercicio'].between(ANO_INICIO, ANO_FIM)]
    logger.info(f"  Após filtro anual {ANO_INICIO}-{ANO_FIM}: {len(df):,} linhas")

    # --- PASSO 2: Normaliza planos de contas ---
    # Aplica mapeamento de nomes antigos para modernos
    df['nome_tipo_plano_contas'] = df['nome_tipo_plano_contas'].replace(MAPA_PLANOS)

    # Remove planos descartados (None no mapa ou fora dos válidos)
    df = df[df['nome_tipo_plano_contas'].isin(PLANOS_VALIDOS)]
    logger.info(f"  Após filtro de planos válidos: {len(df):,} linhas")

    # --- PASSO 3: Normaliza siglas de empresas ---
    df['sigla_empresa'] = df['sigla_empresa'].replace(MAPA_SIGLAS)

    # Atualiza o nome_empresa de acordo com a sigla canônica
    # (usa o nome mais recente que aparecer para cada sigla)
    nome_por_sigla = (
        df.sort_values('exercicio', ascending=False)
          .drop_duplicates('sigla_empresa')
          .set_index('sigla_empresa')['nome_empresa']
    )
    df['nome_empresa'] = df['sigla_empresa'].map(nome_por_sigla)

    # --- PASSO 4: Limpa nomes de rubricas ---
    # Remove espaços extras e padroniza capitalização
    df['rubrica_nome'] = (
        df['rubrica_nome']
          .astype(str)
          .str.strip()
          .str.title()   # Title Case: "LUCRO LÍQUIDO" → "Lucro Líquido"
    )

    # --- PASSO 5: Limpa outras colunas de texto ---
    for col in ['dependencia', 'setor', 'nome_tipo_plano_contas']:
        df[col] = df[col].astype(str).str.strip()

    # --- PASSO 6: Garante tipos corretos ---
    df['exercicio']    = df['exercicio'].astype(int)
    df['rubrica']      = pd.to_numeric(df['rubrica'], errors='coerce')
    df['valor']        = pd.to_numeric(df['valor'], errors='coerce')
    df['codigo_siest'] = pd.to_numeric(df['codigo_siest'], errors='coerce').astype('Int64')

    # --- PASSO 7: Remove linhas sem valor (rubricas de cabeçalho/total) ---
    df = df.dropna(subset=['valor', 'rubrica'])

    # --- PASSO 8: Remove a coluna de periodicidade (não vai para o BQ) ---
    df = df.drop(columns=['periodicidade'])

    # --- PASSO 9: Adiciona metadados padrão do projeto ---
    df = tr.adicionar_metadados(df, fonte_dado='SEST/MGI - LAI')

    logger.info(f"  Normalização concluída: {n_original:,} → {len(df):,} linhas")
    logger.info(f"  Empresas únicas: {df['sigla_empresa'].nunique()}")
    logger.info(f"  Período: {df['exercicio'].min()} – {df['exercicio'].max()}")
    logger.info(f"  Planos: {sorted(df['nome_tipo_plano_contas'].unique())}")

    return df[COLUNAS_FINAIS]


# ==============================================================================
# 4. VALIDAÇÃO ANTES DO REPLACE
# ==============================================================================
def validar_contra_bigquery(df_novo: pd.DataFrame) -> bool:
    """
    Compara o DataFrame novo com o que está no BigQuery.
    Aborta se a nova planilha tiver significativamente menos dados
    que a versão atual — proteção contra sobrescrever com arquivo ruim.

    Retorna True se passou na validação, False se falhou.
    """
    logger.info("Validando contra versão atual no BigQuery...")

    try:
        client = utils.get_bq_client()
        sql = f"""
            SELECT
                COUNT(*)                    AS total_linhas,
                COUNT(DISTINCT sigla_empresa) AS total_empresas,
                MIN(exercicio)              AS ano_min,
                MAX(exercicio)              AS ano_max
            FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`
        """
        df_bq = client.query(sql).to_dataframe()
        bq = df_bq.iloc[0]

        novo_linhas   = len(df_novo)
        novo_empresas = df_novo['sigla_empresa'].nunique()

        logger.info(f"  BigQuery atual : {int(bq['total_linhas']):>8,} linhas | "
                    f"{int(bq['total_empresas'])} empresas | "
                    f"{int(bq['ano_min'])}-{int(bq['ano_max'])}")
        logger.info(f"  Nova planilha  : {novo_linhas:>8,} linhas | "
                    f"{novo_empresas} empresas")

        # Critério 1: nova planilha não pode ter menos de 90% das linhas atuais
        if novo_linhas < int(bq['total_linhas']) * 0.90:
            logger.error(
                f"  ❌ FALHA: nova planilha tem {novo_linhas:,} linhas — "
                f"menos de 90% das {int(bq['total_linhas']):,} atuais no BQ."
            )
            return False

        # Critério 2: não pode ter menos empresas que a versão atual
        if novo_empresas < int(bq['total_empresas']):
            logger.warning(
                f"  ⚠️  AVISO: nova planilha tem {novo_empresas} empresas — "
                f"menos que as {int(bq['total_empresas'])} atuais no BQ. "
                f"Verifique se alguma empresa sumiu."
            )
            # Aviso, mas não bloqueia

        logger.info("  ✅ Validação aprovada.")
        return True

    except Exception:
        # Se a tabela não existe ainda (primeira carga), pula a validação
        logger.info("  Tabela não existe no BQ ainda — primeira carga, validação ignorada.")
        return True


# ==============================================================================
# 5. PONTO DE ENTRADA
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ETL SEST — Carrega demonstrações financeiras das estatais no BigQuery."
    )
    parser.add_argument(
        '--arquivo', required=True,
        help='Caminho para o arquivo .xlsx da SEST.'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Pula a validação e força o replace (usar com cautela).'
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ETL SEST — Empresas Estatais Federais")
    logger.info("=" * 60)

    # 1. Lê a planilha
    df_bruto = ler_planilha(args.arquivo)

    # 2. Normaliza
    df_limpo = normalizar(df_bruto)

    # 3. Valida contra o BQ (exceto se --force)
    if not args.force:
        passou = validar_contra_bigquery(df_limpo)
        if not passou:
            logger.error(
                "Carga abortada. Use --force para ignorar a validação "
                "se tiver certeza que a planilha está correta."
            )
            sys.exit(1)
    else:
        logger.warning("--force ativo: validação ignorada.")

    # 4. Carrega no BigQuery (replace completo)
    logger.info(f"Carregando {len(df_limpo):,} linhas no BigQuery...")
    sucesso = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )

    if sucesso:
        logger.info("✅ Carga concluída com sucesso.")
        logger.info(f"   Tabela: {utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}")
    else:
        logger.error("❌ Falha na carga.")

    logger.info("=" * 60)


if __name__ == "__main__":
    # Caminho direto para rodar pelo Spyder (sem precisar de argumento)
    CAMINHO_PLANILHA = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data\processed\Estatais_Dados_historicos___1988___2025.xlsx"
    FORCE = False  # Mude para True se quiser pular a validação

    logger.info("=" * 60)
    logger.info("ETL SEST — Empresas Estatais Federais")
    logger.info("=" * 60)

    df_bruto = ler_planilha(CAMINHO_PLANILHA)
    df_limpo = normalizar(df_bruto)

    if not FORCE:
        passou = validar_contra_bigquery(df_limpo)
        if not passou:
            logger.error("Carga abortada. Mude FORCE = True para ignorar.")
            sys.exit(1)

    sucesso = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )

    if sucesso:
        logger.info("✅ Carga concluída com sucesso.")
    else:
        logger.error("❌ Falha na carga.")

    logger.info("=" * 60)