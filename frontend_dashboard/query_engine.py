import sys
import os
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ==============================================================================
# 1. CONFIGURAÇÃO DE AMBIENTE E CAMINHOS
# ==============================================================================
# Identificação dinâmica de diretórios para garantir que o Deploy funcione
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / 'backend_etl' / 'scripts'

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    # Centraliza a conexão através do utils.py
    from utils import get_bq_client, PROJECT_ID
except ImportError:
    st.error(f"❌ Erro Crítico: 'utils.py' não localizado em {SCRIPTS_DIR}")
    st.stop()

# ==============================================================================
# 2. MOTOR DE EXECUÇÃO (Função Genérica)
# ==============================================================================
def executar_query(sql: str) -> pd.DataFrame:
    """
    Executa uma consulta no BigQuery e retorna um DataFrame.
    """
    try:
        client = get_bq_client()
        query_job = client.query(sql)
        return query_job.to_dataframe()
    except Exception as e:
        st.error(f"⚠️ Erro na consulta ao BigQuery: {e}")
        return pd.DataFrame()

# ==============================================================================
# 3. CARREGAMENTO DE DADOS (Com Cache de 1 Hora)
# ==============================================================================

@st.cache_data(ttl=3600)
def carregar_dados_sociais():
    """Busca dados consolidados do PBF/CadÚnico."""
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_sociais.base_consolidada_pbf_cadun` ORDER BY data DESC"
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_macro():
    """Busca indicadores do Banco Central (SGS)."""
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_macroeconomicos.banco_central_sgs` ORDER BY data DESC"
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_fiscais(tipo="reais"):
    """Busca séries do Tesouro Nacional (RTN)."""
    tabela = "rtn_valores_reais_ipca" if tipo == "reais" else "rtn_percentual_pib"
    sql = f"SELECT * FROM `{PROJECT_ID}.dados_fiscais.{tabela}` ORDER BY data_referencia DESC"
    
    df = executar_query(sql)
    if not df.empty and 'data_referencia' in df.columns:
        df = df.rename(columns={'data_referencia': 'data'})
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_ettj():
    """
    Busca a série histórica da curva de juros ETTJ (ANBIMA).
    Colunas: data | vertice_du | nome_variavel | valor
    """
    sql = f"""
        SELECT data, vertice_du, nome_variavel, valor
        FROM `{PROJECT_ID}.dados_macroeconomicos.anbima_ettj`
        ORDER BY data DESC, vertice_du ASC
    """
    df = executar_query(sql)
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df

@st.cache_data(ttl=3600)
def carregar_dados_estatais():
    """
    Busca a base completa de estatais do BigQuery.
    Retorna todos os planos de contas (Balanço, DRE, DVA, Fluxo de Caixa)
    para todos os anos e empresas disponíveis.
    """
    sql = f"""
        SELECT
            exercicio,
            codigo_siest,
            sigla_empresa,
            nome_empresa,
            dependencia,
            setor,
            nome_tipo_plano_contas,
            rubrica,
            rubrica_nome,
            valor
        FROM `{PROJECT_ID}.dados_fiscais.sest_estatais`
        ORDER BY exercicio, sigla_empresa, nome_tipo_plano_contas, rubrica
    """
    return executar_query(sql)


@st.cache_data(ttl=3600)
def carregar_dados_siga_brasil():
    """
    Carrega dados do SIGA Brasil — Estatais Dependentes (Pellegrini v2).
    Tabela: dados_fiscais.siga_brasil_dependentes
 
    Colunas novas em relação à v1:
      despesa_pessoal_mi           — GND Pessoal isolado (R$ Mi)
      num_funcionarios             — quantitativo dez/ano (arquivo pessoal SEST)
      desp_pessoal_por_func_mes_rs — Pellegrini: Pessoal / (Func × 13)
    """
    sql = f"""
        SELECT
            exercicio,
            sigla_empresa,
            despesas_totais_mi,
            recursos_tesouro_mi,
            grau_dependencia_pct,
            comp_pessoal_correntes_pct,
            comp_investimentos_pct,
            despesa_pessoal_mi,
            num_funcionarios,
            desp_pessoal_por_func_mes_rs
        FROM `{PROJECT_ID}.dados_fiscais.siga_brasil_dependentes`
        ORDER BY exercicio, sigla_empresa
    """
    return executar_query(sql)


