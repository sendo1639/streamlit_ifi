# Monitor de Economia IFI — Contexto do Projeto

Dashboard Streamlit + pipeline de ETL Python + BigQuery, dando suporte à
produção do RAF (Relatório de Acompanhamento Fiscal) da IFI. Duas grandes
frentes ativas: sustentabilidade das estatais federais, e reestruturação
do monitor de indicadores macroeconômicos.

## Estrutura de pastas

```
monitor_economia_ifi/
├── .github/workflows/           # Pipeline automatizado (GitHub Actions)
├── backend_etl/
│   ├── scripts/
│   │   ├── estatais/             # ETLs de dados das estatais (SIEST, SIGA Brasil)
│   │   ├── fiscal/                # ETLs fiscais (RTN etc.)
│   │   ├── macro/                  # ETLs macroeconômicos (BCB, ANBIMA, Focus, PTAX)
│   │   ├── social/                 # ETLs sociais (Bolsa Família/CadÚnico, Auxílio Brasil)
│   │   └── utils.py                 # Autenticação BigQuery + subir_para_bigquery()
│   └── data/
│       ├── backup/
│       ├── processed/
│       ├── raw/
│       └── historico_auxilio_brasil_congelado.csv
├── frontend_dashboard/
│   └── pages/                       # 01_Macroeconomia.py, 04_Estatais.py, 05_Estatais_2025.py, ...
├── data/
├── notebooks/
├── ambiente/
├── requirements.txt
├── service_account.json              # Credencial BigQuery — confirmar que está no .gitignore
└── exportar_serie_sustentabilidade.py
```

## Infraestrutura crítica — BigQuery Sandbox

- Roda no plano **Sandbox** (sem conta de faturamento vinculada).
- Toda tabela tem expiração **imutável de 60 dias** desde a **criação** — não dá
  pra remover nem estender sem billing.
- **Nenhuma carga reseta esse relógio** (confirmado pelos metadados em
  24/09/2026): nem `append`, nem `if_exists='replace'` do pandas-gbq, nem
  `WRITE_TRUNCATE` — os dois últimos sobrescrevem os dados mas preservam o
  objeto. A regra antiga ("replace reseta") estava **errada**. Só recriar a
  tabela reseta: DROP + CREATE, ou `CREATE OR REPLACE TABLE ... AS SELECT`.
- **Já perdemos dados por causa disso**: `anbima_ettj` expirou em jul/2026;
  e as tabelas de estatais em `dados_fiscais` (`sest_estatais`,
  `estatais_2025`, `siga_brasil_dependentes`) **não existem mais** em
  24/09/2026 — o renovador só varria `dados_macroeconomicos`.
- Mitigação: `backend_etl/scripts/macro/renovar_tabelas_bigquery.py` roda
  como 1º passo do `.yml` e, desde 24/09/2026, varre **todos os datasets**
  do projeto, renovando (copia → apaga → recria) qualquer tabela a ≤5 dias
  de expirar. Em 24/09 salvou `base_consolidada_pbf_cadun` (expiraria 27/09).
  Backups CSV de social e RTN em `data/backup/*_20260924.csv`.
- Limite do Sandbox: 10GB armazenamento, 1TB consulta/mês — longe de ser
  um problema no volume atual (~2,5 milhões de linhas no Focus, por ex.).

## Frente 1 — Estatais (RAF julho 2026)

**Status: maduro no código, mas as TABELAS EXPIRARAM** — `sest_estatais`,
`estatais_2025` e `siga_brasil_dependentes` não existem no BigQuery em
24/09/2026; as páginas 04 e 05 estão sem dado. Os ETLs de estatais não estão
no `.yml`: precisam ser rodados localmente para recriar as tabelas (o
renovador as protege daí em diante).

- `04_Estatais.py` — histórico anual 2008–2024, rubricas de 6 dígitos.
- `05_Estatais_2025.py` — trimestral 2025+, rubricas de 9 dígitos
  (estrutura de contas diferente da anual — não presumir que os códigos
  se correspondem sem checar).
