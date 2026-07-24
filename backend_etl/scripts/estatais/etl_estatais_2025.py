"""
ETL: Dados Contábeis Trimestrais das Estatais Federais — 2025
=============================================================
Processa a planilha extraída do SIEST com dados trimestrais de 2025.

Diferenças em relação à planilha histórica (etl_estatais.py):
  - Códigos de conta com 9 dígitos (vs 6 dígitos na histórica)
  - Valores em R$ mil (vs R$ unidade na histórica) → convertidos para R$
  - Campo 'Universo' no lugar de 'dependencia' → cruzado com cadastral
  - Periodicidade trimestral (1º a 4º Trimestre)
  - Coluna 'Empresa Abrev.' no lugar de 'sigla_empresa'

Tabela BQ: dados_fiscais.estatais_2025

Execução (Spyder):
    Ajuste CAMINHO abaixo e rode o bloco if __name__ == "__main__"
"""

import sys
import os
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
# CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_fiscais'
TABELA_ID  = 'estatais_2025'

# Caminho base dos dados do projeto
BASE_DADOS = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data"

# Caminho do arquivo cadastral (para cruzar dependência)
CAMINHO_CADASTRAL = BASE_DADOS + r"\processed\sest-identificacao-empresas-ativas.csv"

# Contas de FLUXO (DRE, Fluxo de Caixa, DVA) no SIEST trimestral vêm
# ACUMULADAS no ano (1T, 1T+2T, 1T+2T+3T, 1T+2T+3T+4T) — confirmado
# empiricamente: Receita Líquida EMBRAPA 2025 = 29.813 / 43.542 / 53.224 / 68.184
# (cada trimestre maior que o anterior, não são valores isolados).
# Contas de ESTOQUE (Balanço) são saldos pontuais — não se acumulam.
PLANOS_FLUXO   = {'DRE', 'Fluxo de Caixa', 'DVA'}
PLANOS_ESTOQUE = {'Balanço'}

# Mapeamento de trimestre → número
MAPA_TRIMESTRE = {
    '1º Trimestre': 1,
    '2º Trimestre': 2,
    '3º Trimestre': 3,
    '4º Trimestre': 4,
}

# Planos a manter (exclui DVA por ora — foco nas análises TCU)
PLANOS_VALIDOS = {'Balanço', 'DRE', 'Fluxo de Caixa', 'DVA'}

# Universos: 2=Financeiro, 10=ETG (grupos consolidados), 11=SPE (empresas individuais)
# Mantemos todos — o frontend filtra conforme necessário
UNIVERSOS_VALIDOS = {2, 10, 11}

# Empresas "principais" — grupos consolidados (GRUPO BB, GRUPO CAIXA, etc.)
# em vez de cada subsidiária isolada (BB AG Viena, BB Cartões, Caixa
# Corretora, ANSA, TI BV, etc.). Mantém paridade com a contagem de
# empresas dependentes/não dependentes usada na base histórica
# (04_Estatais.py) e evita poluir os gráficos com dezenas de subsidiárias
# já consolidadas nos grupos.
#
# Exceção: ENBPar usa a EMPRESA isolada, não o GRUPO ENBPar. O grupo
# consolida participações em outras empresas (Eletronuclear, Amazônia
# Azul etc.), inflando os números (ex: Receita Líquida quase 27x maior
# no 4T2025 no grupo vs na empresa) — não representa a ENBPar em si.
EMPRESAS_PRINCIPAIS = {
    "ABGF", "AMAZUL", "APS", "BASA", "BNB", "CBTU", "CDC", "CDP", "CDRJ",
    "CEAGESP", "CEASAMINAS", "CEITEC", "CEITEC - EM LIQUIDAÇÃO", "CMB",
    "CODEBA", "CODERN", "CODESA", "CODEVASF", "CONAB", "CONCEIÇÃO", "CPRM",
    "DATAPREV", "EBC", "EBSERH", "ECT", "EMBRAPA", "EMGEA", "EMGEPRON",
    "ENBPAR", "EPE", "FINEP", "GRUPO BB", "GRUPO BNDES", "GRUPO CAIXA",
    "GRUPO NAV BRASIL", "HCPA", "HEMOBRÁS", "IMBEL", "INFRA S.A.",
    "INFRAERO", "NUCLEP", "GR. PETROBRAS", "PPSA", "SERPRO", "TELEBRAS",
    "TRENSURB",
}

