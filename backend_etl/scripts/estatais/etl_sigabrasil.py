"""
ETL: Despesas das Estatais Dependentes — SIGA Brasil (SAP BI)
=============================================================
Processa o arquivo exportado do WebI com despesas das 17 empresas
estatais federais dependentes do Tesouro Nacional.

Metodologia: Pellegrini (2019) — "Empresas estatais federais:
relações com o Tesouro e valor", Ipea.

Execução manual (quando gerar novo arquivo no WebI):
    python etl_siga_brasil.py --arquivo "caminho/despesas_estatais.xlsx"
"""

import sys
import os
import argparse
import logging
from pathlib import Path

import pandas as pd

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
TABELA_ID  = 'siga_brasil_dependentes'

# GNDs que compõem as despesas totais (exclui Juros/Dívida e Reserva)
GNDS_VALIDOS = {
    'PESSOAL E ENCARGOS SOCIAIS',
    'OUTRAS DESPESAS CORRENTES',
    'INVESTIMENTOS',
    'INVERSOES FINANCEIRAS',
}

# Mapeamento UO (nome completo no SIGA) → sigla usada na base SEST
MAPA_UO_SIGLA = {
    'AMAZÔNIA AZUL TECNOLOGIAS DE DEFESA S.A. - AMAZUL':                              'AMAZUL',
    'CENTRO NACIONAL DE TECNOLOGIA ELETRÔNICA AVANÇADA - S.A. - CEITEC':             'CEITEC',
    'COMPANHIA BRASILEIRA DE TRENS URBANOS - CBTU':                                   'CBTU',
    'COMPANHIA DE DESENVOLVIMENTO DOS VALES DO SÃO FRANCISCO E DO PARNAÍBA - CODEVASF': 'CODEVASF',
    'COMPANHIA DE PESQUISA DE RECURSOS MINERAIS - CPRM':                              'CPRM',
    'COMPANHIA NACIONAL DE ABASTECIMENTO - CONAB':                                    'CONAB',
    'EMPRESA BRASIL DE COMUNICAÇÃO S.A. - EBC':                                       'EBC',
    'EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA - EMBRAPA':                          'EMBRAPA',
    'EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES - EBSERH':                           'EBSERH',
    'EMPRESA DE PESQUISA ENERGÉTICA - EPE':                                            'EPE',
    'EMPRESA DE PLANEJAMENTO E LOGÍSTICA S.A. - EPL':                                 'INFRA S.A.',
    'EMPRESA DE TRENS URBANOS DE PORTO ALEGRE S.A. - TRENSURB':                       'TRENSURB',
    'INDÚSTRIA DE MATERIAL BÉLICO DO BRASIL - IMBEL':                                 'IMBEL',
    'INDÚSTRIAS NUCLEARES DO BRASIL S.A. - INB':                                      'INB',
    'NUCLEBRÁS EQUIPAMENTOS PESADOS S.A. - NUCLEP':                                   'NUCLEP',
    'SERVIÇO FEDERAL DE PROCESSAMENTO DE DADOS - SERPRO':                             'SERPRO',
    'TELECOMUNICAÇÕES BRASILEIRAS S.A. - TELEBRAS':                                   'TELEBRAS',
}

# ==============================================================================
# 3. CLASSIFICAÇÃO DE FONTES
# ==============================================================================
def classificar_fonte(codigo_str: str, descricao: str) -> str:
    """
    Classifica a fonte de recurso seguindo a metodologia Pellegrini (2019):

    TESOURO: fontes cujo primeiro dígito é 1 ou 3, excluindo recursos próprios.
    - "Fonte de recurso 1" = Tesouro exercício corrente (100, 111, 112, 1000, 1037...)
    - "Grupo da fonte de recurso 3" = Tesouro exercícios anteriores (300, 311, 3000...)

    PRÓPRIOS: fontes de arrecadação própria da empresa.
    - Identificadas pela descrição ("PRÓPRIOS", "PROP.", "NÃO-FINANCEIROS ARRECADADOS")
    - Ou por códigos terminados em 50 no padrão antigo (150, 250, 350...)

    OUTROS: operações de crédito externas, convênios, doações, compensações.
    """
    try:
        codigo = int(str(codigo_str).strip())
    except (ValueError, TypeError):
        return 'OUTROS'

    desc = str(descricao).upper()

    # Indicadores de recursos próprios (têm prioridade na classificação)
    eh_proprio = any(t in desc for t in [
        'PROPRIOS', 'PROP.', 'REC.PROP',
        'NAO-FINANCEIROS DIRETAM', 'DIRETAMENTE ARRECADADOS',
        'RECURSOS FINANCEIROS DE LIVRE APLICACAO',
        'RECURSOS FINANCEIROS DIRETAMENTE ARRECADADOS',
    ])

    if eh_proprio:
        return 'PRÓPRIOS'

    # Pellegrini: primeiro dígito 1 ou 3 → Tesouro
    primeiro_digito = str(codigo)[0]
    if primeiro_digito in ('1', '3') and not eh_proprio:
        return 'TESOURO'

    return 'OUTROS'


