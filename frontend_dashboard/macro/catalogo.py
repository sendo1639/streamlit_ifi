"""
Catálogo de séries da página de Macroeconomia.

Toda referência a uma série sai daqui — nunca buscar por pedaço do nome
(`str.contains`), que quebra quando a fonte renomeia algo. Os códigos
foram validados contra os metadados oficiais (SGS/BCB e SIDRA/IBGE).
"""

# --- BCB / SGS -----------------------------------------------------------------
SGS = {
    'ipca_mensal': '433',
    'ipca_12m': '13522',
    'meta_inflacao': '13521',
    'igpm_mensal': '189',
    'selic_meta': '432',
    'selic_efetiva': '1178',
    'selic_mes': '4390',
    'ibcbr': '24363',
    'ibcbr_sa': '24364',
    'dolar_venda': '1',
}

IPCA_ABERTURAS_SGS = {
    'Livres': '11428',
    'Administrados': '4449',
    'Alimentação no domicílio': '27864',
    'Industriais': '27863',
    'Serviços': '10844',
}

# Núcleos que o BCB acompanha. A "média dos núcleos" usa os cinco abaixo
# (EX0, EX3, MS, DP, P55); os demais ficam disponíveis para consulta.
NUCLEOS_MEDIA = {'EX0': '11427', 'EX3': '27839', 'MS': '4466', 'DP': '16122', 'P55': '28750'}
NUCLEOS_OUTROS = {'EX1': '16121', 'EX2': '27838', 'MA': '11426', 'EX-FE': '28751'}

CREDITO_SGS = {
    'Juros médios – Total': '20714',
    'Juros médios – Pessoas jurídicas': '20715',
    'Juros médios – Pessoas físicas': '20716',
    'Custo do Crédito (ICC)': '25351',
}

# --- IBGE / SIDRA: (tabela, variável[, categoria]) ------------------------------
IBGE = {
    'ipca_12m': (1737, 2265),
    'ipca_mensal': (1737, 63),
    'desocupacao': (6381, 4099),
    'participacao': (5944, 4096),
    'informalidade': (8513, 12466),
    'pib_4tri': (5932, 6562, 'PIB a preços de mercado'),
    'pib_tri_sa': (5932, 6564, 'PIB a preços de mercado'),
}

# Atividade mensal: (tabela, rótulo, categoria do índice de VOLUME)
# Variáveis por pesquisa: índice sa, M/M-1 sa, M/M-12, acumulado no ano, 12 meses.
ATIVIDADE_MENSAL = {
    'Indústria (PIM-PF)': (8888, '1 Indústria geral', (12607, 11601, 11602, 11603, 11604)),
    'Serviços (PMS)': (5906, 'Índice de volume de serviços', (7168, 11623, 11624, 11625, 11626)),
    'Varejo restrito (PMC)': (8880, 'Índice de volume de vendas no comércio varejista',
                              (7170, 11708, 11709, 11710, 11711)),
    'Varejo ampliado (PMC)': (8881, 'Índice de volume de vendas no comércio varejista ampliado',
                              (7170, 11708, 11709, 11710, 11711)),
}

# --- Focus ---------------------------------------------------------------------
# Indicadores do quadro principal do Relatório Focus → unidade exibida.
# (Balança comercial fica de fora: só existe aberta em Saldo/Exportações/Importações.)
FOCUS_QUADRO = {
    'IPCA': '%',
    'PIB Total': '%',
    'Câmbio': 'R$/US$ (fim de ano)',
    'Selic': '% a.a. (fim de ano)',
    'IGP-M': '%',
    'IPCA Administrados': '%',
    'Conta corrente': 'US$ bilhões',
    'Investimento direto no país': 'US$ bilhões',
    'Dívida líquida do setor público': '% do PIB',
    'Resultado primário': '% do PIB',
    'Resultado nominal': '% do PIB',
}
