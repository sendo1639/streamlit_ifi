"""
ETL: Calendário de divulgações — IBGE + Banco Central
=======================================================
Grava numa tabela única:  dados_macroeconomicos.calendario_divulgacoes
(para o aviso de "próximas divulgações" no dashboard).

Fontes (validadas em 24/09/2026):
  - IBGE: API oficial de calendário
        servicodados.ibge.gov.br/api/v3/calendario/?de=MM-DD-AAAA&ate=MM-DD-AAAA&qtd=N
    Horário vem em UTC ("12:00:00" = 9h de Brasília, padrão do IBGE) —
    convertido para horário de Brasília (UTC−3, sem horário de verão).
  - BCB: feeds iCalendar (.ics) oficiais, listados em
        bcb.gov.br/acessoinformacao/calendariobc_ics
        bcb.gov.br/api/exportarics/sitebcb/agendaics?lista=<nome da lista>
    Horário já vem em America/Sao_Paulo. As reuniões do Copom vêm como
    dois eventos (um por dia, sem hora) — agrupados num só "Copom — decisão"
    no 2º dia, quando o comunicado é divulgado (após o fechamento do mercado).

Escopo: só os produtos que conversam com o monitor (mapas IBGE_PRODUTOS e
BCB_LISTAS abaixo). Para incluir outro, acrescentar uma entrada.
Janela: de JANELA_PASSADO_DIAS atrás até JANELA_FUTURO_DIAS à frente — o
passado permite mostrar "última divulgação".

Carga: recarga completa (replace). Se uma fonte falhar, as linhas dela da
versão anterior do BigQuery são mantidas.

Como usar:
    python etl_calendario.py
"""

import re
import sys
import time
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from urllib.parse import quote

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
except ImportError as e:
    logger.critical(f"Módulo não encontrado: {e}")
    sys.exit(1)

DATASET_ID = 'dados_macroeconomicos'
TABELA_ID = 'calendario_divulgacoes'

URL_IBGE = "https://servicodados.ibge.gov.br/api/v3/calendario/"
URL_BCB_ICS = "https://www.bcb.gov.br/api/exportarics/sitebcb/agendaics?lista={lista}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"}
TIMEOUT = 60
MAX_RETRIES = 3
JANELA_PASSADO_DIAS = 400
JANELA_FUTURO_DIAS = 460
FUSO_IBGE_UTC = timedelta(hours=-3)   # UTC → Brasília

# produto_id do IBGE → (nome curto, tema, onde o dado está no BigQuery)
IBGE_PRODUTOS = {
    9256: ('IPCA', 'Inflação', 'ibge_sidra: 1737, 7060'),
    9260: ('IPCA-15', 'Inflação', 'ibge_sidra: 3065'),
    9258: ('INPC', 'Inflação', 'ibge_sidra: 1736'),
    9171: ('PNAD Contínua mensal', 'Mercado de trabalho', 'ibge_sidra: 6381, 6441, 8513, 6318, 6390, 6392'),
    9173: ('PNAD Contínua trimestral', 'Mercado de trabalho', None),
    9294: ('PIM-PF (Indústria)', 'Atividade', 'ibge_sidra: 8888'),
    9229: ('PMS (Serviços)', 'Atividade', 'ibge_sidra: 5906'),
    9227: ('PMC (Comércio)', 'Atividade', 'ibge_sidra: 8880, 8881'),
    9300: ('PIB trimestral', 'Atividade', 'ibge_sidra: 1620, 1621, 5932, 1846'),
}

# lista .ics do BCB → (nome curto, tema, onde o dado está no BigQuery)
BCB_LISTAS = {
    'Reuniões do Copom': ('Copom — decisão', 'Política monetária', 'banco_central_sgs: 432'),
    'Atas e Comunicados do Copom': ('Copom — ata', 'Política monetária', None),
    'Focus': ('Boletim Focus', 'Expectativas', 'focus_*'),
    'Estatísticas fiscais': ('Estatísticas fiscais (NFSP, dívida)', 'Fiscal', None),
    'Estatísticas do setor externo': ('Setor externo', 'Setor externo', None),
    'Estatísticas monetárias e de crédito': ('Moeda e crédito', 'Crédito', None),
    'Estatísticas macroeconômicas': (None, 'Estatísticas macroeconômicas', None),  # nome = título do evento
}

