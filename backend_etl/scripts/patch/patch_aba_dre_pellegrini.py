# ==============================================================================
# PATCH para 04_Estatais.py — ABA "Desempenho (DRE)"
# Aplica três substituições cirúrgicas no código existente.
#
# COMO USAR:
#   Copie cada bloco "SUBSTITUIR ISSO" → "POR ISSO" manualmente no arquivo,
#   ou rode este script para aplicar automaticamente:
#
#   python patch_aba_dre_pellegrini.py --apply
# ==============================================================================

import sys

ARQUIVO = r"U:\NovaRede_IFI\Dados\monitor_economia_ifi\frontend_dashboard\pages\04_Estatais.py"

# ------------------------------------------------------------------------------
# PATCH 1: Coluna nova na tabela Pellegrini (total_row + df_tab + formatação)
# ------------------------------------------------------------------------------
PATCH_1_ANTES = '''        if not df_pell.empty:
            # Total
            total_row = pd.DataFrame([{
                "sigla_empresa":             "TOTAL",
                "despesas_totais_mi":         df_pell["despesas_totais_mi"].sum().round(1),
                "recursos_tesouro_mi":        df_pell["recursos_tesouro_mi"].sum().round(1),
                "grau_dependencia_pct":       round(
                    df_pell["recursos_tesouro_mi"].sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_pessoal_correntes_pct": round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_pessoal_correntes_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_investimentos_pct":     round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_investimentos_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
            }])
            df_tab = pd.concat([df_pell[list(total_row.columns)], total_row],
                               ignore_index=True)
            df_tab.columns = ["Denominação","Despesas (R$ Mi)","Rec. Tesouro (R$ Mi)",
                               "Grau Depend. (%)","Pessoal e Correntes (%)","Invest. e Inversões (%)"]
            for c in ["Despesas (R$ Mi)","Rec. Tesouro (R$ Mi)"]:
                df_tab[c] = df_tab[c].map(fmt1)
            for c in ["Grau Depend. (%)","Pessoal e Correntes (%)","Invest. e Inversões (%)"]:
                df_tab[c] = df_tab[c].map(lambda x: f"{x:.1f}")'''

PATCH_1_DEPOIS = '''        if not df_pell.empty:
            # Média ponderada de despesa por funcionário (denominador = total func × 13)
            tot_pess_r = (df_pell["despesa_pessoal_mi"].fillna(0) * 1e6).sum()
            tot_func   = df_pell["num_funcionarios"].sum(skipna=True)

            # Total
            total_row = pd.DataFrame([{
                "sigla_empresa":             "TOTAL",
                "despesas_totais_mi":         df_pell["despesas_totais_mi"].sum().round(1),
                "recursos_tesouro_mi":        df_pell["recursos_tesouro_mi"].sum().round(1),
                "grau_dependencia_pct":       round(
                    df_pell["recursos_tesouro_mi"].sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_pessoal_correntes_pct": round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_pessoal_correntes_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "comp_investimentos_pct":     round(
                    (df_pell["despesas_totais_mi"] *
                     df_pell["comp_investimentos_pct"] / 100).sum() /
                    df_pell["despesas_totais_mi"].sum() * 100, 1),
                "desp_pessoal_por_func_mes_rs": round(
                    tot_pess_r / (tot_func * 13), 2)
                    if pd.notna(tot_func) and tot_func > 0 else None,
            }])
            colunas_tab = [
                "sigla_empresa", "despesas_totais_mi", "recursos_tesouro_mi",
                "grau_dependencia_pct", "comp_pessoal_correntes_pct",
                "comp_investimentos_pct", "desp_pessoal_por_func_mes_rs",
            ]
            df_tab = pd.concat(
                [df_pell[[c for c in colunas_tab if c in df_pell.columns]],
                 total_row[[c for c in colunas_tab if c in total_row.columns]]],
                ignore_index=True
            )
            df_tab.columns = [
                "Denominação", "Despesas (R$ Mi)", "Rec. Tesouro (R$ Mi)",
                "Grau Depend. (%)", "Pessoal e Correntes (%)",
                "Invest. e Inversões (%)", "Desp. Pessoal/Func./Mês (R$)",
            ]
            for c in ["Despesas (R$ Mi)", "Rec. Tesouro (R$ Mi)"]:
                df_tab[c] = df_tab[c].map(fmt1)
            for c in ["Grau Depend. (%)", "Pessoal e Correntes (%)",
                      "Invest. e Inversões (%)"]:
                df_tab[c] = df_tab[c].map(
                    lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            df_tab["Desp. Pessoal/Func./Mês (R$)"] = df_tab[
                "Desp. Pessoal/Func./Mês (R$)"].map(
                lambda x: f"R$ {float(x):,.0f}" if pd.notna(x) and x != "—"
                else "—")'''