# Grupos consolidados que não têm match direto no cadastral (que lista
# entidades individuais como "BB", "BNDES", "CAIXA", não "GRUPO BB" etc.)
# Classificação manual: todos são não dependentes do Tesouro Nacional.
# ENBPAR não entra aqui — é empresa isolada (não grupo), então casa
# naturalmente com o cadastral, que já lista "ENBPar" individualmente.
GRUPOS_NAO_DEPENDENTES_OVERRIDE = {
    "GR. PETROBRAS", "GRUPO BB", "GRUPO BNDES", "GRUPO CAIXA",
    "GRUPO NAV BRASIL",
}

# Normalização dos rótulos longos do cadastral para o padrão curto
# já usado na página histórica (04_Estatais.py)
MAPA_DEPENDENCIA = {
    "Dependente do Tesouro Nacional":     "Dependente",
    "Não dependente do Tesouro Nacional": "Não dependente",
}

# ==============================================================================
# LEITURA
# ==============================================================================
def ler_arquivo(caminho: str) -> pd.DataFrame:
    logger.info(f"Lendo arquivo: {caminho}")
    df = pd.read_excel(caminho, sheet_name='Base')
    logger.info(f"  {len(df):,} linhas brutas.")
    return df


def ler_cadastral(caminho: str) -> pd.DataFrame:
    """
    Lê o arquivo cadastral (CSV ou XLSX) para obter dependência e setor oficial.

    CSVs exportados do Excel em pt-BR frequentemente vêm em Latin-1/cp1252,
    não UTF-8 — por isso tentamos utf-8-sig primeiro e caímos para latin-1
    se houver erro de decodificação (caractere acentuado como 'ê', 'ç' etc.
    em byte fora do range UTF-8 válido).
    """
    try:
        if caminho.lower().endswith(('.xlsx', '.xls')):
            cad = pd.read_excel(caminho)
        else:
            try:
                cad = pd.read_csv(caminho, encoding='utf-8-sig', sep=';')
            except UnicodeDecodeError:
                logger.info("  UTF-8 falhou, tentando latin-1...")
                cad = pd.read_csv(caminho, encoding='latin-1', sep=';')

        cad.columns = [c.strip().lower().replace(' ', '_') for c in cad.columns]
        logger.info(f"  Cadastral carregado: {len(cad)} empresas.")

        # Uppercase na sigla — o cadastral tem 6 siglas fora do padrão
        # maiúsculo (ex: "ENBPar", "Caixa DTVM", "NAV Brasil"), o que
        # quebrava o merge silenciosamente contra sigla_empresa (sempre
        # uppercased na base principal). Normaliza aqui na origem.
        cad['sigla'] = cad['sigla'].astype(str).str.strip().str.upper()

        return cad[['sigla', 'dependencia', 'setor']].rename(
            columns={'sigla': 'sigla_empresa_cad',
                     'dependencia': 'dependencia_cad',
                     'setor': 'setor_cad'}
        )
    except Exception as e:
        logger.warning(f"  Cadastral não carregado: {e}")
        return pd.DataFrame()


