import sys
import os
import pandas as pd
import requests
import time
import warnings
from io import StringIO
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# --- CONFIGURAÇÃO DE IMPORTAÇÃO ---
try:
    BASE_DIR = Path(_file_).resolve().parent.parent
except NameError:
    import os
    BASE_DIR = Path(os.getcwd()).parent if 'social' in os.getcwd() else Path(os.getcwd()) / 'backend_etl' / 'scripts'

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    import utils
    import transformations as tr
except ImportError:
    print(f"❌ Erro: Não encontrei 'utils.py' na pasta: {BASE_DIR}")
    sys.exit()

warnings.filterwarnings("ignore")

DATASET_ID = 'dados_sociais'
TABELA_ID = 'base_consolidada_pbf_cadun' # Mesma tabela, vamos adicionar dados nela

def processar_pab_legacy(config):
    if not config['ativo']: return pd.DataFrame()
    
    nome_indicador = config['nome']
    url_csv = config['url_full']
    
    print(f" Baixando Histórico: {nome_indicador}...", end=" ")
    
    try:
        if len(url_csv) > 2048:
            parsed_url = urlparse(url_csv)
            url_base = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
            params = parse_qs(parsed_url.query)
            response = requests.post(url_base, data=params, timeout=120)
        else:
            response = requests.get(url_csv, timeout=120)
        
        response.raise_for_status()
        csv_content = response.content.decode('iso-8859-1', errors='ignore')
        
        df = None
        for sep in [',', ';', '\t']:
            try:
                df = pd.read_csv(StringIO(csv_content), sep=sep, encoding='iso-8859-1', decimal=',')
                if df.shape[1] >= 2: break 
            except: continue
            
        if df is None or df.empty:
            print("⚠️ Vazio")
            return pd.DataFrame()

        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        coluna_data = df.columns[0] 

        df = df.rename(columns={coluna_data: 'data'})
        df['data'] = df['data'].astype(str).str.strip()
        df['data'] = pd.to_datetime(df['data'], format='%m/%Y', errors='coerce') \
                     .fillna(pd.to_datetime(df['data'], format='%Y%m', errors='coerce'))

        df = df.dropna(subset=['data']) 

        cols_valores = [c for c in df.columns if c != 'data']
        for c in cols_valores:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce')

        df_long = df.melt(id_vars=['data'], value_vars=cols_valores, var_name='nome_variavel', value_name='valor')
        
        df_long['nome_variavel'] = df_long['nome_variavel'].apply(lambda x: f"{nome_indicador} - {x}")
        df_long['nome_indicador'] = nome_indicador
        
        
        df_long['origem_dado'] = '(Auxílio Brasil/Emergencial)' 
        # ----------------------------

        df_long = df_long[df_long['valor'] > 0]
        
        print(f"✅ Sucesso! ({len(df_long)} linhas)")
        return df_long
        
        print(f"✅ Sucesso! ({len(df_long)} linhas)")
        
        
        return df_long

    except Exception as e:
        print(f"❌ Erro Legacy: {e}")
        return pd.DataFrame()

