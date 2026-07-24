"""
Teste do código SGS 1178 — Selic anualizada (base 252)
=========================================================
Complemento ao explorar_bcb_sgs.py. Compara o código 1178 (Selic
diária já anualizada) contra o código 432 (meta Copom) para os
mesmos dias — se estiverem certos, os dois devem ficar muito
próximos, já que a Selic efetiva persegue a meta.

Como usar (Spyder, console IPython):
    %run "CAMINHO\\testar_selic_anualizada.py"
"""

import pandas as pd
from bcb import sgs

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 140)

print("=" * 74)
print("TESTE — Selic anualizada (1178) vs. Meta Copom (432)")
print("=" * 74)

try:
    df = sgs.get({
        "Selic anualizada (1178)": 1178,
        "Selic meta Copom (432)":  432,
    }, start='2026-01-01')

    print(f"\n✅ Período disponível: {df.index.min().date()} a {df.index.max().date()}")
    print(f"   Nº de observações: {len(df)}")
    print(f"\n   Últimas 10 observações lado a lado:")
    print(df.tail(10).to_string())

    # Diferença entre as duas séries — deveria ser próxima de zero
    df['diferenca_pp'] = df["Selic anualizada (1178)"] - df["Selic meta Copom (432)"]
    print(f"\n   Diferença (anualizada - meta), últimos 10 dias:")
    print(df[['diferenca_pp']].tail(10).to_string())
    print(f"\n   Diferença média (todo o período): {df['diferenca_pp'].mean():.4f} p.p.")
    print(f"   Diferença máxima absoluta: {df['diferenca_pp'].abs().max():.4f} p.p.")

except Exception as e:
    print(f"\n❌ ERRO ao buscar código 1178: {e}")

print("\n" + "=" * 74)
print("👉 Se a diferença ficar próxima de zero (poucos centésimos de p.p.),")
print("   o código 1178 está correto e substituímos o 11 como fonte da")
print("   Selic anualizada na página.")
print("=" * 74)