# ==============================================================================
# TRANSFORMAÇÃO
# ==============================================================================
def transformar(df: pd.DataFrame, df_cad: pd.DataFrame) -> pd.DataFrame:
    logger.info("Transformando dados...")

    # --- Filtros básicos ---
    df = df[df['Universo'].isin(UNIVERSOS_VALIDOS)].copy()
    df = df[df['Plano'].isin(PLANOS_VALIDOS)].copy()
    df = df[df['Status Atual'] == 'Ativa'].copy()
    logger.info(f"  Após filtros: {len(df):,} linhas")

    # --- Renomear colunas ---
    df = df.rename(columns={
        'Exercício':       'exercicio',
        'Periodicidade':   'periodicidade',
        'Universo':        'universo_cod',
        'Universo Descrição': 'universo_desc',
        'Empresa Abrev.':  'sigla_empresa',
        'Empresa Nome':    'nome_empresa',
        'Cód. Plano':      'cod_plano',
        'Plano':           'nome_tipo_plano_contas',
        'Cód. Conta':      'rubrica',
        'Conta':           'rubrica_nome',
        'Valor (Em R$mil)': 'valor_rs_mil',
        'Setor Economia':  'setor',
        'Área de Atuação': 'area_atuacao',
        'Ministério Supervisor': 'ministerio',
        'Listada em Bolsa': 'listada_bolsa',
        'Sede':            'sede',
        'RP':              'rp',
        'Controle':        'controle',
        'Vínculo':         'vinculo',
        'Status Atual':    'status',
    })

    # --- Trimestre numérico ---
    df['trimestre'] = df['periodicidade'].map(MAPA_TRIMESTRE)

    # --- Converter R$ mil → R$ ---
    df['valor'] = pd.to_numeric(df['valor_rs_mil'], errors='coerce').fillna(0) * 1000

    # --- Garantir tipos ---
    df['exercicio'] = pd.to_numeric(df['exercicio'], errors='coerce').astype('Int64')
    df['rubrica']   = df['rubrica'].astype(str).str.strip()
    df['rubrica_nome'] = df['rubrica_nome'].astype(str).str.strip().str.title()
    df['sigla_empresa'] = df['sigla_empresa'].astype(str).str.strip().str.upper()

    # --- Filtrar apenas empresas/grupos principais (remove subsidiárias isoladas) ---
    n_antes_emp = df['sigla_empresa'].nunique()
    n_antes_linhas = len(df)
    df = df[df['sigla_empresa'].isin(EMPRESAS_PRINCIPAIS)].copy()
    logger.info(
        f"  Filtro empresas principais: {n_antes_emp} → "
        f"{df['sigla_empresa'].nunique()} empresas "
        f"({n_antes_linhas:,} → {len(df):,} linhas)"
    )
    faltando = EMPRESAS_PRINCIPAIS - set(df['sigla_empresa'].unique())
    if faltando:
        logger.warning(
            f"  Empresas da lista não encontradas na planilha (verificar "
            f"grafia): {sorted(faltando)}"
        )

    # --- Cruzar com cadastral para dependência ---
    if not df_cad.empty:
        df = df.merge(
            df_cad,
            left_on='sigla_empresa', right_on='sigla_empresa_cad',
            how='left'
        )
        # Normaliza rótulos longos do cadastral → padrão curto (consistente
        # com a página histórica, que usa "Dependente"/"Não dependente")
        df['dependencia'] = df['dependencia_cad'].map(MAPA_DEPENDENCIA)
        df.drop(columns=['sigla_empresa_cad', 'dependencia_cad', 'setor_cad'],
                inplace=True, errors='ignore')
    else:
        df['dependencia'] = pd.NA

    # --- Override: grupos consolidados sem match direto no cadastral ---
    # (GRUPO BB, GRUPO BNDES, GRUPO CAIXA, GR. PETROBRAS, GRUPO ENBPAR,
    #  GRUPO NAV BRASIL não existem como tal no cadastral, que só lista
    #  as entidades individuais — classificação manual abaixo)
    mask_override = df['sigla_empresa'].isin(GRUPOS_NAO_DEPENDENTES_OVERRIDE)
    df.loc[mask_override, 'dependencia'] = 'Não dependente'

    # Qualquer empresa que ainda ficou sem classificação é sinalizada —
    # o objetivo é manter apenas duas categorias (Dependente/Não dependente)
    df['dependencia'] = df['dependencia'].fillna('Não classificada')
    sem_classificacao = sorted(
        df.loc[df['dependencia'] == 'Não classificada', 'sigla_empresa'].unique()
    )
    if sem_classificacao:
        logger.warning(
            f"  ⚠️ Empresas SEM classificação de dependência (verificar "
            f"cadastral ou adicionar ao override): {sem_classificacao}"
        )
    else:
        logger.info("  ✅ Todas as empresas classificadas (Dependente/Não dependente).")

    # --- Desacumular contas de fluxo (DRE, FC, DVA) ---
    logger.info("  Desacumulando valores trimestrais (DRE/FC/DVA)...")
    df = desacumular_fluxos(df)

    # --- Metadados ---
    df = tr.adicionar_metadados(df, fonte_dado='SIEST - Dados Contábeis 2025')

    # --- Colunas finais ---
    colunas = [
        'exercicio', 'trimestre', 'periodicidade',
        'universo_cod', 'universo_desc',
        'sigla_empresa', 'nome_empresa',
        'dependencia', 'setor', 'area_atuacao',
        'ministerio', 'controle', 'vinculo',
        'listada_bolsa', 'sede', 'status',
        'nome_tipo_plano_contas', 'rubrica', 'rubrica_nome',
        'valor', 'valor_trimestre',
        'fonte', 'data_carga'
    ]
    colunas_presentes = [c for c in colunas if c in df.columns]
    df = df[colunas_presentes]

    logger.info(f"  Transformação concluída: {len(df):,} linhas")
    logger.info(f"  Empresas: {df['sigla_empresa'].nunique()}")
    logger.info(f"  Trimestres: {sorted(df['trimestre'].dropna().unique())}")

    return df