CONFIG_HISTORICO = [
    # --- AUXÍLIO BRASIL (PAB) ---
    {
        "nome": "Auxílio Brasil - Geral", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOhlMHqwJOsuqSe9Wp%2BhrNe09Gv17llja1%2BYW15YmqqdH9%2BaWCEkWWXbWTZ8X5kc3xwoNqlwLNyocnWmKV4mb7nwJl3g6iv5lzDf2lfiJyZy6mmwrazlai7mnW0n666qpKSnKbfqlbTrH1rcYOprO6eiMKporycbtCen9DgiG%2BvvaJd9Fqwr6qSd9ibz6tTnfF%2BZm55c2qZrbWzpU3J0KjYoVuFu8NlbH9qdLOnwrucn8DEXJl9qY6tf2Voel5a3qXAs1ebzM2fiqKhwZzKb6Kpoa3edLOvo6C8nG7Qnp%2FQ4Ihvr72itr%2BauhHkmcDCpo2DlMo%2B%2BqClqahayXqPbpyad9GU0Z6gwunBo1%2Belqboq22ipqG4zVO8oqO%2B7sCVoLdVnuhZjsOv8ATNnNlddc%2FcwJ2oa4ub5ai%2FbomSx8Km3Z6XzJu69%2BWsnqmZq7KxnI%2FAxaKKrZjJ3MBUoqmi%2FSaltq%2BqTbvQU6uyqyAouZ2raHes2qy2urOdkt2v5m9jj6x6ZW11ZWvNaX2IZ12RkWPEeA%3D%3D&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=v1074&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=2&columns[2][name]=v1075&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&columns[3][data]=3&columns[3][name]=(case%20when%20t.v1221%3E0%20then%20round((t.v1075%3A%3Anumeric)%2Ft.v1221%2C2)%20e&columns[3][searchable]=true&columns[3][orderable]=true&columns[3][search][value]=&columns[3][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    },
    {
        "nome": "Auxílio Brasil - Beneficiários", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOhlMHqwJOsuqSe9WqCgrNe09Gv17llja1%2BYW15YmqqdH9%2BaWCEkWWXbWTZ8X5mbnpwoNqlwLNyk7jNps94bsPcuaehg3Ct7qbJnpygytCU3V2VwumymqWrnv0aq7avqqnHnK%2FmuW4%3D&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=v1222&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    },
    {
        
        "nome": "Auxílio Brasil - Benefícios por Tipo", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOhlMHqwJOsuqSe9Wp%2Bh7Ne09Gv17llja1%2BYW15YmqqdH9%2BaWCEkWiXbWTZ8X5kc35woNqlwLNyocnWmKV4mb7nwJl3g6iv5lzDf2dkjpyZy6mmwrbBprGtcHXfmrnBnGiS1KjXYKmOq4Rsd66WpuyeiMKporycbtCen9DgiG%2BvvaJd72p9hXBovcKf3aJu0e3CmXeDm5vlrLKJcqDMzlbgbmOVq4ianbSon7Stv8OcaJLHlNawmJi2wKmpa6trq2x%2FiZ2Ow9SYpaOUye6yb3eulqbsnoiJqqLEhKmbbWuOtrOVqLuade2rwrNyaL3Cn92ibpjuwqFfvmZqsWuItJiZysZu3q%2BowraImp20qJ%2B0dMDDpFDNkmaedm7D3LmnoYObm%2BWssolyk7jNps94btDwuleyeWhwqXSzr6OgvJyZy6mmwraImp20qJ%2B0dMDDpKmr0KfLqVPB4G12obaaoDzmsLemoHexpdOqmMbtrlSFtpv9G6ewt5hNf6ODs2ZWserBlahomZ%2BZe7K8nJMaDpbTrKZ9vryhrLeoozzgEPGmTZ3CoNOpnL7tbWFci6ej2qcQ9ZhNf6N2rWZWserBlahomZ%2BZe7K8nJMaDpbTrKZ9vryhrLeoozzgEPGmTZ3CoNOpnL7tbWFciZmp5Z7AsZyby8ZTkn92nqRwiKu8lqaZnbJueZLFxpkt6pbG6sBUf7eiquisthHe8PrQU7CeoMbntpWuaGJaw6jDs6RNf6N2tGZWserBlahomZ%2BZe7K8nJMaDpbTrKZ9vryhrLeoozzgEPGmTZ3CoNOpnL7tbWFcj5qt7Zq7wpxNf6N2sWZWserBlahomZ%2BZe7K8nJMaDpbTrKZ9vryhrLeoozzgEPGmTZ3CoNOpnL7tbWFclqqu66LHbl9vmq9cjZGi0dy5VKCtVXzep7K0%2Btq6yqLdXaO%2B7a5Uj72ln%2BuaEPX60MaBl8tdeNXvv5mpqVWK6Ju%2Fs7GOd4l1vY1cgM%2B8qJ20VZ7eWY%2BzpZK9JODNpqLQm5CjqbiaqOyawRHqn8DQpoqRpb7pwJ2wC%2Bis4qjAbl9vmrCAumZWserBlahomZ%2BZe7K8nJMaDpbTrKZ9wMWorqmkrN2iuxHYn8DQpopleLXPdleQt6mb5Vmxs1dvvM%2BY0ADgwOS8p1yJmaPcory8mJbKgXbZqqPJ4LqZqryWrN6syb5yqdPdbg%3D%3D&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=v1076&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=2&columns[2][name]=v1077&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&columns[3][data]=3&columns[3][name]=v1078&columns[3][searchable]=true&columns[3][orderable]=true&columns[3][search][value]=&columns[3][search][regex]=false&columns[4][data]=4&columns[4][name]=v1079&columns[4][searchable]=true&columns[4][orderable]=true&columns[4][search][value]=&columns[4][search][regex]=false&columns[5][data]=5&columns[5][name]=v1080&columns[5][searchable]=true&columns[5][orderable]=true&columns[5][search][value]=&columns[5][search][regex]=false&columns[6][data]=6&columns[6][name]=v1232&columns[6][searchable]=true&columns[6][orderable]=true&columns[6][search][value]=&columns[6][search][regex]=false&columns[7][data]=7&columns[7][name]=v1081&columns[7][searchable]=true&columns[7][orderable]=true&columns[7][search][value]=&columns[7][search][regex]=false&columns[8][data]=8&columns[8][name]=v1082&columns[8][searchable]=true&columns[8][orderable]=true&columns[8][search][value]=&columns[8][search][regex]=false&columns[9][data]=9&columns[9][name]=v1349&columns[9][searchable]=true&columns[9][orderable]=true&columns[9][search][value]=&columns[9][search][regex]=false&columns[10][data]=10&columns[10][name]=v1360&columns[10][searchable]=true&columns[10][orderable]=true&columns[10][search][value]=&columns[10][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    },
    {
        "nome": "Auxílio Brasil - Habilitadas", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOtlcPavaarrLFsrWzJf7Od086vnG1ljqh%2BZml4ZnWraX%2BBZF2JjmObuamOrIVkd66WpuyeiLSYmcrGbqWjlMnusm93u6qnnK9%2BgGlhkseU1rCYmOGuoK%2BtcHXfmrnBnGiS1KjXYK5%2B3q6noWisot6nbY6tXoiZY4qGhn3JnIhcloqGxVmuvJtNl9dknG9nfcSgVIqXiVrHjpmaV6G%2FxqGKoKK%2B57Knn61deu9qfoZnWYeKYM2slMngwJehcHWwqmt%2FgmNdgIGY1rCYfenCoKhomqjdWsqJnY7D1Jilo5TJ7rJvd66WpuyeiImqosTdh9mxlMmbsZlcrpanPOa5t5igd8mUzKafxu%2BumJ27VZvoWZ3AppTJwqDLXXTS8xDhqLGkWrurrsGgmXqkotigmNDuEOmhu1We6FmdwKaUycKgy1100vMQ4aixpFq7q67BoJl6tJTWoaJ937JUoqmi%2FSaltq%2BqTb%2FCldOpnNHcsZWvaJapmYm%2FvZ6fuM6Uin6o1T76oKW3VXzrmsC3o03HJObdapbM6bCZr7v43ei1vYmzqdOc&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=v1180&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=2&columns[2][name]=v1224&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&columns[3][data]=3&columns[3][name]=(case%20when%20t.v1180%20IS%20NOT%20NULL%20and%20t.v1224%20IS%20NOT%20NULL%20then%20coa&columns[3][searchable]=true&columns[3][orderable]=true&columns[3][search][value]=&columns[3][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    },

    # --- AUXÍLIO EMERGENCIAL (AE) 
    {
        "nome": "Auxílio Emergencial - Elegíveis", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOtlcPavaarrLFrsWvJf7Od086vnG1ljah9aGl4ZnWraX%2BAZF2PjmObua5%2Bo7CjnbSardyedY6tYIyNY5NolszcuZmvq5piua%2BCgWNdgIyW2Z6fwu6wmWSIq26tcHl%2BYFi60JTWoqbA4HV0sntrbqVpdndYqpLHlNawmJjvv6mhg3Cg2qXAs3JoytagjbhUwOquoKG7mJ%2BhecN%2Fb1%2BDkVyVoKK%2B57Knn61deu9shYdjXYCMltmen8LusJlkiKtzr2V9d2KQxsKfz7CWwqONqm9%2BamapYnixpo7DxqbNolud8YBrbXRlY6ScvK%2BjksrEmJJ9qZCyhGBscWCd6Jq5s6qQvIlz4HBrkKd9XWerpJvlnsCxnFWX12aac1%2BNpHiXq6mhn%2BycsnZ3o4yVX5pmXsDqrqChu5ifoXnDf2hhg5FclaCivueyp5%2BtXXrvan2AY12AjJbZnp%2FC7rCZZIira6tveX5gWLrQlNaipsDgdXSyeWpupWl2eZqcuM2Y3aCYhbvDZnN4YWqiZLC9mJm81JbPZXPTrYVmaHheZdyorrqcoLrGW6qzZZaveWRlc5ip2qWywZqSf6GpnW5liat2X5%2B3lqberLCzX23NlGmWbVyI3ryVqK2ond5hjcRoYY%2BNY5NolszcuZmvq5piua9%2Bfm9Zh4pezayUyeDAl6FwdbCqa316Z1aCxKLLqZjQ3rJcfL5ncatlfXdikMbCn8%2BwlsKjjapugG1mqWJ4saaOw8amzaJbnfGAZGx0ZWOknLyvo5LKxJiSfamOr31gbHFgneiaubOqkLyJc%2BBuapanfV1nq6Sb5Z7AsZxVl9dkoXBfjaR4l6upoZ%2FsnLJ2d6OImGmWbVyI3ryVqK2ond5hjcRqY4eNY5NolszcuZmvq5piua%2BBgW9Zh4pezayUyeDAl6FwdbCtboJ6Z1aCxKLLqZjQ3rJcfL5pb7FlfXdikMbCn8%2BwlsKjjap1eWxmqWJ4saaOw8amzaJbnfGGZm50ZWOknLyvo5LKxJiSfamWs4BgbHFgneiaubOqkLyJc%2BB2a5OnfV1dxXCg2qXAs3KhydaYpXiZvufAmXeDqK%2FmXMOBbGi9wp%2Fdom7R7cKZd4Obm%2BWssolyoMzOVuVelszcuZmvq5piua%2BAf2lZh4pezayUyeDAl6FwdbCsb3l%2BYFi60JTWoqbA4HV0snlpcqVpdnmanLjNmN2gmIW7w21ydGVjpJy8r6OSysSYkn2pjquFYGxxYJ3omrmzqpC8iXPgbmWNp31dZ6ukm%2BWewLGcVZfXZaFvX42keJerqaGf7JyydnejiZlrlm1ciN68laitqJ3eYY3Eal2HjWOTXrCY4a6gr61wruuusolyk7jNps94btDwuleyfWh135q5wZxoy9Ooz3huw9y5p6GDcK3upnDJWJDGwp%2FPsJbCo42qb3hrZqlieLGmjsPGps2iW53xgmhoeF5l3KiuupygusZbqrNkjq95ZGVzmKnapbLBmpJ%2FoambbWWJq3Zfn7eWpt6ssLNfbc2SZaBpY4amsKOdtJqt3J51jq1ejJVfmmZewOquoKG7mJ%2BhecOAbl2DkVyVoKK%2B57Knn61deu9rhYBjXYCMltmen8LusJlkiKtssm15fmBO1JyZy6mmwrbBprGtcHXfmrnBnGiS1KjXYKmQsYFvoqmhrd50wcCskpKcmcuppsK2iKextVi1mpy8r6OSysSYkn2pkLOGYGxxYJ3omrmzqpC8iXPgcGmSp31dZ6ukm%2BWewLGcVZfXZqFuX42keJerqaGf7Jyydnejiphqlm1ciN68laitqJ3eYY3EamWKjWOTXrCY4a6gr61wruuusolyk7jNps94btDwuleyfGlxtJ%2BuuqqSktWl36JumOGuoK%2BtcHXsrrpxsk660JTWoqbA4HV0snlpaqVpdnmanLjNmN2gmIW7w2VzgWFqomSwvZiZvNSWz2Vz06yEZ2h4XmXcqK66nKC6xluqs2SUsXlkZXOYqdqlssGakn%2BhqZt1ZYmrdl%2Bft5am3qyws19tzZRpmmljhqawo520mq3cnnWOrWGKmV%2BaZl7A6q6gobuYn6F5w4JsYoORXJWgor7nsqefrV16722ChmNdgIyW2Z6fwu6wmWSIq3OqcHl%2BYFi60JTWoqbA4HV0soFnbKVpdnmanLjNmN2gmIW7w210e2FqomSwvZiZvNSWz2Vz07SFamh4Xlv2dLOvo6C8nKfcspiYtrOVqLuadbSswruzgcbVlNZdl8KbvZmvu6Sb7FmyupyUGg6pz6amgNGuoKu6Va7ora66V4531JjcXaXC666nr6mZqZmpsrqmTZjWqy3qn8bqbXmpraeh3qewt5iZerGY3bCivu5tmaitnP0mr7K3qk270FPaAO2%2F57aXq2h4m92awMKpnHckzdimlsybdaehtVWc6KXAr2BQrcKf2a9T0erBlahollrsnr9uqZLHwqbdnpfMm72VrqlVqjzzr7qgkMaBdsuhlNDvv6NcC8%2Bo4py8bl%2BgvM5TzKyf0Nx2V4ytqK3omsBunJm8yPYXs5jG7m2Yq2il%2FTObubeanHeio9amlr7vtqqraHib4rGucY2Ow9ClirGi0dy5VJ1oqJ%2FrWb%2Bzp47K1JTOrFPN3L%2BVXLj49NultrGmTZjRn9OglNHkw6Nci5aj8ZpwnpygytCU3V2YyeC09%2Bm%2BmqPsWb29qU3ExpzZXX3S37aXpamhXc%2Baub2pTcvQp8upU76bwJmuaKef6ZrAwZiRxoGjy6%2BUfesQ7p60np3oWZfDm5a6ypTWYIPC7sCjnbtVn%2BWetBHko7zKpoqhon3rEO6etJ6d6FmPvaOguIF5y6r2Cue2lV%2Belqboq23CpqG4zVPLXabC7W2mobiWreyasb1XnbjTlIqt9hfduZ2ft1V86KXAr1dzuM72F6mcvve9b7jEsWypa317Z2GEkWS%2BbWOXq31ubHiPdQ%3D%3D&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=(coalesce(v1372%2C0)%2Bcoalesce(v1380%2C0)%2Bcoalesce(v1388%2C0)%2Bcoalesce&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=2&columns[2][name]=(coalesce(v1373%2C0)%2Bcoalesce(v1381%2C0)%2Bcoalesce(v1389%2C0)%2Bcoalesce&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    },
    {
        "nome": "Auxílio Emergencial - Valor Repassado", "ativo": True,
        "url_full": "https://aplicacoes.cidadania.gov.br/vis/data3/v.php?q[]=oNOtlcPavaarrLFsqnHJf7Od086vnG1jkqh%2BZml4ZnWraX%2BDZF6JjmObua5%2B3ryVqK2ond5hw39qZImNY5NolszcuZmvq5pi72qAhmdZh4pezayUyeDAl6Fwq2uscYV6Z1aCxKLLqZjQ3rJcsnlpbKtlfXdYqpLHlNawmJjhrqCvrXB135q5wZxoktSo12Cuft68laitqJ3eYcN%2FamSKjWOTaJbM3LmZr6uaYu9qgIZoWYeKXs2slMngwJehcKtrrHGGemdWgsSiy6mY0N6yXLJ5aWysZX13WKqS1aXfom7D3LmnoYNwoNqlwLNyaMrWoI24VMDqrqChu5ifoa9%2BgW5hg5FclaCivueyp5%2BtXbCqbIWAY12AjJbZnp%2FC7rCZZL5mbbJpeX5gWLrQlNaipsDgdaptfGdvpWl2b7RovcKf3aJuw9y5p6GDcKDapcCzcmjK1qCNuFTA6q6gobuYn6GvfoFuYoORXJWgor7nsqefrV2wqmyFgWNdgIyW2Z6fwu6wmWS%2BZm2yanl%2BYFi60JTWoqbA4HWqbXxncKVpdm%2B0aMvTqM94mb7nwJl3g5ub5ayyiXKgzM5W5V6WzNy5ma%2BrmmLvaoCFbVmHil7NrJTJ4MCXoXCra6xxgXpnVoLEosupmNDeslyyeWhzq2V9d2KQxsKfz7CWwqPDZXB6bGapYm7LcpO4zabPeJm%2B58CZd4Obm%2BWssolyoMzOVuVelszcuZmvq5pi72qAhW5Zh4pezayUyeDAl6Fwq2uscYJ6Z1aCxKLLqZjQ3rJcsnloc6xlfXdikMbCn8%2BwlsKjw2Vwem1mqWJuy3KhydaYpaOUye6yb3eulqbsnoiJqqLEhK6LoKK%2B57Knn61dsKpshIZjXYCMltmen8LusJlkvmZtsW95fmBYutCU1qKmwOB1qm17bm6laXZ5mpy4zZjdoJiF8X5oboFhaqJayomdjsPUmKWjlMnusm93rpam7J6IiaqixISui6Civueyp5%2BtXbCqbISHY12AjJbZnp%2FC7rCZZL5mbbFweX5gWLrQlNaipsDgdapte25vpWl2eZqcuM2Y3aCYhfF%2BaG94YWqiWsqJq5%2FMxm7Qnp%2FQ4Ihvoqmhrd50iMGsmtOxmN2wor7ubZmorZz9Jq%2Byt6pQrcKf2a9TvpvAma5op5%2FpmsDBmJHGhIPPsKbM3MBUobSaoTzmw7OgoHfCU9yilsLdsqZcmllaqm59cYmSutal3axTweDAqKW2lp7oWa69qk28zZjRAODT4LanXKukp5mvrrqmn3fFmIqPV32sgmRfmJqt7KiuwVeSw8aaLeqpwuTAVJ1op5%2Fcnq%2BzqU2phVOccmOAzbKXsbqoqZmdssGrlsXCl9ldlMzubZmorZz9Jq%2Byt6pNutCgirOUyeq%2FVKCtVYydWX%2BDZ1CnxqbdrJTQm7Kgoa%2F45%2B%2BetsFXjnfTmM2ilcLtbYZgaGhxrlyfs5qiydSiiqGY0O%2B2op2spFraqMBunJm8yPYXs5jG7m2Xq7VVsNqlvMBXkbyBhY5dZpSwyaR3xLG2q2l%2Ff2Rdi45jm5FjjbV9ZHZ4ZZS0&wt=json&tp_funcao_consulta=0&draw=2&columns[0][data]=0&columns[0][name]=mes_ano_formatado&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=1&columns[1][name]=(coalesce(v1372%2C0)%2Bcoalesce(v1380%2C0)%2Bcoalesce(v1388%2C0)%2Bcoalesce&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=2&columns[2][name]=(coalesce(v1373%2C0)%2Bcoalesce(v1381%2C0)%2Bcoalesce(v1389%2C0)%2Bcoalesce&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=3147483647&search[value]=&search[regex]=false&export=1&export_data_comma=1&export_tipo=csv&"
    }
]

if __name__ == "__main__":
    print(" Iniciando Carga HISTÓRICA (Auxílio Brasil)...")
    dfs = [processar_pab_legacy(c) for c in CONFIG_HISTORICO]
    df_final = pd.concat([d for d in dfs if not d.empty], ignore_index=True)
    
    if not df_final.empty:
        # ATENÇÃO: Aqui usamos 'append' para não apagar o que já existe (ou 'replace' se for a primeira vez)
        print(f"\n Enviando {len(df_final)} linhas de histórico para o BigQuery...")
        utils.subir_para_bigquery(df=df_final, dataset=DATASET_ID, tabela=TABELA_ID, if_exists='append')
    else:
        print("⚠️ Nada extraído.")