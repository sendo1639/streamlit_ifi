"""
Aba Explorar e baixar — acesso irrestrito a tudo o que o monitor coleta.

  1. Séries: catálogo pesquisável (SGS, IBGE, PTAX) → monta uma seleção,
     compara no gráfico e baixa a série COMPLETA em formato largo.
  2. Focus: expectativas anuais com filtros, histórico inteiro.
  3. Bases completas: qualquer tabela do BigQuery, inteira.

Formatos: Excel (.xlsx) até o limite de linhas do Excel; CSV compactado
(.zip) sempre — separador ';' e vírgula decimal, que o Excel em português
abre direto.
"""

import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from query_engine import (carregar_em_paralelo, carregar_tabela_completa, info_tabelas_macro,
                          sql_sgs, sql_ibge_series, sql_ptax, sql_focus_anual,
                          SQL_CATALOGO_SGS, SQL_CATALOGO_IBGE, SQL_FOCUS_INDICADORES)
from macro import visual as v
from macro.calculos import focus_semanal

LIMITE_EXCEL = 1_048_000          # linhas por planilha no Excel: 1.048.576
LIMITE_SELECAO = 40
MOEDAS = {'USD': 'Dólar', 'EUR': 'Euro'}

DESCRICAO_TABELAS = {
    'banco_central_sgs': 'BCB – séries do SGS (inflação, juros, crédito, câmbio, atividade)',
    'ibge_sidra': 'IBGE – 19 tabelas do SIDRA (IPCA, PNAD, PIM, PMS, PMC, PIB)',
    'focus_expectativas_anuais': 'BCB – Focus: expectativas anuais (todas as posições desde 1999)',
    'focus_expectativas_mensais': 'BCB – Focus: expectativas mensais',
    'focus_inflacao_12meses': 'BCB – Focus: inflação esperada 12 meses à frente',
    'ptax_cotacoes': 'BCB – PTAX de fechamento (USD e EUR desde 2000)',
    'anbima_ettj': 'ANBIMA – curva de juros ETTJ (desde 17/07/2026)',
    'calendario_divulgacoes': 'Calendário de divulgações do IBGE e do BCB',
}


# ==============================================================================
# ARQUIVOS
# ==============================================================================
def csv_zip(df: pd.DataFrame, nome: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{nome}.csv", df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"))
    return buffer.getvalue()


def excel_varias_abas(abas: dict) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nome, df in abas.items():
            df.to_excel(writer, index=False, sheet_name=nome[:31])
    return buffer.getvalue()


# ==============================================================================
# 1. SÉRIES
# ==============================================================================
def _frequencia(inicio, fim, obs) -> str:
    anos = max((pd.Timestamp(fim) - pd.Timestamp(inicio)).days / 365.25, 1)
    por_ano = obs / anos
    return "diária" if por_ano > 150 else "mensal" if por_ano > 10 else "trimestral" if por_ano > 3 else "anual"