# ==============================================================================
# DESACUMULAÇÃO DOS VALORES TRIMESTRAIS
# ==============================================================================
def desacumular_fluxos(df: pd.DataFrame) -> pd.DataFrame:
    """
    O SIEST reporta contas de FLUXO (DRE, Fluxo de Caixa, DVA) como valores
    acumulados no ano-calendário: o "3º Trimestre" já soma 1T+2T+3T.

    Esta função calcula o valor do TRIMESTRE ISOLADO a partir dos acumulados:
        isolado(T) = acumulado(T) - acumulado(T-1)
        isolado(1T) = acumulado(1T)  [não há trimestre anterior]

    Contas de ESTOQUE (Balanço) são saldos pontuais e não passam por esse
    cálculo — o valor do "3º Trimestre" já é o saldo real naquela data.

    Adiciona a coluna 'valor_trimestre' ao lado de 'valor' (que permanece
    como o acumulado original, útil para comparação direta com o TCU,
    que também reporta "parcial até o Nº trimestre").

    Quando o trimestre anterior está ausente na série (gap de dados), o
    cálculo da diferença não é possível — nesses casos 'valor_trimestre'
    fica como NULL, em vez de usar o acumulado como aproximação. Isso
    evita inferir um valor isolado que poderia estar errado.
    """
    df = df.sort_values(
        ['sigla_empresa', 'nome_tipo_plano_contas', 'rubrica', 'exercicio', 'trimestre']
    ).copy()

    eh_fluxo = df['nome_tipo_plano_contas'].isin(PLANOS_FLUXO)

    # Padrão: valor_trimestre = valor (válido para Balanço e para o 1º trimestre)
    df['valor_trimestre'] = df['valor']

    # Para contas de fluxo, isolado = diferença entre acumulados consecutivos
    grupo_cols = ['sigla_empresa', 'nome_tipo_plano_contas', 'rubrica', 'exercicio']
    diffs = df.loc[eh_fluxo].groupby(grupo_cols)['valor'].diff()
    df.loc[eh_fluxo, 'valor_trimestre'] = diffs

    # 1º trimestre não tem "anterior" → diff() retorna NaN → usa o próprio acumulado
    primeiro_tri = df['trimestre'] == 1
    df.loc[eh_fluxo & primeiro_tri, 'valor_trimestre'] = (
        df.loc[eh_fluxo & primeiro_tri, 'valor']
    )

    n_nan = df['valor_trimestre'].isna().sum()
    if n_nan > 0:
        logger.warning(
            f"  {n_nan} linhas com valor_trimestre NaN após desacumulação "
            f"(trimestre intermediário ausente para a série). "
            f"Mantido como NULL — não inferimos o valor isolado para "
            f"evitar dado incorreto. O valor acumulado ('valor') permanece "
            f"disponível normalmente para essas linhas."
        )

    return df