# ==============================================================================
# 4. LEITURA E TRANSFORMAÇÃO
# ==============================================================================
def ler_arquivo(caminho: str) -> pd.DataFrame:
    """Lê o Excel exportado do WebI."""
    logger.info(f"Lendo arquivo: {caminho}")
    try:
        df = pd.read_excel(caminho, header=1)
        df = df.drop(
            columns=[c for c in df.columns if 'Unnamed' in str(c)],
            errors='ignore'
        )
        logger.info(f"  {len(df):,} linhas brutas lidas.")
        return df
    except Exception as e:
        logger.critical(f"Erro ao ler arquivo: {e}")
        sys.exit(1)


def transformar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica filtros, mapeamentos e calcula as métricas do Pellegrini.
    Retorna uma tabela analítica pronta para o BigQuery.
    """
    logger.info("Iniciando transformação...")

    # --- PASSO 1: Padroniza nomes de colunas ---
    df.columns = [str(c).strip() for c in df.columns]

    # --- PASSO 2: Filtra GNDs válidos ---
    df['GND_upper'] = df['GND'].astype(str).str.upper().str.strip()
    df = df[df['GND_upper'].isin(GNDS_VALIDOS)].copy()
    logger.info(f"  Após filtro GND: {len(df):,} linhas")

    # --- PASSO 3: Mapeia UO → sigla ---
    df['sigla_empresa'] = df['UO (Ajustado)'].map(MAPA_UO_SIGLA)
    nao_mapeadas = df[df['sigla_empresa'].isna()]['UO (Ajustado)'].unique()
    if len(nao_mapeadas) > 0:
        logger.warning(f"  UOs não mapeadas: {list(nao_mapeadas)}")
    df = df[df['sigla_empresa'].notna()]

    # --- PASSO 4: Classifica fontes ---
    df['tipo_fonte'] = df.apply(
        lambda r: classificar_fonte(r['Fonte (Cod)'], r['Fonte (Cod/Desc)']),
        axis=1
    )

    # --- PASSO 5: Garante tipos numéricos ---
    df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce').astype('Int64')
    df['pago'] = pd.to_numeric(df['Pago + RP Pago'], errors='coerce').fillna(0)

    # --- PASSO 6: Classifica GND em dois grupos (composição) ---
    df['grupo_gnd'] = df['GND_upper'].map({
        'PESSOAL E ENCARGOS SOCIAIS':  'pessoal_correntes',
        'OUTRAS DESPESAS CORRENTES':   'pessoal_correntes',
        'INVESTIMENTOS':               'investimentos_inversoes',
        'INVERSOES FINANCEIRAS':       'investimentos_inversoes',
    })

    # --- PASSO 7: Agrega por empresa e ano ---
    logger.info("  Agregando métricas por empresa e ano...")

    # Total pago por empresa/ano/grupo_gnd
    por_grupo = (
        df.groupby(['Ano', 'sigla_empresa', 'grupo_gnd'])['pago']
          .sum().unstack(fill_value=0).reset_index()
    )
    for col in ['pessoal_correntes', 'investimentos_inversoes']:
        if col not in por_grupo.columns:
            por_grupo[col] = 0

    # Total Tesouro por empresa/ano
    tesouro = (
        df[df['tipo_fonte'] == 'TESOURO']
          .groupby(['Ano', 'sigla_empresa'])['pago']
          .sum().reset_index()
          .rename(columns={'pago': 'recursos_tesouro'})
    )

    # Total despesas por empresa/ano
    total = (
        df.groupby(['Ano', 'sigla_empresa'])['pago']
          .sum().reset_index()
          .rename(columns={'pago': 'despesas_totais'})
    )

    # Junta tudo
    df_final = (
        total
        .merge(tesouro, on=['Ano', 'sigla_empresa'], how='left')
        .merge(por_grupo[['Ano', 'sigla_empresa', 'pessoal_correntes',
                           'investimentos_inversoes']],
               on=['Ano', 'sigla_empresa'], how='left')
    )
    df_final['recursos_tesouro'] = df_final['recursos_tesouro'].fillna(0)

    # --- PASSO 8: Calcula indicadores ---
    df_final['grau_dependencia_pct'] = (
        (df_final['recursos_tesouro'] / df_final['despesas_totais'] * 100)
        .round(1)
    )
    df_final['comp_pessoal_correntes_pct'] = (
        (df_final['pessoal_correntes'] / df_final['despesas_totais'] * 100)
        .round(1)
    )
    df_final['comp_investimentos_pct'] = (
        (df_final['investimentos_inversoes'] / df_final['despesas_totais'] * 100)
        .round(1)
    )

    # Converte para R$ milhões (facilita visualização)
    df_final['despesas_totais_mi']   = (df_final['despesas_totais']   / 1e6).round(1)
    df_final['recursos_tesouro_mi']  = (df_final['recursos_tesouro']  / 1e6).round(1)

    # --- PASSO 9: Renomeia e seleciona colunas finais ---
    df_final = df_final.rename(columns={'Ano': 'exercicio'})

    df_final = df_final[[
        'exercicio',
        'sigla_empresa',
        'despesas_totais_mi',
        'recursos_tesouro_mi',
        'grau_dependencia_pct',
        'comp_pessoal_correntes_pct',
        'comp_investimentos_pct',
    ]]

    # --- PASSO 10: Metadados ---
    df_final = tr.adicionar_metadados(df_final, fonte_dado='SIGA Brasil - SAP BI WebI')

    logger.info(f"  Transformação concluída: {len(df_final):,} linhas")
    logger.info(f"  Empresas: {df_final['sigla_empresa'].nunique()}")
    logger.info(f"  Período: {df_final['exercicio'].min()} – {df_final['exercicio'].max()}")

    return df_final


# ==============================================================================
# 5. PONTO DE ENTRADA
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ETL SIGA Brasil — Despesas das Estatais Dependentes"
    )
    parser.add_argument(
        '--arquivo', required=True,
        help='Caminho para o .xlsx exportado do WebI.'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Pula validação e força o replace.'
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ETL SIGA Brasil — Estatais Dependentes (Pellegrini)")
    logger.info("=" * 60)

    df_bruto   = ler_arquivo(args.arquivo)
    df_limpo   = transformar(df_bruto)

    # Validação simples
    if not args.force:
        try:
            client = utils.get_bq_client()
            bq_count = client.query(
                f"SELECT COUNT(*) as n FROM "
                f"`{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`"
            ).to_dataframe()['n'].iloc[0]

            if len(df_limpo) < int(bq_count) * 0.9:
                logger.error(
                    f"Novo arquivo tem {len(df_limpo)} linhas vs "
                    f"{int(bq_count)} no BQ. Use --force para confirmar."
                )
                sys.exit(1)
        except Exception:
            logger.info("Tabela não existe — primeira carga.")

    sucesso = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )

    if sucesso:
        logger.info("✅ Carga concluída.")
        # Exibe prévia da tabela analítica
        ano_max = df_limpo['exercicio'].max()
        preview = (
            df_limpo[df_limpo['exercicio'] == ano_max]
            .sort_values('grau_dependencia_pct', ascending=False)
            [['sigla_empresa', 'despesas_totais_mi', 'recursos_tesouro_mi',
              'grau_dependencia_pct', 'comp_pessoal_correntes_pct',
              'comp_investimentos_pct']]
        )
        logger.info(f"\n=== Prévia — {ano_max} ===\n{preview.to_string(index=False)}")
    else:
        logger.error("❌ Falha na carga.")

    logger.info("=" * 60)


if __name__ == "__main__":
    # Para rodar direto pelo Spyder, substitua pelo caminho local:
    CAMINHO = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data\processed\despesas_estatais_nao_dep.xlsx"
    FORCE   = False

    logger.info("=" * 60)
    logger.info("ETL SIGA Brasil — Estatais Dependentes (Pellegrini)")
    logger.info("=" * 60)

    df_bruto = ler_arquivo(CAMINHO)
    df_limpo = transformar(df_bruto)

    if not FORCE:
        try:
            client   = utils.get_bq_client()
            bq_count = client.query(
                f"SELECT COUNT(*) as n FROM "
                f"`{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}`"
            ).to_dataframe()['n'].iloc[0]
            if len(df_limpo) < int(bq_count) * 0.9:
                logger.error("Arquivo menor que 90% do BQ. Mude FORCE=True para confirmar.")
                sys.exit(1)
        except Exception:
            logger.info("Tabela não existe — primeira carga.")

    sucesso = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )
    if sucesso:
        logger.info("✅ Carga concluída.")
        ano_max = df_limpo['exercicio'].max()
        preview = (
            df_limpo[df_limpo['exercicio'] == ano_max]
            .sort_values('grau_dependencia_pct', ascending=False)
        )
        logger.info(f"\n=== Prévia — {ano_max} ===\n{preview.to_string(index=False)}")
    logger.info("=" * 60)