@st.cache_data(ttl=3600, show_spinner=False)
def _catalogo() -> pd.DataFrame:
    d = carregar_em_paralelo((
        ('sgs', SQL_CATALOGO_SGS),
        ('ibge', SQL_CATALOGO_IBGE),
        ('ptax', sql_ptax(tuple(MOEDAS))),
    ))
    partes = []

    sgs = d['sgs']
    if not sgs.empty:
        partes.append(pd.DataFrame({
            'id': 'sgs|' + sgs['codigo_sgs'],
            'Fonte': 'BCB – SGS',
            'Série': sgs['nome'],
            'Código': 'SGS ' + sgs['codigo_sgs'],
            'Frequência': [_frequencia(i, f, n) for i, f, n in zip(sgs['inicio'], sgs['fim'], sgs['observacoes'])],
            'Início': sgs['inicio'], 'Fim': sgs['fim'],
        }))

    ibge = d['ibge']
    if not ibge.empty:
        nome = ibge['pesquisa'] + ' – ' + ibge['variavel'] + ibge['categoria'].map(lambda c: f' – {c}' if c else '')
        partes.append(pd.DataFrame({
            'id': ('ibge|' + ibge['tabela'].astype(str) + '|' + ibge['variavel_codigo'].astype(str) + '|'
                   + ibge['categoria'].fillna('')),
            'Fonte': 'IBGE – SIDRA',
            'Série': nome + ' (' + ibge['unidade'] + ')',
            'Código': 'Tabela ' + ibge['tabela'].astype(str) + ' · var. ' + ibge['variavel_codigo'].astype(str),
            'Frequência': ibge['periodicidade'],
            'Início': ibge['inicio'], 'Fim': ibge['fim'],
        }))

    ptax = d['ptax']
    for moeda, rotulo in MOEDAS.items():
        p = ptax[ptax['moeda'] == moeda]
        if p.empty:
            continue
        for lado in ['compra', 'venda']:
            partes.append(pd.DataFrame([{
                'id': f'ptax|{moeda}|{lado}', 'Fonte': 'BCB – PTAX',
                'Série': f'PTAX {rotulo} – {lado} (R$)', 'Código': f'PTAX {moeda}', 'Frequência': 'diária',
                'Início': p['data'].min(), 'Fim': p['data'].max(),
            }]))

    cat = pd.concat(partes, ignore_index=True)
    cat['Início'] = pd.to_datetime(cat['Início']).dt.strftime('%d/%m/%Y')
    cat['Fim'] = pd.to_datetime(cat['Fim']).dt.strftime('%d/%m/%Y')
    return cat.sort_values(['Fonte', 'Série']).reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_series(ids: tuple, rotulos: tuple) -> pd.DataFrame:
    """Séries escolhidas, em formato longo: data | série | valor."""
    nome = dict(zip(ids, rotulos))
    sgs = tuple(i.split('|')[1] for i in ids if i.startswith('sgs|'))
    ibge = tuple((int(t), int(var), cat or None) for _, t, var, cat in
                 (i.split('|') for i in ids if i.startswith('ibge|')))
    ptax = tuple(i for i in ids if i.startswith('ptax|'))

    consultas = []
    if sgs:
        consultas.append(('sgs', sql_sgs(sgs)))
    if ibge:
        consultas.append(('ibge', sql_ibge_series(ibge)))
    if ptax:
        consultas.append(('ptax', sql_ptax(tuple({i.split('|')[1] for i in ptax}))))
    d = carregar_em_paralelo(tuple(consultas))

    partes = []
    if 'sgs' in d and not d['sgs'].empty:
        s = d['sgs']
        partes.append(pd.DataFrame({'data': s['data'], 'serie': ('sgs|' + s['codigo_sgs']).map(nome), 'valor': s['valor']}))
    if 'ibge' in d and not d['ibge'].empty:
        s = d['ibge']
        chave = 'ibge|' + s['tabela'].astype(str) + '|' + s['variavel_codigo'].astype(str) + '|' + s['categoria'].fillna('')
        partes.append(pd.DataFrame({'data': s['data'], 'serie': chave.map(nome), 'valor': s['valor']}))
    if 'ptax' in d and not d['ptax'].empty:
        s = d['ptax']
        for i in ptax:
            _, moeda, lado = i.split('|')
            p = s[s['moeda'] == moeda]
            partes.append(pd.DataFrame({'data': p['data'], 'serie': nome[i], 'valor': p[lado]}))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=['data', 'serie', 'valor'])


def _series():
    catalogo = _catalogo()
    # A seleção vive na chave do próprio multiselect: mudar o `default` de um
    # widget que já existe não tem efeito no Streamlit.
    st.session_state.setdefault('exp_cesta', [])

    st.markdown("##### 1. Encontre as séries")
    c1, c2 = st.columns([1, 2])
    with c1:
        fontes = st.multiselect("Fonte", sorted(catalogo['Fonte'].unique()),
                                default=sorted(catalogo['Fonte'].unique()), key="exp_fontes")
    with c2:
        busca = st.text_input("Buscar (ex.: IPCA serviços, desocupação, Selic, PIM)", key="exp_busca")
    filtro = catalogo['Fonte'].isin(fontes)
    for termo in busca.lower().split():
        filtro &= (catalogo['Série'] + ' ' + catalogo['Código']).str.lower().str.contains(termo, regex=False)
    visiveis = catalogo[filtro].reset_index(drop=True)
    st.caption(f"{len(visiveis):,} de {len(catalogo):,} séries · marque as linhas e clique em Adicionar."
               .replace(",", "."))

    escolha = st.dataframe(visiveis.drop(columns='id'), hide_index=True, width="stretch", height=300,
                           on_select="rerun", selection_mode="multi-row", key="exp_tabela")
    linhas = escolha.selection.rows if escolha else []
    if st.button(f"➕ Adicionar {len(linhas)} série(s) à seleção", disabled=not linhas, key="exp_add"):
        atuais = st.session_state['exp_cesta']
        novas = [i for i in visiveis.loc[linhas, 'id'] if i not in atuais]
        st.session_state['exp_cesta'] = (atuais + novas)[:LIMITE_SELECAO]
        if len(atuais) + len(novas) > LIMITE_SELECAO:
            st.warning(f"Limite de {LIMITE_SELECAO} séries por seleção — para mais, use Bases completas.")

    st.markdown("##### 2. Séries selecionadas")
    rotulo = dict(zip(catalogo['id'], catalogo['Série']))
    cesta = st.multiselect("Selecionadas (clique no × para remover)", options=st.session_state['exp_cesta'],
                           format_func=lambda i: rotulo.get(i, i), key="exp_cesta")
    if not cesta:
        st.info("Nenhuma série selecionada ainda.")
        return

    longo = _carregar_series(tuple(cesta), tuple(rotulo.get(i, i) for i in cesta))
    if longo.empty:
        st.warning("As séries escolhidas não retornaram dados.")
        return
    largo = longo.pivot_table(index='data', columns='serie', values='valor').reset_index().sort_values('data')
    largo = largo[['data'] + [rotulo.get(i, i) for i in cesta if rotulo.get(i, i) in largo.columns]]

    st.markdown("##### 3. Compare e baixe")
    inicio = v.seletor_periodo("explorar", padrao="Tudo")
    fig = v.figura_base(None, None, altura=460)
    for i, col in enumerate(largo.columns[1:]):
        s = v.recortar(largo[['data', col]].dropna(), inicio)
        v.linha(fig, s['data'], s[col], col, cor=v.CORES[i % len(v.CORES)], largura=2)
    st.plotly_chart(fig, width="stretch", key="graf_explorar")
    st.caption("O período acima vale só para o gráfico — os arquivos trazem a série completa. "
               "Séries com unidades diferentes dividem o mesmo eixo.")

    meta = catalogo[catalogo['id'].isin(cesta)].drop(columns='id')
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("📊 Excel (séries lado a lado + metadados)",
                           excel_varias_abas({'dados': largo, 'metadados': meta}),
                           f"monitor_ifi_series_{date.today():%Y%m%d}.xlsx", key="exp_dl_xlsx", width="stretch")
    with c2:
        st.download_button("📄 CSV largo (;)", largo.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                           f"monitor_ifi_series_{date.today():%Y%m%d}.csv", key="exp_dl_csv", width="stretch")
    with c3:
        st.download_button("📄 CSV longo (data, série, valor)",
                           longo.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                           f"monitor_ifi_series_longo_{date.today():%Y%m%d}.csv", key="exp_dl_longo", width="stretch")
    with st.expander(f"Ver dados ({len(largo):,} linhas)".replace(",", ".")):
        st.dataframe(largo, hide_index=True, width="stretch")