COLUNAS = ['data', 'hora', 'fonte', 'evento', 'titulo', 'referencia', 'tema',
           'dado_no_monitor', 'data_carga']


# ==============================================================================
# ACESSO
# ==============================================================================
def get(url: str, params: dict = None) -> requests.Response:
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"  Tentativa {tentativa}/{MAX_RETRIES} falhou ({url[:90]}): {e}")
            if tentativa == MAX_RETRIES:
                raise
            time.sleep(5 * tentativa)


# ==============================================================================
# IBGE
# ==============================================================================
def referencia_ibge(item: dict) -> str:
    ini = (item.get('mes_referencia_inicio'), item.get('ano_referencia_inicio'))
    fim = (item.get('mes_referencia_fim'), item.get('ano_referencia_fim'))
    if not ini[0] or not ini[1]:
        return None
    if fim[0] and fim[1] and fim != ini:
        return f"{ini[0]:02d}/{ini[1]} a {fim[0]:02d}/{fim[1]}"
    return f"{ini[0]:02d}/{ini[1]}"


def coletar_ibge(inicio: date, fim: date) -> pd.DataFrame:
    params = {'de': f"{inicio:%m-%d-%Y}", 'ate': f"{fim:%m-%d-%Y}", 'qtd': 5000}
    dados = get(URL_IBGE, params).json()
    if dados.get('count', 0) > len(dados.get('items', [])):
        raise ValueError(f"API devolveu {len(dados['items'])} de {dados['count']} itens — paginação truncou")

    linhas = []
    for item in dados['items']:
        produto = IBGE_PRODUTOS.get(item.get('produto_id'))
        if produto is None:
            continue
        momento = datetime.strptime(item['data_divulgacao'], '%d/%m/%Y %H:%M:%S') + FUSO_IBGE_UTC
        linhas.append({
            'data': pd.Timestamp(momento.date()),
            'hora': f"{momento:%H:%M}",
            'fonte': 'IBGE',
            'evento': produto[0],
            'titulo': item['titulo'],
            'referencia': referencia_ibge(item),
            'tema': produto[1],
            'dado_no_monitor': produto[2],
        })
    return pd.DataFrame(linhas)


# ==============================================================================
# BCB (iCalendar)
# ==============================================================================
def ler_ics(texto: str) -> list:
    """Parser mínimo de iCalendar: devolve [{'inicio': datetime, 'dia_inteiro': bool, 'titulo': str}]."""
    texto = texto.replace('\r\n', '\n').replace('\n ', '').replace('\n\t', '')  # "unfold" das linhas
    eventos = []
    for bloco in texto.split('BEGIN:VEVENT')[1:]:
        campos = dict(re.findall(r'^([A-Z\-]+)(?:;[^:\n]*)?:(.*)$', bloco, re.M))
        inicio = campos.get('DTSTART', '').strip()
        titulo = (campos.get('SUMMARY', '')
                  .replace('\\,', ',').replace('\\;', ';').replace('\\n', ' ')
                  .replace('​', '').strip())
        if not inicio or not titulo:
            continue
        momento = datetime.strptime(inicio[:15], '%Y%m%dT%H%M%S') if 'T' in inicio else \
            datetime.strptime(inicio[:8], '%Y%m%d')
        eventos.append({'inicio': momento, 'dia_inteiro': 'T' not in inicio or inicio.endswith('T000000'),
                        'titulo': titulo})
    return eventos


def agrupar_reunioes_copom(eventos: list) -> list:
    """Dias consecutivos de reunião viram um evento só, no último dia (quando sai a decisão)."""
    dias = sorted({e['inicio'].date() for e in eventos})
    reunioes, atual = [], []
    for d in dias:
        if atual and (d - atual[-1]).days > 1:
            reunioes.append(atual)
            atual = []
        atual.append(d)
    if atual:
        reunioes.append(atual)
    return [{'inicio': datetime.combine(r[-1], datetime.min.time()), 'dia_inteiro': True,
             'titulo': f"Reunião do Copom ({r[0]:%d/%m}{'–' + format(r[-1], '%d/%m') if len(r) > 1 else ''})"}
            for r in reunioes]


