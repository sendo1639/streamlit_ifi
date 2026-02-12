import sys
import os
import pandas as pd
import urllib.parse
import time
import warnings
from pathlib import Path

# --- CONFIGURAÇÃO DE IMPORTAÇÃO ---
try:
    # Correção: __file__ (dois underscores)
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path(os.getcwd()) / 'backend_etl' / 'scripts'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    import utils
    import transformations as tr
except ImportError as e:
    # Agora a mensagem dirá EXATAMENTE qual biblioteca falta (ex: unidecode)
    print(f"❌ Erro de Importação: {e}")
    print(f"Verifique se todas as bibliotecas (pip install) estão no arquivo .yml")
    sys.exit(1)

warnings.filterwarnings("ignore")

DATASET_ID = 'dados_sociais'
TABELA_ID = 'base_consolidada_pbf_cadun'

def garantir_continuidade_temporal(df):
    if df.empty: return df
    df['data'] = pd.to_datetime(df['data'])
    dfs_preenchidos = []
    
    for variavel, grupo in df.groupby('nome_variavel'):
        if grupo.empty: continue
        try:
            idx_completo = pd.date_range(start=grupo['data'].min(), end=grupo['data'].max(), freq='MS')
            grupo_cheio = grupo.set_index('data').reindex(idx_completo).reset_index()
            grupo_cheio['nome_variavel'] = variavel
            grupo_cheio['nome_indicador'] = grupo['nome_indicador'].iloc[0]
            grupo_cheio = grupo_cheio.rename(columns={'index': 'data'})
            dfs_preenchidos.append(grupo_cheio)
        except:
            dfs_preenchidos.append(grupo)
    
    if not dfs_preenchidos: return df
    return pd.concat(dfs_preenchidos, ignore_index=True)

def processar_consulta_brasil(config):
    if not config['ativo']: return pd.DataFrame()

    nome_grupo = config['nome']
    params = config['params']
    
    if params.get('q') in ['*:*', '', None]: params['q'] = '*:*'
    
    shift_padrao = config.get('shift_padrao', 0)
    ajustes_por_variavel = config.get('ajuste_especifico', {}) 
    
    url_base = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial/"
    query_string = urllib.parse.urlencode(params) 
    url_final = f"{url_base}?{query_string}"
    
    print(f"🔄 Baixando: {nome_grupo}...", end=" ")
    
    try:
        df = pd.read_csv(url_final)
        if df.empty:
            print("⚠️ (Vazio)")
            return pd.DataFrame()

        col_data = next((c for c in df.columns if c in ['anomes_s', 'anomes', 'mes_ano', 'referencia']), None)
        if not col_data: return pd.DataFrame()
        
        df = df.rename(columns={col_data: 'data'})
        try:
            df['data'] = pd.to_datetime(df['data'].astype(str), format='%Y%m', errors='coerce')
        except: pass

        colunas_numericas = df.select_dtypes(include=['number']).columns.tolist()
        cols_para_somar = [c for c in colunas_numericas if 'ibge' not in c and 'anomes' not in c]
        if not cols_para_somar: return pd.DataFrame()

        df_agrupado = df.groupby(['data'])[cols_para_somar].sum().reset_index()

        df_long = df_agrupado.melt(id_vars=['data'], value_vars=cols_para_somar, var_name='nome_variavel', value_name='valor')
        
        df_long['nome_indicador'] = nome_grupo
        df_long = df_long[df_long['valor'] > 0]

        if shift_padrao != 0:
            df_long['data'] = df_long['data'] + pd.DateOffset(months=shift_padrao)

        for variavel, meses_extra in ajustes_por_variavel.items():
            mask = df_long['nome_variavel'] == variavel
            if shift_padrao != 0:
                df_long.loc[mask, 'data'] = df_long.loc[mask, 'data'] - pd.DateOffset(months=shift_padrao)
            if meses_extra != 0:
                df_long.loc[mask, 'data'] = df_long.loc[mask, 'data'] + pd.DateOffset(months=meses_extra)
        
       
        df_long['origem_dado'] = 'MDS (Bolsa Família/CadÚnico)'
     
      
        df_long = garantir_continuidade_temporal(df_long)
        print(f"✅ Sucesso! ({len(df_long)} linhas)")
        return df_long
        
        print(f"✅ Sucesso! ({len(df_long)} linhas)")
        return df_long

    except Exception as e:
        print(f"❌ Erro: {e}")
        return pd.DataFrame()