# ==============================================================================
# 2. FOCUS
# ==============================================================================
ESTATISTICAS = {'Mediana': 'mediana', 'Média': 'media', 'Desvio-padrão': 'desvio',
                'Mínimo': 'minimo', 'Máximo': 'maximo', 'Respondentes': 'respondentes'}


def _focus():
    st.markdown("##### Expectativas de mercado (Focus) — anuais")
    indicadores = carregar_em_paralelo((('ind', SQL_FOCUS_INDICADORES),))['ind']
    if indicadores.empty:
        st.warning("Focus indisponível.")
        return
    anos_por_ind = dict(zip(indicadores['indicador'], indicadores['anos']))

    c1, c2 = st.columns(2)
    with c1:
        escolhidos = st.multiselect("Indicadores", list(anos_por_ind),
                                    default=[i for i in ['IPCA', 'PIB Total', 'Selic', 'Câmbio'] if i in anos_por_ind],
                                    key="expf_ind")
        estat = st.multiselect("Estatísticas", list(ESTATISTICAS), default=['Mediana', 'Respondentes'], key="expf_est")
    with c2:
        anos_disp = sorted({a for i in escolhidos for a in anos_por_ind[i]}, reverse=True)
        ano = date.today().year
        anos = st.multiselect("Anos de referência", anos_disp,
                              default=[a for a in (str(ano), str(ano + 1)) if a in anos_disp], key="expf_anos")
        base = st.radio("Base de cálculo", ["30 dias (padrão do relatório)", "5 dias úteis"], horizontal=True,
                        key="expf_base")
        freq = st.radio("Posições", ["Semanal (sextas, como o relatório)", "Diária (todas)"], horizontal=True,
                        key="expf_freq")

    if not (escolhidos and anos and estat):
        st.info("Escolha ao menos um indicador, um ano e uma estatística.")
        return

    df = carregar_em_paralelo((('f', sql_focus_anual(tuple(escolhidos), tuple(anos), '1999-01-01',
                                                     0 if base.startswith("30") else 1)),))['f']
    if freq.startswith("Semanal"):
        # Última posição de cada semana (sexta; quinta quando a sexta é feriado)
        df = focus_semanal(df).drop(columns='semana')
    colunas = ['data', 'indicador', 'ano_referencia'] + [ESTATISTICAS[e] for e in estat]
    df = df[colunas].sort_values(['indicador', 'ano_referencia', 'data'])
    st.caption(f"{len(df):,} linhas · {df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y} · "
               f"formato longo (uma linha por data × indicador × ano)".replace(",", "."))
    st.dataframe(df.head(200), hide_index=True, width="stretch", height=250)

    c1, c2 = st.columns(2)
    with c1:
        if len(df) <= LIMITE_EXCEL:
            st.download_button("📊 Excel", v.para_excel(df, "Focus"), f"focus_{date.today():%Y%m%d}.xlsx",
                               key="expf_xlsx", width="stretch")
        else:
            st.caption("Acima do limite de linhas do Excel — use o CSV.")
    with c2:
        st.download_button("🗜️ CSV compactado (.zip)", csv_zip(df, "focus"), f"focus_{date.today():%Y%m%d}.zip",
                           key="expf_zip", width="stretch")
    st.caption("Fonte: Banco Central — Sistema de Expectativas de Mercado. Câmbio e Selic: valor de fim de ano. "
               "Bases mensais e de inflação 12 meses: em Bases completas.")