- Aba central: "📉 Sustentabilidade", com Bloco A (não dependentes) e
  Bloco B (dependentes).
- Indicadores: Margem_Op (LARF/RL), Margem_Liq (LLE/RL), RF_RL_pct (RF/RL),
  FCO_LLE (FCO/LLE); para dependentes, "suficiência" = FCO + Subvenção
  para Custeio.
- Achados centrais: INFRAERO e EMGEPRON mascaram déficit operacional com
  receita financeira; ECT (Correios) tem déficit exposto sem colchão;
  CODEVASF, INFRA S.A., EBC e AMAZUL têm subvenção insuficiente em 2025.
- Descoberta metodológica importante: o SIEST classifica Subvenção para
  Custeio como atividade de **financiamento**, não operacional — o FCO
  no banco de dados já vem líquido do subsídio.
- `exportar_serie_sustentabilidade.py` gera a série 2008–2025 completa em
  Excel, formato long, 26 indicadores.
- Bugs de dado já corrigidos: duplicação ENBPar (grupo vs. individual,
  inflava ~27x), case-sensitivity do GRUPO NAV BRASIL, código AFAC
  errado (330019000 → 330031000 corrigido).

## Frente 2 — Macroeconomia (reestruturação em andamento)

**Status: backend COMPLETO (BCB, ANBIMA, IBGE) e no pipeline (24/09/2026) —
a página do Streamlit AINDA NÃO foi reescrita.**

Objetivo: reorganizar `01_Macroeconomia.py` por **fonte** de dado (BCB,
IBGE, ANBIMA) em vez de por tema. Foco atual do projeto.

O `python-bcb` **não é mais usado**: a 0.4.0 converte datas ISO do PTAX
para `7/13/2026`, que a API aceita mas responde vazio. PTAX e Focus chamam
a API Olinda direto via `requests`. Atenção: o servidor Olinda **não
decodifica `+` como espaço** — URLs de `$filter` montadas à mão com `%20`.

| Fonte | Tabela(s) | Status (validado em 24/09/2026) |
|---|---|---|
| SGS (BCB) | `banco_central_sgs` | ✅ `etl_bcb.py` diário, replace. Agora com retry por bloco, série que falha mantém a versão anterior (antes sumia em silêncio — a Meta Selic tinha perdido 1999), corte de datas futuras (a 432 vinha projetada até o próximo Copom) |
| Focus (BCB) | `focus_expectativas_anuais`, `_mensais`, `focus_inflacao_12meses` | ✅ `etl_focus.py` diário, **incremental**: recoleta as 2 últimas semanas e mescla via `CREATE OR REPLACE TABLE` (staging guarda só a coleta do dia). `--completo` recarrega tudo. Idempotente (2ª execução = +0); valores do PDF 17/07 preservados. Estava parado em 17/07 |
| PTAX (BCB) | `ptax_cotacoes` (+ `_staging` com todos os boletins) | ✅ **Bug resolvido** — era o python-bcb (ver acima), não janela nem MM/DD. `etl_ptax.py` diário, recarga completa (USD/EUR desde 2000, 1 chamada por moeda). Só boletim `Fechamento` exato, 1 linha por (moeda, data). Bate 100% com SGS 1 em 6.714 dias |
| ANBIMA (ETTJ) | `anbima_ettj` | ✅ diário, append incremental, 48 dias úteis contínuos desde 17/07/2026. `anbima_ettj_staging` guarda 25–29/mai (resto do que expirou) |
| IBGE (SIDRA) | `ibge_sidra` (formato longo, ~222 mil linhas) | ✅ `etl_ibge.py` diário, recarga completa; tabela que falha mantém a versão anterior. API direta (sem `sidrapy` — ele não trata o limite de **50 mil valores por consulta**; o ETL fatia por período). 18 tabelas, códigos validados nos metadados: IPCA 1737 (geral desde 1979) e 7060 (457 aberturas desde 2020, com pesos), IPCA-15 3065, INPC 1736, PNAD mensal 6381/6441/8513/6318/6390/6392 (desocupação, subutilização, informalidade, população, rendimento e massa), PIM 8888, PMS 5906, PMC 8880/8881 (base 2022=100), PIB 1620/1621/5932/1846. Conferido: IPCA bate 100% com SGS 433/13522; pesos dos grupos somam 100 |

