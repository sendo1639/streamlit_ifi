"""
ETL: Despesas das Estatais Dependentes — SIGA Brasil (SAP BI)
=============================================================
Metodologia: Pellegrini (2019) — "Empresas estatais federais:
relações com o Tesouro e valor", Ipea.

Novidades v2:
  - Classificação de fontes por lista explícita de códigos (não
    mais pelo primeiro dígito, que incluía recursos próprios como
    388, 180, 150 etc.)
  - Trata tanto o sistema antigo (3 dígitos, até 2022) quanto o
    novo (4 dígitos, a partir de 2023)
  - Coluna adicional: despesa de pessoal por funcionário por mês
    (metodologia Pellegrini — divide por 13 por causa do 13º salário)
  - Mapeamento de continuidade EPL → INFRA S.A. e extinção INB/TELEBRAS
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
# 1. CONSTANTES
# ==============================================================================
DATASET_ID = 'dados_fiscais'
TABELA_ID  = 'siga_brasil_dependentes'

BASE_DADOS = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data"

# GNDs válidos (Pellegrini)
GNDS_PESSOAL       = {'PESSOAL E ENCARGOS SOCIAIS'}
GNDS_CORRENTES     = {'OUTRAS DESPESAS CORRENTES'}
GNDS_INVESTIMENTOS = {'INVESTIMENTOS', 'INVERSOES FINANCEIRAS'}
GNDS_VALIDOS       = GNDS_PESSOAL | GNDS_CORRENTES | GNDS_INVESTIMENTOS

# Mapeamento UO → sigla
MAPA_UO_SIGLA = {
    # AMAZUL
    'AMAZÔNIA AZUL TECNOLOGIAS DE DEFESA S.A. - AMAZUL':                              'AMAZUL',
    'RECURSOS SOB SUPERVISÃO DA AMAZÔNIA AZUL TECNOLOGIAS DE DEFESA S.A. - AMAZUL':  'AMAZUL',

    # CEITEC
    'CENTRO NACIONAL DE TECNOLOGIA ELETRÔNICA AVANÇADA - S.A. - CEITEC':             'CEITEC',
    'CENTRO NACIONAL DE TECNOLOGIA ELETRÔNICA AVANÇADA S.A. - CEITEC':             'CEITEC',
    'RECURSOS SOB SUPERVISÃO DO CENTRO NACIONAL DE TECNOLOGIA ELETRÔNICA AVANÇADA - S.A. - CEITEC': 'CEITEC',

    # CBTU
    'COMPANHIA BRASILEIRA DE TRENS URBANOS - CBTU':                                   'CBTU',
    'RECURSOS SOB SUPERVISÃO DA COMPANHIA BRASILEIRA DE TRENS URBANOS - CBTU':       'CBTU',

    # CODEVASF — três grafias históricas no SIGA
    'COMPANHIA DE DESENVOLVIMENTO DOS VALES DO SÃO FRANCISCO E DO PARNAÍBA - CODEVASF': 'CODEVASF',
    'COMPANHIA DE DESENVOLVIMENTO DO VALE DO SÃO FRANCISCO':                            'CODEVASF',
    'COMPANHIA DE DESENVOLVIMENTO DOS VALES DO SÃO FRANCISCO - CODEVASF':            'CODEVASF',
    'COMPANHIA DE DESENVOLVIMENTO DO VALE DO SÃO FRANCISCO - CODEVASF':              'CODEVASF',
    'RECURSOS SOB SUPERVISÃO DA COMPANHIA DE DESENVOLVIMENTO DOS VALES DO SÃO FRANCISCO E DO PARNAÍBA - CODEVASF': 'CODEVASF',

    # CONAB
    'COMPANHIA NACIONAL DE ABASTECIMENTO - CONAB':                                    'CONAB',
    'RECURSOS SOB SUPERVISÃO DA COMPANHIA NACIONAL DE ABASTECIMENTO - CONAB':        'CONAB',

    # CPRM
    'COMPANHIA DE PESQUISA DE RECURSOS MINERAIS - CPRM':                              'CPRM',
    'RECURSOS SOB SUPERVISÃO DA COMPANHIA DE PESQUISA DE RECURSOS MINERAIS - CPRM':  'CPRM',

    # EBC — duas grafias (com e sem acento)
    'EMPRESA BRASIL DE COMUNICAÇÃO S.A. - EBC':                                       'EBC',
    'EMPRESA BRASIL DE COMUNICACOES S.A - EBC':                                       'EBC',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA BRASIL DE COMUNICAÇÃO S.A. - EBC':           'EBC',

    # EBSERH
    'EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES':                                    'EBSERH',
    'EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES S.A. - EBSERH':                      'EBSERH',
    'EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES - EBSERH':                           'EBSERH',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES - EBSERH': 'EBSERH',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES':           'EBSERH',

    # EMBRAPA
    'EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA - EMBRAPA':                          'EMBRAPA',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA BRASILEIRA DE PESQUISA AGROPECUÁRIA - EMBRAPA': 'EMBRAPA',

    # EPE
    'EMPRESA DE PESQUISA ENERGÉTICA - EPE':                                            'EPE',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA DE PESQUISA ENERGÉTICA - EPE':               'EPE',

    # INFRA S.A. = EPL + VALEC
    # No SIGA Brasil ambas continuam como UOs separadas até 2025 —
    # nunca foram fundidas para fins orçamentários. Mapeamos as duas
    # (e seus "Recursos sob Supervisão") para INFRA S.A.
    'EMPRESA DE PLANEJAMENTO E LOGÍSTICA S.A. - EPL':                                 'INFRA S.A.',
    'EMPRESA DE PLANEJAMENTO E LOGISTICA S.A-EPL':                                    'INFRA S.A.',
    'VALEC - ENGENHARIA, CONSTRUÇÕES E FERROVIAS S.A.':                               'INFRA S.A.',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA DE PLANEJAMENTO E LOGÍSTICA S.A. - EPL':     'INFRA S.A.',
    'RECURSOS SOB SUPERVISÃO DA VALEC - ENGENHARIA, CONSTRUÇÕES E FERROVIAS S.A.':   'INFRA S.A.',

    # TRENSURB
    'EMPRESA DE TRENS URBANOS DE PORTO ALEGRE S.A. - TRENSURB':                       'TRENSURB',
    'RECURSOS SOB SUPERVISÃO DA EMPRESA DE TRENS URBANOS DE PORTO ALEGRE S.A. - TRENSURB': 'TRENSURB',

    # IMBEL
    'INDÚSTRIA DE MATERIAL BÉLICO DO BRASIL - IMBEL':                                 'IMBEL',
    'RECURSOS SOB SUPERVISÃO DO INDÚSTRIA DE MATERIAL BÉLICO DO BRASIL - IMBEL':     'IMBEL',

    # INB (extinta após 2021 — incorporada à ENBPar, não dependente)
    'INDÚSTRIAS NUCLEARES DO BRASIL S.A. - INB':                                      'INB',
    'RECURSOS SOB SUPERVISÃO DA INDÚSTRIAS NUCLEARES DO BRASIL S.A. - INB':          'INB',

    # NUCLEP — duas grafias
    'NUCLEBRÁS EQUIPAMENTOS PESADOS S.A. - NUCLEP':                                   'NUCLEP',
    'NUCLEBRAS EQUIPAMENTOS PESADOS S/A - NUCLEP':                                    'NUCLEP',
    'RECURSOS SOB SUPERVISÃO DA NUCLEBRÁS EQUIPAMENTOS PESADOS S.A. - NUCLEP':       'NUCLEP',

    # SERPRO
    'SERVIÇO FEDERAL DE PROCESSAMENTO DE DADOS - SERPRO':                             'SERPRO',

    # TELEBRAS (dados disponíveis 2020–2024 no arquivo de pessoal)
    'TELECOMUNICAÇÕES BRASILEIRAS S.A. - TELEBRAS':                                   'TELEBRAS',
    'RECURSOS SOB SUPERVISÃO DA TELECOMUNICAÇÕES BRASILEIRAS S.A. - TELEBRAS':       'TELEBRAS',

    # HCPA — presente no SIGA de 2001 a 2024 (ausente em 2025)
    'HOSPITAL DE CLÍNICAS DE PORTO ALEGRE - HCPA':                                    'HCPA',
    'HOSPITAL DE CLÍNICAS DE PORTO ALEGRE':                                           'HCPA',
    # CONCEIÇÃO — duas grafias: sem sufixo até 2024, com "- CONCEIÇÃO" em 2025
    'HOSPITAL NOSSA SENHORA DA CONCEIÇÃO S.A.':                                       'CONCEIÇÃO',
    'HOSPITAL NOSSA SENHORA DA CONCEIÇÃO S.A. - CONCEIÇÃO':                          'CONCEIÇÃO',
}

# ==============================================================================
# 2. CLASSIFICAÇÃO DE FONTES (lista explícita — v2)
# ==============================================================================
# Sistema antigo (até 2022) — 3 dígitos
TESOURO_3DIG = {
    # Orçamento Fiscal — exercício corrente (1xx)
    100, 108, 111, 112, 115, 129, 134, 139, 142, 143, 144, 145,
    151, 153, 156, 160, 169, 172, 176, 178, 179, 183, 185, 186,
    192, 199,
    # Seguridade Social com origem no Tesouro (2xx)
    292,
    # Restos a Pagar — Orçamento Fiscal (3xx)
    300, 311, 312, 315, 329, 339, 342, 343, 344, 345,
    351, 353, 360, 372, 376, 378, 379, 385, 392, 399,
    # Especiais/históricos
    900, 911, 944, 979, 985,
}

PROPRIOS_3DIG = {
    # Exercício corrente
    150, 163, 180, 181, 188, 191, 195, 196,
    250, 263, 280, 281, 282, 295, 296,
    # Restos a Pagar
    350, 363, 370, 380, 381, 388, 396,
    # Terceira esfera (OI)
    650, 663, 680, 681, 696,
    # Financeiros próprios (especiais)
    8180,
}

# Sistema novo (a partir de 2023) — 4 dígitos
TESOURO_4DIG = {
    # Exercício corrente
    1000, 1001, 1002, 1003, 1008, 1037, 1045, 1046,
    1060, 1062, 1071, 1080, 1120, 1123, 1443, 1444,
    # Restos a Pagar
    3000, 3008, 3011, 3037, 3045, 3060, 3062, 3129, 3444,
    # Grupo especial
    8100, 8444,
}

PROPRIOS_4DIG = {
    # Exercício corrente
    1048, 1049, 1050, 1051, 1081, 1095, 1096,
    # Restos a Pagar
    3048, 3049, 3050, 3051, 3081, 3096,
    # Grupo especial
    8180,
}

# Códigos ambíguos → OUTROS (não entram no numerador Tesouro)
# Operações de crédito externas/internas, convênios, doações, saldos de RP
OUTROS_CODIGOS = {
    90,          # NÃO INFORMADO
    148, 149,    # Op. crédito externas
    181, 281,    # Convênios
    195, 196,    # Doações
    246, 247, 249,  # Op. crédito internas/externas (2xx)
    1081, 1095, 1096,  # Convênios e doações (novo)
    3081, 3096,        # idem RP
    646,               # Op. crédito (OI)
    681, 696,          # Convênios e doações (OI)
}


def classificar_fonte(codigo) -> str:
    """
    Classifica a fonte de recurso em TESOURO, PRÓPRIOS ou OUTROS.

    Usa listas explícitas de códigos — mais preciso do que o critério
    de "primeiro dígito 1 ou 3" do Pellegrini (2019), que incluía
    recursos próprios como 150, 188, 388, 650 etc.

    Compatível com ambos os sistemas:
      - 3 dígitos: vigente até 2022 (ex: 100, 150, 300, 350)
      - 4 dígitos: a partir de 2023 (ex: 1000, 1050, 3000, 3050)
    """
    try:
        cod = int(str(codigo).strip())
    except (ValueError, TypeError):
        return 'OUTROS'

    if cod in TESOURO_3DIG or cod in TESOURO_4DIG:
        return 'TESOURO'
    if cod in PROPRIOS_3DIG or cod in PROPRIOS_4DIG:
        return 'PRÓPRIOS'
    return 'OUTROS'


# ==============================================================================
# 3. QUANTITATIVO DE PESSOAL
# ==============================================================================
# Regras de continuidade (fusões e extinções):
#   EPL desaparece após 2021 → incorporado à INFRA S.A. (já unificados no MAPA_UO_SIGLA)
#   INB desaparece após 2021 → incorporado à ENBPar (não dependente)
#   TELEBRAS: dados apenas 2020–2024
#   CONCEIÇÃO, HCPA: constam no pessoal mas não no SIGA Brasil (financiadas via SUS)

CAMINHO_PESSOAL = (
    BASE_DADOS + r"\processed\Quantitativo_de_Pessoal_das_Estatais___Demanda_de_Cidadao_2016_12_a_2025_12.xlsx"
)

def carregar_pessoal(caminho: str) -> pd.DataFrame:
    """
    Carrega e prepara o quantitativo de pessoal das estatais dependentes.
    Retorna DataFrame com colunas: exercicio, sigla_empresa, num_funcionarios
    """
    try:
        df = pd.read_excel(caminho)
        df.columns = [c.strip() for c in df.columns]
        logger.info(f"  Pessoal carregado: {len(df):,} linhas")
    except Exception as e:
        logger.warning(f"  Pessoal não carregado: {e}")
        return pd.DataFrame()

    # Filtra grupo Dependentes
    df = df[df['Grupo'] == 'Dependentes'].copy()

    # Soma todas as áreas (Administrativo + Operacional + Investimento)
    df_tot = (
        df.groupby(['Competência', 'Empresa'])['Qtd Pessoal']
          .sum().reset_index()
          .rename(columns={'Competência': 'exercicio', 'Empresa': 'sigla_pessoal'})
    )

    # Harmoniza siglas EPL → INFRA S.A.
    # (EPL existia até 2021 em paralelo com INFRA S.A.; soma os dois
    # nos anos de coexistência para ter o quadro completo da empresa)
    df_epl = df_tot[df_tot['sigla_pessoal'] == 'EPL'].rename(
        columns={'sigla_pessoal': 'dummy', 'Qtd Pessoal': 'qtd_epl'}
    )
    df_tot.loc[df_tot['sigla_pessoal'] == 'EPL', 'sigla_pessoal'] = 'INFRA S.A.'

    df_tot = (
        df_tot.groupby(['exercicio', 'sigla_pessoal'])['Qtd Pessoal']
              .sum().reset_index()
              .rename(columns={'sigla_pessoal': 'sigla_empresa',
                               'Qtd Pessoal': 'num_funcionarios'})
    )

    logger.info(
        f"  Pessoal processado: {df_tot['sigla_empresa'].nunique()} empresas, "
        f"anos {df_tot['exercicio'].min()}–{df_tot['exercicio'].max()}"
    )
    return df_tot


# ==============================================================================
# 4. LEITURA E TRANSFORMAÇÃO
# ==============================================================================
def ler_arquivo(caminho: str) -> pd.DataFrame:
    logger.info(f"Lendo arquivo: {caminho}")
    try:
        # Detecta automaticamente qual linha contém os cabeçalhos
        # procurando pela coluna 'Ano' — independente do nº de linhas
        # de metadados que o WebI coloca antes dos dados
        header_row = None
        df_raw = pd.read_excel(caminho, header=None, nrows=10)
        for i, row in df_raw.iterrows():
            if any(str(v).strip().lower() == 'ano' for v in row.values):
                header_row = i
                break

        if header_row is None:
            raise ValueError(
                "Não foi possível detectar a linha de cabeçalho "
                "(esperava encontrar coluna 'Ano' nas primeiras 10 linhas)."
            )

        df = pd.read_excel(caminho, header=header_row)
        df = df.drop(
            columns=[c for c in df.columns if 'Unnamed' in str(c)],
            errors='ignore'
        )
        logger.info(f"  Cabeçalho detectado na linha {header_row}. "
                    f"Colunas: {list(df.columns)}")
        logger.info(f"  {len(df):,} linhas brutas lidas.")
        return df
    except Exception as e:
        logger.critical(f"Erro ao ler arquivo: {e}")
        raise


def transformar(df: pd.DataFrame, df_pessoal: pd.DataFrame) -> pd.DataFrame:
    logger.info("Transformando...")

    # Padroniza nomes de colunas
    df.columns = [str(c).strip() for c in df.columns]

    # Filtra GNDs válidos
    df['GND_upper'] = df['GND'].astype(str).str.upper().str.strip()
    df = df[df['GND_upper'].isin(GNDS_VALIDOS)].copy()
    logger.info(f"  Após filtro GND: {len(df):,} linhas")

    # Mapeia UO → sigla
    df['sigla_empresa'] = df['UO'].map(MAPA_UO_SIGLA)
    nao_mapeadas = df[df['sigla_empresa'].isna()]['UO'].unique()
    if len(nao_mapeadas) > 0:
        logger.warning(f"  UOs não mapeadas: {list(nao_mapeadas)}")
    df = df[df['sigla_empresa'].notna()].copy()

    # Classifica fontes com lista explícita
    df['tipo_fonte'] = df['Fonte (Cod)'].apply(classificar_fonte)

    # Tipos numéricos
    df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce').astype('Int64')
    df['pago'] = pd.to_numeric(df['Pago + RP Pago'], errors='coerce').fillna(0)

    # Classifica grupo GND (para coluna de composição)
    df['grupo_gnd'] = df['GND_upper'].map({
        'PESSOAL E ENCARGOS SOCIAIS':  'pessoal',
        'OUTRAS DESPESAS CORRENTES':   'correntes',
        'INVESTIMENTOS':               'investimentos',
        'INVERSOES FINANCEIRAS':       'investimentos',
    })

    # Agrega por empresa/ano/grupo_gnd
    por_grupo = (
        df.groupby(['Ano', 'sigla_empresa', 'grupo_gnd'])['pago']
          .sum().unstack(fill_value=0).reset_index()
    )
    for col in ['pessoal', 'correntes', 'investimentos']:
        if col not in por_grupo.columns:
            por_grupo[col] = 0

    # Tesouro por empresa/ano
    tesouro = (
        df[df['tipo_fonte'] == 'TESOURO']
          .groupby(['Ano', 'sigla_empresa'])['pago']
          .sum().reset_index()
          .rename(columns={'pago': 'recursos_tesouro'})
    )

    # Total por empresa/ano
    total = (
        df.groupby(['Ano', 'sigla_empresa'])['pago']
          .sum().reset_index()
          .rename(columns={'pago': 'despesas_totais'})
    )

    # Monta tabela base
    df_final = (
        total
        .merge(tesouro, on=['Ano', 'sigla_empresa'], how='left')
        .merge(
            por_grupo[['Ano', 'sigla_empresa', 'pessoal', 'correntes', 'investimentos']],
            on=['Ano', 'sigla_empresa'], how='left'
        )
    )
    df_final['recursos_tesouro'] = df_final['recursos_tesouro'].fillna(0)
    df_final['pessoal_correntes'] = df_final['pessoal'] + df_final['correntes']

    # Indicadores Pellegrini
    df_final['grau_dependencia_pct'] = (
        (df_final['recursos_tesouro'] / df_final['despesas_totais'] * 100)
        .round(1)
    )
    df_final['comp_pessoal_correntes_pct'] = (
        (df_final['pessoal_correntes'] / df_final['despesas_totais'] * 100)
        .round(1)
    )
    df_final['comp_investimentos_pct'] = (
        (df_final['investimentos'] / df_final['despesas_totais'] * 100)
        .round(1)
    )

    # Converte para R$ Milhões
    df_final['despesas_totais_mi']   = (df_final['despesas_totais']   / 1e6).round(1)
    df_final['recursos_tesouro_mi']  = (df_final['recursos_tesouro']  / 1e6).round(1)
    df_final['despesa_pessoal_mi']   = (df_final['pessoal']           / 1e6).round(1)

    df_final = df_final.rename(columns={'Ano': 'exercicio'})

    # -------------------------------------------------------
    # Despesa de pessoal por funcionário por mês (Pellegrini)
    # -------------------------------------------------------
    if not df_pessoal.empty:
        df_final = df_final.merge(df_pessoal, on=['exercicio', 'sigla_empresa'], how='left')

        # Fórmula: Despesa Pessoal (R$) / (Nº Funcionários × 13)
        # × 13 porque o Brasil tem 13º salário — para base mensal real
        df_final['desp_pessoal_por_func_mes_rs'] = (
            (df_final['pessoal'] / (df_final['num_funcionarios'] * 13))
            .round(2)
        )
        logger.info(
            f"  Pessoal por funcionário calculado para "
            f"{df_final['desp_pessoal_por_func_mes_rs'].notna().sum()} combinações empresa/ano"
        )
    else:
        df_final['num_funcionarios'] = pd.NA
        df_final['desp_pessoal_por_func_mes_rs'] = pd.NA
        logger.warning("  Pessoal por funcionário não calculado (arquivo não carregado).")

    # -------------------------------------------------------
    # Diagnóstico de cobertura — facilita manutenção futura
    # -------------------------------------------------------
    logger.info("\n=== DIAGNÓSTICO DE COBERTURA ===")

    # UOs que existem no arquivo mas não estão no mapa (dados descartados)
    uos_sem_mapa = (
        df[df['sigla_empresa'].isna()]['UO']
        .value_counts()
    )
    if uos_sem_mapa.empty:
        logger.info("  ✅ Todas as UOs mapeadas.")
    else:
        logger.warning(
            f"  ⚠️  {len(uos_sem_mapa)} UO(s) NÃO mapeadas "
            f"(linhas descartadas — adicionar ao MAPA_UO_SIGLA se necessário):"
        )
        for uo, n in uos_sem_mapa.items():
            logger.warning(f"    [{n:>4} linhas] {uo}")

    # Códigos de fonte que foram para OUTROS (não entram no numerador Tesouro)
    outros = (
        df[df['tipo_fonte'] == 'OUTROS']
        .groupby(['Fonte (Cod)', 'Fonte (Cod/Desc)'])['pago']
        .sum()
        .reset_index()
        .assign(pago_mi=lambda x: x['pago'] / 1e6)
        .sort_values('pago_mi', ascending=False)
    )
    outros_signif = outros[outros['pago_mi'].abs() > 1]
    if outros_signif.empty:
        logger.info("  ✅ Nenhum código OUTROS com valor significativo (> R$ 1 Mi).")
    else:
        logger.info(
            f"  ℹ️  {len(outros_signif)} código(s) OUTROS com valor > R$ 1 Mi "
            f"(não entram no numerador Tesouro — verificar se correto):"
        )
        for _, r in outros_signif.iterrows():
            logger.info(
                f"    Fonte {int(r['Fonte (Cod)']):>4} | "
                f"R$ {r['pago_mi']:>8.1f} Mi | {r['Fonte (Cod/Desc)']}"
            )
    logger.info("=== FIM DO DIAGNÓSTICO ===\n")

    # Colunas finais
    df_final = df_final[[
        'exercicio',
        'sigla_empresa',
        'despesas_totais_mi',
        'recursos_tesouro_mi',
        'grau_dependencia_pct',
        'comp_pessoal_correntes_pct',
        'comp_investimentos_pct',
        'despesa_pessoal_mi',
        'num_funcionarios',
        'desp_pessoal_por_func_mes_rs',
    ]]

    df_final = tr.adicionar_metadados(df_final, fonte_dado='SIGA Brasil / Quantitativo de Pessoal')

    logger.info(f"  Concluído: {len(df_final):,} linhas | "
                f"{df_final['sigla_empresa'].nunique()} empresas | "
                f"{df_final['exercicio'].min()}–{df_final['exercicio'].max()}")
    return df_final


# ==============================================================================
# 5. VALIDAÇÃO
# ==============================================================================
def validar(df: pd.DataFrame, force: bool = False) -> bool:
    passou = True

    # 1. Linhas suficientes
    ok = len(df) > 50
    logger.info(f"  {'✅' if ok else '❌'} Linhas suficientes (> 50): {len(df)}")
    if not ok: passou = False

    # 2. Grau de dependência — verifica apenas valores não-nulos
    grau = df['grau_dependencia_pct'].dropna()
    fora = grau[~grau.between(0, 100)]
    nulos = df['grau_dependencia_pct'].isna().sum()

    if len(fora) == 0:
        logger.info(f"  ✅ Grau dependência entre 0–100 "
                    f"({len(grau)} valores válidos, {nulos} nulos)")
    else:
        logger.warning(
            f"  ⚠️  {len(fora)} caso(s) com grau fora de 0–100 "
            f"(provavelmente estornos ou anos com dado parcial):"
        )
        casos = df[~df['grau_dependencia_pct'].between(0, 100)][
            ['exercicio','sigla_empresa','despesas_totais_mi',
             'recursos_tesouro_mi','grau_dependencia_pct']
        ].sort_values('grau_dependencia_pct')
        for _, r in casos.iterrows():
            logger.warning(
                f"    {r['exercicio']} {r['sigla_empresa']:12s} "
                f"total={r['despesas_totais_mi']:,.1f} Mi  "
                f"tesouro={r['recursos_tesouro_mi']:,.1f} Mi  "
                f"grau={r['grau_dependencia_pct']:.1f}%"
            )
        if nulos > 0:
            logger.warning(f"  ⚠️  {nulos} caso(s) com grau = NaN "
                           f"(total de despesas = 0 para aquele ano)")
        # Não bloqueia a carga por casos fora do intervalo — apenas avisa
        # São geralmente anos com poucos meses de dado ou estornos pontuais

    # 3. Empresas-chave
    ok = {'EBSERH', 'EMBRAPA', 'CONAB'}.issubset(set(df['sigla_empresa'].unique()))
    logger.info(f"  {'✅' if ok else '❌'} Empresas-chave presentes")
    if not ok: passou = False

    # 4. Pessoal por funcionário
    ok = df['desp_pessoal_por_func_mes_rs'].notna().any()
    logger.info(f"  {'✅' if ok else '❌'} Despesa pessoal por func calculada "
                f"para ≥ 1 empresa")
    if not ok: passou = False

    if not passou and not force:
        logger.error("Validação falhou. Use FORCE=True para forçar a carga.")
    return passou or force


# ==============================================================================
# 6. PONTO DE ENTRADA
# ==============================================================================
def executar(caminho_dados: str, caminho_pessoal: str, force: bool = False):
    logger.info("=" * 60)
    logger.info("ETL SIGA Brasil — Estatais Dependentes (Pellegrini v2)")
    logger.info("=" * 60)

    df_bruto   = ler_arquivo(caminho_dados)
    df_pessoal = carregar_pessoal(caminho_pessoal)
    df_limpo   = transformar(df_bruto, df_pessoal)

    logger.info("Validando...")
    if not validar(df_limpo, force):
        return

    # Preview
    ano_max = df_limpo['exercicio'].max()
    logger.info(f"\n=== Prévia — {ano_max} (ordenado por grau desc.) ===")
    preview = (
        df_limpo[df_limpo['exercicio'] == ano_max]
        .sort_values('grau_dependencia_pct', ascending=False)
        [[  'sigla_empresa', 'despesas_totais_mi', 'recursos_tesouro_mi',
            'grau_dependencia_pct', 'comp_pessoal_correntes_pct',
            'comp_investimentos_pct', 'num_funcionarios',
            'desp_pessoal_por_func_mes_rs'
        ]]
    )
    logger.info(preview.to_string(index=False))

    ok = utils.subir_para_bigquery(
        df_limpo, DATASET_ID, TABELA_ID, if_exists='replace'
    )
    logger.info("✅ Carga concluída." if ok else "❌ Falha na carga.")
    logger.info("=" * 60)


if __name__ == "__main__":
    CAMINHO = BASE_DADOS + r"\processed\despesas_estatais_nao_dep_1.xlsx"
    FORCE   = False
    executar(CAMINHO, CAMINHO_PESSOAL, force=FORCE)