"""
Padrão visual da página de Macroeconomia.

Todo gráfico passa por `figura_base` (cores, fonte, números em pt-BR) e é
exibido por `mostrar_grafico`, que acrescenta a linha de fonte/última
observação e o botão de download em Excel com os dados do gráfico.
"""

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

AZUL_IFI = "#003366"
CORES = ["#003366", "#E67E22", "#27AE60", "#8E44AD", "#C0392B", "#16A085", "#7F8C8D", "#2E86C1"]
COR_META = "#7F8C8D"
COR_FAIXA = "rgba(0, 51, 102, 0.12)"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ==============================================================================
# FORMATAÇÃO pt-BR
# ==============================================================================
def num(valor, casas: int = 1, sufixo: str = "") -> str:
    """4.2 → '4,2'; 13428.5 → '13.428,5'. None/NaN → '–'."""
    if valor is None or pd.isna(valor):
        return "–"
    texto = f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto}{sufixo}"


def mes_ano(data) -> str:
    """Timestamp → 'ago/2026'."""
    data = pd.Timestamp(data)
    return f"{MESES[data.month - 1]}/{data.year}"


def dia(data) -> str:
    return pd.Timestamp(data).strftime("%d/%m/%Y")


def trimestre(data) -> str:
    """Timestamp do último mês do trimestre → '2º tri/2026'."""
    data = pd.Timestamp(data)
    return f"{(data.month - 1) // 3 + 1}º tri/{data.year}"


# ==============================================================================
# GRÁFICOS
# ==============================================================================
def figura_base(titulo: str = None, unidade_y: str = None, altura: int = 420) -> go.Figure:
    """
    Figura padrão. Legenda ABAIXO do gráfico, para nunca disputar espaço com o
    título. Sem título, o layout não recebe a chave `title` — passar
    `title=None` faz o Plotly escrever "undefined" no topo.
    """
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=altura,
        separators=",.",
        colorway=CORES,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=50 if titulo else 20, b=20),
        yaxis=dict(title=unidade_y, gridcolor="#EEEEEE"),
        xaxis=dict(gridcolor="#EEEEEE"),
    )
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=15, color=AZUL_IFI),
                                     x=0, xanchor="left", y=0.98, yanchor="top"))
    return fig


def linha(fig: go.Figure, x, y, nome: str, cor: str = None, tracejado: bool = False,
          degrau: bool = False, largura: float = 2.4, casas: int = 2, sufixo: str = ""):
    fig.add_trace(go.Scatter(
        x=x, y=y, name=nome, mode="lines",
        line=dict(color=cor, width=largura, dash="dash" if tracejado else None,
                  shape="hv" if degrau else "linear"),
        hovertemplate=f"%{{y:.{casas}f}}{sufixo}",
    ))


def barras(fig: go.Figure, x, y, nome: str, cor: str = None, casas: int = 2, sufixo: str = ""):
    fig.add_trace(go.Bar(x=x, y=y, name=nome, marker_color=cor,
                         hovertemplate=f"%{{y:.{casas}f}}{sufixo}"))


def faixa(fig: go.Figure, x, inferior, superior, nome: str, cor: str = COR_FAIXA):
    """Área sombreada entre duas séries (ex.: intervalo da meta, mín–máx do Focus)."""
    x = list(x)
    fig.add_trace(go.Scatter(
        x=x + x[::-1], y=list(superior) + list(inferior)[::-1],
        fill="toself", fillcolor=cor, line=dict(width=0),
        name=nome, hoverinfo="skip",
    ))


def para_excel(dados: pd.DataFrame, aba: str = "dados") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dados.to_excel(writer, index=False, sheet_name=aba[:31])
    return buffer.getvalue()


def mostrar_grafico(fig: go.Figure, dados: pd.DataFrame, fonte: str, chave: str,
                    nota: str = None):
    """Exibe o gráfico com rodapé (fonte, última observação, nota) e download em Excel."""
    st.plotly_chart(fig, width="stretch", key=f"graf_{chave}")

    ultima = ""
    if dados is not None and not dados.empty and "data" in dados.columns:
        ultima = f" · Última observação: {dia(dados['data'].max())}"
    rodape, botao = st.columns([5, 1])
    with rodape:
        st.caption(f"Fonte: {fonte}{ultima}" + (f"  \n{nota}" if nota else ""))
    with botao:
        if dados is not None and not dados.empty:
            st.download_button("📥 Excel", data=para_excel(dados), file_name=f"{chave}.xlsx",
                               key=f"dl_{chave}", width="stretch")


def cartao(rotulo: str, valor: str, referencia: str, variacao: str = None,
           variacao_invertida: bool = False, ajuda: str = None):
    """Métrica do Panorama: valor, variação e data de referência."""
    st.metric(rotulo, valor, delta=variacao,
              delta_color="inverse" if variacao_invertida else "normal", help=ajuda)
    st.caption(referencia)


PERIODOS = {"1 ano": 1, "2 anos": 2, "5 anos": 5, "10 anos": 10, "Desde 2012": None, "Tudo": 0}


def seletor_periodo(chave: str, padrao: str = "5 anos") -> pd.Timestamp:
    """Rádio horizontal de período; devolve a data inicial (ou None para 'Tudo')."""
    escolha = st.radio("Período", list(PERIODOS), index=list(PERIODOS).index(padrao),
                       horizontal=True, key=f"per_{chave}", label_visibility="collapsed")
    anos = PERIODOS[escolha]
    if anos == 0:
        return None
    if anos is None:
        return pd.Timestamp("2012-01-01")
    return pd.Timestamp.today().normalize() - pd.DateOffset(years=anos)


def recortar(df: pd.DataFrame, inicio) -> pd.DataFrame:
    return df if inicio is None else df[df['data'] >= inicio]


def abas(nomes: list, chave: str):
    """
    Abas "preguiçosas": só a aba aberta é executada (Streamlit ≥ 1.56, o do
    Python da rede). Sem isso, toda aba roda suas consultas a cada carga.
    Em versões antigas, cai no comportamento normal (todas executam).
    """
    try:
        return st.tabs(nomes, key=chave, on_change="rerun")
    except TypeError:
        return st.tabs(nomes)


def aberta(aba) -> bool:
    """True se a aba está selecionada (ou se a versão não suporta abas preguiçosas)."""
    return getattr(aba, "open", True) is not False


def em_construcao(o_que: str):
    st.info(f"🚧 **{o_que}** — em construção nas próximas fases da reformulação.")
