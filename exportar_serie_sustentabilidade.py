"""
Exporta série histórica 2008-2025 de indicadores de sustentabilidade
econômico-financeira das estatais federais.

Fontes LOCAIS (sem BigQuery):
  - Histórico 2008-2024: Estatais_Dados_historicos___1988___2025.xlsx
  - Trimestral 2025    : Dados_contabeis_2025_extracao_02_06_26.xlsx (4T apenas)
  - Cadastral          : sest-identificacao-empresas-ativas.csv

Saída: Excel com duas abas — Dependentes e Nao_Dependentes
Formato: long (empresa | ano | dependencia | setor | indicador | valor)

Como usar (Spyder, IPython Console):
    %run "CAMINHO\\exportar_serie_sustentabilidade.py"

--------------------------------------------------------------------------
CORREÇÕES APLICADAS NESTA VERSÃO (ver comentários "# CORRIGIDO:" no corpo):

1) filtrar(): toda comparação/mapeamento de nome de empresa (CONTINUIDADE e
   EMPRESAS_PRINCIPAIS) agora acontece sobre a coluna "empresa" já normalizada
   em maiúsculas. Antes, a base histórica não normalizava o sigla no
   carregamento, então "NAV Brasil (Grupo)" (histórico) e "GRUPO NAV Brasil"
   (2025) nunca batiam com a entrada "GRUPO NAV BRASIL" de EMPRESAS_PRINCIPAIS,
   e a empresa inteira desaparecia da base, em todos os anos, sem aviso.

2) CONTINUIDADE: a chave "GRUPO NAV BRASIL" apontava para "NAV Brasil (Grupo)",
   um nome que não existe em EMPRESAS_PRINCIPAIS — ou seja, o próprio
   mapeamento causava a exclusão. Corrigido para apontar para o nome
   canônico correto ("GRUPO NAV BRASIL"), e foi adicionada a variante usada
   na base histórica ("NAV BRASIL (GRUPO)") apontando para o mesmo canônico.

3) filtrar(): depois do rename por CONTINUIDADE, mais de um sigla de origem
   pode passar a ter o mesmo nome final (ex.: "ENBPAR" e "GRUPO ENBPAR" viram
   "ENBPAR"). Antes, isso deixava duas linhas separadas para a mesma
   empresa/ano na base final (visível como duplicidade ao filtrar por
   indicador). Agora, quando isso ocorre, mantemos apenas a versão de
   relatório consolidado ("GRUPO ..."), pois ela já inclui a controladora —
   somar as duas dobraria os valores. A versão individual é descartada, e um
   aviso é registrado no log para cada duplicidade resolvida.
--------------------------------------------------------------------------
"""

import sys
import logging
import pandas as pd
import numpy as np
from datetime import date
from pathlib import Path

