import os
import re

# Define o caminho da pasta mãe onde a busca começará
pasta_raiz = r"D:\Users\02943903167\Desktop\Sinconfi"

def renomear_arquivos_recursivamente(diretorio_base):
    print(f"Iniciando a busca e renomeação em: {diretorio_base}")

    # Percorre todos os diretórios e arquivos recursivamente (os.walk)
    for root, dirs, files in os.walk(diretorio_base):
        for nome_arquivo_original in files:
            # Filtra apenas arquivos zip que correspondem ao padrão 'finbraRREO'
            if nome_arquivo_original.endswith('.zip') and 'finbraRREO' in nome_arquivo_original:
                
                caminho_completo_antigo = os.path.join(root, nome_arquivo_original)
                
                # --- Lógica para extrair Ano e Bimestre do caminho (root) ---
                
                # Usamos Expressões Regulares (Regex) para encontrar o ano (e.g., '2022')
                # e o bimestre (e.g., '1°_bimestre') no caminho do diretório (root).
                
                match_ano = re.search(r'\\(\d{4})\\', root)
                match_bimestre = re.search(r'\\(\d{1,2})°_bimestre\\', root)

                if match_ano and match_bimestre:
                    ano = match_ano.group(1)
                    # Formata o bimestre para B1, B2, ..., B6
                    numero_bimestre = match_bimestre.group(1)
                    bimestre = f"B{numero_bimestre}"

                    # --- Lógica para criar o novo nome ---

                    # O novo formato desejado é: 2023_B6_finbraRREO_...
                    
                    # Remove a parte inicial padrão do nome do arquivo original 
                    # (que é sempre 'finbraRREO_...')
                    parte_remanescente_nome = re.sub(r'^finbraRREO_', '', nome_arquivo_original)

                    # Constrói o novo nome completo do arquivo
                    novo_nome_arquivo = f"{ano}_{bimestre}_finbraRREO_{parte_remanescente_nome}"
                    
                    caminho_completo_novo = os.path.join(root, novo_nome_arquivo)

                    # --- Executa a renomeação ---
                    try:
                        os.rename(caminho_completo_antigo, caminho_completo_novo)
                        print(f"Renomeado: \n  DE: {nome_arquivo_original}\n  PARA: {novo_nome_arquivo}\n")
                    except Exception as e:
                        print(f"Erro ao renomear {nome_arquivo_original}: {e}")
                else:
                    print(f"Aviso: Não foi possível extrair ano/bimestre do caminho: {root}")

# Executa a função principal
renomear_arquivos_recursivamente(pasta_raiz)
print("Processo de renomeação concluído.")