def coletar_bcb(inicio: date, fim: date) -> pd.DataFrame:
    linhas = []
    for lista, (nome, tema, dado) in BCB_LISTAS.items():
        eventos = ler_ics(get(URL_BCB_ICS.format(lista=quote(lista))).text)
        if not eventos:
            raise ValueError(f"lista '{lista}' veio vazia")
        if lista == 'Reuniões do Copom':
            eventos = agrupar_reunioes_copom(eventos)
        for e in eventos:
            if not (inicio <= e['inicio'].date() <= fim):
                continue
            linhas.append({
                'data': pd.Timestamp(e['inicio'].date()),
                'hora': None if e['dia_inteiro'] else f"{e['inicio']:%H:%M}",
                'fonte': 'BCB',
                'evento': nome or e['titulo'],
                'titulo': e['titulo'],
                'referencia': None,
                'tema': tema,
                'dado_no_monitor': dado,
            })
        logger.info(f"  {lista}: {len(eventos)} evento(s) no feed")
    return pd.DataFrame(linhas)


# ==============================================================================
# VALIDAÇÃO E CARGA
# ==============================================================================
def validar(df: pd.DataFrame, fonte: str) -> list:
    if df.empty:
        return ["nenhum evento"]
    problemas = []
    futuros = df[df['data'] >= pd.Timestamp(date.today())]
    if futuros.empty:
        problemas.append("nenhum evento futuro")
    if df.duplicated(subset=['data', 'hora', 'evento', 'titulo']).any():
        problemas.append("eventos duplicados")
    return problemas


def carregar_fontes_atuais(fontes: list) -> pd.DataFrame:
    lista = ", ".join(f"'{f}'" for f in fontes)
    sql = f"SELECT * FROM `{utils.PROJECT_ID}.{DATASET_ID}.{TABELA_ID}` WHERE fonte IN ({lista})"
    return utils.get_bq_client().query(sql).to_dataframe()


def executar() -> bool:
    logger.info("=" * 60)
    logger.info("ETL Calendário de divulgações — IBGE + BCB")
    logger.info("=" * 60)

    hoje = date.today()
    inicio, fim = hoje - timedelta(days=JANELA_PASSADO_DIAS), hoje + timedelta(days=JANELA_FUTURO_DIAS)
    logger.info(f"Janela: {inicio} → {fim}")

    coletados, falhas = [], []
    for fonte, coletor in [('IBGE', coletar_ibge), ('BCB', coletar_bcb)]:
        logger.info(f"{fonte}...")
        try:
            df = coletor(inicio, fim)
            problemas = validar(df, fonte)
        except Exception as e:
            problemas = [f"erro na coleta: {e}"]
        if problemas:
            logger.error(f"  ❌ {fonte}: {'; '.join(problemas)}")
            falhas.append(fonte)
            continue
        prox = df[df['data'] >= pd.Timestamp(hoje)].sort_values(['data', 'hora'])
        logger.info(f"  ✅ {len(df):,} evento(s) | {len(prox):,} futuros | último: {df['data'].max():%d/%m/%Y}")
        coletados.append(df)

    if falhas:
        logger.warning(f"Fontes com falha: {falhas} — mantendo a versão atual do BigQuery.")
        try:
            coletados.append(carregar_fontes_atuais(falhas))
        except NotFound:
            logger.warning(f"{TABELA_ID} ainda não existe (primeira carga) — seguindo sem as fontes com falha.")
        except Exception as e:
            logger.error(f"Não foi possível ler a versão anterior ({e}) — abortando para não perder dados.")
            return False

    if not coletados:
        logger.error("❌ Nada coletado.")
        return False

    df_final = pd.concat(coletados, ignore_index=True)
    df_final['data_carga'] = datetime.now()
    df_final = df_final[COLUNAS].sort_values(['data', 'hora', 'fonte'], na_position='last')

    logger.info(f"Total: {len(df_final):,} evento(s) → {DATASET_ID}.{TABELA_ID}")
    sucesso = utils.subir_para_bigquery(df_final, DATASET_ID, TABELA_ID, if_exists='replace')

    logger.info("=" * 60)
    logger.info("✅ ETL Calendário concluído." if sucesso and not falhas else "❌ ETL Calendário terminou com falhas.")
    logger.info("=" * 60)
    return sucesso and not falhas


if __name__ == "__main__":
    sys.exit(0 if executar() else 1)