# ==============================================================================
# VALIDAÇÃO
# ==============================================================================
def validar(df: pd.DataFrame, force: bool = False) -> bool:
    """Verifica integridade mínima antes de subir."""
    checks = {
        'Linhas suficientes (> 1000)':
            len(df) > 1000,
        'Trimestres esperados (1 a 4)':
            set(df['trimestre'].dropna().unique()).issubset({1, 2, 3, 4}),
        'Empresas conhecidas presentes':
            {'ECT', 'EMGEPRON', 'INFRAERO'}.issubset(
                set(df['sigla_empresa'].unique())
            ),
        'LLE presente (DRE)':
            df[(df['nome_tipo_plano_contas'] == 'DRE') &
               (df['rubrica'] == '290000000')].shape[0] > 0,
        'FCO presente (FC)':
            df[(df['nome_tipo_plano_contas'] == 'Fluxo de Caixa') &
               (df['rubrica'] == '319900000')].shape[0] > 0,
    }

    passou = True
    for nome, resultado in checks.items():
        status = '✅' if resultado else '❌'
        logger.info(f"  {status} {nome}")
        if not resultado:
            passou = False

    if not passou and not force:
        logger.error("Validação falhou. Use FORCE=True para forçar a carga.")

    return passou or force


# ==============================================================================
# CARGA
# ==============================================================================
def executar(caminho_dados: str, caminho_cad: str, force: bool = False):
    logger.info("=" * 60)
    logger.info("ETL Estatais 2025 — Dados Trimestrais SIEST")
    logger.info("=" * 60)

    df_raw  = ler_arquivo(caminho_dados)
    df_cad  = ler_cadastral(caminho_cad)
    df_limpo = transformar(df_raw, df_cad)

    logger.info("Validando...")
    if not validar(df_limpo, force):
        return

    # Preview antes de subir — mostra acumulado vs isolado lado a lado
    logger.info("\n=== Preview LLE por empresa — Acumulado vs Trimestre Isolado (3T2025) ===")
    preview = (
        df_limpo[
            (df_limpo['nome_tipo_plano_contas'] == 'DRE') &
            (df_limpo['rubrica'] == '290000000') &
            (df_limpo['trimestre'] == 3) &
            (df_limpo['exercicio'] == 2025)
        ][['sigla_empresa', 'valor', 'valor_trimestre']]
        .assign(
            acumulado_mi=lambda x: x['valor'] / 1e6,
            isolado_mi=lambda x: x['valor_trimestre'] / 1e6
        )
        .drop(columns=['valor', 'valor_trimestre'])
        .sort_values('acumulado_mi')
        .head(15)
    )
    logger.info(preview.to_string(index=False))

    ok = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )
    logger.info("✅ Carga concluída." if ok else "❌ Falha na carga.")
    logger.info("=" * 60)


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================
if __name__ == "__main__":
    # Caminhos do ambiente do usuário (confirmados via log de execução)
    CAMINHO = BASE_DADOS + r"\processed\Dados_contabeis_2025_extracao_02.06.26.xlsx"
    FORCE = False

    executar(CAMINHO, CAMINHO_CADASTRAL, force=FORCE)