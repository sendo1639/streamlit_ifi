"""
Aba IBGE — inflação, mercado de trabalho, atividade mensal e PIB.

Desenho a partir do uso nos RAFs de 2026: IPCA × média dos núcleos × meta
(RAF 113, Gráf. 3), aberturas em 12 meses (livres, alimentos, serviços,
industriais), desemprego × participação (RAF 113, Gráf. 2), serviços e
comércio em 12 meses (RAF 110, Gráf. 5) e contribuições para o PIB em
4 trimestres (RAF 113, Tab. 2).
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from query_engine import carregar_em_paralelo, sql_ibge, sql_sgs
from macro import visual as v
from macro.calculos import acumulado_12m, contribuicoes_pib, contribuicao_grupos_ipca
from macro.catalogo import SGS, IPCA_ABERTURAS_SGS, NUCLEOS_MEDIA, ATIVIDADE_MENSAL

FONTE_IBGE = "IBGE (SIDRA)"


def _serie(df: pd.DataFrame, variavel: int, categoria: str = None) -> pd.DataFrame:
    s = df[df['variavel_codigo'] == variavel]
    if categoria is not None:
        s = s[s['categoria'] == categoria]
    return s.sort_values('data')


def _banda_meta(ano: int) -> float:
    """Intervalo de tolerância da meta: ±1,5 p.p. desde 2017; ±2,0 p.p. de 2006 a 2016."""
    return 1.5 if ano >= 2017 else 2.0


# ==============================================================================
# INFLAÇÃO
# ==============================================================================
def _inflacao():
    codigos = tuple(NUCLEOS_MEDIA.values()) + tuple(IPCA_ABERTURAS_SGS.values()) + (SGS['meta_inflacao'],)
    d = carregar_em_paralelo((
        ('ipca', sql_ibge(1737, (63, 2265))),
        ('sgs', sql_sgs(codigos)),
        ('grupos', sql_ibge(7060, (63, 66, 2265))),
        ('ipca15', sql_ibge(3065, (1120,))),
        ('inpc', sql_ibge(1736, (2292,))),
    ))
    ipca, sgs = d['ipca'], d['sgs']
    ipca12 = _serie(ipca, 2265)

    # --- IPCA × média dos núcleos × meta ------------------------------------------
    st.markdown("##### IPCA, média dos núcleos e meta — acumulado em 12 meses")
    inicio = v.seletor_periodo("ipca_nucleos", padrao="5 anos")
    nucleos = {}
    for nome, codigo in NUCLEOS_MEDIA.items():
        s = sgs[sgs['codigo_sgs'] == codigo].sort_values('data').set_index('data')['valor']
        nucleos[nome] = acumulado_12m(s)
    nucleos = pd.DataFrame(nucleos)
    nucleos['media_nucleos'] = nucleos.mean(axis=1, skipna=False)
    nucleos = nucleos.dropna(subset=['media_nucleos']).reset_index()

    meta = sgs[sgs['codigo_sgs'] == SGS['meta_inflacao']]
    metas = {int(dt.year): val for dt, val in zip(meta['data'], meta['valor'])}
    meses = pd.date_range(ipca12['data'].min(), ipca12['data'].max(), freq='MS')
    faixa_meta = pd.DataFrame({'data': meses})
    faixa_meta['meta'] = [metas.get(m.year, metas.get(max(metas))) if m.year >= 1999 else None for m in meses]
    faixa_meta['banda'] = [_banda_meta(m.year) for m in meses]
    faixa_meta = faixa_meta.dropna()

    i12, nuc, fm = v.recortar(ipca12, inicio), v.recortar(nucleos, inicio), v.recortar(faixa_meta, inicio)
    fig = v.figura_base(None, "%")
    v.faixa(fig, fm['data'], fm['meta'] - fm['banda'], fm['meta'] + fm['banda'], "Intervalo de tolerância")
    v.linha(fig, fm['data'], fm['meta'], "Meta", cor=v.COR_META, tracejado=True, degrau=True, largura=1.5)
    v.linha(fig, i12['data'], i12['valor'], "IPCA", cor=v.AZUL_IFI)
    v.linha(fig, nuc['data'], nuc['media_nucleos'], "Média dos núcleos", cor=v.CORES[1])
    dados = (i12[['data', 'valor']].rename(columns={'valor': 'ipca_12m'})
             .merge(nuc.rename(columns={k: f'nucleo_{k}' for k in NUCLEOS_MEDIA}), on='data', how='outer')
             .merge(fm, on='data', how='left'))
    v.mostrar_grafico(fig, dados, "IBGE; Banco Central (núcleos e meta)", chave="ipca_nucleos",
                      nota=f"Média dos núcleos: média simples dos acumulados em 12 meses de "
                           f"{', '.join(NUCLEOS_MEDIA)}. Intervalo: ±1,5 p.p. desde 2017 (±2,0 p.p. antes).")

    # --- Mensal + aberturas ---------------------------------------------------------
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### IPCA — variação mensal e em 12 meses")
        mensal = v.recortar(_serie(ipca, 63), inicio)
        fig = v.figura_base(None, "%", altura=380)
        v.barras(fig, mensal['data'], mensal['valor'], "Mensal", cor="#A9CCE3")
        v.linha(fig, i12['data'], i12['valor'], "12 meses", cor=v.AZUL_IFI)
        dados = mensal[['data', 'valor']].rename(columns={'valor': 'mensal'}).merge(
            i12[['data', 'valor']].rename(columns={'valor': 'acumulado_12m'}), on='data')
        v.mostrar_grafico(fig, dados, f"{FONTE_IBGE}, tabela 1737", chave="ipca_mensal")
    with c2:
        st.markdown("##### Aberturas do IPCA — acumulado em 12 meses")
        fig = v.figura_base(None, "%", altura=380)
        largo = {}
        for i, (nome, codigo) in enumerate(IPCA_ABERTURAS_SGS.items()):
            s = sgs[sgs['codigo_sgs'] == codigo].sort_values('data').reset_index(drop=True)
            s['a12'] = acumulado_12m(s['valor'])
            s = v.recortar(s, inicio)
            v.linha(fig, s['data'], s['a12'], nome, cor=v.CORES[i])
            largo[nome] = s.set_index('data')['a12']
        v.mostrar_grafico(fig, pd.DataFrame(largo).reset_index(), "Banco Central (SGS), com dados do IBGE",
                          chave="ipca_aberturas", nota="Classificação do Banco Central.")

    # --- Grupos: contribuição no mês ------------------------------------------------
    st.markdown("##### Grupos do IPCA — contribuição para a variação do mês")
    grupos = d['grupos']
    grupos = grupos[grupos['categoria'].str.match(r'^\d\.') | (grupos['categoria'] == 'Índice geral')]
    contrib = contribuicao_grupos_ipca(grupos)
    meses_disp = sorted(contrib['data'].unique(), reverse=True)
    mes = st.selectbox("Mês", [pd.Timestamp(m).strftime('%Y-%m-%d') for m in meses_disp],
                       format_func=v.mes_ano, key="ipca_grupos_mes")
    do_mes = contrib[contrib['data'] == pd.Timestamp(mes)]
    geral = do_mes[do_mes['categoria'] == 'Índice geral']
    gr = do_mes[do_mes['categoria'] != 'Índice geral'].copy()
    gr['grupo'] = gr['categoria'].str.replace(r'^\d\.', '', regex=True)
    gr = gr.sort_values('contribuicao')

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = v.figura_base(None, "p.p.", altura=400)
        fig.add_trace(go.Bar(y=gr['grupo'], x=gr['contribuicao'], orientation='h',
                             marker_color=[v.CORES[4] if x > 0 else v.CORES[2] for x in gr['contribuicao']],
                             hovertemplate="%{x:.3f} p.p.<extra></extra>", name="Contribuição"))
        fig.update_layout(hovermode="closest", showlegend=False, xaxis=dict(title="p.p."), yaxis=dict(title=None))
        st.plotly_chart(fig, width="stretch", key="graf_ipca_grupos")
    with c2:
        tabela = pd.DataFrame({
            'Grupo': gr['grupo'][::-1],
            'Peso (%)': gr['peso'][::-1].map(lambda x: v.num(x, 2)),
            'Var. mês (%)': gr['variacao_mes'][::-1].map(lambda x: v.num(x, 2)),
            'Contrib. (p.p.)': gr['contribuicao'][::-1].map(lambda x: v.num(x, 3)),
            '12 meses (%)': gr['acumulado_12m'][::-1].map(lambda x: v.num(x, 2)),
        })
        st.dataframe(tabela, hide_index=True, width="stretch", key="ipca_grupos_tab")
        if not geral.empty:
            g = geral.iloc[0]
            st.caption(f"**Índice geral:** {v.num(g['variacao_mes'], 2)}% no mês · soma das contribuições: "
                       f"{v.num(gr['contribuicao'].sum(), 2)} p.p. · 12 meses: {v.num(g['acumulado_12m'], 2)}%")
    rodape, botao = st.columns([5, 1])
    with rodape:
        st.caption(f"Fonte: {FONTE_IBGE}, tabela 7060 · Contribuição = variação do mês × peso do mês.")
    with botao:
        st.download_button("📥 Excel", v.para_excel(contrib, "grupos"), "ipca_grupos.xlsx",
                           key="dl_ipca_grupos", width="stretch")

    # --- IPCA × IPCA-15 × INPC --------------------------------------------------------
    st.markdown("##### IPCA, IPCA-15 e INPC — acumulado em 12 meses")
    ipca15, inpc = v.recortar(d['ipca15'], inicio), v.recortar(d['inpc'], inicio)
    fig = v.figura_base(None, "%")
    v.linha(fig, i12['data'], i12['valor'], "IPCA", cor=v.AZUL_IFI)
    v.linha(fig, ipca15['data'], ipca15['valor'], "IPCA-15", cor=v.CORES[1])
    v.linha(fig, inpc['data'], inpc['valor'], "INPC", cor=v.CORES[2])
    dados = (i12[['data', 'valor']].rename(columns={'valor': 'IPCA'})
             .merge(ipca15[['data', 'valor']].rename(columns={'valor': 'IPCA-15'}), on='data', how='outer')
             .merge(inpc[['data', 'valor']].rename(columns={'valor': 'INPC'}), on='data', how='outer'))
    v.mostrar_grafico(fig, dados, f"{FONTE_IBGE}, tabelas 1737, 3065 e 1736", chave="ipca_ipca15_inpc",
                      nota="O INPC corrige o salário mínimo e benefícios previdenciários.")


# ==============================================================================
# MERCADO DE TRABALHO
# ==============================================================================
def _trabalho():
    d = carregar_em_paralelo((
        ('deso', sql_ibge(6381, (4099,))),
        ('part', sql_ibge(5944, (4096,))),
        ('info', sql_ibge(8513, (12466,))),
        ('subu', sql_ibge(6441, (4118,))),
        ('rend', sql_ibge(6390, (5933,))),
        ('massa', sql_ibge(6392, (6293,))),
        ('ocup', sql_ibge(6318, (1641,), ('Força de trabalho - ocupada',))),
    ))
    inicio = v.seletor_periodo("trabalho", padrao="Tudo")
    st.caption("PNAD Contínua mensal — trimestres móveis; cada ponto é datado pelo último mês do trimestre.")

    st.markdown("##### Taxa de desemprego e taxa de participação")
    deso, part = v.recortar(d['deso'], inicio), v.recortar(d['part'], inicio)
    fig = v.figura_base(None, "% da força de trabalho")
    v.linha(fig, deso['data'], deso['valor'], "Taxa de desemprego (eixo esq.)", cor=v.AZUL_IFI, casas=1, sufixo="%")
    fig.add_trace(go.Scatter(x=part['data'], y=part['valor'], name="Taxa de participação (eixo dir.)",
                             line=dict(color=v.CORES[1], width=2.4), yaxis="y2", hovertemplate="%{y:.1f}%"))
    fig.update_layout(yaxis2=dict(title="% da população em idade de trabalhar", overlaying="y", side="right",
                                  showgrid=False))
    dados = deso[['data', 'periodo', 'valor']].rename(columns={'valor': 'desemprego'}).merge(
        part[['data', 'valor']].rename(columns={'valor': 'participacao'}), on='data', how='outer')
    v.mostrar_grafico(fig, dados, f"{FONTE_IBGE}, tabelas 6381 e 5944", chave="desemprego_participacao")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Informalidade e subutilização")
        info, subu = v.recortar(d['info'], inicio), v.recortar(d['subu'], inicio)
        fig = v.figura_base(None, "%", altura=380)
        v.linha(fig, info['data'], info['valor'], "Taxa de informalidade", cor=v.CORES[3], casas=1)
        v.linha(fig, subu['data'], subu['valor'], "Taxa composta de subutilização", cor=v.CORES[4], casas=1)
        dados = info[['data', 'valor']].rename(columns={'valor': 'informalidade'}).merge(
            subu[['data', 'valor']].rename(columns={'valor': 'subutilizacao'}), on='data', how='outer')
        v.mostrar_grafico(fig, dados, f"{FONTE_IBGE}, tabelas 8513 e 6441", chave="informalidade")
    with c2:
        st.markdown("##### Rendimento e massa real — variação anual")
        rend, massa, ocup = (x.sort_values('data').set_index('data')['valor'] for x in (d['rend'], d['massa'], d['ocup']))
        var = pd.DataFrame({
            'Rendimento médio real': (rend / rend.shift(12) - 1) * 100,
            'Massa de rendimento real': (massa / massa.shift(12) - 1) * 100,
            'População ocupada': (ocup / ocup.shift(12) - 1) * 100,
        }).dropna(how='all').reset_index()
        var = v.recortar(var, inicio)
        fig = v.figura_base(None, "% (mesmo trimestre do ano anterior)", altura=380)
        for i, col in enumerate(['Rendimento médio real', 'Massa de rendimento real', 'População ocupada']):
            v.linha(fig, var['data'], var[col], col, cor=v.CORES[i], casas=1, sufixo="%")
        fig.add_hline(y=0, line=dict(color="#BBBBBB", width=1))
        v.mostrar_grafico(fig, var, f"{FONTE_IBGE}, tabelas 6390, 6392 e 6318", chave="rendimento",
                          nota="Rendimento habitual de todos os trabalhos, deflacionado pelo IBGE.")


# ==============================================================================
# ATIVIDADE MENSAL (PIM, PMS, PMC)
# ==============================================================================
def _atividade():
    consultas = tuple((nome, sql_ibge(tab, vars_, (cat,))) for nome, (tab, cat, vars_) in ATIVIDADE_MENSAL.items())
    d = carregar_em_paralelo(consultas + (('pim_secoes', sql_ibge(8888, (11604, 11602))),))

    st.markdown("##### Último dado divulgado")
    linhas = []
    for nome, (tab, cat, (v_ind, v_mm, v_a, v_ano, v_12)) in ATIVIDADE_MENSAL.items():
        df = d[nome]
        if df.empty:
            continue
        ult = df['data'].max()
        valor = lambda var: df[(df['variavel_codigo'] == var) & (df['data'] == ult)]['valor']
        pega = lambda var: v.num(valor(var).iloc[0], 1) if not valor(var).empty else '–'
        linhas.append({'Pesquisa': nome, 'Referência': v.mes_ano(ult),
                       'Mês/mês anterior (dessaz.) %': pega(v_mm), 'Mês/mesmo mês ano ant. %': pega(v_a),
                       'Acumulado no ano %': pega(v_ano), 'Acumulado 12 meses %': pega(v_12)})
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch", key="atividade_resumo")
    st.caption(f"Fonte: {FONTE_IBGE} (PIM-PF 8888, PMS 5906, PMC 8880 e 8881) · índices de volume.")

    inicio = v.seletor_periodo("atividade", padrao="10 anos")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Variação acumulada em 12 meses")
        fig = v.figura_base(None, "%", altura=400)
        largo = {}
        for i, (nome, (tab, cat, vars_)) in enumerate(ATIVIDADE_MENSAL.items()):
            s = v.recortar(_serie(d[nome], vars_[4]), inicio)
            v.linha(fig, s['data'], s['valor'], nome, cor=v.CORES[i], casas=1, sufixo="%")
            largo[nome] = s.set_index('data')['valor']
        fig.add_hline(y=0, line=dict(color="#BBBBBB", width=1))
        v.mostrar_grafico(fig, pd.DataFrame(largo).reset_index(), FONTE_IBGE, chave="atividade_12m")
    with c2:
        st.markdown("##### Índices de volume com ajuste sazonal (2022 = 100)")
        fig = v.figura_base(None, "índice (2022 = 100)", altura=400)
        largo = {}
        for i, (nome, (tab, cat, vars_)) in enumerate(ATIVIDADE_MENSAL.items()):
            s = v.recortar(_serie(d[nome], vars_[0]), inicio)
            v.linha(fig, s['data'], s['valor'], nome, cor=v.CORES[i], casas=1)
            largo[nome] = s.set_index('data')['valor']
        fig.add_hline(y=100, line=dict(color="#BBBBBB", width=1, dash="dot"))
        v.mostrar_grafico(fig, pd.DataFrame(largo).reset_index(), FONTE_IBGE, chave="atividade_indices")

    with st.expander("Indústria por seções e atividades (PIM-PF)"):
        pim = d['pim_secoes']
        ult = pim['data'].max()
        tab = pim[pim['data'] == ult].pivot_table(index='categoria', columns='variavel_codigo', values='valor')
        tab = tab.rename(columns={11602: 'Mês/mesmo mês ano ant. %', 11604: 'Acumulado 12 meses %'}) \
            .sort_values('Acumulado 12 meses %').reset_index().rename(columns={'categoria': 'Seção / atividade'})
        for c in ['Mês/mesmo mês ano ant. %', 'Acumulado 12 meses %']:
            tab[c] = tab[c].map(lambda x: v.num(x, 1))
        st.caption(f"Referência: {v.mes_ano(ult)} · ordenado pelo acumulado em 12 meses")
        st.dataframe(tab, hide_index=True, width="stretch", key="pim_secoes")


# ==============================================================================
# PIB TRIMESTRAL
# ==============================================================================
def _pib():
    d = carregar_em_paralelo((
        ('taxas', sql_ibge(5932)),
        ('nominal', sql_ibge(1846, (585,))),
    ))
    taxas = d['taxas']
    inicio = v.seletor_periodo("pib", padrao="10 anos")

    st.markdown("##### PIB — crescimento real")
    tt = v.recortar(_serie(taxas, 6564, 'PIB a preços de mercado'), inicio)
    a4 = v.recortar(_serie(taxas, 6562, 'PIB a preços de mercado'), inicio)
    fig = v.figura_base(None, "%")
    v.barras(fig, tt['data'], tt['valor'], "Trimestre contra trimestre anterior (dessaz.)", cor="#A9CCE3", casas=1)
    v.linha(fig, a4['data'], a4['valor'], "Acumulado em 4 trimestres", cor=v.AZUL_IFI, casas=1)
    dados = tt[['data', 'periodo', 'valor']].rename(columns={'valor': 't_t1_dessaz'}).merge(
        a4[['data', 'valor']].rename(columns={'valor': 'acumulado_4tri'}), on='data', how='outer')
    v.mostrar_grafico(fig, dados, f"{FONTE_IBGE}, tabela 5932", chave="pib_crescimento",
                      nota="Datas no último mês de cada trimestre.")

    st.markdown("##### Contribuições para o crescimento acumulado em 4 trimestres (p.p.)")
    cresc = taxas[taxas['variavel_codigo'] == 6562].pivot_table(index='data', columns='categoria', values='valor')
    nominal = d['nominal'].pivot_table(index='data', columns='categoria', values='valor')
    contrib = contribuicoes_pib(cresc, nominal).reset_index()
    cr = v.recortar(contrib, inicio)
    fig = v.figura_base(None, "p.p.")
    fig.update_layout(barmode="relative")
    for i, comp in enumerate(['Consumo das famílias', 'Consumo do governo', 'FBCF',
                              'Variação de estoques', 'Exportações líquidas']):
        v.barras(fig, cr['data'], cr[comp], comp, cor=v.CORES[i], casas=1)
    v.linha(fig, cr['data'], cr['PIB'], "PIB", cor="#222222", casas=1)
    colunas = ['data', 'PIB', 'Absorção interna', 'Consumo das famílias', 'Consumo do governo', 'FBCF',
               'Variação de estoques', 'Exportações líquidas', 'Exportações', 'Importações']
    v.mostrar_grafico(fig, cr[colunas], f"{FONTE_IBGE}, tabelas 5932 e 1846; cálculo IFI", chave="pib_contribuicoes",
                      nota="Contribuição = crescimento real do componente × participação nominal no PIB dos "
                           "4 trimestres anteriores. Variação de estoques calculada por resíduo.")

    ult = taxas['data'].max()
    st.markdown(f"##### Componentes — {v.trimestre(ult)}")
    tab = taxas[taxas['data'] == ult].pivot_table(index='categoria', columns='variavel_codigo', values='valor')
    tab = tab.rename(columns={6564: 'T/T-1 dessaz. %', 6561: 'T/mesmo tri. ano ant. %',
                              6563: 'Acumulado no ano %', 6562: 'Acumulado 4 tri. %'})
    ordem = [c for c in ['T/T-1 dessaz. %', 'T/mesmo tri. ano ant. %', 'Acumulado no ano %', 'Acumulado 4 tri. %']
             if c in tab.columns]
    categorias = list(dict.fromkeys(taxas.sort_values('categoria_codigo')['categoria']))
    tab = tab.reindex([c for c in categorias if c in tab.index])[ordem].reset_index() \
        .rename(columns={'categoria': 'Componente'})
    for c in ordem:
        tab[c] = tab[c].map(lambda x: v.num(x, 1))
    st.dataframe(tab, hide_index=True, width="stretch", key="pib_componentes")
    st.caption(f"Fonte: {FONTE_IBGE}, tabela 5932 · volume, óticas da produção e da demanda.")


# ==============================================================================
def render():
    inflacao, trabalho, atividade, pib = v.abas(
        ["Inflação", "Mercado de trabalho", "Atividade mensal", "PIB"], chave="abas_ibge")
    with inflacao:
        if v.aberta(inflacao):
            _inflacao()
    with trabalho:
        if v.aberta(trabalho):
            _trabalho()
    with atividade:
        if v.aberta(atividade):
            _atividade()
    with pib:
        if v.aberta(pib):
            _pib()
