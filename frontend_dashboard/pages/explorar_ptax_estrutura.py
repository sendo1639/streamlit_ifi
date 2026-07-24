"""
Verificação — a API do Focus pagina automaticamente ou trunca em
algum teto quando pedimos sem limite explícito?
=========================================================================
Testa IPCA (Anuais) sem nenhum .limit(), e compara com uma contagem
esperada aproximada, para detectar truncamento silencioso.

Como usar (Spyder, console IPython):
    Salve como testar_paginacao_focus.py e rode:
    %run "CAMINHO\\testar_paginacao_focus.py"
"""

import pandas as pd
from bcb import Expectativas

api = Expectativas()
ep = api.get_endpoint("ExpectativasMercadoAnuais")

print("=" * 74)
print("TESTE — IPCA, sem limit(), série completa")
print("=" * 74)

try:
    df = ep.query().filter(ep.Indicador == "IPCA").collect()
    print(f"\n✅ {len(df)} linha(s) retornadas")

    df['Data'] = pd.to_datetime(df['Data'])
    print(f"Data mais antiga: {df['Data'].min().date()}")
    print(f"Data mais recente: {df['Data'].max().date()}")
    print(f"Anos de referência distintos: {sorted(df['DataReferencia'].unique())}")

    # Sinal de alerta: se o total for um número redondo suspeito
    # (1000, 5000, 10000...) ou se a data mais recente NÃO for de
    # poucos dias atrás, é sinal de truncamento.
    if len(df) in (1000, 5000, 10000):
        print(f"\n⚠️  ATENÇÃO: total de linhas é um número redondo suspeito —")
        print(f"    pode indicar teto de paginação no servidor.")

    dias_desde_ultima = (pd.Timestamp.today() - df['Data'].max()).days
    if dias_desde_ultima > 15:
        print(f"\n⚠️  ATENÇÃO: a data mais recente está a {dias_desde_ultima} dias")
        print(f"    atrás — isso é suspeito, o Focus é semanal. Pode indicar")
        print(f"    que a paginação não trouxe os dados mais novos.")
    else:
        print(f"\n✅ Data mais recente está a {dias_desde_ultima} dia(s) — parece OK.")

except Exception as e:
    print(f"❌ ERRO: {e}")

print("\n" + "=" * 74)