# ==============================================================================
# 3. BASES COMPLETAS
# ==============================================================================
@st.cache_data(ttl=3600, max_entries=6, show_spinner=False)
def _arquivo_base(tabela: str, formato: str) -> tuple:
    """
    Arquivo pronto de uma tabela inteira, em cache por 1h: a tabela anual do
    Focus (~1 milhão de linhas) leva ~2,5 min para sair do BigQuery sem o
    pacote google-cloud-bigquery-storage no Python da rede.
    """
    df = carregar_tabela_completa(tabela)
    if formato.startswith("Excel"):
        return v.para_excel(df, tabela), f"{tabela}_{date.today():%Y%m%d}.xlsx"
    return csv_zip(df, tabela), f"{tabela}_{date.today():%Y%m%d}.zip"


def _bases():
    st.markdown("##### Bases completas do BigQuery")
    info = info_tabelas_macro()
    info = info[~info['tabela'].str.endswith('_renovacao_tmp')].copy()
    info['Descrição'] = info['tabela'].map(DESCRICAO_TABELAS).fillna('Tabela de apoio (dado bruto / staging)')
    info = info.sort_values(['Descrição', 'tabela'])
    exibir = pd.DataFrame({
        'Tabela': info['tabela'], 'Conteúdo': info['Descrição'],
        'Linhas': info['linhas'].map(lambda x: f"{x:,}".replace(",", ".")),
        'Tamanho (MB)': info['mb'].map(lambda x: v.num(x, 1)),
        'Atualizada em': info['atualizada_em'].dt.strftime('%d/%m/%Y %H:%M'),
    })
    st.dataframe(exibir, hide_index=True, width="stretch")

    c1, c2, c3 = st.columns([2, 1.3, 1])
    with c1:
        tabela = st.selectbox("Tabela", info['tabela'].tolist(),
                              format_func=lambda t: f"{t} — {DESCRICAO_TABELAS.get(t, 'apoio')}", key="expb_tab")
    linhas = int(info.loc[info['tabela'] == tabela, 'linhas'].iloc[0])
    opcoes = ["CSV compactado (.zip)"] + (["Excel (.xlsx)"] if linhas <= LIMITE_EXCEL else [])
    with c2:
        formato = st.radio("Formato", opcoes, key="expb_fmt")
    with c3:
        st.write("")
        preparar = st.button("⚙️ Preparar arquivo", key="expb_prep", width="stretch")

    if linhas > 300_000:
        minutos = max(1, round(linhas / 1_059_853 * 2.5))
        st.caption(f"Tabela grande ({linhas:,} linhas): a preparação leva cerca de {minutos} min na primeira vez; "
                   "depois fica pronta por 1 hora.".replace(",", "."))
    elif formato.startswith("Excel") and linhas > 100_000:
        st.caption("Excel com mais de 100 mil linhas leva cerca de 1 minuto para ser gerado; o CSV é mais rápido.")

    # A flag evita que trocar de tabela dispare um download pesado sem pedido explícito
    preparados = st.session_state.setdefault('expb_preparados', set())
    if preparar:
        preparados.add((tabela, formato))
    if (tabela, formato) in preparados:
        with st.spinner(f"Baixando {tabela} do BigQuery e gerando o arquivo..."):
            dados, nome = _arquivo_base(tabela, formato)
        st.download_button(f"📥 Baixar {nome} ({v.num(len(dados) / 1e6, 1)} MB)", dados, nome,
                           key="expb_dl", type="primary")
    st.caption("CSV: separador ';' e vírgula decimal (abre direto no Excel em português). "
               "O Excel tem limite de 1.048.576 linhas por planilha — tabelas maiores, só em CSV.")


# ==============================================================================
def render():
    series, focus, bases = v.abas(["Séries", "Expectativas Focus", "Bases completas"], chave="abas_explorar")
    with series:
        if v.aberta(series):
            _series()
    with focus:
        if v.aberta(focus):
            _focus()
    with bases:
        if v.aberta(bases):
            _bases()
