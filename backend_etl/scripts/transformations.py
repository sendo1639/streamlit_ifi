import pandas as pd
from datetime import datetime
import unidecode
import numpy as np
import re

def normalizar_colunas(df):
    """
    Padroniza nomes de colunas para snake_case.
    """
    novas_colunas = []
    for col in df.columns:
        s = str(col).strip()
        s = unidecode.unidecode(s)
        s = s.lower()
        
        # Substitui espaços e hífens por sublinhado
        s = s.replace(' ', '_').replace('-', '_').replace('.', '').replace('/', '_')
        s = s.replace('(', '').replace(')', '').replace('%', 'pct')
        
        # Remove múltiplos sublinhados seguidos (ex: __ vira _)
        s = re.sub(r'_+', '_', s)
        
        novas_colunas.append(s)
    
    df.columns = novas_colunas
    return df

def tratar_data(df, nome_coluna, formato_origem='%Y%m'):
    """
    Converte coluna para datetime tratando sujeiras.
    """
    if nome_coluna in df.columns:
        # Garante que tratamos apenas strings para o regex
        serie_limpa = df[nome_coluna].astype(str).str.replace(r'\D', '', regex=True)
        df[nome_coluna] = pd.to_datetime(serie_limpa, format=formato_origem, errors='coerce')
    else:
        print(f"⚠️ Aviso: Coluna '{nome_coluna}' não encontrada.")
    return df

def limpar_float(valor):
    """
    Transforma formato brasileiro '1.200,50' em float 1200.50.
    """
    if pd.isna(valor) or str(valor).strip() == '':
        return np.nan
    
    v = str(valor).strip()
    # Se já tiver ponto e vírgula, assume padrão BR
    if '.' in v and ',' in v:
        v = v.replace('.', '').replace(',', '.')
    # Se tiver apenas vírgula, troca por ponto
    elif ',' in v:
        v = v.replace(',', '.')
        
    try:
        return float(v)
    except:
        return np.nan