@st.cache_data(ttl=3600)
def carregar_dados_estatais_2025():
    """
    Carrega dados contábeis trimestrais das estatais (2025+).
    Tabela: dados_fiscais.estatais_2025
    Schema: exercicio, trimestre, periodicidade, universo_cod, universo_desc,
            sigla_empresa, nome_empresa, dependencia, setor, area_atuacao,
            nome_tipo_plano_contas, rubrica, rubrica_nome,
            valor (acumulado no ano), valor_trimestre (isolado do trimestre)

    IMPORTANTE: 'valor' é o acumulado no ano-calendário (1T, 1T+2T, ...),
    como reportado pelo SIEST. 'valor_trimestre' é o valor isolado daquele
    trimestre (calculado no ETL por diferença entre acumulados). Contas de
    Balanço (estoque) têm valor == valor_trimestre, pois são saldos pontuais.
    'valor_trimestre' pode ser NULL quando há um trimestre faltante na série
    (não inferimos esse caso para evitar dado incorreto).
    """
    sql = f"""
        SELECT
            exercicio, trimestre, periodicidade,
            universo_cod, universo_desc,
            sigla_empresa, nome_empresa,
            dependencia, setor, area_atuacao,
            nome_tipo_plano_contas, rubrica, rubrica_nome,
            valor, valor_trimestre
        FROM `{PROJECT_ID}.dados_fiscais.estatais_2025`
        ORDER BY exercicio, trimestre, sigla_empresa
    """
    df = executar_query(sql)
    if df is not None and not df.empty:
        # Rubrica como int para compatibilizar com filtros (vem como string do BQ)
        df['rubrica'] = pd.to_numeric(df['rubrica'], errors='coerce').astype('Int64')
    return df

# ==============================================================================
# 3b. MACROECONOMIA — consultas filtradas no BigQuery (página 01)
# ==============================================================================
# Cada consulta traz só o que o gráfico usa: as tabelas do Focus têm milhões de
# linhas e não podem ser carregadas inteiras. O SQL é montado pelas funções
# sql_*; carregar_* executa uma consulta e carregar_em_paralelo executa várias
# ao mesmo tempo (cada ida ao BigQuery leva ~2s — em série, o Panorama levaria
# ~20s na primeira carga). Parâmetros de lista são tuplas (exigência do cache).
DS_MACRO = f"{PROJECT_ID}.dados_macroeconomicos"


def _lista_sql(valores) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def sql_sgs(codigos: tuple) -> str:
    """Séries do SGS (BCB). Colunas: data, codigo_sgs, nome_variavel, valor."""
    return f"""
        SELECT DATE(data) AS data, codigo_sgs, nome_variavel, valor
        FROM `{DS_MACRO}.banco_central_sgs`
        WHERE codigo_sgs IN ({_lista_sql(codigos)})
        ORDER BY codigo_sgs, data
    """


def sql_ibge(tabela: int, variaveis: tuple = None, categorias: tuple = None) -> str:
    """Uma tabela do SIDRA (ibge_sidra), opcionalmente filtrada por variável e categoria."""
    filtros = [f"tabela = {int(tabela)}"]
    if variaveis:
        filtros.append(f"variavel_codigo IN ({', '.join(str(int(v)) for v in variaveis)})")
    if categorias:
        filtros.append(f"categoria IN ({_lista_sql(categorias)})")
    return f"""
        SELECT DATE(data) AS data, periodo, pesquisa, tabela, variavel_codigo, variavel,
               unidade, categoria_codigo, categoria, valor
        FROM `{DS_MACRO}.ibge_sidra`
        WHERE {' AND '.join(filtros)}
        ORDER BY variavel_codigo, categoria, data
    """


def sql_focus_anual(indicadores: tuple, anos_referencia: tuple, desde: str,
                    base_calculo: int = 0) -> str:
    """
    Focus — expectativas anuais (mediana, média, dispersão, respondentes).
    base_calculo 0 = respostas dos últimos 30 dias (padrão do Relatório Focus);
    1 = últimos 5 dias úteis. Só o IndicadorDetalhe nulo (agregado do indicador;
    no Câmbio é o valor de fim de ano).
    """
    return f"""
        SELECT DATE(Data) AS data, Indicador AS indicador, DataReferencia AS ano_referencia,
               Mediana AS mediana, Media AS media, DesvioPadrao AS desvio,
               Minimo AS minimo, Maximo AS maximo, numeroRespondentes AS respondentes
        FROM `{DS_MACRO}.focus_expectativas_anuais`
        WHERE Indicador IN ({_lista_sql(indicadores)})
          AND DataReferencia IN ({_lista_sql(anos_referencia)})
          AND baseCalculo = {int(base_calculo)}
          AND IndicadorDetalhe IS NULL
          AND Data >= '{desde}'
        ORDER BY indicador, ano_referencia, data
    """


def sql_focus_12m(indicador: str = 'IPCA', suavizada: str = 'S',
                  base_calculo: int = 0, desde: str = '2000-01-01') -> str:
    """Focus — inflação esperada para os próximos 12 meses."""
    return f"""
        SELECT DATE(Data) AS data, Mediana AS mediana, Media AS media,
               Minimo AS minimo, Maximo AS maximo, numeroRespondentes AS respondentes
        FROM `{DS_MACRO}.focus_inflacao_12meses`
        WHERE Indicador = '{indicador}' AND Suavizada = '{suavizada}'
          AND baseCalculo = {int(base_calculo)} AND Data >= '{desde}'
        ORDER BY data
    """


def sql_ptax(moedas: tuple = ('USD',)) -> str:
    """PTAX de fechamento. Colunas: data, moeda, compra, venda."""
    return f"""
        SELECT DATE(data) AS data, moeda, cotacaoCompra AS compra, cotacaoVenda AS venda
        FROM `{DS_MACRO}.ptax_cotacoes`
        WHERE moeda IN ({_lista_sql(moedas)})
        ORDER BY moeda, data
    """


