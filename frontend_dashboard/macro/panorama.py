"""Aba Panorama — os números que abrem uma análise de conjuntura + próximas divulgações."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from query_engine import (carregar_em_paralelo, sql_sgs, sql_ibge, sql_focus_anual,
                          sql_focus_12m, sql_ptax, SQL_CALENDARIO)
from macro import visual as v
from macro.calculos import juro_real_ex_ante, ultimo_e_anterior
from macro.catalogo import SGS, IBGE
from macro.calendario import tabela_agenda

DIAS_AGENDA = 14


def _sql_ibge(chave: str) -> str:
    tabela, variavel, *categoria = IBGE[chave]
    return sql_ibge(tabela, (variavel,), tuple(categoria) or None)


def _carregar() -> dict:
    """Todas as consultas do Panorama numa rodada só, em paralelo."""
    hoje = date.today()
    consultas = (
        ('ipca_12m', _sql_ibge('ipca_12m')),
        ('desocupacao', _sql_ibge('desocupacao')),
        ('pib_4tri', _sql_ibge('pib_4tri')),
        ('pib_tri_sa', _sql_ibge('pib_tri_sa')),
        ('selic', sql_sgs((SGS['selic_meta'],))),
        ('focus_12m', sql_focus_12m('IPCA', 'S', 0, desde=f"{hoje.year - 2}-01-01")),
        ('focus_anual', sql_focus_anual(('IPCA', 'Selic'), (str(hoje.year),),
                                        desde=str(hoje - timedelta(days=60)))),
        ('ptax', sql_ptax(('USD',))),
        ('agenda', SQL_CALENDARIO),
    )
    dados = carregar_em_paralelo(consultas)
    return {nome: (df.sort_values('data') if 'data' in df.columns else df) for nome, df in dados.items()}


def _pp(delta) -> str:
    """Variação em pontos percentuais, com sinal explícito (o st.metric colore pelo sinal)."""
    if delta is None or pd.isna(delta):
        return None
    return ('+' if delta >= 0 else '') + v.num(delta, 2, ' p.p.')


def _focus_valor_em(df: pd.DataFrame, data_alvo) -> float:
    """Mediana vigente numa data (último boletim até ela)."""
    anteriores = df[df['data'] <= data_alvo]
    return anteriores['mediana'].iloc[-1] if not anteriores.empty else None


def _linha_1(d: dict):
    c1, c2, c3, c4 = st.columns(4)

    with c1, st.container(border=True):
        ipca = d['ipca_12m']
        ult, ant = ultimo_e_anterior(ipca)
        if ult is not None:
            v.cartao("IPCA – 12 meses", v.num(ult['valor'], 2, '%'),
                     f"IBGE · {v.mes_ano(ult['data'])}",
                     _pp(ult['valor'] - ant['valor']) if ant is not None else None,
                     variacao_invertida=True, ajuda="Variação em relação ao acumulado do mês anterior.")

    selic = d['selic']
    with c2, st.container(border=True):
        if not selic.empty:
            atual = selic['valor'].iloc[-1]
            mudancas = selic[selic['valor'] != atual]
            anterior = mudancas['valor'].iloc[-1] if not mudancas.empty else None
            vigente_desde = selic[selic['data'] > mudancas['data'].max()]['data'].min() if not mudancas.empty else selic['data'].min()
            v.cartao("Selic – meta", v.num(atual, 2, '% a.a.'),
                     f"BCB · vigente desde {v.dia(vigente_desde)}",
                     _pp(atual - anterior) if anterior is not None else None,
                     variacao_invertida=True, ajuda="Variação em relação à meta anterior (última decisão do Copom que alterou a taxa).")

    with c3, st.container(border=True):
        focus12 = d['focus_12m']
        if not selic.empty and not focus12.empty:
            real = juro_real_ex_ante(selic, focus12)
            ult = real.iloc[-1]
            ha_4_sem = real[real['data'] <= ult['data'] - timedelta(days=28)]
            delta = ult['juro_real_ex_ante'] - ha_4_sem['juro_real_ex_ante'].iloc[-1] if not ha_4_sem.empty else None
            v.cartao("Juro real ex-ante", v.num(ult['juro_real_ex_ante'], 2, '% a.a.'),
                     f"BCB · Selic ÷ IPCA esperado 12m ({v.num(ult['ipca_esperado_12m'], 2, '%')})",
                     _pp(delta), variacao_invertida=True,
                     ajuda="Selic meta deflacionada pela mediana do Focus para o IPCA dos próximos 12 meses "
                           "(série suavizada). Variação em relação a 4 semanas antes.")

    with c4, st.container(border=True):
        deso = d['desocupacao']
        ult, ant = ultimo_e_anterior(deso, defasagem=12)
        if ult is not None:
            v.cartao("Taxa de desocupação", v.num(ult['valor'], 1, '%'),
                     f"IBGE · trim. móvel {ult['periodo']}",
                     _pp(ult['valor'] - ant['valor']) if ant is not None else None,
                     variacao_invertida=True, ajuda="Variação em relação ao mesmo trimestre móvel do ano anterior.")


def _linha_2(d: dict):
    c1, c2, c3, c4 = st.columns(4)

    with c1, st.container(border=True):
        pib4 = d['pib_4tri']
        pib_tt = d['pib_tri_sa']
        ult, ant = ultimo_e_anterior(pib4)
        if ult is not None:
            tt = pib_tt['valor'].iloc[-1] if not pib_tt.empty else None
            v.cartao("PIB – acumulado em 4 trimestres", v.num(ult['valor'], 1, '%'),
                     f"IBGE · {v.trimestre(ult['data'])} · T/T-1 dessaz.: {v.num(tt, 1, '%')}",
                     _pp(ult['valor'] - ant['valor']) if ant is not None else None,
                     ajuda="Variação em relação ao acumulado em 4 trimestres do trimestre anterior.")

    with c2, st.container(border=True):
        ptax = d['ptax']
        if not ptax.empty:
            ult = ptax.iloc[-1]
            mes_antes = ptax[ptax['data'] <= ult['data'] - timedelta(days=30)]
            var = (ult['venda'] / mes_antes['venda'].iloc[-1] - 1) * 100 if not mes_antes.empty else None
            v.cartao("Dólar – PTAX venda", f"R$ {v.num(ult['venda'], 4)}",
                     f"BCB · {v.dia(ult['data'])}",
                     None if var is None else (('+' if var >= 0 else '') + v.num(var, 1, '% em 30 dias')),
                     variacao_invertida=True)

    ano = date.today().year
    focus = d['focus_anual']
    for col, indicador, rotulo, sufixo in [(c3, 'IPCA', f"Focus – IPCA {ano}", '%'),
                                           (c4, 'Selic', f"Focus – Selic fim de {ano}", '% a.a.')]:
        with col, st.container(border=True):
            f = focus[focus['indicador'] == indicador].sort_values('data')
            if not f.empty:
                ult = f.iloc[-1]
                antes = _focus_valor_em(f, ult['data'] - timedelta(days=28))
                v.cartao(rotulo, v.num(ult['mediana'], 2, sufixo),
                         f"Mediana · boletim de {v.dia(ult['data'])} · {int(ult['respondentes'])} respostas",
                         _pp(ult['mediana'] - antes) if antes is not None else None,
                         variacao_invertida=True, ajuda="Variação em relação à mediana de 4 semanas antes.")


def render():
    with st.spinner("Carregando indicadores..."):
        d = _carregar()
    st.markdown("#### Indicadores de conjuntura")
    _linha_1(d)
    _linha_2(d)

    st.markdown(f"#### Próximas divulgações ({DIAS_AGENDA} dias)")
    agenda = d['agenda']
    hoje = pd.Timestamp(date.today())
    proximas = agenda[(agenda['data'] >= hoje) & (agenda['data'] <= hoje + timedelta(days=DIAS_AGENDA))]
    if proximas.empty:
        st.caption("Nenhuma divulgação prevista no período.")
    else:
        tabela_agenda(proximas, chave="panorama")
    st.caption("Agenda completa na aba **Calendário**.")