| Calendário | `calendario_divulgacoes` (~310 eventos) | ✅ `etl_calendario.py` diário, recarga completa, janela −400/+460 dias. **IBGE**: API `servicodados.ibge.gov.br/api/v3/calendario` (hora vem em UTC — convertida para Brasília; o IBGE só publica a agenda ~4 meses à frente). **BCB**: feeds iCalendar oficiais `bcb.gov.br/api/exportarics/sitebcb/agendaics?lista=...` (lista em `bcb.gov.br/acessoinformacao/calendariobc_ics`): Copom (reuniões até dez/2027, agrupadas em 1 evento no dia da decisão; atas), Focus, estatísticas fiscais, setor externo, crédito, macroeconômicas. Coluna `dado_no_monitor` liga o evento à tabela do BigQuery |

Colunas úteis para o front: PTAX tem `data` (dia) além de `dataHoraCotacao`;
Focus mantém os nomes camelCase da API (`Data` DATETIME, `DataReferencia`
STRING, `baseCalculo` 0/1). `ibge_sidra`: `data` = 1º dia do **último** mês do
período (trimestral 2026T2 → 2026-06-01; trimestre móvel mai-jun-jul → 2026-07-01);
filtrar por `tabela` + `variavel_codigo` (+ `categoria` quando houver).

SGS também tem (desde 24/09/2026) aberturas e núcleos do IPCA, meta de inflação,
Selic mensal e juros/ICC/spread do crédito — nomes conferidos no serviço
FachadaWSSGS do BCB e valores em 12 meses conferidos contra o RAF nº 113.

### Frontend — reformulação de `01_Macroeconomia.py` (em andamento)

Desenho baseado na leitura dos RAFs de 2026 (como a IFI usa os dados: mediana
do Focus como consenso, comparação PLOA × IFI × Focus, juro real ex-ante,
IPCA × média dos núcleos × meta, desemprego × participação, contribuições do PIB).
Estrutura por FONTE: Panorama | IBGE | Banco Central | ANBIMA | Calendário | Explorar.

Código: a página só monta as abas; cada aba é um módulo em
`frontend_dashboard/macro/` (`panorama.py`, `calendario.py`, `anbima.py`...),
com `catalogo.py` (todo código de série — nunca `str.contains` no nome),
`visual.py` (gráfico padrão IFI, pt-BR, fonte no rodapé, download Excel) e
`calculos.py` (acumulado 12m COMPOSTO — a página antiga somava; juro real).
Consultas em `query_engine.py` (funções `sql_*` + `carregar_em_paralelo`).

Status (24/09/2026): **Panorama, IBGE, Banco Central, ANBIMA e Calendário prontos**;
falta só "Explorar e baixar".
- BCB: quadro no formato do Relatório Focus (há 4 sem./1 sem./hoje, ▲▼= com
  semanas seguidas, comparação de SEXTA a sexta — o Focus tem posição DIÁRIA),
  seletor de data (reproduz o "Focus de 04/09" do RAF 116 — conferido), evolução
  da mediana, IPCA esperado 12m; Selic + juro real ex-ante/ex-post + decisões do
  Copom; crédito; PTAX; IBC-Br.
- IBGE: IPCA × média de 5 núcleos (EX0, EX3, MS, DP, P55) × meta com intervalo;
  aberturas 12m; contribuição dos grupos no mês (soma = índice geral, conferido);
  IPCA-15/INPC; desemprego × participação; informalidade/subutilização; rendimento
  e massa real; PIM/PMS/PMC; PIB com contribuições em 4 tri (`contribuicoes_pib`,
  até 0,1 p.p. da Tab. 2 do RAF 113).