SQL_CALENDARIO = f"""
    SELECT DATE(data) AS data, hora, fonte, evento, titulo, referencia, tema, dado_no_monitor
    FROM `{DS_MACRO}.calendario_divulgacoes`
    ORDER BY data, hora
"""


def _com_datas(df: pd.DataFrame) -> pd.DataFrame:
    if not df.empty and 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_em_paralelo(consultas: tuple) -> dict:
    """
    Executa várias consultas ao mesmo tempo. `consultas` = ((nome, sql), ...).
    Retorna {nome: DataFrame}; uma consulta que falha vira DataFrame vazio
    (e o erro aparece na tela), sem derrubar as demais.
    """
    client = get_bq_client()

    def rodar(item):
        nome, sql = item
        try:
            return nome, _com_datas(client.query(sql).to_dataframe()), None
        except Exception as e:
            return nome, pd.DataFrame(), f"{nome}: {e}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        resultados = list(executor.map(rodar, consultas))
    erros = [erro for _, _, erro in resultados if erro]
    if erros:
        st.error("⚠️ Erro na consulta ao BigQuery — " + " | ".join(erros))
    return {nome: df for nome, df, _ in resultados}


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_sgs(codigos: tuple) -> pd.DataFrame:
    return _com_datas(executar_query(sql_sgs(codigos)))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_ibge(tabela: int, variaveis: tuple = None, categorias: tuple = None) -> pd.DataFrame:
    return _com_datas(executar_query(sql_ibge(tabela, variaveis, categorias)))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_focus_anual(indicadores: tuple, anos_referencia: tuple, desde: str,
                         base_calculo: int = 0) -> pd.DataFrame:
    return _com_datas(executar_query(sql_focus_anual(indicadores, anos_referencia, desde, base_calculo)))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_focus_12m(indicador: str = 'IPCA', suavizada: str = 'S',
                       base_calculo: int = 0, desde: str = '2000-01-01') -> pd.DataFrame:
    return _com_datas(executar_query(sql_focus_12m(indicador, suavizada, base_calculo, desde)))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_ptax(moedas: tuple = ('USD',)) -> pd.DataFrame:
    return _com_datas(executar_query(sql_ptax(moedas)))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_calendario() -> pd.DataFrame:
    return _com_datas(executar_query(SQL_CALENDARIO))


@st.cache_data(ttl=600, show_spinner=False)
def get_status_macro() -> pd.DataFrame:
    """
    Última atualização de cada tabela da página de Macro, em horário de Brasília.
    Usa o metadado 'modified' do BigQuery (sempre UTC) — a coluna data_carga
    mistura UTC (GitHub Actions) com horário local (execução manual).
    """
    tabelas = {
        'BCB – SGS': 'banco_central_sgs',
        'BCB – Focus': 'focus_expectativas_anuais',
        'BCB – PTAX': 'ptax_cotacoes',
        'IBGE – SIDRA': 'ibge_sidra',
        'ANBIMA – ETTJ': 'anbima_ettj',
        'Calendário': 'calendario_divulgacoes',
    }
    try:
        client = get_bq_client()
        with ThreadPoolExecutor(max_workers=6) as executor:
            modificadas = list(executor.map(
                lambda t: client.get_table(f"{DS_MACRO}.{t}").modified, tabelas.values()))
    except Exception:
        return pd.DataFrame(columns=['fonte', 'atualizada_em'])
    df = pd.DataFrame({'fonte': list(tabelas), 'atualizada_em': modificadas})
    df['atualizada_em'] = (pd.to_datetime(df['atualizada_em'], utc=True)
                           .dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None))
    return df


# ==============================================================================
# 4. MONITORAMENTO E STATUS (Sinal de Vida)
# ==============================================================================

def get_status_atualizacao():
    """
    Monitora a saúde do pipeline consultando os metadados das tabelas.
    """
    # Usamos o ID do projeto para evitar erros de localização 404
    sql = f"""
    SELECT 'Macro' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `{PROJECT_ID}.dados_macroeconomicos.banco_central_sgs`
    UNION ALL
    SELECT 'Fiscal' as dominio, MAX(data_carga) as ultima_carga, MAX(data_referencia) as referencia 
    FROM `{PROJECT_ID}.dados_fiscais.rtn_valores_reais_ipca`
    UNION ALL
    SELECT 'Social' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia 
    FROM `{PROJECT_ID}.dados_sociais.base_consolidada_pbf_cadun`
    UNION ALL
    SELECT 'ETTJ' as dominio, MAX(data_carga) as ultima_carga, MAX(data) as referencia
    FROM `{PROJECT_ID}.dados_macroeconomicos.anbima_ettj`
    """
    return executar_query(sql)

def converter_para_csv(df):
    """Auxiliar para exportação de dados no dashboard."""
    return df.to_csv(index=False).encode('utf-8')