"""Cálculos usados na página de Macroeconomia."""

import pandas as pd


def acumulado_12m(variacao_mensal: pd.Series) -> pd.Series:
    """
    Acumulado em 12 meses de uma série de variações (ou taxas) mensais em %,
    por composição: ∏(1 + v/100) − 1. Somar as 12 variações — como a página
    antiga fazia — subestima o resultado. Serve também para a Selic mensal.
    """
    fator = 1 + variacao_mensal / 100
    return (fator.rolling(12).apply(lambda x: x.prod(), raw=True) - 1) * 100


def juro_real(nominal_aa: pd.Series, inflacao_aa: pd.Series) -> pd.Series:
    """Equação de Fisher: (1 + i) / (1 + π) − 1, com taxas em % a.a."""
    return ((1 + nominal_aa / 100) / (1 + inflacao_aa / 100) - 1) * 100


def juro_real_ex_ante(selic: pd.DataFrame, focus_12m: pd.DataFrame) -> pd.DataFrame:
    """
    Selic meta deflacionada pela mediana do Focus para o IPCA dos próximos
    12 meses, na mesma data (a última expectativa disponível até aquele dia).
    Entradas: selic[data, valor]; focus_12m[data, mediana].
    """
    base = selic[['data', 'valor']].rename(columns={'valor': 'selic'}).sort_values('data')
    esperada = focus_12m[['data', 'mediana']].rename(columns={'mediana': 'ipca_esperado_12m'}).sort_values('data')
    df = pd.merge_asof(base, esperada, on='data', direction='backward').dropna()
    df['juro_real_ex_ante'] = juro_real(df['selic'], df['ipca_esperado_12m'])
    return df


def variacao_12m_media(indice: pd.Series) -> pd.Series:
    """
    Variação da média de 12 meses sobre os 12 meses anteriores (em %), a partir
    de um índice mensal — o "acumulado em 12 meses" usado para IBC-Br, PIM etc.
    """
    media = indice.rolling(12).mean()
    return (media / media.shift(12) - 1) * 100


# ------------------------------------------------------------------------------
# PIB — contribuições para o crescimento acumulado em 4 trimestres
# ------------------------------------------------------------------------------
COMPONENTES_PIB = {
    'Consumo das famílias': 'Despesa de consumo das famílias',
    'Consumo do governo': 'Despesa de consumo da administração pública',
    'FBCF': 'Formação bruta de capital fixo',
    'Exportações': 'Exportação de bens e serviços',
    'Importações': 'Importação de bens e serviços (-)',
}
PIB = 'PIB a preços de mercado'


def contribuicoes_pib(crescimento_4tri: pd.DataFrame, nominal: pd.DataFrame) -> pd.DataFrame:
    """
    Contribuição (p.p.) de cada componente da demanda para a taxa do PIB
    acumulada em 4 trimestres: crescimento real do componente × participação
    nominal dele no PIB dos 4 trimestres anteriores. Importações entram com
    sinal negativo; a variação de estoques é o resíduo (o SIDRA não traz o
    volume dela). Entradas pivotadas: índice = data, colunas = categoria do SIDRA.
    Conferido contra a Tabela 2 do RAF nº 113 (jun/2026): diferenças de até
    0,1 p.p., por arredondamento/ponderação.
    """
    nominal_4t = nominal.rolling(4).sum()
    participacao = nominal_4t.div(nominal_4t[PIB], axis=0).shift(4)
    ct = pd.DataFrame({nome: crescimento_4tri[cat] * participacao[cat]
                       for nome, cat in COMPONENTES_PIB.items()})
    ct['Importações'] = -ct['Importações']
    ct['PIB'] = crescimento_4tri[PIB]
    ct['Exportações líquidas'] = ct['Exportações'] + ct['Importações']
    ct['Variação de estoques'] = ct['PIB'] - ct[['Consumo das famílias', 'Consumo do governo', 'FBCF',
                                                 'Exportações líquidas']].sum(axis=1)
    ct['Absorção interna'] = ct[['Consumo das famílias', 'Consumo do governo', 'FBCF',
                                 'Variação de estoques']].sum(axis=1)
    return ct.dropna(subset=['PIB', 'Consumo das famílias'])