# ------------------------------------------------------------------------------
# PATCH 2: Bloco C — gráfico Despesa por Funcionário
# (inserir APÓS o bloco de evolução do grau, antes do "else: st.info(ETL)")
# ------------------------------------------------------------------------------
PATCH_2_ANTES = '''    else:
        st.info("⏳ Execute `etl_siga_brasil.py` para popular o Grau de Dependência.")

    st.divider()

    # --- Resultado Líquido (DRE) ---'''

PATCH_2_DEPOIS = '''        st.divider()

        # --- Bloco C: Despesa de Pessoal por Funcionário por Mês ---
        st.markdown("#### Despesa de Pessoal por Funcionário por Mês")
        st.caption(
            "GND Pessoal ÷ (Nº funcionários × 13). "
            "Divisor 13 = 12 meses + 13º salário, para base mensal real. "
            "Fonte: Quantitativo de Pessoal das Estatais (SEST/MGI, dez/ano)."
        )

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            df_func_ano = (
                df_siga[df_siga["exercicio"] == ano_pell]
                .dropna(subset=["desp_pessoal_por_func_mes_rs"])
                .sort_values("desp_pessoal_por_func_mes_rs", ascending=True)
            )
            if not df_func_ano.empty:
                fig_func = px.bar(
                    df_func_ano,
                    x="desp_pessoal_por_func_mes_rs", y="sigla_empresa",
                    orientation="h",
                    title=f"Ranking — {ano_pell} (R$ / func. / mês)",
                    labels={"desp_pessoal_por_func_mes_rs": "R$",
                            "sigla_empresa": ""},
                    color="desp_pessoal_por_func_mes_rs",
                    color_continuous_scale=["#AED6F1", "#1A5276"],
                    template="plotly_white"
                )
                fig_func.update_traces(
                    hovertemplate="%{y}: R$ %{x:,.0f}<extra></extra>")
                fig_func.update_layout(
                    height=max(380, len(df_func_ano) * 30),
                    coloraxis_showscale=False,
                    xaxis_tickprefix="R$ ", xaxis_tickformat=",."
                )
                st.plotly_chart(fig_func, use_container_width=True)
            else:
                st.info("Dados de funcionários não disponíveis para este ano.")

        with col_c2:
            emps_com_func = [
                e for e in sorted(df_siga["sigla_empresa"].unique())
                if df_siga[df_siga["sigla_empresa"] == e]
                   ["desp_pessoal_por_func_mes_rs"].notna().any()
            ]
            if emps_com_func:
                emp_func = st.selectbox(
                    "Empresa — evolução histórica:",
                    emps_com_func, key="func_empresa"
                )
                df_func_emp = (
                    df_siga[df_siga["sigla_empresa"] == emp_func]
                    .dropna(subset=["desp_pessoal_por_func_mes_rs"])
                    .sort_values("exercicio")
                )
                fig_func_ev = px.line(
                    df_func_emp,
                    x="exercicio", y="desp_pessoal_por_func_mes_rs",
                    markers=True,
                    title=f"{emp_func} — Desp. Pessoal / Func. / Mês (R$)",
                    labels={"desp_pessoal_por_func_mes_rs": "R$",
                            "exercicio": "Ano"},
                    template="plotly_white"
                )
                fig_func_ev.update_traces(
                    line_color=CORES["azul_ifi"],
                    hovertemplate="%{x}: R$ %{y:,.0f}<extra></extra>"
                )
                fig_func_ev.update_layout(
                    height=380,
                    yaxis_tickprefix="R$ ", yaxis_tickformat=",."
                )
                st.plotly_chart(fig_func_ev, use_container_width=True)

    else:
        st.info("⏳ Execute `etl_siga_brasil.py` para popular o Grau de Dependência.")

    st.divider()

    # --- Resultado Líquido (DRE) ---'''

# ------------------------------------------------------------------------------
# Aplicação automática (opcional)
# ------------------------------------------------------------------------------
if "--apply" in sys.argv:
    with open(ARQUIVO, "r", encoding="utf-8") as f:
        codigo = f.read()

    if PATCH_1_ANTES in codigo:
        codigo = codigo.replace(PATCH_1_ANTES, PATCH_1_DEPOIS)
        print("✅ Patch 1 aplicado (coluna Desp. Pessoal/Func./Mês na tabela)")
    else:
        print("⚠️  Patch 1: trecho não encontrado — verificar manualmente")

    if PATCH_2_ANTES in codigo:
        codigo = codigo.replace(PATCH_2_ANTES, PATCH_2_DEPOIS)
        print("✅ Patch 2 aplicado (Bloco C — gráfico por funcionário)")
    else:
        print("⚠️  Patch 2: trecho não encontrado — verificar manualmente")

    with open(ARQUIVO, "w", encoding="utf-8") as f:
        f.write(codigo)
    print("\nArquivo atualizado com sucesso.")
else:
    print("Para aplicar os patches automaticamente, rode:")
    print(f"  python patch_aba_dre_pellegrini.py --apply")
    print("\nOu aplique manualmente — veja os comentários no início do arquivo.")
