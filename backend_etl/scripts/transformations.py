import pandas as pd
from datetime import datetime
import unidecode
import numpy as np

# ==============================================================================
# 1. PADRONIZAÇÃO DE NOMES (Colunas)
# ==============================================================================
def normalizar_colunas(df):
    """
    Padroniza nomes de colunas para snake_case (minúsculo, sem acento, com _).
    Ex: 'Valor (R$)' -> 'valor_r'
    Ex: 'Código IBGE' -> 'codigo_ibge'
    """
    novas_colunas = []
    for col in df.columns:
        # Força conversão para string, remove acentos e espaços nas pontas
        s = str(col).strip()
        s = unidecode.unidecode(s)
        s = s.lower()
        
        # Substituições comuns de sujeira
        s = s.replace(' ', '').replace('-', '').replace('.', '').replace('/', '_')
        s = s.replace('(', '').replace(')', '').replace('%', 'pct')
        
        novas_colunas.append(s)
    
    df.columns = novas_colunas
    return df

# ==============================================================================
# 2. TRATAMENTO DE DATAS
# ==============================================================================
def tratar_data(df, nome_coluna, formato_origem='%Y%m'):
    """
    Tenta converter uma coluna para datetime.
    Aceita formatos como '202301' (padrão) ou ajusta autom.
    """
    if nome_coluna in df.columns:
        # Remove sujeira não numérica (caso venha 2023-01 ou 2023/01)
        # O regex \D remove tudo que não é dígito
        serie_limpa = df[nome_coluna].astype(str).str.replace(r'\D', '', regex=True)
        
        df[nome_coluna] = pd.to_datetime(serie_limpa, format=formato_origem, errors='coerce')
    else:
        print(f"⚠️ Aviso: Coluna de data '{nome_coluna}' não encontrada para tratamento.")
    
    return df

# ==============================================================================
# 3. TRATAMENTO NUMÉRICO (Brasil -> Python)
# ==============================================================================
def limpar_float(valor):
    """
    Função auxiliar para aplicar em cada célula.
    Transforma '1.200,50' em 1200.50
    """
    if pd.isna(valor) or str(valor).strip() == '':
        return np.nan
    
    v = str(valor)
    # Remove ponto de milhar
    v = v.replace('.', '')
    # Troca vírgula decimal por ponto
    v = v.replace(',', '.')
    
    try:
        return float(v)
    except:
        return np.nan

def tratar_numeros(df, lista_colunas):
    """
    Aplica a limpeza numérica em uma lista de colunas.
    """
    for col in lista_colunas:
        if col in df.columns:
            # Se a coluna já for numérica (float/int), não faz nada
            if not pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].apply(limpar_float)
            else:
                # Apenas garante float para consistência
                df[col] = df[col].astype(float)
    return df

# ==============================================================================
# 4. METADADOS E FINALIZAÇÃO
# ==============================================================================
def adicionar_metadados(df, fonte_dado, frequencia='mensal'):
    """
    Adiciona colunas de controle para o BigQuery.
    """
    df['data_carga'] = datetime.now()
    df['fonte'] = fonte_dado
    df['frequencia'] = frequencia
    return df