# ─── CONFIGURAR AQUI ────────────────────────────────────────────────────────
BASE_DIR = Path(r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\data")

ARQ_HIST     = BASE_DIR / "processed" / "Estatais_Dados_historicos___1988___2025.xlsx"
ARQ_2025     = BASE_DIR / "processed" / "Dados_contabeis_2025_extracao_02.06.26.xlsx"
ARQ_CADASTRAL= BASE_DIR / "processed" / "sest-identificacao-empresas-ativas.csv"

OUTPUT_DIR   = BASE_DIR / "processed"
OUTPUT_FILE  = OUTPUT_DIR / f"sustentabilidade_estatais_{date.today():%Y%m%d}.xlsx"
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ─── Empresas principais ─────────────────────────────────────────────────────
EMPRESAS_PRINCIPAIS = {
    "ABGF", "AMAZUL", "APS", "BASA", "BNB", "CBTU", "CDC", "CDP", "CDRJ",
    "CEAGESP", "CEASAMINAS", "CEITEC", "CMB", "CODEBA", "CODERN", "CODESA",
    "CODEVASF", "CONAB", "CONCEIÇÃO", "CPRM", "DATAPREV", "EBC", "EBSERH",
    "ECT", "EMBRAPA", "EMGEA", "EMGEPRON", "ENBPAR", "EPE", "FINEP",
    "GRUPO BB", "GRUPO BNDES", "GRUPO CAIXA", "GRUPO NAV BRASIL", "HCPA",
    "HEMOBRÁS", "IMBEL", "INFRA S.A.", "INFRAERO", "NUCLEP",
    "GR. PETROBRAS", "PPSA", "SERPRO", "TELEBRAS", "TRENSURB",
}

# CORRIGIDO (item 2): "GRUPO NAV BRASIL" agora aponta para si mesmo (nome já
# correto, mantido apenas por clareza/robustez) e foi adicionada a variante
# de nome usada na base histórica ("NAV BRASIL (GRUPO)"), que antes não
# tinha nenhum mapeamento e ficava de fora do filtro final.
# Os siglas "GRUPO ENBPar" e "GRUPO ENBPAR" foram unificados em uma única
# chave, já que a normalização em maiúsculas (aplicada em filtrar()) torna
# as duas formas idênticas.
CONTINUIDADE = {
    "EPL":                  "INFRA S.A.",
    "VALEC":                "INFRA S.A.",
    "GRUPO ENBPAR":         "ENBPAR",
    "NAV BRASIL (GRUPO)":   "GRUPO NAV BRASIL",
    "GRUPO NAV BRASIL":     "GRUPO NAV BRASIL",
}
GRUPOS_NAO_DEP_OVERRIDE = {
    "GR. PETROBRAS", "GRUPO BB", "GRUPO BNDES",
    "GRUPO CAIXA", "GRUPO NAV BRASIL",
}

# ─── Mapeamento de rubricas ──────────────────────────────────────────────────
PLANOS_DRE = ["DRE", "Resultado"]
PLANOS_BAL = ["Balanço", "Ativo e Passivo"]
PLANOS_FC  = ["Fluxo de Caixa", "Fluxo Cx"]

HIST = {
    "RL":      (PLANOS_DRE, 330000),
    "LARF":    (PLANOS_DRE, 404000),
    "RF":      (PLANOS_DRE, 405100),
    "Subv":    (PLANOS_DRE, 407000),
    "LLE":     (PLANOS_DRE, 500000),
    "Dep1":    (PLANOS_DRE, 343000),
    "Dep2":    (PLANOS_DRE, 364300),
    "AC":      (PLANOS_BAL, 110000),
    "Estoques":(PLANOS_BAL, 113000),
    "Imob":    (PLANOS_BAL, 133000),
    "AT":      (PLANOS_BAL, 199999),
    "PC":      (PLANOS_BAL, 210000),
    "PL":      (PLANOS_BAL, 250000),
    "PT":      (PLANOS_BAL, 299999),
    "Atu":     (PLANOS_BAL, 960000),
    "DemProv": (PLANOS_BAL, 911000),
    "FCO":     (PLANOS_FC,  230000),
    "Caixa":   (PLANOS_FC,  700000),
}

BASE25 = {
    "RL":      ("DRE",            230000000),
    "LARF":    ("DRE",            250000000),
    "RF":      ("DRE",            250101000),
    "Subv":    ("DRE",            260100000),
    "LLE":     ("DRE",            290000000),
    "Dep1":    ("DRE",            230110000),
    "Dep2":    ("DRE",            240101250),
    "AC":      ("Balanço",        110100000),
    "Estoques":("Balanço",        110113000),
    "Imob":    ("Balanço",        110207000),
    "AT":      ("Balanço",        110000000),
    "PC":      ("Balanço",        120100000),
    "PL":      ("Balanço",        130000000),
    "PT":      ("Balanço",        120000000),
    "Atu_c":   ("Balanço",        120116070),
    "Atu_nc":  ("Balanço",        120216070),
    # DemProv: 130707070 = R$0 em todas empresas — lacuna trimestral
    "FCO":     ("Fluxo de Caixa", 319900000),
    "Caixa":   ("Fluxo de Caixa", 390000000),
}

MAPA_DEP = {
    "Dependente do Tesouro Nacional":     "Dependente",
    "Não dependente do Tesouro Nacional": "Não dependente",
}

# ─── Cadastral ───────────────────────────────────────────────────────────────
def carregar_cadastral(caminho: Path) -> pd.DataFrame:
    log.info("Carregando cadastral...")
    cad = pd.read_csv(caminho, sep=";", encoding="latin-1", on_bad_lines="skip")
    cad.columns = [c.strip().lower().replace(" ", "_") for c in cad.columns]
    cad["sigla"] = cad["sigla"].astype(str).str.strip().str.upper()
    cad["dep_clean"] = cad["dependencia"].map(MAPA_DEP).fillna("Não dependente")
    cad["setor_clean"] = cad["setor"].fillna("Outros")
    return cad[["sigla", "dep_clean", "setor_clean"]].rename(
        columns={"sigla": "sigla_empresa", "dep_clean": "dependencia", "setor_clean": "setor"}
    )

# ─── Histórico ───────────────────────────────────────────────────────────────
def carregar_historico(caminho: Path) -> pd.DataFrame:
    log.info(f"Carregando histórico: {caminho.name}...")
    df = pd.read_excel(caminho, usecols=[
        "exercicio", "sigla_empresa", "nome_empresa",
        "dependencia", "setor", "nome_tipo_plano_contas", "rubrica", "valor"
    ])
    df["rubrica"] = pd.to_numeric(df["rubrica"], errors="coerce")
    df = df[df["exercicio"].between(2008, 2024)]
    log.info(f"  {len(df):,} linhas | {df['sigla_empresa'].nunique()} empresas")
    return df

def pivotar_historico(df_raw: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for var, (planos, cod) in HIST.items():
        sub = (
            df_raw[df_raw["nome_tipo_plano_contas"].isin(planos) & (df_raw["rubrica"] == cod)]
            .groupby(["exercicio", "sigla_empresa", "dependencia", "setor"])["valor"]
            .sum().reset_index()
        )
        for _, r in sub.iterrows():
            key = (r["exercicio"], r["sigla_empresa"])
            if key not in rows:
                rows[key] = {
                    "ano": r["exercicio"], "empresa": r["sigla_empresa"],
                    "dependencia": r["dependencia"], "setor": r["setor"],
                }
            rows[key][var] = r["valor"]

    df = pd.DataFrame(list(rows.values()))
    df["Deprec"] = df.get("Dep1", pd.Series(0.0)).fillna(0) + df.get("Dep2", pd.Series(0.0)).fillna(0)
    df.drop(columns=["Dep1", "Dep2"], errors="ignore", inplace=True)
    df["fonte"] = "Histórico"
    return df

# ─── 2025 ────────────────────────────────────────────────────────────────────
def carregar_2025(caminho: Path, cad: pd.DataFrame) -> pd.DataFrame:
    log.info(f"Carregando 2025: {caminho.name} (4T)...")
    df = pd.read_excel(caminho, sheet_name="Base", usecols=[
        "Exercício", "Periodicidade", "Empresa Abrev.",
        "Plano", "Cód. Conta", "Valor (Em R$mil)"
    ])
    df = df[df["Periodicidade"] == "4º Trimestre"].copy()
    df.rename(columns={
        "Exercício":        "exercicio",
        "Empresa Abrev.":   "sigla_empresa",
        "Plano":            "nome_tipo_plano_contas",
        "Cód. Conta":       "rubrica",
        "Valor (Em R$mil)": "valor_mil",
    }, inplace=True)
    df["valor"] = pd.to_numeric(df["valor_mil"], errors="coerce") * 1000
    df["rubrica"] = pd.to_numeric(df["rubrica"], errors="coerce")
    df["sigla_empresa"] = df["sigla_empresa"].astype(str).str.strip().str.upper()

    # Merge com cadastral para dependencia e setor
    cad_upper = cad.copy()
    cad_upper["sigla_empresa"] = cad_upper["sigla_empresa"].str.upper()
    df = df.merge(cad_upper, on="sigla_empresa", how="left")

    # Override para grupos sem match no cadastral
    for grp in GRUPOS_NAO_DEP_OVERRIDE:
        mask = df["sigla_empresa"] == grp.upper()
        df.loc[mask, "dependencia"] = "Não dependente"
        df.loc[mask, "setor"] = "Produtivo"

    df["dependencia"] = df["dependencia"].fillna("Não dependente")
    df["setor"] = df["setor"].fillna("Produtivo")
    log.info(f"  {len(df):,} linhas | {df['sigla_empresa'].nunique()} empresas")
    return df

def pivotar_2025(df_raw: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for var, (plano, cod) in BASE25.items():
        sub = (
            df_raw[(df_raw["nome_tipo_plano_contas"] == plano) & (df_raw["rubrica"] == cod)]
            .groupby(["exercicio", "sigla_empresa", "dependencia", "setor"])["valor"]
            .sum().reset_index()
        )
        for _, r in sub.iterrows():
            key = (r["exercicio"], r["sigla_empresa"])
            if key not in rows:
                rows[key] = {
                    "ano": r["exercicio"], "empresa": r["sigla_empresa"],
                    "dependencia": r["dependencia"], "setor": r["setor"],
                }
            rows[key][var] = r["valor"]

    df = pd.DataFrame(list(rows.values()))
    df["Deprec"]  = df.get("Dep1",   pd.Series(0.0)).fillna(0) + df.get("Dep2",  pd.Series(0.0)).fillna(0)
    df["Atu"]     = df.get("Atu_c",  pd.Series(0.0)).fillna(0) + df.get("Atu_nc",pd.Series(0.0)).fillna(0)
    df.drop(columns=["Dep1","Dep2","Atu_c","Atu_nc"], errors="ignore", inplace=True)
    df["DemProv"] = np.nan  # lacuna estrutural na base trimestral
    df["fonte"]   = "2025 (4T)"
    return df

# ─── Filtrar e aplicar continuidade ──────────────────────────────────────────
def filtrar(df: pd.DataFrame) -> pd.DataFrame:
    # CORRIGIDO (item 1): normaliza para maiúsculas ANTES de comparar com
    # CONTINUIDADE e EMPRESAS_PRINCIPAIS. A base histórica não normaliza o
    # sigla no carregamento (carregar_historico não tem .str.upper()), então
    # nomes como "NAV Brasil (Grupo)" nunca batiam com a entrada em maiúsculas
    # de EMPRESAS_PRINCIPAIS e a empresa sumia da base inteira, silenciosamente.
    df["empresa"] = df["empresa"].astype(str).str.strip().str.upper()

    # CORRIGIDO (item 3, parte 1): marca ANTES do rename se a linha veio de um
    # relatório consolidado "de grupo". Usado logo abaixo para resolver
    # duplicidade sem somar os valores (o consolidado já inclui a
    # controladora, então somar dobraria o valor).
    df["_from_grupo"] = df["empresa"].str.startswith("GRUPO")

    continuidade_upper = {k.upper(): v.upper() for k, v in CONTINUIDADE.items()}
    df["empresa"] = df["empresa"].replace(continuidade_upper)

    empresas_upper = {e.upper() for e in EMPRESAS_PRINCIPAIS}
    df = df[df["empresa"].isin(empresas_upper)].copy()
    df = df[~((df["empresa"] == "INB") & (df["ano"] > 2021))]

    # CORRIGIDO (item 3, parte 2): depois do rename, mais de um sigla de
    # origem pode ter virado o mesmo nome final (ex.: "ENBPAR" e
    # "GRUPO ENBPAR" -> "ENBPAR"). Sem este passo, as duas linhas continuavam
    # separadas na base final, aparecendo como duplicidade ao filtrar por
    # empresa/ano/indicador. Mantemos apenas a versão de grupo (mais
    # completa); a individual é descartada.
    n_antes = len(df)
    df = df.sort_values("_from_grupo", ascending=False)
    duplicadas = df.duplicated(subset=["empresa", "ano"], keep="first")
    if duplicadas.any():
        dups_info = df.loc[duplicadas, ["empresa", "ano"]].drop_duplicates()
        for _, r in dups_info.iterrows():
            log.warning(
                f"  Duplicidade grupo/individual resolvida (mantida versão de grupo): "
                f"{r['empresa']} / {int(r['ano'])}"
            )
    df = df[~duplicadas].drop(columns="_from_grupo")
    n_removidas = n_antes - len(df)
    if n_removidas:
        log.info(f"  {n_removidas} linha(s) duplicada(s) removida(s) após unificação de nomes.")

    log.info(f"  Após filtro: {df['empresa'].nunique()} empresas | {df['ano'].nunique()} anos")
    return df

# ─── Calcular indicadores ────────────────────────────────────────────────────
def calcular(df: pd.DataFrame) -> pd.DataFrame:
    def div(num, den, escala=1):
        n = df.get(num, pd.Series(dtype=float)) * escala
        d = df.get(den, pd.Series(dtype=float))
        return np.where((d == 0) | d.isna() | n.isna(), np.nan, n / d)

    for col in ["RL","LARF","LLE","RF","Subv","FCO","PL","AT","AC","PC",
                "PT","Imob","Deprec","Atu","DemProv","Caixa"]:
        df[f"{col}_mi"] = (df.get(col, np.nan) / 1e6).round(2)

    df["Margem_Op_pct"]    = div("LARF","RL",100).round(2)
    df["Margem_Liq_pct"]   = div("LLE", "RL",100).round(2)
    df["RF_RL_pct"]        = div("RF",  "RL",100).round(2)
    df["FCO_LLE_ratio"]    = div("FCO", "LLE").round(3)
    df["Liq_Corrente"]     = div("AC",  "PC").round(3)
    df["Liq_Seca"]         = np.where(
        df.get("PC",pd.Series(dtype=float)) == 0, np.nan,
        (df.get("AC",pd.Series(dtype=float)).fillna(0) -
         df.get("Estoques",pd.Series(dtype=float)).fillna(0)) /
        df.get("PC",pd.Series(dtype=float))
    ).round(3)
    df["Endividamento_pct"]  = div("PT",  "AT",100).round(2)
    df["Deprec_Imob_pct"]   = div("Deprec","Imob",100).round(2)
    df["Atu_PL_pct"]         = div("Atu",  "PL",100).round(2)

    df.sort_values(["empresa","ano"], inplace=True)
    df["RL_lag"]     = df.groupby("empresa")["RL"].shift(1)
    df["Var_RL_pct"] = np.where(
        (df["RL_lag"].isna()) | (df["RL_lag"] == 0), np.nan,
        (df["RL"] / df["RL_lag"] - 1) * 100
    ).round(2)
    df.drop(columns=["RL_lag"], inplace=True)
    return df

# ─── Long format ─────────────────────────────────────────────────────────────
def para_long(df: pd.DataFrame) -> pd.DataFrame:
    ids = ["empresa","ano","dependencia","setor","fonte"]
    vals = [c for c in df.columns if c.endswith("_mi") or c in [
        "Margem_Op_pct","Margem_Liq_pct","RF_RL_pct","FCO_LLE_ratio",
        "Liq_Corrente","Liq_Seca","Endividamento_pct",
        "Deprec_Imob_pct","Atu_PL_pct","Var_RL_pct"
    ]]
    df_long = df[ids+vals].melt(id_vars=ids, value_vars=vals,
                                 var_name="indicador", value_name="valor")
    df_long = df_long[df_long["valor"].notna()].copy()
    df_long["valor"] = df_long["valor"].round(4)
    return df_long.sort_values(["empresa","ano","indicador"]).reset_index(drop=True)

# ─── Dicionário ──────────────────────────────────────────────────────────────
DICIONARIO = pd.DataFrame([
    ("RL_mi",           "R$ Mi", "Receita Líquida",                                                      "Ambas"),
    ("LARF_mi",         "R$ Mi", "Resultado Antes do Resultado Financeiro (Operacional)",                 "Ambas"),
    ("LLE_mi",          "R$ Mi", "Lucro/Prejuízo Líquido do Exercício",                                  "Ambas"),
    ("RF_mi",           "R$ Mi", "Receita Financeira",                                                   "Ambas"),
    ("Subv_mi",         "R$ Mi", "Subvenção do Tesouro Nacional (DRE)",                                  "Dependentes"),
    ("FCO_mi",          "R$ Mi", "Fluxo de Caixa Operacional",                                           "Ambas"),
    ("PL_mi",           "R$ Mi", "Patrimônio Líquido",                                                   "Ambas"),
    ("AT_mi",           "R$ Mi", "Ativo Total",                                                          "Ambas"),
    ("AC_mi",           "R$ Mi", "Ativo Circulante",                                                     "Ambas"),
    ("PC_mi",           "R$ Mi", "Passivo Circulante",                                                   "Ambas"),
    ("PT_mi",           "R$ Mi", "Passivo Total",                                                        "Ambas"),
    ("Imob_mi",         "R$ Mi", "Ativo Imobilizado",                                                    "Ambas"),
    ("Deprec_mi",       "R$ Mi", "Depreciação total na DRE (custos + despesas)",                         "Ambas"),
    ("Atu_mi",          "R$ Mi", "Passivos Atuariais — obrigações com benefícios pós-emprego",           "Ambas"),
    ("DemProv_mi",      "R$ Mi", "Demandas Judiciais Prováveis — NULL em 2025 (lacuna trimestral)",      "Ambas"),
    ("Caixa_mi",        "R$ Mi", "Saldo de Caixa e Equivalentes Final do Período",                       "Ambas"),
    ("Margem_Op_pct",   "%",     "LARF ÷ RL × 100",                                                     "Ambas"),
    ("Margem_Liq_pct",  "%",     "LLE ÷ RL × 100",                                                      "Ambas"),
    ("RF_RL_pct",       "%",     "RF ÷ RL × 100 — peso da receita financeira na receita total",          "Ambas"),
    ("FCO_LLE_ratio",   "×",     "FCO ÷ LLE — conversão do lucro em caixa (>1 saudável; <0 crítico)",   "Ambas"),
    ("Liq_Corrente",    "×",     "AC ÷ PC",                                                              "Não dependentes"),
    ("Liq_Seca",        "×",     "(AC − Estoques) ÷ PC",                                                 "Não dependentes"),
    ("Endividamento_pct","%",    "PT ÷ AT × 100",                                                        "Ambas"),
    ("Deprec_Imob_pct", "%",     "Depreciação ÷ Imobilizado × 100 — proxy de desgaste sem reposição",   "Ambas"),
    ("Atu_PL_pct",      "%",     "Passivos Atuariais ÷ PL × 100",                                       "Ambas"),
    ("Var_RL_pct",      "%",     "(RL_t ÷ RL_t-1 − 1) × 100 — variação anual da receita líquida",      "Ambas"),
], columns=["indicador","unidade","descricao","relevante_para"])

# ─── Exportar ────────────────────────────────────────────────────────────────
def exportar(df_long: pd.DataFrame, caminho: Path):
    dep = df_long[df_long["dependencia"] == "Dependente"]
    nd  = df_long[df_long["dependencia"] == "Não dependente"]
    log.info(f"  Dependentes   : {dep['empresa'].nunique()} empresas | {len(dep):,} linhas")
    log.info(f"  Não dependentes: {nd['empresa'].nunique()} empresas | {len(nd):,} linhas")

    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        dep.to_excel(w, sheet_name="Dependentes",    index=False)
        nd.to_excel(w,  sheet_name="Nao_Dependentes", index=False)
        DICIONARIO.to_excel(w, sheet_name="Dicionario", index=False)

        for sh in ["Dependentes","Nao_Dependentes","Dicionario"]:
            ws = w.sheets[sh]
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(width + 2, 50)

    log.info(f"✅ Arquivo salvo: {caminho}")

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    for arq in [ARQ_HIST, ARQ_2025, ARQ_CADASTRAL]:
        if not Path(arq).exists():
            log.error(f"Arquivo não encontrado: {arq}")
            log.error("Ajuste os caminhos no início do script.")
            sys.exit(1)

    log.info("=== INÍCIO — Série de Sustentabilidade das Estatais (arquivos locais) ===")

    cad       = carregar_cadastral(ARQ_CADASTRAL)
    df_h_raw  = carregar_historico(ARQ_HIST)
    df_25_raw = carregar_2025(ARQ_2025, cad)

    df_h_wide  = pivotar_historico(df_h_raw)
    df_25_wide = pivotar_2025(df_25_raw)

    df_wide = pd.concat([df_h_wide, df_25_wide], ignore_index=True)
    df_wide = filtrar(df_wide)

    log.info("\n  Cobertura por empresa:")
    for emp, g in df_wide.groupby("empresa"):
        log.info(f"    {emp:<22} {int(g['ano'].min())}–{int(g['ano'].max())} ({len(g)} anos)")

    log.info("\n  Calculando indicadores...")
    df_wide = calcular(df_wide)

    df_long = para_long(df_wide)
    log.info(f"\n  Total de registros long: {len(df_long):,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    exportar(df_long, OUTPUT_FILE)
    log.info(f"\n=== FIM === {OUTPUT_FILE}")

if __name__ == "__main__":
    main()