Desempenho: abas "preguiçosas" (`st.tabs(on_change="rerun")` + `.open`, Streamlit
1.56 da rede) — só a aba aberta consulta o BigQuery; consultas de cada aba em
paralelo e com cache de 1h. A abertura do Dashboard.bat leva ~1-2 min só
importando bibliotecas do Python da rede (`U:\softwares\python_313`) — custo
pré-existente, independe da página.
Teste: `streamlit.testing.v1.AppTest` com o Python da rede; trocar aba via
`at.session_state["abas_macro"] = "🇧🇷 IBGE"` (sub-abas: `abas_bcb`, `abas_ibge`).

**Pendente:** confirmar no 1º run do GitHub Actions que Olinda (BCB) e
SIDRA (IBGE) não bloqueiam IP de datacenter; **reescrever
`01_Macroeconomia.py`** — o `query_engine.py` ainda não lê Focus, PTAX nem IBGE.
Os `explorar_*.py` em `frontend_dashboard/pages/` são scripts de teste que
aparecem como páginas no menu — tirar de lá.

## Frente 3 — Social (Bolsa Família / CadÚnico / Auxílio Brasil)

**Status: PROBLEMA ATIVO, não resolvido — apenas contornado.**

- `etl_social.py` busca Bolsa Família/CadÚnico ao vivo de
  `aplicacoes.mds.gov.br`, diário, `if_exists='replace'`.
- `etl_historico_pab_ae.py` reanexa (`append`) o histórico do Auxílio
  Brasil (programa extinto) depois do replace acima. Reescrito pra ler
  de `backend_etl/data/historico_auxilio_brasil_congelado.csv` (estático)
  em vez de buscar da web, porque a fonte original bloqueava o GitHub
  Actions.
- `congelar_historico_pab.py` gerou esse CSV — ferramenta de uso único,
  não roda no pipeline automático.
- **`etl_social.py` continua bloqueado no GitHub Actions** — mesmo erro
  de conexão do Auxílio Brasil, mas essa fonte não pode ser "congelada"
  (dado vivo, muda todo mês). Aplicamos `continue-on-error: true` no
  `.yml` só pra não travar os ETLs seguintes — **isso não é correção**,
  é só evitar que quebre o resto do pipeline. A tabela
  `base_consolidada_pbf_cadun` está sem atualizar de verdade.
- Hipótese: bloqueio de IP de datacenter (faixa do GitHub Actions),
  afetando múltiplos domínios `.gov.br` — não um site específico fora
  do ar.
- Rotas não tentadas: cabeçalhos de User-Agent tipo navegador (como o
  `etl_anbima.py` já faz), ou runner auto-hospedado na rede da IFI.

## Regras de trabalho aprendidas nesse projeto

- **Nunca assumir um código de rubrica/série/coluna sem validar contra
  dado real primeiro.** Vários bugs nesse projeto vieram de códigos
  plausíveis mas errados (AFAC, dólar compra/venda, Selic anualizada).
- **Testar volume pequeno antes de coletar histórico completo.** O
  `etl_focus.py` quebrou por timeout porque tentamos o histórico inteiro
  sem testar antes.
- **Quando uma API "retorna vazio", chamar a URL crua antes de culpar a
  API.** O bug do PTAX era da biblioteca wrapper, não do BCB.
- **Nenhuma carga reseta a expiração do Sandbox** — só recriar a tabela.
  Toda tabela depende do renovador; conferir que ele varre o dataset.
- **Scripts de ETL saem com código 1 em falha** (macro, desde 24/09/2026)
  e cada passo do `.yml` tem `if: always()`: o run fica vermelho no GitHub,
  mas os ETLs seguintes rodam.
- **Rodar ETLs de rede sempre localmente, nunca em ambiente de nuvem**
  (VM do GitHub Actions, ou execução em nuvem do Claude Code) — sites
  `.gov.br` têm bloqueado repetidamente faixas de IP de datacenter.
- **Diferenciar "contornado" de "resolvido"** ao reportar status —
  `continue-on-error` e workarounds temporários devem ficar marcados
  como pendência real, não como problema fechado.
