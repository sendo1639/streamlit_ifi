"""
Aba Banco Central — expectativas Focus, juros, crédito, câmbio e IBC-Br.

Desenho a partir do uso nos RAFs de 2026: mediana do Focus como consenso
(quadro no formato do Relatório Focus e comparação com PLOA/IFI), Selic com
juro real ex-ante (RAF 113, Gráf. 4) e ex-post (RAF 116, Gráf. 2), e juros
do crédito (RAF 116, Gráf. 3).
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from query_engine import (carregar_em_paralelo, sql_sgs, sql_focus_anual, sql_focus_12m, sql_ptax)
from macro import visual as v
from macro.calculos import (acumulado_12m, juro_real, juro_real_ex_ante, tabela_focus,
                            variacao_12m_media)
from macro.catalogo import SGS, CREDITO_SGS, FOCUS_QUADRO

FONTE_FOCUS = "Banco Central — Sistema de Expectativas de Mercado (Focus)"


def _meta_por_ano(meta: pd.DataFrame) -> dict:
    """{ano: meta}; anos futuros herdam a última meta definida."""
    return {int(d.year): val for d, val in zip(meta['data'], meta['valor'])}


def _meta_do_ano(metas: dict, ano: int):
    if not metas:
        return None
    return metas.get(ano, metas[max(metas)] if ano > max(metas) else None)


# ==============================================================================
# EXPECTATIVAS (FOCUS)
# ==============================================================================
def _quadro_focus():
    st.markdown("##### Quadro de expectativas — formato do Relatório Focus")
    ano = date.today().year
    anos = (str(ano), str(ano + 1))

    c1, c2 = st.columns([1, 2])
    with c2:
        base = st.radio("Base de cálculo da mediana",
                        ["Respostas dos últimos 30 dias (padrão do relatório)", "Últimos 5 dias úteis"],
                        horizontal=True, key="focus_base")
    base_calculo = 0 if base.startswith("Respostas") else 1

    dados = carregar_em_paralelo((
        ('focus', sql_focus_anual(tuple(FOCUS_QUADRO), anos, desde=str(date.today() - timedelta(days=500)),
                                  base_calculo=base_calculo)),
    ))['focus']
    if dados.empty:
        st.warning("Sem dados do Focus.")
        return

    # Datas de referência: sextas-feiras (posição usada no relatório de segunda) + a mais recente
    # Opções como texto ISO ('2026-09-04'): datas numpy no selectbox confundem dia e mês
    datas = sorted({pd.Timestamp(d).strftime('%Y-%m-%d') for d in dados['data']}, reverse=True)
    sextas = [d for d in datas if pd.Timestamp(d).weekday() == 4]
    opcoes = sorted(set(sextas[:52]) | {datas[0]}, reverse=True)
    with c1:
        data_ref = st.selectbox("Posição de", opcoes, format_func=lambda d: v.dia(d), key="focus_data_ref",
                                help="Sexta-feira = posição publicada no Relatório Focus da segunda seguinte. "
                                     "Use uma data antiga para reproduzir o 'Focus de [data]' citado num RAF.")

    quadro = tabela_focus(dados, pd.Timestamp(data_ref))
    if quadro.empty:
        st.info("Sem dados na data escolhida.")
        return

    linhas = []
    for indicador, unidade in FOCUS_QUADRO.items():
        for a in anos:
            q = quadro[(quadro['indicador'] == indicador) & (quadro['ano'] == a)]
            if q.empty:
                continue
            q = q.iloc[0]
            linhas.append({
                'Indicador': indicador, 'Unidade': unidade, 'Ano': a,
                'Há 4 semanas': v.num(q['ha_4_semanas'], 2), 'Há 1 semana': v.num(q['ha_1_semana'], 2),
                'Hoje': v.num(q['hoje'], 2),
                'Comportamento semanal': f"{q['sentido']} ({q['semanas']})" if q['sentido'] else '',
                'Respostas': int(q['respondentes']) if pd.notna(q['respondentes']) else None,
            })
    tabela = pd.DataFrame(linhas)
    st.dataframe(tabela, hide_index=True, width="stretch", key="focus_quadro")
    rodape, botao = st.columns([5, 1])
    with rodape:
        st.caption(f"Fonte: {FONTE_FOCUS} · Posição de {v.dia(data_ref)} · Mediana. "
                   "Comportamento semanal: ▲ alta, ▼ queda, = estabilidade; entre parênteses, "
                   "semanas consecutivas (comparação de sexta a sexta, como no relatório).")
    with botao:
        st.download_button("📥 Excel", v.para_excel(tabela, "Focus"), f"focus_{pd.Timestamp(data_ref):%Y%m%d}.xlsx",
                           key="dl_focus_quadro", width="stretch")


def _evolucao_focus():
    st.markdown("##### Evolução das expectativas")
    ano = date.today().year
    c1, c2 = st.columns([1, 2])
    with c1:
        indicador = st.selectbox("Indicador", list(FOCUS_QUADRO), key="focus_ev_ind")
    with c2:
        inicio = v.seletor_periodo("focus_ev", padrao="2 anos")
    faixa = st.checkbox(f"Mostrar dispersão (mínimo–máximo) para {ano}", key="focus_ev_faixa")

    anos = (str(ano), str(ano + 1), str(ano + 2))
    d = carregar_em_paralelo((
        ('focus', sql_focus_anual((indicador,), anos, desde=str((inicio or pd.Timestamp('2000-01-01')).date()))),
        ('meta', sql_sgs((SGS['meta_inflacao'],))),
    ))
    focus, metas = d['focus'], _meta_por_ano(d['meta'])
    if focus.empty:
        st.info("Sem dados para o indicador no período.")
        return

    unidade = FOCUS_QUADRO[indicador]
    fig = v.figura_base(f"{indicador} — mediana das expectativas", unidade)
    if faixa:
        f0 = focus[focus['ano_referencia'] == str(ano)]
        v.faixa(fig, f0['data'], f0['minimo'], f0['maximo'], f"Mín–máx {ano}")
    for i, a in enumerate(anos):
        f = focus[focus['ano_referencia'] == a]
        v.linha(fig, f['data'], f['mediana'], a, cor=v.CORES[i])
    meta = _meta_do_ano(metas, ano) if indicador == 'IPCA' else None
    if meta is not None:
        fig.add_hline(y=meta, line=dict(color=v.COR_META, dash="dot"),
                      annotation_text=f"Meta {v.num(meta, 1)}%", annotation_position="bottom right")
    v.mostrar_grafico(fig, focus, FONTE_FOCUS, chave=f"focus_ev_{indicador}",
                      nota="Mediana diária, base de 30 dias. Câmbio e Selic: valor de fim de ano.")


def _inflacao_12m():
    st.markdown("##### Inflação esperada para os próximos 12 meses")
    inicio = v.seletor_periodo("focus_12m", padrao="5 anos")
    d = carregar_em_paralelo((
        ('focus12', sql_focus_12m('IPCA', 'S', 0)),
        ('ipca12', sql_sgs((SGS['ipca_12m'],))),
        ('meta', sql_sgs((SGS['meta_inflacao'],))),
    ))
    focus12, ipca12 = v.recortar(d['focus12'], inicio), v.recortar(d['ipca12'], inicio)
    metas = _meta_por_ano(d['meta'])

    fig = v.figura_base("IPCA — esperado 12 meses à frente × realizado em 12 meses", "%")
    v.linha(fig, focus12['data'], focus12['mediana'], "Esperado 12 meses (Focus, suavizado)", cor=v.CORES[0])
    v.linha(fig, ipca12['data'], ipca12['valor'], "Realizado 12 meses (IBGE)", cor=v.CORES[1])
    if not focus12.empty:
        meses = pd.date_range(focus12['data'].min(), pd.Timestamp.today(), freq='MS')
        v.linha(fig, meses, [_meta_do_ano(metas, m.year) for m in meses], "Meta", cor=v.COR_META,
                tracejado=True, degrau=True, largura=1.5)
    dados = pd.merge_asof(focus12[['data', 'mediana']].rename(columns={'mediana': 'ipca_esperado_12m'}),
                          ipca12[['data', 'valor']].rename(columns={'valor': 'ipca_12m_realizado'}),
                          on='data', direction='backward')
    v.mostrar_grafico(fig, dados, f"{FONTE_FOCUS}; IBGE", chave="focus_12m",
                      nota="Meta de inflação do ano-calendário (CMN).")


# ==============================================================================
# JUROS
# ==============================================================================
def _juros():
    inicio = v.seletor_periodo("juros", padrao="Desde 2012")
    d = carregar_em_paralelo((
        ('selic', sql_sgs((SGS['selic_meta'],))),
        ('selic_mes', sql_sgs((SGS['selic_mes'],))),
        ('ipca12', sql_sgs((SGS['ipca_12m'],))),
        ('focus12', sql_focus_12m('IPCA', 'S', 0)),
    ))
    selic = d['selic']

    # Ex-ante: Selic meta ÷ IPCA esperado 12m (Focus). Mensal, na posição do fim do mês.
    ex_ante = juro_real_ex_ante(selic, d['focus12'])
    ex_ante = ex_ante.set_index('data').resample('ME').last().dropna().reset_index()
    ex_ante['data'] = ex_ante['data'].dt.to_period('M').dt.to_timestamp()

    # Ex-post: Selic acumulada nos últimos 12 meses ÷ IPCA acumulado em 12 meses.
    sm = d['selic_mes'][['data', 'valor']].sort_values('data')
    sm['selic_12m'] = acumulado_12m(sm['valor'])
    ex_post = sm.merge(d['ipca12'][['data', 'valor']].rename(columns={'valor': 'ipca_12m'}), on='data').dropna()
    ex_post['juro_real_ex_post'] = juro_real(ex_post['selic_12m'], ex_post['ipca_12m'])

    selic_r, ex_ante_r, ex_post_r = v.recortar(selic, inicio), v.recortar(ex_ante, inicio), v.recortar(ex_post, inicio)
    fig = v.figura_base("Taxa Selic e taxa de juros real", "% a.a.")
    v.linha(fig, selic_r['data'], selic_r['valor'], "Selic meta", cor=v.AZUL_IFI, degrau=True)
    v.linha(fig, ex_ante_r['data'], ex_ante_r['juro_real_ex_ante'], "Juro real ex-ante", cor=v.CORES[1])
    v.linha(fig, ex_post_r['data'], ex_post_r['juro_real_ex_post'], "Juro real ex-post", cor=v.CORES[2], tracejado=True)
    fig.add_hline(y=0, line=dict(color="#BBBBBB", width=1))
    dados = (ex_ante[['data', 'selic', 'ipca_esperado_12m', 'juro_real_ex_ante']]
             .merge(ex_post[['data', 'selic_12m', 'ipca_12m', 'juro_real_ex_post']], on='data', how='outer')
             .sort_values('data'))
    v.mostrar_grafico(fig, v.recortar(dados, inicio), f"Banco Central (SGS e Focus); IBGE", chave="juros_real",
                      nota="Ex-ante: Selic meta deflacionada pela mediana do Focus para o IPCA 12 meses à frente "
                           "(fim de cada mês). Ex-post: Selic acumulada em 12 meses deflacionada pelo IPCA de 12 meses. "
                           "Equação de Fisher: (1 + i) / (1 + π) − 1.")

    st.markdown("##### Decisões do Copom que alteraram a meta")
    s = selic.sort_values('data')[['data', 'valor']]
    s['anterior'] = s['valor'].shift()
    mudancas = s[s['valor'] != s['anterior']].dropna().tail(15).iloc[::-1]
    variacao = mudancas['valor'] - mudancas['anterior']
    tabela = pd.DataFrame({
        'Vigência': mudancas['data'].map(v.dia),
        'Meta Selic (% a.a.)': mudancas['valor'].map(lambda x: v.num(x, 2)),
        'Variação (p.p.)': variacao.map(lambda x: ('+' if x > 0 else '') + v.num(x, 2)),
    })
    st.dataframe(tabela, hide_index=True, width="stretch", key="copom_decisoes")
    st.caption("Fonte: Banco Central (SGS 432). Reuniões que mantiveram a taxa não aparecem — "
               "veja as datas das reuniões na aba Calendário.")


# ==============================================================================
# CRÉDITO
# ==============================================================================
def _credito():
    inicio = v.seletor_periodo("credito", padrao="10 anos")
    codigos = tuple(CREDITO_SGS.values()) + (SGS['selic_meta'],)
    d = carregar_em_paralelo((('credito', sql_sgs(codigos)),))['credito']
    d = v.recortar(d, inicio)

    fig = v.figura_base("Taxas de juros do crédito e Selic", "% a.a.")
    for i, (nome, codigo) in enumerate(CREDITO_SGS.items()):
        s = d[d['codigo_sgs'] == codigo]
        v.linha(fig, s['data'], s['valor'], nome, cor=v.CORES[i])
    selic = d[d['codigo_sgs'] == SGS['selic_meta']]
    v.linha(fig, selic['data'], selic['valor'], "Selic meta", cor=v.COR_META, degrau=True, tracejado=True, largura=1.5)
    largo = d.pivot_table(index='data', columns='nome_variavel', values='valor').reset_index()
    v.mostrar_grafico(fig, largo, "Banco Central (SGS 20714, 20715, 20716, 25351, 432)", chave="credito",
                      nota="Juros médios: taxa média das concessões do mês (recursos livres e direcionados). "
                           "ICC: custo médio do saldo da carteira.")


# ==============================================================================
# CÂMBIO
# ==============================================================================
def _cambio():
    inicio = v.seletor_periodo("cambio", padrao="5 anos")
    ptax = v.recortar(carregar_em_paralelo((('ptax', sql_ptax(('USD', 'EUR'))),))['ptax'], inicio)
    fig = v.figura_base("PTAX — taxa de venda (fechamento)", "R$ por unidade")
    for i, moeda in enumerate(['USD', 'EUR']):
        s = ptax[ptax['moeda'] == moeda]
        v.linha(fig, s['data'], s['venda'], {'USD': 'Dólar (US$)', 'EUR': 'Euro (€)'}[moeda],
                cor=v.CORES[i], casas=4, sufixo="")
    largo = ptax.pivot_table(index='data', columns='moeda', values='venda').reset_index()
    v.mostrar_grafico(fig, largo, "Banco Central (PTAX, boletim de fechamento)", chave="ptax")


# ==============================================================================
# ATIVIDADE — IBC-Br
# ==============================================================================
def _ibcbr():
    inicio = v.seletor_periodo("ibcbr", padrao="10 anos")
    d = carregar_em_paralelo((('ibc', sql_sgs((SGS['ibcbr'], SGS['ibcbr_sa']))),))['ibc']
    sa = d[d['codigo_sgs'] == SGS['ibcbr_sa']].sort_values('data')
    nsa = d[d['codigo_sgs'] == SGS['ibcbr']].sort_values('data').copy()
    nsa['var_12m'] = variacao_12m_media(nsa['valor'])
    nsa['var_interanual'] = (nsa['valor'] / nsa['valor'].shift(12) - 1) * 100

    c1, c2 = st.columns(2)
    with c1:
        s = v.recortar(sa, inicio)
        fig = v.figura_base("IBC-Br com ajuste sazonal", "índice")
        v.linha(fig, s['data'], s['valor'], "IBC-Br dessazonalizado", cor=v.AZUL_IFI)
        v.mostrar_grafico(fig, s[['data', 'valor']], "Banco Central (SGS 24364)", chave="ibcbr_sa")
    with c2:
        n = v.recortar(nsa, inicio)
        fig = v.figura_base("IBC-Br — variação", "%")
        v.barras(fig, n['data'], n['var_interanual'], "Mês contra mesmo mês do ano anterior", cor="#A9CCE3")
        v.linha(fig, n['data'], n['var_12m'], "Acumulada em 12 meses", cor=v.AZUL_IFI)
        v.mostrar_grafico(fig, n[['data', 'valor', 'var_interanual', 'var_12m']], "Banco Central (SGS 24363)",
                          chave="ibcbr_var")


# ==============================================================================
def render():
    focus, juros, credito, cambio, ibc = v.abas(
        ["Expectativas (Focus)", "Juros", "Crédito", "Câmbio", "Atividade (IBC-Br)"], chave="abas_bcb")
    with focus:
        if v.aberta(focus):
            _quadro_focus()
            st.divider()
            _evolucao_focus()
            st.divider()
            _inflacao_12m()
    with juros:
        if v.aberta(juros):
            _juros()
    with credito:
        if v.aberta(credito):
            _credito()
    with cambio:
        if v.aberta(cambio):
            _cambio()
    with ibc:
        if v.aberta(ibc):
            _ibcbr()