CONFIG_CONSULTAS = [
    # --- GRUPO: CADASTRO ÚNICO ---
    {
        "nome": "CadUnico - Famílias (Renda)", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc, codigo_ibge asc', 'fq': 'anomes:*',
                   'fl': 'anomes,cadun_qtd_familias_cadastradas_rfpc_acima_meio_sm_i,cadun_qtd_familias_cadastradas_rfpc_ate_meio_sm_i,cadun_qtd_familias_cadastradas_pobreza_pbf_i'}
    },
    {
        "nome": "CadUnico - Famílias Unipessoais", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc, codigo_ibge asc', 'fq': 'anomes:*',
                   'fl': 'anomes,cadunico_qtd_fam_1_integrante_i'}
    },
    {
        "nome": "CadUnico - Pessoas (Renda)", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc, codigo_ibge asc', 'fq': 'anomes:*',
                   'fl': 'anomes,cadun_qtd_pessoas_cadastradas_rfpc_acima_meio_sm_i,cadun_qtd_pessoas_cadastradas_pobreza_pbf_i,cadun_qtd_pessoas_cadastradas_rfpc_ate_meio_sm_i'}
    },
    {
        "nome": "CadUnico - Pessoas por Faixa Etaria e sexo", "ativo": True,
        "shift_padrao": 1, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc', 'fq': 'anomes:*',
                   'fl': 'anomes,qtd_pes_cad_nao_pbf_idade_0_e_4_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_0_e_4_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_5_a_6_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_5_a_6_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_7_a_15_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_7_a_15_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_16_a_17_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_16_a_17_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_18_a_24_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_18_a_24_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_25_a_34_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_25_a_34_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_35_a_39_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_35_a_39_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_40_a_44_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_40_a_44_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_45_a_49_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_45_a_49_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_50_a_54_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_50_a_54_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_55_a_59_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_55_a_59_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_60_a_64_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_60_a_64_sexo_masculino_i,qtd_pes_cad_nao_pbf_idade_maior_que_65_sexo_feminino_i,qtd_pes_cad_nao_pbf_idade_maior_que_65_sexo_masculino_i'}
    },
    {
        "nome": "CadUnico - Pessoas com Deficiencia",
        "ativo": False, 
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {
            'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc, codigo_ibge asc',
            'fq': 'anomes:*',
            'fl': 'anomes'
        }
    },

    # --- GRUPO: BOLSA FAMÍLIA ---
    {
        "nome": "Bolsa Família (Geral)", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes_s desc, codigo_ibge asc', 'fq': 'anomes_s:*',
                   'fl': 'anomes,qtd_familias_beneficiarias_bolsa_familia_s,valor_repassado_bolsa_familia_s,qtd_bloqueios_pbf_i,qtd_suspensao_pbf_i'}
    },
    {
        "nome": "Bolsa Família - Famílias Pré-Habilitadas", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes_s desc, codigo_ibge asc', 'fq': 'anomes_s:*',
                   'fl': 'anomes,pbf_familias_habilitadas_saldo_apos_concessao_i,pbf_familias_habilitadas_total_familias_i,pbf_familias_habilitadas_total_novas_concessoes_i'}
    },
    {
        "nome": "Bolsa Família - Pessoas beneficiárias", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes_s desc, codigo_ibge asc', 'fq': 'anomes_s:*',
                   'fl': 'anomes,qtd_pessoas_beneficiarias_bolsa_familia_i'}
    },
    {
        # RECUPERADO: Este é o item que faltava!
        "nome": "Bolsa Família- Pessoas por Faixa Etaria e sexo", "ativo": True,
        "shift_padrao": 1, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes desc', 'fq': 'anomes:*',
                   'fl': 'anomes,qtd_pes_pbf_idade_0_e_4_sexo_feminino_i,qtd_pes_pbf_idade_0_e_4_sexo_masculino_i,qtd_pes_pbf_idade_5_a_6_sexo_feminino_i,qtd_pes_pbf_idade_5_a_6_sexo_masculino_i,qtd_pes_pbf_idade_7_a_15_sexo_feminino_i,qtd_pes_pbf_idade_7_a_15_sexo_masculino_i,qtd_pes_pbf_idade_16_a_17_sexo_feminino_i,qtd_pes_pbf_idade_16_a_17_sexo_masculino_i,qtd_pes_pbf_idade_18_a_24_sexo_feminino_i,qtd_pes_pbf_idade_18_a_24_sexo_masculino_i,qtd_pes_pbf_idade_25_a_34_sexo_feminino_i,qtd_pes_pbf_idade_25_a_34_sexo_masculino_i,qtd_pes_pbf_idade_35_a_39_sexo_feminino_i,qtd_pes_pbf_idade_35_a_39_sexo_masculino_i,qtd_pes_pbf_idade_40_a_44_sexo_feminino_i,qtd_pes_pbf_idade_40_a_44_sexo_masculino_i,qtd_pes_pbf_idade_45_a_49_sexo_feminino_i,qtd_pes_pbf_idade_45_a_49_sexo_masculino_i,qtd_pes_pbf_idade_50_a_54_sexo_feminino_i,qtd_pes_pbf_idade_50_a_54_sexo_masculino_i,qtd_pes_pbf_idade_55_a_59_sexo_feminino_i,qtd_pes_pbf_idade_55_a_59_sexo_masculino_i,qtd_pes_pbf_idade_60_a_64_sexo_feminino_i,qtd_pes_pbf_idade_60_a_64_sexo_masculino_i,qtd_pes_pbf_idade_maior_que_65_sexo_feminino_i,qtd_pes_pbf_idade_maior_que_65_sexo_masculino_i'}
    },
    {
        # SEPARADO: Unipessoais do Bolsa Família
        "nome": "Bolsa Família - Percentual Famílias Unipessoais", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {"cadunico_qtd_fam_1_integrante_benef_pabpbf_i": 1},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes_s desc, codigo_ibge asc', 'fq': 'anomes_s:*',
                   'fl': 'anomes,cadunico_qtd_fam_1_integrante_benef_pabpbf_i,qtd_familias_beneficiarias_bolsa_familia_s'}
    },
    {
        # SEPARADO: Condicionalidades
        "nome": "Bolsa Família - Condicionalidades", "ativo": True,
        "shift_padrao": 0, "ajuste_especifico": {},
        "params": {'q': '*:*', 'wt': 'csv', 'rows': '10000000', 'sort': 'anomes_s desc, codigo_ibge asc', 'fq': 'anomes_s:*',
                   'fl': 'anomes,qtd_bloqueios_pbf_i,qtd_cancelamentos_pbf_i,qtd_suspensao_pbf_i,qtd_liberacoes_pbf_i,qtd_novas_concessoes_pbf_i'}
    }
]

if __name__ == "__main__":
    print("🚀 Iniciando Extração Mensal (MDS - CadÚnico e Bolsa Família)...")
    
    lista_dfs = []
    
    for consulta in CONFIG_CONSULTAS:
        df_temp = processar_consulta_brasil(consulta)
        if not df_temp.empty:
            lista_dfs.append(df_temp)
        time.sleep(1)

    if lista_dfs:
        df_final = pd.concat(lista_dfs, ignore_index=True)
        # Consolida para não ter gaps
        df_final = garantir_continuidade_temporal(df_final)

        print(f"\n📤 Atualizando {len(df_final)} linhas recentes no BigQuery...")
        # Como o script mensal baixa TUDO do PBF, 'replace' é mais seguro para não duplicar, 
        # Use 'replace' aqui para limpar a base e garantir consistência, e rode o histórico PAB em seguida.
        
        utils.subir_para_bigquery(df=df_final, dataset=DATASET_ID, tabela=TABELA_ID, if_exists='replace')
        print("✨ Tabela PBF/CadÚnico atualizada com sucesso!")
    else:
        print("\n⚠️ Nada extraído.")