def contribuicao_grupos_ipca(abertura: pd.DataFrame) -> pd.DataFrame:
    """
    Contribuição (p.p.) de cada grupo do IPCA para a variação do mês:
    variação mensal × peso mensal / 100 (tabela 7060: variáveis 63 e 66).
    """
    largo = abertura.pivot_table(index=['data', 'categoria'], columns='variavel_codigo', values='valor').reset_index()
    largo = largo.rename(columns={63: 'variacao_mes', 66: 'peso', 2265: 'acumulado_12m', 69: 'acumulado_ano'})
    largo['contribuicao'] = largo['variacao_mes'] * largo['peso'] / 100
    return largo


# ------------------------------------------------------------------------------
# FOCUS
# ------------------------------------------------------------------------------
def focus_semanal(df: pd.DataFrame) -> pd.DataFrame:
    """
    O Focus tem posição DIÁRIA; o Relatório Focus (segunda-feira) usa a posição
    da sexta-feira anterior. Aqui: última posição de cada semana encerrada na
    sexta, por indicador e ano de referência.
    """
    d = df.sort_values('data').copy()
    d['semana'] = d['data'].dt.to_period('W-FRI')
    return d.groupby(['indicador', 'ano_referencia', 'semana'], as_index=False).last()


def sequencia_semanal(medianas: pd.Series) -> tuple:
    """
    Comportamento semanal como no Relatório Focus: sentido da última variação
    ('▲', '▼' ou '=') e há quantas semanas seguidas ele se repete.
    """
    variacoes = medianas.diff().dropna().round(6)
    if variacoes.empty:
        return '', 0
    sinal = lambda x: '▲' if x > 0 else '▼' if x < 0 else '='
    atual = sinal(variacoes.iloc[-1])
    n = 0
    for x in reversed(variacoes.tolist()):
        if sinal(x) != atual:
            break
        n += 1
    return atual, n


def tabela_focus(df: pd.DataFrame, data_ref: pd.Timestamp) -> pd.DataFrame:
    """
    Quadro no formato do Relatório Focus para cada (indicador, ano):
    mediana há 4 semanas, há 1 semana e na data de referência, comportamento
    semanal e número de respostas.
    """
    linhas = []
    base = df[df['data'] <= data_ref]
    for (indicador, ano), g in base.groupby(['indicador', 'ano_referencia'], sort=False):
        g = g.sort_values('data')
        hoje = g.iloc[-1]
        valor_em = lambda dias: g[g['data'] <= hoje['data'] - pd.Timedelta(days=dias)]['mediana'].iloc[-1] \
            if (g['data'] <= hoje['data'] - pd.Timedelta(days=dias)).any() else None
        semanal = focus_semanal(g)
        sentido, n = sequencia_semanal(semanal['mediana'])
        linhas.append({
            'indicador': indicador, 'ano': ano,
            'ha_4_semanas': valor_em(28), 'ha_1_semana': valor_em(7), 'hoje': hoje['mediana'],
            'sentido': sentido, 'semanas': n, 'respondentes': hoje['respondentes'],
            'data': hoje['data'],
        })
    return pd.DataFrame(linhas)


def ultimo_e_anterior(serie: pd.DataFrame, coluna: str = 'valor', defasagem: int = 1):
    """(última linha, linha `defasagem` observações antes) de uma série ordenada por data."""
    s = serie.sort_values('data')
    if s.empty:
        return None, None
    anterior = s.iloc[-1 - defasagem] if len(s) > defasagem else None
    return s.iloc[-1], anterior
